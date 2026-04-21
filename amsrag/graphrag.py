"""
Enhanced GraphRAG System
闆嗘垚鐜颁唬璇勪及鍣ㄣ€佸鏉傚害鎰熺煡璺敱涓庝紶缁熻瀺鍚堢瓥鐣ワ紝閫傞厤鏈鐢熼」鐩殑瀹為檯闇€姹傦紝淇濇寔楂樻€ц兘鍜屽彲鐢ㄦ€?
"""

import os
import asyncio
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Type, Union, List, Dict, Any, Optional, Callable

import tiktoken

from ._utils import (
    logger,
    always_get_an_event_loop,
    limit_async_func_call,
    convert_response_to_json,
    compute_mdhash_id,
)

# 鏍稿績瀛樺偍鍜屽鐞嗘ā鍧?
from .base import (
    BaseVectorStorage,
    BaseKVStorage, 
    BaseGraphStorage,
    QueryParam,
    CommunitySchema,
    TextChunkSchema,
    StorageNameSpace,
)

# 鏁版嵁澶勭悊妯″潡
from .chunking import get_chunks, chunking_by_token_size
from .entity_extraction import extract_entities
from .community import generate_community_report

# 鏌ヨ澶勭悊妯″潡
from .query_processing import local_query, global_query, global_local_query, naive_query

# 瀛樺偍瀹炵幇
from ._storage import JsonKVStorage, NetworkXStorage, SimpleVectorDBStorage, FAISSVectorStorage
from ._storage.other.bm25 import BM25Storage  # 鏂板锛欱M25 瀛樺偍鍚庣

# LLM鍜屽祵鍏ュ嚱鏁?
from ._llm import (
    gpt_4o_complete,
    gpt_4o_mini_complete,
    openai_embedding,
    azure_gpt_4o_complete,
    azure_gpt_4o_mini_complete,
    azure_openai_embedding,
    amazon_bedrock_embedding,
    create_amazon_bedrock_complete_function,
    qwen_turbo_complete,
    siliconflow_embedding,
)

from .complexity.router import ComplexityAwareRouter
from .retrieval import ConfidenceAwareFusion, FusionConfig, create_fusion_engine
from .retrieval.similarity import SimilarityMethod


@dataclass
class EnhancedGraphRAG:
    
    # 鍩虹閰嶇疆
    working_dir: str = field(
        # Windows 璺緞涓嶅厑璁稿啋鍙凤紝缁熶竴浣跨敤鏃犲啋鍙风殑鏃堕棿鏍煎紡
        default_factory=lambda: f"./amsrag_cache_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    
    # 妯″紡鎺у埗
    enable_local: bool = True
    enable_naive_rag: bool = True  # 榛樿鍚敤锛屽鍔犵伒娲绘€?
    enable_bm25: bool = False  # 鏂板锛氭槸鍚﹀惎鐢?BM25 妫€绱?
    enable_enhanced_features: bool = True  # 鏄惁鍚敤澧炲己鍔熻兘
    
    # 鏂囨湰鍒嗗潡閰嶇疆
    chunk_func: Callable = chunking_by_token_size
    chunk_token_size: int = 1200
    chunk_overlap_token_size: int = 100
    tiktoken_model_name: str = "gpt-4o"
    
    # 瀹炰綋鎻愬彇閰嶇疆
    entity_extract_max_gleaning: int = 1
    entity_summary_to_max_tokens: int = 500
    
    # 鍥捐仛绫婚厤缃?
    graph_cluster_algorithm: str = "leiden"
    max_graph_cluster_size: int = 10
    graph_cluster_seed: int = 0xDEADBEEF
    
    # 鑺傜偣宓屽叆閰嶇疆锛堜繚鐣欏吋瀹规€э級
    node_embedding_algorithm: str = "node2vec"
    node2vec_params: dict = field(
        default_factory=lambda: {
            "dimensions": 1536,
            "num_walks": 10,
            "walk_length": 40,
            "window_size": 2,
            "iterations": 3,
            "random_seed": 3,
        }
    )
    
    # 绀惧尯鎶ュ憡閰嶇疆
    special_community_report_llm_kwargs: dict = field(
        default_factory=lambda: {"response_format": {"type": "json_object"}}
    )
    
    # 宓屽叆閰嶇疆锛堥粯璁や娇鐢ㄧ鍩烘祦鍔?BGE-M3锛?
    embedding_func: Callable = field(default_factory=lambda: siliconflow_embedding)
    embedding_batch_num: int = 32
    embedding_func_max_async: int = 16
    query_better_than_threshold: float = 0.2
    
    # LLM閰嶇疆
    using_azure_openai: bool = False
    using_amazon_bedrock: bool = False
    best_model_id: str = "us.anthropic.claude-3-sonnet-20240229-v1:0"
    cheap_model_id: str = "us.anthropic.claude-3-haiku-20240307-v1:0"
    best_model_func: callable = gpt_4o_complete
    best_model_max_token_size: int = 32768
    best_model_max_async: int = 16
    cheap_model_func: callable = gpt_4o_mini_complete
    cheap_model_max_token_size: int = 32768
    cheap_model_max_async: int = 16
    answer_stream_callback: Optional[Callable[[str], Any]] = None
    
    # 瀹炰綋鎻愬彇鍑芥暟
    entity_extraction_func: callable = extract_entities
    
    # DSPy瀹炰綋鎻愬彇閰嶇疆
    use_compiled_dspy_entity_relationship: bool = False  # 绂佺敤缂栬瘧妯″瀷閬垮厤瀛楁鍐茬獊
    
    # 瀛樺偍閰嶇疆
    key_string_value_json_storage_cls: Type[BaseKVStorage] = JsonKVStorage
    vector_db_storage_cls: Type[BaseVectorStorage] = FAISSVectorStorage  # v0.6.0: 榛樿浣跨敤FAISS锛堟€ц兘鎻愬崌6.7鍊嶏級
    vector_db_storage_cls_kwargs: dict = field(default_factory=dict)
    graph_storage_cls: Type[BaseGraphStorage] = NetworkXStorage
    enable_llm_cache: bool = True
    # 杩愯鏃跺瓨鍌ㄥ疄渚嬶紙鏂板锛欱M25锛?
    bm25_storage: Optional[BM25Storage] = None
    
    # 澧炲己鍔熻兘閰嶇疆 - 璇勪及鍣?
    enable_modern_evaluator: bool = True  # 鍚敤璇勪及鍣?
    evaluator_config: Optional[Dict[str, Any]] = None  # 璇勪及鍣ㄩ厤缃?

    # RRF缃俊搴︽劅鐭ヨ瀺鍚堥厤缃?
    fusion_config: Optional[FusionConfig] = None  # RRF铻嶅悎閰嶇疆
    
    # 娑堣瀺瀹為獙寮€鍏筹紙Signal-level Ablation锛?
    ablation_routing_adaptive: bool = True      # 鏄惁鍚敤鑷€傚簲璺敱锛堢瓥鐣/B/C锛?
    ablation_fusion_ca: bool = True             # 鏄惁鍚敤CA-RRF锛堢疆淇″害鎰熺煡铻嶅悎锛?
    ablation_diversity_mmr: bool = True         # 鏄惁鍚敤MMR澶氭牱鎬х害鏉?
    enable_confidence_fusion: bool = True  # 鏄惁鍚敤缃俊搴︽劅鐭ヨ瀺鍚?
    rrf_k: float = 60.0  # RRF骞虫粦鍙傛暟
    fusion_max_results: int = 20  # 铻嶅悎鏈€澶х粨鏋滄暟
    
    # 娓愯繘寮忔绱㈤厤缃?
    confidence_high_threshold: float = 0.9  # 楂樼疆淇″害闃堝€硷紙绛栫暐A锛?
    confidence_medium_threshold: float = 0.6  # 涓瓑缃俊搴﹂槇鍊硷紙绛栫暐B锛?
    max_parallel_retrievers: int = 4  # 鏈€澶у苟琛屾绱㈠櫒鏁伴噺
    retrieval_timeout_seconds: float = 30.0  # 妫€绱㈣秴鏃舵椂闂达紙绉掞級
    
    # 妫€绱㈠櫒浼樺厛绾ч厤缃?
    retriever_priority_weights: Dict[str, float] = field(default_factory=lambda: {
        "global": 1.0,    # 鍏ㄥ眬鍥炬绱㈡潈閲?
        "local": 0.9,     # 灞€閮ㄥ浘妫€绱㈡潈閲?
        "naive": 0.8,     # 鍚戦噺妫€绱㈡潈閲?
        "bm25": 0.7,      # BM25妫€绱㈡潈閲?
        "llm_only": 0.6   # 绾疞LM鏉冮噸
    })
    
    # 鎵╁睍閰嶇疆
    always_create_working_dir: bool = True
    addon_params: dict = field(default_factory=dict)
    convert_response_to_json_func: callable = convert_response_to_json

    # 娣峰悎妫€绱?璺敱锛堜笌 Hybrid 鎵╁睍鍏煎鐨勫崰浣嶅睘鎬э級
    router_cls: type = ComplexityAwareRouter  # 渚涙墿灞曠被妫€鏌?
    router_kwargs: dict = field(default_factory=dict)  # 渚涙墿灞曠被澶嶅埗骞惰鐩?
    model_path: str = field(default_factory=lambda: os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "models", "modernbert_complexity_classifier_standard"
    ))

    def __post_init__(self):

        _print_config = ",\n  ".join([f"{k} = {v}" for k, v in asdict(self).items()])
        logger.debug(f"Enhanced GraphRAG init with param:\n\n  {_print_config}\n")

        # 閰嶇疆LLM鎻愪緵鍟?
        self._setup_llm_providers()
        
        # 鍒涘缓宸ヤ綔鐩綍
        self._setup_working_directory()
        
        # 鍒濆鍖栧瓨鍌ㄧ粍浠?
        self._setup_storage_components()
        
        # 鍒濆鍖朙LM鍜屽祵鍏ュ嚱鏁?
        self._setup_llm_and_embedding()
        
        # 鍒濆鍖栧寮哄姛鑳芥ā鍧?
        if self.enable_enhanced_features:
            self._setup_enhanced_modules()
    
    def _setup_llm_providers(self):
        """璁剧疆LLM鎻愪緵鍟?"""
        if self.using_azure_openai:
            if self.best_model_func == gpt_4o_complete:
                self.best_model_func = azure_gpt_4o_complete
            if self.cheap_model_func == gpt_4o_mini_complete:
                self.cheap_model_func = azure_gpt_4o_mini_complete
            if self.embedding_func == openai_embedding:
                self.embedding_func = azure_openai_embedding
            logger.info("Switched to Azure OpenAI")

        if self.using_amazon_bedrock:
            self.best_model_func = create_amazon_bedrock_complete_function(self.best_model_id)
            self.cheap_model_func = create_amazon_bedrock_complete_function(self.cheap_model_id)
            self.embedding_func = amazon_bedrock_embedding
            logger.info("Switched to Amazon Bedrock")

        # DashScope/OpenAI 鍏煎绔偣澶勭悊
        # 1) 妫€娴?DashScope 绔偣鏃讹紝绉婚櫎浼氬鑷?JSON mode 鐨勫弬鏁?
        # 2) 鑻ユ娴嬪埌 DASHSCOPE_API_KEY锛屽垯灏嗙ぞ鍖烘姤鍛婄殑榛樿妯″瀷鍑芥暟鍒囧埌 qwen-turbo
        api_base = os.getenv("OPENAI_BASE_URL", "") or os.getenv("OPENAI_API_BASE", "")
        if "dashscope" in api_base.lower() or os.getenv("DASHSCOPE_API_KEY", ""):
            if isinstance(self.special_community_report_llm_kwargs, dict):
                self.special_community_report_llm_kwargs.pop("response_format", None)
            logger.info("Detected DashScope endpoint, removed response_format from community report kwargs.")
            # 鍒囨崲绀惧尯鎶ュ憡鍒?Qwen Turbo锛堣嫢浠嶆槸榛樿鐨?gpt_4o_complete锛?
            try:
                if self.best_model_func == gpt_4o_complete:
                    self.best_model_func = qwen_turbo_complete
                    logger.info("Switch community report LLM to qwen-turbo for DashScope.")
            except Exception:
                pass
    
    def _setup_working_directory(self):
        """璁剧疆宸ヤ綔鐩綍"""
        if not os.path.exists(self.working_dir) and self.always_create_working_dir:
            logger.info(f"Creating working directory {self.working_dir}")
            os.makedirs(self.working_dir)
    
    def _setup_storage_components(self):
        """璁剧疆瀛樺偍缁勪欢"""
        config_dict = asdict(self)
        
        self.full_docs = self.key_string_value_json_storage_cls(
            namespace="full_docs", global_config=config_dict
        )
        
        self.text_chunks = self.key_string_value_json_storage_cls(
            namespace="text_chunks", global_config=config_dict
        )
        
        self.llm_response_cache = (
            self.key_string_value_json_storage_cls(
                namespace="llm_response_cache", global_config=config_dict
            )
            if self.enable_llm_cache
            else None
        )
        
        self.community_reports = self.key_string_value_json_storage_cls(
            namespace="community_reports", global_config=config_dict
        )
        
        self.chunk_entity_relation_graph = self.graph_storage_cls(
            namespace="chunk_entity_relation", global_config=config_dict
        )

        # 鏂板锛氬垵濮嬪寲 BM25 瀛樺偍锛堝彲閫夛級
        if self.enable_bm25:
            try:
                self.bm25_storage = BM25Storage(namespace="bm25", global_config=config_dict)
                # 鍏煎鏃т唬鐮佸懡鍚嶏紙渚嬪 examples 涓娇鐢?bm25_store锛?
                setattr(self, "bm25_store", self.bm25_storage)
                logger.info("BM25 storage initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize BM25 storage: {e}")
                self.bm25_storage = None
                setattr(self, "bm25_store", None)
        else:
            self.bm25_storage = None
            setattr(self, "bm25_store", None)
    
    def _setup_llm_and_embedding(self):
        """璁剧疆LLM鍜屽祵鍏ュ嚱鏁?"""
        # 闄愬埗骞跺彂璋冪敤
        self.embedding_func = limit_async_func_call(self.embedding_func_max_async)(
            self.embedding_func
        )
        
        # 璁剧疆鍚戦噺鏁版嵁搴?
        self.entities_vdb = (
            self.vector_db_storage_cls(
                namespace="entities",
                global_config=asdict(self),
                embedding_func=self.embedding_func,
                meta_fields={"entity_name"},
            )
            if self.enable_local
            else None
        )
        
        self.chunks_vdb = (
            self.vector_db_storage_cls(
                namespace="chunks",
                global_config=asdict(self),
                embedding_func=self.embedding_func,
            )
            if self.enable_naive_rag
            else None
        )
        
        # 璁剧疆LLM鍑芥暟
        self.best_model_func = limit_async_func_call(self.best_model_max_async)(
            self.best_model_func
        )
        self.cheap_model_func = limit_async_func_call(self.cheap_model_max_async)(
            self.cheap_model_func
        )
    
    def _setup_enhanced_modules(self):
        """璁剧疆澧炲己鍔熻兘妯″潡"""
        try:
            # 璇勪及鍣ㄥ垵濮嬪寲
            if self.enable_modern_evaluator:
                try:
                    from .evaluation import RAGMetrics
                    
                    # 鍒涘缓璇勪及鍣ㄥ疄渚?
                    self.evaluator = RAGMetrics()
                    logger.info("璇勪及鍣ㄥ垵濮嬪寲鎴愬姛")
                        
                except Exception as e:
                    logger.warning(f"璇勪及鍣ㄥ垵濮嬪寲澶辫触: {e}")
                    self.evaluator = None
            else:
                self.evaluator = None
                logger.info("璇勪及鍣ㄥ凡绂佺敤")
            
            # Complexity Router锛堜娇鐢ㄦ纭殑妯″瀷璺緞锛?
            self.complexity_router = ComplexityAwareRouter(
                model_path=self.model_path
            )
            # 鍏煎锛氭毚闇查€氱敤鍚嶇О渚?Hybrid 鎵╁睍浣跨敤
            self.router = self.complexity_router
            logger.info("Complexity Router initialized successfully")
            
            # RRF缃俊搴︽劅鐭ヨ瀺鍚堝紩鎿庡垵濮嬪寲
            if self.enable_confidence_fusion:
                if self.fusion_config is None:
                    self.fusion_config = FusionConfig(
                        k=self.rrf_k,
                        max_results=self.fusion_max_results,
                        confidence_aware=True,
                        embedding_func=self.embedding_func,  # 浼犻€掑祵鍏ュ嚱鏁帮紒
                        similarity_method=SimilarityMethod.TFIDF,  # 榛樿浣跨敤TFIDF
                        enable_mmr=self.ablation_diversity_mmr  # 浼犻€扢MR寮€鍏筹紒
                    )
                
                self.fusion_engine = create_fusion_engine(
                    k=self.fusion_config.k,
                    max_results=self.fusion_config.max_results,
                    confidence_aware=self.fusion_config.confidence_aware,
                    embedding_func=self.embedding_func,  # 浼犻€掑祵鍏ュ嚱鏁帮紒
                    similarity_method=self.fusion_config.similarity_method,
                    enable_mmr=self.ablation_diversity_mmr  # 浼犻€扢MR寮€鍏筹紒
                )
                logger.info("鉁?RRF缃俊搴︽劅鐭ヨ瀺鍚堝紩鎿庡垵濮嬪寲鎴愬姛")
                logger.info(f"RRF鍙傛暟k: {self.fusion_config.k}")
                logger.info(f"鏈€澶х粨鏋滄暟: {self.fusion_config.max_results}")
                logger.info(
                    f"MMR enabled: {'yes' if self.ablation_diversity_mmr else 'no'}"
                )
                logger.info(
                    f"Embedding function configured: {'yes' if self.embedding_func else 'no'}"
                )
            else:
                self.fusion_engine = None
                logger.info("RRF fusion engine disabled")
            
        except Exception as e:
            logger.warning(f"Failed to initialize enhanced modules: {e}")
            logger.warning("Falling back to basic functionality")
            self.enable_enhanced_features = False

    def insert(self, string_or_strings):
        """鍚屾鎻掑叆鎺ュ彛"""
        loop = always_get_an_event_loop()
        return loop.run_until_complete(self.ainsert(string_or_strings))

    def query(self, query: str, param: QueryParam = QueryParam()):
        """鍚屾鏌ヨ鎺ュ彛"""
        loop = always_get_an_event_loop()
        return loop.run_until_complete(self.aquery(query, param))
    
    async def aquery(self, query: str, param: QueryParam = QueryParam(), return_timing: bool = False):
        """
        寮傛鏌ヨ鎺ュ彛 - 娓愯繘寮忓苟琛屾绱㈡灦鏋?
        
        瀹炵幇涓変釜闃舵鐨勫鐞嗘祦绋嬶細
        1. 澶嶆潅搴﹀拰缃俊搴﹀垎鏋?
        2. 娓愯繘寮忔绱㈢瓥鐣ユ墽琛?
        3. 鏅鸿兘铻嶅悎
        
        Args:
            query: 鏌ヨ鏂囨湰
            param: 鏌ヨ鍙傛暟
            return_timing: 鏄惁杩斿洖璇︾粏鐨勬椂闂翠俊鎭?
            
        Returns:
            濡傛灉return_timing=False: str (鍝嶅簲鏂囨湰)
            濡傛灉return_timing=True: dict {
                "response": str,
                "timing": {
                    "complexity_analysis": float,  # 澶嶆潅搴﹀垎鏋愭椂闂?ms)
                    "retrieval": float,            # 妫€绱㈡椂闂?ms)
                    "llm_generation": float,       # LLM鐢熸垚鏃堕棿(ms)
                    "total": float                 # 鎬绘椂闂?ms)
                }
            }
        """
        import time
        
        timing = {}
        start_total = time.time()
        evidence_results = []
        retrieval_summary = {
            "planned_modes": [],
            "raw_result_counts": {},
            "normalized_result_counts": {},
            "fusion_method": "none",
            "evidence_count": 0,
        }
        
        try:
            # 绗竴闃舵锛氬鏉傚害鍜岀疆淇″害鍒嗘瀽
            start_complexity = time.time()
            if self.enable_enhanced_features and hasattr(self, 'complexity_router'):
                complexity_result = await self.complexity_router.predict_complexity_detailed(query)
                logger.info(f"澶嶆潅搴﹀垎鏋? {complexity_result.get('complexity')}, 缃俊搴? {complexity_result.get('confidence', 0):.3f}")
                
                # 娑堣瀺瀹為獙锛氬鏋滅鐢ㄨ嚜閫傚簲璺敱锛岃鐩栦负鍥哄畾鍊?
                if not self.ablation_routing_adaptive:
                    logger.info("娑堣瀺瀹為獙锛氫娇鐢ㄥ浐瀹氬鏉傚害鍜岀疆淇″害")
                    complexity_result = {
                        "complexity": "one_hop",
                        "confidence": 0.5,
                        "probabilities": {"one_hop": 1.0},
                        "method": "fixed_for_ablation"
                    }
            else:
                # 鍥為€€鍒伴粯璁ゅ鏉傚害缁撴灉
                complexity_result = {
                    "complexity": "one_hop",
                    "confidence": 0.5,
                    "probabilities": {"one_hop": 1.0},
                    "method": "fallback"
                }
                logger.warning("澶嶆潅搴﹀垎鏋愬櫒涓嶅彲鐢紝浣跨敤榛樿閰嶇疆")
            timing["complexity_analysis"] = (time.time() - start_complexity) * 1000
            
            # 绗簩闃舵锛氭笎杩涘紡妫€绱㈢瓥鐣ユ墽琛?
            # 娑堣瀺瀹為獙锛氭牴鎹紑鍏冲喅瀹氫娇鐢ㄨ嚜閫傚簲璺敱杩樻槸鍥哄畾璺敱
            if self.ablation_routing_adaptive:
                retrieval_tasks = self._plan_retrieval_tasks(complexity_result, param, query=query)
                logger.info(f"浣跨敤鑷€傚簲璺敱锛岀瓥鐣? {retrieval_tasks}")
            else:
                retrieval_tasks = self._plan_fixed_retrieval_tasks(param)
                logger.info(f"浣跨敤鍥哄畾璺敱锛岀瓥鐣? {retrieval_tasks}")
            retrieval_summary["planned_modes"] = retrieval_tasks
            
            if not retrieval_tasks:
                # 绛栫暐A锛氱洿鎺LM鍥炵瓟锛堝綋妫€绱换鍔′负绌烘椂锛?
                logger.info("鎵ц绛栫暐A - 鐩存帴LLM鍥炵瓟")
                timing["retrieval"] = 0
                
                start_llm = time.time()
                response = await self._llm_only_response(query, param)
                timing["llm_generation"] = (time.time() - start_llm) * 1000
                
                await self._query_done()
                timing["total"] = (time.time() - start_total) * 1000
                
                if return_timing:
                    return {
                        "response": response,
                        "timing": timing,
                        "evidence": [],
                        "retrieval_summary": retrieval_summary,
                    }
                else:
                    return response
            
            # 骞惰鎵ц妫€绱换鍔★紙鏍规嵁澶嶆潅搴?缃俊搴﹁皟鏁存瘡涓绱㈠櫒鐨勮祫婧愯妯★級
            start_retrieval = time.time()
            retrieval_results = await self._execute_retrieval_tasks(
                retrieval_tasks, query, param, complexity_result
            )
            timing["retrieval"] = (time.time() - start_retrieval) * 1000
            retrieval_summary["raw_result_counts"] = {
                mode: (len(result) if isinstance(result, list) else int(bool(result)))
                for mode, result in retrieval_results.items()
            }
            # Global fallback: if every retriever returned nothing and local graph is
            # enabled, try global (community-report) retrieval as a last resort.
            _all_empty = all(
                (not r) or (isinstance(r, list) and len(r) == 0)
                or (isinstance(r, dict) and len(r) == 0)
                for r in retrieval_results.values()
            )
            if _all_empty and "global" not in retrieval_tasks and self.enable_local:
                logger.warning(
                    "All retrievers returned empty results - "
                    "falling back to global (community-report) retrieval"
                )
                try:
                    _fb_result = await self._execute_retrieval_tasks(
                        ["global"], query, param, complexity_result
                    )
                    if _fb_result.get("global"):
                        retrieval_results = _fb_result
                        retrieval_tasks = ["global"]
                        retrieval_summary["planned_modes"] = ["global"]
                        logger.info("Global fallback retrieval succeeded")
                except Exception as _fb_exc:
                    logger.error("Global fallback retrieval failed: %s", _fb_exc)
            
            # 绗笁闃舵锛氭櫤鑳借瀺鍚堬紙鍖呭惈LLM鐢熸垚锛?
            start_llm = time.time()
            # Defensive init: prevent UnboundLocalError if no retrieval branch assigns response
            from .answer_generation.prompts import PROMPTS as _PROMPTS_GUARD
            response = _PROMPTS_GUARD["fail_response"]
            if len(retrieval_results) == 1:
                # 鍗曚竴妫€绱㈢粨鏋滐紝鐩存帴澶勭悊
                mode, result = next(iter(retrieval_results.items()))
                if mode == "llm_only":
                    # llm_only杩斿洖瀛楃涓?                    response = result
                    retrieval_summary["fusion_method"] = "llm_only"
                else:
                    # 鍏朵粬妯″紡闇€瑕佽浆鎹负瀛楃涓插搷搴?                    response = await self._convert_retrieval_results_to_response(result, query, param)
                    evidence_results = self._extract_single_mode_evidence(result)
                    retrieval_summary["fusion_method"] = "single_mode"
                    retrieval_summary["normalized_result_counts"] = {
                        mode: len(evidence_results)
                    }
                logger.info(f"鍗曚竴妫€绱㈡ā寮忓畬鎴? {mode}")
            else:
                # 澶氭绱㈢粨鏋滐紝闇€瑕佽瀺鍚?                # 娑堣瀺瀹為獙锛氭牴鎹紑鍏冲喅瀹氫娇鐢–A-RRF杩樻槸vanilla RRF
                if self.ablation_fusion_ca:
                    fusion_result = await self._confidence_aware_fusion(
                        retrieval_results,
                        complexity_result,
                        query,
                        param,
                        return_details=True,
                    )
                    logger.info(f"浣跨敤CA-RRF铻嶅悎瀹屾垚: {list(retrieval_results.keys())}")
                    response = fusion_result["response"]
                else:
                    fusion_result = await self._vanilla_rrf_fusion(
                        retrieval_results,
                        query,
                        param,
                        return_details=True,
                    )
                    logger.info(f"浣跨敤vanilla RRF铻嶅悎瀹屾垚: {list(retrieval_results.keys())}")
                    response = fusion_result["response"]

                evidence_results = fusion_result.get("fused_results", [])
                retrieval_summary["normalized_result_counts"] = {
                    source: len(results)
                    for source, results in fusion_result.get("results_by_source", {}).items()
                }
                retrieval_summary["fusion_method"] = fusion_result.get(
                    "fusion_method",
                    "ca_rrf" if self.ablation_fusion_ca else "vanilla_rrf",
                )
            timing["llm_generation"] = (time.time() - start_llm) * 1000
            
            await self._query_done()
            timing["total"] = (time.time() - start_total) * 1000
            serialized_evidence = await self._serialize_evidence_results(evidence_results)
            retrieval_summary["evidence_count"] = len(serialized_evidence)
            
            if return_timing:
                return {
                    "response": response,
                    "timing": timing,
                    "evidence": serialized_evidence,
                    "retrieval_summary": retrieval_summary,
                }
            else:
                return response
            
        except Exception as e:
            logger.error(f"鏌ヨ澶勭悊澶辫触: {e}")
            # 鍥為€€鍒颁紶缁熷崟涓€妯″紡
            logger.info("鍥為€€鍒颁紶缁熷崟涓€妯″紡")
            
            start_fallback = time.time()
            response = await self._fallback_single_mode_query(query, param)
            
            await self._query_done()
            
            # 鍥為€€妯″紡鐨則iming
            timing["complexity_analysis"] = timing.get("complexity_analysis", 0)
            timing["retrieval"] = 0
            timing["llm_generation"] = (time.time() - start_fallback) * 1000
            timing["total"] = (time.time() - start_total) * 1000
            
            if return_timing:
                return {
                    "response": response,
                    "timing": timing,
                    "evidence": [],
                    "retrieval_summary": retrieval_summary,
                }
            else:
                return response

    def _extract_single_mode_evidence(self, retrieval_results) -> List[Any]:
        from .retrieval.alignment import RetrievalResult

        if isinstance(retrieval_results, list) and retrieval_results:
            return [result for result in retrieval_results if isinstance(result, RetrievalResult)]
        return []

    async def _serialize_evidence_results(
        self,
        evidence_results: List[Any],
        limit: int = 6,
        snippet_length: int = 280,
    ) -> List[Dict[str, Any]]:
        from .retrieval.alignment import RetrievalResult

        if not evidence_results:
            return []

        limited_results = [
            result for result in evidence_results[:limit] if isinstance(result, RetrievalResult)
        ]
        if not limited_results:
            return []

        chunk_ids = [
            result.chunk_id
            for result in limited_results
            if isinstance(result.chunk_id, str)
        ]
        chunk_payloads = []
        if chunk_ids and hasattr(self, "text_chunks") and self.text_chunks:
            try:
                chunk_payloads = await self.text_chunks.get_by_ids(chunk_ids)
            except Exception as exc:
                logger.warning(f"Failed to enrich evidence chunks: {exc}")
                chunk_payloads = []

        chunk_map = {}
        for index, chunk_id in enumerate(chunk_ids):
            payload = chunk_payloads[index] if index < len(chunk_payloads) else None
            if payload:
                chunk_map[chunk_id] = payload

        serialized = []
        for index, result in enumerate(limited_results, start=1):
            metadata = dict(result.metadata or {})
            chunk_payload = chunk_map.get(result.chunk_id, {})
            original_result = metadata.get("original_result", {})
            if not isinstance(original_result, dict):
                original_result = {}

            serialized.append(
                {
                    "index": index,
                    "source": result.source,
                    "chunk_id": result.chunk_id,
                    "doc_id": chunk_payload.get("full_doc_id")
                    or original_result.get("full_doc_id"),
                    "chunk_order_index": chunk_payload.get("chunk_order_index")
                    or original_result.get("chunk_order_index"),
                    "score": round(float(result.score), 6),
                    "rank": int(metadata.get("fusion_rank", result.rank)),
                    "rrf_score": round(float(metadata.get("rrf_score", 0.0)), 6),
                    "sources": metadata.get("sources", [result.source]),
                    "snippet": self._truncate_evidence_text(
                        result.content,
                        limit=snippet_length,
                    ),
                    "context_section": bool(metadata.get("context_section")),
                }
            )

        return serialized

    def _truncate_evidence_text(self, text: str, limit: int = 280) -> str:
        if not text:
            return ""
        normalized = " ".join(text.split()).strip()
        if len(normalized) <= limit:
            return normalized
        return f"{normalized[: max(limit - 3, 0)].rstrip()}..."
    
    async def _convert_retrieval_results_to_response(self, retrieval_results, query: str, param: QueryParam) -> str:
        """将检索结果转换为最终响应"""
        try:
            from .retrieval.alignment import RetrievalResult

            logger.info(
                f"[convert] type={type(retrieval_results).__name__}, "
                f"len={len(retrieval_results) if isinstance(retrieval_results, (list, dict)) else 'n/a'}"
            )

            if isinstance(retrieval_results, str):
                return retrieval_results
            elif isinstance(retrieval_results, list) and retrieval_results:
                first = retrieval_results[0]
                is_rr = isinstance(first, RetrievalResult)
                logger.info(f"[convert] first item type={type(first).__name__}, is_RetrievalResult={is_rr}")
                if is_rr:
                    context_parts = [r.content for r in retrieval_results if r.content]
                    logger.info(
                        f"[convert] context_parts={len(context_parts)} / {len(retrieval_results)}"
                    )
                    if not context_parts:
                        logger.warning("[convert] context_parts 为空，直接返回 fail_response（未调用 LLM）")
                        from .answer_generation.prompts import PROMPTS
                        return PROMPTS["fail_response"]

                    context = "\n\n".join(context_parts)
                    from .answer_generation.prompts import PROMPTS
                    sys_prompt_temp = PROMPTS.get(
                        "naive_rag_response",
                        "Please answer based on the context: {content_data}",
                    )
                    # 使用 replace 而非 format，避免 content 中含有 {} 导致格式化异常
                    sys_prompt = sys_prompt_temp.replace("{content_data}", context).replace(
                        "{response_type}", str(param.response_type or "多段落回答（中文）")
                    )

                    logger.info(
                        f"[convert] 调用 best_model_func, stream_callback={self.answer_stream_callback is not None}"
                    )
                    response = await self.best_model_func(
                        query,
                        system_prompt=sys_prompt,
                        stream_callback=self.answer_stream_callback,
                    )
                    logger.info(
                        f"[convert] LLM 返回: type={type(response).__name__}, "
                        f"len={len(response) if isinstance(response, str) else 'n/a'}, "
                        f"preview={repr(response[:80]) if isinstance(response, str) else response}"
                    )
                    if not response or (isinstance(response, str) and not response.strip()):
                        logger.warning("[convert] LLM 返回空响应，降级为 fail_response")
                        return PROMPTS["fail_response"]
                    return response
                else:
                    logger.warning(
                        f"[convert] 第一项不是 RetrievalResult 而是 {type(first).__name__}，转为字符串"
                    )
                    return str(first)
            else:
                logger.warning(
                    f"[convert] retrieval_results 为空列表或非列表: {type(retrieval_results).__name__}，返回 fail_response"
                )
                from .answer_generation.prompts import PROMPTS
                return PROMPTS["fail_response"]

        except Exception as e:
            logger.error(f"[convert] 结果转换失败: {type(e).__name__}: {e}", exc_info=True)
            from .answer_generation.prompts import PROMPTS
            return PROMPTS["fail_response"]

    
    async def _fallback_single_mode_query(self, query: str, param: QueryParam) -> str:
        """
        鍥為€€鍒颁紶缁熷崟涓€妯″紡鏌ヨ
        
        Args:
            query: 鏌ヨ鏂囨湰
            param: 鏌ヨ鍙傛暟
            
        Returns:
            鏌ヨ鍝嶅簲
        """
        try:
            # 楠岃瘉妯″紡鍙敤鎬?
            if param.mode in ("local", "global", "global_local") and not self.enable_local:
                param.mode = "naive"
            if param.mode == "naive" and not self.enable_naive_rag:
                param.mode = "llm_only"
            
            # 鎵ц浼犵粺鏌ヨ
            if param.mode == "local":
                return await local_query(
                    query, self.chunk_entity_relation_graph, self.entities_vdb,
                    self.community_reports, self.text_chunks, param, self._get_query_config()
                )
            elif param.mode == "global":
                return await global_query(
                    query, self.chunk_entity_relation_graph, self.entities_vdb,
                    self.community_reports, self.text_chunks, param, self._get_query_config()
                )
            elif param.mode == "global_local":
                return await global_local_query(
                    query, self.chunk_entity_relation_graph, self.entities_vdb,
                    self.community_reports, self.text_chunks, param, self._get_query_config()
                )
            elif param.mode == "naive":
                return await naive_query(
                    query, self.chunks_vdb, self.text_chunks, param, self._get_query_config()
                )
            elif param.mode == "bm25":
                from .query_processing.bm25_query import bm25_query
                return await bm25_query(
                    query, self.bm25_storage, self.text_chunks, param, self._get_query_config()
                )
            elif param.mode == "llm_only":
                return await self._llm_only_response(query, param)
            else:
                return await self._llm_only_response(query, param)
                
        except Exception as e:
            logger.error(f"鍥為€€鏌ヨ澶辫触: {e}")
            from .answer_generation.prompts import PROMPTS
            return PROMPTS["fail_response"]

    async def ainsert(self, string_or_strings, progress_callback=None):
        """寮傛鎻掑叆鎺ュ彛"""
        import inspect as _inspect

        async def _report(pct: int, stage: str) -> None:
            if progress_callback is None:
                return
            try:
                if _inspect.iscoroutinefunction(progress_callback):
                    await progress_callback(pct, stage)
                else:
                    progress_callback(pct, stage)
            except Exception as _cb_err:
                logger.warning(f"progress_callback raised: {_cb_err}")

        await self._insert_start()
        await _report(5, "初始化")
        try:
            if isinstance(string_or_strings, str):
                string_or_strings = [string_or_strings]
                
            # 澶勭悊鏂版枃妗?
            new_docs = {
                compute_mdhash_id(c.strip(), prefix="doc-"): {"content": c.strip()}
                for c in string_or_strings
            }
            _add_doc_keys = await self.full_docs.filter_keys(list(new_docs.keys()))
            new_docs = {k: v for k, v in new_docs.items() if k in _add_doc_keys}
            
            if not len(new_docs):
                logger.warning("All docs are already in the storage")
                return
            logger.info(f"[New Docs] inserting {len(new_docs)} docs")

            # 鏂囨湰鍒嗗潡
            inserting_chunks = get_chunks(
                new_docs=new_docs,
                chunk_func=self.chunk_func,
                overlap_token_size=self.chunk_overlap_token_size,
                max_token_size=self.chunk_token_size,
            )

            _add_chunk_keys = await self.text_chunks.filter_keys(
                list(inserting_chunks.keys())
            )
            inserting_chunks = {
                k: v for k, v in inserting_chunks.items() if k in _add_chunk_keys
            }
            
            if not len(inserting_chunks):
                logger.warning("All chunks are already in the storage")
                return
            logger.info(f"[New Chunks] inserting {len(inserting_chunks)} chunks")
            await _report(10, "文本分块")
            
            if self.enable_naive_rag:
                logger.info("Insert chunks for naive RAG")
                await self.chunks_vdb.upsert(inserting_chunks)

            # 鏂板锛欱M25 鏂囨。绱㈠紩锛堝熀浜?chunks 鍐呭锛?
            if self.enable_bm25 and self.bm25_storage is not None:
                try:
                    bm25_docs = {k: v.get("content", "") for k, v in inserting_chunks.items()}
                    # 杩囨护绌哄唴瀹癸紝閬垮厤鏃犳晥绱㈠紩
                    bm25_docs = {k: c for k, c in bm25_docs.items() if isinstance(c, str) and c.strip()}
                    if bm25_docs:
                        logger.info("Indexing %d chunks into BM25 storage", len(bm25_docs))
                        await self.bm25_storage.index_documents(bm25_docs)
                except Exception as e:
                    logger.warning(f"BM25 indexing failed: {e}")

            # 娓呯悊绀惧尯鎶ュ憡锛堥渶瑕侀噸鏂扮敓鎴愶級
            # 瀹炰綋鎻愬彇鍜屽浘鏋勫缓
            await _report(35, "实体抽取")
            logger.info("[Entity Extraction]...")
            maybe_new_kg = await self.entity_extraction_func(
                inserting_chunks,
                knwoledge_graph_inst=self.chunk_entity_relation_graph,
                entity_vdb=self.entities_vdb,
                global_config=asdict(self),
                using_amazon_bedrock=self.using_amazon_bedrock,
            )
            
            if maybe_new_kg is None:
                logger.warning("No new entities found")
                return
            self.chunk_entity_relation_graph = maybe_new_kg
            await self.community_reports.drop()
            await _report(65, "实体抽取完成")

            # 鍥捐仛绫诲拰绀惧尯鎶ュ憡鐢熸垚
            await _report(70, "图谱聚类")
            logger.info("[Community Report]...")
            await self.chunk_entity_relation_graph.clustering(
                self.graph_cluster_algorithm
            )
            await _report(75, "社区报告生成")
            await generate_community_report(
                self.community_reports, self.chunk_entity_relation_graph, asdict(self)
            )

            # 鎻愪氦鏇存柊
            await _report(90, "索引提交")
            await self.full_docs.upsert(new_docs)
            await self.text_chunks.upsert(inserting_chunks)
            await _report(100, "处理完成")
            
        finally:
            await self._insert_done()


    async def rebuild_vector_index_only(self, progress_callback=None) -> dict:
        """
        仅重建向量索引\uff08FAISS\uff09和 BM25 索引\uff0c不重新运行实体抽取和图谱构建\u3002

        \u9002\u7528\u573a\u666f\uff1a\u5411\u91cf\u7d22\u5f15\u88ab\u968f\u673a\u5411\u91cf\u6c61\u67d3\uff08Embedding API \u6545\u969c\uff09\u65f6\u5feb\u901f\u4fee\u590d\u3002
        \u77e5\u8bc6\u56fe\u8c31\u3001\u793e\u533a\u62a5\u544a\u3001\u5b9e\u4f53\u7d22\u5f15\u5747\u4fdd\u6301\u4e0d\u53d8\u3002
        """
        import inspect as _inspect

        async def _report(pct: int, stage: str) -> None:
            if progress_callback is None:
                return
            try:
                if _inspect.iscoroutinefunction(progress_callback):
                    await progress_callback(pct, stage)
                else:
                    progress_callback(pct, stage)
            except Exception as _cb_err:
                logger.warning(f"progress_callback raised: {_cb_err}")

        await _report(5, "\u52a0\u8f7d\u5206\u5757\u6570\u636e")

        # 1. \u4ece\u5df2\u6709\u7684 text_chunks KV \u5b58\u50a8\u4e2d\u52a0\u8f7d\u5168\u90e8\u5206\u5757
        all_chunk_ids = await self.text_chunks.all_keys()
        if not all_chunk_ids:
            logger.warning("text_chunks \u4e3a\u7a7a\uff0c\u65e0\u6cd5\u91cd\u5efa\u5411\u91cf\u7d22\u5f15\uff0c\u8bf7\u5148\u5b8c\u6574\u5efa\u5e93\u3002")
            return {"error": "no_chunks", "chunks_reindexed": 0, "bm25_reindexed": 0}

        all_chunks_raw = await self.text_chunks.get_by_ids(all_chunk_ids)
        chunks_data = {}
        for chunk_id, chunk in zip(all_chunk_ids, all_chunks_raw):
            if chunk and isinstance(chunk, dict) and isinstance(chunk.get("content"), str) and chunk["content"].strip():
                chunks_data[chunk_id] = chunk

        if not chunks_data:
            logger.warning("\u672a\u627e\u5230\u6709\u6548 chunk\uff0c\u8bf7\u68c0\u67e5 text_chunks \u5185\u5bb9\u3002")
            return {"error": "no_valid_chunks", "chunks_reindexed": 0, "bm25_reindexed": 0}

        logger.info(f"\u51c6\u5907\u91cd\u5efa\u5411\u91cf\u7d22\u5f15\uff0c\u5171 {len(chunks_data)} \u4e2a chunks")
        await _report(15, f"\u51c6\u5907\u5d4c\u5165 {len(chunks_data)} \u4e2a chunks")

        # 2. \u91cd\u5efa FAISS \u7d22\u5f15
        faiss_reindexed = 0
        if self.enable_naive_rag and hasattr(self, "chunks_vdb") and self.chunks_vdb is not None:
            try:
                # \u6e05\u7a7a\u65e7\u7d22\u5f15
                self.chunks_vdb._create_new_index()
                logger.info("FAISS \u65e7\u7d22\u5f15\u5df2\u6e05\u7a7a\uff0c\u5f00\u59cb\u91cd\u65b0\u751f\u6210\u5d4c\u5165\u5411\u91cf...")
                await _report(20, "\u751f\u6210 embedding \u5411\u91cf")

                # \u91cd\u65b0\u5d4c\u5165\uff08\u5185\u90e8\u4f1a\u5206\u6279\u8c03\u7528 embedding_func\uff09
                await self.chunks_vdb.upsert(chunks_data)

                # \u6301\u4e45\u5316\u5230\u78c1\u76d8
                await self.chunks_vdb.index_done_callback()
                faiss_reindexed = len(chunks_data)
                logger.info(f"FAISS \u91cd\u5efa\u5b8c\u6210\uff1a{faiss_reindexed} \u4e2a vectors")
                await _report(70, "FAISS \u5411\u91cf\u7d22\u5f15\u91cd\u5efa\u5b8c\u6210")
            except Exception as e:
                logger.error(f"FAISS \u91cd\u5efa\u5931\u8d25: {e}")
                return {"error": str(e), "chunks_reindexed": 0, "bm25_reindexed": 0}
        else:
            logger.info("\u6587\u6863\u68c0\u7d22\uff08naive RAG\uff09\u672a\u542f\u7528\uff0c\u8df3\u8fc7 FAISS \u91cd\u5efa")
            await _report(70, "\u8df3\u8fc7 FAISS\uff08\u672a\u542f\u7528\uff09")

        # 3. \u91cd\u5efa BM25 \u7d22\u5f15
        bm25_reindexed = 0
        if self.enable_bm25 and hasattr(self, "bm25_storage") and self.bm25_storage is not None:
            try:
                # \u6e05\u7a7a\u65e7\u7d22\u5f15
                self.bm25_storage._index = {}
                self.bm25_storage._doc_lengths = {}
                self.bm25_storage._documents = {}
                self.bm25_storage._avg_doc_length = 0
                self.bm25_storage._initialized = False

                bm25_docs = {k: v.get("content", "") for k, v in chunks_data.items()}
                bm25_docs = {k: c for k, c in bm25_docs.items() if isinstance(c, str) and c.strip()}
                if bm25_docs:
                    logger.info(f"\u91cd\u5efa BM25 \u7d22\u5f15\uff0c\u5171 {len(bm25_docs)} \u4e2a docs")
                    await _report(80, "\u91cd\u5efa BM25 \u5173\u952e\u8bcd\u7d22\u5f15")
                    await self.bm25_storage.index_documents(bm25_docs)
                    bm25_reindexed = len(bm25_docs)
                    logger.info(f"BM25 \u91cd\u5efa\u5b8c\u6210\uff1a{bm25_reindexed} \u4e2a docs")
            except Exception as e:
                logger.warning(f"BM25 \u91cd\u5efa\u5931\u8d25\uff08\u4e0d\u5f71\u54cd FAISS\uff09: {e}")
        else:
            logger.info("\u5173\u952e\u8bcd\u68c0\u7d22\uff08BM25\uff09\u672a\u542f\u7528\uff0c\u8df3\u8fc7")

        await _report(100, "\u5411\u91cf\u7d22\u5f15\u91cd\u5efa\u5b8c\u6210")
        return {
            "chunks_reindexed": faiss_reindexed,
            "bm25_reindexed": bm25_reindexed,
            "total_chunks": len(chunks_data),
        }


    async def rebuild_graph_only(self, progress_callback=None) -> dict:
        """
        \u4ec5\u91cd\u5efa\u77e5\u8bc6\u56fe\u8c31\uff08\u5b9e\u4f53\u62bd\u53d6\u3001\u805a\u7c7b\u548c\u793e\u533a\u62a5\u544a\uff09\uff0c\u4fdd\u7559\u73b0\u6709\u7684 FAISS \u548c BM25 \u7d22\u5f15\u3002
        \u9002\u7528\u573a\u666f\uff1a\u9700\u8981\u66f4\u65b0\u5b9e\u4f53\u62bd\u53d6\u903b\u8f91\u6216\u793e\u533a\u62a5\u544a\uff0c\u4f46\u5411\u91cf\u7d22\u5f15\u5df2\u6b63\u5e38\u3002
        """
        import inspect as _inspect

        async def _report(pct: int, stage: str) -> None:
            if progress_callback is None:
                return
            try:
                if _inspect.iscoroutinefunction(progress_callback):
                    await progress_callback(pct, stage)
                else:
                    progress_callback(pct, stage)
            except Exception as _cb_err:
                logger.warning(f"progress_callback raised: {_cb_err}")

        await _report(5, "\u52a0\u8f7d\u5206\u5757\u6570\u636e")

        # 1. \u4ece\u5df2\u6709\u7684 text_chunks \u52a0\u8f7d\u5168\u90e8 chunks
        all_chunk_ids = await self.text_chunks.all_keys()
        if not all_chunk_ids:
            logger.warning("text_chunks \u4e3a\u7a7a\uff0c\u8bf7\u5148\u5b8c\u6574\u5efa\u5e93")
            return {"error": "no_chunks"}

        all_chunks_raw = await self.text_chunks.get_by_ids(all_chunk_ids)
        chunks_data = {}
        for chunk_id, chunk in zip(all_chunk_ids, all_chunks_raw):
            if chunk and isinstance(chunk, dict) and isinstance(chunk.get("content"), str) and chunk["content"].strip():
                chunks_data[chunk_id] = chunk

        if not chunks_data:
            return {"error": "no_valid_chunks"}

        logger.info(f"\u51c6\u5907\u91cd\u5efa\u77e5\u8bc6\u56fe\u8c31\uff0c\u5171 {len(chunks_data)} \u4e2a chunks")
        await _report(10, f"\u51c6\u5907\u5206\u6790 {len(chunks_data)} \u4e2a chunks")

        # 2. \u6e05\u7a7a\u793e\u533a\u62a5\u544a
        await self.community_reports.drop()
        await _report(15, "\u6e05\u7a7a\u793e\u533a\u62a5\u544a")

        # 3. \u6e05\u7a7a\u5b9e\u4f53\u5411\u91cf\u7d22\u5f15\uff08\u4f1a\u88ab\u5b9e\u4f53\u62bd\u53d6\u91cd\u5efa\uff09
        if hasattr(self, "entities_vdb") and self.entities_vdb is not None and hasattr(self.entities_vdb, "_create_new_index"):
            self.entities_vdb._create_new_index()
            logger.info("\u5b9e\u4f53\u5411\u91cf\u7d22\u5f15\u5df2\u6e05\u7a7a")

        # 4. \u6e05\u7a7a\u77e5\u8bc6\u56fe\u8c31
        import networkx as _nx
        if hasattr(self.chunk_entity_relation_graph, "_graph"):
            self.chunk_entity_relation_graph._graph = _nx.Graph()
            logger.info("\u5185\u5b58\u56fe\u8c31\u5df2\u6e05\u7a7a")

        await _report(20, "\u56fe\u8c31\u5df2\u6e05\u7a7a\uff0c\u5f00\u59cb\u5b9e\u4f53\u62bd\u53d6")

        # 5. \u91cd\u65b0\u8fd0\u884c\u5b9e\u4f53\u62bd\u53d6
        logger.info("[Graph Rebuild] Entity Extraction...")
        from dataclasses import asdict
        try:
            maybe_new_kg = await self.entity_extraction_func(
                chunks_data,
                knwoledge_graph_inst=self.chunk_entity_relation_graph,
                entity_vdb=self.entities_vdb,
                global_config=asdict(self),
                using_amazon_bedrock=self.using_amazon_bedrock,
            )
        except Exception as e:
            logger.error(f"\u5b9e\u4f53\u62bd\u53d6\u5931\u8d25: {e}")
            return {"error": str(e)}

        if maybe_new_kg is None:
            logger.warning("\u5b9e\u4f53\u62bd\u53d6\u8fd4\u56de\u7a7a\u56fe\u8c31")
            return {"error": "entity_extraction_returned_none"}

        self.chunk_entity_relation_graph = maybe_new_kg
        await _report(65, "\u5b9e\u4f53\u62bd\u53d6\u5b8c\u6210\uff0c\u5f00\u59cb\u56fe\u8c31\u805a\u7c7b")

        # 6. \u91cd\u65b0\u805a\u7c7b\u548c\u793e\u533a\u62a5\u544a
        logger.info("[Graph Rebuild] Community Clustering...")
        await self.chunk_entity_relation_graph.clustering(self.graph_cluster_algorithm)
        await _report(75, "\u805a\u7c7b\u5b8c\u6210\uff0c\u751f\u6210\u793e\u533a\u62a5\u544a")

        logger.info("[Graph Rebuild] Community Reports...")
        await generate_community_report(
            self.community_reports, self.chunk_entity_relation_graph, asdict(self)
        )
        await _report(90, "\u793e\u533a\u62a5\u544a\u751f\u6210\u5b8c\u6210")

        # 7. \u6301\u4e45\u5316\u56fe\u8c31\u548c\u5b9e\u4f53 VDB
        if hasattr(self.chunk_entity_relation_graph, "index_done_callback"):
            await self.chunk_entity_relation_graph.index_done_callback()
        if hasattr(self, "entities_vdb") and self.entities_vdb is not None:
            await self.entities_vdb.index_done_callback()

        node_count = 0
        edge_count = 0
        if hasattr(self.chunk_entity_relation_graph, "_graph"):
            node_count = self.chunk_entity_relation_graph._graph.number_of_nodes()
            edge_count = self.chunk_entity_relation_graph._graph.number_of_edges()

        await _report(100, "\u77e5\u8bc6\u56fe\u8c31\u91cd\u5efa\u5b8c\u6210")
        logger.info(f"\u56fe\u8c31\u91cd\u5efa\u5b8c\u6210: nodes={node_count}, edges={edge_count}")
        return {
            "nodes": node_count,
            "edges": edge_count,
            "chunks_used": len(chunks_data),
        }

    async def evaluate_system(self, 
                            questions: List[str],
                            answers: List[str] = None,
                            contexts_list: List[List[str]] = None,
                            ground_truths: List[str] = None,
                            system_name: str = "GraphRAG System") -> Dict[str, Any]:
        """
        璇勪及绯荤粺鎬ц兘
        浣跨敤鐜颁唬璇勪及鍣ㄨ繘琛屽叏闈㈣瘎浼?
        
        Args:
            questions: 闂鍒楄〃
            answers: 绛旀鍒楄〃锛堝彲閫夛紝濡傛灉涓虹┖鍒欎細璋冪敤绯荤粺鐢熸垚锛?
            contexts_list: 涓婁笅鏂囧垪琛紙鍙€夛級
            ground_truths: 鏍囧噯绛旀鍒楄〃锛堝繀闇€锛?
            system_name: 绯荤粺鍚嶇О
        
        Returns:
            Dict[str, Any]: 璇勪及缁撴灉
        """
        if not self.enable_enhanced_features or not hasattr(self, 'evaluator') or self.evaluator is None:
            logger.warning("Evaluator not available, skipping evaluation")
            return {"error": "Evaluator not available"}
        
        try:
            # 濡傛灉娌℃湁鎻愪緵鏍囧噯绛旀锛屾棤娉曡繘琛岃瘎浼?
            if not ground_truths or len(ground_truths) != len(questions):
                logger.error("Ground truth answers are required for evaluation")
                return {"error": "Ground truth answers are required"}
            
            # 浣跨敤璇勪及鍣ㄨ繘琛岃瘎浼?
            results_list = []
            
            # 濡傛灉娌℃湁鎻愪緵answers锛岀敓鎴愬畠浠?
            if answers is None or len(answers) != len(questions):
                answers = []
                for question in questions:
                    answer = await self.aquery(question)
                    answers.append(answer)
            
            # 璇勪及姣忎釜闂
            for i, question in enumerate(questions):
                metrics = self.evaluator.evaluate_single(
                    query=question,
                    generated_answer=answers[i],
                    reference_answer=ground_truths[i] if i < len(ground_truths) else None,
                    retrieved_docs=None,  # 鍙€夛細濡傛灉闇€瑕佸彲浠ヤ紶鍏ユ绱㈡枃妗?
                    relevant_docs=None
                )
                results_list.append({
                    "question": question,
                    "generated_answer": answers[i],
                    "ground_truth": ground_truths[i] if i < len(ground_truths) else None,
                    "metrics": metrics
                })
            
            # 璁＄畻骞冲潎鎸囨爣
            avg_metrics = self.evaluator.get_average_metrics()
            
            # 鏋勫缓缁撴灉瀛楀吀
            result_dict = {
                "system_name": system_name,
                "total_cases": len(questions),
                "valid_cases": len(results_list),
                "average_metrics": avg_metrics,
                "individual_results": results_list
            }
            
            logger.info("System evaluation completed successfully")
            return result_dict
            
        except Exception as e:
            logger.error(f"System evaluation failed: {e}")
            import traceback
            traceback.print_exc()
            return {"error": str(e)}

    def get_system_statistics(self) -> Dict[str, Any]:
        """鑾峰彇绯荤粺缁熻淇℃伅"""
        stats = {
            "basic_info": {
                "working_dir": self.working_dir,
                "enable_enhanced_features": self.enable_enhanced_features,
                "enable_local": self.enable_local,
                "enable_naive_rag": self.enable_naive_rag
            }
        }
        
        # 娣诲姞澧炲己鍔熻兘缁熻
        if self.enable_enhanced_features:
            if hasattr(self, 'complexity_router') and self.complexity_router:
                stats["complexity_stats"] = self.complexity_router.get_complexity_stats()
            
            if hasattr(self, 'evaluator') and self.evaluator:
                stats["evaluation_summary"] = self.evaluator.get_summary()
            
            # 娣诲姞铻嶅悎寮曟搸缁熻
            if hasattr(self, 'fusion_engine') and self.fusion_engine:
                stats["fusion_stats"] = self.fusion_engine.get_fusion_stats()
                stats["fusion_engine_type"] = "RRF_ConfidenceAware"
        
        return stats

    async def _insert_start(self):
        """鎻掑叆寮€濮嬪洖璋?"""
        tasks = []
        for storage_inst in [self.chunk_entity_relation_graph]:
            if storage_inst is None:
                continue
            tasks.append(storage_inst.index_start_callback())
        await asyncio.gather(*tasks)

    async def _insert_done(self):
        """鎻掑叆瀹屾垚鍥炶皟"""
        tasks = []
        for storage_inst in [
            self.full_docs,
            self.text_chunks,
            self.llm_response_cache,
            self.community_reports,
            self.entities_vdb,
            self.chunks_vdb,
            self.chunk_entity_relation_graph,
            self.bm25_storage,  # 鏂板锛欱M25 绱㈠紩钀界洏
        ]:
            if storage_inst is None:
                continue
            tasks.append(storage_inst.index_done_callback())
        await asyncio.gather(*tasks)

    def _plan_retrieval_tasks(self, complexity_result: Dict[str, Any], param: QueryParam, query: str = "") -> List[str]:
        """
        瑙勫垝妫€绱换鍔?- 鍩轰簬澶嶆潅搴﹀拰缃俊搴﹂€夋嫨妫€绱㈢瓥鐣?
        
        Args:
            complexity_result: 澶嶆潅搴﹀垎鏋愮粨鏋?
            param: 鏌ヨ鍙傛暟
            
        Returns:
            閫夋嫨鐨勬绱㈡ā寮忓垪琛?
        """
        # 鑾峰彇鍙敤鐨勬绱㈡ā寮?
        # Hard guarantees about user-chosen modes:
        # - `llm_only` must never hit any KB retrieval.
        # - Except for `auto`, all modes are strict single-engine execution.
        if param.mode == "llm_only":
            logger.info("User explicitly selected llm_only mode - skipping retrieval router")
            return ["llm_only"]
        if param.mode != "auto":
            logger.info(f"User explicitly selected {param.mode} mode - enforcing single-engine execution")
            return [param.mode]

        available_modes = ["llm_only", "naive", "bm25", "local", "global", "global_local"]
        if not self.enable_local:
            available_modes = [m for m in available_modes if m not in ["local", "global", "global_local"]]
        if not self.enable_naive_rag:
            available_modes = [m for m in available_modes if m != "naive"]
        if not self.enable_bm25:
            available_modes = [m for m in available_modes if m != "bm25"]
        
        # 浣跨敤ComplexityRouter瑙勫垝妫€绱换鍔?
        if hasattr(self, 'complexity_router') and self.complexity_router:
            try:
                retrieval_plan = self.complexity_router.get_retrieval_plan(complexity_result, available_modes, query=query)
                logger.info(f"妫€绱㈣鍒? {retrieval_plan}")
                return retrieval_plan
            except Exception as e:
                logger.error(f"妫€绱㈣鍒掑け璐? {e}")
                # 鍥為€€鍒板崟涓€妯″紡
                return [param.mode] if param.mode in available_modes else [available_modes[0]]
        else:
            # 濡傛灉娌℃湁璺敱鍣紝鍥為€€鍒板師濮嬫ā寮?
            return [param.mode] if param.mode in available_modes else [available_modes[0]]
    
    def _plan_fixed_retrieval_tasks(self, param: QueryParam) -> List[str]:
        """
        鍥哄畾妫€绱换鍔¤鍒?- 鐢ㄤ簬娑堣瀺瀹為獙
        
        鎵€鏈夋煡璇娇鐢ㄧ浉鍚岀殑妫€绱㈢瓥鐣ワ紝涓嶆牴鎹鏉傚害璋冩暣
        
        Args:
            param: 鏌ヨ鍙傛暟
            
        Returns:
            鍥哄畾鐨勬绱㈡ā寮忓垪琛?
        """
        # 鍥哄畾浣跨敤local + naive鐨勭粍鍚堬紙妯℃嫙涓瓑澶嶆潅搴︽煡璇級
        # Hard guarantees about user-chosen modes:
        # - `llm_only` must never hit any KB retrieval.
        # - Except for `auto`, all modes are strict single-engine execution.
        if param.mode == "llm_only":
            logger.info("User explicitly selected llm_only mode (fixed) - skipping retrieval")
            return ["llm_only"]
        if param.mode != "auto":
            logger.info(f"User explicitly selected {param.mode} mode (fixed) - enforcing single-engine execution")
            return [param.mode]

        available_modes = []
        
        if self.enable_local:
            available_modes.append("local")
        if self.enable_naive_rag:
            available_modes.append("naive")
        if self.enable_bm25:
            available_modes.append("bm25")
        
        # 濡傛灉娌℃湁鍙敤妯″紡锛屼娇鐢╨lm_only
        if not available_modes:
            available_modes = ["llm_only"]
        
        logger.info(f"鍥哄畾妫€绱㈢瓥鐣? {available_modes}")
        return available_modes
    
    async def _execute_retrieval_tasks(self, retrieval_modes: List[str], query: str, param: QueryParam, complexity_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        骞惰鎵ц妫€绱换鍔?
        
        Args:
            retrieval_modes: 瑕佹墽琛岀殑妫€绱㈡ā寮忓垪琛?
            query: 鏌ヨ鏂囨湰
            param: 鏌ヨ鍙傛暟
            
        Returns:
            妫€绱㈢粨鏋滃瓧鍏?{mode: result}
        """
        import asyncio
        from .query_processing.bm25_query import bm25_query
        from .query_processing.llm_only_query import llm_only_query
        
        async def _execute_single_retrieval(mode: str):
            """鎵ц鍗曚釜妫€绱换鍔?"""
            try:
                # 鍩轰簬澶嶆潅搴﹀拰缃俊搴︿负涓嶅悓妫€绱㈡ā寮忓垱寤鸿皟鏁村悗鐨?QueryParam
                mode_param = self._create_mode_specific_param(mode, param, complexity_result)
                if mode == "local":
                    result = await local_query(
                        query,
                        self.chunk_entity_relation_graph,
                        self.entities_vdb,
                        self.community_reports,
                        self.text_chunks,
                        mode_param,
                        self._get_query_config(),
                        return_raw_results=True  # 浣跨敤鏂扮殑鍙傛暟
                    )
                elif mode == "global":
                    result = await global_query(
                        query,
                        self.chunk_entity_relation_graph,
                        self.entities_vdb,
                        self.community_reports,
                        self.text_chunks,
                        mode_param,
                        self._get_query_config(),
                        return_raw_results=True
                    )
                elif mode == "global_local":
                    result = await global_local_query(
                        query,
                        self.chunk_entity_relation_graph,
                        self.entities_vdb,
                        self.community_reports,
                        self.text_chunks,
                        mode_param,
                        self._get_query_config(),
                        return_raw_results=True
                    )
                elif mode == "naive":
                    result = await naive_query(
                        query,
                        self.chunks_vdb,
                        self.text_chunks,
                        mode_param,
                        self._get_query_config(),
                        return_raw_results=True
                    )
                elif mode == "bm25":
                    result = await bm25_query(
                        query,
                        self.bm25_storage if hasattr(self, 'bm25_storage') else None,
                        self.text_chunks,
                        mode_param,
                        self._get_query_config(),
                        return_raw_results=True
                    )
                elif mode == "llm_only":
                    # LLM only妯″紡杩斿洖瀛楃涓茶€屼笉鏄疪etrievalResult鍒楄〃
                    result = await llm_only_query(
                        query,
                        mode_param,
                        self._get_query_config(),
                    )
                else:
                    logger.warning(f"Unknown retrieval mode: {mode}")
                    result = []
                
                return result
                
            except Exception as e:
                logger.error(f"妫€绱㈡ā寮?{mode} 鎵ц澶辫触: {e}")
                return []
        
        # 骞惰鎵ц鎵€鏈夋绱换鍔?
        tasks = {mode: _execute_single_retrieval(mode) for mode in retrieval_modes}
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        
        # 鏋勫缓缁撴灉瀛楀吀
        retrieval_results = {}
        for i, mode in enumerate(retrieval_modes):
            result = results[i]
            if isinstance(result, Exception):
                logger.error(f"妫€绱㈡ā寮?{mode} 鍑虹幇寮傚父: {result}")
                retrieval_results[mode] = []
            else:
                retrieval_results[mode] = result
        
        logger.info(f"骞惰妫€绱㈠畬鎴愶紝妯″紡: {list(retrieval_results.keys())}")
        return retrieval_results
    
    async def _llm_only_response(self, query: str, param: QueryParam) -> str:
        """
        澶勭悊绛栫暐A鐨勭洿鎺LM鍥炵瓟
        
        Args:
            query: 鏌ヨ鏂囨湰
            param: 鏌ヨ鍙傛暟
            
        Returns:
            LLM鐢熸垚鐨勫洖绛?
        """
        try:
            from .query_processing.llm_only_query import llm_only_query
            response = await llm_only_query(
                query,
                param,
                self._get_query_config(),
            )
            logger.info("浣跨敤LLM鐩存帴鍥炵瓟绛栫暐")
            return response
        except Exception as e:
            logger.error(f"LLM鐩存帴鍥炵瓟澶辫触: {e}")
            from .answer_generation.prompts import PROMPTS
            return PROMPTS["fail_response"]

    def _create_mode_specific_param(
        self, mode: str, base_param: QueryParam, complexity_result: Dict[str, Any]
    ) -> QueryParam:
        """
        鏍规嵁澶嶆潅搴﹀拰缃俊搴︿负涓嶅悓妫€绱㈡ā寮忓垱寤鸿皟鏁村悗鐨?QueryParam銆?

        鐩爣锛氬湪涓嶆敼鍙樿涔夎涓虹殑鍓嶆彁涓嬶紝瀹炵幇璁烘枃涓€滄笎杩涘紡銆佸灞傝祫婧愬垎閰嶁€濈殑鎬濇兂锛?
        - 绛栫暐A锛堥珮缃俊搴︼級锛氭敹绱?top_k 鍜?token 涓婇檺锛屽噺灏戝啑浣欐绱?
        - 绛栫暐B锛堜腑绛夌疆淇″害锛夛細閫傚害鎵╁睍
        - 绛栫暐C锛堜綆缃俊搴︼級锛氫繚鐣欏師濮嬭緝澶х殑妫€绱㈣妯?
        """
        import copy

        param = copy.deepcopy(base_param)
        complexity = complexity_result.get("complexity", "one_hop")
        confidence = complexity_result.get("confidence", 0.5)

        # 鎸夎鏂囩瓥鐣ュ尯鍒?A/B/C
        if confidence >= 0.9:
            strategy = "A"
        elif confidence >= 0.6:
            strategy = "B"
        else:
            strategy = "C"

        # 鍩虹 top_k 璋冩暣
        if strategy == "A":
            # 楂樼疆淇″害锛氭洿灏忕殑 top_k
            param.top_k = min(param.top_k, 5)
        elif strategy == "B":
            # 涓瓑缃俊搴︼細閫備腑瑙勬ā
            param.top_k = min(param.top_k, 10)
        else:
            # 浣庣疆淇″害锛氫繚鎸佸師鏈?top_k锛堥€氬父涓?20锛?
            param.top_k = base_param.top_k

        # 閽堝涓嶅悓妫€绱㈠櫒鐨?token 棰勭畻缂╂斁鍥犲瓙
        if strategy == "A":
            scale = 0.5
        elif strategy == "B":
            scale = 0.75
        else:
            scale = 1.0

        # 鎸夋ā寮忚皟鏁村叿浣撶殑 token 闄愬埗
        if mode in ("naive", "vector"):
            # 鏈寸礌鍚戦噺妫€绱?
            if hasattr(param, "naive_max_token_for_text_unit"):
                param.naive_max_token_for_text_unit = int(
                    base_param.naive_max_token_for_text_unit * scale
                )
        elif mode == "bm25":
            if hasattr(param, "bm25_max_token_for_text_unit"):
                param.bm25_max_token_for_text_unit = int(
                    base_param.bm25_max_token_for_text_unit * scale
                )
        elif mode == "local":
            # 灞€閮ㄥ浘妫€绱細缁煎悎璋冩暣灞€閮ㄧ浉鍏冲瓧娈?
            if hasattr(param, "local_max_token_for_text_unit"):
                param.local_max_token_for_text_unit = int(
                    base_param.local_max_token_for_text_unit * scale
                )
            if hasattr(param, "local_max_token_for_local_context"):
                param.local_max_token_for_local_context = int(
                    base_param.local_max_token_for_local_context * scale
                )
            if hasattr(param, "local_max_token_for_community_report"):
                param.local_max_token_for_community_report = int(
                    base_param.local_max_token_for_community_report * scale
                )
        elif mode == "global":
            # 鍏ㄥ眬鍥炬憳瑕侊細鎺у埗绀惧尯鎶ュ憡闀垮害
            if hasattr(param, "global_max_token_for_community_report"):
                # 瀵瑰鏉?multi-hop 鍦烘櫙锛屽湪绛栫暐C涓嬩繚鐣欒緝澶ч绠楋紝鍏朵綑鎯呭喌鐣ュ井鏀剁揣
                if complexity == "multi_hop" and strategy == "C":
                    param.global_max_token_for_community_report = (
                        base_param.global_max_token_for_community_report
                    )
                else:
                    param.global_max_token_for_community_report = int(
                        base_param.global_max_token_for_community_report * scale
                    )
        elif mode == "global_local":
            if hasattr(param, "local_max_token_for_text_unit"):
                param.local_max_token_for_text_unit = int(
                    base_param.local_max_token_for_text_unit * scale
                )
            if hasattr(param, "local_max_token_for_local_context"):
                param.local_max_token_for_local_context = int(
                    base_param.local_max_token_for_local_context * scale
                )
            if hasattr(param, "local_max_token_for_community_report"):
                param.local_max_token_for_community_report = int(
                    base_param.local_max_token_for_community_report * scale
                )
            if hasattr(param, "global_max_token_for_community_report"):
                param.global_max_token_for_community_report = int(
                    base_param.global_max_token_for_community_report * scale
                )
        # llm_only 涓嶉渶瑕佹绱㈤绠楄皟鏁?

        return param

    def _normalize_results_by_source(
        self, retrieval_results: Dict[str, Any]
    ) -> tuple[Optional[str], Dict[str, List[Any]]]:
        from .retrieval.alignment import RetrievalResult

        active_results = {
            retriever_name: result
            for retriever_name, result in retrieval_results.items()
            if result
        }
        direct_response: Optional[str] = None
        results_by_source: Dict[str, List[Any]] = {}

        for retriever_name, result in active_results.items():
            if isinstance(result, str):
                if retriever_name == "llm_only":
                    if len(active_results) == 1:
                        direct_response = result
                    continue

                content_parts: List[str] = []
                if "--New Chunk--" in result:
                    content_parts = [
                        segment.strip()
                        for segment in result.split("--New Chunk--")
                        if segment.strip()
                    ]
                elif "-----" in result and "```csv" in result:
                    for part in result.split("-----"):
                        if "```csv" not in part:
                            continue
                        csv_start = part.find("```csv\n")
                        csv_end = part.find("\n```")
                        if csv_start == -1 or csv_end == -1:
                            continue
                        csv_content = part[csv_start + 7 : csv_end].strip()
                        if csv_content:
                            content_parts.append(csv_content)
                else:
                    stripped = result.strip()
                    if stripped:
                        content_parts = [stripped]

                converted_results: List[Any] = []
                for index, content in enumerate(content_parts):
                    if len(content.strip()) <= 10:
                        continue
                    converted_results.append(
                        RetrievalResult(
                            content=content,
                            score=1.0 - (index * 0.1),
                            source=retriever_name,
                            chunk_id=f"{retriever_name}_part_{index}",
                            rank=index + 1,
                            metadata={"converted_from_string": True},
                        )
                    )

                if converted_results:
                    results_by_source[retriever_name] = converted_results
                continue

            if isinstance(result, list) and all(
                isinstance(item, RetrievalResult) for item in result
            ):
                if result:
                    results_by_source[retriever_name] = result
                continue

            logger.warning(
                f"Unsupported retrieval result format from {retriever_name}: {type(result)}"
            )

        return direct_response, results_by_source

    def _build_vanilla_fused_results(
        self, results_by_source: Dict[str, List[Any]], top_k: int = 20
    ) -> List[Any]:
        rrf_k = 60.0
        rrf_scores: Dict[str, Dict[str, Any]] = {}

        for source, results in results_by_source.items():
            for rank, result in enumerate(results, start=1):
                chunk_id = getattr(result, "chunk_id", None) or compute_mdhash_id(
                    f"{source}:{rank}:{getattr(result, 'content', '')}",
                    prefix="rrf-",
                )
                rrf_score = 1.0 / (rrf_k + rank)

                if chunk_id not in rrf_scores:
                    rrf_scores[chunk_id] = {
                        "score": 0.0,
                        "result": result,
                        "sources": [],
                    }

                rrf_scores[chunk_id]["score"] += rrf_score
                rrf_scores[chunk_id]["sources"].append(source)

        sorted_results = sorted(
            rrf_scores.items(),
            key=lambda item: item[1]["score"],
            reverse=True,
        )

        fused_results: List[Any] = []
        for index, (_, data) in enumerate(sorted_results[:top_k]):
            result = data["result"]
            metadata = (
                result.metadata if isinstance(getattr(result, "metadata", None), dict) else {}
            )
            metadata["rrf_score"] = data["score"]
            metadata["fusion_rank"] = index + 1
            metadata["sources"] = list(dict.fromkeys(data["sources"]))
            result.metadata = metadata
            fused_results.append(result)

        return fused_results

    async def _confidence_aware_fusion(self, retrieval_results: Dict[str, Any], complexity_result: Dict[str, Any], query: str, param: QueryParam) -> str:
        """
        缃俊搴︽劅鐭ョ殑澶氭簮妫€绱㈣瀺鍚堟柟娉?
        
        浣跨敤RRF(Reciprocal Rank Fusion)绠楁硶鍜岀疆淇″害鎰熺煡鏉冮噸璋冩暣锛?
        灏嗗涓绱㈠櫒鐨勭粨鏋滆繘琛屾櫤鑳介噸鎺掑簭鍜岃瀺鍚堛€?
        
        鏍稿績鐗规€э細
        - RRF鎺掑簭铻嶅悎锛氬熀浜庢帓鍚嶈€岄潪鍒嗘暟杩涜铻嶅悎锛岄伩鍏嶄笉鍚屾绱㈠櫒鍒嗘暟涓嶅彲姣旂殑闂
        - 缃俊搴︽劅鐭ワ細鏍规嵁鏌ヨ澶嶆潅搴﹀姩鎬佽皟鏁村悇妫€绱㈡簮鐨勬潈閲?
        - 澶氭牱鎬т繚璇侊細纭繚铻嶅悎缁撴灉鏉ユ簮澶氭牱鍖?
        
        Args:
            retrieval_results: 妫€绱㈢粨鏋滃瓧鍏?{retriever_name: List[RetrievalResult] or str}
            complexity_result: 澶嶆潅搴﹀垎鏋愮粨鏋?
            query: 鏌ヨ鏂囨湰
            param: 鏌ヨ鍙傛暟
            
        Returns:
            铻嶅悎鍚庣殑鍝嶅簲瀛楃涓?
        """
        try:
            logger.info("Using confidence-aware RRF fusion")
            
            # 妫€鏌ユ槸鍚﹀惎鐢ㄧ疆淇″害鎰熺煡铻嶅悎寮曟搸
            if not self.enable_confidence_fusion or self.fusion_engine is None:
                logger.warning("RRF fusion engine unavailable; falling back to simple fusion")
                return await self._fallback_fusion_strategy(retrieval_results, query, param)
            
            # 灏嗘绱㈢粨鏋滆浆鎹负鎸夋簮鍒嗙粍鐨凴etrievalResult鍒楄〃
            from .retrieval.alignment import RetrievalResult
            results_by_source = {}
            
            for retriever_name, result in retrieval_results.items():
                if not result:
                    continue
                    
                if isinstance(result, str):
                    # 瀛楃涓茬粨鏋滆浆鎹负RetrievalResult鍒楄〃
                    if retriever_name == "llm_only":
                        # llm_only缁撴灉鐩存帴杩斿洖锛屼笉鍙備笌铻嶅悎
                        if len(retrieval_results) == 1:
                            return result
                        continue
                    else:
                        # 鍏朵粬瀛楃涓茬粨鏋滆浆鎹负RetrievalResult
                        # 灏濊瘯鎸夋钀藉垎鍓插瓧绗︿覆缁撴灉浠ュ鍔犵矑搴?
                        content_parts = []
                        if "--New Chunk--" in result:
                            content_parts = [s.strip() for s in result.split("--New Chunk--") if s.strip()]
                        elif "-----" in result and "```csv" in result:
                            # 澶勭悊鍥炬绱㈢粨鏋滄牸寮?
                            parts = result.split("-----")
                            for part in parts:
                                if "```csv" in part:
                                    csv_start = part.find("```csv\n") + 7
                                    csv_end = part.find("\n```")
                                    if csv_start != -1 and csv_end != -1:
                                        csv_content = part[csv_start:csv_end].strip()
                                        if csv_content:
                                            content_parts.append(csv_content)
                        else:
                            content_parts = [result.strip()]
                        
                        retrieval_results_list = []
                        for i, content in enumerate(content_parts):
                            if content and len(content.strip()) > 10:
                                converted_result = RetrievalResult(
                                    content=content,
                                    score=1.0 - (i * 0.1),  # 閫掑噺鍒嗘暟
                                    source=retriever_name,
                                    chunk_id=f"{retriever_name}_part_{i}",
                                    rank=i + 1,
                                    metadata={"converted_from_string": True}
                                )
                                retrieval_results_list.append(converted_result)
                        results_by_source[retriever_name] = retrieval_results_list
                
                elif isinstance(result, list) and all(isinstance(r, RetrievalResult) for r in result):
                    # 宸茬粡鏄疪etrievalResult鍒楄〃
                    results_by_source[retriever_name] = result
                
                else:
                    logger.warning(f"鏈煡鐨勭粨鏋滄牸寮忔潵鑷?{retriever_name}: {type(result)}")
                    continue
            
            if not results_by_source:
                logger.warning("No valid retrieval results available for fusion")
                from .answer_generation.prompts import PROMPTS
                return PROMPTS["fail_response"]
            
            # 浣跨敤RRF铻嶅悎寮曟搸杩涜鏅鸿兘铻嶅悎
            fused_results = await self.fusion_engine.fuse_results(
                results_by_source=results_by_source,
                query_complexity=complexity_result
            )
            
            if not fused_results:
                logger.warning("RRF fusion engine returned empty results")
                from .answer_generation.prompts import PROMPTS
                return PROMPTS["fail_response"]
            
            # 灏嗚瀺鍚堢粨鏋滆浆鎹负涓婁笅鏂囧苟鐢熸垚绛旀
            response = await self._generate_answer_from_rrf_results(fused_results, query, param, complexity_result)
            
            logger.info(
                f"RRF fusion completed with {len(results_by_source)} retrievers and "
                f"{len(fused_results)} fused results"
            )
            
            return response
            
        except Exception as e:
            logger.error(f"RRF铻嶅悎澶辫触: {e}")
            logger.info("Fallback to simple fusion strategy")
            return await self._fallback_fusion_strategy(retrieval_results, query, param)
    
    async def _generate_answer_from_rrf_results(
        self, 
        fused_results: List,  # List[RetrievalResult] from RRF
        query: str, 
        param: QueryParam,
        complexity_result: Dict[str, Any]
    ) -> str:
        """
        浠嶳RF铻嶅悎缁撴灉鐢熸垚鏈€缁堢瓟妗?
        
        Args:
            fused_results: RRF铻嶅悎鍚庣殑妫€绱㈢粨鏋滃垪琛?
            query: 鍘熷鏌ヨ
            param: 鏌ヨ鍙傛暟
            complexity_result: 澶嶆潅搴﹀垎鏋愮粨鏋?
            
        Returns:
            鐢熸垚鐨勭瓟妗堝瓧绗︿覆
        """
        try:
            from .retrieval.alignment import RetrievalResult
            
            if not fused_results:
                from .answer_generation.prompts import PROMPTS
                return PROMPTS["fail_response"]
            
            # 鏋勫缓铻嶅悎涓婁笅鏂?
            context_parts = []
            for i, result in enumerate(fused_results):
                if isinstance(result, RetrievalResult):
                    # 娣诲姞缁撴灉鏉ユ簮鍜孯RF鍒嗘暟淇℃伅
                    rrf_score = result.metadata.get('rrf_score', 0.0)
                    fusion_rank = result.metadata.get('fusion_rank', i + 1)
                    source_info = f"[鏉ユ簮: {result.source}, RRF鍒嗘暟: {rrf_score:.3f}, 铻嶅悎鎺掑悕: {fusion_rank}]"
                    context_parts.append(f"{source_info}\n{result.content}")
                else:
                    # 鍏煎鍏朵粬鏍煎紡
                    context_parts.append(str(result))
            
            if not context_parts:
                from .answer_generation.prompts import PROMPTS
                return PROMPTS["fail_response"]
            
            # 浣跨敤鍒嗛殧绗﹁繛鎺ュ唴瀹?
            fused_context = "\n\n--铻嶅悎鍐呭--\n".join(context_parts)
            
            # 娣诲姞RRF铻嶅悎缁熻淇℃伅
            fusion_stats = (
                f"\n\n[RRF fusion stats] confidence-aware RRF fused {len(fused_results)} results"
            )
            if self.fusion_engine:
                fusion_engine_stats = self.fusion_engine.get_fusion_stats()
                fusion_stats += (
                    f", engine total fusions: {fusion_engine_stats.get('total_fusions', 0)}"
                )
            
            complete_context = fused_context + fusion_stats
            
            # 鏍规嵁澶嶆潅搴﹂€夋嫨鍚堥€傜殑鎻愮ず妯℃澘
            confidence = complexity_result.get("confidence", 0.5)
            complexity = complexity_result.get("complexity", "one_hop")
            
            # 閫夋嫨鎻愮ず妯℃澘
            from .answer_generation.prompts import PROMPTS
            if complexity == "multi_hop" or confidence < 0.5:
                # 澶嶆潅鏌ヨ鎴栦綆缃俊搴︼紝浣跨敤鏇磋缁嗙殑鎻愮ず
                prompt_template = PROMPTS.get("fusion_complex_response", PROMPTS["naive_rag_response"])
            else:
                # 绠€鍗曟煡璇㈡垨楂樼疆淇″害锛屼娇鐢ㄦ爣鍑嗘彁绀?
                prompt_template = PROMPTS.get("fusion_response", PROMPTS["naive_rag_response"])
            
            # 鏍煎紡鍖栨彁绀?
            system_prompt = prompt_template.format(
                content_data=complete_context,
                response_type=param.response_type
            )
            
            # 鐢熸垚绛旀
            use_model_func = self.best_model_func
            response = await use_model_func(
                query,
                system_prompt=system_prompt,
                stream_callback=self.answer_stream_callback,
                **self.special_community_report_llm_kwargs
            )
            
            logger.debug(f"浠?{len(fused_results)} 涓猂RF铻嶅悎缁撴灉鐢熸垚绛旀鎴愬姛")
            return response
            
        except Exception as e:
            logger.error(f"浠嶳RF铻嶅悎缁撴灉鐢熸垚绛旀澶辫触: {e}")
            from .answer_generation.prompts import PROMPTS
            return PROMPTS["fail_response"]
    
    async def _vanilla_rrf_fusion(self, retrieval_results: Dict[str, Any], query: str, param: QueryParam) -> str:
        """
        Vanilla RRF铻嶅悎鏂规硶 - 鐢ㄤ簬娑堣瀺瀹為獙
        
        浣跨敤鏍囧噯RRF绠楁硶锛屾墍鏈夋绱㈡簮鍧囩瓑鏉冮噸锛屼笉浣跨敤缃俊搴﹁皟鏁?
        
        Args:
            retrieval_results: 妫€绱㈢粨鏋滃瓧鍏?{retriever_name: List[RetrievalResult] or str}
            query: 鏌ヨ鏂囨湰
            param: 鏌ヨ鍙傛暟
            
        Returns:
            铻嶅悎鍚庣殑鍝嶅簲瀛楃涓?
        """
        try:
            logger.info("浣跨敤vanilla RRF铻嶅悎锛堝潎绛夋潈閲嶏級")
            
            from .retrieval.alignment import RetrievalResult
            
            # 灏嗘绱㈢粨鏋滆浆鎹负缁熶竴鏍煎紡
            results_by_source = {}
            
            for retriever_name, result in retrieval_results.items():
                if not result:
                    continue
                    
                if isinstance(result, str):
                    if retriever_name == "llm_only":
                        if len(retrieval_results) == 1:
                            return result
                        continue
                    else:
                        # 杞崲瀛楃涓蹭负RetrievalResult鍒楄〃
                        content_parts = []
                        if "--New Chunk--" in result:
                            content_parts = [s.strip() for s in result.split("--New Chunk--") if s.strip()]
                        else:
                            content_parts = [result.strip()]
                        
                        retrieval_results_list = []
                        for i, content in enumerate(content_parts):
                            if content and len(content.strip()) > 10:
                                converted_result = RetrievalResult(
                                    content=content,
                                    score=1.0 - (i * 0.1),
                                    source=retriever_name,
                                    chunk_id=f"{retriever_name}_part_{i}",
                                    rank=i + 1,
                                    metadata={"converted_from_string": True}
                                )
                                retrieval_results_list.append(converted_result)
                        results_by_source[retriever_name] = retrieval_results_list
                
                elif isinstance(result, list) and all(isinstance(r, RetrievalResult) for r in result):
                    results_by_source[retriever_name] = result
                else:
                    logger.warning(f"鏈煡鐨勭粨鏋滄牸寮忔潵鑷?{retriever_name}: {type(result)}")
                    continue
            
            if not results_by_source:
                logger.warning("No valid retrieval results available for fusion")
                from .answer_generation.prompts import PROMPTS
                return PROMPTS["fail_response"]
            
            # 鏍囧噯RRF铻嶅悎锛氬潎绛夋潈閲?
            k = 60.0  # RRF甯告暟
            rrf_scores = {}
            
            for source, results in results_by_source.items():
                for rank, result in enumerate(results, start=1):
                    chunk_id = result.chunk_id
                    # 鏍囧噯RRF鍏紡锛? / (k + rank)
                    rrf_score = 1.0 / (k + rank)
                    
                    if chunk_id not in rrf_scores:
                        rrf_scores[chunk_id] = {
                            "score": 0.0,
                            "result": result,
                            "sources": []
                        }
                    
                    rrf_scores[chunk_id]["score"] += rrf_score
                    rrf_scores[chunk_id]["sources"].append(source)
            
            # 鎸塕RF鍒嗘暟鎺掑簭
            sorted_results = sorted(
                rrf_scores.items(),
                key=lambda x: x[1]["score"],
                reverse=True
            )
            
            # 鍙杢op-k缁撴灉
            top_k = min(20, len(sorted_results))
            fused_results = []
            
            for i, (chunk_id, data) in enumerate(sorted_results[:top_k]):
                result = data["result"]
                result.metadata["rrf_score"] = data["score"]
                result.metadata["fusion_rank"] = i + 1
                result.metadata["sources"] = data["sources"]
                fused_results.append(result)
            
            # 鐢熸垚绛旀
            context_parts = []
            for i, result in enumerate(fused_results):
                rrf_score = result.metadata.get('rrf_score', 0.0)
                sources = ", ".join(result.metadata.get('sources', [result.source]))
                source_info = f"[鏉ユ簮: {sources}, RRF鍒嗘暟: {rrf_score:.3f}, 鎺掑悕: {i+1}]"
                context_parts.append(f"{source_info}\n{result.content}")
            
            fused_context = "\n\n--铻嶅悎鍐呭--\n".join(context_parts)
            fusion_stats = (
                f"\n\n[Vanilla RRF fusion] standard RRF fused {len(fused_results)} results"
            )
            complete_context = fused_context + fusion_stats
            
            # 鐢熸垚绛旀
            from .answer_generation.prompts import PROMPTS
            prompt_template = PROMPTS.get("fusion_response", PROMPTS["naive_rag_response"])
            system_prompt = prompt_template.format(
                content_data=complete_context,
                response_type=param.response_type
            )
            
            response = await self.best_model_func(
                query,
                system_prompt=system_prompt,
                stream_callback=self.answer_stream_callback,
                **self.special_community_report_llm_kwargs
            )
            
            logger.info(
                f"Vanilla RRF fusion completed with {len(results_by_source)} retrievers and "
                f"{len(fused_results)} fused results"
            )
            return response
            
        except Exception as e:
            logger.error(f"Vanilla RRF铻嶅悎澶辫触: {e}")
            return await self._fallback_fusion_strategy(retrieval_results, query, param)
    
    
    async def _fallback_fusion_strategy(
        self, 
        retrieval_results: Dict[str, Any], 
        query: str, 
        param: QueryParam
    ) -> str:
        """
        鍥為€€铻嶅悎绛栫暐 - 褰撶疆淇″害鎰熺煡铻嶅悎澶辫触鏃朵娇鐢?
        
        Args:
            retrieval_results: 妫€绱㈢粨鏋滃瓧鍏?
            query: 鏌ヨ鏂囨湰
            param: 鏌ヨ鍙傛暟
            
        Returns:
            鍥為€€绛栫暐鐨勫搷搴?
        """
        try:
            logger.info("浣跨敤鍥為€€铻嶅悎绛栫暐")
            
            # 绠€鍗曠瓥鐣ワ細鎸変紭鍏堢骇閫夋嫨绗竴涓潪绌虹粨鏋?
            priority_order = ["global_local", "global", "local", "naive", "bm25", "llm_only"]
            
            for mode in priority_order:
                if mode in retrieval_results and retrieval_results[mode]:
                    result = retrieval_results[mode]
                    logger.info(f"Fallback to {mode} retrieval result")
                    
                    if mode == "llm_only":
                        return result
                    else:
                        return await self._convert_retrieval_results_to_response(result, query, param)
            
            # 濡傛灉鎸変紭鍏堢骇娌℃壘鍒帮紝閫夋嫨浠讳綍闈炵┖缁撴灉
            for mode, result in retrieval_results.items():
                if result:
                    logger.info(f"Fallback to {mode} retrieval result (no priority match)")
                    if mode == "llm_only":
                        return result
                    else:
                        return await self._convert_retrieval_results_to_response(result, query, param)
            
            # 濡傛灉鎵€鏈夌粨鏋滈兘涓虹┖锛岃繑鍥炲け璐ュ搷搴?
            logger.warning("鎵€鏈夋绱㈢粨鏋滈兘涓虹┖")
            from .answer_generation.prompts import PROMPTS
            return PROMPTS["fail_response"]
            
        except Exception as e:
            logger.error(f"鍥為€€铻嶅悎绛栫暐澶辫触: {e}")
            from .answer_generation.prompts import PROMPTS
            return PROMPTS["fail_response"]

    async def _confidence_aware_fusion(
        self,
        retrieval_results: Dict[str, Any],
        complexity_result: Dict[str, Any],
        query: str,
        param: QueryParam,
        return_details: bool = False,
    ) -> Union[str, Dict[str, Any]]:
        try:
            logger.info("Using confidence-aware RRF fusion")

            if not self.enable_confidence_fusion or self.fusion_engine is None:
                logger.warning("Fusion engine unavailable, fallback to simple fusion")
                return await self._fallback_fusion_strategy(
                    retrieval_results,
                    query,
                    param,
                    return_details=return_details,
                )

            direct_response, results_by_source = self._normalize_results_by_source(
                retrieval_results
            )
            if direct_response is not None:
                if return_details:
                    return {
                        "response": direct_response,
                        "fused_results": [],
                        "results_by_source": {},
                        "fusion_method": "llm_only",
                    }
                return direct_response

            if not results_by_source:
                from .answer_generation.prompts import PROMPTS

                fail_response = PROMPTS["fail_response"]
                if return_details:
                    return {
                        "response": fail_response,
                        "fused_results": [],
                        "results_by_source": {},
                        "fusion_method": "ca_rrf_empty",
                    }
                return fail_response

            fused_results = await self.fusion_engine.fuse_results(
                results_by_source=results_by_source,
                query_complexity=complexity_result,
            )
            if not fused_results:
                from .answer_generation.prompts import PROMPTS

                fail_response = PROMPTS["fail_response"]
                if return_details:
                    return {
                        "response": fail_response,
                        "fused_results": [],
                        "results_by_source": results_by_source,
                        "fusion_method": "ca_rrf_empty",
                    }
                return fail_response

            response = await self._generate_answer_from_rrf_results(
                fused_results, query, param, complexity_result
            )
            logger.info(
                f"Confidence-aware fusion complete with {len(results_by_source)} retrievers "
                f"and {len(fused_results)} fused results"
            )

            if return_details:
                return {
                    "response": response,
                    "fused_results": fused_results,
                    "results_by_source": results_by_source,
                    "fusion_method": "ca_rrf",
                }
            return response
        except Exception as e:
            logger.error(f"RRF fusion failed: {e}")
            return await self._fallback_fusion_strategy(
                retrieval_results,
                query,
                param,
                return_details=return_details,
            )

    async def _vanilla_rrf_fusion(
        self,
        retrieval_results: Dict[str, Any],
        query: str,
        param: QueryParam,
        return_details: bool = False,
    ) -> Union[str, Dict[str, Any]]:
        try:
            logger.info("Using vanilla RRF fusion")

            direct_response, results_by_source = self._normalize_results_by_source(
                retrieval_results
            )
            if direct_response is not None:
                if return_details:
                    return {
                        "response": direct_response,
                        "fused_results": [],
                        "results_by_source": {},
                        "fusion_method": "llm_only",
                    }
                return direct_response

            if not results_by_source:
                from .answer_generation.prompts import PROMPTS

                fail_response = PROMPTS["fail_response"]
                if return_details:
                    return {
                        "response": fail_response,
                        "fused_results": [],
                        "results_by_source": {},
                        "fusion_method": "vanilla_rrf_empty",
                    }
                return fail_response

            fused_results = self._build_vanilla_fused_results(results_by_source, top_k=20)
            if not fused_results:
                from .answer_generation.prompts import PROMPTS

                fail_response = PROMPTS["fail_response"]
                if return_details:
                    return {
                        "response": fail_response,
                        "fused_results": [],
                        "results_by_source": results_by_source,
                        "fusion_method": "vanilla_rrf_empty",
                    }
                return fail_response

            context_parts = []
            for index, result in enumerate(fused_results, start=1):
                rrf_score = result.metadata.get("rrf_score", 0.0)
                sources = ", ".join(result.metadata.get("sources", [result.source]))
                source_info = (
                    f"[Source: {sources}, RRF: {rrf_score:.3f}, Rank: {index}]"
                )
                context_parts.append(f"{source_info}\n{result.content}")

            fused_context = "\n\n--Fused Content--\n".join(context_parts)
            fusion_stats = (
                "\n\n[Vanilla RRF] Standard reciprocal rank fusion over "
                f"{len(fused_results)} results."
            )
            complete_context = fused_context + fusion_stats

            from .answer_generation.prompts import PROMPTS

            prompt_template = PROMPTS.get(
                "fusion_response", PROMPTS["naive_rag_response"]
            )
            system_prompt = prompt_template.format(
                content_data=complete_context,
                response_type=param.response_type,
            )
            response = await self.best_model_func(
                query,
                system_prompt=system_prompt,
                stream_callback=self.answer_stream_callback,
                **self.special_community_report_llm_kwargs,
            )

            if return_details:
                return {
                    "response": response,
                    "fused_results": fused_results,
                    "results_by_source": results_by_source,
                    "fusion_method": "vanilla_rrf",
                }
            return response
        except Exception as e:
            logger.error(f"Vanilla RRF fusion failed: {e}")
            return await self._fallback_fusion_strategy(
                retrieval_results,
                query,
                param,
                return_details=return_details,
            )

    async def _fallback_fusion_strategy(
        self,
        retrieval_results: Dict[str, Any],
        query: str,
        param: QueryParam,
        return_details: bool = False,
    ) -> Union[str, Dict[str, Any]]:
        try:
            logger.info("Using fallback fusion strategy")

            priority_order = ["global_local", "global", "local", "naive", "bm25", "llm_only"]
            selected_mode: Optional[str] = None
            selected_result: Any = None

            for mode in priority_order:
                if mode in retrieval_results and retrieval_results[mode]:
                    selected_mode = mode
                    selected_result = retrieval_results[mode]
                    break

            if selected_mode is None:
                for mode, result in retrieval_results.items():
                    if result:
                        selected_mode = mode
                        selected_result = result
                        break

            if selected_mode is None:
                from .answer_generation.prompts import PROMPTS

                fail_response = PROMPTS["fail_response"]
                if return_details:
                    return {
                        "response": fail_response,
                        "fused_results": [],
                        "results_by_source": {},
                        "fusion_method": "fallback_empty",
                    }
                return fail_response

            logger.info(f"Fallback selected retrieval mode: {selected_mode}")

            if selected_mode == "llm_only":
                if return_details:
                    return {
                        "response": selected_result,
                        "fused_results": [],
                        "results_by_source": {},
                        "fusion_method": "fallback_llm_only",
                    }
                return selected_result

            response = await self._convert_retrieval_results_to_response(
                selected_result, query, param
            )
            evidence_results = self._extract_single_mode_evidence(selected_result)
            _, normalized_results = self._normalize_results_by_source(
                {selected_mode: selected_result}
            )

            if return_details:
                return {
                    "response": response,
                    "fused_results": evidence_results,
                    "results_by_source": normalized_results,
                    "fusion_method": f"fallback_{selected_mode}",
                }
            return response
        except Exception as e:
            logger.error(f"Fallback fusion failed: {e}")
            from .answer_generation.prompts import PROMPTS

            fail_response = PROMPTS["fail_response"]
            if return_details:
                return {
                    "response": fail_response,
                    "fused_results": [],
                    "results_by_source": {},
                    "fusion_method": "fallback_error",
                }
            return fail_response

    def _get_query_config(self) -> Dict[str, Any]:
        """鑾峰彇鏌ヨ閰嶇疆瀛楀吀锛岄伩鍏峚sdict鐨勫簭鍒楀寲闂"""
        return {
            "best_model_func": self.best_model_func,
            "cheap_model_func": self.cheap_model_func,
            "convert_response_to_json_func": self.convert_response_to_json_func,
            "embedding_func": self.embedding_func,
            "entity_extraction_func": self.entity_extraction_func,
            "best_model_max_token_size": self.best_model_max_token_size,
            "cheap_model_max_token_size": self.cheap_model_max_token_size,
            "tiktoken_model_name": self.tiktoken_model_name,
            "special_community_report_llm_kwargs": self.special_community_report_llm_kwargs,
            "answer_stream_callback": self.answer_stream_callback,
            "llm_response_cache": self.llm_response_cache, # 鏂板
            # 娣诲姞鍏朵粬鏌ヨ鍑芥暟鍙兘闇€瑕佺殑閰嶇疆
            "embedding_batch_num": self.embedding_batch_num,
            "embedding_func_max_async": self.embedding_func_max_async,
            "query_better_than_threshold": self.query_better_than_threshold,
        }

    async def _query_done(self):
        """鏌ヨ瀹屾垚鍥炶皟"""
        tasks = []
        for storage_inst in [self.llm_response_cache]:
            if storage_inst is None:
                continue
            tasks.append(storage_inst.index_done_callback())
        await asyncio.gather(*tasks)


# 涓轰簡鍚戝悗鍏煎锛屼繚鐣欏師鏈夌殑GraphRAG绫?
GraphRAG = EnhancedGraphRAG


def create_enhanced_graphrag(**kwargs) -> EnhancedGraphRAG:

    return EnhancedGraphRAG(**kwargs)


def create_basic_graphrag(**kwargs) -> EnhancedGraphRAG:

    kwargs['enable_enhanced_features'] = False
    return EnhancedGraphRAG(**kwargs)



