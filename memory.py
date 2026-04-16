"""
Long-Term Memory Module
=======================
Harness 的长期记忆层 —— 跨会话持久化存储关键信息。

工作流程：
  会话结束 → 模型提炼本次要点 → 写入 memory.json
  下次启动 → 读取 memory.json → 注入系统提示
"""

import json
import os
from datetime import datetime

from langchain_core.messages import HumanMessage

import config

MEMORY_FILE = os.path.join(os.path.dirname(__file__), "memory.json")
MAX_MEMORIES = 20


def load_memories() -> list[dict]:
    """读取持久化记忆，文件不存在时返回空列表"""
    if not os.path.exists(MEMORY_FILE):
        return []
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def save_memories(memories: list[dict]) -> None:
    """写入持久化记忆，超过上限时裁剪最旧的条目"""
    memories = memories[-MAX_MEMORIES:]
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memories, f, ensure_ascii=False, indent=2)


def format_memories_for_prompt(memories: list[dict]) -> str:
    """把记忆列表格式化为可注入提示的字符串，只取最近 5 条"""
    if not memories:
        return ""
    lines = ["## Long-Term Memory (from previous sessions)\n"]
    for m in memories[-5:]:
        lines.append(f"- [{m['date']}] {m['summary']}")
    return "\n".join(lines)


def extract_and_save_memory(messages: list, task: str) -> str:
    """
    会话结束后，调用模型提炼本次会话的关键信息，写入持久化存储。
    使用 config.MEMORY_MODEL，通过 config.get_llm() 支持所有 provider。
    """
    history_text = []
    for m in messages:
        role = getattr(m, "type", "unknown")
        content = m.content if isinstance(m.content, str) else str(m.content)
        if content.strip():
            history_text.append(f"[{role}]: {content[:500]}")

    history_str = "\n".join(history_text[-20:])

    extract_prompt = f"""你是一个记忆提取助手。

根据本次会话内容，提取一句简洁的总结（最多100字），包含以下信息：
- 用户下达了什么任务，给出了什么关键信息
- 回答中给出的哪些关键建议和措施规划
- 任何重要的结果或错误

任务: {task}

会话历史:
{history_str}

只回复总结句子，不要添加其他内容。"""

    llm = config.get_llm(config.MEMORY_MODEL)
    response = llm.invoke([HumanMessage(content=extract_prompt)])
    summary = response.content.strip()

    memories = load_memories()
    memories.append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "task": task[:100],
        "summary": summary,
    })
    save_memories(memories)

    return summary
