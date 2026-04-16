"""
Rerank 重排序模块
================
对向量召回的结果进行重排序，提高召回质量。

标准 RAG 流程：
1. 向量召回（Embedding Search）
2. Rerank 重排序（Cross-Encoder / LLM）
3. 阈值过滤（Similarity Threshold）

配置项（可在 .env 中设置）：
- MEMORY_SIMILARITY_THRESHOLD: 相似度阈值 (0-1)，默认 0.5
- USE_LLM_RERANK: 是否使用LLM重排序，默认 False
"""

import os
from dataclasses import dataclass
from typing import Optional

from memory.long_term import MemoryRecord

# 从环境变量读取配置，默认阈值 0.5
SIMILARITY_THRESHOLD = float(os.environ.get("MEMORY_SIMILARITY_THRESHOLD", "0.5"))
USE_LLM_RERANK = os.environ.get("USE_LLM_RERANK", "false").lower() == "true"


@dataclass
class RankedMemory:
    """带评分的记忆记录"""
    record: MemoryRecord
    original_score: float  # 原始相似度分数 (0-1)，来自向量检索
    rerank_score: Optional[float] = None  # 重排序后的分数，来自Rerank模型
    
    @property
    def final_score(self) -> float:
        """最终分数：优先使用重排序分数"""
        return self.rerank_score if self.rerank_score is not None else self.original_score
    
    @property
    def is_relevant(self) -> bool:
        """是否超过阈值，被认为是相关的"""
        return self.final_score >= SIMILARITY_THRESHOLD


def calculate_similarity_score(distance: Optional[float]) -> float:
    """
    将余弦距离转换为相似度分数 (0-1)
    
    Args:
        distance: 余弦距离值，范围通常为 [0, 2]
        
    Returns:
        相似度分数，0-1之间，1表示完全相同
    """
    if distance is None:
        return 0.0
    # 余弦距离转相似度：similarity = 1 - distance / 2
    # distance=0 → score=1 (完全相同)
    # distance=2 → score=0 (完全相反)
    score = max(0.0, min(1.0, 1.0 - distance / 2.0))
    return round(score, 4)


def rerank_with_llm(
    query: str,
    memories: list[RankedMemory]
) -> list[RankedMemory]:
    """
    使用LLM对召回的记忆进行重排序
    
    Args:
        query: 用户查询
        memories: 初步召回的记忆列表
        
    Returns:
        重排序后的记忆列表（按rerank_score降序）
    """
    if not memories or not USE_LLM_RERANK:
        return memories
    
    try:
        import config
        from langchain_core.messages import HumanMessage
    except ImportError:
        return memories
    
    # 构建重排序提示
    rerank_prompt = f"""你是一个相关性评估助手。

用户查询：{query}

请评估以下每条记忆片段与用户查询的相关性，给出0-1的分数（1表示完全相关，0表示完全不相关）。

只回复JSON格式：{{"results": [{{"id": 0, "score": 0.9, "reason": "简要原因"}}, ...]}}

记忆片段：
"""
    
    for i, mem in enumerate(memories):
        rerank_prompt += f"\n[{i}] {mem.record.text[:300]}"
    
    try:
        llm = config.get_llm(config.RERANK_MODEL)
        response = llm.invoke([HumanMessage(content=rerank_prompt)])
        
        # 解析JSON响应
        import json
        import re
        
        content = response.content.strip()
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            scores = {item["id"]: item["score"] for item in result.get("results", [])}
            
            # 更新重排序分数
            for i, mem in enumerate(memories):
                if i in scores:
                    mem.rerank_score = scores[i]
        
        # 按重排序分数降序排序
        memories.sort(key=lambda x: x.final_score, reverse=True)
        
        print(f"[RERANK] LLM重排序完成，已重新评分 {len(scores)} 条记忆")
        
    except Exception as e:
        print(f"[RERANK] LLM重排序失败，使用原始排序: {e}")
    
    return memories


def filter_by_threshold(memories: list[RankedMemory]) -> list[RankedMemory]:
    """
    根据阈值过滤记忆（在重排序之后执行）
    
    Args:
        memories: 已重排序的记忆列表
        
    Returns:
        超过阈值的记忆列表（保持原有排序）
    """
    filtered = [m for m in memories if m.is_relevant]
    print(f"[RERANK] 阈值过滤: {len(memories)} → {len(filtered)} 条 (阈值: {SIMILARITY_THRESHOLD})")
    return filtered


def rerank_memories(
    query: str,
    memories: list[MemoryRecord],
    top_k: int = 10,
    final_k: int = 5
) -> list[RankedMemory]:
    """
    完整的 RAG 重排序流程
    
    标准流程：
    1. 向量召回（由调用方完成，传入memories）
    2. 距离 → 相似度分数转换
    3. Rerank 重排序（LLM或Cross-Encoder）
    4. 阈值过滤（基于重排序后的分数）
    5. 返回 Top-K
    
    Args:
        query: 用户查询
        memories: 向量召回的原始记忆
        top_k: 初始召回数量（已由调用方控制）
        final_k: 最终返回数量
        
    Returns:
        经过重排序和阈值过滤的记忆列表
    """
    if not memories:
        return []
    
    # 步骤1：转换为带评分的记忆（原始分数）
    ranked = [
        RankedMemory(
            record=mem,
            original_score=calculate_similarity_score(mem.distance)
        )
        for mem in memories
    ]
    print(f"[RERANK] 向量召回 {len(ranked)} 条记忆")
    
    # 步骤2：Rerank 重排序
    if USE_LLM_RERANK and len(ranked) > 1:
        ranked = rerank_with_llm(query, ranked)
    else:
        # 未启用LLM重排序，按原始分数排序
        ranked.sort(key=lambda x: x.original_score, reverse=True)
        print(f"[RERANK] 使用原始向量相似度排序")
    
    # 步骤3：阈值过滤（在重排序之后）
    ranked = filter_by_threshold(ranked)
    
    # 步骤4：返回 Top-K
    return ranked[:final_k]


def format_ranked_memories(ranked: list[RankedMemory]) -> str:
    """将重排序后的记忆格式化为提示文本"""
    if not ranked:
        return ""
    
    lines = ["## 相关历史记忆（已重排序过滤）\n"]
    for i, item in enumerate(ranked, 1):
        score_info = f"[相关度: {item.final_score:.2f}]"
        if item.rerank_score is not None:
            score_info += f" (原始: {item.original_score:.2f})"
        
        lines.append(f"{i}. [{item.record.timestamp}] {score_info}")
        lines.append(f"   {item.record.text}")
        lines.append("")
    
    return "\n".join(lines)
