"""
DCL Client Router — routes NLQ queries to v2 client (triples) or old client.

v2 handles: all metric queries, dashboards, financial statements, reports.
Old handles: catalog operations, graph resolution, metric negotiation, search.

No silent fallback from v2 to old.  If v2 can't resolve a metric, it returns
a structured error — not a quiet redirect to the legacy path.
"""

import logging
from typing import Any, Dict, List, Optional, Set

from src.nlq.services.dcl_semantic_client import DCLSemanticClient, _entity_id_ctx
from src.nlq.services.dcl_semantic_client_v2 import (
    DCLSemanticClientV2,
    resolve_metric_name,
)

logger = logging.getLogger(__name__)


class DCLClientRouter:
    """Routes queries to v2 (triple-based) or old (catalog-based) client.

    The v2 client is the primary path for all metric/data queries.
    The old client is retained for catalog operations that v2 doesn't
    yet replace (catalog browsing, graph resolution, metric search).
    """

    def __init__(self, v2: DCLSemanticClientV2, old: DCLSemanticClient):
        self.v2 = v2
        self.old = old

    # ------------------------------------------------------------------
    # Metric queries — always v2
    # ------------------------------------------------------------------

    def get_metric(self, metric_name: str, **kwargs) -> Dict[str, Any]:
        """Resolve a metric via v2 triples."""
        return self.v2.get_metric(metric_name, **kwargs)

    def get_metric_timeseries(self, metric_name: str, **kwargs) -> List[Dict[str, Any]]:
        """Get metric timeseries via v2 triples."""
        return self.v2.get_metric_timeseries(metric_name, **kwargs)

    def get_derived_metric(self, metric_name: str, **kwargs) -> Dict[str, Any]:
        """Compute derived metric from v2 triples."""
        return self.v2.get_derived_metric(metric_name, **kwargs)

    def get_dashboard_metrics(self, persona: str, **kwargs) -> List[Dict[str, Any]]:
        """Get persona dashboard metrics via v2."""
        return self.v2.get_dashboard_metrics(persona, **kwargs)

    # ------------------------------------------------------------------
    # Financial statements — always v2
    # ------------------------------------------------------------------

    def get_income_statement(self, **kwargs) -> Dict[str, Any]:
        return self.v2.get_income_statement(**kwargs)

    def get_balance_sheet(self, **kwargs) -> Dict[str, Any]:
        return self.v2.get_balance_sheet(**kwargs)

    def get_cash_flow(self, **kwargs) -> Dict[str, Any]:
        return self.v2.get_cash_flow(**kwargs)

    # ------------------------------------------------------------------
    # Reports — always v2
    # ------------------------------------------------------------------

    def get_overlap(self) -> Dict[str, Any]:
        return self.v2.get_overlap()

    def get_cross_sell(self) -> Dict[str, Any]:
        return self.v2.get_cross_sell()

    def get_ebitda_bridge(self, **kwargs) -> Dict[str, Any]:
        return self.v2.get_ebitda_bridge(**kwargs)

    def get_qoe(self, **kwargs) -> Dict[str, Any]:
        return self.v2.get_qoe(**kwargs)

    # ------------------------------------------------------------------
    # Catalog / search — old client (v2 doesn't replace these yet)
    # ------------------------------------------------------------------

    def get_catalog(self):
        """Get semantic catalog (still from old client's cached catalog)."""
        return self.old.get_catalog()

    def resolve_metric(self, user_term: str, **kwargs):
        """Resolve user term to canonical metric.

        Tries v2 metric map first, falls back to old catalog.
        Accepts **kwargs for backward compatibility with callers
        passing local_only or other flags.
        """
        canonical = resolve_metric_name(user_term)
        if canonical is not None:
            return {"id": canonical, "source": "v2_metric_map"}
        return self.old.resolve_metric(user_term, **kwargs)

    def validate_metrics(self, metric_ids: list):
        """Validate a list of metric IDs — delegates to old client."""
        return self.old.validate_metrics(metric_ids)

    def search(self, term: str, **kwargs):
        """Semantic search — delegates to old client."""
        return self.old.search(term, **kwargs)

    def resolve_entity(self, entity_term: str, **kwargs):
        """Entity resolution — delegates to old client."""
        return self.old.resolve_entity(entity_term, **kwargs)

    def resolve_via_graph(self, **kwargs):
        """Graph resolution — delegates to old client."""
        return self.old.resolve_via_graph(**kwargs)

    def check_dcl_health(self):
        """Health check — delegates to old client."""
        return self.old.check_dcl_health()

    def validate_dimension(self, metric: str, dimension: str):
        """Dimension validation — delegates to old catalog."""
        return self.old.validate_dimension(metric, dimension)

    def resolve_dimension(self, user_term: str):
        """Dimension resolution — delegates to old catalog."""
        return self.old.resolve_dimension(user_term)

    def get_valid_dimensions(self, metric_id: str):
        """Get valid dimensions for a metric — delegates to old catalog."""
        return self.old.get_valid_dimensions(metric_id)

    # ------------------------------------------------------------------
    # v1-compatible query() — translates old-style calls to v2
    # ------------------------------------------------------------------

    def query(
        self,
        metric: str,
        dimensions: List[str] = None,
        filters: Dict[str, Any] = None,
        time_range: Dict[str, Any] = None,
        grain: str = None,
        order_by: str = None,
        limit: int = None,
        tenant_id: str = None,
        entity_id: str = None,
    ) -> Dict[str, Any]:
        """v1-compatible query interface that routes through v2 triples.

        Translates the old DCLSemanticClient.query() call signature into
        v2 get_metric() calls so that executor.py and routes.py work
        without changes to their call sites.
        """
        # Auto-read entity_id from context when not explicitly provided
        if entity_id is None:
            entity_id = _entity_id_ctx.get()

        # Extract period from time_range
        period = None
        if time_range:
            period = time_range.get("period")
            if not period:
                # DCL format: {start, end}
                period = time_range.get("start")

        # Check if v2 knows this metric
        canonical = resolve_metric_name(metric)
        if canonical is None:
            # Try old client's metric negotiation
            negotiated = self.old._negotiate_metric_id(metric)
            canonical = resolve_metric_name(negotiated)

        if canonical is not None:
            # Route through v2
            try:
                v2_result = self.v2.get_metric(canonical, entity_id=entity_id, period=period)

                if v2_result.get("value") is not None:
                    # Translate v2 response to v1 format for executor compatibility
                    return {
                        "metric": metric,
                        "data": [{"period": v2_result.get("period", period), "value": v2_result["value"]}],
                        "data_source": "dcl_v2",
                        "metadata": {
                            "source": "dcl_v2",
                            "concept": v2_result.get("concept"),
                            "confidence_score": v2_result.get("confidence_score"),
                            "confidence_tier": v2_result.get("confidence_tier"),
                            "source_system": v2_result.get("source_system"),
                        },
                    }
                else:
                    # v2 found the metric definition but no data
                    error_msg = v2_result.get("error", f"No data for metric '{metric}'")
                    logger.warning(f"DCL v2 metric query returned no value: {error_msg}")
                    return {
                        "error": error_msg,
                        "status": "no_data",
                        "data_source": "dcl_v2",
                    }

            except ValueError as e:
                # Formula computation error (e.g. division by zero)
                logger.warning(f"DCL v2 derived metric error: {e}")
                return {"error": str(e), "status": "error", "data_source": "dcl_v2"}

            except RuntimeError as e:
                # DCL HTTP error — surface it, don't fall back silently
                logger.error(f"DCL v2 HTTP error for metric '{metric}': {e}")
                return {"error": str(e), "status": "error", "data_source": "dcl_v2"}

        # Metric not in v2 concept map — use old client
        # This is NOT a silent fallback: we log it explicitly so we can
        # identify metrics that need to be added to the concept map.
        logger.info(
            f"Metric '{metric}' not in v2 metric_concept_map — "
            f"routing to legacy DCL client"
        )
        return self.old.query(
            metric=metric,
            dimensions=dimensions,
            filters=filters,
            time_range=time_range,
            grain=grain,
            order_by=order_by,
            limit=limit,
            tenant_id=tenant_id,
            entity_id=entity_id,
        )

    # ------------------------------------------------------------------
    # Passthrough for old client methods used by executor/routes
    # ------------------------------------------------------------------

    def _negotiate_metric_id(self, metric: str) -> str:
        """Metric name negotiation — checks v2 map then old catalog."""
        canonical = resolve_metric_name(metric)
        if canonical is not None:
            return canonical
        return self.old._negotiate_metric_id(metric)

    def get_ingest_runs(self, **kwargs):
        """Ingest run info — old client."""
        return self.old.get_ingest_runs(**kwargs)

    def get_latest_period(self) -> str:
        """Latest available period — old client."""
        return self.old.get_latest_period()

    def query_ranking(self, **kwargs):
        """Ranking queries — old client."""
        return self.old.query_ranking(**kwargs)


# ---------------------------------------------------------------------------
# Singleton — drop-in replacement for get_semantic_client()
# ---------------------------------------------------------------------------

_routed_client: Optional[DCLClientRouter] = None


def get_routed_client() -> DCLClientRouter:
    """Return the singleton DCLClientRouter.

    This is the drop-in replacement for get_semantic_client().
    Callers that import this get v2 triple resolution for all known
    metrics, with catalog/search/graph falling through to the old client.
    """
    global _routed_client
    if _routed_client is None:
        from src.nlq.services.dcl_semantic_client import get_semantic_client
        from src.nlq.services.dcl_semantic_client_v2 import get_semantic_client_v2

        old = get_semantic_client()
        v2 = get_semantic_client_v2()
        _routed_client = DCLClientRouter(v2=v2, old=old)
    return _routed_client
