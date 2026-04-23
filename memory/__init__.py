"""
记忆系统模块
============
统一导出记忆系统的所有接口。

使用示例：
    from memory import (
        ShortTermMemory,
        LongTermMemory,
        get_short_term_memory,
        get_long_term_memory,
        save_conversation_with_memory,
        build_context_with_memory
    )
"""

# 短期记忆
from memory.short_term import (
    ShortTermMemory,
    MemoryEntry,
    get_short_term_memory,
    save_conversation,
    get_recent_full_memories,
    get_recent_summary_memories,
    format_short_term_for_prompt,
    get_short_term_stats,
)

# 长期记忆
from memory.long_term import (
    LongTermMemory,
    MemoryRecord,
    get_long_term_memory,
    add_to_long_term,
    search_long_term,
    format_long_term_for_prompt,
)

# 向量化
from memory.embedder import (
    Embedder,
    OpenAIEmbedder,
    LocalEmbedder,
    get_embedder,
    embed_text,
    embed_texts,
    get_embedding_dimension,
)


def save_conversation_with_memory(user_msg: str, assistant_msg: str) -> None:
    """
    保存对话到记忆系统。
    
    逻辑：
    1. 新对话作为全文存入短期记忆
    2. 如果全文超过5条，将最旧的全文转为AI摘要
    3. 如果总记忆超过10条，将最早的一条向量化后移入长期记忆
    
    Args:
        user_msg: 用户消息
        assistant_msg: 助手回复
    """
    stm = get_short_term_memory()
    
    # 添加到短期记忆，返回被淘汰的记忆（如果有）
    evicted = stm.add(user_msg, assistant_msg)
    
    # 如果有被淘汰的记忆，将其向量化后移入长期记忆
    if evicted:
        ltm = get_long_term_memory()
        text = evicted.to_text()
        ltm.add(
            text=text,
            timestamp=evicted.timestamp
        )


def build_context_with_memory(user_input: str) -> str:
    """
    构建包含记忆的上下文。
    
    返回的上下文结构：
    1. 相关历史记忆（从向量数据库召回，经过重排序和阈值过滤）
    2. 近期对话记忆（最近5条全文 + 5条AI摘要）
    
    Args:
        user_input: 当前用户输入
        
    Returns:
        格式化后的上下文文本
    """
    context, _ = build_context_with_memory_detailed(user_input)
    return context


def build_context_with_memory_detailed(user_input: str) -> tuple[str, list[dict]]:
    """
    构建包含记忆的上下文，并返回向量库召回的详细数据。
    
    返回的上下文结构：
    1. 相关历史记忆（从向量数据库召回，经过重排序和阈值过滤）
    2. 近期对话记忆（最近5条全文 + 5条AI摘要）
    
    Args:
        user_input: 当前用户输入
        
    Returns:
        (格式化后的上下文文本, 向量库召回的记忆列表)
    """
    parts = []
    vector_memories = []
    
    # 1. 从长期记忆中召回相关内容（带重排序）
    ltm = get_long_term_memory()
    
    # 使用重排序搜索（召回10条，返回最相关的5条，经过阈值过滤）
    try:
        from memory.reranker import rerank_memories, format_ranked_memories
        candidates = ltm.search(user_input, top_k=10)
        if candidates:
            ranked_memories = rerank_memories(user_input, candidates, top_k=10, final_k=5)
            if ranked_memories:
                parts.append(format_ranked_memories(ranked_memories))
                # 提取向量库记忆数据用于日志
                for item in ranked_memories:
                    vector_memories.append({
                        "timestamp": item.record.timestamp,
                        "text": item.record.text,
                        "score": item.final_score
                    })
    except ImportError:
        # 如果reranker模块不存在，使用普通搜索
        related_memories = ltm.search(user_input, top_k=5)
        if related_memories:
            parts.append(ltm.format_for_prompt(related_memories))
            # 提取向量库记忆数据用于日志
            for record in related_memories:
                vector_memories.append({
                    "timestamp": record.timestamp,
                    "text": record.text,
                    "distance": record.distance
                })
    
    # 2. 添加短期记忆
    stm = get_short_term_memory()
    short_term_text = stm.format_for_prompt()
    if short_term_text:
        parts.append(short_term_text)
    
    return "\n\n".join(parts), vector_memories


def get_memory_stats() -> dict:
    """
    获取记忆系统统计信息
    
    Returns:
        {
            "short_term": {"total": 10, "full": 5, "summary": 5},
            "long_term_count": 长期记忆数量,
            "total_memories": 总记忆数
        }
    """
    stm = get_short_term_memory()
    ltm = get_long_term_memory()
    
    return {
        "short_term": stm.get_stats(),
        "long_term_count": ltm.count(),
        "total_memories": len(stm) + ltm.count()
    }


def clear_all_memory() -> None:
    """清空所有记忆（短期+长期）"""
    stm = get_short_term_memory()
    stm.clear()
    
    ltm = get_long_term_memory()
    ltm.clear()


__all__ = [
    # 类
    "ShortTermMemory",
    "LongTermMemory",
    "MemoryEntry",
    "MemoryRecord",
    "Embedder",
    "OpenAIEmbedder",
    "LocalEmbedder",
    # 函数
    "get_short_term_memory",
    "get_long_term_memory",
    "save_conversation_with_memory",
    "build_context_with_memory",
    "get_memory_stats",
    "clear_all_memory",
    "save_conversation",
    "get_recent_full_memories",
    "get_recent_summary_memories",
    "format_short_term_for_prompt",
    "format_long_term_for_prompt",
    "get_short_term_stats",
    "add_to_long_term",
    "search_long_term",
    "get_embedder",
    "embed_text",
    "embed_texts",
    "get_embedding_dimension",
]
