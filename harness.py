"""
MicroHarness — Tool-based Memory 版本（v3.3）
============================================
基于 LangGraph 的最小可运行聊天 Agent。

配置：编辑 .env 文件即可，无需改动代码。
支持多 Provider：openai / deepseek / kimi / minimax / qwen / glm

架构层级（v3.3 更新）：
  [User Input]
       ↓
  [agent_node]   ← 系统提示（含 Tool 说明）
       ↓
  [判断] 是否需要调用 memory_search？
       ↓ 是
  [memory_tool]  ← 召回相关记忆
       ↓
  [二次推理]     ← 系统提示 + 记忆上下文
       ↓
  [memory]       ← 双层记忆系统（存储用）：
                   - 短期记忆：最近10轮AI生成的对话摘要（memory.json）
                   - 长期记忆：向量数据库语义搜索（chroma_db）

工作流程（v3.3 更新）：
  1. 对话前：加载系统提示（含 Tool 使用说明）
  2. AI 判断：是否需要调用 memory_search？
  3. 如需要：召回记忆 → 二次推理
  4. 如不需要：直接回答
  5. 对话后：AI生成摘要 → 存入短期记忆
  6. 超过10轮：最早摘要以完整对话向量化 → 移入长期记忆

用法：
  python harness.py
"""

import threading
from typing import Annotated

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

import config
from memory import save_conversation_with_memory, get_memory_stats
from prompts import get_system_prompt_with_memory_tool, get_system_prompt
from logger import log_query_with_memory
from tools.memory_tool import get_memory_tool, MemoryTool


# ──────────────────────────────────────────────────
# State 定义
# ──────────────────────────────────────────────────

class HarnessState(TypedDict):
    messages: Annotated[list, add_messages]
    step_count: int
    user_input: str  # 保存原始用户输入
    memory_context: str  # 召回的记忆上下文（如果有）


# ──────────────────────────────────────────────────
# 模型初始化
# ──────────────────────────────────────────────────

llm = config.get_llm(config.MAIN_MODEL)
memory_tool = get_memory_tool()


# ──────────────────────────────────────────────────
# Nodes
# ──────────────────────────────────────────────────

def agent_node(state: HarnessState) -> dict:
    """
    模型推理节点（v3.3 Tool-based 版本）：
    1. 首次推理：系统提示 + 用户输入（无记忆）
    2. 解析响应：检查是否包含 tool_call
    3. 如需要：召回记忆 → 二次推理
    4. 如不需要：直接返回结果
    """
    user_input = state["user_input"]
    
    # 获取包含 Tool 说明的系统提示
    system_prompt = get_system_prompt_with_memory_tool()
    
    # 第一阶段：让 AI 判断是否需要记忆
    print(f"\n[HARNESS] Step {state['step_count'] + 1}/{config.MAX_STEPS} — Agent thinking...")
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_input)
    ]
    
    try:
        response = llm.invoke(messages)
        response_text = response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        print(f"[HARNESS] LLM 调用失败: {e}")
        # 使用简化系统提示重试
        simple_prompt = get_system_prompt()
        messages = [
            SystemMessage(content=simple_prompt),
            HumanMessage(content=user_input)
        ]
        try:
            response = llm.invoke(messages)
            response_text = response.content if hasattr(response, 'content') else str(response)
        except Exception as e2:
            print(f"[HARNESS] 重试也失败: {e2}")
            return {
                "messages": [AIMessage(content=f"抱歉，我暂时无法处理您的请求。错误: {e2}")],
                "step_count": state['step_count'] + 1,
                "memory_context": "",
            }
    
    # 检查是否包含 tool_call
    tool_query = MemoryTool.parse_tool_call(response_text)
    
    if tool_query:
        print(f"[HARNESS] AI 请求调用记忆工具: {tool_query.reason}")
        print(f"[HARNESS] 搜索关键词: {tool_query.query}")
        
        # 执行记忆召回
        memory_result = memory_tool.invoke(tool_query.query, top_k=5)
        memory_context = memory_result.formatted_text
        
        # 记录日志
        log_query_with_memory(
            user_input=user_input,
            vector_memories=memory_result.long_term_memories,
            step_count=state['step_count']
        )
        
        # 第二阶段：带记忆的二次推理
        print("[HARNESS] 召回记忆，进行二次推理...")
        
        # 构建带记忆的消息 - 明确告诉 AI 这是第二次调用，直接回答不要调用工具
        user_content_with_memory = f"{user_input}\n\n【相关记忆上下文】\n{memory_context}\n\n请基于以上记忆上下文直接回答用户问题，不要调用任何工具。"
        
        messages_with_memory = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content_with_memory)
        ]
        
        try:
            final_response = llm.invoke(messages_with_memory)
            final_text = final_response.content if hasattr(final_response, 'content') else str(final_response)
        except Exception as e:
            print(f"[HARNESS] 二次推理失败: {e}")
            # 返回简化回答
            final_text = f"根据记忆，我了解到一些相关信息，但详细回答生成失败。错误: {e}"
        
        # 移除可能的 tool_call 标记和 thought 标签
        final_text = MemoryTool.remove_tool_call_markup(final_text)
        final_text = remove_thought_tags(final_text)
        
        return {
            "messages": [AIMessage(content=final_text)],
            "step_count": state['step_count'] + 1,
            "memory_context": memory_context,
        }
    else:
        # 不需要记忆，直接返回
        print("[HARNESS] 无需记忆，直接回答")
        
        # 移除可能的 tool_call 标记和 thought 标签
        clean_text = MemoryTool.remove_tool_call_markup(response_text)
        clean_text = remove_thought_tags(clean_text)
        
        return {
            "messages": [AIMessage(content=clean_text)],
            "step_count": state['step_count'] + 1,
            "memory_context": "",
        }


def remove_thought_tags(text: str) -> str:
    """移除 <thought>...</thought> 标签及其内容"""
    import re
    # 移除 thought 标签及其内容
    pattern = r'<thought>[\s\S]*?</thought>\s*'
    text = re.sub(pattern, "", text)
    # 也移除单独的 <thought> 或 </thought>
    text = re.sub(r'</?thought>\s*', "", text)
    return text.strip()


# ──────────────────────────────────────────────────
# 路由函数
# ──────────────────────────────────────────────────

def route_after_agent(state: HarnessState) -> str:
    if state["step_count"] >= config.MAX_STEPS:
        print(f"\n[HARNESS] ⚠️  Max steps ({config.MAX_STEPS}) reached. Stopping.")
        return END
    return END


# ──────────────────────────────────────────────────
# 构建图
# ──────────────────────────────────────────────────

def build_harness():
    graph = StateGraph(HarnessState)
    graph.add_node("agent", agent_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", route_after_agent)
    return graph.compile()


# ──────────────────────────────────────────────────
# 主程序
# ──────────────────────────────────────────────────

def print_welcome():
    """打印欢迎信息"""
    print("=" * 55)
    print("  MicroHarness  —  LangGraph Chat Agent (v3.3)")
    print("  新特性: Tool-based Memory（AI 自主决策）")
    print(f"  Provider    : {config.PROVIDER}")
    print(f"  Main Model  : {config.MAIN_MODEL}")
    print(f"  Memory Model: {config.MEMORY_MODEL}")
    print(f"  Max Steps   : {config.MAX_STEPS}")
    print("=" * 55)

    # 显示记忆统计
    stats = get_memory_stats()
    if stats["total_memories"] > 0:
        print(f"\n[HARNESS] 记忆系统已加载:")
        short_stats = stats['short_term']
        print(f"          - 短期记忆: {short_stats['total']} 条 (全文{short_stats['full']} + 摘要{short_stats['summary']})")
        print(f"          - 长期记忆: {stats['long_term_count']} 条")
        print(f"\n[HARNESS] AI 将根据需要自主决定是否调用记忆工具")
    else:
        print("\n[HARNESS] 记忆系统为空，开始新的对话。")


def process_single_conversation(harness, user_input: str) -> str:
    """
    处理单轮对话
    
    Returns:
        助手的回复内容
    """
    init_state: HarnessState = {
        "messages": [HumanMessage(content=user_input)],
        "step_count": 0,
        "user_input": user_input,
        "memory_context": "",
    }

    print("\n[HARNESS] Starting...\n")
    final_state = harness.invoke(init_state)

    final_messages = final_state["messages"]
    final_response = next(
        (m for m in reversed(final_messages)
         if hasattr(m, "content") and isinstance(m.content, str) and m.content.strip()),
        None
    )

    assistant_reply = final_response.content if final_response else "(No response)"

    print("\n" + "=" * 55)
    print("  FINAL RESPONSE")
    print("=" * 55)
    print(assistant_reply)
    print("=" * 55)
    print(f"  Total steps used: {final_state['step_count']}/{config.MAX_STEPS}")
    if final_state.get("memory_context"):
        print("  Memory used: ✓")
    else:
        print("  Memory used: ✗")
    print("=" * 55)

    # 保存对话到记忆系统（快速保存，不等待AI摘要生成）
    # AI摘要生成在后台进行，不阻塞用户输入
    print("\n[HARNESS] 对话已记录，AI摘要后台生成中...")
    
    def save_memory_async():
        try:
            # 后台线程使用 verbose=False，避免打印干扰用户输入
            save_conversation_with_memory(user_input, assistant_reply, verbose=False)
        except Exception:
            # 静默失败，不影响用户体验
            pass
    
    # 启动后台线程保存记忆（daemon=True 确保不会阻塞程序退出）
    save_thread = threading.Thread(target=save_memory_async, daemon=True)
    save_thread.start()
    
    return assistant_reply


def main():
    config.validate()
    
    print_welcome()
    
    harness = build_harness()

    print("\n输入你的消息，示例：")
    print("  • 你好，请介绍一下你自己")
    print("  • 帮我写一个 Python 函数计算斐波那契数列")
    print("  • 还记得我们上次聊过什么吗？（会触发记忆工具）")
    print("  • 输入 'exit' 或 'quit' 退出程序")
    print()

    # 主循环
    while True:
        try:
            user_input = input("\nYou: ").strip()
        except EOFError:
            print("\n[HARNESS] 输入结束，再见！")
            break
        
        # 检查退出命令
        if user_input.lower() in ("exit", "quit", "退出", "q"):
            print("\n[HARNESS] 感谢使用，再见！")
            break
        
        if not user_input:
            print("[HARNESS] 输入为空，请重新输入。")
            continue

        # 处理对话
        process_single_conversation(harness, user_input)
        
        # 打印分隔线
        print("\n" + "-" * 55)


if __name__ == "__main__":
    main()
