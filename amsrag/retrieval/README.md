# 置信度感知的多源检索融合模块

本模块实现了论文中描述的CA-RRF（Confidence-Aware Reciprocal Rank Fusion）算法，并集成了多种语义相似度计算方法。

## 核心组件

### 1. 统一检索结果表示 (`alignment.py`)

所有检索器的结果都转换为统一的`RetrievalResult`格式：

```python
from amsrag.retrieval import RetrievalResult

result = RetrievalResult(
    content="检索到的文本内容",
    score=0.85,
    source="bm25",  # "naive", "bm25", "local", "global"
    chunk_id="chunk-123",
    rank=1,
    metadata={}
)
```

### 2. 语义相似度计算器 (`similarity.py`)

支持多种相似度计算方法，用于MMR多样性约束和内容去重：

```python
from amsrag.retrieval import (
    SemanticSimilarityCalculator,
    SimilarityConfig,
    SimilarityMethod
)

# 创建TF-IDF相似度计算器（推荐，无需API）
config = SimilarityConfig(method=SimilarityMethod.TFIDF)
calculator = SemanticSimilarityCalculator(config)

# 计算相似度
similarity = await calculator.compute_similarity(text1, text2)

# 批量计算相似度矩阵
matrix = await calculator.compute_similarity_matrix(texts)
```

**支持的相似度方法**：

| 方法 | 说明 | 适用场景 |
|------|------|---------|
| `EMBEDDING` | 基于嵌入向量的余弦相似度 | 最准确，需要嵌入API |
| `TFIDF` | 基于TF-IDF的余弦相似度 | 推荐默认，无需API |
| `JACCARD` | Jaccard词袋相似度 | 最简单，速度最快 |
| `BM25` | BM25相似度 | 关键词匹配场景 |
| `HYBRID` | 混合多种方法 | 综合考虑多种特征 |

### 3. CA-RRF融合引擎 (`fusion_impl.py`)

实现论文公式：

**CA-RRF公式**：
```
CA-RRF(d) = Σ_{r∈R_S} w_r(c,α) × 1/(k_r(c) + rank_r(d))
```

**权重计算公式**：
```
w_r(c,α) = (1-ρ(α)) × 1/|R_S| + ρ(α) × β_r^(c)
ρ(α) = σ(κ(α-α_0))
```

**MMR多样性约束**（使用语义相似度）：
```
d* = argmax_{d ∉ L} [CA-RRF(d) - λ × max_{d'∈L} Sim(d,d')]
```

## 使用方法

### 基础融合（异步）

```python
from amsrag.retrieval import create_fusion_engine, RetrievalResult, SimilarityMethod

# 创建融合引擎（使用TF-IDF相似度）
fusion_engine = create_fusion_engine(
    k=60.0,
    max_results=20,
    confidence_aware=True,
    similarity_method=SimilarityMethod.TFIDF
)

# 准备检索结果
results_by_source = {
    "naive": [
        RetrievalResult(content="...", score=0.9, source="naive", chunk_id="1", rank=1),
    ],
    "bm25": [
        RetrievalResult(content="...", score=15.2, source="bm25", chunk_id="2", rank=1),
    ],
}

# 异步融合
fused_results = await fusion_engine.fuse_results(
    results_by_source=results_by_source,
    query_complexity={
        "complexity": "multi_hop",
        "confidence": 0.65,
    }
)
```

### 同步融合（向后兼容）

```python
# 同步版本
fused_results = fusion_engine.fuse_results_sync(
    results_by_source=results_by_source,
    query_complexity=query_complexity
)
```

### 使用嵌入相似度

```python
# 定义嵌入函数
async def my_embedding_func(texts: list[str]) -> np.ndarray:
    # 调用嵌入API
    return embeddings

# 创建使用嵌入的融合引擎
fusion_engine = create_fusion_engine(
    embedding_func=my_embedding_func,
    similarity_method=SimilarityMethod.EMBEDDING
)
```

### 在GraphRAG中使用

```python
from amsrag import EnhancedGraphRAG

rag = EnhancedGraphRAG(
    enable_enhanced_features=True,
    enable_confidence_fusion=True,
    rrf_k=60.0,
    fusion_max_results=20
)

# 自动使用CA-RRF融合（内部使用语义相似度）
response = await rag.aquery("复杂查询问题")
```

## 配置选项

### FusionConfig

```python
from amsrag.retrieval import FusionConfig, SimilarityMethod

config = FusionConfig(
    # RRF参数
    k=60.0,                      # RRF基础平滑参数
    max_results=20,              # 最大融合结果数
    
    # 置信度感知
    confidence_aware=True,       # 启用置信度感知
    weight_adjustment_factor=2.0,# κ参数
    
    # MMR多样性
    enable_mmr=True,             # 启用MMR多样性
    mmr_lambda=0.5,              # MMR的λ参数
    mmr_similarity_threshold=0.85,
    
    # 去重
    diversity_threshold=0.85,    # 去重阈值
    
    # 语义相似度配置
    similarity_method=SimilarityMethod.TFIDF,  # 相似度方法
    embedding_func=None,         # 嵌入函数（可选）
    embedding_cache_size=1000,   # 嵌入缓存大小
)
```

### SimilarityConfig

```python
from amsrag.retrieval import SimilarityConfig, SimilarityMethod

config = SimilarityConfig(
    method=SimilarityMethod.TFIDF,
    
    # 嵌入配置
    embedding_func=None,
    embedding_cache_size=1000,
    
    # TF-IDF配置
    tfidf_max_features=5000,
    tfidf_ngram_range=(1, 2),
    
    # 混合方法权重
    hybrid_weights={
        "embedding": 0.7,
        "tfidf": 0.2,
        "jaccard": 0.1
    },
    
    # 回退配置
    fallback_method=SimilarityMethod.TFIDF,
)
```

## 先验权重矩阵 β_r^(c)

根据复杂度为每个检索器分配先验权重：

| 检索器 | Zero-hop | One-hop | Multi-hop |
|--------|----------|---------|-----------|
| llm_only | 0.8 | 0.0 | 0.0 |
| naive | 0.05 | 0.35 | 0.15 |
| bm25 | 0.1 | 0.3 | 0.15 |
| local | 0.025 | 0.2 | 0.35 |
| global | 0.025 | 0.15 | 0.35 |

## 动态k参数 k_r(c)

根据复杂度调整平滑参数：

| 复杂度 | k值 | 说明 |
|--------|-----|------|
| zero_hop | 80 | 简单查询，大k值突出高相关 |
| one_hop | 60 | 标准k值 |
| multi_hop | 40 | 复杂查询，小k值保留多样性 |

## 性能特征

- **语义级别相似度**：使用TF-IDF或嵌入计算真正的语义相似度
- **无需训练**：CA-RRF不需要额外的学习过程
- **动态适应**：根据查询复杂度和置信度自动调整
- **缓存优化**：嵌入结果自动缓存，避免重复计算
- **异步支持**：完全支持异步操作，适合高并发场景

## 统计信息

```python
# 获取融合统计
fusion_stats = fusion_engine.get_fusion_stats()
print(f"总融合次数: {fusion_stats['total_fusions']}")
print(f"相似度计算统计: {fusion_stats['similarity_stats']}")

# 获取相似度计算统计
sim_stats = fusion_engine.get_similarity_stats()
print(f"总计算次数: {sim_stats['total_computations']}")
print(f"缓存命中率: {sim_stats['cache_hit_rate']:.2%}")
```

## 论文公式对应

| 论文公式 | 代码实现 | 文件位置 |
|---------|---------|---------|
| 式(4) CA-RRF | `_compute_rrf_scores` | `fusion_impl.py` |
| 式(5) w_r(c,α) | `_calculate_confidence_aware_weights` | `fusion_impl.py` |
| 式(6) MMR | `_apply_mmr_diversity` | `fusion_impl.py` |
| 语义相似度 | `SemanticSimilarityCalculator` | `similarity.py` |

## 参考文献

- Cormack et al. (2009): Reciprocal Rank Fusion
- Carbonell & Goldstein (1998): MMR (Maximal Marginal Relevance)
- Reimers & Gurevych (2019): Sentence-BERT
- Guo et al. (2017): Temperature Scaling
