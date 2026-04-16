"""
文本向量化模块
==============
封装文本嵌入模型，将文本转换为向量。

支持两种模式：
1. OpenAI API (text-embedding-3-small)
2. 本地模型 (sentence-transformers)
"""

import os
from typing import Union

import config

# 嵌入模型维度
EMBEDDING_DIMENSION = 1536  # text-embedding-3-small 的维度


class Embedder:
    """文本嵌入器基类"""
    
    def embed(self, text: str) -> list[float]:
        """将单条文本转换为向量"""
        raise NotImplementedError
    
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量转换文本为向量"""
        raise NotImplementedError
    
    @property
    def dimension(self) -> int:
        """返回向量维度"""
        raise NotImplementedError


class OpenAIEmbedder(Embedder):
    """使用 OpenAI API 进行文本嵌入"""
    
    def __init__(self, model: str = "GLM-Embedding-3"):
        self.model = model
        self._client = None
    
    def _get_client(self):
        """延迟初始化 OpenAI 客户端"""
        if self._client is None:
            from openai import OpenAI
            
            # 使用 config 中的配置
            base_url = (
                config.OPENAI_COMPATIBLE_BASE_URL
                or config._DEFAULT_BASE_URLS.get(config.PROVIDER, "")
            )
            
            self._client = OpenAI(
                api_key=config.OPENAI_COMPATIBLE_API_KEY,
                base_url=base_url
            )
        return self._client
    
    def embed(self, text: str) -> list[float]:
        """单条文本嵌入"""
        client = self._get_client()
        response = client.embeddings.create(
            model=self.model,
            input=text
        )
        return response.data[0].embedding
    
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量文本嵌入"""
        if not texts:
            return []
        
        client = self._get_client()
        response = client.embeddings.create(
            model=self.model,
            input=texts
        )
        return [item.embedding for item in response.data]
    
    @property
    def dimension(self) -> int:
        # text-embedding-3-small: 1536
        # text-embedding-3-large: 3072
        if "large" in self.model:
            return 3072
        return 1536


class LocalEmbedder(Embedder):
    """使用本地 sentence-transformers 模型"""
    
    def __init__(self, model_name: str = "paraphrase-multilingual-MiniLM-L12-v2"):
        self.model_name = model_name
        self._model = None
    
    def _get_model(self):
        """延迟加载模型"""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
            except ImportError:
                raise ImportError(
                    "使用本地嵌入模型需要安装 sentence-transformers:\n"
                    "pip install sentence-transformers"
                )
        return self._model
    
    def embed(self, text: str) -> list[float]:
        """单条文本嵌入"""
        model = self._get_model()
        embedding = model.encode(text)
        return embedding.tolist()
    
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量文本嵌入"""
        if not texts:
            return []
        
        model = self._get_model()
        embeddings = model.encode(texts)
        return embeddings.tolist()
    
    @property
    def dimension(self) -> int:
        # paraphrase-multilingual-MiniLM-L12-v2: 384
        return 384


# 全局嵌入器实例（延迟初始化）
_embedder: Union[OpenAIEmbedder, LocalEmbedder, None] = None


def get_embedder() -> Embedder:
    """
    获取嵌入器实例（单例模式）
    
    优先使用 OpenAI API，如果未配置则尝试本地模型
    """
    global _embedder
    
    if _embedder is None:
        # 检查是否配置了 API Key
        if config.OPENAI_COMPATIBLE_API_KEY:
            _embedder = OpenAIEmbedder()
        else:
            # 使用本地模型
            _embedder = LocalEmbedder()
    
    return _embedder


def embed_text(text: str) -> list[float]:
    """便捷函数：单条文本嵌入"""
    return get_embedder().embed(text)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """便捷函数：批量文本嵌入"""
    return get_embedder().embed_batch(texts)


def get_embedding_dimension() -> int:
    """获取当前嵌入器的向量维度"""
    return get_embedder().dimension
