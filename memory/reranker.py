"""
Rerank 重排序模块
================
对向量召回的结果进行重排序，提高召回质量。

支持两种模式：
1. local: 使用本地 Qwen3-Reranker 模型（推荐，免费且准确）
2. none: 仅使用向量相似度排序

配置项（在 .env 中设置）：
- MEMORY_SIMILARITY_THRESHOLD: 相似度阈值 (0-1)，默认 0.6
- RERANK_MODE: 重排序模式 (local / none)，默认 none
- LOCAL_RERANKER_PATH: 本地模型路径
"""

import os
from dataclasses import dataclass
from typing import Optional

from memory.long_term import MemoryRecord

# 从环境变量读取配置
SIMILARITY_THRESHOLD = float(os.environ.get("MEMORY_SIMILARITY_THRESHOLD", "0.6"))
RERANK_MODE = os.environ.get("RERANK_MODE", "none").lower()
LOCAL_RERANKER_PATH = os.environ.get("LOCAL_RERANKER_PATH", "")


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
    """将余弦距离转换为相似度分数 (0-1)"""
    if distance is None:
        return 0.0
    score = max(0.0, min(1.0, 1.0 - distance / 2.0))
    return round(score, 4)


class Qwen3Reranker:
    """本地 Qwen3 Reranker 模型封装"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        # 判断是本地路径还是 HuggingFace repo id
        model_path = LOCAL_RERANKER_PATH or "Qwen/Qwen3-Reranker-0.6B"
        is_local_path = os.path.exists(model_path)

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        torch_dtype = torch.float16 if self.device == "cuda" else torch.float32

        print(f"[RERANK] 加载模型: {model_path}")
        print(f"[RERANK] 使用设备: {self.device}")
        print(f"[RERANK] 路径类型: {'本地路径' if is_local_path else 'HuggingFace'}")

        # 本地路径需要设置 local_files_only=True
        load_kwargs = {"trust_remote_code": True}
        if is_local_path:
            load_kwargs["local_files_only"] = True

        self.tokenizer = AutoTokenizer.from_pretrained(model_path, **load_kwargs)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype=torch_dtype,
            **load_kwargs
        ).to(self.device).eval()

        self.yes_id = self.tokenizer.convert_tokens_to_ids("yes")
        self.no_id = self.tokenizer.convert_tokens_to_ids("no")

        self.prefix = (
            '<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and the Instruct provided. '
            'Note that the answer can only be "yes" or "no".<|im_end|>\n'
            '<|im_start|>user\n'
        )
        self.suffix = '<|im_end|>\n<|im_start|>assistant\n\n\n\n\n'

        self._initialized = True
        print("[RERANK] 模型加载完成")

    def score(self, query: str, documents: list[str]) -> list[float]:
        """计算 query 与每个 document 的相关性分数"""
        if not documents:
            return []

        import torch

        instruction = "Given a web search query, retrieve relevant passages that answer the query"

        prompts = []
        for doc in documents:
            text = f"<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {doc}"
            prompt = self.prefix + text + self.suffix
            prompts.append(prompt)

        inputs = self.tokenizer(
            prompts,
            padding=True,
            truncation=True,
            max_length=8192,
            return_tensors="pt"
        ).to(self.device)

        with torch.no_grad():
            logits = self.model(**inputs).logits[:, -1, :]

        yes_logit = logits[:, self.yes_id]
        no_logit = logits[:, self.no_id]

        scores = torch.softmax(torch.stack([no_logit, yes_logit], dim=1), dim=1)[:, 1]
        return scores.cpu().numpy().tolist()


def rerank_with_local_model(query: str, memories: list[RankedMemory]) -> list[RankedMemory]:
    """使用本地 Qwen3 Reranker 进行重排序"""
    if not memories:
        return memories

    try:
        reranker = Qwen3Reranker()
        docs = [m.record.text for m in memories]
        scores = reranker.score(query, docs)

        for i, mem in enumerate(memories):
            mem.rerank_score = scores[i]

        memories.sort(key=lambda x: x.final_score, reverse=True)
        print(f"[RERANK] 本地模型重排序完成，已评分 {len(scores)} 条记忆")

    except Exception as e:
        print(f"[RERANK] 本地模型重排序失败: {e}")
        print("[RERANK] 回退到向量相似度排序")
        memories.sort(key=lambda x: x.original_score, reverse=True)

    return memories


def filter_by_threshold(memories: list[RankedMemory]) -> list[RankedMemory]:
    """根据阈值过滤记忆"""
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

    Args:
        query: 用户查询
        memories: 向量召回的原始记忆
        top_k: 初始召回数量
        final_k: 最终返回数量

    Returns:
        经过重排序和阈值过滤的记忆列表
    """
    if not memories:
        return []

    # 转换为带评分的记忆
    ranked = [
        RankedMemory(
            record=mem,
            original_score=calculate_similarity_score(mem.distance)
        )
        for mem in memories
    ]
    print(f"[RERANK] 向量召回 {len(ranked)} 条记忆")

    # 根据配置选择重排序方式
    if RERANK_MODE == "local" and len(ranked) > 1:
        ranked = rerank_with_local_model(query, ranked)
    else:
        ranked.sort(key=lambda x: x.original_score, reverse=True)
        if RERANK_MODE == "none":
            print(f"[RERANK] 使用原始向量相似度排序")

    # 阈值过滤
    ranked = filter_by_threshold(ranked)

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
