"""
DCL Semantic Client v2 — queries triple-based v2 endpoints.

All metric resolution goes through DCL's semantic_triples table via v2
report and browse endpoints.  No hardcoded hierarchy, system-of-record,
or dimension data — those are DCL's responsibility (RACI).

Metric name → DCL concept mapping is loaded from
src/nlq/config/metric_concept_map.yaml.
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Metric concept map loader
# ---------------------------------------------------------------------------

def _load_metric_concept_map() -> Dict[str, Dict[str, Any]]:
    """Load metric_concept_map.yaml — raises RuntimeError if missing/bad."""
    yaml_path = Path(__file__).resolve().parent.parent / "config" / "metric_concept_map.yaml"
    try:
        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        raise RuntimeError(
            f"metric_concept_map.yaml not found at {yaml_path} — "
            "cannot resolve NLQ metric names to DCL concepts"
        )
    except Exception as e:
        raise RuntimeError(
            f"Failed to parse metric_concept_map.yaml at {yaml_path}: {e}"
        )

    if not data or not isinstance(data, dict):
        raise RuntimeError(
            f"metric_concept_map.yaml at {yaml_path} is empty or not a mapping"
        )

    # Build alias reverse-index
    for metric_name, defn in data.items():
        if not isinstance(defn, dict):
            raise RuntimeError(
                f"metric_concept_map.yaml: entry '{metric_name}' is not a mapping"
            )
        defn.setdefault("aliases", [])

    return data


METRIC_CONCEPT_MAP: Dict[str, Dict[str, Any]] = _load_metric_concept_map()

# Build alias → canonical name index
_ALIAS_INDEX: Dict[str, str] = {}
for _metric_name, _defn in METRIC_CONCEPT_MAP.items():
    _ALIAS_INDEX[_metric_name.lower()] = _metric_name
    for _alias in _defn.get("aliases", []):
        _ALIAS_INDEX[_alias.lower()] = _metric_name


def resolve_metric_name(user_term: str) -> Optional[str]:
    """Resolve a user-supplied metric term to the canonical metric name.

    Returns None if the term is not recognized — caller must handle.
    """
    return _ALIAS_INDEX.get(user_term.lower())


# ---------------------------------------------------------------------------
# V2 Client
# ---------------------------------------------------------------------------

class DCLSemanticClientV2:
    """Queries DCL v2 triple-based endpoints.

    No hardcoded semantic data.  Hierarchy, system-of-record, and dimension
    information come from DCL at runtime.
    """

    def __init__(self, dcl_base_url: Optional[str] = None):
        raw_url = dcl_base_url or os.environ.get("DCL_API_URL")
        if not raw_url:
            raise RuntimeError(
                "DCL_API_URL not configured — DCLSemanticClientV2 requires a DCL endpoint. "
                "Set DCL_API_URL environment variable."
            )
        self.base_url = raw_url.rstrip("/")
        self._http = httpx.Client(base_url=self.base_url, timeout=30.0)
        logger.info(f"DCLSemanticClientV2 initialized — endpoint: {self.base_url}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """GET request to DCL. Raises on non-2xx."""
        resp = self._http.get(path, params=params)
        if resp.status_code >= 400:
            raise RuntimeError(
                f"DCL v2 GET {self.base_url}{path} returned {resp.status_code}: "
                f"{resp.text[:500]}"
            )
        return resp.json()

    def _post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """POST request to DCL. Raises on non-2xx."""
        resp = self._http.post(path, json=body)
        if resp.status_code >= 400:
            raise RuntimeError(
                f"DCL v2 POST {self.base_url}{path} returned {resp.status_code}: "
                f"{resp.text[:500]}"
            )
        return resp.json()

    def _resolve_metric_def(self, metric_name: str) -> Dict[str, Any]:
        """Look up a metric in the concept map. Returns the definition dict.

        Tries the name directly, then via alias index.
        Raises ValueError if the metric is unknown.
        """
        canonical = resolve_metric_name(metric_name)
        if canonical is None:
            raise ValueError(
                f"Unknown metric '{metric_name}' — not found in metric_concept_map.yaml. "
                f"Available: {', '.join(sorted(METRIC_CONCEPT_MAP.keys())[:20])}..."
            )
        return METRIC_CONCEPT_MAP[canonical]

    _RE_BARE_YEAR = re.compile(r"^20\d{2}$")

    def _is_bare_year(self, period: Optional[str]) -> bool:
        """Check if period is a bare year like '2025' (not quarterly '2025-Q1')."""
        return bool(period and self._RE_BARE_YEAR.match(str(period)))

    def _expand_year_to_quarters(self, year: str) -> List[str]:
        """Expand '2025' → ['2025-Q1', '2025-Q2', '2025-Q3', '2025-Q4']."""
        return [f"{year}-Q{q}" for q in range(1, 5)]

    def _get_latest_quarter(self) -> Optional[str]:
        """Ask DCL for the latest available period from triples overview."""
        overview = self._get("/api/dcl/triples/overview")
        periods = overview.get("periods", [])
        if not periods:
            return None
        # Periods are strings like "2025-Q1"; sorted lexically = chronologically
        return sorted(periods)[-1]

    def _browse_triple(
        self,
        domain: str,
        entity_id: Optional[str] = None,
        period: Optional[str] = None,
        property_name: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Call /api/dcl/triples/browse with filters."""
        params: Dict[str, Any] = {"domain": domain, "limit": limit}
        if entity_id:
            params["entity_id"] = entity_id
        if period:
            params["period"] = period
        if property_name:
            params["property"] = property_name
        return self._get("/api/dcl/triples/browse", params=params)

    def _extract_triple_value(
        self,
        triples: List[Dict[str, Any]],
        concept: str,
        property_name: str,
    ) -> Optional[Dict[str, Any]]:
        """Find a specific triple by concept + property from a browse result.

        Returns the full triple dict or None.
        """
        for t in triples:
            if t.get("concept") == concept and t.get("property") == property_name:
                return t
        return None

    def _numeric_value(self, triple: Optional[Dict[str, Any]]) -> Optional[float]:
        """Extract numeric value from a triple, handling JSONB encoding."""
        if triple is None:
            return None
        val = triple.get("value")
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            try:
                return float(val)
            except (ValueError, TypeError):
                raise ValueError(
                    f"Triple value '{val}' is not numeric — cannot extract float"
                )
        raise ValueError(
            f"Triple value of type {type(val).__name__} is not numeric — "
            f"cannot extract float"
        )

    # ------------------------------------------------------------------
    # Single metric
    # ------------------------------------------------------------------

    def get_metric(
        self,
        metric_name: str,
        entity_id: Optional[str] = None,
        period: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Resolve a metric name to a value from DCL triples.

        Period handling:
        - Bare year ("2025") → query each quarter, SUM additive / AVG non-additive
        - Quarterly ("2025-Q1") → single query
        - None → default to latest available quarter

        Returns: {value, entity_id, period, confidence_score, confidence_tier,
                  source_system, data_source, metric_name, concept}
        """
        defn = self._resolve_metric_def(metric_name)

        if defn["type"] == "derived":
            return self.get_derived_metric(metric_name, entity_id=entity_id, period=period)

        concept = defn["concept"]
        prop = defn["property"]
        domain = concept.split(".")[0]
        unit = defn.get("unit", "usd")

        # --- Period resolution ---
        if self._is_bare_year(period):
            return self._get_metric_annual(
                metric_name, concept, prop, domain, unit, entity_id, period,
            )

        if period is None:
            period = self._get_latest_quarter()
            if period is None:
                return {
                    "value": None,
                    "error": "No periods available in DCL triples — store may be empty",
                    "metric_name": metric_name,
                    "concept": concept,
                    "data_source": "dcl_v2",
                }

        # --- Single quarter query ---
        return self._get_metric_single_period(
            metric_name, concept, prop, domain, entity_id, period,
        )

    def _get_metric_single_period(
        self,
        metric_name: str,
        concept: str,
        prop: str,
        domain: str,
        entity_id: Optional[str],
        period: str,
    ) -> Dict[str, Any]:
        """Query a single metric for one specific period."""
        browse_result = self._browse_triple(
            domain=domain,
            entity_id=entity_id,
            period=period,
            property_name=prop,
        )
        triples = browse_result.get("triples", [])
        triple = self._extract_triple_value(triples, concept, prop)

        # If no triples found at all, retry without period filter.
        # Some data (e.g. employee headcount) is stored with period=NULL
        # meaning "current state" — period-filtered queries won't find it.
        if not triples and period:
            browse_no_period = self._browse_triple(
                domain=domain,
                entity_id=entity_id,
                period=None,
                property_name=prop,
            )
            triples = browse_no_period.get("triples", [])
            triple = self._extract_triple_value(triples, concept, prop)

        # If no exact concept match but concept is a ".total" aggregate,
        # sum all triples in the domain with the matching property.
        # e.g. employee.total sums employee.sales + employee.finance + ...
        if triple is None and concept.endswith(".total") and triples:
            domain_prefix = concept.rsplit(".total", 1)[0] + "."
            matching = [t for t in triples
                        if t.get("concept", "").startswith(domain_prefix)
                        and t.get("property") == prop]
            if matching:
                total = 0.0
                last = matching[-1]
                for t in matching:
                    val = self._numeric_value(t)
                    if val is not None:
                        total += val
                return {
                    "value": total,
                    "entity_id": entity_id or last.get("entity_id"),
                    "period": last.get("period"),
                    "confidence_score": last.get("confidence_score"),
                    "confidence_tier": last.get("confidence_tier"),
                    "source_system": last.get("source_system"),
                    "data_source": "dcl_v2",
                    "metric_name": metric_name,
                    "concept": concept,
                }

        if triple is None:
            return {
                "value": None,
                "error": (
                    f"No triple found for concept='{concept}', property='{prop}'"
                    f"{f', entity_id={entity_id}' if entity_id else ''}"
                    f", period={period}"
                    f" — domain '{domain}' returned {len(triples)} triples, "
                    f"none matching the target concept"
                ),
                "metric_name": metric_name,
                "concept": concept,
                "data_source": "dcl_v2",
            }

        return {
            "value": self._numeric_value(triple),
            "entity_id": triple.get("entity_id"),
            "period": triple.get("period"),
            "confidence_score": triple.get("confidence_score"),
            "confidence_tier": triple.get("confidence_tier"),
            "source_system": triple.get("source_system"),
            "data_source": "dcl_v2",
            "metric_name": metric_name,
            "concept": concept,
        }

    def _get_metric_annual(
        self,
        metric_name: str,
        concept: str,
        prop: str,
        domain: str,
        unit: str,
        entity_id: Optional[str],
        year: str,
    ) -> Dict[str, Any]:
        """Query a metric across Q1-Q4 of a year. SUM additive, AVG non-additive."""
        quarters = self._expand_year_to_quarters(year)
        values: List[float] = []
        last_triple: Optional[Dict[str, Any]] = None

        for q in quarters:
            browse_result = self._browse_triple(
                domain=domain,
                entity_id=entity_id,
                period=q,
                property_name=prop,
            )
            triples = browse_result.get("triples", [])
            triple = self._extract_triple_value(triples, concept, prop)
            if triple is not None:
                val = self._numeric_value(triple)
                if val is not None:
                    values.append(val)
                    last_triple = triple

        if not values:
            return {
                "value": None,
                "error": (
                    f"No data for '{concept}' across {year} Q1-Q4"
                    f"{f', entity_id={entity_id}' if entity_id else ''}"
                ),
                "metric_name": metric_name,
                "concept": concept,
                "data_source": "dcl_v2",
            }

        # Additive units (money, counts) → SUM; rates/ratios/pcts → AVG
        is_additive = unit in ("usd", "count", "months", "days", "hours", "points")
        aggregated = sum(values) if is_additive else sum(values) / len(values)

        return {
            "value": aggregated,
            "entity_id": entity_id or (last_triple.get("entity_id") if last_triple else None),
            "period": year,
            "confidence_score": last_triple.get("confidence_score") if last_triple else None,
            "confidence_tier": last_triple.get("confidence_tier") if last_triple else None,
            "source_system": last_triple.get("source_system") if last_triple else None,
            "data_source": "dcl_v2",
            "metric_name": metric_name,
            "concept": concept,
            "quarters_found": len(values),
        }

    def get_metric_timeseries(
        self,
        metric_name: str,
        entity_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get a metric across all periods. Returns list of {value, period, ...}."""
        defn = self._resolve_metric_def(metric_name)

        if defn["type"] == "derived":
            raise ValueError(
                f"Timeseries for derived metric '{metric_name}' not yet supported — "
                "use get_metric with explicit period instead"
            )

        concept = defn["concept"]
        prop = defn["property"]
        domain = concept.split(".")[0]

        browse_result = self._browse_triple(
            domain=domain,
            entity_id=entity_id,
            property_name=prop,
            limit=500,
        )
        triples = browse_result.get("triples", [])

        results = []
        for t in triples:
            if t.get("concept") == concept and t.get("property") == prop:
                results.append({
                    "value": self._numeric_value(t),
                    "period": t.get("period"),
                    "entity_id": t.get("entity_id"),
                    "confidence_score": t.get("confidence_score"),
                    "source_system": t.get("source_system"),
                    "data_source": "dcl_v2",
                })
        return results

    # ------------------------------------------------------------------
    # Derived metrics
    # ------------------------------------------------------------------

    def get_derived_metric(
        self,
        metric_name: str,
        entity_id: Optional[str] = None,
        period: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Compute derived metrics from raw triples.

        Each derived metric is computed from raw triples, not looked up.
        Returns the computed value plus the source triples used (provenance).
        """
        defn = self._resolve_metric_def(metric_name)
        if defn["type"] != "derived":
            return self.get_metric(metric_name, entity_id=entity_id, period=period)

        # For derived metrics with bare year, default to latest quarter
        # (formula needs same-period components — annual aggregation not applicable)
        if self._is_bare_year(period) or period is None:
            resolved = self._get_latest_quarter()
            if resolved is None:
                return {
                    "value": None,
                    "error": "No periods available in DCL triples — store may be empty",
                    "metric_name": metric_name,
                    "data_source": "dcl_v2",
                }
            period = resolved

        components = defn.get("components", [])
        formula = defn.get("formula", "")

        # Fetch each component triple
        component_values: Dict[str, float] = {}
        source_triples: List[Dict[str, Any]] = []

        for comp in components:
            comp_concept = comp["concept"]
            comp_prop = comp["property"]
            comp_domain = comp_concept.split(".")[0]

            browse_result = self._browse_triple(
                domain=comp_domain,
                entity_id=entity_id,
                period=period,
                property_name=comp_prop,
            )
            triples = browse_result.get("triples", [])
            triple = self._extract_triple_value(triples, comp_concept, comp_prop)

            if triple is None:
                return {
                    "value": None,
                    "error": (
                        f"Cannot compute derived metric '{metric_name}': "
                        f"missing component concept='{comp_concept}', property='{comp_prop}'"
                        f"{f', entity_id={entity_id}' if entity_id else ''}"
                        f"{f', period={period}' if period else ''}"
                    ),
                    "metric_name": metric_name,
                    "formula": formula,
                    "data_source": "dcl_v2",
                }

            val = self._numeric_value(triple)
            if val is None:
                return {
                    "value": None,
                    "error": (
                        f"Cannot compute derived metric '{metric_name}': "
                        f"component '{comp_concept}' has non-numeric value: {triple.get('value')}"
                    ),
                    "metric_name": metric_name,
                    "formula": formula,
                    "data_source": "dcl_v2",
                }

            component_values[comp_concept] = val
            source_triples.append({
                "concept": comp_concept,
                "property": comp_prop,
                "value": val,
                "entity_id": triple.get("entity_id"),
                "period": triple.get("period"),
                "source_system": triple.get("source_system"),
            })

        # Compute the derived value
        computed = self._compute_formula(metric_name, formula, component_values)

        return {
            "value": computed,
            "entity_id": entity_id,
            "period": period,
            "confidence_score": min(
                (t.get("confidence_score") or 0.0) for t in source_triples
            ) if source_triples else 0.0,
            "confidence_tier": "derived",
            "source_triples": source_triples,
            "formula": formula,
            "data_source": "dcl_v2",
            "metric_name": metric_name,
        }

    def _compute_formula(
        self,
        metric_name: str,
        formula: str,
        values: Dict[str, float],
    ) -> float:
        """Evaluate a derived metric formula.

        Supports the specific formulas in metric_concept_map.yaml.
        Not a general-purpose eval — explicit pattern matching for safety.
        """
        # gross_margin: revenue.total - cogs.total
        if metric_name == "gross_margin":
            return values.get("revenue.total", 0) - values.get("cogs.total", 0)

        # gross_margin_pct: (revenue.total - cogs.total) / revenue.total * 100
        if metric_name == "gross_margin_pct":
            rev = values.get("revenue.total", 0)
            cogs = values.get("cogs.total", 0)
            if rev == 0:
                raise ValueError(
                    f"Cannot compute {metric_name}: revenue.total is zero (division by zero)"
                )
            return (rev - cogs) / rev * 100

        # operating_margin_pct: pnl.ebitda / revenue.total * 100
        if metric_name == "operating_margin_pct":
            ebitda = values.get("pnl.ebitda", 0)
            rev = values.get("revenue.total", 0)
            if rev == 0:
                raise ValueError(
                    f"Cannot compute {metric_name}: revenue.total is zero (division by zero)"
                )
            return ebitda / rev * 100

        # burn_multiple: cash_flow.net_burn / revenue.recurring
        if metric_name == "burn_multiple":
            burn = values.get("cash_flow.net_burn", 0)
            recurring = values.get("revenue.recurring", 0)
            if recurring == 0:
                raise ValueError(
                    f"Cannot compute {metric_name}: revenue.recurring is zero (division by zero)"
                )
            return burn / recurring

        # revenue_per_employee: revenue.total / employee.total
        if metric_name == "revenue_per_employee":
            rev = values.get("revenue.total", 0)
            hc = values.get("employee.total", 0)
            if hc == 0:
                raise ValueError(
                    f"Cannot compute {metric_name}: employee.total is zero (division by zero)"
                )
            return rev / hc

        # cloud_spend_pct_revenue: vendor.cloud_spend / revenue.total * 100
        if metric_name == "cloud_spend_pct_revenue":
            spend = values.get("vendor.cloud_spend", 0)
            rev = values.get("revenue.total", 0)
            if rev == 0:
                raise ValueError(
                    f"Cannot compute {metric_name}: revenue.total is zero (division by zero)"
                )
            return spend / rev * 100

        # magic_number is a multi-period metric — needs special handling
        if metric_name == "magic_number":
            # This requires t and t-1 periods; single-period fallback
            rev = values.get("revenue.total", 0)
            sm = values.get("opex.sales_marketing", 0)
            if sm == 0:
                raise ValueError(
                    f"Cannot compute {metric_name}: opex.sales_marketing is zero (division by zero)"
                )
            return rev / sm

        raise ValueError(
            f"No formula implementation for derived metric '{metric_name}'. "
            f"Formula: {formula}. Add it to _compute_formula()."
        )

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    def get_dashboard_metrics(
        self,
        persona: str,
        entity_id: Optional[str] = None,
        period: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get all key metrics for a persona dashboard.

        Calls persona-stats to know which domains are relevant,
        then fetches key metrics per domain.
        """
        # Get persona domain mapping from DCL
        persona_stats = self._get("/api/dcl/triples/persona-stats")
        persona_upper = persona.upper()

        if persona_upper not in persona_stats:
            raise ValueError(
                f"Unknown persona '{persona}' — available: {', '.join(persona_stats.keys())}"
            )

        domains = persona_stats[persona_upper].get("domain_list", [])

        # Collect metrics whose concepts fall in this persona's domains
        results = []
        for metric_name, defn in METRIC_CONCEPT_MAP.items():
            if defn["type"] == "direct":
                domain = defn["concept"].split(".")[0]
            elif defn["type"] == "derived":
                # For derived, check if any component is in the persona's domains
                comp_domains = {c["concept"].split(".")[0] for c in defn.get("components", [])}
                if not comp_domains.intersection(set(domains)):
                    continue
                domain = None  # Will include it
            else:
                continue

            if domain is not None and domain not in domains:
                continue

            try:
                result = self.get_metric(metric_name, entity_id=entity_id, period=period)
                if result.get("value") is not None:
                    results.append(result)
            except (ValueError, RuntimeError) as e:
                logger.debug(f"Dashboard metric '{metric_name}' skipped: {e}")
                continue

        return results

    # ------------------------------------------------------------------
    # Financial statements
    # ------------------------------------------------------------------

    def get_income_statement(
        self,
        entity_id: Optional[str] = None,
        period: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calls /api/dcl/reports/v2/combining/income-statement."""
        params: Dict[str, Any] = {}
        if period:
            params["period"] = period
        return self._get("/api/dcl/reports/v2/combining/income-statement", params=params)

    def get_balance_sheet(
        self,
        entity_id: Optional[str] = None,
        period: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calls /api/dcl/reports/v2/combining/balance-sheet."""
        params: Dict[str, Any] = {}
        if period:
            params["period"] = period
        return self._get("/api/dcl/reports/v2/combining/balance-sheet", params=params)

    def get_cash_flow(
        self,
        entity_id: Optional[str] = None,
        period: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Calls /api/dcl/reports/v2/combining/cash-flow."""
        params: Dict[str, Any] = {}
        if period:
            params["period"] = period
        return self._get("/api/dcl/reports/v2/combining/cash-flow", params=params)

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------

    def get_overlap(self) -> Dict[str, Any]:
        """Calls /api/dcl/reports/v2/overlap/summary."""
        return self._get("/api/dcl/reports/v2/overlap/summary")

    def get_cross_sell(self) -> Dict[str, Any]:
        """Calls /api/dcl/reports/v2/cross-sell/summary."""
        return self._get("/api/dcl/reports/v2/cross-sell/summary")

    def get_ebitda_bridge(self, entity_id: Optional[str] = None) -> Dict[str, Any]:
        """Calls /api/dcl/reports/v2/bridge."""
        params: Dict[str, Any] = {}
        if entity_id:
            params["entity_id"] = entity_id
        return self._get("/api/dcl/reports/v2/bridge", params=params)

    def get_qoe(self, entity_id: Optional[str] = None) -> Dict[str, Any]:
        """Calls /api/dcl/reports/v2/qoe."""
        params: Dict[str, Any] = {}
        if entity_id:
            params["entity_id"] = entity_id
        return self._get("/api/dcl/reports/v2/qoe", params=params)

    def get_whatif_scenario(
        self,
        entity_id: str,
        period: str,
        adjustments: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Calls POST /api/dcl/reports/v2/whatif/scenario."""
        return self._post("/api/dcl/reports/v2/whatif/scenario", {
            "entity_id": entity_id,
            "period": period,
            "adjustments": adjustments,
        })

    # ------------------------------------------------------------------
    # Raw triple access
    # ------------------------------------------------------------------

    def get_triples_overview(self) -> Dict[str, Any]:
        """Calls /api/dcl/triples/overview — summary stats."""
        return self._get("/api/dcl/triples/overview")

    def get_persona_stats(self) -> Dict[str, Any]:
        """Calls /api/dcl/triples/persona-stats."""
        return self._get("/api/dcl/triples/persona-stats")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self):
        """Close the HTTP client."""
        if self._http:
            self._http.close()
            self._http = None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_v2_client: Optional[DCLSemanticClientV2] = None


def get_semantic_client_v2() -> DCLSemanticClientV2:
    """Return the singleton v2 client instance."""
    global _v2_client
    if _v2_client is None:
        _v2_client = DCLSemanticClientV2()
    return _v2_client
