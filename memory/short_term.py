"""
短期记忆模块（分层存储版本）
===========================
管理最近10轮对话，采用分层存储策略：
- 最近5轮：全文存储（完整对话内容）
- 6-10轮：AI摘要存储（由MEMORY_MODEL总结）

数据结构：
[
  {
    "timestamp": "2025-01-14 10:30",
    "type": "full",           # "full" 或 "summary"
    "user_msg": "完整用户消息...",
    "assistant_msg": "完整助手回复...",
    "summary": null           # full类型时为空
  },
  {
    "timestamp": "2025-01-14 10:25",
    "type": "summary",
    "user_msg": null,
    "assistant_msg": null,
    "summary": "用户询问Python函数，助手提供了斐波那契数列的实现代码"
  }
]

工作流程：
  新对话进入 → 作为全文存储（位置0）
  如果超过5条 → 第6条开始自动转为AI摘要
  如果超过10条 → 最早的一条向量化 → 移入长期记忆
"""

import json
import os
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, asdict

import config
from langchain_core.messages import HumanMessage

MEMORY_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memory.json")
MAX_SHORT_TERM_ROUNDS = 10
FULL_MEMORY_COUNT = 5  # 前5条为全文存储


@dataclass
class MemoryEntry:
    """单条记忆记录"""
    timestamp: str
    memory_type: str  # "full" 或 "summary"
    user_msg: Optional[str] = None
    assistant_msg: Optional[str] = None
    summary: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "type": self.memory_type,
            "user_msg": self.user_msg,
            "assistant_msg": self.assistant_msg,
            "summary": self.summary
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "MemoryEntry":
        return cls(
            timestamp=data.get("timestamp", ""),
            memory_type=data.get("type", "summary"),
            user_msg=data.get("user_msg"),
            assistant_msg=data.get("assistant_msg"),
            summary=data.get("summary")
        )
    
    def to_text(self) -> str:
        """转换为文本格式，用于向量化"""
        if self.memory_type == "full" and self.user_msg and self.assistant_msg:
            return f"用户: {self.user_msg[:200]}... 助手: {self.assistant_msg[:200]}..."
        return self.summary or ""
    
    def format_for_prompt(self, index: int) -> str:
        """格式化为提示文本"""
        if self.memory_type == "full":
            return f"{index}. [{self.timestamp}] [全文]\n   用户: {self.user_msg}\n   助手: {self.assistant_msg}"
        else:
            return f"{index}. [{self.timestamp}] [摘要] {self.summary}"


def generate_summary(user_msg: str, assistant_msg: str) -> str:
    """
    使用AI模型生成对话摘要
    
    Args:
        user_msg: 用户消息
        assistant_msg: 助手回复
        
    Returns:
        对话摘要（150字以内）
    """
    extract_prompt = f"""你是一个记忆提取助手。

根据本次会话内容，提取一句简洁的总结（最多150字），包含以下信息：
- 用户下达了什么任务，给出了什么关键信息
- 回答中给出的哪些关键建议和措施规划
- 任何重要的结果或错误

用户输入：
{user_msg[:500]}

助手回复：
{assistant_msg[:500]}

只回复总结句子，不要添加其他内容。"""

    try:
        llm = config.get_llm(config.MEMORY_MODEL)
        response = llm.invoke([HumanMessage(content=extract_prompt)])
        summary = response.content.strip()
        return summary
    except Exception as e:
        # 如果生成失败，使用简单截断
        return f"用户询问: {user_msg[:100]}..."


class ShortTermMemory:
    """短期记忆管理器，分层存储策略"""
    
    def __init__(self, max_rounds: int = MAX_SHORT_TERM_ROUNDS):
        self.max_rounds = max_rounds
        self.full_count = FULL_MEMORY_COUNT
        self.memories: list[MemoryEntry] = []
        self._load()
    
    def _load(self):
        """从文件加载短期记忆"""
        if not os.path.exists(MEMORY_FILE):
            self.memories = []
            return
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.memories = [MemoryEntry.from_dict(d) for d in data]
        except (json.JSONDecodeError, IOError, KeyError):
            self.memories = []
    
    def save(self):
        """保存短期记忆到文件"""
        data = [m.to_dict() for m in self.memories]
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _convert_oldest_full_to_summary(self):
        """将最旧的全文记忆转换为摘要"""
        # 策略：始终保持前5条记忆为全文，第6条及以后为摘要
        # 由于新记忆插入在开头(索引0)，所以索引0-4应该是full，索引5+应该是summary
        
        # 检查索引5及以后的记忆，将其中是full的转为summary
        for i in range(self.full_count, len(self.memories)):
            if self.memories[i].memory_type == "full":
                oldest = self.memories[i]
                
                # 生成摘要
                summary_text = generate_summary(oldest.user_msg or "", oldest.assistant_msg or "")
                
                # 转换为摘要类型
                self.memories[i] = MemoryEntry(
                    timestamp=oldest.timestamp,
                    memory_type="summary",
                    summary=summary_text
                )
                print(f"[SHORT_TERM] 将 [{oldest.timestamp}] 的全文记忆转换为摘要")
                break  # 每次只转换一条
    
    def add(self, user_msg: str, assistant_msg: str) -> Optional[MemoryEntry]:
        """
        添加新对话到短期记忆
        
        策略：
        1. 新对话总是作为全文存储
        2. 如果全文超过5条，将最旧的全文转为AI摘要
        3. 如果总记忆超过10条，淘汰最早的一条到长期记忆
        
        Args:
            user_msg: 用户消息
            assistant_msg: 助手回复
            
        Returns:
            如果超过10轮，返回最早的一条（需要移入长期记忆）
            否则返回 None
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # 创建新的全文记忆
        new_entry = MemoryEntry(
            timestamp=timestamp,
            memory_type="full",
            user_msg=user_msg,
            assistant_msg=assistant_msg
        )
        
        # 插入到开头（最新的在前面）
        self.memories.insert(0, new_entry)
        
        # 检查是否需要转换旧的全文为摘要
        self._convert_oldest_full_to_summary()
        
        # 检查是否超过上限
        evicted = None
        if len(self.memories) > self.max_rounds:
            evicted = self.memories.pop()  # 移除最旧的一条
            print(f"[SHORT_TERM] 记忆超过{self.max_rounds}条，将 [{evicted.timestamp}] 移入长期记忆")
        
        self.save()
        return evicted
    
    def get_recent_full(self, n: int = 5) -> list[MemoryEntry]:
        """获取最近n条全文记忆"""
        full_memories = [m for m in self.memories if m.memory_type == "full"]
        return full_memories[:n]
    
    def get_recent_summaries(self, n: Optional[int] = None) -> list[MemoryEntry]:
        """获取最近n条摘要记忆"""
        summary_memories = [m for m in self.memories if m.memory_type == "summary"]
        if n is None:
            return summary_memories
        return summary_memories[:n]
    
    def get_all(self) -> list[MemoryEntry]:
        """获取所有短期记忆"""
        return self.memories.copy()
    
    def clear(self):
        """清空短期记忆"""
        self.memories = []
        self.save()
    
    def is_empty(self) -> bool:
        """检查是否为空"""
        return len(self.memories) == 0
    
    def __len__(self) -> int:
        return len(self.memories)
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        full_count = sum(1 for m in self.memories if m.memory_type == "full")
        summary_count = sum(1 for m in self.memories if m.memory_type == "summary")
        return {
            "total": len(self.memories),
            "full": full_count,
            "summary": summary_count
        }
    
    def format_for_prompt(self) -> str:
        """格式化为提示文本"""
        if not self.memories:
            return ""
        
        lines = ["## 近期对话记忆\n"]
        lines.append(f"（共{len(self.memories)}条：最近{self.get_stats()['full']}条全文，{self.get_stats()['summary']}条摘要）\n")
        
        for i, entry in enumerate(self.memories, 1):
            lines.append(entry.format_for_prompt(i))
        
        return "\n\n".join(lines)


# 便捷函数接口
_short_term_memory: Optional[ShortTermMemory] = None


def get_short_term_memory() -> ShortTermMemory:
    """获取短期记忆管理器（单例）"""
    global _short_term_memory
    if _short_term_memory is None:
        _short_term_memory = ShortTermMemory()
    return _short_term_memory


def save_conversation(user_msg: str, assistant_msg: str) -> Optional[MemoryEntry]:
    """
    保存对话，返回被淘汰的记忆（如果有）
    """
    stm = get_short_term_memory()
    return stm.add(user_msg, assistant_msg)


def get_recent_full_memories(n: int = 5) -> list[MemoryEntry]:
    """获取最近n条全文记忆"""
    stm = get_short_term_memory()
    return stm.get_recent_full(n)


def get_recent_summary_memories(n: Optional[int] = None) -> list[MemoryEntry]:
    """获取最近n条摘要记忆"""
    stm = get_short_term_memory()
    return stm.get_recent_summaries(n)


def format_short_term_for_prompt() -> str:
    """将短期记忆格式化为提示文本"""
    stm = get_short_term_memory()
    return stm.format_for_prompt()


def get_short_term_stats() -> dict:
    """获取短期记忆统计"""
    stm = get_short_term_memory()
    return stm.get_stats()
