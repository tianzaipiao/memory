"""
长期记忆模块
============
管理向量化后的历史对话摘要，使用 Chroma 向量数据库。

功能：
- 存储被淘汰出短期记忆的对话摘要
- 基于语义相似度搜索相关历史摘要
- 支持 top-k 召回
"""

import os
import uuid
from dataclasses import dataclass
from typing import Optional

from memory.embedder import get_embedder, get_embedding_dimension

# Chroma 数据库路径
CHROMA_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "chroma_db")
COLLECTION_NAME = "long_term_memory"


@dataclass
class MemoryRecord:
    """记忆记录"""
    id: str
    text: str  # 摘要文本（用于向量和展示）
    timestamp: str
    distance: Optional[float] = None  # 查询时的相似度距离
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "timestamp": self.timestamp,
        }


class LongTermMemory:
    """长期记忆管理器，基于 Chroma 向量数据库"""
    
    def __init__(self, collection_name: str = COLLECTION_NAME):
        self.collection_name = collection_name
        self._client = None
        self._collection = None
    
    def _get_client(self):
        """延迟初始化 Chroma 客户端"""
        if self._client is None:
            try:
                import chromadb
                from chromadb.config import Settings
            except ImportError:
                raise ImportError(
                    "使用长期记忆需要安装 Chroma:\n"
                    "pip install chromadb"
                )
            
            # 确保目录存在
            os.makedirs(CHROMA_DB_PATH, exist_ok=True)
            
            self._client = chromadb.PersistentClient(
                path=CHROMA_DB_PATH,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
        return self._client
    
    def _get_collection(self):
        """获取或创建集合"""
        if self._collection is None:
            client = self._get_client()
            
            # 获取向量维度
            dimension = get_embedding_dimension()
            
            # 获取或创建集合
            self._collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}  # 使用余弦相似度
            )
        return self._collection
    
    def add(self, text: str, timestamp: str, user_msg: str = "", assistant_msg: str = "") -> str:
        """
        添加记忆到长期存储
        
        Args:
            text: 摘要文本（用于向量化）
            timestamp: 时间戳
            user_msg: 保留参数（向后兼容，不再使用）
            assistant_msg: 保留参数（向后兼容，不再使用）
            
        Returns:
            记忆ID
        """
        # 生成唯一ID
        memory_id = str(uuid.uuid4())
        
        # 获取向量
        embedding = get_embedder().embed(text)
        
        # 存入 Chroma
        collection = self._get_collection()
        collection.add(
            ids=[memory_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[{
                "timestamp": timestamp,
            }]
        )
        
        return memory_id
    
    def search(self, query: str, top_k: int = 10) -> list[MemoryRecord]:
        """
        基于语义相似度搜索记忆
        
        Args:
            query: 查询文本
            top_k: 返回最相关的k条
            
        Returns:
            记忆记录列表，按相似度排序
        """
        # 获取查询向量
        query_embedding = get_embedder().embed(query)
        
        # 搜索
        collection = self._get_collection()
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )
        
        # 解析结果
        records = []
        if results["ids"] and results["ids"][0]:
            for i, memory_id in enumerate(results["ids"][0]):
                metadata = results["metadatas"][0][i]
                records.append(MemoryRecord(
                    id=memory_id,
                    text=results["documents"][0][i],
                    timestamp=metadata.get("timestamp", ""),
                    distance=results["distances"][0][i] if results["distances"] else None
                ))
        
        return records
    
    def get_all(self, limit: int = 100) -> list[MemoryRecord]:
        """获取所有记忆（用于调试）"""
        collection = self._get_collection()
        results = collection.get(
            limit=limit,
            include=["documents", "metadatas"]
        )
        
        records = []
        for i, memory_id in enumerate(results["ids"]):
            metadata = results["metadatas"][i]
            records.append(MemoryRecord(
                id=memory_id,
                text=results["documents"][i],
                timestamp=metadata.get("timestamp", "")
            ))
        
        return records
    
    def count(self) -> int:
        """获取记忆总数"""
        collection = self._get_collection()
        return collection.count()
    
    def clear(self):
        """清空所有长期记忆"""
        try:
            client = self._get_client()
            client.delete_collection(self.collection_name)
            self._collection = None
        except Exception:
            pass
    
    def format_for_prompt(self, records: list[MemoryRecord]) -> str:
        """将记忆记录格式化为提示文本"""
        if not records:
            return ""
        
        lines = ["## 相关历史记忆\n"]
        for i, record in enumerate(records, 1):
            similarity = ""
            if record.distance is not None:
                # 将距离转换为相似度分数 (0-1)
                score = max(0, min(1, 1 - record.distance))
                similarity = f" [相关度: {score:.2f}]"
            
            lines.append(f"{i}. [{record.timestamp}] {record.text}{similarity}")
        
        return "\n".join(lines)


# 便捷函数接口
_long_term_memory: Optional[LongTermMemory] = None


def get_long_term_memory() -> LongTermMemory:
    """获取长期记忆管理器（单例）"""
    global _long_term_memory
    if _long_term_memory is None:
        _long_term_memory = LongTermMemory()
    return _long_term_memory


def add_to_long_term(text: str, timestamp: str, user_msg: str = "", assistant_msg: str = "") -> str:
    """便捷函数：添加记忆到长期存储"""
    ltm = get_long_term_memory()
    return ltm.add(text, timestamp, user_msg, assistant_msg)


def search_long_term(query: str, top_k: int = 10) -> list[MemoryRecord]:
    """便捷函数：搜索长期记忆"""
    ltm = get_long_term_memory()
    return ltm.search(query, top_k)


def format_long_term_for_prompt(records: list[MemoryRecord]) -> str:
    """便捷函数：格式化长期记忆为提示文本"""
    ltm = get_long_term_memory()
    return ltm.format_for_prompt(records)
