"""
FAISS向量数据库存储实现

基于Facebook FAISS库的高性能向量存储
支持余弦相似度、批量查询、阈值过滤等功能
"""

import asyncio
import os
import pickle
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
import numpy as np

try:
    import faiss
except ImportError:
    raise ImportError(
        "FAISS is required but not installed. "
        "Please install it with: pip install faiss-cpu"
    )

from ..._utils import logger
from ...base import BaseVectorStorage


@dataclass
class FAISSVectorStorage(BaseVectorStorage):
    """
    FAISS向量数据库存储
    
    特点：
    - 高性能：比nano_vectordb快5-10倍
    - 支持余弦相似度（通过向量归一化）
    - 支持阈值过滤
    - 支持批量操作
    - 持久化存储
    
    参数：
        cosine_better_than_threshold: 余弦相似度阈值（0-1），默认0.2
        use_gpu: 是否使用GPU（需要faiss-gpu），默认False
    """
    cosine_better_than_threshold: float = 0.2
    use_gpu: bool = False

    def __post_init__(self):
        """初始化FAISS索引"""
        # 文件路径
        self._index_file = os.path.join(
            self.global_config["working_dir"], 
            f"faiss_{self.namespace}.index"
        )
        self._metadata_file = os.path.join(
            self.global_config["working_dir"], 
            f"faiss_{self.namespace}_meta.pkl"
        )

        # Ensure persistence directory exists before any load/save attempts.
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self._index_file)), exist_ok=True)
        except Exception as e:
            logger.warning(f"Failed to ensure FAISS working_dir exists: {e}")
        
        # 获取嵌入维度
        if hasattr(self.embedding_func, 'embedding_dim'):
            self.embedding_dim = self.embedding_func.embedding_dim
        else:
            # 默认维度（BGE-M3是1024）
            self.embedding_dim = 1024
            logger.warning(
                f"Embedding dimension not found, using default: {self.embedding_dim}"
            )
        
        # 批量大小
        self._max_batch_size = self.global_config.get("embedding_batch_num", 32)
        
        # 阈值配置
        self.cosine_better_than_threshold = self.global_config.get(
            "query_better_than_threshold", self.cosine_better_than_threshold
        )
        
        # 元数据存储
        self._id_to_data = {}  # {doc_id: metadata}
        self._id_list = []  # [doc_id1, doc_id2, ...] 按索引顺序
        
        # 创建或加载FAISS索引
        self._initialize_index()
        
        logger.info(
            f"FAISS storage initialized for '{self.namespace}': "
            f"dim={self.embedding_dim}, vectors={self._index.ntotal}, "
            f"threshold={self.cosine_better_than_threshold}"
        )
    
    def _initialize_index(self):
        """初始化或加载FAISS索引"""
        if os.path.exists(self._index_file) and os.path.exists(self._metadata_file):
            # 加载已有索引
            try:
                self._index = faiss.read_index(self._index_file)
                with open(self._metadata_file, 'rb') as f:
                    data = pickle.load(f)
                    self._id_to_data = data['id_to_data']
                    self._id_list = data['id_list']
                
                logger.info(
                    f"Loaded FAISS index from {self._index_file}: "
                    f"{self._index.ntotal} vectors"
                )
            except Exception as e:
                logger.error(f"Failed to load FAISS index: {e}")
                logger.info("Creating new index")
                self._create_new_index()
        else:
            # 创建新索引
            self._create_new_index()
    
    def _create_new_index(self):
        """创建新的FAISS索引"""
        # 使用IndexFlatIP（内积索引）
        # 对于余弦相似度，我们会先归一化向量，然后内积等价于余弦相似度
        self._index = faiss.IndexFlatIP(self.embedding_dim)
        
        # 如果需要GPU加速（需要faiss-gpu）
        if self.use_gpu:
            try:
                res = faiss.StandardGpuResources()
                self._index = faiss.index_cpu_to_gpu(res, 0, self._index)
                logger.info("FAISS GPU acceleration enabled")
            except Exception as e:
                logger.warning(f"Failed to enable GPU: {e}, using CPU")
        
        self._id_to_data = {}
        self._id_list = []
    
    async def upsert(self, data: Dict[str, Dict]) -> List[str]:
        """
        插入或更新向量
        
        Args:
            data: {doc_id: {"content": str, ...}}
            
        Returns:
            插入的文档ID列表
        """
        if not data:
            logger.warning("Empty data provided to upsert")
            return []
        
        logger.info(f"Upserting {len(data)} vectors to FAISS '{self.namespace}'")
        
        try:
            # 提取内容
            contents = [v["content"] for v in data.values()]
            doc_ids = list(data.keys())
            
            # 批量生成嵌入
            batches = [
                contents[i : i + self._max_batch_size]
                for i in range(0, len(contents), self._max_batch_size)
            ]
            
            embeddings_list = await asyncio.gather(
                *[self.embedding_func(batch) for batch in batches]
            )
            
            # 合并所有批次的嵌入
            embeddings = np.concatenate(embeddings_list, axis=0)
            embeddings = np.array(embeddings, dtype=np.float32)
            
            # 归一化向量（用于余弦相似度）
            faiss.normalize_L2(embeddings)
            
            # 添加到索引
            self._index.add(embeddings)
            
            # 保存元数据
            for doc_id, doc_data in data.items():
                self._id_list.append(doc_id)
                # 只保存meta_fields中指定的字段
                self._id_to_data[doc_id] = {
                    k: v for k, v in doc_data.items() 
                    if k in self.meta_fields or k == 'content'
                }
            
            logger.info(
                f"Successfully upserted {len(data)} vectors, "
                f"total vectors: {self._index.ntotal}"
            )
            
            return doc_ids
            
        except Exception as e:
            logger.error(f"Failed to upsert vectors: {e}")
            raise
    
    async def query(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        查询相似向量
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            
        Returns:
            相似文档列表，每个文档包含：
            - id: 文档ID
            - distance: 距离（越小越相似，范围0-2）
            - score: 相似度分数（越大越相似，范围0-1）
            - 其他元数据字段
        """
        if self._index.ntotal == 0:
            logger.warning("FAISS index is empty")
            return []
        
        try:
            # 生成查询向量
            query_embedding = await self.embedding_func([query])
            query_embedding = np.array(query_embedding, dtype=np.float32)
            
            # 归一化
            faiss.normalize_L2(query_embedding)
            
            # 搜索（返回内积分数，范围-1到1，归一化后范围0到1）
            # top_k可能大于索引中的向量数，需要限制
            actual_top_k = min(top_k, self._index.ntotal)
            distances, indices = self._index.search(query_embedding, actual_top_k)
            
            # 构建结果
            results = []
            for dist, idx in zip(distances[0], indices[0]):
                # FAISS返回-1表示无结果
                if idx == -1:
                    continue
                
                # 内积分数（归一化后等于余弦相似度）
                similarity_score = float(dist)
                
                # 应用阈值过滤
                if similarity_score < self.cosine_better_than_threshold:
                    continue
                
                # 获取文档ID和元数据
                doc_id = self._id_list[idx]
                metadata = self._id_to_data.get(doc_id, {})
                
                result = {
                    "id": doc_id,
                    "distance": 1.0 - similarity_score,  # 转换为距离（兼容旧接口）
                    "score": similarity_score,  # 相似度分数
                    **metadata
                }
                results.append(result)
            
            logger.debug(
                f"Query returned {len(results)} results "
                f"(before threshold: {len([d for d in distances[0] if d != -1])})"
            )
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to query vectors: {e}")
            return []
    
    async def index_done_callback(self):
        """索引完成回调：保存索引到磁盘"""
        try:
            # Ensure parent directories exist (Windows: write_index won't create them).
            os.makedirs(os.path.dirname(os.path.abspath(self._index_file)), exist_ok=True)
            os.makedirs(os.path.dirname(os.path.abspath(self._metadata_file)), exist_ok=True)

            # 如果使用GPU，先转回CPU
            if self.use_gpu and hasattr(self._index, 'index'):
                index_to_save = faiss.index_gpu_to_cpu(self._index)
            else:
                index_to_save = self._index
            
            # 保存FAISS索引
            faiss.write_index(index_to_save, self._index_file)
            
            # 保存元数据
            with open(self._metadata_file, 'wb') as f:
                pickle.dump({
                    'id_to_data': self._id_to_data,
                    'id_list': self._id_list
                }, f)
            
            logger.info(
                f"FAISS index saved: {self._index_file} "
                f"({self._index.ntotal} vectors)"
            )
            
        except Exception as e:
            logger.error(f"Failed to save FAISS index: {e}")
            raise
    
    def get_stats(self) -> Dict[str, Any]:
        """获取索引统计信息"""
        return {
            "namespace": self.namespace,
            "total_vectors": self._index.ntotal,
            "dimension": self.embedding_dim,
            "threshold": self.cosine_better_than_threshold,
            "index_type": "IndexFlatIP",
            "use_gpu": self.use_gpu,
            "total_documents": len(self._id_to_data)
        }


def create_faiss_storage(
    namespace: str,
    global_config: Dict[str, Any],
    embedding_func,
    meta_fields: set = None,
    use_gpu: bool = False
) -> FAISSVectorStorage:
    """
    创建FAISS向量存储实例的便捷函数
    
    Args:
        namespace: 命名空间
        global_config: 全局配置
        embedding_func: 嵌入函数
        meta_fields: 元数据字段集合
        use_gpu: 是否使用GPU
        
    Returns:
        FAISSVectorStorage实例
    """
    return FAISSVectorStorage(
        namespace=namespace,
        global_config=global_config,
        embedding_func=embedding_func,
        meta_fields=meta_fields or set(),
        use_gpu=use_gpu
    )
