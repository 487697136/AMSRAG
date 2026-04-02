"""
AMSRAG - 增强版图检索增强生成系统 (整合版)

一个高性能、模块化的RAG系统，集成了：
- Modern Evaluator：基于RAGAS的现代评估体系 (整合传统+现代评估)
- Simple Optimizer：轻量级自适应优化器
- Complexity Router：智能复杂度感知路由
- Confidence Calibration：置信度校准系统

v0.2.0 整合版特性：
- 统一评估接口：整合传统与现代评估功能
- 统一融合接口：整合传统融合策略
- 保持向后兼容性
- 提供便捷的创建函数
"""

__version__ = "0.6.0"
__author__ = "AMSRAG Team"

# 核心类 - 向后兼容
from .graphrag import (
    GraphRAG,                    # 向后兼容的主类
    EnhancedGraphRAG,           # 新的增强版主类
    create_enhanced_graphrag,    # 创建增强版实例
    create_basic_graphrag,       # 创建基础版实例
)

# 基础数据结构和接口
from .base import (
    QueryParam,
    BaseVectorStorage,
    BaseKVStorage,
    BaseGraphStorage,
    CommunitySchema,
    TextChunkSchema,
    StorageNameSpace,
)

# 存储实现
from ._storage import (
    JsonKVStorage,
    NetworkXStorage,
    SimpleVectorDBStorage,
    # 新增存储实现
    FAISSVectorStorage,
    Neo4jStorage,
    HNSWVectorStorage,
    create_faiss_storage,
)

# 核心处理模块
from .chunking import get_chunks, chunking_by_token_size
from .entity_extraction import extract_entities
from .community import generate_community_report

# 查询处理
from .query_processing import (
    local_query,
    global_query, 
    global_local_query,
    naive_query,
)

# 复杂度分析和路由 (新增)
from .complexity import (
    ComplexityClassifier,
    ComplexityClassifierConfig,
    ComplexityAwareRouter,
)

# ============= 增强功能模块 (整合版) =============

# 评估系统
from .evaluation import RAGMetrics, LatencyTracker, calculate_bleu, calculate_ndcg

# 融合功能
from .retrieval import ConfidenceAwareFusion, FusionConfig, create_fusion_engine

# 简单的评估器创建函数
def create_evaluator(evaluator_type: str = "basic", **kwargs):
    """
    创建评估器实例
    
    Args:
        evaluator_type: 评估器类型，目前支持 "basic"
        **kwargs: 评估器配置参数
        
    Returns:
        评估器实例（RAGMetrics）
    """
    if evaluator_type == "basic":
        return RAGMetrics()
    else:
        logger.warning(f"不支持的评估器类型: {evaluator_type}，使用basic")
        return RAGMetrics()

# 检索结果对齐 (从实际实现的模块导入)
from .retrieval.alignment import (
    RetrievalResult,
    RetrievalAdapter,
)

# 工具函数
from ._utils import (
    logger,  # 添加logger导入
    compute_args_hash,
    compute_mdhash_id,
    normalize_text,
    compute_text_hash,
    get_timestamp,
    save_json,
    load_json,
)

# LLM和嵌入函数
from ._llm import (
    gpt_4o_complete,
    gpt_4o_mini_complete,
    openai_embedding,
    azure_gpt_4o_complete,
    azure_gpt_4o_mini_complete,
    azure_openai_embedding,
    amazon_bedrock_embedding,
    create_amazon_bedrock_complete_function,
    siliconflow_embedding,
)

# 配置管理
from .config import (
    load_config,
    save_config,
    create_config_from_template,
    validate_config,
    get_default_config,
)

import os
from pathlib import Path
from typing import Optional as _Optional, Dict as _Dict, Any as _Any

import yaml  # 依赖已在 requirements.txt 中声明

# ============= 主要导出列表 =============
__all__ = [
    # 版本信息
    "__version__",
    "__author__",
    
    # 主要类
    "GraphRAG",
    "EnhancedGraphRAG", 
    "create_enhanced_graphrag",
    "create_basic_graphrag",
    "create_amsrag",
    
    # 基础接口
    "QueryParam",
    "BaseVectorStorage",
    "BaseKVStorage", 
    "BaseGraphStorage",
    "CommunitySchema",
    "TextChunkSchema",
    "StorageNameSpace",
    
    # 存储实现
    "JsonKVStorage",
    "NetworkXStorage",
    "SimpleVectorDBStorage",
    "FAISSVectorStorage",
    "Neo4jStorage", 
    "HNSWVectorStorage",
    "create_faiss_storage",
    
    # 核心处理
    "get_chunks",
    "chunking_by_token_size",
    "extract_entities",
    "generate_community_report",
    
    # 查询处理
    "local_query",
    "global_query",
    "global_local_query",
    "naive_query",
    
    # 复杂度分析 (新增)
    "ComplexityClassifier",
    "ComplexityClassifierConfig", 
    "ComplexityAwareRouter",
    
    # ============= 增强功能 (整合版) =============

    # 评估系统
    "RAGMetrics",
    "LatencyTracker",
    "calculate_bleu",
    "calculate_ndcg",
    "create_evaluator",
    
    # 融合功能
    "ConfidenceAwareFusion",
    "FusionConfig",
    "create_fusion_engine",
    
    # 检索结果对齐
    "RetrievalResult",
    "RetrievalAdapter",
    # 混合检索功能已集成到其他模块中
    
    # 工具函数
    "compute_args_hash",
    "compute_mdhash_id",
    "normalize_text",
    "compute_text_hash",
    "get_timestamp",
    "save_json", 
    "load_json",
    
    # LLM函数
    "gpt_4o_complete",
    "gpt_4o_mini_complete",
    "openai_embedding",
    "siliconflow_embedding",
    
    # 配置管理
    "load_config",
    "save_config",
    "get_default_config",
    "create_graphrag_from_paper_config",
]


def create_graphrag_from_paper_config(
    config_path: str = "config_paper_framework.yaml",
    overrides: _Optional[_Dict[str, _Any]] = None,
) -> EnhancedGraphRAG:
    """
    根据论文使用的 YAML 配置文件创建 EnhancedGraphRAG/AMSRAG 实例。
    
    该函数主要完成以下映射：
    - 基础运行目录 / 开关：working_dir, enable_enhanced_features
    - 复杂度分类器模型路径: complexity_classifier.model_path
    - 渐进式检索策略阈值: retrieval_strategy.thresholds.high/medium
    - CA-RRF 融合配置: fusion.rrf_k, fusion.max_results, dynamic_k_values, prior_weights,
      fusion.mmr, fusion.deduplication
    
    LLM/Embedding 的具体模型名称和提供方与运行环境强相关，因此保持使用代码默认，
    用户可通过 EnhancedGraphRAG 的参数或环境变量自行覆盖。
    """
    cfg_path = Path(config_path)
    if not cfg_path.is_file():
        # 允许相对于项目根目录的路径
        root_candidate = Path(__file__).parent.parent / cfg_path.name
        if root_candidate.is_file():
            cfg_path = root_candidate
        else:
            raise FileNotFoundError(f"找不到配置文件: {config_path}")

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    overrides = overrides or {}

    working_dir = overrides.get(
        "working_dir", cfg.get("working_dir", "./amsrag_cache")
    )
    enable_enhanced_features = overrides.get(
        "enable_enhanced_features", cfg.get("enable_enhanced_features", True)
    )

    # 复杂度分类器配置
    complexity_cfg = cfg.get("complexity_classifier", {})
    model_path = overrides.get(
        "model_path",
        complexity_cfg.get(
            "model_path", "amsrag/models/modernbert_complexity_classifier_standard"
        ),
    )

    # 渐进式检索策略阈值
    strategy_cfg = cfg.get("retrieval_strategy", {}).get("thresholds", {})
    confidence_high_threshold = overrides.get(
        "confidence_high_threshold", strategy_cfg.get("high", 0.9)
    )
    confidence_medium_threshold = overrides.get(
        "confidence_medium_threshold", strategy_cfg.get("medium", 0.6)
    )

    # CA-RRF 融合配置
    fusion_cfg = cfg.get("fusion", {})
    dynamic_k_values = fusion_cfg.get("dynamic_k_values", {})
    prior_weights = fusion_cfg.get("prior_weights", {})
    mmr_cfg = fusion_cfg.get("mmr", {})
    dedup_cfg = fusion_cfg.get("deduplication", {})

    fusion_config = FusionConfig(
        k=fusion_cfg.get("rrf_k", 60.0),
        max_results=fusion_cfg.get("max_results", 20),
        confidence_aware=fusion_cfg.get("confidence_aware", True),
        dynamic_k_values=dynamic_k_values,
        prior_weights=prior_weights,
        enable_mmr=mmr_cfg.get("enabled", True),
        mmr_lambda=mmr_cfg.get("lambda", 0.5),
        mmr_similarity_threshold=mmr_cfg.get("similarity_threshold", 0.85),
        diversity_threshold=dedup_cfg.get("threshold", 0.85),
    )

    # 构造 EnhancedGraphRAG（AMSRAG）
    rag = EnhancedGraphRAG(
        working_dir=str(working_dir),
        enable_enhanced_features=enable_enhanced_features,
        model_path=str(model_path),
        confidence_high_threshold=confidence_high_threshold,
        confidence_medium_threshold=confidence_medium_threshold,
        fusion_config=fusion_config,
        rrf_k=fusion_config.k,
        fusion_max_results=fusion_config.max_results,
    )

    return rag

# ============= 便捷创建函数 =============

def create_amsrag(enhanced: bool = True, **kwargs):
    """
    便捷函数：创建amsrag实例
    
    Args:
        enhanced: 是否启用增强功能（默认True）
        **kwargs: 其他配置参数
    
    Returns:
        EnhancedGraphRAG实例
    
    Examples:
        >>> # 创建增强版（推荐）
        >>> rag = create_amsrag()
        
        >>> # 创建基础版（兼容老代码）
        >>> rag = create_amsrag(enhanced=False)
        
        >>> # 自定义配置
        >>> rag = create_amsrag(
        ...     working_dir="./my_graphrag",
        ...     enable_naive_rag=True
        ... )
    """
    if enhanced:
        return create_enhanced_graphrag(**kwargs)
    else:
        return create_basic_graphrag(**kwargs)

def create_unified_pipeline(evaluator_type: str = "modern", **kwargs):
    """
    创建统一的RRF融合+评估管道
    
    Args:
        evaluator_type: 评估器类型 ("modern", "comprehensive", "basic")
        **kwargs: 配置参数
        
    Returns:
        (fusion_engine, evaluator) 元组
    """
    from .retrieval import create_fusion_engine
    
    # 创建RRF融合引擎
    fusion_engine = create_fusion_engine(**kwargs)
    
    # 创建评估器
    evaluator = create_evaluator(evaluator_type, **kwargs)
    
    return fusion_engine, evaluator

def get_available_fusion_types():
    """获取可用的融合类型"""
    available_types = []
    
    # 检查RRF融合是否可用
    try:
        from .retrieval import ConfidenceAwareFusion
        available_types.append("rrf")
    except ImportError:
        pass
    
    # 默认总是有简单的线性融合作为回退
    if "rrf" not in available_types:
        available_types.append("fallback")
    
    return available_types

# 系统能力标志
RRF_FUSION_AVAILABLE = True  # RRF融合总是可用
BASIC_EVALUATION_AVAILABLE = True  # 基础评估可用

def get_system_capabilities():
    """获取系统可用能力"""
    capabilities = {
        "fusion_types": get_available_fusion_types(),
        "rrf_fusion_available": RRF_FUSION_AVAILABLE,
        "basic_evaluation_available": BASIC_EVALUATION_AVAILABLE,
        "enhanced_features": [
            "modern_evaluator", 
            "complexity_router",
            "rrf_fusion",
            "retrieval_alignment"
        ]
    }
    return capabilities

# 添加便捷函数到导出列表
__all__.extend([
    "create_unified_pipeline", 
    "get_system_capabilities"
])

# ============= 依赖检查和初始化 =============

def check_dependencies():
    """检查依赖项是否正确安装"""
    import warnings
    
    try:
        import torch
        logger.info(f"PyTorch version: {torch.__version__}")
    except ImportError:
        warnings.warn("PyTorch not found. Enhanced features may not work.")
    
    try:
        import sentence_transformers
        logger.info(f"Sentence Transformers version: {sentence_transformers.__version__}")
    except ImportError:
        warnings.warn("Sentence Transformers not found. Modern evaluator may not work.")
    
    try:
        import sklearn
        logger.info(f"Scikit-learn version: {sklearn.__version__}")
    except ImportError:
        warnings.warn("Scikit-learn not found. Some evaluation features may not work.")

# 初始化时检查依赖
try:
    check_dependencies()
except Exception as e:
    logger.warning(f"Dependency check failed: {e}")

# 显示欢迎信息
logger.info(f"AMSRAG v{__version__} (置信度感知融合版) loaded successfully!")
logger.info("🔧 核心特性: RRF置信度感知融合, Modern Evaluator")
logger.info("🚀 融合技术: 基于互惠排名融合的智能多源检索")
logger.info("💡 快速开始: create_amsrag() | 管道创建: create_unified_pipeline()")
logger.info(f"📊 系统能力: {len(get_system_capabilities()['fusion_types'])} 种融合策略可用")
