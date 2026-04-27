"""
记忆召回工具 (Memory Tool)
==========================
供 AI 自主调用的记忆检索工具。

使用场景:
- 用户提到"之前说过"、"上次"等指代历史内容
- 需要了解用户的习惯、偏好、背景信息
- 当前话题与历史对话有明显关联

调用方式:
AI 在响应中输出特定格式的 tool call 标记，系统解析后执行
"""

import json
from typing import Optional
from dataclasses import dataclass


@dataclass
class MemoryQuery:
    """记忆查询参数"""
    query: str  # 搜索关键词或问题
    reason: str  # 调用原因（AI 的自我解释）


@dataclass
class MemoryResult:
    """记忆召回结果"""
    short_term_memories: list[dict]  # 短期记忆（最近对话）
    long_term_memories: list[dict]   # 长期记忆（向量召回）
    formatted_text: str              # 格式化后的文本


class MemoryTool:
    """
    记忆召回工具
    
    功能:
    1. 召回短期记忆（最近5条全文 + 摘要）
    2. 召回长期记忆（基于语义相似度的向量搜索）
    3. 格式化结果供 AI 使用
    """
    
    # Tool 描述，用于系统提示
    DESCRIPTION = """
## 工具: memory_search

当你需要参考历史对话或了解用户背景时调用此工具。

### 适用场景
- 用户提到"之前说过"、"上次"、"还记得"等指代历史内容
- 需要了解用户的习惯、偏好、背景信息
- 当前话题与历史对话有明显关联
- 用户询问某个之前讨论过的主题

### 不适用场景
- 用户开启全新话题，与历史无关
- 简单的问候或闲聊
- 纯粹的技术问题解答（无需历史背景）

### 调用格式
在需要调用时，在你的思考过程中输出：

<tool_call>
{
  "tool": "memory_search",
  "query": "搜索关键词或问题描述",
  "reason": "为什么需要调用此工具"
}
</tool_call>

### 返回内容
工具将返回：
1. 近期对话记忆（最近5轮全文 + 摘要）
2. 相关历史记忆（基于语义相似度召回）

你可以基于这些信息给出更准确的回答。
"""
    
    def __init__(self):
        self._initialized = False
    
    def _ensure_initialized(self):
        """延迟初始化，避免循环导入"""
        if not self._initialized:
            # 在这里导入，避免循环依赖
            from memory import (
                get_short_term_memory,
                get_long_term_memory,
                search_long_term,
                get_recent_full_memories,
                get_recent_summary_memories,
            )
            self._get_stm = get_short_term_memory
            self._get_ltm = get_long_term_memory
            self._search_ltm = search_long_term
            self._get_recent_full = get_recent_full_memories
            self._get_recent_summary = get_recent_summary_memories
            self._initialized = True
    
    def invoke(self, query: str, top_k: int = 5) -> MemoryResult:
        """
        执行记忆召回
        
        Args:
            query: 搜索关键词或问题
            top_k: 召回的长期记忆数量
            
        Returns:
            MemoryResult 包含短期和长期记忆
        """
        self._ensure_initialized()
        
        # 召回短期记忆
        short_term_full = self._get_recent_full(3)  # 最近3条全文
        short_term_summary = self._get_recent_summary(3)  # 最近3条摘要
        
        short_term_list = []
        for m in short_term_full:
            short_term_list.append({
                "type": "full",
                "timestamp": m.timestamp,
                "user": m.user_msg,
                "assistant": m.assistant_msg
            })
        for m in short_term_summary:
            short_term_list.append({
                "type": "summary",
                "timestamp": m.timestamp,
                "content": m.summary
            })
        
        # 召回长期记忆（向量搜索）
        long_term_records = self._search_ltm(query, top_k=top_k)
        long_term_list = []
        for r in long_term_records:
            similarity = 1 - r.distance if r.distance else 0
            long_term_list.append({
                "timestamp": r.timestamp,
                "content": r.text,
                "similarity": round(similarity, 2)
            })
        
        # 格式化文本
        formatted = self._format_memories(short_term_list, long_term_list)
        
        return MemoryResult(
            short_term_memories=short_term_list,
            long_term_memories=long_term_list,
            formatted_text=formatted
        )
    
    def _format_memories(self, short_term: list, long_term: list) -> str:
        """格式化记忆为可读文本"""
        lines = []
        
        if short_term:
            lines.append("## 近期对话记忆")
            for i, m in enumerate(short_term[:5], 1):
                if m["type"] == "full":
                    lines.append(f"{i}. [{m['timestamp']}] 用户: {m['user'][:100]}...")
                else:
                    lines.append(f"{i}. [{m['timestamp']}] {m['content'][:150]}...")
            lines.append("")
        
        if long_term:
            lines.append("## 相关历史记忆")
            for i, m in enumerate(long_term[:5], 1):
                lines.append(f"{i}. [{m['timestamp']}] [相关度{m['similarity']}] {m['content'][:150]}...")
            lines.append("")
        
        return "\n".join(lines) if lines else "（无相关记忆）"
    
    @staticmethod
    def parse_tool_call(text: str) -> Optional[MemoryQuery]:
        """
        从 AI 响应中解析 tool call
        
        Args:
            text: AI 的响应文本
            
        Returns:
            如果包含 tool call，返回 MemoryQuery；否则返回 None
        """
        import re
        
        # 匹配 <tool_call>...</tool_call> 格式
        pattern = r'<tool_call>\s*(\{[\s\S]*?\})\s*</tool_call>'
        match = re.search(pattern, text)
        
        if match:
            try:
                data = json.loads(match.group(1))
                if data.get("tool") == "memory_search":
                    return MemoryQuery(
                        query=data.get("query", ""),
                        reason=data.get("reason", "")
                    )
            except json.JSONDecodeError:
                pass
        
        return None
    
    @staticmethod
    def remove_tool_call_markup(text: str) -> str:
        """移除响应中的 tool call 标记，保留其他内容"""
        import re
        pattern = r'<tool_call>[\s\S]*?</tool_call>\s*'
        return re.sub(pattern, "", text).strip()


# 单例实例
_memory_tool: Optional[MemoryTool] = None


def get_memory_tool() -> MemoryTool:
    """获取记忆工具单例"""
    global _memory_tool
    if _memory_tool is None:
        _memory_tool = MemoryTool()
    return _memory_tool


def search_memory(query: str, top_k: int = 5) -> str:
    """
    便捷函数：执行记忆搜索并返回格式化文本
    
    Args:
        query: 搜索关键词
        top_k: 召回数量
        
    Returns:
        格式化后的记忆文本
    """
    tool = get_memory_tool()
    result = tool.invoke(query, top_k)
    return result.formatted_text
