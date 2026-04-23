"""
日志模块
========
记录用户提问和向量库召回内容，用于调试和分析对话流程。

功能：
- 记录用户原始提问
- 记录从向量库召回的相关记忆
- 支持按时间分片存储
- 支持日志轮转和清理
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

# 日志文件路径
LOG_DIR = Path(__file__).parent / "logs"
LOG_FILE = LOG_DIR / "query_logs.json"

# 配置
MAX_LOG_ENTRIES = 1000  # 最大保留条目数
MAX_LOG_DAYS = 30  # 日志保留天数


def _ensure_log_dir():
    """确保日志目录存在"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _load_logs() -> list[dict]:
    """加载现有日志"""
    if not LOG_FILE.exists():
        return []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_logs(logs: list[dict]):
    """保存日志到文件"""
    _ensure_log_dir()
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)


def log_query_with_memory(
    user_input: str,
    vector_memories: list[dict],
    session_id: Optional[str] = None,
    step_count: int = 0
) -> None:
    """
    记录用户提问和向量库召回内容

    Args:
        user_input: 用户原始提问
        vector_memories: 从向量库召回的记忆列表
        session_id: 会话ID（可选）
        step_count: 当前步骤计数
    """
    logs = _load_logs()

    entry = {
        "timestamp": datetime.now().isoformat(),
        "session_id": session_id or "default",
        "step_count": step_count,
        "user_input": user_input,
        "user_input_length": len(user_input),
        "vector_memories": vector_memories,
        "vector_memory_count": len(vector_memories)
    }

    logs.append(entry)

    # 限制日志条目数
    if len(logs) > MAX_LOG_ENTRIES:
        logs = logs[-MAX_LOG_ENTRIES:]

    _save_logs(logs)


def get_log_stats() -> dict:
    """获取日志统计信息"""
    logs = _load_logs()
    if not logs:
        return {"total_entries": 0, "sessions": 0, "avg_input_length": 0, "avg_memory_count": 0}

    sessions = set(log.get("session_id", "default") for log in logs)
    avg_input_length = sum(log.get("user_input_length", 0) for log in logs) / len(logs)
    avg_memory_count = sum(log.get("vector_memory_count", 0) for log in logs) / len(logs)

    return {
        "total_entries": len(logs),
        "sessions": len(sessions),
        "avg_input_length": round(avg_input_length, 2),
        "avg_memory_count": round(avg_memory_count, 2),
        "oldest_timestamp": logs[0].get("timestamp") if logs else None,
        "latest_timestamp": logs[-1].get("timestamp") if logs else None
    }


def get_recent_logs(n: int = 10) -> list[dict]:
    """获取最近 n 条日志"""
    logs = _load_logs()
    return logs[-n:] if n < len(logs) else logs


def get_logs_by_session(session_id: str) -> list[dict]:
    """获取指定会话的所有日志"""
    logs = _load_logs()
    return [log for log in logs if log.get("session_id") == session_id]


def clear_logs() -> None:
    """清空所有日志"""
    if LOG_FILE.exists():
        LOG_FILE.unlink()


def export_logs_to_text(output_path: Optional[str] = None) -> str:
    """导出日志为可读文本格式"""
    logs = _load_logs()
    if not logs:
        return "No logs found."

    lines = ["=" * 60, "Query & Memory 日志导出", "=" * 60, ""]

    for log in logs:
        lines.append(f"时间: {log.get('timestamp', 'N/A')}")
        lines.append(f"会话: {log.get('session_id', 'N/A')}")
        lines.append(f"步骤: {log.get('step_count', 'N/A')}")
        lines.append("-" * 40)
        lines.append("【用户提问】")
        lines.append(log.get("user_input", "(empty)"))
        lines.append("")
        lines.append(f"【向量库召回 - 共{log.get('vector_memory_count', 0)}条】")
        for i, mem in enumerate(log.get("vector_memories", []), 1):
            score = mem.get('score') or mem.get('distance')
            score_str = f"[相关度: {score:.4f}]" if score is not None else ""
            lines.append(f"{i}. [{mem.get('timestamp', 'N/A')}] {score_str}")
            lines.append(f"   {mem.get('text', '')[:200]}...")
        lines.append("=" * 60)
        lines.append("")

    text = "\n".join(lines)

    if output_path:
        Path(output_path).write_text(text, encoding="utf-8")

    return text
