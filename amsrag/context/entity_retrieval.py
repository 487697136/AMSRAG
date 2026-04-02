"""
实体检索增强模块

提供混合检索策略：向量检索 + 关键词匹配回退
解决Local模式实体检索失败率高的问题
"""

import re
from typing import Dict, Any, List, Set
from ..base import BaseGraphStorage, BaseVectorStorage, QueryParam
from .._utils import logger


# 英文停用词列表
STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "which", "what", "who", "whom", "whose", "where", "when", "why", "how",
    "to", "for", "of", "in", "on", "at", "by", "with", "from", "about",
    "according", "their", "this", "that", "these", "those", "it", "its",
    "have", "has", "had", "do", "does", "did", "will", "would", "should",
    "could", "may", "might", "must", "can", "shall"
}


def extract_keywords(query: str, min_length: int = 3) -> List[str]:
    """
    从查询中提取关键词
    
    Args:
        query: 查询文本
        min_length: 最小关键词长度
        
    Returns:
        关键词列表
    """
    # 转小写
    query_lower = query.lower()
    
    # 提取单词（字母和数字）
    words = re.findall(r'\b[a-zA-Z0-9]{' + str(min_length) + r',}\b', query_lower)
    
    # 过滤停用词
    keywords = [w for w in words if w not in STOP_WORDS]
    
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
        text = text.lower()
        keywords = [k.lower() for k in keywords]
    
    # 计算匹配的关键词数量
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
    # 提取关键词
    keywords = extract_keywords(query)
    
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
