"""
Prompt Management Module
========================
Harness 的提示管理层 —— 负责组装系统提示和上下文。

v3.1 更新：支持AI摘要的短期记忆
- 短期记忆：最近10轮AI生成的对话摘要
- 长期记忆：向量数据库召回的语义相关内容

v3.2 更新：系统提示从外部markdown文件加载
加载顺序：SystemPrompt → Rules → UserPrompt → ToolList
"""

from pathlib import Path

from memory import build_context_with_memory, get_memory_stats

# System_Prompt 目录路径
SYSTEM_PROMPT_DIR = Path(__file__).parent / "System_Prompt"

# 定义加载顺序
SYSTEM_PROMPT_FILES = [
    "SystemPrompt.md",
    "Rules.md",
    "UserPrompt.md",
    "ToolList.md",
]


def load_markdown_file(filename: str) -> str:
    """从System_Prompt目录加载markdown文件内容"""
    filepath = SYSTEM_PROMPT_DIR / filename
    if not filepath.exists():
        return f"# {filename} 文件不存在\n"
    
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return content if content else f"# {filename} 文件为空\n"
    except Exception as e:
        return f"# 加载 {filename} 失败: {e}\n"


def load_system_prompt_base() -> str:
    """
    从四个markdown文件加载系统提示，按指定顺序拼接
    
    Returns:
        拼接后的完整系统提示文本
    """
    parts = []
    
    for filename in SYSTEM_PROMPT_FILES:
        content = load_markdown_file(filename)
        if content:
            parts.append(content)
    
    return "\n\n".join(parts)


def get_system_prompt(user_input: str = "") -> tuple[str, str]:
    """
    组装系统提示和记忆上下文，返回分离的两部分。

    结构：
    1. 基础系统提示（从外部markdown文件加载）
    2. 记忆上下文（相关历史记忆 + 近期对话记忆）

    Args:
        user_input: 当前用户输入，用于召回相关记忆

    Returns:
        (system_prompt, memory_context) 元组
    """
    # 从外部文件加载系统提示
    system_prompt = load_system_prompt_base()
    
    # 构建记忆上下文（不含系统提示）
    memory_context = ""
    if user_input:
        memory_context = build_context_with_memory(user_input)
    
    # 打印记忆统计信息
    stats = get_memory_stats()
    if stats["total_memories"] > 0:
        short_term_stats = stats['short_term']
        print(f"[HARNESS] 记忆加载: 短期摘要{short_term_stats['summary']}条, 长期记忆{stats['long_term_count']}条")
    
    return system_prompt, memory_context


def get_simple_system_prompt() -> str:
    """
    获取简化版系统提示（不含记忆上下文）
    用于初始化或测试场景
    """
    return load_system_prompt_base()
