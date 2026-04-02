"""
评估模块

提供RAG系统评估的指标和工具
"""

from .metrics import (
    calculate_bleu,
    calculate_rouge,
    calculate_f1,
    calculate_ndcg,
    calculate_mrr,
    calculate_recall,
    RAGMetrics
)

from .timing import (
    measure_latency,
    LatencyTracker
)

__all__ = [
    # 指标函数
    'calculate_bleu',
    'calculate_rouge',
    'calculate_f1',
    'calculate_ndcg',
    'calculate_mrr',
    'calculate_recall',
    'RAGMetrics',
    
    # 延迟测量
    'measure_latency',
    'LatencyTracker',
]

