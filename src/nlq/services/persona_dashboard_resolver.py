"""WS-5 B3 — persona dashboard tile resolver.

For each widget in a persona dashboard (loaded from
src/nlq/config/personas/<persona>.yaml in B1), call the AAM
cross-source-query endpoint (B2) to fetch live triples, then
aggregate per widget type:

  kpi_card        → sum metric across all triples
  bar_chart       → group by dimension, sum metric per bucket
  horizontal_bar  → same as bar_chart, render-time only
  donut_chart     → group by dimension, sum metric per slice
  data_table      → row-per-record, optionally filtered

Per-row provenance is preserved end-to-end. The aggregated data
points carry a `provenance_samples` field with a small set of
representative source-triple provenance dicts so the operator can
drill from any cell back to the originating source.

This resolver does NOT replace the existing DCL-direct widget
resolver (DashboardDataResolver). It runs only for persona
dashboards — identified by the dashboard id prefix `persona_`.
Dynamic `dash_<8hex>` dashboards continue through the existing path.
"""
from __future__ import annotations

import logging
import os
from collections import defaultdict
from typing import Any, Optional

import httpx

from src.nlq.config import get_tenant_id
from src.nlq.models.dashboard_schema import DashboardSchema, Widget, WidgetType

logger = logging.getLogger(__name__)


# Persona metric names → AAM cross-source-query `domain` parameter.
# Operator-friendly metric names live in the persona YAMLs; the
# dispatch-table domain key is what AAM understands.
_METRIC_TO_DOMAIN: dict[str, str] = {
    "ar_outstanding_usd": "invoice",
    "invoice_amount_usd": "invoice",
    "ap_outstanding_usd": "ap_invoice",
    "vendor_spend_usd": "ap_invoice",
    "customer_count": "customer",
    "vendor_count": "vendor",
}


class PersonaDashboardResolver:
    """Stateless. One instance per persona dashboard resolution."""

    def __init__(
        self,
        *,
        aam_base_url: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> None:
        # AAM_BASE_URL points at the AAM service (default localhost:8002 in dev).
        # A1: missing AAM_BASE_URL when persona resolution is attempted raises.
        self._aam_base_url = (
            aam_base_url or os.environ.get("AAM_BASE_URL") or ""
        ).rstrip("/")
        if not self._aam_base_url:
            raise RuntimeError(
                "PersonaDashboardResolver: AAM_BASE_URL not set. Cannot route "
                "tile data through AAM cross-source-query (A1: fail loud)."
            )
        # I2: the AAM cross-source-query endpoint is tenant-scoped (R2) — a
        # tenant_id is required on every call. Resolve from AOS_TENANT_ID when
        # the caller did not pass one; get_tenant_id() raises if none exists.
        self._tenant_id = tenant_id or get_tenant_id()
        # entity_id is data-derived: collected from the AAM cross-source
        # responses during resolve(). The route stamps the I2 pair from
        # tenant_id + resolved_entity_id.
        self._entity_ids_seen: set[str] = set()

    def resolve(self, schema: DashboardSchema) -> dict[str, Any]:
        """Resolve every widget in the dashboard. Returns
        {widget_id: widget_data_dict} mapping. Per-row provenance is
        attached on the widget data points.

        Missing-source surfacing: if a widget's domain query returns
        sources=[] or every requested source missing, the widget's
        result includes a `missing_sources` field so the renderer can
        show an explicit gap instead of an empty tile.
        """
        widget_data: dict[str, Any] = {}
        for widget in schema.widgets:
            try:
                widget_data[widget.id] = self._resolve_widget(widget)
            except Exception as exc:  # noqa: BLE001 — per-widget isolation
                # One failing widget should not nuke the whole dashboard.
                # Surface the error in the widget data; the renderer
                # shows it in-tile. The dashboard-level response stays
                # successful.
                logger.warning(
                    "persona widget %s resolution failed: %s",
                    widget.id, exc,
                )
                widget_data[widget.id] = {
                    "loading": False,
                    "error": f"resolution failed: {exc}",
                }
        return widget_data

    @property
    def resolved_entity_id(self) -> Optional[str]:
        """The entity_id observed across the AAM cross-source responses
        during resolve(). Exactly one distinct non-null id → that id;
        disagreement or no data → None. The route stamps this as the I2
        entity_id alongside tenant_id."""
        ids = {e for e in self._entity_ids_seen if e}
        return next(iter(ids)) if len(ids) == 1 else None

    def _resolve_widget(self, widget: Widget) -> dict[str, Any]:
        """One widget → its data dict. Format depends on widget type."""
        metric_name = self._primary_metric(widget)
        if not metric_name:
            return {"loading": False, "error": "widget has no metric binding"}
        domain = _METRIC_TO_DOMAIN.get(metric_name)
        if domain is None:
            return {
                "loading": False,
                "error": (
                    f"persona metric {metric_name!r} has no domain mapping. "
                    f"Add entry to _METRIC_TO_DOMAIN in persona_dashboard_resolver.py."
                ),
            }
        period = self._period(widget)
        triples_response = self._call_aam_cross_source(
            domain=domain, period=period,
        )
        triples = triples_response.get("triples", []) or []
        sources = triples_response.get("sources", {}) or {}
        missing = triples_response.get("missing_sources", []) or []
        # I2: AAM echoes the entity_id its sources resolved to — accumulate
        # it so the route can stamp the identity pair on the response.
        eid = triples_response.get("entity_id")
        if eid:
            self._entity_ids_seen.add(eid)

        widget_type = widget.type if isinstance(widget.type, str) else widget.type.value

        if widget_type == "kpi_card":
            data = self._aggregate_kpi(triples, metric_name)
        elif widget_type in ("bar_chart", "horizontal_bar", "donut_chart"):
            dim = self._primary_dimension(widget)
            data = self._aggregate_dimensional(triples, dim, metric_name)
        elif widget_type == "data_table":
            dims = [d.dimension for d in widget.data.dimensions]
            filters = dict(widget.data.filters or {})
            data = self._aggregate_table(triples, dims, metric_name, filters)
        else:
            data = {
                "loading": False,
                "error": f"persona resolver: widget type {widget_type!r} not yet wired (B3 covers kpi/bar/donut/table)",
            }
            data["sources"] = sources
            data["missing_sources"] = missing
            return data

        data["sources"] = sources
        data["missing_sources"] = missing
        return data

    # ------------------------------------------------------------------
    # AAM call
    # ------------------------------------------------------------------

    def _call_aam_cross_source(
        self,
        *,
        domain: str,
        period: Optional[str],
        limit_per_source: int = 2000,
    ) -> dict[str, Any]:
        params: list[tuple[str, Any]] = [
            ("tenant_id", self._tenant_id),
            ("domain", domain),
            ("limit_per_source", limit_per_source),
        ]
        if period:
            params.append(("period", period))
        url = f"{self._aam_base_url}/api/aam/cross-source-query"
        with httpx.Client(timeout=15.0) as client:
            r = client.get(url, params=params)
        r.raise_for_status()
        return r.json()

    # ------------------------------------------------------------------
    # Per-widget-type aggregators
    # ------------------------------------------------------------------

    def _aggregate_kpi(
        self, triples: list[dict[str, Any]], metric_name: str,
    ) -> dict[str, Any]:
        """Sum the metric across all triples that match property='amount'.

        Provenance: capture a small set of sample provenance dicts
        (one per source_system) so the drill-through can show which
        sources contributed."""
        property_for_metric = "amount"
        total = 0.0
        sample_provenance: dict[str, dict[str, Any]] = {}
        for t in triples:
            if t.get("property") != property_for_metric:
                continue
            try:
                total += float(t.get("value", 0) or 0)
            except (ValueError, TypeError):
                continue
            src = t.get("_source_system_display") or t.get("source_system") or "unknown"
            if src not in sample_provenance:
                sample_provenance[src] = _prov_from_triple(t)
        return {
            "loading": False,
            "value": round(total, 2),
            "metric": metric_name,
            "provenance_samples": sample_provenance,
        }

    def _aggregate_dimensional(
        self,
        triples: list[dict[str, Any]],
        dimension: Optional[str],
        metric_name: str,
    ) -> dict[str, Any]:
        """Group triples by dimension value, sum amount per group.

        dimension is taken from the widget's `data.dimensions[0]` —
        either a source-field name (e.g. 'aging_bucket') OR a
        provenance-derived dimension ('source_system'). The aggregator
        handles both: triples carry source_system as a provenance field,
        so grouping by source_system uses the provenance value; other
        dimensions group by the matching property's value across triples
        sharing the same record_key.
        """
        if not dimension:
            return {"loading": False, "error": "widget has no dimension binding"}
        # Special case: source_system is a provenance field, not a property.
        if dimension == "source_system":
            return self._group_by_source_system(triples, metric_name)
        # General case: triples are per-property. To group by `aging_bucket`,
        # we need to join the amount-property triple to its same-record
        # aging_bucket-property triple. We do this by entity_id+concept
        # since each invoice (entity_id) has both properties as separate
        # triples in the same batch.
        return self._group_by_property_dimension(triples, dimension, metric_name)

    def _group_by_source_system(
        self, triples: list[dict[str, Any]], metric_name: str,
    ) -> dict[str, Any]:
        sums: dict[str, float] = defaultdict(float)
        samples: dict[str, dict[str, Any]] = {}
        for t in triples:
            if t.get("property") != "amount":
                continue
            src = t.get("_source_system_display") or t.get("source_system") or "unknown"
            try:
                sums[src] += float(t.get("value", 0) or 0)
            except (ValueError, TypeError):
                continue
            if src not in samples:
                samples[src] = _prov_from_triple(t)
        breakdown = [
            {"label": k, "value": round(v, 2), "provenance": samples.get(k)}
            for k, v in sorted(sums.items(), key=lambda kv: -kv[1])
        ]
        total = sum(sums.values()) or 1
        for row in breakdown:
            row["ratio"] = round(row["value"] / total, 2)
        return {"loading": False, "breakdown": breakdown, "metric": metric_name}

    def _group_by_property_dimension(
        self,
        triples: list[dict[str, Any]],
        dimension: str,
        metric_name: str,
    ) -> dict[str, Any]:
        """Join amount triples to dimension triples by entity_id.

        Each invoice record has multiple triples in the same batch
        (one per property). We index dimension triples by entity_id,
        then walk amount triples summing per dimension value.
        """
        # Index: entity_id → dimension value
        dim_by_entity: dict[str, str] = {}
        for t in triples:
            if t.get("property") != dimension:
                continue
            eid = t.get("entity_id") or t.get("subject")
            if eid is not None:
                dim_by_entity[str(eid)] = str(t.get("value", "unknown"))
        sums: dict[str, float] = defaultdict(float)
        samples: dict[str, dict[str, Any]] = {}
        for t in triples:
            if t.get("property") != "amount":
                continue
            eid = t.get("entity_id") or t.get("subject")
            bucket = dim_by_entity.get(str(eid), "unknown")
            try:
                sums[bucket] += float(t.get("value", 0) or 0)
            except (ValueError, TypeError):
                continue
            if bucket not in samples:
                samples[bucket] = _prov_from_triple(t)
        breakdown = [
            {"label": k, "value": round(v, 2), "provenance": samples.get(k)}
            for k, v in sorted(sums.items(), key=lambda kv: -kv[1])
        ]
        total = sum(sums.values()) or 1
        for row in breakdown:
            row["ratio"] = round(row["value"] / total, 2)
        return {"loading": False, "breakdown": breakdown, "metric": metric_name}

    def _aggregate_table(
        self,
        triples: list[dict[str, Any]],
        dimensions: list[str],
        metric_name: str,
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        """Row-per-record table. Reconstruct each record by joining
        triples sharing entity_id; apply filters from the widget config."""
        # Group all triples by entity_id, accumulating property values
        records: dict[str, dict[str, Any]] = defaultdict(dict)
        for t in triples:
            eid = t.get("entity_id") or t.get("subject")
            if eid is None:
                continue
            eid = str(eid)
            prop = t.get("property")
            if prop:
                records[eid][prop] = t.get("value")
            # Preserve a representative provenance per record
            if "_provenance" not in records[eid]:
                records[eid]["_provenance"] = _prov_from_triple(t)
        # Apply filters
        rows: list[dict[str, Any]] = []
        for eid, rec in records.items():
            keep = True
            for fkey, fval in filters.items():
                if str(rec.get(fkey, "")) != str(fval):
                    keep = False
                    break
            if not keep:
                continue
            row: dict[str, Any] = {"entity_id": eid}
            for dim in dimensions:
                row[dim] = rec.get(dim)
            row["amount"] = rec.get("amount")
            row["provenance"] = rec.pop("_provenance", None)
            rows.append(row)
        return {"loading": False, "rows": rows, "metric": metric_name}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _primary_metric(self, widget: Widget) -> Optional[str]:
        if not widget.data or not widget.data.metrics:
            return None
        return widget.data.metrics[0].metric

    def _primary_dimension(self, widget: Widget) -> Optional[str]:
        if not widget.data or not widget.data.dimensions:
            return None
        return widget.data.dimensions[0].dimension

    def _period(self, widget: Widget) -> Optional[str]:
        if widget.data and widget.data.time and widget.data.time.period:
            return widget.data.time.period
        return None


_PROVENANCE_FIELDS = (
    "source_system", "source_field", "pipe_id",
    "fabric_plane", "confidence_score",
    # R5: resolution chain — WS-5 dropped these at the NLQ tile. canonical_id
    # is the entity-resolution key; resolution_method/resolution_confidence
    # record how and how confidently the triple was resolved to it.
    "canonical_id", "resolution_method", "resolution_confidence",
)


def _prov_from_triple(t: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Pull the 5 provenance fields from a triple. Returns None when
    none are present (don't fabricate)."""
    prov = {f: t.get(f) for f in _PROVENANCE_FIELDS if t.get(f) is not None}
    # Also include the aggregator tags so drill-through has full context
    for tag in ("_source_system_display", "_vendor", "_batch_id"):
        if t.get(tag) is not None:
            prov[tag.lstrip("_")] = t[tag]
    return prov or None
