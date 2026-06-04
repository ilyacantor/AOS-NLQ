"""
Entity-aware dashboard generation.

A generated dashboard schema describes the tiles a persona query asked for (revenue,
gross margin, pipeline, by-region breakdowns, …). Whether the CURRENT entity actually
carries each of those concepts is a separate question — a four-fabric entity has no
P&L, a financial entity has no support fabric. This module drops the tiles whose DCL
concept the current entity does not carry, so no absent/speculative tile is ever shown.

Crucially it distinguishes ABSENT from BROKEN:
  - absent  → the entity has zero triples for the concept (any period) → DROP the tile.
  - broken  → the concept EXISTS but fails to resolve for the queried period → KEEP it,
              so the tile surfaces its real error rather than being silently hidden.
The carried check is "does the entity have this concept for ANY period", so a
genuinely-broken tile (concept present, period missing) is never masked.

Fails OPEN: if DCL is unreachable or a widget cannot be classified, the tile is kept
(we never drop a tile we are unsure about).
"""

import logging
import os
import threading
import time
from typing import Optional

import httpx

from src.nlq.services.dcl_semantic_client_v2 import METRIC_CONCEPT_MAP, resolve_metric_name

logger = logging.getLogger(__name__)

# Per-(entity, tenant, domain) concept cache — entity↔concepts is stable within a run,
# so the first dashboard pays the browse and the rest are free.
_CONCEPT_CACHE: dict = {}
_CONCEPT_CACHE_TS: dict = {}
_CONCEPT_TTL_S = 60.0
_CACHE_LOCK = threading.Lock()

# Widget types whose value is a metric's own concept (direct or derived components).
_SCALAR_TYPES = {"kpi_card", "line_chart", "area_chart", "sparkline", "data_table"}
# Widget types whose value is a {metric}.by_{dimension} breakdown.
_BREAKDOWN_TYPES = {"bar_chart", "horizontal_bar", "donut_chart", "stacked_bar", "map"}


def _widget_type(widget) -> str:
    wt = getattr(widget, "type", None)
    return wt.value if hasattr(wt, "value") else str(wt)


def _widget_required_concepts(widget) -> Optional[list]:
    """[(concept, needs_series)] — every concept must be carried for the tile to have
    data; needs_series=True (line/area trends) additionally requires the concept to
    have a quarterly (non-atemporal) period, since a single atemporal value renders no
    trend. Returns None when the widget cannot be classified (unknown type / unmapped
    metric / missing dimension), so the caller keeps it (fail open)."""
    wt = _widget_type(widget)

    # Sales funnel reads customer.pipeline.{stage} (DCLSemanticClientV2.get_pipeline_stages).
    if wt == "sales_funnel":
        return [("customer.pipeline", False)]

    data = getattr(widget, "data", None)
    metrics = list(getattr(data, "metrics", None) or [])
    if not metrics:
        return None  # nothing to classify — keep

    needs_series = wt in ("line_chart", "area_chart")
    required: list = []
    for mb in metrics:
        metric = mb.metric
        canonical = resolve_metric_name(metric) or metric
        defn = METRIC_CONCEPT_MAP.get(canonical)

        if wt in _SCALAR_TYPES:
            if not defn:
                return None  # unmapped metric — don't guess, keep the tile
            if defn.get("type") == "derived":
                comps = [c.get("concept") for c in defn.get("components", []) if c.get("concept")]
                if not comps:
                    return None
                required.extend((c, needs_series) for c in comps)  # derived needs ALL components
            elif defn.get("concept"):
                required.append((defn["concept"], needs_series))
            else:
                return None
        elif wt in _BREAKDOWN_TYPES:
            if wt == "map":
                dimension = "region"
            else:
                dims = list(getattr(data, "dimensions", None) or [])
                dimension = dims[0].dimension if dims else None
            if not dimension:
                return None  # breakdown without a dimension — keep
            # The resolver queries f"{metric}.by_{dimension}" (e.g. revenue.by_region).
            required.append((f"{metric}.by_{dimension}", False))
        else:
            return None  # unknown widget type — keep

    return required or None


def _browse_domain_concept_periods(base_url: str, tenant_id: str, entity_id: str, domain: str) -> Optional[dict]:
    """{concept: set(periods)} the entity has in one domain. The browse endpoint ignores
    a `concept` query param, so this lists the domain's triples and groups periods by
    concept (so a trend can require a non-atemporal period). limit is capped at 500 by
    DCL; the persona-dashboard domains are well under that. None on DCL error (caller
    fails open). Cached per (entity, domain)."""
    key = (entity_id, tenant_id, domain)
    now = time.monotonic()
    with _CACHE_LOCK:
        if key in _CONCEPT_CACHE and (now - _CONCEPT_CACHE_TS.get(key, 0.0)) < _CONCEPT_TTL_S:
            return _CONCEPT_CACHE[key]
    try:
        resp = httpx.get(
            f"{base_url}/api/dcl/triples/browse",
            params={"tenant_id": tenant_id, "entity_id": entity_id, "domain": domain, "limit": 500},
            timeout=8.0,
        )
        resp.raise_for_status()
        concept_periods: dict = {}
        for t in resp.json().get("triples", []):
            c = t.get("concept")
            if c:
                concept_periods.setdefault(c, set()).add(t.get("period"))
    except (httpx.HTTPError, ValueError, KeyError):
        return None
    with _CACHE_LOCK:
        _CONCEPT_CACHE[key] = concept_periods
        _CONCEPT_CACHE_TS[key] = now
    return concept_periods


def filter_dashboard_to_entity(schema, entity_id: Optional[str], tenant_id: Optional[str]):
    """Drop tiles whose concept the entity does not carry. Mutates and returns schema.

    No-op (keeps every tile) when there is no single entity to scope to (combined / no
    identity), when DCL is unreachable, or for any tile that cannot be classified."""
    if not entity_id or entity_id == "combined" or not tenant_id:
        return schema

    widgets = list(getattr(schema, "widgets", None) or [])
    if not widgets:
        return schema

    per_widget = [(w, _widget_required_concepts(w)) for w in widgets]
    domains = {c.split(".")[0] for _, reqs in per_widget if reqs for c, _ in reqs}
    if not domains:
        return schema

    base_url = os.environ.get("DCL_API_URL", "").rstrip("/")
    if not base_url:
        return schema  # cannot check — fail open

    # Browse the needed domains SEQUENTIALLY (not parallel): the aos-dev pooler is small
    # (15 clients) and the resolver fans out right after — piling concurrent connections
    # here exhausts and wedges it (#39). These are cached, so only the first dashboard pays.
    carried: dict = {}  # {concept: set(periods)}
    for domain in domains:
        cp = _browse_domain_concept_periods(base_url, tenant_id, entity_id, domain)
        if cp is None:
            return schema  # a domain browse failed → fail open, keep all tiles
        for concept, periods in cp.items():
            carried.setdefault(concept, set()).update(periods)

    def _match(concept: str, needs_series: bool) -> bool:
        # carried iff the entity has the concept exactly or as a parent of a sub-concept,
        # matching how the resolver reads it: "revenue.by_region" → "revenue.by_region.amer",
        # "customer.pipeline" → "customer.pipeline.{stage}", "pnl.net_income" → itself. A
        # trend (needs_series) additionally requires a non-atemporal (quarterly) period.
        for e, periods in carried.items():
            if e == concept or e.startswith(concept + "."):
                if not needs_series or any(p for p in periods):
                    return True
        return False

    kept = []
    dropped = []
    for widget, reqs in per_widget:
        if reqs is None or all(_match(c, ns) for c, ns in reqs):
            kept.append(widget)
        else:
            dropped.append(getattr(widget, "title", None) or _widget_type(widget))

    if dropped:
        logger.info(
            "Entity-aware dashboard: %s carries %d/%d tiles; dropped absent-concept tiles: %s",
            entity_id, len(kept), len(per_widget), dropped,
        )
    schema.widgets = kept
    return schema
