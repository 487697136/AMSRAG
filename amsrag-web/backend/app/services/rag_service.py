"""RAG service wrapper for backend endpoints."""

import asyncio
import copy
import hashlib
import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from loguru import logger

os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

amsrag_root = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(amsrag_root))

from app.core.config import settings

_AMSRAG_COMPONENTS: Optional[Tuple[Any, Any, Any]] = None


def _load_amsrag_components() -> Tuple[Any, Any, Any]:
    """Load AMSRAG symbols lazily to avoid heavy backend startup."""
    global _AMSRAG_COMPONENTS
    if _AMSRAG_COMPONENTS is None:
        from amsrag import GraphRAG, QueryParam
        from amsrag._storage.vector.faiss import FAISSVectorStorage

        _AMSRAG_COMPONENTS = (GraphRAG, QueryParam, FAISSVectorStorage)
    return _AMSRAG_COMPONENTS


class RAGService:
    """Per-user knowledge-base RAG service."""

    def __init__(self, user_id: int, kb_id: int):
        self.user_id = user_id
        self.kb_id = kb_id
        self.working_dir = str(settings.get_rag_workspace_path(user_id, kb_id))
        self.rag_instance: Optional[Any] = None
        self._is_initialized = False

        logger.info(
            "RAG service created for user={}, kb={}, dir={}",
            user_id,
            kb_id,
            self.working_dir,
        )

    async def initialize(
        self,
        dashscope_key: str,
        siliconflow_key: str,
        enable_local: bool = True,
        enable_naive_rag: bool = True,
        enable_bm25: bool = False,
        llm_provider: str = "",
        llm_api_key: str = "",
        llm_model: str = "",
        embedding_model: str = "",
    ) -> bool:
        try:
            GraphRAG, _, FAISSVectorStorage = _load_amsrag_components()
            os.environ["DASHSCOPE_API_KEY"] = dashscope_key
            os.environ["SILICONFLOW_API_KEY"] = siliconflow_key
            os.environ["SILKFLOW_API_KEY"] = siliconflow_key
            # 注入用户选择的嵌入模型（覆盖默认 BAAI/bge-m3）
            if embedding_model:
                os.environ["SILICONFLOW_EMBED_MODEL"] = embedding_model
                os.environ["SILKFLOW_EMBED_MODEL"] = embedding_model
            os.environ["AMSRAG_ENTITY_EXTRACTION_MODEL"] = (
                settings.RAG_ENTITY_EXTRACTION_MODEL
            )

            from amsrag._llm import (
                create_openai_compatible_complete_function,
                siliconflow_embedding,
            )

            graph_storage_cls = None
            graph_addon_params: dict[str, Any] = {}
            if settings.RAG_GRAPH_BACKEND.strip().lower() == "neo4j":
                neo4j_auth = settings.get_neo4j_auth()
                if settings.NEO4J_URL and neo4j_auth:
                    try:
                        from neo4j import GraphDatabase
                        from amsrag._storage.graph.neo4j import Neo4jStorage

                        connectivity_driver = GraphDatabase.driver(
                            settings.NEO4J_URL,
                            auth=neo4j_auth,
                        )
                        try:
                            connectivity_driver.verify_connectivity()
                        finally:
                            connectivity_driver.close()

                        graph_storage_cls = Neo4jStorage
                        graph_addon_params = {
                            "neo4j_url": settings.NEO4J_URL,
                            "neo4j_auth": neo4j_auth,
                        }
                        logger.info(
                            "Neo4j connectivity verified for user={}, kb={}",
                            self.user_id,
                            self.kb_id,
                        )
                    except Exception as exc:
                        logger.warning(
                            "Neo4j graph backend requested but connectivity verification failed: {}. Falling back to NetworkX.",
                            exc,
                        )
                else:
                    logger.warning(
                        "Neo4j graph backend requested but NEO4J_URL/NEO4J_USERNAME/NEO4J_PASSWORD are incomplete; falling back to NetworkX."
                    )

            from openai import AsyncOpenAI
            from app.schemas.api_key import PROVIDER_REGISTRY

            if llm_provider and llm_api_key and llm_provider != "dashscope":
                provider_info = PROVIDER_REGISTRY.get(llm_provider, {})
                base_url = provider_info.get("base_url", "")
                llm_client = AsyncOpenAI(
                    base_url=base_url or None,
                    api_key=llm_api_key,
                )
                best_model_name = llm_model or (provider_info.get("default_models", [""])[0])
                cheap_model_name = llm_model or best_model_name
            else:
                # dashscope 或未指定 provider，使用 DashScope 端点
                _dashscope_key = dashscope_key or os.getenv("DASHSCOPE_API_KEY", "")
                _dashscope_base = os.getenv(
                    "DASHSCOPE_API_BASE",
                    "https://dashscope.aliyuncs.com/compatible-mode/v1",
                )
                llm_client = AsyncOpenAI(
                    base_url=_dashscope_base,
                    api_key=_dashscope_key or "dummy",
                )
                best_model_name = llm_model or settings.RAG_BEST_MODEL.strip() or "qwen-plus"
                cheap_model_name = settings.RAG_CHEAP_MODEL.strip() or "qwen-flash"
                if llm_model:
                    cheap_model_name = llm_model

            best_model_func = create_openai_compatible_complete_function(
                best_model_name, client=llm_client
            )
            cheap_model_func = create_openai_compatible_complete_function(
                cheap_model_name, client=llm_client
            )

            rag_kwargs: dict[str, Any] = {}
            if graph_storage_cls is not None:
                rag_kwargs["graph_storage_cls"] = graph_storage_cls
                rag_kwargs["addon_params"] = graph_addon_params

            self.rag_instance = GraphRAG(
                working_dir=self.working_dir,
                best_model_id=best_model_name,
                cheap_model_id=cheap_model_name,
                best_model_func=best_model_func,
                cheap_model_func=cheap_model_func,
                embedding_func=siliconflow_embedding,
                vector_db_storage_cls=FAISSVectorStorage,
                enable_local=enable_local,
                enable_naive_rag=enable_naive_rag,
                enable_bm25=enable_bm25,
                query_better_than_threshold=0.05,
                **rag_kwargs,
            )
            self._is_initialized = True
            logger.info(
                "RAG instance initialized for user={}, kb={}, best_model={}, cheap_model={}, graph_backend={}",
                self.user_id,
                self.kb_id,
                best_model_name,
                cheap_model_name,
                settings.RAG_GRAPH_BACKEND,
            )
            return True
        except Exception as exc:
            logger.error(f"Failed to initialize RAG instance: {exc}")
            self._is_initialized = False
            return False

    async def insert_document(
        self,
        content: str,
        progress_callback: Optional[Callable[[int, str], Any]] = None,
    ) -> Dict[str, Any]:
        if not self._is_initialized or not self.rag_instance:
            raise RuntimeError("RAG instance not initialized")

        try:
            logger.info(f"Inserting document, length={len(content)} chars")
            await self.rag_instance.ainsert(content, progress_callback=progress_callback)
            stats = self.get_statistics()
            logger.info(f"Document inserted successfully: {stats}")
            return stats
        except Exception as exc:
            logger.exception(f"Failed to insert document: {exc.__class__.__name__}: {exc}")
            # If the error is connection-related, mark this service as stale so the
            # cache evicts it and creates a fresh instance on the next attempt.
            exc_str = str(exc).lower()
            if any(kw in exc_str for kw in (
                "routing", "serviceunavailable", "unavailable",
                "connection", "connectionreset", "connection lost",
            )):
                logger.warning(
                    "Connection-related failure detected – invalidating cached RAG service "
                    f"(user={self.user_id}, kb={self.kb_id}) so it is re-initialized next time."
                )
                self._is_initialized = False
            raise

    async def rebuild_graph_index(
        self,
        progress_callback=None,
    ) -> dict:
        """
        仅重建知识图谱（实体抽取、图聚类、社区报告），保留 FAISS 和 BM25 向量索引。
        """
        if not self._is_initialized or not self.rag_instance:
            raise RuntimeError("RAG instance not initialized")

        try:
            logger.info("Starting graph-only rebuild (user={}, kb={})", self.user_id, self.kb_id)
            result = await self.rag_instance.rebuild_graph_only(
                progress_callback=progress_callback
            )
            logger.info("Graph rebuild completed: {}", result)
            return result
        except Exception as exc:
            logger.exception("Failed to rebuild graph: {}", exc)
            raise

    async def rebuild_vector_index(
        self,
        progress_callback=None,
    ) -> dict:
        """
        仅重建 FAISS 向量索引和 BM25 索引，不重新运行实体抽取和知识图谱构建。
        用于修复因 Embedding API 故障导致的向量污染，速度远快于完整重建。
        """
        if not self._is_initialized or not self.rag_instance:
            raise RuntimeError("RAG instance not initialized")

        try:
            logger.info("Starting vector-only index rebuild (user={}, kb={})", self.user_id, self.kb_id)
            result = await self.rag_instance.rebuild_vector_index_only(
                progress_callback=progress_callback
            )
            logger.info("Vector index rebuild completed: {}", result)
            return result
        except Exception as exc:
            logger.exception("Failed to rebuild vector index: {}", exc)
            raise

    def _normalize_mode(self, mode: str) -> str:
        # Compatibility aliases
        if mode == "mix":
            return "global"
        # `auto` is a first-class entrypoint handled by EnhancedGraphRAG (adaptive planner).
        return mode

    def _prepare_history_messages(
        self,
        history_messages: Optional[list[dict[str, Any]]],
        memory_turn_window: int,
    ) -> list[dict[str, str]]:
        if not history_messages or memory_turn_window <= 0:
            return []

        filtered_messages: list[dict[str, str]] = []
        for message in history_messages:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role", "")).strip().lower()
            content = str(message.get("content", "")).strip()
            if role not in {"user", "assistant", "system"} or not content:
                continue
            filtered_messages.append({"role": role, "content": content})

        if not filtered_messages:
            return []

        max_messages = memory_turn_window * 2
        system_messages = [msg for msg in filtered_messages if msg["role"] == "system"]
        dialog_messages = [msg for msg in filtered_messages if msg["role"] != "system"]
        truncated_dialog = dialog_messages[-max_messages:]
        return system_messages[-1:] + truncated_dialog

    def _build_memory_augmented_question(
        self,
        question: str,
        prepared_history: list[dict[str, str]],
    ) -> str:
        if not prepared_history:
            return question

        history_lines = []
        for message in prepared_history:
            label = "User" if message["role"] == "user" else "Assistant"
            if message["role"] == "system":
                label = "System"
            history_lines.append(f"{label}: {message['content']}")

        history_block = "\n".join(history_lines)
        return (
            "Conversation context:\n"
            f"{history_block}\n\n"
            "Current question:\n"
            f"{question}"
        )

    def _count_tokens(self, text: str) -> int:
        try:
            import tiktoken

            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except Exception:
            return len(text.split())

    async def _build_query_plan(
        self,
        question: str,
        query_param: Any,
    ) -> Dict[str, Any]:
        if not self.rag_instance:
            return {
                "complexity": None,
                "confidence": None,
                "probabilities": None,
                "planner_method": "unavailable",
                "planned_modes": [query_param.mode],
            }

        complexity_result = {
            "complexity": "one_hop",
            "confidence": 0.5,
            "probabilities": {"one_hop": 1.0},
            "method": "fallback",
        }

        if (
            getattr(self.rag_instance, "enable_enhanced_features", False)
            and hasattr(self.rag_instance, "complexity_router")
            and self.rag_instance.complexity_router
        ):
            try:
                complexity_result = (
                    await self.rag_instance.complexity_router.predict_complexity_detailed(
                        question
                    )
                )
                if not getattr(self.rag_instance, "ablation_routing_adaptive", True):
                    complexity_result = {
                        "complexity": "one_hop",
                        "confidence": 0.5,
                        "probabilities": {"one_hop": 1.0},
                        "method": "fixed_for_ablation",
                    }
            except Exception as exc:
                logger.warning(f"Failed to build query plan: {exc}")

        if hasattr(self.rag_instance, "_plan_retrieval_tasks") and getattr(
            self.rag_instance, "ablation_routing_adaptive", True
        ):
            planned_modes = self.rag_instance._plan_retrieval_tasks(
                complexity_result, copy.deepcopy(query_param)
            )
        elif hasattr(self.rag_instance, "_plan_fixed_retrieval_tasks"):
            planned_modes = self.rag_instance._plan_fixed_retrieval_tasks(
                copy.deepcopy(query_param)
            )
        else:
            planned_modes = [query_param.mode]

        return {
            "complexity": complexity_result.get("complexity"),
            "confidence": complexity_result.get("confidence"),
            "probabilities": complexity_result.get("probabilities"),
            "planner_method": complexity_result.get("method"),
            "planned_modes": planned_modes,
        }

    async def query_with_details(
        self,
        question: str,
        mode: str = "naive",
        top_k: int = 20,
        history_messages: Optional[list[dict[str, Any]]] = None,
        use_memory: bool = True,
        memory_turn_window: int = 4,
        stream_callback: Optional[Callable[[str], Any]] = None,
    ) -> Dict[str, Any]:
        if not self._is_initialized or not self.rag_instance:
            raise RuntimeError("RAG instance not initialized")

        requested_mode = mode
        effective_mode = self._normalize_mode(mode)
        _, QueryParam, _ = _load_amsrag_components()
        query_param = QueryParam(mode=effective_mode, top_k=top_k)
        prepared_history = (
            self._prepare_history_messages(history_messages, memory_turn_window)
            if use_memory
            else []
        )
        effective_question = self._build_memory_augmented_question(
            question, prepared_history
        )
        query_plan = await self._build_query_plan(effective_question, query_param)

        logger.info(
            "Querying with details: question='{}...', requested_mode={}, effective_mode={}, top_k={}, memory_messages={}",
            question[:50],
            requested_mode,
            effective_mode,
            top_k,
            len(prepared_history),
        )

        previous_stream_callback = getattr(
            self.rag_instance, "answer_stream_callback", None
        )
        self.rag_instance.answer_stream_callback = stream_callback
        try:
            response = await self.rag_instance.aquery(
                effective_question,
                param=query_param,
                return_timing=True,
            )
        finally:
            self.rag_instance.answer_stream_callback = previous_stream_callback

        if isinstance(response, dict):
            answer = response.get("response", "")
            timing_ms = response.get("timing", {})
            evidence = response.get("evidence", []) or []
            retrieval_summary = response.get("retrieval_summary", {}) or {}
        else:
            answer = str(response)
            timing_ms = {}
            evidence = []
            retrieval_summary = {}

        query_time = timing_ms.get("total", 0.0) / 1000 if timing_ms else None
        total_tokens = self._count_tokens(answer)

        return {
            "answer": answer,
            "mode": effective_mode,
            "requested_mode": requested_mode,
            "query_time": query_time,
            "response_time": query_time,
            "total_tokens": total_tokens,
            "sources": evidence,
            "metadata": {
                "query_plan": query_plan,
                "retrieval": retrieval_summary,
                "timing_ms": timing_ms,
                "working_dir": self.working_dir,
                "memory": {
                    "used": bool(prepared_history),
                    "message_count": len(prepared_history),
                    "turn_window": memory_turn_window,
                },
                "enabled_modes": {
                    "local": getattr(self.rag_instance, "enable_local", False),
                    "naive": getattr(self.rag_instance, "enable_naive_rag", False),
                    "bm25": getattr(self.rag_instance, "enable_bm25", False),
                },
                "configured_models": {
                    "best": getattr(self.rag_instance, "best_model_id", None)
                    or settings.RAG_BEST_MODEL,
                    "cheap": getattr(self.rag_instance, "cheap_model_id", None)
                    or settings.RAG_CHEAP_MODEL,
                },
            },
        }

    async def query(
        self,
        question: str,
        mode: str = "naive",
        top_k: int = 20,
    ) -> str:
        result = await self.query_with_details(question, mode, top_k)
        return result["answer"]

    def get_statistics(self) -> Dict[str, Any]:
        if not self._is_initialized or not self.rag_instance:
            return {
                "initialized": False,
                "nodes": 0,
                "edges": 0,
                "chunks": 0,
            }

        try:
            stats = {
                "initialized": True,
                "nodes": 0,
                "edges": 0,
                "chunks": 0,
                "node_types": {},
            }

            graph_storage = getattr(
                self.rag_instance, "chunk_entity_relation_graph", None
            )
            if graph_storage is not None:
                if hasattr(graph_storage, "_graph"):
                    graph = graph_storage._graph
                    stats["nodes"] = graph.number_of_nodes()
                    stats["edges"] = graph.number_of_edges()

                    node_types = {}
                    for _, data in graph.nodes(data=True):
                        node_type = data.get("entity_type", "unknown")
                        node_types[node_type] = node_types.get(node_type, 0) + 1
                    stats["node_types"] = node_types
                else:
                    neo4j_stats = self._get_neo4j_graph_statistics(graph_storage)
                    if neo4j_stats is not None:
                        stats.update(neo4j_stats)
                    else:
                        graphml_stats = self._get_graphml_statistics()
                        if graphml_stats is not None:
                            stats.update(graphml_stats)

            if hasattr(self.rag_instance, "text_chunks") and hasattr(
                self.rag_instance.text_chunks, "_data"
            ):
                stats["chunks"] = len(self.rag_instance.text_chunks._data)

            return stats
        except Exception as exc:
            logger.error(f"Failed to get statistics: {exc}")
            return {"initialized": True, "error": str(exc)}

    def _serialize_graph_node(self, node_id: Any, data: Dict[str, Any]) -> Dict[str, Any]:
        node_label = (
            data.get("entity_name")
            or data.get("name")
            or data.get("label")
            or str(node_id)
        )
        return {
            "id": str(node_id),
            "label": str(node_label)[:60],
            "type": data.get("entity_type", "unknown"),
            **data,
        }

    def _serialize_graph_edge(
        self,
        source: Any,
        target: Any,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "source": str(source),
            "target": str(target),
            "relation": data.get("relationship")
            or data.get("relation")
            or data.get("description")
            or "related",
            "weight": data.get("weight", 1.0),
            **data,
        }

    def _get_graphml_path(self) -> Path:
        return Path(self.working_dir) / "graph_chunk_entity_relation.graphml"

    def _get_neo4j_graph_statistics(
        self,
        graph_storage: Any,
    ) -> Optional[Dict[str, Any]]:
        namespace = getattr(graph_storage, "namespace", None)
        neo4j_auth = settings.get_neo4j_auth()
        if not namespace or not settings.NEO4J_URL or not neo4j_auth:
            return None

        try:
            from neo4j import GraphDatabase

            driver = GraphDatabase.driver(settings.NEO4J_URL, auth=neo4j_auth)
            try:
                with driver.session() as session:
                    node_count = session.run(
                        f"MATCH (n:`{namespace}`) RETURN count(n) AS c"
                    ).single()["c"]
                    edge_count = session.run(
                        f"MATCH (a:`{namespace}`)-[r]->(b:`{namespace}`) RETURN count(r) AS c"
                    ).single()["c"]
                    node_type_rows = session.run(
                        f"""
                        MATCH (n:`{namespace}`)
                        RETURN coalesce(n.entity_type, 'unknown') AS entity_type, count(n) AS c
                        """
                    ).data()
                node_types = {
                    str(row["entity_type"]): int(row["c"]) for row in node_type_rows
                }
                return {
                    "nodes": int(node_count),
                    "edges": int(edge_count),
                    "node_types": node_types,
                }
            finally:
                driver.close()
        except Exception as exc:
            logger.warning(f"Failed to collect Neo4j graph statistics: {exc}")
            return None

    def _get_graphml_statistics(self) -> Optional[Dict[str, Any]]:
        graphml_path = self._get_graphml_path()
        if not graphml_path.exists():
            return None

        try:
            import networkx as nx

            graph = nx.read_graphml(graphml_path)
            node_types: dict[str, int] = {}
            for _, data in graph.nodes(data=True):
                node_type = str(data.get("entity_type", "unknown"))
                node_types[node_type] = node_types.get(node_type, 0) + 1
            return {
                "nodes": int(graph.number_of_nodes()),
                "edges": int(graph.number_of_edges()),
                "node_types": node_types,
            }
        except Exception as exc:
            logger.warning(f"Failed to collect GraphML statistics: {exc}")
            return None

    def _build_graph_data_from_networkx_graph(
        self,
        graph: Any,
        node_id: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 80,
        depth: int = 1,
    ) -> Dict[str, Any]:
        selected_node_ids: set[Any] = set()
        normalized_keyword = (keyword or "").strip().lower()
        safe_depth = max(1, min(depth, 2))
        safe_limit = max(10, min(limit, 200))

        if node_id and graph.has_node(node_id):
            selected_node_ids.add(node_id)
            frontier = {node_id}
            for _ in range(safe_depth):
                next_frontier: set[Any] = set()
                for current_node in frontier:
                    next_frontier.update(graph.neighbors(current_node))
                selected_node_ids.update(next_frontier)
                frontier = next_frontier
                if len(selected_node_ids) >= safe_limit:
                    break
        elif normalized_keyword:
            matched_node_ids = []
            for current_node_id, data in graph.nodes(data=True):
                haystack = " ".join(
                    [
                        str(current_node_id),
                        str(data.get("entity_name", "")),
                        str(data.get("description", "")),
                        str(data.get("entity_type", "")),
                    ]
                ).lower()
                if normalized_keyword in haystack:
                    matched_node_ids.append(current_node_id)
            seed_nodes = matched_node_ids[: max(1, safe_limit // 3)]
            selected_node_ids.update(seed_nodes)
            for seed_node in seed_nodes:
                selected_node_ids.update(list(graph.neighbors(seed_node))[:8])
        else:
            ranked_nodes = sorted(
                graph.nodes(),
                key=lambda current_node_id: graph.degree(current_node_id),
                reverse=True,
            )
            selected_node_ids.update(ranked_nodes[:safe_limit])

        if not selected_node_ids:
            return {"nodes": [], "edges": [], "stats": {"node_count": 0, "edge_count": 0}}

        trimmed_node_ids = list(selected_node_ids)[:safe_limit]
        node_id_set = set(trimmed_node_ids)
        nodes = [
            self._serialize_graph_node(current_node_id, data)
            for current_node_id, data in graph.nodes(data=True)
            if current_node_id in node_id_set
        ]

        edges = [
            self._serialize_graph_edge(source, target, data)
            for source, target, data in graph.edges(data=True)
            if source in node_id_set and target in node_id_set
        ]

        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "node_count": len(nodes),
                "edge_count": len(edges),
            },
            "filters": {
                "node_id": node_id,
                "keyword": keyword,
                "limit": safe_limit,
                "depth": safe_depth,
            },
        }

    async def _get_networkx_graph_data(
        self,
        node_id: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 80,
        depth: int = 1,
    ) -> Dict[str, Any]:
        if not self._is_initialized or not self.rag_instance:
            return {"nodes": [], "edges": []}

        try:
            if not hasattr(self.rag_instance, "chunk_entity_relation_graph"):
                return {"nodes": [], "edges": []}

            graph = self.rag_instance.chunk_entity_relation_graph._graph
            return self._build_graph_data_from_networkx_graph(
                graph,
                node_id=node_id,
                keyword=keyword,
                limit=limit,
                depth=depth,
            )
        except Exception as exc:
            logger.error(f"Failed to get graph data: {exc}")
            return {"nodes": [], "edges": [], "error": str(exc)}

    async def _get_graphml_fallback_graph_data(
        self,
        node_id: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 80,
        depth: int = 1,
    ) -> Dict[str, Any]:
        graphml_path = self._get_graphml_path()
        if not graphml_path.exists():
            return {"nodes": [], "edges": []}

        try:
            import networkx as nx

            graph = nx.read_graphml(graphml_path)
            result = self._build_graph_data_from_networkx_graph(
                graph,
                node_id=node_id,
                keyword=keyword,
                limit=limit,
                depth=depth,
            )
            result["message"] = (
                "Neo4j 中当前知识库尚无图数据，已回退显示本地历史图谱缓存。"
            )
            result["fallback"] = "graphml"
            return result
        except Exception as exc:
            logger.warning(f"Failed to read GraphML fallback data: {exc}")
            return {"nodes": [], "edges": [], "error": str(exc)}

    async def _get_neo4j_graph_data(
        self,
        node_id: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 80,
        depth: int = 1,
    ) -> Dict[str, Any]:
        graph_storage = getattr(self.rag_instance, "chunk_entity_relation_graph", None)
        driver = getattr(graph_storage, "async_driver", None)
        namespace = getattr(graph_storage, "namespace", None)
        if not driver or not namespace:
            return {"nodes": [], "edges": [], "error": "Neo4j graph storage unavailable."}

        safe_depth = max(1, min(depth, 2))
        safe_limit = max(10, min(limit, 200))
        nodes_map: dict[str, Dict[str, Any]] = {}
        edges_map: dict[str, Dict[str, Any]] = {}

        try:
            async with driver.session() as session:
                if node_id:
                    seed_query = (
                        f"MATCH (n:`{namespace}` {{id: $node_id}}) "
                        "RETURN n "
                        "LIMIT 1"
                    )
                    seed_result = await session.run(seed_query, node_id=node_id)
                elif keyword:
                    normalized_keyword = keyword.strip().lower()
                    seed_query = (
                        f"MATCH (n:`{namespace}`) "
                        "WHERE toLower(n.id) CONTAINS $keyword "
                        "OR toLower(coalesce(n.entity_name, '')) CONTAINS $keyword "
                        "OR toLower(coalesce(n.description, '')) CONTAINS $keyword "
                        "RETURN n "
                        "LIMIT $limit"
                    )
                    seed_result = await session.run(
                        seed_query,
                        keyword=normalized_keyword,
                        limit=max(1, safe_limit // 3),
                    )
                else:
                    seed_query = (
                        f"MATCH (n:`{namespace}`) "
                        "RETURN n ORDER BY COUNT { (n)--() } DESC LIMIT $limit"
                    )
                    seed_result = await session.run(
                        seed_query,
                        limit=max(1, safe_limit // 2),
                    )

                seed_ids: list[str] = []
                async for record in seed_result:
                    node_props = dict(record["n"])
                    node_key = str(node_props.get("id"))
                    if not node_key:
                        continue
                    seed_ids.append(node_key)
                    nodes_map[node_key] = self._serialize_graph_node(node_key, node_props)

                if not seed_ids:
                    fallback_result = await self._get_graphml_fallback_graph_data(
                        node_id=node_id,
                        keyword=keyword,
                        limit=limit,
                        depth=depth,
                    )
                    if fallback_result.get("nodes") or fallback_result.get("message"):
                        return fallback_result
                    return {
                        "nodes": [],
                        "edges": [],
                        "stats": {"node_count": 0, "edge_count": 0},
                        "message": "当前知识库在 Neo4j 中暂无图数据。",
                    }

                neighborhood_query = f"""
                    UNWIND $seed_ids AS seed_id
                    MATCH (seed:`{namespace}` {{id: seed_id}})
                    OPTIONAL MATCH p=(seed)-[*1..{safe_depth}]-(neighbor:`{namespace}`)
                    WITH collect(DISTINCT seed) + collect(DISTINCT neighbor) AS raw_nodes,
                         collect(DISTINCT relationships(p)) AS raw_rels
                    UNWIND raw_nodes AS node
                    WITH collect(DISTINCT node) AS dedup_nodes, raw_rels
                    UNWIND raw_rels AS rel_list
                    UNWIND rel_list AS rel
                    WITH dedup_nodes, collect(DISTINCT rel) AS dedup_rels
                    RETURN dedup_nodes AS nodes, dedup_rels AS rels
                """
                neighborhood_result = await session.run(
                    neighborhood_query,
                    seed_ids=seed_ids[: max(1, safe_limit // 2)],
                )
                neighborhood_record = await neighborhood_result.single()
                if neighborhood_record:
                    for node in neighborhood_record["nodes"] or []:
                        node_props = dict(node)
                        node_key = str(node_props.get("id"))
                        if not node_key or len(nodes_map) >= safe_limit:
                            continue
                        nodes_map[node_key] = self._serialize_graph_node(
                            node_key,
                            node_props,
                        )

                    node_id_set = set(nodes_map.keys())
                    for rel in neighborhood_record["rels"] or []:
                        source = str(rel.start_node.get("id"))
                        target = str(rel.end_node.get("id"))
                        if source not in node_id_set or target not in node_id_set:
                            continue
                        edge_key = f"{source}::{target}::{rel.type}"
                        edge_props = dict(rel)
                        edge_props.setdefault("relationship", rel.type)
                        edges_map[edge_key] = self._serialize_graph_edge(
                            source,
                            target,
                            edge_props,
                        )
        except Exception as exc:
            logger.warning(
                "Neo4j graph query failed for user={}, kb={}, fallback to GraphML: {}",
                self.user_id,
                self.kb_id,
                exc,
            )
            fallback_result = await self._get_graphml_fallback_graph_data(
                node_id=node_id,
                keyword=keyword,
                limit=limit,
                depth=depth,
            )
            if fallback_result.get("nodes") or fallback_result.get("message"):
                fallback_result.setdefault(
                    "message",
                    "Neo4j 图查询失败，已回退显示本地历史图谱缓存。",
                )
                fallback_result["fallback"] = "graphml"
                fallback_result["fallback_reason"] = "neo4j_query_failed"
                return fallback_result
            return {
                "nodes": [],
                "edges": [],
                "stats": {"node_count": 0, "edge_count": 0},
                "error": f"Neo4j query failed: {exc}",
            }

        nodes = list(nodes_map.values())[:safe_limit]
        node_id_set = {node["id"] for node in nodes}
        edges = [
            edge
            for edge in edges_map.values()
            if edge["source"] in node_id_set and edge["target"] in node_id_set
        ]
        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "node_count": len(nodes),
                "edge_count": len(edges),
            },
            "filters": {
                "node_id": node_id,
                "keyword": keyword,
                "limit": safe_limit,
                "depth": safe_depth,
            },
        }

    async def get_graph_data(
        self,
        node_id: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 80,
        depth: int = 1,
    ) -> Dict[str, Any]:
        graph_storage = getattr(self.rag_instance, "chunk_entity_relation_graph", None)
        if getattr(graph_storage, "async_driver", None) is not None:
            try:
                return await self._get_neo4j_graph_data(
                    node_id=node_id,
                    keyword=keyword,
                    limit=limit,
                    depth=depth,
                )
            except Exception as exc:
                logger.warning(
                    "Unexpected Neo4j graph handler failure for user={}, kb={}: {}",
                    self.user_id,
                    self.kb_id,
                    exc,
                )
                fallback_result = await self._get_graphml_fallback_graph_data(
                    node_id=node_id,
                    keyword=keyword,
                    limit=limit,
                    depth=depth,
                )
                if fallback_result.get("nodes") or fallback_result.get("message"):
                    fallback_result.setdefault(
                        "message",
                        "Neo4j 图查询失败，已回退显示本地历史图谱缓存。",
                    )
                    fallback_result["fallback"] = "graphml"
                    fallback_result["fallback_reason"] = "neo4j_handler_failed"
                    return fallback_result
                return {
                    "nodes": [],
                    "edges": [],
                    "error": f"Failed to fetch graph data: {exc}",
                }
        return await self._get_networkx_graph_data(
            node_id=node_id,
            keyword=keyword,
            limit=limit,
            depth=depth,
        )

    @property
    def is_initialized(self) -> bool:
        return self._is_initialized


ServiceCacheKey = Tuple[int, int, str, bool, bool, bool]
_rag_service_cache: Dict[ServiceCacheKey, RAGService] = {}
_rag_service_cache_lock = asyncio.Lock()


def _build_service_cache_key(
    user_id: int,
    kb_id: int,
    dashscope_key: str,
    siliconflow_key: str,
    enable_local: bool,
    enable_naive_rag: bool,
    enable_bm25: bool,
    llm_provider: str = "",
    llm_model: str = "",
    embedding_model: str = "",
) -> ServiceCacheKey:
    secret_fingerprint = hashlib.sha256(
        f"{dashscope_key}::{siliconflow_key}::{llm_provider}::{llm_model}::{embedding_model}".encode("utf-8")
    ).hexdigest()
    return (
        user_id,
        kb_id,
        secret_fingerprint,
        enable_local,
        enable_naive_rag,
        enable_bm25,
    )


async def get_initialized_rag_service(
    user_id: int,
    kb_id: int,
    dashscope_key: str,
    siliconflow_key: str,
    enable_local: bool = True,
    enable_naive_rag: bool = True,
    enable_bm25: bool = False,
    llm_provider: str = "",
    llm_api_key: str = "",
    llm_model: str = "",
    embedding_model: str = "",
) -> RAGService:
    cache_key = _build_service_cache_key(
        user_id=user_id,
        kb_id=kb_id,
        dashscope_key=dashscope_key,
        siliconflow_key=siliconflow_key,
        enable_local=enable_local,
        enable_naive_rag=enable_naive_rag,
        enable_bm25=enable_bm25,
        llm_provider=llm_provider,
        llm_model=llm_model,
        embedding_model=embedding_model,
    )

    async with _rag_service_cache_lock:
        stale_keys = [
            key
            for key in list(_rag_service_cache.keys())
            if key[0] == user_id and key[1] == kb_id and key != cache_key
        ]
        for key in stale_keys:
            _rag_service_cache.pop(key, None)

        cached_service = _rag_service_cache.get(cache_key)
        if cached_service and cached_service.is_initialized:
            return cached_service

        rag_service = RAGService(user_id, kb_id)
        init_success = await rag_service.initialize(
            dashscope_key=dashscope_key,
            siliconflow_key=siliconflow_key,
            enable_local=enable_local,
            enable_naive_rag=enable_naive_rag,
            enable_bm25=enable_bm25,
            llm_provider=llm_provider,
            llm_api_key=llm_api_key,
            llm_model=llm_model,
            embedding_model=embedding_model,
        )
        if not init_success:
            raise RuntimeError(
                f"Failed to initialize RAG service for user={user_id}, kb={kb_id}"
            )

        _rag_service_cache[cache_key] = rag_service
        return rag_service


def clear_rag_service_cache(
    user_id: Optional[int] = None,
    kb_id: Optional[int] = None,
) -> None:
    keys_to_remove = []
    for key in list(_rag_service_cache.keys()):
        same_user = user_id is None or key[0] == user_id
        same_kb = kb_id is None or key[1] == kb_id
        if same_user and same_kb:
            keys_to_remove.append(key)

    for key in keys_to_remove:
        _rag_service_cache.pop(key, None)

    if keys_to_remove:
        logger.info(f"Cleared {len(keys_to_remove)} cached RAG service instance(s)")
