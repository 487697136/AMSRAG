"""
相似度计算策略模式

提供统一的相似度计算接口，支持异步和同步两种模式。
用于消除去重和MMR方法中的代码重复。
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional
from .similarity import SemanticSimilarityCalculator

logger = logging.getLogger(__name__)


class SimilarityStrategy(ABC):
    """相似度计算策略基类"""
    
    @abstractmethod
    async def compute_similarity(self, text1: str, text2: str) -> float:
        """
        计算两个文本的相似度
        
        Args:
            text1: 第一个文本
            text2: 第二个文本
            
        Returns:
            相似度分数 [0, 1]
        """
        pass
    
    @abstractmethod
    def get_strategy_name(self) -> str:
        """获取策略名称"""
        pass


class AsyncSimilarityStrategy(SimilarityStrategy):
    """异步相似度计算策略（使用语义相似度计算器）"""
    
    def __init__(self, similarity_calculator: SemanticSimilarityCalculator):
        """
        初始化异步策略
        
        Args:
            similarity_calculator: 语义相似度计算器实例
        """
        self.similarity_calculator = similarity_calculator
    
    async def compute_similarity(self, text1: str, text2: str) -> float:
        """
        使用语义相似度计算器计算相似度（异步）
        
        支持多种方法：EMBEDDING, TFIDF, JACCARD, BM25, HYBRID
        """
        try:
            sim = await self.similarity_calculator.compute_similarity(text1, text2)
            return sim
        except Exception as e:
            logger.warning(f"异步相似度计算失败: {e}，使用默认值0.0")
            return 0.0
    
    def get_strategy_name(self) -> str:
        return f"async_{self.similarity_calculator.config.method.value}"


class SyncSimilarityStrategy(SimilarityStrategy):
    """同步相似度计算策略（使用Jaccard相似度）"""
    
    def __init__(self):
        """初始化同步策略"""
        pass
    
    async def compute_similarity(self, text1: str, text2: str) -> float:
        """
        使用Jaccard相似度计算（同步，向后兼容）
        
        公式：0.7 * jaccard + 0.3 * length_ratio
        """
        return self._compute_jaccard_similarity(text1, text2)
    
    def _compute_jaccard_similarity(self, text1: str, text2: str) -> float:
        """
        计算Jaccard相似度
        
        Args:
            text1: 第一个文本
            text2: 第二个文本
            
        Returns:
            相似度分数 [0, 1]
        """
        tokens1 = set(text1.split()) if text1 else set()
        tokens2 = set(text2.split()) if text2 else set()
        
        if not tokens1 or not tokens2:
            return 0.0
        
        # Jaccard相似度
        inter = tokens1 & tokens2
        union = tokens1 | tokens2
        jaccard = len(inter) / len(union) if union else 0.0
        
        # 长度比率
        len_ratio = (
            min(len(text1), len(text2)) / max(len(text1), len(text2))
            if text1 and text2
            else 0.0
        )
        
        # 组合分数
        return 0.7 * jaccard + 0.3 * len_ratio
    
    def get_strategy_name(self) -> str:
        return "sync_jaccard"


def create_similarity_strategy(
    similarity_calculator: Optional[SemanticSimilarityCalculator] = None,
    use_async: bool = True
) -> SimilarityStrategy:
    """
    创建相似度计算策略
    
    Args:
        similarity_calculator: 语义相似度计算器（异步策略需要）
        use_async: 是否使用异步策略
        
    Returns:
        相似度计算策略实例
    """
    if use_async and similarity_calculator is not None:
        return AsyncSimilarityStrategy(similarity_calculator)
    else:
        return SyncSimilarityStrategy()
