"""
多源检索融合模块（实现文件）

实现基于 RRF (Reciprocal Rank Fusion) 的多源检索结果融合算法，
并按照论文设计集成：
- 查询复杂度/置信度感知权重调整 (CA-RRF)
- 动态 k_r(c) 参数
- MMR 多样性约束（使用语义相似度）
- 基于内容相似度的去重

论文参考：
- RRF: Cormack et al., "Reciprocal Rank Fusion outperforms Condorcet and 
  individual Rank Learning Methods", SIGIR 2009
- MMR: Carbonell & Goldstein, "The Use of MMR, Diversity-Based Reranking 
  for Reordering Documents and Producing Summaries", SIGIR 1998
"""

import logging
import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from collections import defaultdict

from .alignment import RetrievalResult
from .similarity import (
    SemanticSimilarityCalculator, 
    SimilarityConfig, 
    SimilarityMethod,
    get_similarity_calculator
)
from .similarity_strategy import (
    SimilarityStrategy,
    AsyncSimilarityStrategy,
    SyncSimilarityStrategy,
    create_similarity_strategy
)

logger = logging.getLogger(__name__)


@dataclass
class FusionConfig:
    """融合配置参数

    该配置与 `config_paper_framework.yaml` 中的 `fusion` 配置保持一致：
    - dynamic_k_values:   k_r(c) 矩阵
    - prior_weights:      beta_r^(c) 先验权重矩阵
    - mmr_*:              MMR 多样性控制参数
    - diversity_threshold: 内容去重/相似度阈值
    - similarity_method:  语义相似度计算方法
    """

    # 基础 RRF 参数（当 dynamic_k_values 为空时使用）
    k: float = 60.0
    max_results: int = 20

    # 多样性与去重
    diversity_threshold: float = 0.85  # 内容相似度阈值（用于去重）
    source_weights: Dict[str, float] = field(
        default_factory=lambda: {
            "bm25": 1.0,
            "vector": 1.0,
            "local": 1.0,
            "global": 1.0,
        }
    )

    # 置信度感知权重调整参数（论文公式 9/10）
    confidence_aware: bool = True
    weight_adjustment_factor: float = 2.0  # kappa
    base_weight: float = 0.5  # 保留字段，当前未单独使用

    # 动态 k 参数矩阵 k_r(c)
    # 结构: {"zero_hop": {"naive": 80, "bm25": 80, ...}, ...}
    dynamic_k_values: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # 先验权重矩阵 beta_r^(c)
    # 结构: {"zero_hop": {"llm_only": 0.8, "naive": 0.05, ...}, ...}
    prior_weights: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # MMR 多样性约束参数（论文公式 11）
    enable_mmr: bool = True
    mmr_lambda: float = 0.5
    mmr_similarity_threshold: float = 0.85  # 与已选结果的最大相似度阈值

    # 语义相似度配置（用于MMR和去重）
    embedding_func: Optional[Callable] = None  # 嵌入函数，用于语义相似度计算
    similarity_method: SimilarityMethod = SimilarityMethod.TFIDF  # 默认使用TF-IDF（无需API）
    embedding_cache_size: int = 1000  # 嵌入缓存大小
    
    def __post_init__(self):
        """参数验证"""
        # 验证数值范围
        if self.k <= 0:
            raise ValueError(f"k必须大于0，当前值: {self.k}")
        if self.max_results <= 0:
            raise ValueError(f"max_results必须大于0，当前值: {self.max_results}")
        if not 0 <= self.diversity_threshold <= 1:
            raise ValueError(f"diversity_threshold必须在[0,1]范围内，当前值: {self.diversity_threshold}")
        if not 0 <= self.mmr_lambda <= 1:
            raise ValueError(f"mmr_lambda必须在[0,1]范围内，当前值: {self.mmr_lambda}")
        if not 0 <= self.mmr_similarity_threshold <= 1:
            raise ValueError(f"mmr_similarity_threshold必须在[0,1]范围内，当前值: {self.mmr_similarity_threshold}")
        if self.embedding_cache_size < 0:
            raise ValueError(f"embedding_cache_size必须非负，当前值: {self.embedding_cache_size}")


class ConfidenceAwareFusion:
    """置信度感知的多源检索融合器 (CA-RRF)"""

    def __init__(self, config: Optional[FusionConfig] = None) -> None:
        self.config = config or FusionConfig()
        self.fusion_stats: Dict[str, Any] = {
            "total_fusions": 0,
            "avg_sources_per_fusion": 0.0,
            "avg_results_per_source": 0.0,
        }
        
        # 初始化语义相似度计算器
        similarity_config = SimilarityConfig(
            method=self.config.similarity_method,
            embedding_func=self.config.embedding_func,
            embedding_cache_size=self.config.embedding_cache_size,
        )
        self.similarity_calculator = SemanticSimilarityCalculator(similarity_config)
        
        # 初始化相似度计算策略
        self.async_strategy = create_similarity_strategy(
            similarity_calculator=self.similarity_calculator,
            use_async=True
        )
        self.sync_strategy = create_similarity_strategy(
            similarity_calculator=None,
            use_async=False
        )
        
        logger.info(
            f"初始化融合器: 相似度方法={self.config.similarity_method.value}, "
            f"嵌入函数={'已配置' if self.config.embedding_func else '未配置'}, "
            f"策略={self.async_strategy.get_strategy_name()}/{self.sync_strategy.get_strategy_name()}"
        )

    # ========= 公共接口 =========

    async def fuse_results(
        self,
        results_by_source: Dict[str, List[RetrievalResult]],
        query_complexity: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievalResult]:
        """融合多源检索结果（异步方法，支持语义相似度计算）"""
        if not results_by_source:
            logger.warning("没有检索结果可供融合")
            return []

        # 基础统计
        self.fusion_stats["total_fusions"] += 1
        source_count = len(results_by_source)
        total_results = sum(len(v) for v in results_by_source.values())
        prev_avg_sources = self.fusion_stats["avg_sources_per_fusion"]
        t = self.fusion_stats["total_fusions"]
        self.fusion_stats["avg_sources_per_fusion"] = (
            (prev_avg_sources * (t - 1) + source_count) / t
        )
        self.fusion_stats["avg_results_per_source"] = (
            total_results / source_count if source_count else 0.0
        )

        logger.info(
            f"开始融合 {source_count} 个检索源的 {total_results} 个结果"
        )

        # 第 1 步：内容去重（基于语义相似度阈值）
        deduplicated = await self._deduplicate_results(results_by_source)

        # 第 2 步：计算置信度感知权重
        source_weights = self._calculate_confidence_aware_weights(
            list(deduplicated.keys()), query_complexity
        )

        # 第 3 步：CA-RRF 打分
        fused_ranked = self._compute_rrf_scores(
            deduplicated, source_weights, query_complexity
        )

        # 第 4 步：多样性优化（MMR 或简易多样性过滤）
        if self.config.enable_mmr:
            final_results = await self._apply_mmr_diversity(
                fused_ranked, lambda_param=self.config.mmr_lambda
            )
        else:
            final_results = self._apply_diversity_filter(fused_ranked)

        logger.info(f"融合完成，返回 {len(final_results)} 个结果")
        return final_results[: self.config.max_results]
    
    def fuse_results_sync(
        self,
        results_by_source: Dict[str, List[RetrievalResult]],
        query_complexity: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievalResult]:
        """同步版本的融合方法（向后兼容，使用简化相似度）"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果已在异步上下文中，使用简化版本
                return self._fuse_results_simple(results_by_source, query_complexity)
            return loop.run_until_complete(
                self.fuse_results(results_by_source, query_complexity)
            )
        except RuntimeError:
            return self._fuse_results_simple(results_by_source, query_complexity)
    
    def _fuse_results_simple(
        self,
        results_by_source: Dict[str, List[RetrievalResult]],
        query_complexity: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievalResult]:
        """简化版融合（同步，使用Jaccard相似度）"""
        if not results_by_source:
            return []
        
        # 使用简化去重
        deduplicated = self._deduplicate_results_simple(results_by_source)
        source_weights = self._calculate_confidence_aware_weights(
            list(deduplicated.keys()), query_complexity
        )
        fused_ranked = self._compute_rrf_scores(
            deduplicated, source_weights, query_complexity
        )
        
        if self.config.enable_mmr:
            final_results = self._apply_mmr_diversity_simple(
                fused_ranked, lambda_param=self.config.mmr_lambda
            )
        else:
            final_results = self._apply_diversity_filter(fused_ranked)
        
        return final_results[: self.config.max_results]

    # ========= 工具函数 =========

    def _sigmoid(self, x: float) -> float:
        """sigmoid(x) = 1 / (1 + e^{-x})"""
        import math as _math
        return 1.0 / (1.0 + _math.exp(-x))

    # ========= 去重 =========

    async def _deduplicate_results(
        self, results_by_source: Dict[str, List[RetrievalResult]]
    ) -> Dict[str, List[RetrievalResult]]:
        """
        基于语义相似度的去重（异步版本）：
        - 使用配置的相似度方法（嵌入/TF-IDF/Jaccard）
        - 使用 FusionConfig.diversity_threshold 控制"视为重复"的阈值
        - 在重复组内保留归一化分数最高的结果
        """
        return await self._deduplicate_results_unified(
            results_by_source, self.async_strategy
        )
    
    def _deduplicate_results_simple(
        self, results_by_source: Dict[str, List[RetrievalResult]]
    ) -> Dict[str, List[RetrievalResult]]:
        """
        基于Jaccard相似度的简化去重（同步版本，向后兼容）
        """
        # 同步策略需要在异步上下文中运行
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果已在异步上下文中，直接使用同步计算
                return self._deduplicate_results_sync(results_by_source)
            return loop.run_until_complete(
                self._deduplicate_results_unified(results_by_source, self.sync_strategy)
            )
        except RuntimeError:
            return self._deduplicate_results_sync(results_by_source)
    
    def _deduplicate_results_sync(
        self, results_by_source: Dict[str, List[RetrievalResult]]
    ) -> Dict[str, List[RetrievalResult]]:
        """纯同步去重（使用Jaccard相似度，不依赖asyncio）"""
        threshold = getattr(self.config, "diversity_threshold", 0.85)

        representatives: List[RetrievalResult] = []
        rep_to_best: Dict[str, RetrievalResult] = {}

        for source, results in results_by_source.items():
            for result in results:
                norm_text = self._normalize_content_for_comparison(result.content)
                if not norm_text:
                    continue

                matched_rep_id: Optional[str] = None

                for rep in representatives:
                    rep_norm = self._normalize_content_for_comparison(rep.content)
                    sim = self._compute_similarity_jaccard(norm_text, rep_norm)
                    if sim >= threshold:
                        matched_rep_id = rep.id
                        break

                if matched_rep_id is None:
                    representatives.append(result)
                    rep_to_best[result.id] = result
                else:
                    existing = rep_to_best[matched_rep_id]
                    if result.normalize_score() > existing.normalize_score():
                        rep_to_best[matched_rep_id] = result

        deduplicated_by_source: Dict[str, List[RetrievalResult]] = defaultdict(list)
        for best in rep_to_best.values():
            deduplicated_by_source[best.source].append(best)

        for source, items in deduplicated_by_source.items():
            items.sort(key=lambda x: x.normalize_score(), reverse=True)
            for i, r in enumerate(items):
                r.rank = i + 1

        return dict(deduplicated_by_source)
    
    async def _deduplicate_results_unified(
        self,
        results_by_source: Dict[str, List[RetrievalResult]],
        strategy: SimilarityStrategy
    ) -> Dict[str, List[RetrievalResult]]:
        """
        统一的去重方法（使用策略模式）
        
        Args:
            results_by_source: 按源分组的检索结果
            strategy: 相似度计算策略
            
        Returns:
            去重后的结果
        """
        threshold = getattr(self.config, "diversity_threshold", 0.85)

        representatives: List[RetrievalResult] = []
        rep_to_best: Dict[str, RetrievalResult] = {}

        for source, results in results_by_source.items():
            for result in results:
                norm_text = self._normalize_content_for_comparison(result.content)
                if not norm_text:
                    continue

                matched_rep_id: Optional[str] = None

                for rep in representatives:
                    rep_norm = self._normalize_content_for_comparison(rep.content)
                    # 使用策略计算相似度
                    try:
                        sim = await strategy.compute_similarity(norm_text, rep_norm)
                    except Exception as e:
                        logger.warning(f"相似度计算失败: {e}，使用默认值0.0")
                        sim = 0.0
                        
                    if sim >= threshold:
                        matched_rep_id = rep.id
                        break

                if matched_rep_id is None:
                    representatives.append(result)
                    rep_to_best[result.id] = result
                else:
                    existing = rep_to_best[matched_rep_id]
                    if result.normalize_score() > existing.normalize_score():
                        rep_to_best[matched_rep_id] = result

        deduplicated_by_source: Dict[str, List[RetrievalResult]] = defaultdict(list)
        for best in rep_to_best.values():
            deduplicated_by_source[best.source].append(best)

        # 排序并更新 rank
        for source, items in deduplicated_by_source.items():
            items.sort(key=lambda x: x.normalize_score(), reverse=True)
            for i, r in enumerate(items):
                r.rank = i + 1

        total_before = sum(len(v) for v in results_by_source.values())
        total_after = sum(len(v) for v in deduplicated_by_source.values())
        logger.debug(
            f"去重前总结果数: {total_before}, 去重后: {total_after}, "
            f"策略: {strategy.get_strategy_name()}"
        )

        return dict(deduplicated_by_source)

    def _normalize_content_for_comparison(self, content: str) -> str:
        """简单规范化文本，用于相似度计算"""
        if not content:
            return ""
        normalized = " ".join(content.lower().split())
        return normalized[:200]

    # ========= 置信度感知权重 w_r(c, alpha) =========

    def _calculate_confidence_aware_weights(
        self,
        sources: List[str],
        query_complexity: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, float]:
        """
        按论文公式计算置信度感知权重：
        w_r(c,alpha) = (1-rho(alpha)) * 1/|R_S| + rho(alpha) * beta_r^(c)
        其中 rho(alpha) = sigmoid(kappa * (alpha - alpha_0))
        """
        if not self.config.confidence_aware or not query_complexity:
            logger.debug("未启用置信度感知或缺少复杂度信息，使用均匀权重")
            return {s: 1.0 / len(sources) for s in sources} if sources else {}

        complexity = query_complexity.get("complexity", "one_hop")
        confidence = query_complexity.get("confidence", 0.5)

        logger.info(
            f"应用置信度感知权重调整: 复杂度={complexity}, 置信度={confidence:.3f}"
        )

        # 先验权重矩阵 beta_r^(c)：优先使用配置，否则使用默认表
        if self.config.prior_weights:
            prior_matrix = self.config.prior_weights
        else:
            prior_matrix = {
                "zero_hop": {
                    "llm_only": 0.8,
                    "naive": 0.05,
                    "bm25": 0.1,
                    "local": 0.025,
                    "global": 0.025,
                    "vector": 0.05,
                },
                "one_hop": {
                    "llm_only": 0.0,
                    "naive": 0.35,
                    "bm25": 0.3,
                    "local": 0.2,
                    "global": 0.15,
                    "vector": 0.35,
                },
                "multi_hop": {
                    "llm_only": 0.0,
                    "naive": 0.15,
                    "bm25": 0.15,
                    "local": 0.35,
                    "global": 0.35,
                    "vector": 0.15,
                },
            }

        prior_weights = prior_matrix.get(complexity, prior_matrix.get("one_hop", {}))

        # rho(alpha) = sigmoid(kappa * (alpha - alpha_0))
        kappa = self.config.weight_adjustment_factor
        alpha_0 = 0.5
        rho = self._sigmoid(kappa * (confidence - alpha_0))

        adjusted: Dict[str, float] = {}
        uniform_w = 1.0 / len(sources) if sources else 0.0

        for source in sources:
            canonical = {"dense": "vector", "graph": "local"}.get(source, source)
            beta_rc = prior_weights.get(canonical, uniform_w)
            weight = (1.0 - rho) * uniform_w + rho * beta_rc
            adjusted[source] = max(0.0, weight)

        total = sum(adjusted.values())
        if total > 0:
            adjusted = {k: v / total for k, v in adjusted.items()}

        logger.debug(
            f"CA-RRF 权重 [复杂度={complexity}, 置信度={confidence:.3f}, rho={rho:.3f}]: {adjusted}"
        )
        return adjusted

    # ========= CA-RRF 计算 =========

    def _compute_rrf_scores(
        self,
        results_by_source: Dict[str, List[RetrievalResult]],
        source_weights: Dict[str, float],
        query_complexity: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievalResult]:
        """
        计算 CA-RRF 分数：
        CA-RRF(d) = sum_r w_r(c,alpha) / (k_r(c) + rank_r(d))
        """
        complexity = (
            query_complexity.get("complexity", "one_hop")
            if query_complexity
            else "one_hop"
        )

        # 动态 k_r(c)：优先使用配置，否则使用论文默认值
        if self.config.dynamic_k_values:
            k_values = self.config.dynamic_k_values
        else:
            k_values = {
                "zero_hop": {
                    "llm_only": 80,
                    "naive": 80,
                    "bm25": 80,
                    "local": 80,
                    "global": 80,
                    "vector": 80,
                },
                "one_hop": {
                    "llm_only": 60,
                    "naive": 60,
                    "bm25": 60,
                    "local": 60,
                    "global": 60,
                    "vector": 60,
                },
                "multi_hop": {
                    "llm_only": 40,
                    "naive": 40,
                    "bm25": 40,
                    "local": 40,
                    "global": 40,
                    "vector": 40,
                },
            }

        k_by_source = k_values.get(complexity, k_values.get("one_hop", {}))

        # 收集所有独特结果
        all_results: Dict[str, RetrievalResult] = {}
        for results in results_by_source.values():
            for r in results:
                if r.id not in all_results:
                    all_results[r.id] = r

        # 逐结果计算 CA-RRF 分数
        for result_id, result in all_results.items():
            score = 0.0

            for source, results in results_by_source.items():
                canonical = {"dense": "vector", "graph": "local"}.get(source, source)
                k_r = k_by_source.get(canonical, self.config.k)
                w_r = source_weights.get(source, 1.0)

                # 查找该结果在当前源中的 rank
                rank_in_source: Optional[int] = None
                for i, r in enumerate(results):
                    if r.id == result_id:
                        rank_in_source = i + 1
                        break

                if rank_in_source is not None:
                    score += w_r / (k_r + rank_in_source)

            result.metadata["ca_rrf_score"] = score
            result.metadata["rrf_score"] = score  # 向后兼容
            result.metadata["fusion_score"] = score

        sorted_results = sorted(
            all_results.values(),
            key=lambda r: r.metadata.get("ca_rrf_score", 0.0),
            reverse=True,
        )

        for i, r in enumerate(sorted_results):
            r.metadata["fusion_rank"] = i + 1

        logger.debug(f"CA-RRF 计算完成，排序 {len(sorted_results)} 个结果")
        return sorted_results

    # ========= 简单多样性过滤 =========

    def _apply_diversity_filter(
        self, fused_results: List[RetrievalResult]
    ) -> List[RetrievalResult]:
        """
        简单的源多样性过滤：限制每个源的结果数量，避免单源垄断。
        """
        if len(fused_results) <= 5:
            return fused_results

        filtered: List[RetrievalResult] = []
        source_counts: Dict[str, int] = defaultdict(int)

        unique_sources = {r.source for r in fused_results}
        max_per_source = max(2, len(fused_results) // max(1, len(unique_sources)))

        for r in fused_results:
            cnt = source_counts[r.source]
            if cnt < max_per_source or len(filtered) < self.config.max_results // 2:
                filtered.append(r)
                source_counts[r.source] += 1
            if len(filtered) >= self.config.max_results:
                break

        logger.debug(
            f"多样性过滤: {len(fused_results)} -> {len(filtered)}, 分布: {dict(source_counts)}"
        )
        return filtered

    # ========= MMR 多样性 =========

    async def _apply_mmr_diversity(
        self,
        ranked_results: List[RetrievalResult],
        lambda_param: float = 0.5,
        max_results: Optional[int] = None,
    ) -> List[RetrievalResult]:
        """
        应用最大边际相关性 (MMR) 多样性约束（异步版本，使用语义相似度）：
        argmax_{d not in L} CA-RRF(d) - lambda * max_{d' in L} Sim(d,d')
        
        对于大规模结果集，使用批量相似度矩阵计算优化性能。
        """
        if not ranked_results:
            return []

        if max_results is None:
            max_results = self.config.max_results

        # 对于大规模结果集，使用批量优化
        if len(ranked_results) > 10:
            return await self._apply_mmr_diversity_batch(
                ranked_results, lambda_param, max_results
            )

        return await self._apply_mmr_diversity_unified(
            ranked_results, self.async_strategy, lambda_param, max_results
        )
    
    async def _apply_mmr_diversity_batch(
        self,
        ranked_results: List[RetrievalResult],
        lambda_param: float = 0.5,
        max_results: Optional[int] = None,
    ) -> List[RetrievalResult]:
        """
        批量优化的MMR多样性约束（适用于大规模结果集）
        
        预先计算相似度矩阵，避免重复计算，显著提升性能。
        """
        import numpy as np
        
        if not ranked_results:
            return []

        if max_results is None:
            max_results = self.config.max_results

        n = len(ranked_results)
        
        # 预先计算所有文本的规范化版本
        normalized_texts = [
            self._normalize_content_for_comparison(r.content)
            for r in ranked_results
        ]
        
        # 批量计算相似度矩阵
        logger.debug(f"批量计算 {n}x{n} 相似度矩阵...")
        similarity_matrix = await self.similarity_calculator.compute_similarity_matrix(
            normalized_texts
        )
        
        # 获取CA-RRF分数
        ca_rrf_scores = np.array([
            r.metadata.get("ca_rrf_score", 0.0) for r in ranked_results
        ])
        
        # MMR选择
        selected_indices: List[int] = [0]  # 先选第一个（CA-RRF最高）
        remaining_indices = set(range(1, n))
        
        sim_threshold = getattr(
            self.config, "mmr_similarity_threshold", self.config.diversity_threshold
        )
        
        while len(selected_indices) < max_results and remaining_indices:
            best_idx = -1
            best_mmr_score = float('-inf')
            best_max_sim = 0.0
            
            for idx in remaining_indices:
                # 计算与已选结果的最大相似度
                max_sim = max(
                    similarity_matrix[idx, sel_idx]
                    for sel_idx in selected_indices
                )
                
                # MMR分数
                mmr_score = ca_rrf_scores[idx] - lambda_param * max_sim
                
                if mmr_score > best_mmr_score:
                    best_mmr_score = mmr_score
                    best_idx = idx
                    best_max_sim = max_sim
            
            # 检查停止条件
            if best_idx == -1 or best_mmr_score < 0.01 or best_max_sim >= sim_threshold:
                break
            
            selected_indices.append(best_idx)
            remaining_indices.remove(best_idx)
        
        selected = [ranked_results[i] for i in selected_indices]
        
        logger.debug(
            f"MMR批量选择: 从 {n} 个结果中选择了 {len(selected)} 个"
        )
        return selected
    
    def _apply_mmr_diversity_simple(
        self,
        ranked_results: List[RetrievalResult],
        lambda_param: float = 0.5,
        max_results: Optional[int] = None,
    ) -> List[RetrievalResult]:
        """
        应用最大边际相关性 (MMR) 多样性约束（同步版本，使用Jaccard相似度）
        """
        if not ranked_results:
            return []

        if max_results is None:
            max_results = self.config.max_results

        # 同步策略需要在异步上下文中运行
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果已在异步上下文中，直接使用同步计算
                return self._apply_mmr_diversity_sync(
                    ranked_results, lambda_param, max_results
                )
            return loop.run_until_complete(
                self._apply_mmr_diversity_unified(
                    ranked_results, self.sync_strategy, lambda_param, max_results
                )
            )
        except RuntimeError:
            return self._apply_mmr_diversity_sync(
                ranked_results, lambda_param, max_results
            )
    
    def _apply_mmr_diversity_sync(
        self,
        ranked_results: List[RetrievalResult],
        lambda_param: float = 0.5,
        max_results: Optional[int] = None,
    ) -> List[RetrievalResult]:
        """纯同步MMR多样性（使用Jaccard相似度，不依赖asyncio）"""
        if not ranked_results:
            return []

        if max_results is None:
            max_results = self.config.max_results

        selected: List[RetrievalResult] = []
        candidates = ranked_results.copy()

        first = candidates.pop(0)
        selected.append(first)

        sim_threshold = getattr(
            self.config, "mmr_similarity_threshold", self.config.diversity_threshold
        )

        while len(selected) < max_results and candidates:
            mmr_scores: List[Any] = []

            for cand in candidates:
                ca_rrf = cand.metadata.get("ca_rrf_score", 0.0)
                max_sim = 0.0
                
                for s in selected:
                    sim = self._compute_similarity_jaccard(
                        self._normalize_content_for_comparison(cand.content),
                        self._normalize_content_for_comparison(s.content),
                    )
                    if sim > max_sim:
                        max_sim = sim

                mmr_score = ca_rrf - lambda_param * max_sim
                mmr_scores.append((cand, mmr_score, max_sim))

            if not mmr_scores:
                break

            mmr_scores.sort(key=lambda x: x[1], reverse=True)
            best_cand, best_score, best_sim = mmr_scores[0]

            if best_score < 0.01 or best_sim >= sim_threshold:
                break

            selected.append(best_cand)
            candidates.remove(best_cand)

        return selected
    
    async def _apply_mmr_diversity_unified(
        self,
        ranked_results: List[RetrievalResult],
        strategy: SimilarityStrategy,
        lambda_param: float = 0.5,
        max_results: Optional[int] = None,
    ) -> List[RetrievalResult]:
        """
        统一的MMR多样性方法（使用策略模式）
        
        Args:
            ranked_results: 排序后的结果列表
            strategy: 相似度计算策略
            lambda_param: MMR lambda参数
            max_results: 最大结果数
            
        Returns:
            应用MMR后的结果列表
        """
        if not ranked_results:
            return []

        if max_results is None:
            max_results = self.config.max_results

        selected: List[RetrievalResult] = []
        candidates = ranked_results.copy()

        # 先选 CA-RRF 分数最高的
        first = candidates.pop(0)
        selected.append(first)

        sim_threshold = getattr(
            self.config, "mmr_similarity_threshold", self.config.diversity_threshold
        )

        while len(selected) < max_results and candidates:
            mmr_scores: List[Any] = []

            for cand in candidates:
                ca_rrf = cand.metadata.get("ca_rrf_score", 0.0)
                max_sim = 0.0
                
                for s in selected:
                    # 使用策略计算相似度
                    try:
                        sim = await strategy.compute_similarity(
                            self._normalize_content_for_comparison(cand.content),
                            self._normalize_content_for_comparison(s.content),
                        )
                    except Exception as e:
                        logger.warning(f"MMR相似度计算失败: {e}，使用默认值0.0")
                        sim = 0.0
                    if sim > max_sim:
                        max_sim = sim

                mmr_score = ca_rrf - lambda_param * max_sim
                mmr_scores.append((cand, mmr_score, max_sim))

            if not mmr_scores:
                break

            # 选取 MMR 得分最高的候选
            mmr_scores.sort(key=lambda x: x[1], reverse=True)
            best_cand, best_score, best_sim = mmr_scores[0]

            # 若得分过低或与已有结果高度相似，则停止扩展
            if best_score < 0.01 or best_sim >= sim_threshold:
                break

            selected.append(best_cand)
            candidates.remove(best_cand)

        logger.debug(
            f"MMR 选择: 从 {len(ranked_results)} 个结果中选择了 {len(selected)} 个, "
            f"策略: {strategy.get_strategy_name()}"
        )
        return selected

    # ========= 文本相似度 =========

    def _compute_similarity_jaccard(self, text1: str, text2: str) -> float:
        """
        Jaccard相似度（同步版本，用于向后兼容）
        """
        tokens1 = set(text1.split()) if text1 else set()
        tokens2 = set(text2.split()) if text2 else set()
        if not tokens1 or not tokens2:
            return 0.0

        inter = tokens1 & tokens2
        union = tokens1 | tokens2
        jaccard = len(inter) / len(union) if union else 0.0

        len_ratio = (
            min(len(text1), len(text2)) / max(len(text1), len(text2))
            if text1 and text2
            else 0.0
        )

        return 0.7 * jaccard + 0.3 * len_ratio

    # ========= 统计 =========

    def get_fusion_stats(self) -> Dict[str, Any]:
        """获取融合统计信息（用于实验分析和调试）"""
        stats = dict(self.fusion_stats)
        # 添加相似度计算器统计
        stats["similarity_stats"] = self.similarity_calculator.get_stats()
        return stats
    
    def get_similarity_stats(self) -> Dict[str, Any]:
        """获取相似度计算统计信息"""
        return self.similarity_calculator.get_stats()


def create_fusion_engine(
    k: float = 60.0,
    max_results: int = 20,
    confidence_aware: bool = True,
    embedding_func: Optional[Callable] = None,
    similarity_method: SimilarityMethod = SimilarityMethod.TFIDF,
    **kwargs: Any,
) -> ConfidenceAwareFusion:
    """
    创建融合引擎。

    Args:
        k: 基础RRF参数（如提供 dynamic_k_values 将优先使用矩阵）
        max_results: 最大返回结果数
        confidence_aware: 是否启用置信度感知
        embedding_func: 嵌入函数（用于语义相似度计算）
        similarity_method: 相似度计算方法（EMBEDDING/TFIDF/JACCARD）
        **kwargs: 额外配置（如 dynamic_k_values / prior_weights / mmr_*）
    
    Returns:
        ConfidenceAwareFusion 实例
    """
    config = FusionConfig(
        k=k,
        max_results=max_results,
        confidence_aware=confidence_aware,
        embedding_func=embedding_func,
        similarity_method=similarity_method,
        **kwargs,
    )
    return ConfidenceAwareFusion(config)
