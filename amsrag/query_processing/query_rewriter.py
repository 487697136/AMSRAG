"""
查询重写模块

将自然语言问句转换为更适合检索的形式
提升实体检索和关键词检索的准确率
"""

import json
import re
from typing import Dict, Any, List, Callable
from .._utils import logger


async def rewrite_query_for_entity_search(
    query: str,
    llm_func: Callable,
    **llm_kwargs
) -> Dict[str, Any]:
    """
    将问句重写为更适合实体检索的形式
    
    策略：
    1. 提取实体名称
    2. 提取关键词
    3. 生成关键词版本的查询
    
    示例：
        输入："Which shards are eligible for Temporal Rebinding Cycles?"
        输出：{
            "original": "Which shards are eligible for Temporal Rebinding Cycles?",
            "rewritten": "Temporal Rebinding Cycles TRC shards eligible SSI",
            "entities": ["Temporal Rebinding Cycles", "shards"],
            "keywords": ["eligible", "TRC", "SSI"]
        }
    
    Args:
        query: 原始查询
        llm_func: LLM函数
        **llm_kwargs: LLM参数
        
    Returns:
        重写结果字典
    """
    prompt = f"""Extract key entities and keywords from this question for entity search.

Question: "{query}"

Return a JSON with:
- entities: list of entity names mentioned (proper nouns, technical terms)
- keywords: list of important keywords (verbs, adjectives, key concepts)
- rewritten: a keyword-based version of the question (remove question words, keep only key terms)

Example:
Question: "Which shards are eligible for Temporal Rebinding Cycles?"
{{
  "entities": ["Temporal Rebinding Cycles", "shards"],
  "keywords": ["eligible", "TRC", "SSI", "values"],
  "rewritten": "Temporal Rebinding Cycles TRC shards eligible SSI"
}}

Now process the question above and return ONLY the JSON:"""
    
    try:
        response = await llm_func(prompt, **llm_kwargs)
        
        # 尝试解析JSON
        # 移除可能的markdown代码块标记
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()
        
        result = json.loads(response)
        
        # 添加原始查询
        result["original"] = query
        
        # 验证必需字段
        if "rewritten" not in result:
            result["rewritten"] = query
        if "entities" not in result:
            result["entities"] = []
        if "keywords" not in result:
            result["keywords"] = []
        
        logger.info(f"Query rewritten: '{query}' -> '{result.get('rewritten')}'")
        
        return result
        
    except Exception as e:
        logger.error(f"Query rewriting failed: {e}")
        # 回退到原始查询
        return {
            "original": query,
            "rewritten": query,
            "entities": [],
            "keywords": [],
            "error": str(e)
        }


def simple_query_rewrite(query: str) -> str:
    """
    简单的查询重写（不使用LLM）
    
    策略：
    1. 移除疑问词
    2. 移除停用词
    3. 保留关键词
    
    Args:
        query: 原始查询
        
    Returns:
        重写后的查询
    """
    # 疑问词列表
    question_words = {
        "which", "what", "who", "whom", "whose", "where", "when", 
        "why", "how", "is", "are", "was", "were", "do", "does", 
        "did", "can", "could", "would", "should", "may", "might"
    }
    
    # 停用词列表
    stop_words = {
        "the", "a", "an", "to", "for", "of", "in", "on", "at", 
        "by", "with", "from", "about", "according", "their"
    }
    
    # 转小写并分词
    words = re.findall(r'\b\w+\b', query.lower())
    
    # 过滤疑问词和停用词
    filtered_words = [
        w for w in words 
        if w not in question_words and w not in stop_words and len(w) > 2
    ]
    
    # 重新组合
    rewritten = " ".join(filtered_words)
    
    return rewritten if rewritten else query


async def expand_query_with_synonyms(
    query: str,
    llm_func: Callable,
    max_synonyms: int = 3,
    **llm_kwargs
) -> List[str]:
    """
    使用LLM扩展查询（生成同义词变体）
    
    Args:
        query: 原始查询
        llm_func: LLM函数
        max_synonyms: 最大同义词数量
        **llm_kwargs: LLM参数
        
    Returns:
        查询变体列表（包含原始查询）
    """
    prompt = f"""Generate {max_synonyms} alternative phrasings of this query using synonyms.

Original query: "{query}"

Return a JSON list of alternative queries:
["alternative 1", "alternative 2", "alternative 3"]

Keep the meaning the same, just use different words.
Return ONLY the JSON list:"""
    
    try:
        response = await llm_func(prompt, **llm_kwargs)
        
        # 解析JSON
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()
        
        alternatives = json.loads(response)
        
        # 添加原始查询
        queries = [query] + alternatives[:max_synonyms]
        
        logger.info(f"Query expanded to {len(queries)} variants")
        
        return queries
        
    except Exception as e:
        logger.error(f"Query expansion failed: {e}")
        return [query]


def extract_entities_from_query(query: str) -> List[str]:
    """
    从查询中提取可能的实体名称（简单版本，不使用LLM）
    
    策略：
    1. 提取首字母大写的词组
    2. 提取全大写的缩写
    3. 提取括号中的内容
    
    Args:
        query: 查询文本
        
    Returns:
        可能的实体列表
    """
    entities = []
    
    # 1. 提取首字母大写的词组（2-4个词）
    capitalized_phrases = re.findall(
        r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}\b', 
        query
    )
    entities.extend(capitalized_phrases)
    
    # 2. 提取全大写的缩写（2-6个字母）
    abbreviations = re.findall(r'\b[A-Z]{2,6}\b', query)
    entities.extend(abbreviations)
    
    # 3. 提取括号中的内容
    parentheses_content = re.findall(r'\(([^)]+)\)', query)
    entities.extend(parentheses_content)
    
    # 去重
    entities = list(set(entities))
    
    return entities
