"""
Utilities for selecting the most relevant text chunks from entity hits.
"""

from typing import Any, Dict, List

from ..answer_generation.prompts import GRAPH_FIELD_SEP
from ..base import BaseGraphStorage, BaseKVStorage, QueryParam, TextChunkSchema
from .._utils import (
    get_tiktoken_encoder,
    logger,
    split_string_by_multi_markers,
    truncate_list_by_token_size,
)


async def _find_most_related_text_unit_from_entities(
    node_datas: List[Dict[str, Any]],
    query_param: QueryParam,
    text_chunks_db: BaseKVStorage[TextChunkSchema],
    knowledge_graph_inst: BaseGraphStorage,
) -> List[TextChunkSchema]:
    """
    Collect and rank text chunks connected to seed entities.
    """
    text_units = [
        split_string_by_multi_markers(dp["source_id"], [GRAPH_FIELD_SEP])
        for dp in node_datas
    ]
    edges = await knowledge_graph_inst.get_nodes_edges_batch(
        [dp["entity_name"] for dp in node_datas]
    )

    all_one_hop_nodes = set()
    for this_edges in edges:
        if not this_edges:
            continue
        all_one_hop_nodes.update([e[1] for e in this_edges])

    all_one_hop_nodes_data_dict = await knowledge_graph_inst.get_nodes_batch(
        list(all_one_hop_nodes)
    )
    all_one_hop_text_units_lookup = {
        k: set(split_string_by_multi_markers(v["source_id"], [GRAPH_FIELD_SEP]))
        for k, v in all_one_hop_nodes_data_dict.items()
        if v is not None
    }

    all_text_units_lookup = {}
    for index, (this_text_units, this_edges) in enumerate(zip(text_units, edges)):
        for chunk_id in this_text_units:
            if chunk_id in all_text_units_lookup:
                continue

            relation_counts = 0
            for edge in this_edges:
                if (
                    edge[1] in all_one_hop_text_units_lookup
                    and chunk_id in all_one_hop_text_units_lookup[edge[1]]
                ):
                    relation_counts += 1

            all_text_units_lookup[chunk_id] = {
                "data": await text_chunks_db.get_by_id(chunk_id),
                "order": index,
                "relation_counts": relation_counts,
            }

    if any(value is None for value in all_text_units_lookup.values()):
        logger.warning("Text chunks are missing, storage may be inconsistent.")

    all_text_units = [
        {"id": key, **value}
        for key, value in all_text_units_lookup.items()
        if value is not None
    ]
    all_text_units = sorted(
        all_text_units, key=lambda item: (item["order"], -item["relation_counts"])
    )

    tiktoken_model = get_tiktoken_encoder("gpt-4o")
    all_text_units = truncate_list_by_token_size(
        all_text_units,
        query_param.local_max_token_for_text_unit,
        tiktoken_model,
        key=lambda item: item["data"]["content"],
    )
    return [item["data"] for item in all_text_units]

