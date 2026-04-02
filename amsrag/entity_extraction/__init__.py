"""
Entity extraction module.

This package intentionally uses lazy imports so that importing `amsrag`
does not require DSPy unless entity extraction is actually invoked.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


async def extract_entities(*args: Any, **kwargs: Any):
    """Lazily dispatch to the default entity extraction implementation."""
    module = import_module(".extract", __name__)
    return await module.extract_entities(*args, **kwargs)


async def generate_dataset(*args: Any, **kwargs: Any):
    """Lazily dispatch to dataset generation implementation."""
    module = import_module(".extract", __name__)
    return await module.generate_dataset(*args, **kwargs)


async def extract_entities_dspy(*args: Any, **kwargs: Any):
    """Lazily dispatch to DSPy-based entity extraction."""
    module = import_module(".extract", __name__)
    return await module.extract_entities_dspy(*args, **kwargs)


_LAZY_EXPORTS = {
    "Entity": ".module",
    "Relationship": ".module",
    "CombinedExtraction": ".module",
    "CritiqueCombinedExtraction": ".module",
    "RefineCombinedExtraction": ".module",
    "TypedEntityRelationshipExtractor": ".module",
    "TypedEntityRelationshipExtractorException": ".module",
    "relationships_similarity_metric": ".metric",
    "entity_recall_metric": ".metric",
    "AssessRelationships": ".metric",
}


def __getattr__(name: str):
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name, __name__)
    return getattr(module, name)


def __dir__():
    return sorted(list(globals().keys()) + list(_LAZY_EXPORTS.keys()))


__all__ = [
    "extract_entities",
    "generate_dataset",
    "extract_entities_dspy",
    "Entity",
    "Relationship",
    "CombinedExtraction",
    "CritiqueCombinedExtraction",
    "RefineCombinedExtraction",
    "TypedEntityRelationshipExtractor",
    "TypedEntityRelationshipExtractorException",
    "relationships_similarity_metric",
    "entity_recall_metric",
    "AssessRelationships",
]
