import os
import re
import pickle
from dataclasses import dataclass
from typing import Dict, List, Union
from collections import Counter
import math

# 尝试导入NLTK（用于高级分词）
try:
    import nltk
    from nltk.tokenize import word_tokenize
    from nltk.stem import PorterStemmer
    from nltk.corpus import stopwords
    NLTK_AVAILABLE = True
except ImportError:
    NLTK_AVAILABLE = False

# 尝试导入jieba（用于中文分词）
try:
    import jieba
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False

from ...base import BaseKVStorage, StorageNameSpace
from ..._utils import logger


@dataclass
class BM25Storage(StorageNameSpace):
    """
    BM25存储类，用于BM25检索
    
    改进：
    - 支持NLTK高级分词（词干提取、停用词过滤）
    - 支持jieba中文分词
    - 自动语言检测
    - 回退到简单分词（如果NLTK/jieba不可用）
    """
    k1: float = 1.5
    b: float = 0.75
    language: str = "auto"  # "auto", "en", "zh", "simple"
    
    def __post_init__(self):
        self._file_name = os.path.join(
            self.global_config["working_dir"], f"bm25_{self.namespace}.pkl"
        )
        self._index = {}  # 倒排索引: {token: {doc_id: freq}}
        self._doc_lengths = {}  # 文档长度: {doc_id: length}
        self._avg_doc_length = 0  # 平均文档长度
        self._documents = {}  # 文档内容: {doc_id: content}
        self._initialized = False
        
        # 初始化分词器
        self._init_tokenizer()
        
        if os.path.exists(self._file_name):
            try:
                with open(self._file_name, "rb") as f:
                    data = pickle.load(f)
                    self._index = data.get("index", {})
                    self._doc_lengths = data.get("doc_lengths", {})
                    self._avg_doc_length = data.get("avg_doc_length", 0)
                    self._documents = data.get("documents", {})
                    self._initialized = True
                logger.info(f"Loaded BM25 index for {self.namespace} with {len(self._documents)} documents")
            except Exception as e:
                logger.error(f"Failed to load BM25 index: {e}")
                self._initialized = False
    
    def _init_tokenizer(self):
        """初始化分词器"""
        self.tokenizer_type = "simple"  # 默认简单分词
        
        if self.language == "auto" or self.language == "en":
            # 尝试使用NLTK
            if NLTK_AVAILABLE:
                try:
                    # 尝试加载NLTK数据
                    self.stemmer = PorterStemmer()
                    self.stop_words = set(stopwords.words('english'))
                    self.tokenizer_type = "nltk"
                    logger.info("BM25: Using NLTK tokenizer with stemming")
                except LookupError:
                    logger.warning(
                        "NLTK data not found. Run: "
                        "python -m nltk.downloader punkt stopwords"
                    )
                    self.stemmer = None
                    self.stop_words = set()
            else:
                logger.info("NLTK not available, using simple tokenizer")
                self.stemmer = None
                self.stop_words = set()
        
        if self.language == "zh":
            # 中文分词
            if JIEBA_AVAILABLE:
                self.tokenizer_type = "jieba"
                logger.info("BM25: Using jieba tokenizer for Chinese")
            else:
                logger.warning("jieba not available for Chinese, using simple tokenizer")
    
    def _detect_language(self, text: str) -> str:
        """
        简单的语言检测
        
        Args:
            text: 文本
            
        Returns:
            "zh" (中文) 或 "en" (英文)
        """
        # 统计中文字符
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        total_chars = len(text)
        
        if total_chars == 0:
            return "en"
        
        # 如果中文字符超过20%，认为是中文
        if chinese_chars / total_chars > 0.2:
            return "zh"
        else:
            return "en"
    
    def _tokenize(self, text: str) -> List[str]:
        """
        改进的分词器
        
        支持：
        - NLTK分词（英文）：词干提取 + 停用词过滤
        - jieba分词（中文）
        - 简单分词（回退）
        
        Args:
            text: 待分词文本
            
        Returns:
            词元列表
        """
        if not text or not isinstance(text, str):
            return []
        
        # 自动语言检测
        if self.language == "auto":
            detected_lang = self._detect_language(text)
        else:
            detected_lang = self.language
        
        # 中文分词
        if detected_lang == "zh" and self.tokenizer_type == "jieba":
            tokens = list(jieba.cut(text.lower()))
            # 过滤空白和标点
            tokens = [t for t in tokens if t.strip() and len(t) > 1]
            return tokens
        
        # 英文NLTK分词
        if self.tokenizer_type == "nltk" and self.stemmer:
            try:
                # 分词
                tokens = word_tokenize(text.lower())
                # 词干提取 + 停用词过滤
                tokens = [
                    self.stemmer.stem(t) 
                    for t in tokens 
                    if t.isalnum() and t not in self.stop_words and len(t) > 2
                ]
                return tokens
            except Exception as e:
                logger.warning(f"NLTK tokenization failed: {e}, using simple tokenizer")
        
        # 简单分词（回退）
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)  # 移除标点
        tokens = text.split()
        tokens = [t for t in tokens if len(t) > 2]  # 过滤短词
        return tokens
    
    def _calculate_idf(self, token: str) -> float:
        """计算逆文档频率 (IDF)"""
        if token not in self._index:
            return 0.0
        
        # 包含该词的文档数
        doc_count = len(self._index[token])
        # 总文档数
        total_docs = len(self._documents)
        
        # IDF计算公式
        return math.log((total_docs - doc_count + 0.5) / (doc_count + 0.5) + 1)
    
    async def index_document(self, doc_id: str, content: str):
        """索引单个文档"""
        tokens = self._tokenize(content)
        doc_length = len(tokens)
        term_freqs = Counter(tokens)
        
        # 更新文档长度
        self._doc_lengths[doc_id] = doc_length
        
        # 更新倒排索引
        for token, freq in term_freqs.items():
            if token not in self._index:
                self._index[token] = {}
            self._index[token][doc_id] = freq
        
        # 更新文档内容
        self._documents[doc_id] = content
        
        # 更新平均文档长度
        self._avg_doc_length = sum(self._doc_lengths.values()) / len(self._doc_lengths) if self._doc_lengths else 0
        
        self._initialized = True
    
    async def index_documents(self, documents: Dict[str, str]):
        """批量索引文档"""
        for doc_id, content in documents.items():
            await self.index_document(doc_id, content)
    
    async def search(self, query: str, top_k: int = 10) -> List[Dict[str, Union[str, float]]]:
        """BM25搜索"""
        if not self._initialized:
            logger.warning("BM25 index not initialized")
            return []
        
        query_tokens = self._tokenize(query)
        scores = {}
        
        for token in query_tokens:
            if token not in self._index:
                continue
            
            idf = self._calculate_idf(token)
            
            for doc_id, term_freq in self._index[token].items():
                if doc_id not in scores:
                    scores[doc_id] = 0
                
                doc_length = self._doc_lengths[doc_id]
                
                # BM25评分公式
                numerator = term_freq * (self.k1 + 1)
                denominator = term_freq + self.k1 * (1 - self.b + self.b * doc_length / self._avg_doc_length)
                scores[doc_id] += idf * numerator / denominator
        
        # 按分数排序
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        # 返回结果
        results = []
        for doc_id, score in sorted_scores[:top_k]:
            results.append({
                "id": doc_id,
                "content": self._documents[doc_id],
                "score": score
            })
        
        return results
    
    async def index_start_callback(self):
        """开始索引回调"""
        pass
    
    async def index_done_callback(self):
        """索引完成回调"""
        with open(self._file_name, "wb") as f:
            data = {
                "index": self._index,
                "doc_lengths": self._doc_lengths,
                "avg_doc_length": self._avg_doc_length,
                "documents": self._documents
            }
            pickle.dump(data, f)
    
    async def query_done_callback(self):
        """查询完成回调"""
        pass 