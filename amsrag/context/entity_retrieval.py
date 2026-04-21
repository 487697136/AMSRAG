"""
实体检索增强模块

提供混合检索策略：向量检索 + 关键词匹配回退
解决Local模式实体检索失败率高的问题
"""

import re
from typing import Dict, Any, List, Set
from ..base import BaseGraphStorage, BaseVectorStorage, QueryParam
from .._utils import logger

# ---------- jieba 延迟加载 ----------
try:
    import jieba
    import jieba.posseg as pseg
    _JIEBA_AVAILABLE = True
    jieba.setLogLevel("WARNING")  # 静默字典加载日志
except ImportError:
    _JIEBA_AVAILABLE = False
    logger.warning("jieba 未安装，中文关键词提取将降级为 n-gram 模式。建议 pip install jieba")

# 英文停用词列表
STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "which", "what", "who", "whom", "whose", "where", "when", "why", "how",
    "to", "for", "of", "in", "on", "at", "by", "with", "from", "about",
    "according", "their", "this", "that", "these", "those", "it", "its",
    "have", "has", "had", "do", "does", "did", "will", "would", "should",
    "could", "may", "might", "must", "can", "shall"
}

# 中文停用词：常见功能词、疑问词、代词等，不携带实体信息
CHINESE_STOP_WORDS = {
    "的", "地", "得", "了", "着", "过",
    "和", "与", "或", "及", "但", "而", "也",
    "在", "于", "从", "到", "对", "向", "把", "被", "由",
    "这", "那", "此", "该", "其", "之", "各", "每",
    "什么", "哪", "谁", "哪里", "哪些", "为何", "怎么", "怎样", "如何",
    "是", "有", "没有", "不", "都", "就", "才", "又", "再", "已",
    "我", "你", "他", "她", "它", "我们", "你们", "他们",
    "请", "请问", "告诉", "分析", "介绍", "说明", "描述", "回答",
    "一个", "一些", "可以", "能够", "需要", "关于", "根据",
    "讲", "说", "写", "述", "谈", "论",
}

# jieba 词性标注中表示实体信息的词性（保留），其余虚词/助词/连词跳过
_JIEBA_KEEP_FLAGS = {
    "n",   # 普通名词
    "nr",  # 人名
    "ns",  # 地名
    "nt",  # 机构名
    "nz",  # 其它专名
    "v",   # 动词（保留，利于描述性实体匹配）
    "vn",  # 动名词
    "an",  # 名形词
    "i",   # 成语
    "j",   # 简称缩写
    "eng", # 英文
    "x",   # 非汉字串（数字/字母混合）
}


def _get_core_query(query: str) -> str:
    """
    从记忆增强查询字符串中提取核心当前问题。

    当后端开启记忆功能时，传入的 query 形如：
        "Conversation context:\\nUser: ...\\nAssistant: ...\\n\\nCurrent question:\\n实际问题"
    此函数提取 "Current question:" 之后的纯问题部分；若无此标记则原样返回。
    """
    for marker in ("Current question:\n", "Current question:"):
        idx = query.find(marker)
        if idx != -1:
            return query[idx + len(marker):].strip()
    return query


def _fallback_chinese_keywords(text: str, min_length: int) -> List[str]:
    """jieba 不可用时的降级方案：提取连续汉字序列 + 2-4 字滑动窗口。"""
    seen: set = set()
    result: List[str] = []

    seqs = re.findall(r'[\u4e00-\u9fff]{' + str(min_length) + r',}', text)
    for seq in seqs:
        if seq not in CHINESE_STOP_WORDS and seq not in seen:
            seen.add(seq)
            result.append(seq)
        if len(seq) > 4:
            n = len(seq)
            for size in range(2, min(5, n + 1)):
                for i in range(n - size + 1):
                    ng = seq[i: i + size]
                    if ng not in CHINESE_STOP_WORDS and ng not in seen:
                        seen.add(ng)
                        result.append(ng)
    return result


def extract_keywords(query: str, min_length: int = 2) -> List[str]:
    """
    从查询中提取关键词，支持中英文混合。

    - 中文：优先使用 jieba 词性标注分词，保留名词/人名/地名等有意义词性，
      过滤助词/连词等停用词；jieba 未安装时降级为 n-gram。
    - 英文：正则提取字母/数字词（长度 ≥ 3），过滤英文停用词。

    Args:
        query: 查询文本（应仅为核心问题，不含对话模板头部）
        min_length: 保留词的最小字符数（中文）

    Returns:
        去重后的关键词列表
    """
    seen: set = set()
    keywords: List[str] = []

    def _add(kw: str) -> None:
        if kw and kw not in seen:
            seen.add(kw)
            keywords.append(kw)

    if _JIEBA_AVAILABLE:
        try:
            # 使用词性标注分词，保留有实体意义的词
            for word, flag in pseg.cut(query):
                word = word.strip()
                if not word or len(word) < min_length:
                    continue
                if word in CHINESE_STOP_WORDS:
                    continue
                # 纯标点/空白跳过
                if re.fullmatch(r'[\s\W]+', word):
                    continue
                # 中文词：按词性过滤
                if re.search(r'[\u4e00-\u9fff]', word):
                    if flag in _JIEBA_KEEP_FLAGS or flag.startswith("n"):
                        _add(word)
                else:
                    # 非中文词（英文/数字等）：长度过滤
                    if len(word) >= 3 and word.lower() not in STOP_WORDS:
                        _add(word.lower())
        except Exception as exc:
            logger.warning("jieba 分词失败，降级到 n-gram: %s", exc)
            for kw in _fallback_chinese_keywords(query, min_length):
                _add(kw)
    else:
        for kw in _fallback_chinese_keywords(query, min_length):
            _add(kw)

    # 英文/数字词补充（jieba 可能对纯英文文本拆得不准）
    query_lower = query.lower()
    for w in re.findall(r'\b[a-zA-Z0-9]{3,}\b', query_lower):
        if w not in STOP_WORDS:
            _add(w)

    return keywords


def calculate_keyword_match_score(
    text: str, 
    keywords: List[str],
    case_sensitive: bool = False
) -> float:
    """
    计算文本与关键词的匹配分数
    
    Args:
        text: 待匹配文本
        keywords: 关键词列表
        case_sensitive: 是否区分大小写
        
    Returns:
        匹配分数（0-1）
    """
    if not keywords:
        return 0.0
    
    if not case_sensitive:
        # lower() 不影响中文字符，英文大小写规范化即可
        text = text.lower()
        keywords = [k.lower() for k in keywords]

    # 计算匹配的关键词数量（子串匹配，中英文均适用）
    matches = sum(1 for kw in keywords if kw in text)
    
    # 归一化分数
    score = matches / len(keywords)
    
    return score


async def keyword_match_entities(
    query: str,
    knowledge_graph_inst: BaseGraphStorage,
    top_k: int = 10,
    min_score: float = 0.1
) -> List[Dict[str, Any]]:
    """
    基于关键词匹配实体（向量检索的回退机制）
    
    策略：
    1. 提取查询中的关键词（去除停用词）
    2. 遍历所有实体，计算关键词重叠度
    3. 返回匹配度最高的top_k个实体
    
    Args:
        query: 查询文本
        knowledge_graph_inst: 知识图谱实例
        top_k: 返回结果数量
        min_score: 最小匹配分数阈值
        
    Returns:
        匹配的实体列表，格式与向量检索兼容
    """
    # 从记忆增强查询中提取核心问题，避免把对话模板英文词误作关键词
    core_query = _get_core_query(query)

    # 提取关键词（中文优先）
    keywords = extract_keywords(core_query)

    if not keywords:
        logger.warning("No keywords extracted from query")
        return []

    logger.debug(f"Extracted keywords: {keywords}")
    
    # 获取所有实体节点
    try:
        all_nodes = knowledge_graph_inst._graph.nodes(data=True)
    except Exception as e:
        logger.error(f"Failed to get graph nodes: {e}")
        return []
    
    # 计算每个实体的匹配分数
    entity_scores = []
    
    for node_id, node_data in all_nodes:
        # 提取实体信息
        entity_name = node_data.get("entity_name", node_id)
        description = node_data.get("description", "")
        entity_type = node_data.get("entity_type", "")
        
        # 合并所有文本用于匹配
        combined_text = f"{entity_name} {description} {entity_type}"
        
        # 计算匹配分数
        score = calculate_keyword_match_score(combined_text, keywords)
        
        # 过滤低分结果
        if score >= min_score:
            entity_scores.append({
                "entity_name": entity_name,
                "score": score,
                "distance": 1.0 - score,  # 兼容向量检索格式
                "match_method": "keyword"  # 标记检索方法
            })
    
    # 按分数排序
    entity_scores.sort(key=lambda x: x["score"], reverse=True)
    
    # 返回top_k结果
    top_results = entity_scores[:top_k]
    
    logger.info(
        f"Keyword matching found {len(entity_scores)} entities, "
        f"returning top {len(top_results)}"
    )
    
    return top_results


async def hybrid_entity_retrieval(
    query: str,
    entities_vdb: BaseVectorStorage,
    knowledge_graph_inst: BaseGraphStorage,
    query_param: QueryParam,
    enable_keyword_fallback: bool = True
) -> List[Dict[str, Any]]:
    """
    混合实体检索：向量检索 + 关键词回退
    
    工作流程：
    1. 首先尝试向量检索
    2. 如果结果不足（< 3个），启用关键词匹配
    3. 合并结果并去重
    
    Args:
        query: 查询文本
        entities_vdb: 实体向量数据库
        knowledge_graph_inst: 知识图谱实例
        query_param: 查询参数
        enable_keyword_fallback: 是否启用关键词回退
        
    Returns:
        实体列表
    """
    # 第一步：向量检索
    vector_results = await entities_vdb.query(query, top_k=query_param.top_k)
    
    logger.info(f"Vector retrieval returned {len(vector_results)} entities")
    
    # 如果向量检索结果充足，直接返回
    if len(vector_results) >= 3 or not enable_keyword_fallback:
        return vector_results
    
    # 第二步：关键词回退
    logger.warning(
        f"Vector retrieval returned only {len(vector_results)} entities, "
        f"enabling keyword fallback"
    )
    
    keyword_results = await keyword_match_entities(
        query,
        knowledge_graph_inst,
        top_k=query_param.top_k
    )
    
    # 第三步：合并结果（去重）
    existing_ids = {r["entity_name"] for r in vector_results}
    
    for kr in keyword_results:
        if kr["entity_name"] not in existing_ids:
            vector_results.append(kr)
            existing_ids.add(kr["entity_name"])
            
            # 达到top_k就停止
            if len(vector_results) >= query_param.top_k:
                break
    
    logger.info(
        f"Hybrid retrieval final result: {len(vector_results)} entities "
        f"(vector: {len([r for r in vector_results if 'match_method' not in r])}, "
        f"keyword: {len([r for r in vector_results if r.get('match_method') == 'keyword'])})"
    )
    
    return vector_results


def generate_entity_variants(entity_name: str) -> List[str]:
    """
    生成实体名称变体（用于未来的实体变体索引功能）
    
    示例：
        "TEMPORAL REBINDING CYCLES (TRC)" → 
        ["TRC", "Temporal Rebinding Cycles", "temporal rebinding cycles", ...]
    
    Args:
        entity_name: 原始实体名称
        
    Returns:
        变体列表（包含原始名称）
    """
    variants: Set[str] = {entity_name}
    
    # 1. 小写版本
    variants.add(entity_name.lower())
    
    # 2. 提取缩写（如果有括号）
    if "(" in entity_name and ")" in entity_name:
        # 提取括号内的缩写
        abbr = entity_name[entity_name.find("(")+1:entity_name.find(")")]
        variants.add(abbr)
        variants.add(abbr.lower())
        
        # 提取括号外的全称
        full_name = entity_name.split("(")[0].strip()
        variants.add(full_name)
        variants.add(full_name.lower())
    
    # 3. 移除特殊字符版本
    clean_name = re.sub(r'[^\w\s]', ' ', entity_name)
    clean_name = ' '.join(clean_name.split())  # 移除多余空格
    if clean_name != entity_name:
        variants.add(clean_name)
        variants.add(clean_name.lower())
    
    # 4. 首字母大写版本
    title_case = entity_name.title()
    if title_case != entity_name:
        variants.add(title_case)
    
    # 5. 移除连字符版本
    if "-" in entity_name:
        no_hyphen = entity_name.replace("-", " ")
        variants.add(no_hyphen)
        variants.add(no_hyphen.lower())
    
    # 6. 移除下划线版本
    if "_" in entity_name:
        no_underscore = entity_name.replace("_", " ")
        variants.add(no_underscore)
        variants.add(no_underscore.lower())
    
    return list(variants)
