"""
检索模块

提供多源检索结果的统一表示、对齐和融合功能：
- RetrievalResult：统一的检索结果数据结构
- 结果对齐：将不同检索源的结果转换为统一格式
- RRF/CA-RRF 融合：基于互惠排名的多源结果合并与置信度感知加权
- 语义相似度：支持多种相似度计算方法（嵌入/TF-IDF/Jaccard）
"""

from .alignment import (
    RetrievalResult,
    RetrievalAdapter,
    create_retrieval_adapter,
    align_retrieval_results,
)

# 融合实现放在 fusion_impl 中，避免历史文件编码问题
from .fusion_impl import ConfidenceAwareFusion, FusionConfig, create_fusion_engine

# 语义相似度模块
from .similarity import (
    SemanticSimilarityCalculator,
    SimilarityConfig,
    SimilarityMethod,
    get_similarity_calculator,
    compute_semantic_similarity,
)

# 相似度策略模块
from .similarity_strategy import (
    SimilarityStrategy,
    AsyncSimilarityStrategy,
    SyncSimilarityStrategy,
    create_similarity_strategy,
)

__all__ = [
    # 数据结构
    "RetrievalResult",
    # 对齐功能
    "RetrievalAdapter",
    "create_retrieval_adapter",
    "align_retrieval_results",
    # 融合功能
    "ConfidenceAwareFusion",
    "FusionConfig",
    "create_fusion_engine",
    # 相似度功能
    "SemanticSimilarityCalculator",
    "SimilarityConfig",
    "SimilarityMethod",
    "get_similarity_calculator",
    "compute_semantic_similarity",
    # 相似度策略
    "SimilarityStrategy",
    "AsyncSimilarityStrategy",
    "SyncSimilarityStrategy",
    "create_similarity_strategy",
]
