"""
MicroHarness — 纯聊天版本（v3.1 AI摘要记忆系统）
================================================
基于 LangGraph 的最小可运行聊天 Agent。

配置：编辑 .env 文件即可，无需改动代码。
支持多 Provider：openai / deepseek / kimi / minimax / qwen / glm

架构层级：
  [User Input]
       ↓
  [agent_node]   ← 系统提示 + 相关记忆召回 + 近期对话摘要
       ↓
  [memory]       ← 双层记忆系统：
                   - 短期记忆：最近10轮AI生成的对话摘要（memory.json）
                   - 长期记忆：向量数据库语义搜索（chroma_db）

工作流程：
  1. 对话前：召回相关历史 + 加载近期摘要 → 组装Context
  2. 对话后：AI生成摘要 → 存入短期记忆
  3. 超过10轮：最早摘要以完整对话向量化 → 移入长期记忆

用法：
  python harness.py
"""

from typing import Annotated

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

import config
from memory import save_conversation_with_memory, get_memory_stats
from prompts import get_system_prompt


# ──────────────────────────────────────────────────
# State 定义
# ──────────────────────────────────────────────────

class HarnessState(TypedDict):
    messages: Annotated[list, add_messages]
    step_count: int
    user_input: str  # 保存原始用户输入，用于记忆召回


# ──────────────────────────────────────────────────
# 模型初始化（通过 config.get_llm 按 provider 构建）
# ──────────────────────────────────────────────────

llm = config.get_llm(config.MAIN_MODEL)


# ──────────────────────────────────────────────────
# Nodes
# ──────────────────────────────────────────────────

def agent_node(state: HarnessState) -> dict:
    """
    模型推理节点：
    1. 根据用户输入召回相关记忆
    2. 组装系统提示（含记忆上下文）
    3. 模型推理
    """
    user_input = state["user_input"]
    
    # 获取包含记忆上下文的系统提示
    system = SystemMessage(content=get_system_prompt(user_input))
    messages = [system] + state["messages"]

    print(f"\n[HARNESS] Step {state['step_count'] + 1}/{config.MAX_STEPS} — Agent thinking...")
    response = llm.invoke(messages)

    return {
        "messages": [response],
        "step_count": state["step_count"] + 1,
    }


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
    print("  MicroHarness  —  LangGraph Chat Agent (v3.1)")
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
    print("=" * 55)

    # 保存对话到记忆系统（自动生成AI摘要）
    print("\n[HARNESS] 正在生成对话摘要并保存...")
    save_conversation_with_memory(user_input, assistant_reply)
    
    # 显示更新后的记忆统计
    new_stats = get_memory_stats()
    short_stats = new_stats['short_term']
    print(f"[HARNESS] 记忆已更新: 短期{short_stats['total']}条(全文{short_stats['full']}+摘要{short_stats['summary']}), 长期{new_stats['long_term_count']}条\n")
    
    return assistant_reply


def main():
    config.validate()
    
    print_welcome()
    
    harness = build_harness()

    print("\n输入你的消息，示例：")
    print("  • 你好，请介绍一下你自己")
    print("  • 帮我写一个 Python 函数计算斐波那契数列")
    print("  • 还记得我们上次聊过什么吗？")
    print("  • 输入 'exit' 或 'quit' 退出程序")
    print()

    # 主循环：持续对话直到用户输入退出命令
    while True:
        user_input = input("You: ").strip()
        
        # 检查退出命令
        if user_input.lower() in ("exit", "quit", "退出", "q"):
            print("\n[HARNESS] 感谢使用，再见！")
            break
        
        if not user_input:
            print("[HARNESS] 输入为空，请重新输入。")
            continue

        # 处理对话
        process_single_conversation(harness, user_input)
        
        # 打印分隔线，准备下一轮
        print("-" * 55)
        print()


if __name__ == "__main__":
    main()
