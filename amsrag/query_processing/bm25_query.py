"""
BM25 retrieval query mode.
"""

from typing import Any, Dict, List, Union

from .._utils import get_tiktoken_encoder, logger, truncate_list_by_token_size
from ..answer_generation.prompts import PROMPTS
from ..base import BaseKVStorage, QueryParam, TextChunkSchema
from ..retrieval.alignment import RetrievalResult, create_retrieval_adapter


async def bm25_query(
    query: str,
    bm25_storage: Any,
    text_chunks_db: BaseKVStorage[TextChunkSchema],
    query_param: QueryParam,
    global_config: Dict[str, Any],
    return_raw_results: bool = False,
) -> Union[str, List[RetrievalResult]]:
    """
    Retrieve with BM25 and optionally synthesize an answer.
    """
    use_model_func = global_config["best_model_func"]

    if bm25_storage is None:
        logger.warning("BM25 storage not available; please enable and build BM25 index.")
        if return_raw_results:
            return []
        return PROMPTS["fail_response"]

    results = await bm25_storage.search(query, top_k=query_param.top_k)
    if not results:
        if return_raw_results:
            return []
        return PROMPTS["fail_response"]

    tiktoken_model = get_tiktoken_encoder("gpt-4o")
    maybe_trun_chunks = truncate_list_by_token_size(
        results,
        query_param.bm25_max_token_for_text_unit,
        tiktoken_model,
        key=lambda item: item["content"],
    )
    logger.info(f"BM25 retrieval truncation: {len(results)} -> {len(maybe_trun_chunks)}")

    if return_raw_results:
        try:
            adapter = create_retrieval_adapter()
            return await adapter.adapt_bm25_results(maybe_trun_chunks, query)
        except Exception as adapter_error:
            logger.error(f"Failed to adapt BM25 results: {adapter_error}")
            return []

    section = "--New Chunk--\n".join([chunk["content"] for chunk in maybe_trun_chunks])
    if query_param.only_need_context:
        return section

    sys_prompt_temp = PROMPTS["naive_rag_response"]
    sys_prompt = sys_prompt_temp.format(
        content_data=section,
        response_type=query_param.response_type,
    )
    return await use_model_func(
        query,
        system_prompt=sys_prompt,
        stream_callback=global_config.get("answer_stream_callback"),
    )
