"""
Prompt Management Module
========================
Harness 的提示管理层 —— 负责组装系统提示和上下文。

v3.1 更新：支持AI摘要的短期记忆
- 短期记忆：最近10轮AI生成的对话摘要
- 长期记忆：向量数据库召回的语义相关内容
"""

from memory import build_context_with_memory, get_memory_stats

SYSTEM_PROMPT_BASE = """
你是一个智能助手，能够记住与用户的对话历史。

规则：
- 保持友好、专业的对话风格
- 基于提供的记忆上下文回答用户问题
- 如果记忆中有相关信息，请主动引用
- 如果任务不明确，请主动询问澄清

记忆说明：
- 【近期对话摘要】是最近10轮对话的AI生成摘要
- 【相关历史记忆】是从长期记忆中语义搜索召回的内容
"""


def get_system_prompt(user_input: str = "") -> str:
    """
    组装完整的系统提示。

    结构：
    1. 基础系统提示
    2. 相关历史记忆（从向量数据库召回，包含完整对话内容）
    3. 近期对话摘要（最近10轮，AI生成的摘要）

    Args:
        user_input: 当前用户输入，用于召回相关记忆

    Returns:
        完整的系统提示文本
    """
    parts = [SYSTEM_PROMPT_BASE.strip()]
    
    # 构建包含记忆的上下文
    if user_input:
        memory_context = build_context_with_memory(user_input)
        if memory_context:
            parts.append(memory_context)
    
    full_prompt = "\n\n".join(parts)
    
    # 打印记忆统计信息
    stats = get_memory_stats()
    if stats["total_memories"] > 0:
        short_term_stats = stats['short_term']
        print(f"[HARNESS] 记忆加载: 短期摘要{short_term_stats['summary']}条, 长期记忆{stats['long_term_count']}条")
    
    return full_prompt


def get_simple_system_prompt() -> str:
    """
    获取简化版系统提示（不含记忆上下文）
    用于初始化或测试场景
    """
    return SYSTEM_PROMPT_BASE.strip()
