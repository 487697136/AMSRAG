"""
评估指标模块

使用标准NLP库实现RAG系统评估指标
- NLTK: BLEU标准实现
- rouge-score: ROUGE标准实现
- jieba: 中文分词
- sacrebleu: 更准确的BLEU
- bert-score: 语义相似度
"""

import numpy as np
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# 导入标准评估库
try:
    import nltk
    from nltk.translate.bleu_score import sentence_bleu, SmoothingFunction
    from nltk.tokenize import word_tokenize
    NLTK_AVAILABLE = True
    
    # 下载必要的NLTK数据（如果未下载）
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        logger.info("下载NLTK punkt tokenizer...")
        nltk.download('punkt', quiet=True)
        nltk.download('punkt_tab', quiet=True)
    
except ImportError:
    NLTK_AVAILABLE = False
    logger.error("❌ NLTK未安装！请运行: pip install nltk")

try:
    from rouge_score import rouge_scorer
    from rouge_score import tokenizers as rouge_tokenizers
    ROUGE_AVAILABLE = True
    
    # 创建中文tokenizer
    class ChineseTokenizer(rouge_tokenizers.Tokenizer):
        """中文分词器（用于ROUGE）"""
        def tokenize(self, text):
            if JIEBA_AVAILABLE:
                return list(jieba.cut(text))
            else:
                # 回退到字符级
                import re
                return list(re.findall(r'[\u4e00-\u9fff]', text))
    
except ImportError:
    ROUGE_AVAILABLE = False
    logger.error("❌ rouge-score未安装！请运行: pip install rouge-score")

try:
    import jieba
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False
    logger.error("❌ jieba未安装！请运行: pip install jieba")

try:
    import sacrebleu
    SACREBLEU_AVAILABLE = True
except ImportError:
    SACREBLEU_AVAILABLE = False
    logger.warning("⚠️ sacrebleu未安装（可选）。推荐安装: pip install sacrebleu")

try:
    from bert_score import score as bert_score_fn
    BERTSCORE_AVAILABLE = True
except ImportError:
    BERTSCORE_AVAILABLE = False
    logger.warning("⚠️ bert-score未安装（可选）。推荐安装: pip install bert-score")


def tokenize_text(text: str, language: str = 'auto') -> List[str]:
    """
    使用标准库进行分词
    
    Args:
        text: 输入文本
        language: 语言 ('zh', 'en', 'auto')
        
    Returns:
        分词后的token列表
    """
    import re
    
    # 自动检测语言
    if language == 'auto':
        has_chinese = bool(re.search(r'[\u4e00-\u9fff]', text))
        language = 'zh' if has_chinese else 'en'
    
    if language == 'zh':
        # 中文：使用jieba分词
        if JIEBA_AVAILABLE:
            return list(jieba.cut(text.lower()))
        else:
            logger.warning("jieba未安装，使用字符级分词（不准确）")
            # 移除标点，按字符分词
            text = re.sub(r'[^\w\s]', '', text.lower())
            return list(re.findall(r'[\u4e00-\u9fff]', text))
    else:
        # 英文：使用NLTK分词
        if NLTK_AVAILABLE:
            return word_tokenize(text.lower())
        else:
            logger.warning("NLTK未安装，使用简单空格分词（不准确）")
            return text.lower().split()


def calculate_bleu(reference: str, hypothesis: str, n_gram: int = 4, use_sacrebleu: bool = False) -> float:
    """
    计算BLEU分数（使用标准库）
    
    Args:
        reference: 参考答案
        hypothesis: 生成的答案
        n_gram: n-gram大小（1-4），默认4表示BLEU-4
        use_sacrebleu: 是否使用sacrebleu（更准确）
        
    Returns:
        BLEU分数 (0-1)
    """
    if not reference or not hypothesis:
        return 0.0
    
    try:
        # 优先使用sacrebleu（更准确，符合WMT标准）
        if use_sacrebleu and SACREBLEU_AVAILABLE:
            bleu = sacrebleu.sentence_bleu(hypothesis, [reference])
            return bleu.score / 100.0  # sacrebleu返回0-100，转换为0-1
        
        # 使用NLTK的BLEU实现
        if NLTK_AVAILABLE:
            reference_tokens = tokenize_text(reference)
            hypothesis_tokens = tokenize_text(hypothesis)
            
            # 设置权重
            if n_gram == 1:
                weights = (1.0, 0, 0, 0)
            elif n_gram == 2:
                weights = (0.5, 0.5, 0, 0)
            elif n_gram == 3:
                weights = (0.33, 0.33, 0.33, 0)
            else:  # n_gram == 4
                weights = (0.25, 0.25, 0.25, 0.25)
            
            # 使用平滑函数避免零分数
            smoothing = SmoothingFunction().method1
            score = sentence_bleu(
                [reference_tokens], 
                hypothesis_tokens,
                weights=weights,
                smoothing_function=smoothing
            )
            return float(score)
        else:
            logger.error("无法计算BLEU：NLTK未安装")
            return 0.0
    
    except Exception as e:
        logger.error(f"BLEU calculation error: {e}")
        return 0.0


def calculate_rouge(reference: str, hypothesis: str, rouge_type: str = 'rougeL') -> float:
    """
    计算ROUGE分数（使用标准库，支持中文）
    
    Args:
        reference: 参考答案
        hypothesis: 生成的答案
        rouge_type: ROUGE类型 ('rouge1', 'rouge2', 'rougeL')
        
    Returns:
        ROUGE F1分数 (0-1)
    """
    if not reference or not hypothesis:
        return 0.0
    
    try:
        if ROUGE_AVAILABLE:
            # 检测是否为中文
            import re
            has_chinese = bool(re.search(r'[\u4e00-\u9fff]', reference + hypothesis))
            
            if has_chinese:
                # 中文：使用自定义tokenizer
                scorer = rouge_scorer.RougeScorer([rouge_type], tokenizer=ChineseTokenizer())
            else:
                # 英文：使用默认tokenizer
                scorer = rouge_scorer.RougeScorer([rouge_type], use_stemmer=True)
            
            scores = scorer.score(reference, hypothesis)
            return float(scores[rouge_type].fmeasure)
        else:
            logger.error("无法计算ROUGE：rouge-score未安装")
            return 0.0
    
    except Exception as e:
        logger.error(f"ROUGE calculation error: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return 0.0


def calculate_f1(reference: str, hypothesis: str) -> float:
    """
    计算Token级别的F1分数（使用标准分词）
    
    Args:
        reference: 参考答案
        hypothesis: 生成的答案
        
    Returns:
        F1分数 (0-1)
    """
    if not reference or not hypothesis:
        return 0.0
    
    try:
        ref_tokens = set(tokenize_text(reference))
        hyp_tokens = set(tokenize_text(hypothesis))
        
        if not hyp_tokens:
            return 0.0
        
        overlap = len(ref_tokens & hyp_tokens)
        if overlap == 0:
            return 0.0
        
        precision = overlap / len(hyp_tokens)
        recall = overlap / len(ref_tokens) if ref_tokens else 0
        f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
        
        return float(f1)
    
    except Exception as e:
        logger.error(f"F1 calculation error: {e}")
        return 0.0


def calculate_bertscore(reference: str, hypothesis: str, lang: str = 'zh', model_type: str = 'bert-base-chinese') -> Dict[str, float]:
    """
    计算BERTScore（语义相似度）
    
    Args:
        reference: 参考答案
        hypothesis: 生成的答案
        lang: 语言代码 ('zh', 'en')
        model_type: BERT模型类型
        
    Returns:
        包含precision, recall, f1的字典
    """
    if not reference or not hypothesis:
        return {'precision': 0.0, 'recall': 0.0, 'f1': 0.0}
    
    try:
        if BERTSCORE_AVAILABLE:
            P, R, F1 = bert_score_fn([hypothesis], [reference], lang=lang, model_type=model_type, verbose=False)
            return {
                'precision': float(P[0]),
                'recall': float(R[0]),
                'f1': float(F1[0])
            }
        else:
            logger.warning("BERTScore未安装，跳过计算")
            return {'precision': 0.0, 'recall': 0.0, 'f1': 0.0}
    
    except Exception as e:
        logger.error(f"BERTScore calculation error: {e}")
        return {'precision': 0.0, 'recall': 0.0, 'f1': 0.0}


def calculate_ndcg(relevance_scores: List[float], k: Optional[int] = None) -> float:
    """
    计算nDCG (Normalized Discounted Cumulative Gain)
    
    Args:
        relevance_scores: 相关性分数列表（按排名顺序）
        k: 截断位置，None表示使用全部
        
    Returns:
        nDCG分数 (0-1)
    """
    if not relevance_scores:
        return 0.0
    
    try:
        if k is not None:
            relevance_scores = relevance_scores[:k]
        
        # 计算DCG
        dcg = relevance_scores[0]
        for i, score in enumerate(relevance_scores[1:], start=2):
            dcg += score / np.log2(i + 1)
        
        # 计算IDCG（理想排序下的DCG）
        ideal_scores = sorted(relevance_scores, reverse=True)
        idcg = ideal_scores[0]
        for i, score in enumerate(ideal_scores[1:], start=2):
            idcg += score / np.log2(i + 1)
        
        # 计算nDCG
        if idcg == 0:
            return 0.0
        
        ndcg = dcg / idcg
        return float(ndcg)
    
    except Exception as e:
        logger.error(f"nDCG calculation error: {e}")
        return 0.0


def calculate_mrr(relevance_binary: List[int]) -> float:
    """
    计算MRR (Mean Reciprocal Rank)
    
    Args:
        relevance_binary: 二元相关性列表（1表示相关，0表示不相关）
        
    Returns:
        MRR分数（倒数排名）
    """
    if not relevance_binary:
        return 0.0
    
    try:
        for i, is_relevant in enumerate(relevance_binary, start=1):
            if is_relevant:
                return 1.0 / i
        return 0.0
    
    except Exception as e:
        logger.error(f"MRR calculation error: {e}")
        return 0.0


def calculate_recall(retrieved_docs: List[str], relevant_docs: List[str], k: Optional[int] = None) -> float:
    """
    计算Recall@k
    
    Args:
        retrieved_docs: 检索到的文档ID列表
        relevant_docs: 相关文档ID列表
        k: 截断位置
        
    Returns:
        Recall分数 (0-1)
    """
    if not relevant_docs:
        return 0.0
    
    try:
        if k is not None:
            retrieved_docs = retrieved_docs[:k]
        
        retrieved_set = set(retrieved_docs)
        relevant_set = set(relevant_docs)
        
        overlap = len(retrieved_set & relevant_set)
        recall = overlap / len(relevant_set)
        
        return float(recall)
    
    except Exception as e:
        logger.error(f"Recall calculation error: {e}")
        return 0.0


class RAGMetrics:
    """RAG评估指标计算器（使用标准库）"""
    
    def __init__(self, use_bertscore: bool = False):
        """
        初始化评估器
        
        Args:
            use_bertscore: 是否计算BERTScore（较慢但更准确）
        """
        self.results = []
        self.use_bertscore = use_bertscore
        
        # 检查必要的库
        if not NLTK_AVAILABLE:
            logger.error("❌ NLTK未安装！BLEU计算将不可用")
        if not ROUGE_AVAILABLE:
            logger.error("❌ rouge-score未安装！ROUGE计算将不可用")
        if not JIEBA_AVAILABLE:
            logger.warning("⚠️ jieba未安装！中文分词将不准确")
    
    def evaluate_single(
        self,
        query: str,
        generated_answer: str,
        reference_answer: Optional[str] = None,
        retrieved_docs: Optional[List[Dict[str, Any]]] = None,
        relevant_docs: Optional[List[str]] = None
    ) -> Dict[str, float]:
        """
        评估单个查询的结果（使用标准库）
        
        Args:
            query: 查询文本
            generated_answer: 生成的答案
            reference_answer: 参考答案（如果有）
            retrieved_docs: 检索到的文档列表
            relevant_docs: 相关文档ID列表（如果有）
            
        Returns:
            评估指标字典
        """
        metrics = {}
        
        # 生成质量指标（需要参考答案）
        if reference_answer:
            # BLEU-4
            metrics['bleu-4'] = calculate_bleu(reference_answer, generated_answer, n_gram=4)
            
            # ROUGE-L
            metrics['rouge-l'] = calculate_rouge(reference_answer, generated_answer, 'rougeL')
            
            # ROUGE-1 和 ROUGE-2（额外指标）
            metrics['rouge-1'] = calculate_rouge(reference_answer, generated_answer, 'rouge1')
            metrics['rouge-2'] = calculate_rouge(reference_answer, generated_answer, 'rouge2')
            
            # Token F1
            metrics['f1'] = calculate_f1(reference_answer, generated_answer)
            
            # BERTScore（可选，较慢）
            if self.use_bertscore and BERTSCORE_AVAILABLE:
                bert_scores = calculate_bertscore(reference_answer, generated_answer)
                metrics['bertscore-p'] = bert_scores['precision']
                metrics['bertscore-r'] = bert_scores['recall']
                metrics['bertscore-f1'] = bert_scores['f1']
        
        # 检索质量指标（需要检索结果）
        if retrieved_docs and relevant_docs:
            retrieved_ids = [doc.get('doc_id', doc.get('id', '')) for doc in retrieved_docs]
            
            # Recall@5
            metrics['recall@5'] = calculate_recall(retrieved_ids, relevant_docs, k=5)
            
            # nDCG@5
            relevance_scores = [1.0 if doc_id in relevant_docs else 0.0 for doc_id in retrieved_ids[:5]]
            metrics['ndcg@5'] = calculate_ndcg(relevance_scores, k=5)
            
            # MRR
            relevance_binary = [1 if doc_id in relevant_docs else 0 for doc_id in retrieved_ids]
            metrics['mrr'] = calculate_mrr(relevance_binary)
        
        self.results.append({
            'query': query,
            'metrics': metrics
        })
        
        return metrics
    
    def get_average_metrics(self) -> Dict[str, float]:
        """计算平均指标"""
        if not self.results:
            return {}
        
        # 收集所有指标
        all_metrics = {}
        for result in self.results:
            for metric_name, value in result['metrics'].items():
                if metric_name not in all_metrics:
                    all_metrics[metric_name] = []
                all_metrics[metric_name].append(value)
        
        # 计算平均值
        avg_metrics = {}
        for metric_name, values in all_metrics.items():
            avg_metrics[metric_name] = np.mean(values)
            avg_metrics[f'{metric_name}_std'] = np.std(values)
        
        return avg_metrics
    
    def get_summary(self) -> Dict[str, Any]:
        """获取评估摘要"""
        return {
            'total_queries': len(self.results),
            'average_metrics': self.get_average_metrics(),
            'individual_results': self.results
        }

