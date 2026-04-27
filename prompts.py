"""
Prompt Management Module
========================
Harness 的提示管理层 —— 负责组装系统提示和上下文。

v3.3 更新：记忆系统改为 Tool 调用模式
- AI 自主判断是否需要召回记忆
- 通过 tool_call 标记触发记忆检索
- 默认不自动加载记忆，保持上下文纯净

加载顺序：SystemPrompt → Rules → UserPrompt → ToolList
"""

from pathlib import Path

from tools.memory_tool import MemoryTool

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


def get_system_prompt() -> str:
    """
    获取纯净的系统提示（不含自动记忆上下文）。
    
    v3.3 更新：不再自动召回记忆，改为 AI 自主决策是否调用 memory_search 工具
    
    Returns:
        系统提示文本
    """
    return load_system_prompt_base()


def get_system_prompt_with_memory_tool() -> str:
    """
    获取包含记忆工具说明的系统提示。
    
    在基础系统提示后追加 MemoryTool 的使用说明。
    
    Returns:
        完整的系统提示（含工具说明）
    """
    base_prompt = load_system_prompt_base()
    tool_description = MemoryTool.DESCRIPTION
    
    return f"{base_prompt}\n\n{tool_description}"


# 保留旧函数以兼容现有代码（标记为废弃）
def get_system_prompt_legacy(user_input: str = "") -> tuple[str, str, list[dict]]:
    """
    [废弃] 旧版系统提示函数，自动召回记忆
    
    保留此函数以确保向后兼容，新项目应使用 get_system_prompt()
    """
    from memory import build_context_with_memory_detailed, get_memory_stats
    
    system_prompt = load_system_prompt_base()
    
    memory_context = ""
    vector_memories = []
    if user_input:
        memory_context, vector_memories = build_context_with_memory_detailed(user_input)
    
    stats = get_memory_stats()
    if stats["total_memories"] > 0:
        short_term_stats = stats['short_term']
        print(f"[HARNESS] 记忆加载: 短期摘要{short_term_stats['summary']}条, 长期记忆{stats['long_term_count']}条")
    
    return system_prompt, memory_context, vector_memories
