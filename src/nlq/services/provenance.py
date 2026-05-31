"""Shared per-triple provenance extraction — single source of truth.

The per-triple provenance contract (AAM Blueprint v3.1 §9.2) is the set of
fields that travel with each contributing triple so any consumer can answer
"which source / field / pipe / fabric plane produced this number, and how
confidently". The canonical set is the 5 fields below.

Before this module the field set was duplicated (and had drifted) across the
dashboard data resolver, the persona dashboard resolver, and was absent from
the Ask path entirely. Defining it once here keeps every surface — Ask,
dimensional dashboards, persona dashboards — extracting provenance identically.
Resolvers that also carry the R5 resolution chain (canonical_id,
resolution_method, resolution_confidence) extend this tuple at their call site.

A1 compliance: extraction never fabricates a missing field. A row that carries
no provenance returns None (not an empty dict, not zero-filled defaults), so a
consumer can tell "no provenance available" from "provenance says zero".
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

# The 5 canonical per-triple provenance fields (AAM Blueprint v3.1 §9.2).
PROVENANCE_FIELDS: tuple[str, ...] = (
    "source_system",
    "source_field",
    "pipe_id",
    "fabric_plane",
    "confidence_score",
)


def prov_from_triple(
    item: Dict[str, Any],
    fields: Sequence[str] = PROVENANCE_FIELDS,
) -> Optional[Dict[str, Any]]:
    """Pull per-triple provenance off one DCL response row / triple.

    Returns a dict containing only the requested fields that are actually
    present on the item (partial provenance is honest surfacing — A1: never
    invent a value for a missing field), or None when the item carries none of
    them (a legacy or aggregated row with no provenance to surface).

    Args:
        item: a DCL data row or triple dict.
        fields: which provenance fields to extract. Defaults to the 5 canonical
            fields; resolvers pass an extended tuple to also pull the R5
            resolution-chain fields.
    """
    prov = {f: item.get(f) for f in fields if item.get(f) is not None}
    return prov or None
