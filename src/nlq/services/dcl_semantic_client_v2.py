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
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import yaml

from src.nlq.services.dcl_semantic_client import propagate_context

logger = logging.getLogger(__name__)


class MetricsBatchResult(dict):
    """Dict subclass that also carries confidence metadata from source triples.

    Used by get_metrics_batch() so callers get {metric: value} dict behavior
    plus .min_confidence_score and .min_confidence_tier from the actual data.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.min_confidence_score: Optional[float] = None
        self.min_confidence_tier: Optional[str] = None


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
        # Convergence client for ME mode — browse calls route here when
        # EntityRegistry detects two entities (acquirer + target).
        convergence_url = os.environ.get("CONVERGENCE_API_URL", "").rstrip("/")
        if convergence_url:
            self._convergence_http: Optional[httpx.Client] = httpx.Client(
                base_url=convergence_url, timeout=30.0,
            )
            self._convergence_base_url = convergence_url
            logger.info(
                "DCLSemanticClientV2 ME routing enabled — Convergence: %s",
                convergence_url,
            )
        else:
            self._convergence_http = None
            self._convergence_base_url = ""
        # Browse cache: key → (expire_time, response_dict)
        self._browse_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._browse_cache_lock = threading.Lock()
        self._browse_cache_ttl = 120  # seconds
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

    def _resolve_browse_target(self) -> Tuple[httpx.Client, str, Optional[str]]:
        """Return (http_client, path_prefix, tenant_id) for browse calls.

        ME mode (Convergence available + 2 entities): routes to Convergence.
        SE mode (no Convergence or single entity): routes to DCL.
        """
        if self._convergence_http is not None:
            from src.nlq.core.entity_registry import get_entity_registry
            registry = get_entity_registry()
            entities = registry.get_entities_sync()
            if len(entities) >= 2:
                from src.nlq.config import get_tenant_id
                tenant_id = get_tenant_id()
                if not tenant_id:
                    raise RuntimeError(
                        "ME mode active (2 entities) but tenant_id is not configured. "
                        "Set AOS_TENANT_ID environment variable."
                    )
                return self._convergence_http, "/api/convergence", tenant_id
        return self._http, "/api/dcl", None

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
        """Get the latest available period from triples overview.

        Routes to Convergence in ME mode, DCL in SE mode.
        """
        client, prefix, tenant_id = self._resolve_browse_target()
        params = {"tenant_id": tenant_id} if tenant_id else None
        overview_path = f"{prefix}/triples/overview"
        resp = client.get(overview_path, params=params)
        if resp.status_code >= 400:
            target = self._convergence_base_url if tenant_id else self.base_url
            raise RuntimeError(
                f"GET {target}{overview_path} returned {resp.status_code}: "
                f"{resp.text[:500]}"
            )
        periods = resp.json().get("periods", [])
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
        """Call triples/browse with filters. TTL-cached (120s).

        Routes to Convergence in ME mode, DCL in SE mode.
        """
        cache_key = f"{domain}|{entity_id}|{period}|{property_name}|{limit}"
        now = time.time()

        with self._browse_cache_lock:
            cached = self._browse_cache.get(cache_key)
            if cached and now < cached[0]:
                return cached[1]

        client, prefix, tenant_id = self._resolve_browse_target()
        params: Dict[str, Any] = {"domain": domain, "limit": limit}
        if entity_id:
            params["entity_id"] = entity_id
        if period:
            params["period"] = period
        if property_name:
            params["property"] = property_name
        if tenant_id:
            params["tenant_id"] = tenant_id

        browse_path = f"{prefix}/triples/browse"
        resp = client.get(browse_path, params=params)
        if resp.status_code >= 400:
            target = self._convergence_base_url if tenant_id else self.base_url
            raise RuntimeError(
                f"GET {target}{browse_path} returned {resp.status_code}: "
                f"{resp.text[:500]}"
            )
        result = resp.json()

        with self._browse_cache_lock:
            self._browse_cache[cache_key] = (now + self._browse_cache_ttl, result)

        return result

    def clear_browse_cache(self):
        """Clear the browse cache. Useful for testing."""
        with self._browse_cache_lock:
            self._browse_cache.clear()

    def _try_total_synthesis(
        self,
        triples: List[Dict[str, Any]],
        concept: str,
        prop: str,
        metric_name: str,
        entity_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Synthesize a .total value by summing sub-concept triples.

        If concept is 'employee.total', sums all 'employee.*' triples with
        the matching property. Returns a result dict or None if no sub-concepts found.
        """
        if not concept.endswith(".total") or not triples:
            return None

        domain_prefix = concept.rsplit(".total", 1)[0] + "."
        matching = [
            t for t in triples
            if t.get("concept", "").startswith(domain_prefix)
            and t.get("property") == prop
        ]
        if not matching:
            return None

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
        if triple is None:
            synthesized = self._try_total_synthesis(triples, concept, prop, metric_name, entity_id)
            if synthesized is not None:
                return synthesized

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

        def _fetch_quarter(q: str) -> Optional[Tuple[float, Dict[str, Any]]]:
            browse_result = self._browse_triple(
                domain=domain,
                entity_id=entity_id,
                period=q,
                property_name=prop,
            )
            triples = browse_result.get("triples", [])
            triple = self._extract_triple_value(triples, concept, prop)

            # Try .total synthesis if no exact match
            if triple is None:
                synthesized = self._try_total_synthesis(triples, concept, prop, metric_name, entity_id)
                if synthesized is not None and synthesized.get("value") is not None:
                    return (synthesized["value"], synthesized)

            if triple is not None:
                val = self._numeric_value(triple)
                if val is not None:
                    return (val, triple)
            return None

        # Parallel quarter fetch (4 concurrent)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(propagate_context(_fetch_quarter), quarters))

        for r in results:
            if r is not None:
                values.append(r[0])
                last_triple = r[1]

        # If no quarterly data found, try period=None (period-agnostic data)
        if not values:
            browse_no_period = self._browse_triple(
                domain=domain,
                entity_id=entity_id,
                period=None,
                property_name=prop,
            )
            triples = browse_no_period.get("triples", [])
            triple = self._extract_triple_value(triples, concept, prop)
            if triple is None:
                synthesized = self._try_total_synthesis(triples, concept, prop, metric_name, entity_id)
                if synthesized is not None and synthesized.get("value") is not None:
                    synthesized["period"] = year
                    return synthesized
            elif triple is not None:
                val = self._numeric_value(triple)
                if val is not None:
                    return {
                        "value": val,
                        "entity_id": triple.get("entity_id"),
                        "period": year,
                        "confidence_score": triple.get("confidence_score"),
                        "confidence_tier": triple.get("confidence_tier"),
                        "source_system": triple.get("source_system"),
                        "data_source": "dcl_v2",
                        "metric_name": metric_name,
                        "concept": concept,
                    }

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
        # gross_margin / gross_profit: revenue.total - cogs.total
        if metric_name in ("gross_margin", "gross_profit"):
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

        # ebitda_margin_pct: pnl.ebitda / revenue.total * 100
        if metric_name == "ebitda_margin_pct":
            ebitda = values.get("pnl.ebitda", 0)
            rev = values.get("revenue.total", 0)
            if rev == 0:
                raise ValueError(
                    f"Cannot compute {metric_name}: revenue.total is zero (division by zero)"
                )
            return ebitda / rev * 100

        # operating_margin_pct: pnl.operating_profit / revenue.total * 100
        if metric_name == "operating_margin_pct":
            op = values.get("pnl.operating_profit", 0)
            rev = values.get("revenue.total", 0)
            if rev == 0:
                raise ValueError(
                    f"Cannot compute {metric_name}: revenue.total is zero (division by zero)"
                )
            return op / rev * 100

        # net_margin_pct: pnl.net_income / revenue.total * 100
        if metric_name == "net_margin_pct":
            net = values.get("pnl.net_income", 0)
            rev = values.get("revenue.total", 0)
            if rev == 0:
                raise ValueError(
                    f"Cannot compute {metric_name}: revenue.total is zero (division by zero)"
                )
            return net / rev * 100

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

        # sga: opex.sales_marketing + opex.general_admin
        if metric_name == "sga":
            sm = values.get("opex.sales_marketing", 0)
            ga = values.get("opex.general_admin", 0)
            return sm + ga

        # fcf: cash_flow.operating.total - cash_flow.investing.capex
        if metric_name == "fcf":
            cfo = values.get("cash_flow.operating.total", 0)
            capex = values.get("cash_flow.investing.capex", 0)
            return cfo - capex

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
    # Batch metric fetch (reduces HTTP calls for reports)
    # ------------------------------------------------------------------

    def get_metrics_batch(
        self,
        metric_names: List[str],
        entity_id: Optional[str] = None,
        period: Optional[str] = None,
    ) -> "MetricsBatchResult":
        """Fetch multiple metrics in one HTTP call via browse-batch endpoint.

        Collects all needed domains (from direct and derived metrics), makes
        a single POST to /api/dcl/triples/browse-batch, and resolves all
        metric values from the response. One HTTP call replaces N per-domain
        browse calls.

        Returns: MetricsBatchResult (dict subclass with .min_confidence_score,
                 .min_confidence_tier from source triples)
        """
        results: Dict[str, Optional[float]] = {}
        direct_by_domain: Dict[str, List[tuple]] = {}  # domain -> [(metric_name, concept, prop)]
        derived_metrics: List[str] = []
        all_domains: set = set()

        for name in metric_names:
            canonical = resolve_metric_name(name)
            if canonical is None:
                results[name] = None
                continue
            defn = METRIC_CONCEPT_MAP[canonical]
            if defn["type"] == "derived":
                derived_metrics.append(name)
                # Collect component domains for derived metrics too
                for comp in defn.get("components", []):
                    all_domains.add(comp["concept"].split(".")[0])
            else:
                concept = defn["concept"]
                prop = defn["property"]
                domain = concept.split(".")[0]
                direct_by_domain.setdefault(domain, []).append((name, concept, prop))
                all_domains.add(domain)

        # Single batch fetch for ALL domains at once
        domain_triples: Dict[str, List[Dict[str, Any]]] = {}
        if all_domains:
            try:
                body: Dict[str, Any] = {"domains": sorted(all_domains)}
                if entity_id:
                    body["entity_ids"] = [entity_id]
                if period:
                    body["period"] = period
                resp = self._http.post("/api/dcl/triples/browse-batch", json=body)
                if resp.status_code >= 400:
                    raise RuntimeError(f"browse-batch returned {resp.status_code}: {resp.text[:300]}")
                data = resp.json()
                domain_triples = data.get("triples_by_domain", {})
            except Exception as exc:
                logger.warning("browse-batch failed, falling back to per-domain browse: %s", exc)
                # Fallback: per-domain browse (original behavior)
                for domain in all_domains:
                    try:
                        browse_result = self._browse_triple(
                            domain=domain,
                            entity_id=entity_id,
                            period=period,
                            limit=200,
                        )
                        domain_triples[domain] = browse_result.get("triples", [])
                    except Exception as inner_exc:
                        logger.warning("Fallback browse failed for domain=%s: %s", domain, inner_exc)
                        domain_triples[domain] = []

        # Extract individual metric values from batch results.
        # Track confidence scores from source triples.
        confidence_scores: List[float] = []
        confidence_tiers: List[str] = []

        def _track_confidence(triple_dict: Optional[Dict[str, Any]]):
            if triple_dict is None:
                return
            score = triple_dict.get("confidence_score")
            tier = triple_dict.get("confidence_tier")
            if score is not None:
                confidence_scores.append(float(score))
            if tier is not None:
                confidence_tiers.append(tier)

        for domain, items in direct_by_domain.items():
            triples = domain_triples.get(domain, [])
            for metric_name, concept, prop in items:
                triple = self._extract_triple_value(triples, concept, prop)
                if triple is not None:
                    results[metric_name] = self._numeric_value(triple)
                    _track_confidence(triple)
                else:
                    synthesized = self._try_total_synthesis(triples, concept, prop, metric_name, entity_id)
                    if synthesized is not None:
                        results[metric_name] = synthesized.get("value")
                        _track_confidence(synthesized)
                    else:
                        results[metric_name] = None

        # Compute derived metrics inline from already-fetched domain triples
        for name in derived_metrics:
            try:
                canonical = resolve_metric_name(name)
                if canonical is None:
                    results[name] = None
                    continue
                defn = METRIC_CONCEPT_MAP[canonical]
                components = defn.get("components", [])
                formula = defn.get("formula", "")

                derived_period = period
                if self._is_bare_year(derived_period) or derived_period is None:
                    resolved = self._get_latest_quarter()
                    if resolved is None:
                        results[name] = None
                        continue
                    derived_period = resolved

                component_values: Dict[str, float] = {}
                missing_component = False
                for comp in components:
                    comp_concept = comp["concept"]
                    comp_prop = comp["property"]
                    comp_domain = comp_concept.split(".")[0]

                    triples = domain_triples.get(comp_domain, [])
                    triple = self._extract_triple_value(triples, comp_concept, comp_prop)

                    if triple is None:
                        synthesized = self._try_total_synthesis(
                            triples, comp_concept, comp_prop, name, entity_id,
                        )
                        if synthesized is not None:
                            component_values[comp_concept] = synthesized.get("value")
                            _track_confidence(synthesized)
                            continue
                        missing_component = True
                        break

                    val = self._numeric_value(triple)
                    if val is None:
                        missing_component = True
                        break
                    component_values[comp_concept] = val
                    _track_confidence(triple)

                if missing_component:
                    results[name] = None
                    continue

                results[name] = self._compute_formula(canonical, formula, component_values)
            except (ValueError, RuntimeError) as exc:
                logger.warning("Derived metric '%s' failed in batch: %s", name, exc)
                results[name] = None

        # Wrap results with confidence metadata from source triples
        batch_result = MetricsBatchResult(results)
        if confidence_scores:
            batch_result.min_confidence_score = min(confidence_scores)
        if confidence_tiers:
            # Tier ordering: exact > high > medium > low
            tier_rank = {"exact": 4, "high": 3, "medium": 2, "low": 1, "derived": 2}
            batch_result.min_confidence_tier = min(
                confidence_tiers, key=lambda t: tier_rank.get(t, 0)
            )

        return batch_result

    def get_all_metrics_by_period(
        self,
        metric_names: List[str],
        entity_id: Optional[str] = None,
    ) -> Tuple["MetricsBatchResult", float]:
        """Fetch ALL periods for given metrics in ONE browse-batch call.

        Makes a single HTTP call with no period filter, then groups results
        by period and extracts metrics per period. Returns:
          - MetricsBatchResult keyed by (metric_name, period) as "{metric}|{period}"
          - min confidence score from source triples

        This replaces N calls to get_metrics_batch (one per period) with 1 call.
        """
        direct_by_domain: Dict[str, List[tuple]] = {}
        derived_metrics: List[str] = []
        all_domains: set = set()

        for name in metric_names:
            canonical = resolve_metric_name(name)
            if canonical is None:
                continue
            defn = METRIC_CONCEPT_MAP[canonical]
            if defn["type"] == "derived":
                derived_metrics.append(name)
                for comp in defn.get("components", []):
                    all_domains.add(comp["concept"].split(".")[0])
            else:
                concept = defn["concept"]
                prop = defn["property"]
                domain = concept.split(".")[0]
                direct_by_domain.setdefault(domain, []).append((name, concept, prop))
                all_domains.add(domain)

        # Single batch fetch — ALL domains, ALL periods, one entity.
        # Routes to Convergence in ME mode, DCL in SE mode.
        all_triples: List[Dict[str, Any]] = []
        if all_domains:
            try:
                client, prefix, tenant_id = self._resolve_browse_target()
                body: Dict[str, Any] = {"domains": sorted(all_domains)}
                if entity_id:
                    body["entity_ids"] = [entity_id]
                batch_params = {"tenant_id": tenant_id} if tenant_id else None
                batch_path = f"{prefix}/triples/browse-batch"
                resp = client.post(batch_path, json=body, params=batch_params)
                if resp.status_code >= 400:
                    target = self._convergence_base_url if tenant_id else self.base_url
                    raise RuntimeError(
                        f"browse-batch {target}{batch_path} returned "
                        f"{resp.status_code}: {resp.text[:300]}"
                    )
                data = resp.json()
                # Flatten all triples
                for domain_triples in data.get("triples_by_domain", {}).values():
                    all_triples.extend(domain_triples)
            except Exception as exc:
                logger.warning("get_all_metrics_by_period: browse-batch failed: %s", exc)
                # No fallback — fail loudly per A1
                raise RuntimeError(
                    f"browse-batch call failed for entity_id={entity_id}, "
                    f"domains={sorted(all_domains)}: {exc}"
                ) from exc

        # Group all triples by (domain, period)
        triples_by_domain_period: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        for t in all_triples:
            concept = t.get("concept", "")
            domain = concept.split(".")[0] if concept else ""
            period = t.get("period", "")
            if domain and period:
                triples_by_domain_period.setdefault((domain, period), []).append(t)

        # Get all unique periods
        all_periods = sorted({t.get("period") for t in all_triples if t.get("period")})

        # Extract metrics per period
        results = MetricsBatchResult()
        confidence_scores: List[float] = []

        def _track_confidence(triple_dict: Optional[Dict[str, Any]]):
            if triple_dict is None:
                return
            score = triple_dict.get("confidence_score")
            if score is not None:
                confidence_scores.append(float(score))

        for period in all_periods:
            # Direct metrics
            for domain, items in direct_by_domain.items():
                triples = triples_by_domain_period.get((domain, period), [])
                for metric_name, concept, prop in items:
                    triple = self._extract_triple_value(triples, concept, prop)
                    if triple is not None:
                        results[f"{metric_name}|{period}"] = self._numeric_value(triple)
                        _track_confidence(triple)
                    else:
                        synthesized = self._try_total_synthesis(triples, concept, prop, metric_name, entity_id)
                        if synthesized is not None:
                            results[f"{metric_name}|{period}"] = synthesized.get("value")
                            _track_confidence(synthesized)

            # Derived metrics
            for name in derived_metrics:
                try:
                    canonical = resolve_metric_name(name)
                    if canonical is None:
                        continue
                    defn = METRIC_CONCEPT_MAP[canonical]
                    components = defn.get("components", [])
                    formula = defn.get("formula", "")

                    component_values: Dict[str, float] = {}
                    missing_component = False
                    for comp in components:
                        comp_concept = comp["concept"]
                        comp_prop = comp["property"]
                        comp_domain = comp_concept.split(".")[0]
                        triples = triples_by_domain_period.get((comp_domain, period), [])
                        triple = self._extract_triple_value(triples, comp_concept, comp_prop)

                        if triple is None:
                            synthesized = self._try_total_synthesis(
                                triples, comp_concept, comp_prop, name, entity_id,
                            )
                            if synthesized is not None:
                                component_values[comp_concept] = synthesized.get("value")
                                _track_confidence(synthesized)
                                continue
                            missing_component = True
                            break

                        val = self._numeric_value(triple)
                        if val is None:
                            missing_component = True
                            break
                        component_values[comp_concept] = val
                        _track_confidence(triple)

                    if not missing_component:
                        results[f"{name}|{period}"] = self._compute_formula(canonical, formula, component_values)
                except (ValueError, RuntimeError) as exc:
                    logger.warning("Derived metric '%s' period=%s failed: %s", name, period, exc)

        if confidence_scores:
            results.min_confidence_score = min(confidence_scores)
        min_conf = min(confidence_scores) if confidence_scores else 1.0

        return results, min_conf

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
    # Pipeline stages
    # ------------------------------------------------------------------

    # Canonical stage ordering for sales pipeline funnel
    _PIPELINE_STAGE_ORDER = [
        "lead", "qualified", "proposal", "negotiation", "closed_won",
    ]

    _PIPELINE_STAGE_LABELS = {
        "lead": "Lead",
        "qualified": "Qualified",
        "proposal": "Proposal",
        "negotiation": "Negotiation",
        "closed_won": "Closed-Won",
    }

    def get_pipeline_stages(
        self,
        entity_id: Optional[str] = None,
        period: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch pipeline stage breakdown from customer.pipeline.* triples.

        Returns ordered list of {label, value, percent} dicts.
        Empty list if no stage triples found.
        """
        browse_result = self._browse_triple(
            domain="customer",
            entity_id=entity_id,
            period=period,
            property_name="amount",
            limit=200,
        )
        triples = browse_result.get("triples", [])

        # Filter to customer.pipeline.{stage} concepts (exclude bare customer.pipeline)
        stage_values: Dict[str, float] = {}
        for t in triples:
            concept = t.get("concept", "")
            if not concept.startswith("customer.pipeline."):
                continue
            suffix = concept[len("customer.pipeline."):]
            if not suffix or "." in suffix:
                continue
            val = t.get("value")
            if val is not None:
                try:
                    stage_values[suffix] = float(val)
                except (TypeError, ValueError):
                    continue

        if not stage_values:
            return []

        # Order by canonical stage order, append any extras at end
        ordered_keys = [
            k for k in self._PIPELINE_STAGE_ORDER if k in stage_values
        ]
        extras = sorted(k for k in stage_values if k not in self._PIPELINE_STAGE_ORDER)
        ordered_keys.extend(extras)

        # Compute percentages relative to the first (largest) stage
        first_val = stage_values.get(ordered_keys[0], 1.0) if ordered_keys else 1.0
        if first_val == 0:
            first_val = 1.0

        stages = []
        for key in ordered_keys:
            val = stage_values[key]
            stages.append({
                "label": self._PIPELINE_STAGE_LABELS.get(key, key.replace("_", " ").title()),
                "value": val,
                "percent": round((val / first_val) * 100, 1),
            })

        return stages

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
