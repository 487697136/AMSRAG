"""
Utilities for selecting relevant communities from entity hits.
"""

import json
from collections import Counter
from typing import Any, Dict, List

from ..base import BaseKVStorage, CommunitySchema, QueryParam
from .._utils import get_tiktoken_encoder, truncate_list_by_token_size


async def _find_most_related_community_from_entities(
    node_datas: List[Dict[str, Any]],
    query_param: QueryParam,
    community_reports: BaseKVStorage[CommunitySchema],
) -> List[Dict[str, Any]]:
    """
    Select communities connected to entities and truncate by token budget.
    """
    import asyncio

    related_communities = []
    for node_data in node_datas:
        if "clusters" not in node_data:
            continue
        try:
            related_communities.extend(json.loads(node_data["clusters"]))
        except (json.JSONDecodeError, TypeError):
            continue

    related_community_dup_keys = [
        str(dp["cluster"])
        for dp in related_communities
        if isinstance(dp, dict)
        and dp.get("cluster") is not None  # 防止缺少 cluster 键
        and dp.get("level") is not None
        and dp["level"] <= query_param.level
    ]
    related_community_keys_counts = dict(Counter(related_community_dup_keys))

    fetched = await asyncio.gather(
        *[community_reports.get_by_id(key) for key in related_community_keys_counts.keys()]
    )
    related_community_datas = {
        key: value
        for key, value in zip(related_community_keys_counts.keys(), fetched)
        if value is not None
    }
    # 只对已成功加载的社区做排序，避免 KeyError
    related_community_keys = sorted(
        related_community_datas.keys(),
        key=lambda key: (
            related_community_keys_counts[key],
            related_community_datas[key]["report_json"].get("rating", -1)
            if isinstance(related_community_datas[key].get("report_json"), dict)
            else -1,
        ),
        reverse=True,
    )
    sorted_community_datas = [related_community_datas[key] for key in related_community_keys]

    tiktoken_model = get_tiktoken_encoder("gpt-4o")
    use_community_reports = truncate_list_by_token_size(
        sorted_community_datas,
        query_param.local_max_token_for_community_report,
        tiktoken_model,
        key=lambda item: item.get("report_string", ""),
    )
    if query_param.local_community_single_one:
        use_community_reports = use_community_reports[:1]
    return use_community_reports

