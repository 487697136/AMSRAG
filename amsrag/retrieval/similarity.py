"""
语义相似度计算模块

提供多种文本相似度计算方法，用于CA-RRF融合中的MMR多样性约束。

支持的方法：
1. 基于嵌入的余弦相似度（推荐，语义级别）
2. 基于TF-IDF的余弦相似度（词汇级别，无需API）
3. Jaccard相似度（词袋级别，最简单）

论文参考：
- MMR (Maximal Marginal Relevance): Carbonell & Goldstein, 1998
- Sentence-BERT: Reimers & Gurevych, 2019
"""

import numpy as np
import logging
from typing import List, Dict, Optional, Callable, Any, Union
from dataclasses import dataclass, field
from enum import Enum
import asyncio
from functools import lru_cache

logger = logging.getLogger(__name__)


class SimilarityMethod(Enum):
    """相似度计算方法枚举"""
    EMBEDDING = "embedding"      # 基于嵌入的余弦相似度
    TFIDF = "tfidf"              # 基于TF-IDF的余弦相似度
    JACCARD = "jaccard"          # Jaccard相似度（词袋）
    BM25 = "bm25"                # BM25相似度
    HYBRID = "hybrid"            # 混合方法


@dataclass
class SimilarityConfig:
    """相似度计算配置"""
    method: SimilarityMethod = SimilarityMethod.EMBEDDING
    
    # 嵌入方法配置
    embedding_func: Optional[Callable] = None
    embedding_cache_size: int = 1000
    
    # TF-IDF配置
    tfidf_max_features: int = 5000
    tfidf_ngram_range: tuple = (1, 2)
    
    # 混合方法权重
    hybrid_weights: Dict[str, float] = field(default_factory=lambda: {
        "embedding": 0.7,
        "tfidf": 0.2,
        "jaccard": 0.1
    })
    
    # 缓存配置
    enable_cache: bool = True
    
    # 回退配置
    fallback_method: SimilarityMethod = SimilarityMethod.TFIDF


class SemanticSimilarityCalculator:
    """
    语义相似度计算器
    
    提供多种相似度计算方法，支持缓存和回退机制。
    """
    
    def __init__(self, config: Optional[SimilarityConfig] = None):
        self.config = config or SimilarityConfig()
        self._embedding_cache: Dict[str, np.ndarray] = {}
        self._tfidf_vectorizer = None
        self._tfidf_fitted = False
        
        # 统计信息
        self.stats = {
            "total_computations": 0,
            "cache_hits": 0,
            "embedding_calls": 0,
            "fallback_count": 0
        }
    
    async def compute_similarity(
        self, 
        text1: str, 
        text2: str,
        method: Optional[SimilarityMethod] = None
    ) -> float:
        """
        计算两个文本的相似度
        
        Args:
            text1: 第一个文本
            text2: 第二个文本
            method: 指定计算方法，None则使用配置的默认方法
            
        Returns:
            相似度分数 [0, 1]
        """
        if not text1 or not text2:
            return 0.0
        
        self.stats["total_computations"] += 1
        method = method or self.config.method
        
        try:
            if method == SimilarityMethod.EMBEDDING:
                return await self._embedding_similarity(text1, text2)
            elif method == SimilarityMethod.TFIDF:
                return self._tfidf_similarity(text1, text2)
            elif method == SimilarityMethod.JACCARD:
                return self._jaccard_similarity(text1, text2)
            elif method == SimilarityMethod.BM25:
                return self._bm25_similarity(text1, text2)
            elif method == SimilarityMethod.HYBRID:
                return await self._hybrid_similarity(text1, text2)
            else:
                logger.warning(f"未知的相似度方法: {method}，使用Jaccard")
                return self._jaccard_similarity(text1, text2)
                
        except Exception as e:
            logger.warning(f"相似度计算失败 ({method}): {e}，使用回退方法")
            self.stats["fallback_count"] += 1
            return self._fallback_similarity(text1, text2)
    
    async def compute_similarity_matrix(
        self,
        texts: List[str],
        method: Optional[SimilarityMethod] = None
    ) -> np.ndarray:
        """
        计算文本列表的相似度矩阵
        
        Args:
            texts: 文本列表
            method: 计算方法
            
        Returns:
            n x n 的相似度矩阵
        """
        n = len(texts)
        if n == 0:
            return np.array([])
        
        method = method or self.config.method
        
        # 对于嵌入方法，批量计算更高效
        if method == SimilarityMethod.EMBEDDING and self.config.embedding_func:
            return await self._batch_embedding_similarity_matrix(texts)
        
        # 其他方法逐对计算
        matrix = np.zeros((n, n))
        for i in range(n):
            matrix[i, i] = 1.0  # 对角线为1
            for j in range(i + 1, n):
                sim = await self.compute_similarity(texts[i], texts[j], method)
                matrix[i, j] = sim
                matrix[j, i] = sim
        
        return matrix
    
    # ==================== 嵌入相似度 ====================
    
    async def _embedding_similarity(self, text1: str, text2: str) -> float:
        """基于嵌入向量的余弦相似度"""
        if not self.config.embedding_func:
            logger.warning("未配置嵌入函数，回退到TF-IDF")
            return self._tfidf_similarity(text1, text2)
        
        # 获取嵌入（带缓存）
        emb1 = await self._get_embedding(text1)
        emb2 = await self._get_embedding(text2)
        
        if emb1 is None or emb2 is None:
            return self._tfidf_similarity(text1, text2)
        
        # 计算余弦相似度
        return self._cosine_similarity(emb1, emb2)
    
    async def _get_embedding(self, text: str) -> Optional[np.ndarray]:
        """获取文本嵌入（带缓存）"""
        # 检查缓存
        cache_key = self._get_cache_key(text)
        if self.config.enable_cache and cache_key in self._embedding_cache:
            self.stats["cache_hits"] += 1
            return self._embedding_cache[cache_key]
        
        try:
            self.stats["embedding_calls"] += 1
            # 调用嵌入函数
            embeddings = await self.config.embedding_func([text])
            embedding = np.array(embeddings[0])
            
            # 存入缓存
            if self.config.enable_cache:
                if len(self._embedding_cache) >= self.config.embedding_cache_size:
                    # 简单的LRU：删除一半缓存
                    keys_to_remove = list(self._embedding_cache.keys())[:len(self._embedding_cache)//2]
                    for key in keys_to_remove:
                        del self._embedding_cache[key]
                self._embedding_cache[cache_key] = embedding
            
            return embedding
            
        except Exception as e:
            logger.error(f"获取嵌入失败: {e}")
            return None
    
    async def _batch_embedding_similarity_matrix(self, texts: List[str]) -> np.ndarray:
        """批量计算嵌入相似度矩阵"""
        n = len(texts)
        
        try:
            # 批量获取嵌入
            embeddings = await self.config.embedding_func(texts)
            embeddings = np.array(embeddings)
            
            # 归一化
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
            norms = np.where(norms == 0, 1, norms)  # 避免除零
            normalized = embeddings / norms
            
            # 计算相似度矩阵
            similarity_matrix = np.dot(normalized, normalized.T)
            
            # 确保对角线为1，值在[0,1]范围内
            np.fill_diagonal(similarity_matrix, 1.0)
            similarity_matrix = np.clip(similarity_matrix, 0.0, 1.0)
            
            return similarity_matrix
            
        except Exception as e:
            logger.error(f"批量嵌入计算失败: {e}")
            # 回退到逐对计算
            matrix = np.zeros((n, n))
            for i in range(n):
                matrix[i, i] = 1.0
                for j in range(i + 1, n):
                    sim = self._tfidf_similarity(texts[i], texts[j])
                    matrix[i, j] = sim
                    matrix[j, i] = sim
            return matrix
    
    # ==================== TF-IDF相似度 ====================
    
    def _tfidf_similarity(self, text1: str, text2: str) -> float:
        """基于TF-IDF的余弦相似度"""
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            
            # 创建向量化器
            vectorizer = TfidfVectorizer(
                max_features=self.config.tfidf_max_features,
                ngram_range=self.config.tfidf_ngram_range,
                stop_words='english'
            )
            
            # 向量化
            tfidf_matrix = vectorizer.fit_transform([text1, text2])
            
            # 计算余弦相似度
            similarity = (tfidf_matrix * tfidf_matrix.T).toarray()[0, 1]
            
            return float(similarity)
            
        except ImportError:
            logger.warning("sklearn未安装，回退到Jaccard")
            return self._jaccard_similarity(text1, text2)
        except Exception as e:
            logger.error(f"TF-IDF计算失败: {e}")
            return self._jaccard_similarity(text1, text2)
    
    # ==================== Jaccard相似度 ====================
    
    def _jaccard_similarity(self, text1: str, text2: str) -> float:
        """Jaccard相似度（词袋模型）"""
        tokens1 = set(self._tokenize(text1))
        tokens2 = set(self._tokenize(text2))
        
        if not tokens1 or not tokens2:
            return 0.0
        
        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)
        
        return intersection / union if union > 0 else 0.0
    
    # ==================== BM25相似度 ====================
    
    def _bm25_similarity(self, text1: str, text2: str, k1: float = 1.5, b: float = 0.75) -> float:
        """
        基于BM25的相似度
        将text1视为查询，text2视为文档
        """
        query_tokens = self._tokenize(text1)
        doc_tokens = self._tokenize(text2)
        
        if not query_tokens or not doc_tokens:
            return 0.0
        
        doc_length = len(doc_tokens)
        avg_doc_length = doc_length  # 单文档情况
        
        # 计算词频
        from collections import Counter
        doc_tf = Counter(doc_tokens)
        
        score = 0.0
        for token in query_tokens:
            if token in doc_tf:
                tf = doc_tf[token]
                # 简化的BM25公式（单文档IDF=1）
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * doc_length / avg_doc_length)
                score += numerator / denominator
        
        # 归一化到[0,1]
        max_possible_score = len(query_tokens) * (k1 + 1)
        normalized_score = score / max_possible_score if max_possible_score > 0 else 0.0
        
        return min(1.0, normalized_score)
    
    # ==================== 混合相似度 ====================
    
    async def _hybrid_similarity(self, text1: str, text2: str) -> float:
        """混合多种相似度方法"""
        weights = self.config.hybrid_weights
        total_weight = sum(weights.values())
        
        scores = {}
        
        # 嵌入相似度
        if "embedding" in weights and weights["embedding"] > 0:
            if self.config.embedding_func:
                scores["embedding"] = await self._embedding_similarity(text1, text2)
            else:
                scores["embedding"] = 0.0
        
        # TF-IDF相似度
        if "tfidf" in weights and weights["tfidf"] > 0:
            scores["tfidf"] = self._tfidf_similarity(text1, text2)
        
        # Jaccard相似度
        if "jaccard" in weights and weights["jaccard"] > 0:
            scores["jaccard"] = self._jaccard_similarity(text1, text2)
        
        # 加权平均
        weighted_sum = sum(
            scores.get(method, 0.0) * weight 
            for method, weight in weights.items()
        )
        
        return weighted_sum / total_weight if total_weight > 0 else 0.0
    
    # ==================== 工具方法 ====================
    
    def _tokenize(self, text: str) -> List[str]:
        """分词"""
        import re
        # 转小写，移除标点，分词
        text = re.sub(r'[^\w\s]', ' ', text.lower())
        return [token for token in text.split() if len(token) > 1]
    
    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """计算余弦相似度"""
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(np.dot(vec1, vec2) / (norm1 * norm2))
    
    def _get_cache_key(self, text: str) -> str:
        """生成缓存键"""
        # 使用文本的前200字符的哈希
        import hashlib
        return hashlib.md5(text[:200].encode()).hexdigest()
    
    def _fallback_similarity(self, text1: str, text2: str) -> float:
        """回退相似度计算"""
        if self.config.fallback_method == SimilarityMethod.TFIDF:
            return self._tfidf_similarity(text1, text2)
        else:
            return self._jaccard_similarity(text1, text2)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = self.stats.copy()
        stats["cache_size"] = len(self._embedding_cache)
        stats["cache_hit_rate"] = (
            self.stats["cache_hits"] / self.stats["embedding_calls"] 
            if self.stats["embedding_calls"] > 0 else 0.0
        )
        return stats
    
    def clear_cache(self):
        """清空缓存"""
        self._embedding_cache.clear()


# ==================== 便捷函数 ====================

_global_calculator: Optional[SemanticSimilarityCalculator] = None


def get_similarity_calculator(
    embedding_func: Optional[Callable] = None,
    method: SimilarityMethod = SimilarityMethod.TFIDF
) -> SemanticSimilarityCalculator:
    """获取全局相似度计算器"""
    global _global_calculator
    
    if _global_calculator is None:
        config = SimilarityConfig(
            method=method,
            embedding_func=embedding_func
        )
        _global_calculator = SemanticSimilarityCalculator(config)
    elif embedding_func is not None and _global_calculator.config.embedding_func is None:
        # 更新嵌入函数
        _global_calculator.config.embedding_func = embedding_func
        _global_calculator.config.method = SimilarityMethod.EMBEDDING
    
    return _global_calculator


async def compute_semantic_similarity(
    text1: str, 
    text2: str,
    embedding_func: Optional[Callable] = None
) -> float:
    """
    便捷函数：计算语义相似度
    
    Args:
        text1: 第一个文本
        text2: 第二个文本
        embedding_func: 嵌入函数（可选）
        
    Returns:
        相似度分数 [0, 1]
    """
    calculator = get_similarity_calculator(embedding_func)
    return await calculator.compute_similarity(text1, text2)
