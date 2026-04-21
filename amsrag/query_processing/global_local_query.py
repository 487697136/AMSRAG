"""
Global-Local query mode.

Workflow:
1. Build global context summary.
2. Rewrite query with global context.
3. Execute local retrieval/generation with the rewritten query.
"""

from __future__ import annotations

from typing import Dict, Any, List, Union

from ..base import (
    BaseGraphStorage,
    BaseKVStorage,
    CommunitySchema,
    TextChunkSchema,
    QueryParam,
    BaseVectorStorage,
)
from .._utils import logger
from ..answer_generation.prompts import PROMPTS
from ..retrieval.alignment import RetrievalResult
from .global_query import global_query
from .local_query import local_query


_REWRITE_SYSTEM_PROMPT = """You are a query rewriting assistant.
Rewrite the user question for entity-centric local graph retrieval.
Keep key constraints and intent unchanged.
Return only one rewritten query sentence with no extra explanation."""


async def _rewrite_query_with_global_context(
    query: str,
    global_context: str,
    global_config: Dict[str, Any],
) -> str:
    use_model_func = global_config["best_model_func"]

    # Prevent excessively large prompt payloads in rewrite stage.
    clipped_context = global_context[:6000]
    rewrite_input = (
        f"Original question:\n{query}\n\n"
        f"Global context summary:\n{clipped_context}\n\n"
        "Rewritten query:"
    )
    rewritten = await use_model_func(
        rewrite_input,
        system_prompt=_REWRITE_SYSTEM_PROMPT,
    )
    rewritten_text = str(rewritten).strip()
    if not rewritten_text:
        return query
    first_line = rewritten_text.splitlines()[0].strip()
    return first_line or query


async def global_local_query(
    query: str,
    knowledge_graph_inst: BaseGraphStorage,
    entities_vdb: BaseVectorStorage,
    community_reports: BaseKVStorage[CommunitySchema],
    text_chunks_db: BaseKVStorage[TextChunkSchema],
    query_param: QueryParam,
    global_config: Dict[str, Any],
    return_context: bool = False,
    return_raw_results: bool = False,
) -> Union[str, List[RetrievalResult]]:
    """
    Global-local retrieval mode:
    - Use global query context to rewrite query.
    - Run local query with rewritten query.
    """

    try:
        global_context = await global_query(
            query,
            knowledge_graph_inst,
            entities_vdb,
            community_reports,
            text_chunks_db,
            query_param,
            global_config,
            return_context=True,
        )
    except Exception as error:
        logger.warning(f"global_local: global stage failed, fallback to local: {error}")
        global_context = ""

    rewritten_query = query
    _fail_resp = PROMPTS.get("fail_response", "")
    if (
        isinstance(global_context, str)
        and global_context.strip()
        and global_context.strip() != _fail_resp.strip()
    ):
        try:
            rewritten_query = await _rewrite_query_with_global_context(
                query,
                global_context,
                global_config,
            )
        except Exception as error:
            logger.warning(f"global_local: rewrite stage failed, keep original query: {error}")
            rewritten_query = query

    if return_raw_results:
        return await local_query(
            rewritten_query,
            knowledge_graph_inst,
            entities_vdb,
            community_reports,
            text_chunks_db,
            query_param,
            global_config,
            return_raw_results=True,
        )

    if query_param.only_need_context or return_context:
        local_context = await local_query(
            rewritten_query,
            knowledge_graph_inst,
            entities_vdb,
            community_reports,
            text_chunks_db,
            query_param,
            global_config,
            return_context=True,
        )
        sections = []
        if isinstance(global_context, str) and global_context.strip():
            sections.append(f"-----Global Context-----\n{global_context}")
        if rewritten_query != query:
            sections.append(f"-----Rewritten Query-----\n{rewritten_query}")
        if isinstance(local_context, str) and local_context.strip():
            sections.append(f"-----Local Context-----\n{local_context}")
        if sections:
            return "\n\n".join(sections)
        return local_context

    return await local_query(
        rewritten_query,
        knowledge_graph_inst,
        entities_vdb,
        community_reports,
        text_chunks_db,
        query_param,
        global_config,
    )
