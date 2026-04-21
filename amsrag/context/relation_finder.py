"""
Utilities for selecting relevant graph relations from entity hits.
"""

from typing import Any, Dict, List

from ..base import BaseGraphStorage, QueryParam
from .._utils import get_tiktoken_encoder, truncate_list_by_token_size


async def _find_most_related_edges_from_entities(
    node_datas: List[Dict[str, Any]],
    query_param: QueryParam,
    knowledge_graph_inst: BaseGraphStorage,
) -> List[Dict[str, Any]]:
    """
    Collect and rank relations connected to seed entities.
    """
    all_related_edges = await knowledge_graph_inst.get_nodes_edges_batch(
        [dp["entity_name"] for dp in node_datas]
    )

    all_edges = []
    seen = set()
    for this_edges in all_related_edges:
        for edge in (this_edges or []):
            sorted_edge = tuple(sorted(edge))
            if sorted_edge not in seen:
                seen.add(sorted_edge)
                all_edges.append(sorted_edge)

    all_edges_pack = await knowledge_graph_inst.get_edges_batch(all_edges)
    all_edges_degree = await knowledge_graph_inst.edge_degrees_batch(all_edges)
    all_edges_data = [
        {"src_tgt": edge_key, "rank": degree, **edge_value}
        for edge_key, edge_value, degree in zip(all_edges, all_edges_pack, all_edges_degree)
        if edge_value is not None
    ]
    all_edges_data = sorted(
        all_edges_data, key=lambda item: (item["rank"], item["weight"]), reverse=True
    )

    tiktoken_model = get_tiktoken_encoder("gpt-4o")
    return truncate_list_by_token_size(
        all_edges_data,
        query_param.local_max_token_for_local_context,
        tiktoken_model,
        key=lambda item: item["description"],
    )

