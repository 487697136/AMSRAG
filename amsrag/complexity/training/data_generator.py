"""
复杂度分类器训练数据生成器

从MS MARCO和HotpotQA生成标注数据，实现自动的复杂度标注
"""

import json
import random
import logging
from typing import List, Dict, Tuple, Optional
from pathlib import Path
import asyncio
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ComplexityLabel:
    """复杂度标签"""
    query: str
    complexity: str  # zero_hop, one_hop, multi_hop
    reasoning: str
    confidence: float


class ComplexityDataGenerator:
    """
    复杂度数据生成器
    
    根据论文定义：
    - Zero-hop: 可以直接依赖模型内部知识作答
    - One-hop: 需要单一证据片段
    - Multi-hop: 涉及跨实体或跨文档的综合推理
    """
    
    def __init__(self, llm_func: Optional[callable] = None):
        """
        初始化数据生成器
        
        Args:
            llm_func: LLM函数，用于辅助标注
        """
        self.llm_func = llm_func
        
        # 用于复杂度判断的关键词模式
        self.zero_hop_patterns = [
            "what is", "define", "explain", "describe",
            "是什么", "定义", "解释", "描述"
        ]
        
        self.multi_hop_patterns = [
            "compare", "relationship", "difference", "similarity",
            "how does", "why does", "what caused", "what led to",
            "比较", "关系", "区别", "相似", "导致", "原因"
        ]
        
        # 实体识别模式（简单版）
        self.entity_patterns = [
            r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*",  # 英文实体
            r"《[^》]+》",  # 中文书名号
            r"「[^」]+」",  # 中文引号
        ]
    
    def classify_complexity_heuristic(self, query: str) -> Tuple[str, float]:
        """
        基于启发式规则的复杂度分类
        
        Args:
            query: 查询文本
            
        Returns:
            (复杂度类别, 置信度)
        """
        query_lower = query.lower()
        
        # 检查zero-hop模式
        for pattern in self.zero_hop_patterns:
            if pattern in query_lower and len(query.split()) <= 10:
                return "zero_hop", 0.8
        
        # 检查multi-hop模式
        multi_hop_score = 0
        for pattern in self.multi_hop_patterns:
            if pattern in query_lower:
                multi_hop_score += 1
        
        # 统计实体数量
        import re
        entity_count = 0
        for pattern in self.entity_patterns:
            entities = re.findall(pattern, query)
            entity_count += len(entities)
        
        # 多实体通常意味着多跳
        if entity_count >= 2 or multi_hop_score >= 2:
            return "multi_hop", 0.7
        elif multi_hop_score >= 1:
            return "multi_hop", 0.6
        
        # 默认为one-hop
        return "one_hop", 0.6
    
    async def classify_with_llm(self, query: str, context: Optional[str] = None, 
                               use_self_consistency: bool = True,
                               num_samples: int = 3) -> ComplexityLabel:
        """
        使用LLM进行复杂度分类（更准确）
        
        实现论文中的自一致性策略：对同一查询生成多次结果并投票表决
        
        Args:
            query: 查询文本
            context: 相关上下文（可选）
            use_self_consistency: 是否使用自一致性策略
            num_samples: 自一致性采样次数
            
        Returns:
            复杂度标签
        """
        if not self.llm_func:
            # 退回到启发式方法
            complexity, confidence = self.classify_complexity_heuristic(query)
            return ComplexityLabel(
                query=query,
                complexity=complexity,
                reasoning="Heuristic classification",
                confidence=confidence
            )
        
        # 构建分类提示（基于论文的标注方法）
        prompt = f"""请分析以下查询的复杂度，并分类为以下三种类型之一：

**复杂度定义**（论文第3.1节）：

1. **zero_hop（零跳）**: 可以直接依赖语言模型内部知识作答，不需要外部信息
   - 示例：什么是人工智能？中国的首都是哪里？

2. **one_hop（单跳）**: 需要检索单一证据片段即可回答
   - 示例：ModernBERT是什么时候发布的？某公司的创始人是谁？

3. **multi_hop（多跳）**: 需要跨实体或跨文档的综合推理，涉及多个证据
   - 示例：《盗梦空间》的导演之前执导过哪部蝙蝠侠电影？

**待分类查询**: {query}

请仔细分析查询需要的推理步骤，并以JSON格式返回：
{{
    "complexity": "zero_hop/one_hop/multi_hop",
    "reasoning": "详细的分类理由，说明需要几步推理",
    "confidence": 0.0-1.0的置信度分数
}}"""
        
        if not use_self_consistency:
            # 单次推理
            try:
                response = await self.llm_func(prompt)
                result = json.loads(response)
                
                return ComplexityLabel(
                    query=query,
                    complexity=result["complexity"],
                    reasoning=result["reasoning"],
                    confidence=result["confidence"]
                )
            except Exception as e:
                logger.warning(f"LLM分类失败，退回到启发式方法: {e}")
                complexity, confidence = self.classify_complexity_heuristic(query)
                return ComplexityLabel(
                    query=query,
                    complexity=complexity,
                    reasoning=f"Fallback to heuristic due to: {str(e)}",
                    confidence=confidence
                )
        
        # 自一致性策略（论文方法）
        try:
            from collections import Counter
            
            samples = []
            for i in range(num_samples):
                try:
                    response = await self.llm_func(prompt)
                    result = json.loads(response)
                    samples.append({
                        "complexity": result["complexity"],
                        "reasoning": result["reasoning"],
                        "confidence": result["confidence"]
                    })
                except Exception as e:
                    logger.warning(f"采样{i+1}失败: {e}")
            
            if not samples:
                raise Exception("所有采样都失败")
            
            # 投票表决
            complexity_votes = Counter([s["complexity"] for s in samples])
            most_common = complexity_votes.most_common(1)[0]
            majority_complexity = most_common[0]
            vote_count = most_common[1]
            
            # 计算一致性
            consistency = vote_count / len(samples)
            
            # 如果一致性低，标记为待审核
            if consistency < 0.5:
                reasoning = f"一致性低({consistency:.2f})，建议人工复核"
                final_confidence = 0.3
            else:
                # 使用多数投票的理由和平均置信度
                majority_samples = [s for s in samples if s["complexity"] == majority_complexity]
                reasoning = majority_samples[0]["reasoning"]
                final_confidence = sum(s["confidence"] for s in majority_samples) / len(majority_samples)
                final_confidence *= consistency  # 用一致性加权
            
            return ComplexityLabel(
                query=query,
                complexity=majority_complexity,
                reasoning=f"自一致性({consistency:.2f}): {reasoning}",
                confidence=final_confidence
            )
            
        except Exception as e:
            logger.warning(f"自一致性策略失败，退回到单次推理: {e}")
            # 退回到单次推理
            return await self.classify_with_llm(query, context, use_self_consistency=False)
    
    async def generate_from_msmarco(self, 
                                   msmarco_path: str,
                                   sample_size: int = 10000) -> List[ComplexityLabel]:
        """
        从MS MARCO数据集生成训练数据
        
        MS MARCO主要包含事实型查询，大部分是zero-hop和one-hop
        
        Args:
            msmarco_path: MS MARCO数据集路径
            sample_size: 采样大小
            
        Returns:
            标注的复杂度数据
        """
        labels = []
        
        try:
            with open(msmarco_path, 'r', encoding='utf-8') as f:
                queries = []
                for i, line in enumerate(f):
                    if i >= sample_size:
                        break
                    data = json.loads(line.strip())
                    queries.append(data.get('query', data.get('question', '')))
            
            # 随机采样
            if len(queries) > sample_size:
                queries = random.sample(queries, sample_size)
            
            # 批量分类
            logger.info(f"开始标注 {len(queries)} 个MS MARCO查询")
            for i, query in enumerate(queries):
                if i % 100 == 0:
                    logger.info(f"进度: {i}/{len(queries)}")
                
                label = await self.classify_with_llm(query)
                labels.append(label)
            
        except Exception as e:
            logger.error(f"处理MS MARCO数据失败: {e}")
        
        return labels
    
    async def generate_from_hotpotqa(self,
                                    hotpotqa_path: str,
                                    sample_size: int = 5000) -> List[ComplexityLabel]:
        """
        从HotpotQA数据集生成训练数据
        
        HotpotQA专注于多跳推理，大部分是multi-hop
        
        Args:
            hotpotqa_path: HotpotQA数据集路径
            sample_size: 采样大小
            
        Returns:
            标注的复杂度数据
        """
        labels = []
        
        try:
            with open(hotpotqa_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            questions = []
            for item in data[:sample_size]:
                question = item.get('question', '')
                # HotpotQA的type字段可以帮助判断
                question_type = item.get('type', 'unknown')
                if question:
                    questions.append((question, question_type))
            
            logger.info(f"开始标注 {len(questions)} 个HotpotQA查询")
            for i, (query, qtype) in enumerate(questions):
                if i % 100 == 0:
                    logger.info(f"进度: {i}/{len(questions)}")
                
                # HotpotQA的bridge和comparison类型通常是multi-hop
                if qtype in ['bridge', 'comparison']:
                    label = ComplexityLabel(
                        query=query,
                        complexity="multi_hop",
                        reasoning=f"HotpotQA {qtype} question",
                        confidence=0.9
                    )
                else:
                    label = await self.classify_with_llm(query)
                
                labels.append(label)
                
        except Exception as e:
            logger.error(f"处理HotpotQA数据失败: {e}")
        
        return labels
    
    def balance_dataset(self, labels: List[ComplexityLabel]) -> List[ComplexityLabel]:
        """
        平衡数据集，确保各类别相对均衡
        
        Args:
            labels: 原始标注数据
            
        Returns:
            平衡后的数据
        """
        # 按复杂度分组
        by_complexity = {
            "zero_hop": [],
            "one_hop": [],
            "multi_hop": []
        }
        
        for label in labels:
            if label.complexity in by_complexity:
                by_complexity[label.complexity].append(label)
        
        # 找到最少的类别数量
        min_count = min(len(v) for v in by_complexity.values())
        max_per_class = min(min_count * 2, max(len(v) for v in by_complexity.values()))
        
        # 平衡采样
        balanced = []
        for complexity, items in by_complexity.items():
            if len(items) > max_per_class:
                sampled = random.sample(items, max_per_class)
            else:
                sampled = items
            balanced.extend(sampled)
        
        random.shuffle(balanced)
        
        logger.info(f"数据平衡完成:")
        for complexity in by_complexity:
            count = sum(1 for l in balanced if l.complexity == complexity)
            logger.info(f"  {complexity}: {count}")
        
        return balanced
    
    def save_dataset(self, labels: List[ComplexityLabel], output_path: str):
        """
        保存数据集
        
        Args:
            labels: 标注数据
            output_path: 输出路径
        """
        data = []
        for label in labels:
            data.append({
                "query": label.query,
                "complexity": label.complexity,
                "reasoning": label.reasoning,
                "confidence": label.confidence
            })
        
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"数据集已保存到: {output_path}")


async def generate_training_data(
    msmarco_path: Optional[str] = None,
    hotpotqa_path: Optional[str] = None,
    output_path: str = "complexity_training_data.json",
    llm_func: Optional[callable] = None,
    msmarco_samples: int = 10000,
    hotpotqa_samples: int = 5000
) -> str:
    """
    生成复杂度分类器的训练数据
    
    Args:
        msmarco_path: MS MARCO数据集路径
        hotpotqa_path: HotpotQA数据集路径
        output_path: 输出路径
        llm_func: LLM函数
        msmarco_samples: MS MARCO采样数
        hotpotqa_samples: HotpotQA采样数
        
    Returns:
        输出文件路径
    """
    generator = ComplexityDataGenerator(llm_func=llm_func)
    all_labels = []
    
    # 从MS MARCO生成
    if msmarco_path:
        logger.info("从MS MARCO生成数据...")
        msmarco_labels = await generator.generate_from_msmarco(
            msmarco_path, msmarco_samples
        )
        all_labels.extend(msmarco_labels)
    
    # 从HotpotQA生成
    if hotpotqa_path:
        logger.info("从HotpotQA生成数据...")
        hotpotqa_labels = await generator.generate_from_hotpotqa(
            hotpotqa_path, hotpotqa_samples
        )
        all_labels.extend(hotpotqa_labels)
    
    # 平衡数据集
    balanced_labels = generator.balance_dataset(all_labels)
    
    # 保存数据
    generator.save_dataset(balanced_labels, output_path)
    
    return output_path
