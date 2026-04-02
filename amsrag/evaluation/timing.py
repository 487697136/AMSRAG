"""
延迟测量模块

提供延迟测量和性能分析工具
"""

import time
import asyncio
from functools import wraps
from typing import Dict, Any, Optional, Callable
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class LatencyTracker:
    """延迟追踪器"""
    
    def __init__(self):
        self.timings = defaultdict(list)
        self.current_session = {}
    
    def start(self, operation: str):
        """开始计时"""
        self.current_session[operation] = time.time()
    
    def end(self, operation: str) -> float:
        """结束计时并返回耗时"""
        if operation not in self.current_session:
            logger.warning(f"Operation '{operation}' was not started")
            return 0.0
        
        start_time = self.current_session.pop(operation)
        elapsed = time.time() - start_time
        self.timings[operation].append(elapsed)
        
        return elapsed
    
    def get_stats(self, operation: Optional[str] = None) -> Dict[str, Any]:
        """获取统计信息"""
        if operation:
            if operation not in self.timings:
                return {}
            
            times = self.timings[operation]
            return {
                'count': len(times),
                'total': sum(times),
                'mean': sum(times) / len(times) if times else 0,
                'min': min(times) if times else 0,
                'max': max(times) if times else 0
            }
        else:
            # 返回所有操作的统计
            stats = {}
            for op_name, times in self.timings.items():
                stats[op_name] = {
                    'count': len(times),
                    'total': sum(times),
                    'mean': sum(times) / len(times) if times else 0,
                    'min': min(times) if times else 0,
                    'max': max(times) if times else 0
                }
            return stats
    
    def reset(self):
        """重置所有计时"""
        self.timings.clear()
        self.current_session.clear()
    
    def get_breakdown(self) -> Dict[str, float]:
        """获取各操作的总耗时占比"""
        total_time = sum(sum(times) for times in self.timings.values())
        
        if total_time == 0:
            return {}
        
        breakdown = {}
        for operation, times in self.timings.items():
            op_total = sum(times)
            breakdown[operation] = {
                'total_time': op_total,
                'percentage': (op_total / total_time) * 100,
                'avg_time': op_total / len(times) if times else 0
            }
        
        return breakdown


def measure_latency(operation_name: Optional[str] = None):
    """
    延迟测量装饰器
    
    Args:
        operation_name: 操作名称，如果为None则使用函数名
        
    Example:
        @measure_latency("retrieval")
        async def retrieve_documents(query):
            # ...
            pass
    """
    def decorator(func: Callable):
        op_name = operation_name or func.__name__
        
        if asyncio.iscoroutinefunction(func):
            # 异步函数
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)
                    elapsed = time.time() - start_time
                    logger.debug(f"{op_name} took {elapsed:.3f}s")
                    
                    # 如果返回值是字典，添加耗时信息
                    if isinstance(result, dict) and '_timing' not in result:
                        result['_timing'] = {op_name: elapsed}
                    
                    return result
                except Exception as e:
                    elapsed = time.time() - start_time
                    logger.error(f"{op_name} failed after {elapsed:.3f}s: {e}")
                    raise
            
            return async_wrapper
        else:
            # 同步函数
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    elapsed = time.time() - start_time
                    logger.debug(f"{op_name} took {elapsed:.3f}s")
                    
                    # 如果返回值是字典，添加耗时信息
                    if isinstance(result, dict) and '_timing' not in result:
                        result['_timing'] = {op_name: elapsed}
                    
                    return result
                except Exception as e:
                    elapsed = time.time() - start_time
                    logger.error(f"{op_name} failed after {elapsed:.3f}s: {e}")
                    raise
            
            return sync_wrapper
    
    return decorator


class TimingContext:
    """计时上下文管理器"""
    
    def __init__(self, operation_name: str, tracker: Optional[LatencyTracker] = None):
        self.operation_name = operation_name
        self.tracker = tracker
        self.start_time = None
        self.elapsed = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.elapsed = time.time() - self.start_time
        
        if self.tracker:
            self.tracker.timings[self.operation_name].append(self.elapsed)
        
        logger.debug(f"{self.operation_name} took {self.elapsed:.3f}s")
    
    async def __aenter__(self):
        self.start_time = time.time()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.elapsed = time.time() - self.start_time
        
        if self.tracker:
            self.tracker.timings[self.operation_name].append(self.elapsed)
        
        logger.debug(f"{self.operation_name} took {self.elapsed:.3f}s")

