"""
澶嶆潅搴︽劅鐭ヨ矾鐢卞櫒妯″潡
鍩轰簬鏌ヨ澶嶆潅搴﹁嚜鍔ㄩ€夋嫨鏈€浣虫绱㈢瓥鐣?
"""

import asyncio
import json
import math
from typing import List, Dict, Optional, Any
from dataclasses import dataclass
from abc import ABC, abstractmethod

from .classifier import ComplexityClassifier, ComplexityClassifierConfig
from .._utils import logger

class BaseRouter(ABC):
    """璺敱鍣ㄥ熀绫?- 鎻愪緵鍩烘湰鐨勮矾鐢辨帴鍙?"""
    
    def __init__(self):
        pass
    
    @abstractmethod
    async def route(self, query: str, available_modes: List[str] = None) -> str:
        """璺敱鏌ヨ鍒版绱㈡ā寮?"""
        pass
    
    @abstractmethod
    def create_query_param(self, query: str, available_modes: List[str] = None, **kwargs) -> Any:
        """鍒涘缓鏌ヨ鍙傛暟"""
        pass

@dataclass
class ComplexityAwareRouter(BaseRouter):
    """澶嶆潅搴︽劅鐭ヨ矾鐢卞櫒
    
    鍩轰簬ModernBERT澶嶆潅搴﹀垎绫诲櫒锛屽皢鏌ヨ璺敱鍒版渶閫傚悎鐨勬绱㈡ā寮忋€?
    """
    
    model_path: str = "amsrag/models/modernbert_complexity_classifier_standard"
    confidence_threshold: float = 0.6
    enable_fallback: bool = False  # 严格使用ModernBERT，禁止基于置信度的规则回退
    use_modernbert: bool = True
    
    def __post_init__(self):
        """鍒濆鍖栬矾鐢卞櫒"""
        super().__init__()
        
        # 澶嶆潅搴﹀埌妫€绱㈡ā寮忕殑鏄犲皠
        # v0.6.0: one_hop涔熶娇鐢╨ocal浠ュ惎鐢ㄦ贩鍚堟绱?
        self._complexity_to_candidate = {
            "zero_hop": ["llm_only"],              # 鏃犳绱細鐩存帴LLM鍥炵瓟
            "one_hop": ["local", "naive", "bm25"], # 鍗曡烦妫€绱細浼樺厛浣跨敤local锛堟贩鍚堟绱級
            "multi_hop": ["local", "global"],      # 澶氳烦妫€绱細鍥炬帹鐞?
        }
        
        # 鍒濆鍖栧垎绫诲櫒
        self.classifier = None
        if self.use_modernbert:
            try:
                config = ComplexityClassifierConfig(
                    model_path=self.model_path,
                    confidence_threshold=self.confidence_threshold
                )
                self.classifier = ComplexityClassifier(config)
                logger.info(f"澶嶆潅搴﹀垎绫诲櫒鍒濆鍖栨垚鍔? {self.model_path}")
            except Exception as e:
                logger.warning(f"澶嶆潅搴﹀垎绫诲櫒鍒濆鍖栧け璐? {e}")
                self.classifier = None
        
        # 缁熻淇℃伅
        self._complexity_stats = {
            "zero_hop": 0,
            "one_hop": 0,
            "multi_hop": 0,
            "fallback": 0
        }
    
    async def predict_complexity_detailed(self, query: str) -> Dict[str, Any]:
        """棰勬祴鏌ヨ澶嶆潅搴︼紙璇︾粏鐗堟湰锛?"""
        try:
            if self.classifier and self.classifier.is_available():
                # 浣跨敤ModernBERT鍒嗙被鍣?
                complexity, confidence, probabilities = self.classifier.predict_with_confidence(query)
                
                # 鏇存柊缁熻
                self._complexity_stats[complexity] += 1
                
                # 鑾峰彇鍊欓€夋ā寮?
                candidate_modes = self._complexity_to_candidate.get(complexity, ["naive"])
                
                return {
                    "complexity": complexity,
                    "confidence": confidence,
                    "probabilities": probabilities,
                    "candidate_modes": candidate_modes,
                    "method": "modernbert"
                }
            else:
                if not self.enable_fallback:
                    # 严格模式：分类器不可用时使用保守默认值，不降级到规则分类
                    logger.error(
                        "ModernBERT分类器不可用且enable_fallback=False，"
                        "使用保守默认值 one_hop 以维持系统运行"
                    )
                    self._complexity_stats["one_hop"] += 1
                    return {
                        "complexity": "one_hop",
                        "confidence": 0.5,
                        "probabilities": {},
                        "candidate_modes": self._complexity_to_candidate.get(
                            "one_hop", ["local", "naive", "bm25"]
                        ),
                        "method": "modernbert_unavailable_default"
                    }
                # 回退到规则分类（仅当 enable_fallback=True 时）
                return await self._rule_based_complexity(query)
                
        except Exception as e:
            logger.error(f"ModernBERT复杂度预测失败: {e}")
            if not self.enable_fallback:
                # 严格模式：异常时也不降级，使用保守默认值
                logger.error("严格模式: enable_fallback=False，异常情况下使用保守默认值 one_hop")
                self._complexity_stats["one_hop"] += 1
                return {
                    "complexity": "one_hop",
                    "confidence": 0.5,
                    "probabilities": {},
                    "candidate_modes": self._complexity_to_candidate.get(
                        "one_hop", ["local", "naive", "bm25"]
                    ),
                    "method": "modernbert_exception_default"
                }
            return await self._rule_based_complexity(query)
    
    async def predict_complexity(self, query: str) -> str:
        """棰勬祴鏌ヨ澶嶆潅搴︼紙绠€鍖栫増鏈級"""
        result = await self.predict_complexity_detailed(query)
        return result["complexity"]
    
    # 需要 global（社区报告）检索的中文关键词
    _GLOBAL_CN_KEYWORDS = [
        "讲的是什么", "讲什么", "主要讲", "主要内容", "内容是什么",
        "关于什么", "是关于", "介绍", "概述", "总结", "概括", "综述",
        "整体", "总体", "全面", "综合", "整个", "主题", "主旨",
        "说的是什么", "写的是什么", "描述的是什么",
        "这本书", "这篇文章", "这份文档", "这个知识库", "此知识库",
        "有哪些", "都有什么", "包含什么", "涉及什么", "涵盖",
    ]

    async def _rule_based_complexity(self, query: str) -> Dict[str, Any]:
        """鍩轰簬瑙勫垯鐨勫鏉傚害鍒嗙被"""
        # 绠€鍗曠殑瑙勫垯鍒嗙被
        query_lower = query.lower()
        
        # zero-hop 瑙勫垯
        if any(word in query_lower for word in ["what is", "define", "explain", "describe"]):
            if len(query.split()) <= 5:
                complexity = "zero_hop"
            else:
                complexity = "one_hop"
        # multi-hop 瑙勫垯
        elif any(word in query_lower for word in ["compare", "relationship", "difference", "similarity", "how does", "why does"]):
            complexity = "multi_hop"
        # multi-hop 规则（中文概述/元问题）
        elif any(kw in query for kw in self._GLOBAL_CN_KEYWORDS):
            complexity = "multi_hop"
        else:
            complexity = "one_hop"
        
        self._complexity_stats[complexity] += 1
        self._complexity_stats["fallback"] += 1
        
        candidate_modes = self._complexity_to_candidate.get(complexity, ["naive"])
        
        return {
            "complexity": complexity,
            "confidence": 0.5,  # 瑙勫垯鍒嗙被鐨勭疆淇″害杈冧綆
            "probabilities": {},
            "candidate_modes": candidate_modes,
            "method": "rule_based"
        }
    
    async def route(self, query: str, available_modes: List[str] = None) -> str:
        """璺敱鏌ヨ鍒版渶浣虫绱㈡ā寮?"""
        if not available_modes:
            available_modes = ["llm_only", "naive", "bm25", "local", "global", "global_local"]
        
        # 棰勬祴澶嶆潅搴?
        complexity_result = await self.predict_complexity_detailed(query)
        complexity = complexity_result["complexity"]
        confidence = complexity_result["confidence"]
        
        # 鑾峰彇鍊欓€夋ā寮?
        candidate_modes = complexity_result["candidate_modes"]
        
        # 浠庡€欓€夋ā寮忎腑閫夋嫨鍙敤鐨勬ā寮?
        available_candidates = [mode for mode in candidate_modes if mode in available_modes]
        
        if not available_candidates:
            # 濡傛灉娌℃湁鍙敤鐨勫€欓€夋ā寮忥紝浣跨敤绗竴涓彲鐢ㄦā寮?
            logger.warning(f"澶嶆潅搴?{complexity} 鐨勫€欓€夋ā寮?{candidate_modes} 閮戒笉鍙敤锛屼娇鐢?{available_modes[0]}")
            return available_modes[0]
        
        # 濡傛灉缃俊搴︿綆浜庨槇鍊间笖鍚敤浜嗗洖閫€锛屼娇鐢ㄨ鍒欏垎绫?
        if confidence < self.confidence_threshold and self.enable_fallback:
            logger.info(f"缃俊搴?{confidence:.3f} 浣庝簬闃堝€?{self.confidence_threshold}锛屼娇鐢ㄨ鍒欏洖閫€")
            fallback_result = await self._rule_based_complexity(query)
            fallback_candidates = [mode for mode in fallback_result["candidate_modes"] if mode in available_modes]
            if fallback_candidates:
                return fallback_candidates[0]
        
        # 杩斿洖绗竴涓彲鐢ㄧ殑鍊欓€夋ā寮?
        selected_mode = available_candidates[0]
        logger.info(f"鏌ヨ澶嶆潅搴? {complexity}, 缃俊搴? {confidence:.3f}, 閫夋嫨妯″紡: {selected_mode}")
        
        return selected_mode
    
    def create_query_param(self, query: str, available_modes: List[str] = None, **kwargs) -> Any:
        """鍒涘缓鏌ヨ鍙傛暟"""
        from ..base import QueryParam
        
        # 鍚屾璺敱 - 浼樺厛浣跨敤璁粌濂界殑鍒嗙被鍣?
        try:
            # 棣栧厛灏濊瘯浣跨敤璁粌濂界殑ModernBERT鍒嗙被鍣?
            if self.classifier and self.classifier.is_available():
                try:
                    # 浣跨敤鍚屾鏂瑰紡璋冪敤鍒嗙被鍣?
                    complexity, confidence, probabilities = self.classifier.predict_with_confidence(query)
                    
                    # 鏇存柊缁熻
                    self._complexity_stats[complexity] += 1
                    
                    # 鑾峰彇鍊欓€夋ā寮?
                    candidate_modes = self._complexity_to_candidate.get(complexity, ["naive"])
                    
                    logger.info(f"ModernBERT鍒嗙被鍣ㄩ娴?- 澶嶆潅搴? {complexity}, 缃俊搴? {confidence:.3f}")
                    
                except Exception as e:
                    logger.warning(f"ModernBERT鍒嗙被鍣ㄩ娴嬪け璐ワ紝浣跨敤瑙勫垯鍒嗙被: {e}")
                    complexity_result = self._rule_based_complexity_sync(query)
                    complexity = complexity_result["complexity"]
                    candidate_modes = complexity_result["candidate_modes"]
                    confidence = complexity_result["confidence"]
            else:
                # 浣跨敤瑙勫垯鍒嗙被
                complexity_result = self._rule_based_complexity_sync(query)
                complexity = complexity_result["complexity"]
                candidate_modes = complexity_result["candidate_modes"]
                confidence = complexity_result["confidence"]
            
            # 浠庡€欓€夋ā寮忎腑閫夋嫨鍙敤鐨勬ā寮?
            if not available_modes:
                available_modes = ["llm_only", "naive", "bm25", "local", "global", "global_local"]
            
            available_candidates = [mode for mode in candidate_modes if mode in available_modes]
            
            if not available_candidates:
                # 濡傛灉娌℃湁鍙敤鐨勫€欓€夋ā寮忥紝浣跨敤绗竴涓彲鐢ㄦā寮?
                logger.warning(f"澶嶆潅搴?{complexity} 鐨勫€欓€夋ā寮?{candidate_modes} 閮戒笉鍙敤锛屼娇鐢?{available_modes[0]}")
                selected_mode = available_modes[0]
            else:
                selected_mode = available_candidates[0]
                
            logger.info(f"鍚屾璺敱 - 鏌ヨ澶嶆潅搴? {complexity}, 缃俊搴? {confidence:.3f}, 閫夋嫨妯″紡: {selected_mode}")
            
        except Exception as e:
            logger.warning(f"鍚屾璺敱澶辫触锛屼娇鐢ㄩ粯璁ゆā寮? {e}")
            selected_mode = "naive" if not available_modes else available_modes[0]
        
        return QueryParam(
            mode=selected_mode,
            **kwargs
        )
    
    def _rule_based_complexity_sync(self, query: str) -> Dict[str, Any]:
        """鍩轰簬瑙勫垯鐨勫鏉傚害鍒嗙被锛堝悓姝ョ増鏈級"""
        # 绠€鍗曠殑瑙勫垯鍒嗙被
        query_lower = query.lower()
        
        # zero-hop 瑙勫垯
        if any(word in query_lower for word in ["what is", "define", "explain", "describe"]):
            if len(query.split()) <= 5:
                complexity = "zero_hop"
            else:
                complexity = "one_hop"
        # multi-hop 瑙勫垯
        elif any(word in query_lower for word in ["compare", "relationship", "difference", "similarity", "how does", "why does"]):
            complexity = "multi_hop"
        # multi-hop 规则（中文概述/元问题）
        elif any(kw in query for kw in self._GLOBAL_CN_KEYWORDS):
            complexity = "multi_hop"
        else:
            complexity = "one_hop"
        
        self._complexity_stats[complexity] += 1
        self._complexity_stats["fallback"] += 1
        
        candidate_modes = self._complexity_to_candidate.get(complexity, ["naive"])
        
        return {
            "complexity": complexity,
            "confidence": 0.5,  # 瑙勫垯鍒嗙被鐨勭疆淇″害杈冧綆
            "probabilities": {},
            "candidate_modes": candidate_modes,
            "method": "rule_based_sync"
        }
    
    def get_complexity_stats(self) -> Dict[str, int]:
        """鑾峰彇澶嶆潅搴︾粺璁′俊鎭?"""
        return self._complexity_stats.copy()
    
    def reset_stats(self):
        """閲嶇疆缁熻淇℃伅"""
        self._complexity_stats = {
            "zero_hop": 0,
            "one_hop": 0,
            "multi_hop": 0,
            "fallback": 0
        }
    
    def get_retrieval_plan(self, complexity_result: Dict[str, Any], available_modes: List[str] = None, query: str = "") -> List[str]:
        """
        鍩轰簬缃俊搴﹀拰澶嶆潅搴︽鐜囧垎甯冪敓鎴愭绱㈣鍒?
        
        瀹炵幇涓夊眰娓愯繘寮忔绱㈢瓥鐣ワ細
        - 绛栫暐A锛氶珮缃俊搴﹀崟璺緞锛坈onfidence >= 0.9锛?
        - 绛栫暐B锛氫腑绛夌疆淇″害鍙岃矾寰勶紙0.6 <= confidence < 0.9锛?
        - 绛栫暐C锛氫綆缃俊搴﹀璺緞锛坈onfidence < 0.6锛?
        
        Args:
            complexity_result: 澶嶆潅搴﹀垎鏋愮粨鏋?
            available_modes: 鍙敤鐨勬绱㈡ā寮?
            
        Returns:
            閫夋嫨鐨勬绱㈡ā寮忓垪琛?
        """
        if not available_modes:
            available_modes = ["llm_only", "naive", "bm25", "local", "global", "global_local"]
        
        confidence = complexity_result.get("confidence", 0.5)
        probabilities = complexity_result.get("probabilities", {})
        
        if confidence >= 0.9:
            # 绛栫暐A锛氶珮缃俊搴﹀崟璺緞
            return self._get_optimal_mode(complexity_result, available_modes)
        elif confidence >= 0.6:
            # 绛栫暐B锛氫腑绛夌疆淇″害鍙岃矾寰?
            return self._get_dual_modes_robust(complexity_result, available_modes)
        else:
            # 绛栫暐C锛氫綆缃俊搴﹀璺緞
            return self._get_multi_modes_with_global_strategy(complexity_result, available_modes, query=query)
    
    def _get_optimal_mode(self, complexity_result: Dict[str, Any], available_modes: List[str]) -> List[str]:
        """鑾峰彇鏈€浼樺崟涓€妯″紡锛堢瓥鐣锛?"""
        complexity = complexity_result.get("complexity", "one_hop")
        candidate_modes = self._complexity_to_candidate.get(complexity, ["naive"])
        
        # 浠庡€欓€夋ā寮忎腑閫夋嫨绗竴涓彲鐢ㄧ殑妯″紡
        for mode in candidate_modes:
            if mode in available_modes:
                logger.info(f"绛栫暐A - 楂樼疆淇″害鍗曡矾寰? {mode}")
                return [mode]
        
        # 濡傛灉娌℃湁鍙敤鐨勫€欓€夋ā寮忥紝杩斿洖绗竴涓彲鐢ㄦā寮?
        logger.warning(f"鍊欓€夋ā寮?{candidate_modes} 閮戒笉鍙敤锛屼娇鐢?{available_modes[0]}")
        return [available_modes[0]] if available_modes else []
    
    def _get_dual_modes_robust(self, complexity_result: Dict[str, Any], available_modes: List[str]) -> List[str]:
        """
        椴佹鐨勫弻璺緞閫夋嫨锛岀‘淇濋€夋嫨涓嶅悓绫诲瀷鐨勬绱㈠櫒锛堢瓥鐣锛?
        
        Args:
            complexity_result: 澶嶆潅搴﹀垎鏋愮粨鏋?
            available_modes: 鍙敤鐨勬绱㈡ā寮?
            
        Returns:
            閫夋嫨鐨勫弻璺緞妫€绱㈡ā寮忓垪琛?
        """
        probabilities = complexity_result.get("probabilities", {})
        complexity = complexity_result.get("complexity", "one_hop")
        
        # 瀹氫箟浜掕ˉ鎬ф槧灏?- 纭繚閫夋嫨鐨勬绱㈠櫒鍏锋湁涓嶅悓鐨勪紭鍔?
        complementary_map = {
            "naive": ["bm25", "local"],      # 鍚戦噺妫€绱?鈫?鍏抽敭璇嶆绱㈡垨鍥炬绱?
            "bm25": ["naive", "local"],      # 鍏抽敭璇嶆绱?鈫?鍚戦噺妫€绱㈡垨鍥炬绱?
            "local": ["naive", "global"],    # 灞€閮ㄥ浘妫€绱?鈫?鍚戦噺妫€绱㈡垨鍏ㄥ眬鍥炬绱?
            "global": ["local", "naive"],    # 鍏ㄥ眬鍥炬绱?鈫?灞€閮ㄥ浘妫€绱㈡垨鍚戦噺妫€绱?
            "llm_only": ["naive", "bm25"]    # 绾敓鎴?鈫?浠讳綍妫€绱?
        }
        
        selected_modes = []
        
        # 浼樺厛閫夋嫨涓诲鏉傚害瀵瑰簲鐨勭涓€涓绱㈠櫒
        primary_candidates = self._complexity_to_candidate.get(complexity, ["naive"])
        primary_mode = None
        
        for mode in primary_candidates:
            if mode in available_modes:
                primary_mode = mode
                selected_modes.append(mode)
                break
        
        # 閫夋嫨浜掕ˉ鐨勭浜屼釜妫€绱㈠櫒
        if primary_mode and primary_mode in complementary_map:
            for complementary_mode in complementary_map[primary_mode]:
                if complementary_mode in available_modes and complementary_mode not in selected_modes:
                    selected_modes.append(complementary_mode)
                    break
        
        # 濡傛灉杩樻病鏈変袱涓绱㈠櫒锛屼娇鐢ㄥ鐢ㄧ瓥鐣?
        if len(selected_modes) < 2:
            # 鏍规嵁姒傜巼鍒嗗竷閫夋嫨绗簩楂樻鐜囩殑澶嶆潅搴﹀搴旂殑妫€绱㈠櫒
            sorted_complexities = sorted(probabilities.items(), key=lambda x: x[1], reverse=True)
            for comp, prob in sorted_complexities:
                if comp != complexity:  # 璺宠繃宸插鐞嗙殑涓诲鏉傚害
                    secondary_candidates = self._complexity_to_candidate.get(comp, [])
                    for mode in secondary_candidates:
                        if mode in available_modes and mode not in selected_modes:
                            # 妫€鏌ョ被鍨嬫槸鍚︿笉鍚?
                            if not selected_modes or self._get_retriever_type(mode) != self._get_retriever_type(selected_modes[0]):
                                selected_modes.append(mode)
                                break
                if len(selected_modes) >= 2:
                    break
        
        # 鏈€缁堝悗澶囷細浣跨敤棰勫畾涔夌殑澶氭牱鍖栫粍鍚?
        if len(selected_modes) < 2:
            backup_modes = self._get_diverse_retriever_combination(available_modes)
            selected_modes.extend(backup_modes[:2-len(selected_modes)])
        
        logger.info(f"绛栫暐B - 涓瓑缃俊搴﹀弻璺緞: {selected_modes[:2]}")
        return selected_modes[:2]
    
    def _get_retriever_type(self, mode: str) -> str:
        """鑾峰彇妫€绱㈠櫒绫诲瀷鐢ㄤ簬澶氭牱鎬ф鏌?"""
        type_mapping = {
            "naive": "vector",
            "bm25": "keyword", 
            "local": "graph_local",
            "global": "graph_global",
            "global_local": "graph_hybrid",
            "llm_only": "generation"
        }
        return type_mapping.get(mode, "unknown")
    
    def _get_diverse_retriever_combination(self, available_modes: List[str]) -> List[str]:
        """鑾峰彇澶氭牱鍖栫殑妫€绱㈠櫒缁勫悎"""
        # 鎸変紭鍏堢骇鎺掑簭鐨勫鏍峰寲缁勫悎
        preferred_combinations = [
            ["naive", "bm25"],      # 鍚戦噺 + 鍏抽敭璇?
            ["naive", "local"],     # 鍚戦噺 + 鍥?
            ["bm25", "local"],      # 鍏抽敭璇?+ 鍥?
            ["local", "global"],    # 鏈湴鍥?+ 鍏ㄥ眬鍥?
        ]
        
        for combination in preferred_combinations:
            available_combination = [mode for mode in combination if mode in available_modes]
            if len(available_combination) >= 2:
                return available_combination
        
        # 濡傛灉娌℃湁鐞嗘兂缁勫悎锛岃繑鍥炲墠涓や釜鍙敤妯″紡
        return available_modes[:2] if len(available_modes) >= 2 else available_modes
    
    def _get_multi_modes_with_global_strategy(self, complexity_result: Dict[str, Any], available_modes: List[str], query: str = "") -> List[str]:
        """
        甯lobal绛栫暐鐨勫璺緞閫夋嫨锛堢瓥鐣锛?
        
        Args:
            complexity_result: 澶嶆潅搴﹀垎鏋愮粨鏋?
            available_modes: 鍙敤鐨勬绱㈡ā寮?
            
        Returns:
            閫夋嫨鐨勫璺緞妫€绱㈡ā寮忓垪琛?
        """
        # 鍩虹涓夎矾寰勶細鍚戦噺銆佸叧閿瘝銆佸浘
        base_modes = ["naive", "bm25", "local"]
        selected_modes = [mode for mode in base_modes if mode in available_modes]
        
        # Global妫€绱㈠喅绛?
        should_use_global = self._should_trigger_global_retrieval(complexity_result, query=query)
        
        if should_use_global and "global" in available_modes:
            # 绛栫暐锛氱敤global鏇挎崲local锛堥伩鍏嶅浘妫€绱㈤噸澶嶏紝鍥犱负global鍖呭惈local淇℃伅锛?
            if "local" in selected_modes:
                selected_modes.remove("local")
            selected_modes.append("global")
        
        logger.info(f"绛栫暐C - 浣庣疆淇″害澶氳矾寰? {selected_modes}")
        return selected_modes
    
    def _should_trigger_global_retrieval(self, complexity_result: Dict[str, Any], query: str = None) -> bool:
        """
        Global妫€绱㈢殑鏄庣‘瑙﹀彂绛栫暐
        
        鏍规嵁璁烘枃瑕佹眰锛屽湪浠ヤ笅鍦烘櫙瑙﹀彂Global妫€绱細
        1. 澶氳烦鏌ヨ锛堥珮姒傜巼锛?
        2. 浣庣疆淇″害澶嶆潅鏌ヨ
        3. 闇€瑕佸叏灞€瑙嗚鐨勬煡璇?
        
        Args:
            complexity_result: 澶嶆潅搴﹀垎鏋愮粨鏋?
            query: 鏌ヨ鏂囨湰锛堝彲閫夌殑鍚彂寮忔鏌ワ級
            
        Returns:
            鏄惁搴旇瑙﹀彂Global妫€绱?
        """
        probabilities = complexity_result.get("probabilities", {})
        
        # 瀹夊叏鑾峰彇姒傜巼鍊硷紝澶勭悊绌哄瓧鍏稿拰缂哄け閿?
        multi_hop_prob = float(probabilities.get("multi_hop", 0) or 0)
        one_hop_prob = float(probabilities.get("one_hop", 0) or 0)
        zero_hop_prob = float(probabilities.get("zero_hop", 0) or 0)
        confidence = float(complexity_result.get("confidence", 0.5) or 0.5)
        complexity = complexity_result.get("complexity", "one_hop")
        
        # 瑙﹀彂鏉′欢1锛氭槑纭殑澶氳烦鏌ヨ
        if complexity == "multi_hop" and confidence > 0.5:
            logger.debug("Global trigger condition #1 matched: explicit multi-hop query.")
            return True
        
        # 瑙﹀彂鏉′欢2锛氬璺虫鐜囬珮浣嗙疆淇″害涓瓑锛堝彲鑳界殑澶氳烦鏌ヨ锛?
        if multi_hop_prob > 0.4 and confidence < 0.7:
            logger.debug("Global trigger condition #2 matched: likely multi-hop query.")
            return True
        
        # 瑙﹀彂鏉′欢3锛氶珮搴︿笉纭畾鐨勫鏉傛煡璇紙姒傜巼鍒嗗竷骞冲潶锛?
        # 娣诲姞绌哄€兼鏌ュ拰鏁板€肩ǔ瀹氭€у鐞?
        if probabilities and len(probabilities) > 0:
            # 杩囨护鏈夋晥姒傜巼鍊硷紙澶т簬0锛?
            valid_probs = [p for p in probabilities.values() if p is not None and p > 0]
            
            if len(valid_probs) > 1:
                # 璁＄畻姒傜巼鍒嗗竷鐨勭喌锛屼娇鐢ㄦ暟鍊肩ǔ瀹氱殑鏂瑰紡
                entropy = 0.0
                for p in valid_probs:
                    if p > 1e-10:  # 閬垮厤log(0)
                        entropy -= p * math.log(p)
                
                # 涓夌被鍧囧寑鍒嗗竷鐨勬渶澶х喌
                max_entropy = math.log(len(valid_probs)) if len(valid_probs) > 1 else 1.0
                normalized_entropy = entropy / max_entropy if max_entropy > 0 else 0.0
                
                if normalized_entropy > 0.8 and confidence < 0.6:
                    logger.debug(
                        f"Global trigger condition #3 matched: high entropy ({normalized_entropy:.2f})."
                    )
                    return True
        
        # 瑙﹀彂鏉′欢4锛氭煡璇㈠寘鍚渶瑕佸叏灞€鐞嗚В鐨勫叧閿瘝
        if query:
            # 鎵╁睍鐨勫叏灞€鎬у叧閿瘝鍒楄〃
            global_keywords = [
                # 鑻辨枃鍏抽敭璇?
                "overall", "summary", "general", "across", "comprehensive",
                "compare", "relationship", "between", "among", "throughout",
                # 涓枃鍏抽敭璇?
                "鎬讳綋", "鎬荤粨", "鍏ㄩ潰", "缁煎悎", "鏁翠綋",
                "姣旇緝", "鍏崇郴", "涔嬮棿", "鐩镐簰", "鑱旂郴"
            ]
            
            query_lower = query.lower()
            if any(keyword in query_lower for keyword in global_keywords):
                logger.debug("Global瑙﹀彂鏉′欢4: 鍖呭惈鍏ㄥ眬鎬у叧閿瘝")
                return True
        
        # 瑙﹀彂鏉′欢5锛氬崟璺冲拰澶氳烦姒傜巼鎺ヨ繎锛堣竟鐣屾儏鍐碉級
        if abs(one_hop_prob - multi_hop_prob) < 0.1 and multi_hop_prob > 0.3:
            logger.debug("Global瑙﹀彂鏉′欢5: 鍗曡烦/澶氳烦杈圭晫鎯呭喌")
            return True
        
        return False
