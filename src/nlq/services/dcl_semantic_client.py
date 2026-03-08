"""
DCL Semantic Layer Client for NLQ.

Fetches and caches the semantic catalog from DCL, providing:
- Metric resolution (user term -> canonical metric ID)
- Dimension validation (is this dimension valid for this metric?)
- Helpful error messages (what ARE the valid options?)

This replaces hardcoded metric mappings in visualization_intent.py with
dynamic discovery from DCL's semantic layer.

Usage:
    client = get_semantic_client()

    # Resolve user term to canonical metric
    metric = client.resolve_metric("AR")  # Returns {"id": "ar", ...}

    # Validate dimension for metric
    valid, error = client.validate_dimension("revenue", "customer")
    # Returns (False, "Dimension 'customer' not available for 'revenue'. Valid: region, segment, product")
"""

import contextlib
import contextvars
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from src.nlq.config import get_tenant_id
from src.nlq.core.dates import current_quarter, current_year
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

_force_local_ctx: contextvars.ContextVar[bool] = contextvars.ContextVar('_force_local_ctx', default=False)
_data_mode_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('_data_mode_ctx', default=None)

# Diagnostic trace collector — route handlers init this to [] before each request,
# and the DCL client appends messages.  The route handler reads it back and includes
# it in the JSON response so the trace is visible in the browser Network tab.
_diag_trace: contextvars.ContextVar[Optional[List[str]]] = contextvars.ContextVar('_diag_trace', default=None)


def diag(msg: str) -> None:
    """Print a diagnostic message AND append it to the per-request trace list."""
    print(msg)
    trace = _diag_trace.get()
    if trace is not None:
        trace.append(msg)


def diag_init() -> List[str]:
    """Call at the start of a request to begin collecting diagnostics."""
    trace: List[str] = []
    _diag_trace.set(trace)
    return trace


def diag_collect() -> Optional[List[str]]:
    """Return the trace list accumulated during this request."""
    return _diag_trace.get()

logger = logging.getLogger(__name__)

# Cache TTL in seconds (5 minutes)
CACHE_TTL_SECONDS = 300

# Pack-to-domain mapping (DCL catalog uses pack names, NLQ uses domain names)
PACK_TO_DOMAIN = {
    "cfo": "CFO",
    "cro": "CRO",
    "coo": "COO",
    "cto": "CTO",
    "chro": "CHRO",
}

# Grain mapping (NLQ callers use long form, DCL expects short form)
GRAIN_TO_DCL = {
    "quarterly": "quarter",
    "monthly": "month",
    "yearly": "year",
    "annual": "year",
}


@dataclass
class MetricDefinition:
    """Definition of a metric from the semantic catalog."""
    id: str  # Canonical metric ID (e.g., "ar", "revenue")
    display_name: str  # Human-readable name
    aliases: List[str]  # Alternative names users might say
    unit: str  # Unit of measurement
    allowed_dimensions: List[str]  # What dimensions can this metric be broken down by
    allowed_grains: List[str]  # Time granularities (quarterly, monthly, etc.)
    domain: str  # CFO, CRO, COO, etc.


@dataclass
class IngestSummary:
    """Summary of ingested data available in DCL's buffer.

    When DCL's Farm mode has buffered data, the semantic export includes
    this block so NLQ knows what live data exists before querying.
    """
    source_systems: List[str] = field(default_factory=list)
    row_count: int = 0
    pipe_count: int = 0
    tenant_names: List[str] = field(default_factory=list)
    available: bool = False


@dataclass
class SemanticCatalog:
    """Complete semantic catalog from DCL."""
    metrics: Dict[str, MetricDefinition] = field(default_factory=dict)
    dimensions: Dict[str, List[str]] = field(default_factory=dict)  # dimension -> valid values
    alias_to_metric: Dict[str, str] = field(default_factory=dict)  # alias -> metric_id
    ingest_summary: Optional[IngestSummary] = None  # Live ingest buffer info from DCL
    dcl_mode: Optional[str] = None       # DCL's data_mode: "Demo", "Ingest", "Farm", "AAM"
    dcl_last_updated: Optional[str] = None  # ISO timestamp of last mode change

    def build_alias_index(self):
        """Build reverse lookup from aliases to metric IDs.

        Two-pass approach ensures aliases take precedence over canonical IDs.
        This allows "attrition" (alias) to map to "attrition_rate_pct" even though
        there's also a metric with canonical ID "attrition".
        """
        self.alias_to_metric = {}
        # First pass: Add all canonical IDs
        for metric_id, metric in self.metrics.items():
            self.alias_to_metric[metric_id.lower()] = metric_id
        # Second pass: Add all aliases (so they can override canonical IDs)
        for metric_id, metric in self.metrics.items():
            for alias in metric.aliases:
                self.alias_to_metric[alias.lower()] = metric_id


class DCLSemanticClient:
    """
    Client for fetching and querying DCL's semantic catalog.

    Provides metric resolution and dimension validation with caching.

    Mode selection:
    - If DCL_API_URL is set: Fetches from DCL's /api/dcl/semantic-export endpoint
    - If DCL_API_URL is not set: Uses local fact_base.json (local dev mode)
    """

    # Circuit breaker tuning — soft enough for Render cold starts
    _CB_FAILURE_THRESHOLD = 5    # failures before opening (was 3)
    _CB_OPEN_DURATION = 30.0     # seconds circuit stays open (was 60)
    _CB_HALF_OPEN_INTERVAL = 15.0  # seconds between probe requests when open

    def __init__(self, dcl_base_url: Optional[str] = None):
        raw_url = dcl_base_url or os.environ.get("DCL_API_URL")
        self.dcl_url = raw_url.rstrip("/") if raw_url else None
        self._catalog: Optional[SemanticCatalog] = None
        self._cache_time: float = 0
        self._mode: str = "dcl" if self.dcl_url else "local"

        # Shared HTTP client — connection pool reused across all DCL calls.
        # Base timeout is 30s; individual methods override per-request where needed.
        self._http_client: httpx.Client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
        )

        # H4: Explicit data source tracking — callers can inspect this
        self._catalog_source: str = "none"  # "dcl", "local", "local_fallback"

        # Circuit breaker state
        self._dcl_consecutive_failures = 0
        self._dcl_circuit_open_until: float = 0
        self._dcl_last_half_open_probe: float = 0

        if self.dcl_url:
            logger.info(f"DCL semantic client initialized - DCL mode (endpoint: {self.dcl_url})")
        else:
            logger.info("DCL semantic client initialized - LOCAL DEV mode (using fact_base.json)")

    # =========================================================================
    # CIRCUIT BREAKER — protects against repeated DCL failures
    # =========================================================================

    def _record_dcl_failure(self) -> None:
        """Record a DCL call failure and open circuit breaker if threshold met."""
        self._dcl_consecutive_failures += 1
        if self._dcl_consecutive_failures >= self._CB_FAILURE_THRESHOLD:
            self._dcl_circuit_open_until = time.time() + self._CB_OPEN_DURATION
            logger.warning(
                f"DCL circuit breaker OPEN for {self._CB_OPEN_DURATION}s "
                f"after {self._dcl_consecutive_failures} consecutive failures"
            )

    def _record_dcl_success(self) -> None:
        """Record a successful DCL call — resets circuit breaker."""
        self._dcl_consecutive_failures = 0
        self._dcl_circuit_open_until = 0
        self._dcl_last_half_open_probe = 0

    def _is_dcl_call_allowed(self) -> bool:
        """Check if a DCL call is allowed under the circuit breaker.

        When the circuit is fully open, allows a single "half-open" probe
        every _CB_HALF_OPEN_INTERVAL seconds so we can detect recovery
        quickly instead of waiting the full open duration.
        """
        now = time.time()

        # Circuit closed — all calls allowed
        if now >= self._dcl_circuit_open_until:
            return True

        # Circuit open — allow a half-open probe every 15s
        if now - self._dcl_last_half_open_probe >= self._CB_HALF_OPEN_INTERVAL:
            self._dcl_last_half_open_probe = now
            logger.debug("DCL circuit breaker half-open probe allowed")
            return True

        return False

    @property
    def catalog_source(self) -> str:
        """Where the current catalog was loaded from: 'dcl', 'local', or 'local_fallback'.

        'local' = intentional dev mode (no DCL_API_URL configured).
        'local_fallback' = DCL was configured but failed — data may be stale.
        """
        return self._catalog_source

    @property
    def catalog(self) -> SemanticCatalog:
        """Get the semantic catalog, fetching/refreshing if needed."""
        return self.get_catalog()

    def get_catalog(self, force_refresh: bool = False, force_local: bool = False) -> SemanticCatalog:
        """
        Fetch semantic catalog from DCL, with caching.

        Args:
            force_refresh: If True, bypass cache and fetch fresh
            force_local: If True, skip DCL and use local fact_base.json

        Returns:
            SemanticCatalog with all metric definitions
        """
        ctx_force = _force_local_ctx.get()
        data_mode = _data_mode_ctx.get()
        diag(f"[NLQ-DIAG] get_catalog called: force_local={force_local}, ctx_force={ctx_force}, dcl_url={self.dcl_url}, data_mode={data_mode}")

        # LIVE MODE guard: only block when DCL IS configured but caller
        # forces local — that's the silent fallback we must prevent.
        if data_mode == "live" and self.dcl_url and (force_local or ctx_force):
            raise RuntimeError(
                "LIVE MODE FAILURE: force_local requested but data_mode='live' and DCL is configured. "
                "Cannot use fact_base.json catalog in live mode when DCL is available."
            )

        if force_local or ctx_force:
            catalog = self._build_local_catalog()
            diag(f"[NLQ-DIAG] get_catalog -> LOCAL ({len(catalog.metrics)} metrics)")
            return catalog

        current_time = time.time()

        # Return cached if valid
        if (not force_refresh
            and self._catalog is not None
            and current_time - self._cache_time < CACHE_TTL_SECONDS):
            return self._catalog

        # Try to fetch from DCL if configured
        if self.dcl_url:
            diag(f"[NLQ-DIAG] Fetching catalog from DCL: {self.dcl_url}/api/dcl/semantic-export")
            try:
                catalog = self._fetch_from_dcl()
                self._catalog = catalog
                self._cache_time = current_time
                self._catalog_source = "dcl"
                diag(f"[NLQ-DIAG] DCL catalog loaded OK: {len(catalog.metrics)} metrics")
                logger.info(f"Loaded semantic catalog from DCL ({len(catalog.metrics)} metrics)")
                return catalog
            except RuntimeError:
                raise  # Re-raise our own mode errors
            except (httpx.RequestError, httpx.HTTPStatusError, json.JSONDecodeError, KeyError) as e:
                diag(f"[NLQ-DIAG] DCL catalog fetch FAILED: {type(e).__name__}: {e}")

                # Live mode: always fail loud
                if data_mode == "live":
                    raise RuntimeError(
                        f"LIVE MODE FAILURE: DCL catalog fetch failed: {e}. "
                        f"Cannot fall back to fact_base.json in live mode. "
                        f"Check DCL_API_URL or DCL service health."
                    )

                # Ingest mode: fail loud — serving demo data when real data
                # exists in DCL would show wrong numbers silently
                if data_mode and data_mode.lower() == "ingest":
                    raise RuntimeError(
                        f"INGEST MODE FAILURE: DCL catalog fetch failed: {e}. "
                        f"Cannot serve queries with stale demo data when real "
                        f"ingested data exists in DCL. "
                        f"Check DCL service health at {self.dcl_url}/api/health"
                    )

                # Demo mode: fallback acceptable (same demo data either way)
                logger.warning(
                    f"DCL catalog fetch failed: {e} — falling back to local fact_base.json. "
                    f"Data may be stale. Check DCL_API_URL or DCL service health."
                )

        # No DCL URL configured — local fact_base is the only data source.
        # This is NOT a silent fallback: DCL was never configured, so local
        # data is the correct and only source. Log clearly and proceed.
        if not self.dcl_url:
            if data_mode in ("live", "ingest"):
                logger.info(
                    "DCL_API_URL not configured — serving %s-mode queries from local tenant data. "
                    "Set DCL_API_URL to enable live DCL queries.", data_mode
                )

        # Local dev mode or DCL fallback
        catalog = self._build_local_catalog()
        self._catalog = catalog

        if self.dcl_url:
            # DCL was configured but unavailable — short cache (30s, not 5min)
            # so we retry quickly
            self._cache_time = current_time - CACHE_TTL_SECONDS + 30
            self._catalog_source = "local_fallback"
            logger.warning(
                f"Using local_fallback catalog ({len(catalog.metrics)} metrics). "
                f"DCL was configured but unavailable. Retrying in 30s."
            )
        else:
            self._cache_time = current_time
            self._catalog_source = "local"
            logger.debug(f"Using local catalog ({len(catalog.metrics)} metrics)")

        return catalog

    def _fetch_from_dcl(self) -> SemanticCatalog:
        """Fetch semantic catalog from DCL's semantic-export endpoint.

        Retries up to 3 times with backoff (0s, 3s, 6s) to survive Render
        cold starts where DCL may take 15-30s to become ready.

        Raises on failure instead of returning None — the caller (get_catalog)
        decides what to do based on data_mode.
        """
        url = f"{self.dcl_url}/api/dcl/semantic-export"
        backoff_schedule = [0, 3, 6]  # seconds between attempts

        for attempt, wait in enumerate(backoff_schedule, 1):
            if wait > 0:
                diag(f"[NLQ-DIAG] _fetch_from_dcl retry {attempt}/{len(backoff_schedule)} after {wait}s backoff")
                time.sleep(wait)

            try:
                diag(f"[NLQ-DIAG] _fetch_from_dcl GET {url} (attempt {attempt}/{len(backoff_schedule)})")
                response = self._http_client.get(url, timeout=20.0)
                diag(f"[NLQ-DIAG] _fetch_from_dcl status={response.status_code}, size={len(response.text)} bytes")
                response.raise_for_status()
                data = response.json()
                metric_ids = list(data.get("metrics", [{}]))[:5]
                diag(f"[NLQ-DIAG] _fetch_from_dcl parsed: {len(data.get('metrics', []))} metrics, mode={data.get('mode', {})}, first_5={[m.get('id','?') if isinstance(m,dict) else '?' for m in metric_ids]}")
                return self._parse_dcl_response(data)
            except (httpx.RequestError, httpx.HTTPStatusError, json.JSONDecodeError) as e:
                diag(f"[NLQ-DIAG] _fetch_from_dcl attempt {attempt}/{len(backoff_schedule)} failed: {type(e).__name__}: {e}")
                if attempt < len(backoff_schedule):
                    continue
                # Final attempt failed — raise so caller handles it
                raise

    def _parse_dcl_response(self, data: Dict[str, Any]) -> SemanticCatalog:
        """Parse DCL's semantic-export response into our catalog format.

        DCL catalog field mapping:
          DCL field       -> NLQ field
          id              -> id (canonical metric key)
          name            -> display_name
          pack            -> domain (via PACK_TO_DOMAIN)
          allowed_dims    -> allowed_dimensions
          allowed_grains  -> allowed_grains
          aliases         -> aliases
          (unit not in catalog — use local _get_metric_units())
          entities[]      -> dimensions dict {id: allowed_values}
        """
        catalog = SemanticCatalog()

        # Store mode information from DCL
        mode_info = data.get("mode", {})
        if mode_info:
            catalog.dcl_mode = mode_info.get("data_mode")
            catalog.dcl_last_updated = mode_info.get("last_updated")
            logger.info(f"DCL mode: {catalog.dcl_mode}/{mode_info.get('run_mode', 'unknown')} (updated: {catalog.dcl_last_updated})")

        # Parse ingest_summary — tells NLQ what live data is buffered in DCL
        ingest_raw = data.get("ingest_summary", {})
        if ingest_raw:
            catalog.ingest_summary = IngestSummary(
                source_systems=ingest_raw.get("source_systems", []),
                row_count=ingest_raw.get("row_count", 0),
                pipe_count=ingest_raw.get("pipe_count", 0),
                tenant_names=ingest_raw.get("tenant_names", []),
                available=True,
            )
            diag(f"[NLQ-DIAG] ingest_summary: {catalog.ingest_summary.row_count} rows, "
                 f"{len(catalog.ingest_summary.source_systems)} sources, "
                 f"tenants={catalog.ingest_summary.tenant_names}")

        # Parse metrics — DCL uses 'name' (not 'display_name') and 'pack' (not 'domain')
        local_units = self._get_metric_units()
        for metric_data in data.get("metrics", []):
            metric_id = metric_data["id"]
            metric = MetricDefinition(
                id=metric_id,
                display_name=metric_data.get("name", metric_id),
                aliases=metric_data.get("aliases", []),
                unit=local_units.get(metric_id, ""),
                allowed_dimensions=metric_data.get("allowed_dims", []),
                allowed_grains=metric_data.get("allowed_grains", ["quarterly"]),
                domain=PACK_TO_DOMAIN.get(
                    metric_data.get("pack", ""),
                    metric_data.get("pack", "").upper(),
                ),
            )
            catalog.metrics[metric.id] = metric

        # Parse dimensions from DCL's entities array
        # DCL sends: [{"id": "customer", "allowed_values": [...], ...}, ...]
        for entity_data in data.get("entities", []):
            entity_id = entity_data.get("id", "")
            allowed_values = entity_data.get("allowed_values", [])
            if entity_id:
                catalog.dimensions[entity_id] = allowed_values

        # Build alias index
        catalog.build_alias_index()

        return catalog

    def _build_local_catalog(self) -> SemanticCatalog:
        """
        Build semantic catalog from local fact_base.json.

        This analyzes fact_base to discover:
        - All metrics and their aliases
        - Which dimensions each metric supports
        """
        catalog = SemanticCatalog()

        # Load fact_base
        fact_base_path = Path(__file__).parent.parent.parent.parent / "data" / "fact_base.json"
        try:
            with open(fact_base_path, 'r') as f:
                fact_base = json.load(f)
        except (FileNotFoundError, IOError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load fact_base.json: {e}")
            return catalog

        # Extract metrics from quarterly data
        quarterly_metrics: Set[str] = set()
        if 'quarterly' in fact_base:
            for entry in fact_base['quarterly']:
                for key in entry.keys():
                    if key not in ('year', 'quarter', 'period'):
                        quarterly_metrics.add(key)

        # Discover dimension breakdowns per metric
        # Pattern: {metric}_by_{dimension} in fact_base keys
        metric_dimensions: Dict[str, List[str]] = {}
        for key in fact_base.keys():
            if '_by_' in key:
                parts = key.split('_by_')
                if len(parts) == 2:
                    metric_name = parts[0]
                    dimension = parts[1]
                    if metric_name not in metric_dimensions:
                        metric_dimensions[metric_name] = []
                    metric_dimensions[metric_name].append(dimension)

        # Build metric definitions with aliases
        metric_aliases = self._get_metric_aliases()
        metric_domains = self._get_metric_domains()
        metric_units = self._get_metric_units()

        for metric_id in quarterly_metrics:
            # Get aliases for this metric
            aliases = metric_aliases.get(metric_id, [])

            # Get allowed dimensions
            allowed_dims = metric_dimensions.get(metric_id, [])

            # Create definition
            metric = MetricDefinition(
                id=metric_id,
                display_name=self._format_display_name(metric_id),
                aliases=aliases,
                unit=metric_units.get(metric_id, ""),
                allowed_dimensions=allowed_dims,
                allowed_grains=["quarterly", "yearly"],
                domain=metric_domains.get(metric_id, ""),
            )
            catalog.metrics[metric_id] = metric

        # Extract dimension values from metadata
        if 'metadata' in fact_base:
            metadata = fact_base['metadata']
            catalog.dimensions = {
                'region': metadata.get('regions', []),
                'segment': metadata.get('segments', []),
                'product': metadata.get('products', []),
                'stage': metadata.get('pipeline_stages', []),
                'department': metadata.get('departments', []),
                'rep': self._extract_rep_names(fact_base),
            }

        # Build alias index
        catalog.build_alias_index()

        return catalog

    def _get_metric_aliases(self) -> Dict[str, List[str]]:
        """Get common aliases for metrics including common misspellings."""
        return {
            # Financial (with common misspellings)
            "revenue": ["sales", "top line", "topline", "total revenue",
                        "reveune", "revnue", "revennue", "revanue"],  # misspellings
            "ar": ["accounts receivable", "receivables", "a/r",
                   "recievables", "receivbles", "recievbles"],  # misspellings
            "ap": ["accounts payable", "payables", "a/p"],
            "ebitda": ["earnings before interest taxes depreciation amortization"],
            "gross_margin_pct": ["gross margin", "gm", "margin"],
            "net_income": ["profit", "net profit", "bottom line", "profitable", "profitability"],
            "operating_profit": ["ebit", "operating income"],
            "cogs": ["cost of goods sold", "cost of sales", "cos"],

            # Sales
            "pipeline": ["sales pipeline", "pipe", "opportunities", "deals"],
            "arr": ["annual recurring revenue", "recurring revenue"],
            "nrr": ["net revenue retention", "net retention", "retention rate", "retention"],
            "win_rate_pct": ["close rate", "conversion rate", "win rate"],
            "quota_attainment_pct": ["quota", "attainment", "quota attainment"],
            "churn_rate_pct": ["churn", "churn rate", "customer churn", "gross churn"],

            # Operations/HR (with common misspellings)
            "headcount": ["employees", "staff", "team size", "hc", "people", "fte",
                          "employess", "employes", "emplyees",  # misspellings
                          "personnel", "personnel hires", "hires", "workforce",  # additional aliases
                          "hiring", "hiring trend"],  # map hiring to headcount trend
            "attrition_rate_pct": ["attrition", "attrition rate", "turnover rate", "employee turnover", "turnover",
                                  "attriton", "attrtion", "attriton rate"],  # misspellings
            "engagement_score": ["engagement", "engagment", "engagmnet"],  # misspellings
            "cac": ["customer acquisition cost", "acquisition cost"],
            "ltv_cac": ["ltv/cac", "ltv to cac", "ltv to cac ratio", "ltv cac ratio",
                       "ltv cac", "lifetime value to cac"],
            "magic_number": ["sales efficiency", "efficiency", "efficient"],  # yes/no query support

            # Tech
            "uptime_pct": ["uptime", "availability"],
            "p1_incidents": ["incidents", "p1s", "outages"],
            "mttr_p1_hours": ["mttr", "mean time to repair", "mean time to resolve"],
            "deployment_success_pct": ["deploy success", "deployment success"],
            "tech_debt_pct": ["tech debt", "technical debt", "debt ratio"],
            "csat": ["csat score", "customer satisfaction", "satisfaction score"],
        }

    def _get_metric_domains(self) -> Dict[str, str]:
        """Get domain (persona) for each metric."""
        return {
            # CFO
            "revenue": "CFO", "ar": "CFO", "ap": "CFO", "ebitda": "CFO",
            "gross_margin_pct": "CFO", "net_income": "CFO", "operating_profit": "CFO",
            "cogs": "CFO", "sga": "CFO", "cash": "CFO",

            # CRO
            "pipeline": "CRO", "arr": "CRO", "nrr": "CRO", "win_rate_pct": "CRO",
            "quota_attainment_pct": "CRO", "churn_rate_pct": "CRO", "bookings": "CRO",
            "sales_cycle_days": "CRO", "avg_deal_size": "CRO",

            # COO
            "headcount": "COO", "cac": "COO", "ltv_cac": "COO", "magic_number": "COO",
            "revenue_per_employee": "COO", "cac_payback_months": "COO",

            # CTO
            "uptime_pct": "CTO", "p1_incidents": "CTO", "deploys_per_week": "CTO",
            "sprint_velocity": "CTO", "code_coverage_pct": "CTO", "tech_debt_pct": "CTO",

            # CHRO
            "attrition_rate_pct": "CHRO", "engagement_score": "CHRO",
            "time_to_fill_days": "CHRO", "offer_acceptance_rate_pct": "CHRO",
        }

    def _get_metric_units(self) -> Dict[str, str]:
        """Get units for each metric."""
        return {
            # Currency (millions)
            "revenue": "USD millions", "ar": "USD millions", "ap": "USD millions",
            "ebitda": "USD millions", "net_income": "USD millions", "pipeline": "USD millions",
            "arr": "USD millions", "cogs": "USD millions", "cash": "USD millions",
            "cac": "USD", "ltv": "USD", "avg_deal_size": "USD",

            # Percentages
            "gross_margin_pct": "%", "net_income_pct": "%", "churn_rate_pct": "%",
            "nrr": "%", "win_rate_pct": "%", "quota_attainment_pct": "%", "uptime_pct": "%",
            "code_coverage_pct": "%", "attrition_rate_pct": "%",

            # Counts
            "headcount": "people", "p1_incidents": "count", "deploys_per_week": "count",

            # Time
            "sales_cycle_days": "days", "cac_payback_months": "months",
            "time_to_fill_days": "days",

            # Ratios
            "ltv_cac": "x", "magic_number": "x",
        }

    def _extract_rep_names(self, fact_base: Dict) -> List[str]:
        """Extract rep names from fact_base."""
        reps = []
        if 'sales_reps' in fact_base:
            for rep in fact_base['sales_reps']:
                if 'name' in rep:
                    reps.append(rep['name'])
        return reps

    def _format_display_name(self, metric_id: str) -> str:
        """Format metric ID into display name."""
        # Handle special cases
        special_names = {
            "ar": "Accounts Receivable",
            "ap": "Accounts Payable",
            "arr": "ARR",
            "nrr": "NRR",
            "cac": "CAC",
            "ltv": "LTV",
            "ltv_cac": "LTV/CAC",
            "ebitda": "EBITDA",
            "cogs": "COGS",
            "sga": "SG&A",
            "nps": "NPS",
        }
        if metric_id in special_names:
            return special_names[metric_id]

        # Default: capitalize words, handle _pct suffix
        name = metric_id.replace("_pct", " %").replace("_", " ")
        return name.title()

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def resolve_metric(self, user_term: str, local_only: bool = False) -> Optional[MetricDefinition]:
        """
        Find metric by name or alias.

        Resolution order:
        1. Local exact match (canonical IDs, registered aliases, underscore normalization)
        2. DCL fuzzy endpoint (skipped when local_only=True)
        3. Local fuzzy fallback (substring matching)

        Args:
            user_term: What the user said (e.g., "AR", "accounts receivable", "revenue")
            local_only: If True, skip DCL fuzzy resolution. Used for multi-word
                phrases in _extract_metrics_from_query to prevent DCL from
                mis-mapping noise phrases like "revenue over time" → "arr".

        Returns:
            MetricDefinition if found, None otherwise
        """
        if not user_term:
            return None

        data_mode = _data_mode_ctx.get()

        # LIVE MODE guard: only block when DCL IS configured but force_local is set
        if data_mode == "live" and self.dcl_url and _force_local_ctx.get():
            raise RuntimeError(
                "LIVE MODE FAILURE: force_local set but data_mode='live' and DCL is configured. "
                "Cannot resolve metrics from fact_base.json in live mode when DCL is available."
            )

        if _force_local_ctx.get():
            return self._resolve_metric_locally(user_term)

        # Try local exact match first — canonical IDs and registered aliases.
        # This prevents DCL's fuzzy resolver from mis-mapping e.g. "revenue" → "arr".
        catalog = self.get_catalog()
        normalized = user_term.lower().strip()
        if normalized in catalog.alias_to_metric:
            metric_id = catalog.alias_to_metric[normalized]
            exact = catalog.metrics.get(metric_id)
            if exact:
                logger.debug(f"Exact local match for '{user_term}' -> '{metric_id}', skipping DCL fuzzy")
                return exact

        # Space → underscore normalization (e.g., "net income" → "net_income")
        underscore_form = normalized.replace(" ", "_")
        if underscore_form != normalized and underscore_form in catalog.alias_to_metric:
            metric_id = catalog.alias_to_metric[underscore_form]
            exact = catalog.metrics.get(metric_id)
            if exact:
                logger.debug(f"Underscore match for '{user_term}' -> '{metric_id}', skipping DCL fuzzy")
                return exact

        # For multi-word phrases: only local resolution (exact + fuzzy substring).
        # DCL's word-overlap scorer mis-maps noise phrases like "show revenue" → "arr".
        if local_only:
            return self._resolve_metric_locally(user_term)

        # Try DCL resolution endpoint for fuzzy/semantic matching
        if self.dcl_url and self._is_dcl_call_allowed():
            try:
                result = self._resolve_metric_via_dcl(user_term)
                if result:
                    return result
            except (httpx.RequestError, httpx.HTTPStatusError, json.JSONDecodeError, KeyError) as e:
                logger.debug(f"DCL metric resolution failed for '{user_term}': {e}")

        # Fall back to catalog-based resolution (uses DCL catalog if available)
        return self._resolve_metric_locally(user_term)

    def _resolve_metric_via_dcl(self, user_term: str) -> Optional[MetricDefinition]:
        """Call DCL's metric resolution endpoint (supports fuzzy matching).

        DCL now does word-overlap scoring against metric names, descriptions,
        and aliases.  On 404, the response may include a ``suggestions`` array
        with the closest candidates — we try the top suggestion as a fallback.
        """
        try:
            response = self._http_client.get(
                f"{self.dcl_url}/api/dcl/semantic-export/resolve/metric",
                params={"q": user_term},
                timeout=5.0,
            )
            if response.status_code == 404:
                # DCL may return suggestions for close matches
                try:
                    body = response.json()
                    suggestions = body.get("suggestions", [])
                    if suggestions:
                        diag(f"[NLQ-DIAG] resolve 404 for '{user_term}', suggestions={suggestions[:3]}")
                        # Try the top suggestion
                        top = suggestions[0]
                        top_id = top if isinstance(top, str) else top.get("id", "")
                        if top_id:
                            return self._resolve_metric_locally(top_id)
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    logger.debug("Failed to parse DCL suggestions from 404 response body: %s", e)
                return None
            response.raise_for_status()

            data = response.json()
            metric_id = data["id"]
            local_units = self._get_metric_units()
            self._record_dcl_success()
            return MetricDefinition(
                id=metric_id,
                display_name=data.get("name", metric_id),
                aliases=data.get("aliases", []),
                unit=local_units.get(metric_id, ""),
                allowed_dimensions=data.get("allowed_dims", []),
                allowed_grains=data.get("allowed_grains", ["quarterly"]),
                domain=PACK_TO_DOMAIN.get(
                    data.get("pack", ""),
                    data.get("pack", "").upper(),
                ),
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 404:
                logger.warning(f"DCL metric resolution error: {e}")
                self._record_dcl_failure()
            return None
        except (httpx.RequestError, json.JSONDecodeError, KeyError) as e:
            logger.warning(f"DCL metric resolution failed: {e}")
            self._record_dcl_failure()
            return None

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search DCL for metrics and entities matching a free-text query.

        Uses the new ``GET /api/dcl/semantic-export/search`` endpoint which
        does ranked keyword matching across all metrics and entities in a
        single call.

        Args:
            query: Free-text search term (e.g. "deploys per week", "revenue by region")
            limit: Maximum number of results to return

        Returns:
            List of ranked result dicts, each with at least ``id``, ``type``
            ('metric' | 'entity'), ``name``, and ``score``.
            Returns empty list if DCL is unavailable or returns no results.
        """
        if not self.dcl_url or _force_local_ctx.get():
            return []

        try:
            response = self._http_client.get(
                f"{self.dcl_url}/api/dcl/semantic-export/search",
                params={"q": query, "limit": limit},
                timeout=5.0,
            )
            if response.status_code == 404:
                return []
            response.raise_for_status()
            data = response.json()
            results = data.get("results", data) if isinstance(data, dict) else data
            return results if isinstance(results, list) else []
        except (httpx.RequestError, httpx.HTTPStatusError, json.JSONDecodeError) as e:
            logger.debug(f"DCL search failed for '{query}': {e}")
            return []

    def _resolve_metric_locally(self, user_term: str) -> Optional[MetricDefinition]:
        """Resolve metric using local catalog."""
        catalog = self.get_catalog()
        normalized = user_term.lower().strip()

        # Try exact match first
        if normalized in catalog.alias_to_metric:
            metric_id = catalog.alias_to_metric[normalized]
            return catalog.metrics.get(metric_id)

        # Try fuzzy match on aliases - require minimum length to avoid false positives
        # e.g., "cu" shouldn't match "customer" -> cac
        min_fuzzy_length = 3
        for alias, metric_id in catalog.alias_to_metric.items():
            # Only fuzzy match if both terms are long enough
            if len(normalized) >= min_fuzzy_length and len(alias) >= min_fuzzy_length:
                # Require the shorter one to be a substantial substring (>50% overlap)
                shorter, longer = (normalized, alias) if len(normalized) <= len(alias) else (alias, normalized)
                if shorter in longer and len(shorter) >= len(longer) * 0.5:
                    return catalog.metrics.get(metric_id)

        return None

    def has_live_ingest_data(self) -> bool:
        """Check whether DCL has live ingested data for the current tenant.

        Uses the catalog's ingest_summary metadata. Returns True only when:
        1. DCL's ingest pipeline is available, AND
        2. The current tenant appears in DCL's tenant list

        If DCL is running but has no data for our tenant, returns False so the
        UI can show a meaningful status (not a false positive).
        """
        if not self.dcl_url:
            return False
        try:
            summary = self.get_ingest_summary()
            if summary is None or not summary.available:
                return False
            # Check if our tenant is in DCL's tenant list
            if summary.tenant_names:
                from src.nlq.config import get_tenant_id
                current = get_tenant_id()
                if current not in summary.tenant_names:
                    logger.debug(
                        "DCL ingest available but tenant %s not in DCL tenants: %s",
                        current, summary.tenant_names
                    )
                    return False
            return True
        except (RuntimeError, AttributeError, KeyError, TypeError) as e:
            logger.debug("Ingest summary check failed: %s", e)
            return False

    def get_ingest_summary(self) -> Optional[IngestSummary]:
        """Return the ingest summary from the cached catalog, or None."""
        catalog = self.get_catalog()
        return catalog.ingest_summary

    def check_dcl_health(self) -> Dict[str, Any]:
        """Check DCL reachability and mode via its health endpoint.

        Returns dict with:
          connected: bool — DCL responded to health check
          phase: str|None — DCL startup phase (ready, warming, degraded)
          data_mode: str|None — DCL data mode (Demo, Ingest, Farm, AAM)
          last_run_id: str|None — last DCL run ID
          last_updated: str|None — last mode change timestamp
          error: str|None — error message if not connected
        """
        if not self.dcl_url:
            return {"connected": False, "error": "DCL_API_URL not configured"}

        try:
            resp = self._http_client.get(
                f"{self.dcl_url}/api/health",
                timeout=5.0,
            )
            if resp.status_code != 200:
                return {
                    "connected": False,
                    "error": f"DCL health returned HTTP {resp.status_code}",
                }
            body = resp.json()
            return {
                "connected": True,
                "phase": body.get("phase"),
                "data_mode": body.get("data_mode"),
                "last_run_id": body.get("last_run_id"),
                "last_updated": body.get("last_updated"),
                "error": body.get("error"),
            }
        except httpx.TimeoutException:
            return {"connected": False, "error": f"DCL health check timed out ({self.dcl_url})"}
        except httpx.RequestError as e:
            return {"connected": False, "error": f"DCL unreachable at {self.dcl_url}: {e}"}

    def get_ingest_runs(self) -> Dict[str, Any]:
        """Fetch detailed ingest run data from DCL.

        Calls GET /api/dcl/ingest/runs to get per-source ingest details
        including row counts, tenants, and source systems.  Falls back
        to the catalog's ingest_summary when the endpoint is unavailable.

        Returns:
            Dict with keys: sources (list), tenants (list), total_rows (int),
            pipe_count (int), available (bool), runs (list of raw run dicts).
        """
        # Try the live endpoint first
        if self.dcl_url and not _force_local_ctx.get():
            try:
                response = self._http_client.get(
                    f"{self.dcl_url}/api/dcl/ingest/runs",
                    timeout=5.0,
                )
                if response.status_code == 200:
                    data = response.json()
                    runs = data if isinstance(data, list) else data.get("runs", [])
                    # Derive aggregates from the runs list
                    sources = sorted({r.get("source_system", "unknown") for r in runs if r.get("source_system")})
                    tenants = sorted({r.get("tenant_id") or r.get("tenant", "unknown") for r in runs if r.get("tenant_id") or r.get("tenant")})
                    total_rows = sum(r.get("row_count", 0) for r in runs)
                    diag(f"[NLQ-DIAG] ingest/runs: {len(runs)} runs, {len(sources)} sources, {len(tenants)} tenants, {total_rows} rows")
                    return {
                        "sources": sources,
                        "tenants": tenants,
                        "total_rows": total_rows,
                        "pipe_count": len(runs),
                        "available": len(runs) > 0,
                        "runs": runs,
                    }
            except (httpx.RequestError, httpx.HTTPStatusError, json.JSONDecodeError) as e:
                logger.debug(f"DCL ingest/runs failed, falling back to catalog: {e}")

        # Fall back to cached ingest_summary from semantic export
        summary = self.get_ingest_summary()
        if summary and summary.available:
            return {
                "sources": summary.source_systems,
                "tenants": summary.tenant_names,
                "total_rows": summary.row_count,
                "pipe_count": summary.pipe_count,
                "available": True,
                "runs": [],
            }

        return {
            "sources": [],
            "tenants": [],
            "total_rows": 0,
            "pipe_count": 0,
            "available": False,
            "runs": [],
        }

    def resolve_entity(self, user_term: str) -> Optional[Dict[str, Any]]:
        """
        Resolve an entity name (e.g., customer, rep) via DCL.

        Args:
            user_term: What the user said (e.g., "Acme Corp", "John Smith")

        Returns:
            Entity definition dict if found, None otherwise
        """
        if not user_term or not self.dcl_url:
            return None

        try:
            response = self._http_client.get(
                f"{self.dcl_url}/api/dcl/semantic-export/resolve/entity",
                params={"q": user_term},
                timeout=5.0,
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except (httpx.RequestError, httpx.HTTPStatusError, json.JSONDecodeError) as e:
            logger.debug(f"DCL entity resolution failed for '{user_term}': {e}")
            return None

    def validate_dimension(self, metric_id: str, dimension: str) -> Tuple[bool, Optional[str]]:
        """
        Check if dimension is valid for this metric.

        Args:
            metric_id: Canonical metric ID
            dimension: Dimension to validate

        Returns:
            (True, None) if valid
            (False, "error message with valid options") if invalid
        """
        catalog = self.get_catalog()
        metric = catalog.metrics.get(metric_id)

        if not metric:
            available = list(catalog.metrics.keys())[:10]
            return (False, f"Unknown metric '{metric_id}'. Available: {', '.join(available)}")

        # Normalize dimension
        dim_normalized = dimension.lower().strip()

        # Check if dimension is allowed
        if dim_normalized in metric.allowed_dimensions:
            return (True, None)

        # Not allowed - provide helpful error
        if metric.allowed_dimensions:
            valid_dims = ", ".join(metric.allowed_dimensions)
            return (False, f"Dimension '{dimension}' not available for '{metric.display_name}'. Valid dimensions: {valid_dims}")
        else:
            return (False, f"Metric '{metric.display_name}' does not support dimensional breakdowns")

    def get_valid_dimensions(self, metric_id: str) -> List[str]:
        """Return list of valid dimensions for a metric."""
        catalog = self.get_catalog()
        metric = catalog.metrics.get(metric_id)
        return metric.allowed_dimensions if metric else []

    def resolve_dimension(self, user_term: str) -> Optional[str]:
        """
        Resolve a user-provided dimension term to its canonical name.

        Handles aliases like "sales rep" -> "rep", "salesperson" -> "rep".

        Args:
            user_term: User-provided dimension term

        Returns:
            Canonical dimension name, or None if not recognized
        """
        if not user_term:
            return None

        term = user_term.lower().strip()

        # Common dimension aliases
        dimension_aliases = {
            "sales rep": "rep",
            "salesperson": "rep",
            "sales representative": "rep",
            "representative": "rep",
            "account exec": "rep",
            "ae": "rep",
            "territory": "region",
            "area": "region",
            "geo": "region",
            "geography": "region",
            "product line": "product",
            "sku": "product",
            "client": "customer",
            "account": "customer",
            "pipeline stage": "stage",
            "deal stage": "stage",
            "sales stage": "stage",
            "funnel stage": "stage",
            "market segment": "segment",
            "vertical": "segment",
            "industry": "segment",
        }

        # Check aliases first
        if term in dimension_aliases:
            return dimension_aliases[term]

        # Check if it's already a canonical dimension name
        catalog = self.get_catalog()
        all_dims = set()
        for metric in catalog.metrics.values():
            all_dims.update(metric.allowed_dimensions)

        if term in all_dims:
            return term

        return None

    def get_all_dimensions(self) -> List[str]:
        """Return list of all known dimension names across all metrics."""
        catalog = self.get_catalog()
        all_dims = set()
        for metric in catalog.metrics.values():
            all_dims.update(metric.allowed_dimensions)
        return sorted(all_dims)

    def get_latest_period(self) -> str:
        """Return the latest period available in the data source.

        In DCL mode, returns current_quarter() (DCL handles period resolution).
        In local mode, scans fact_base quarterly data for the last entry.
        """
        data_mode = _data_mode_ctx.get()
        if self.dcl_url and not _force_local_ctx.get():
            return current_quarter()

        # LIVE MODE: Don't read fact_base for period detection
        if data_mode == "live":
            return current_quarter()

        # Local mode: find latest period from fact_base
        fact_base_path = Path(__file__).parent.parent.parent.parent / "data" / "fact_base.json"
        try:
            with open(fact_base_path, 'r') as f:
                fact_base = json.load(f)
            quarterly = fact_base.get("quarterly", [])
            if quarterly:
                latest = quarterly[-1]
                return latest.get("period", current_quarter())
        except (FileNotFoundError, IOError, json.JSONDecodeError) as e:
            logger.debug("Could not read fact_base for latest period; defaulting to current_quarter(): %s", e)
        return current_quarter()

    def get_all_metrics(self) -> List[str]:
        """Return list of all available metric IDs."""
        return list(self.get_catalog().metrics.keys())

    def get_metric_display_name(self, metric_id: str) -> str:
        """Get display name for a metric."""
        catalog = self.get_catalog()
        metric = catalog.metrics.get(metric_id)
        return metric.display_name if metric else metric_id

    def search_metrics(self, query: str) -> List[MetricDefinition]:
        """Search for metrics matching query."""
        catalog = self.get_catalog()
        query_lower = query.lower()
        results = []

        for metric in catalog.metrics.values():
            # Check metric ID
            if query_lower in metric.id:
                results.append(metric)
                continue
            # Check display name
            if query_lower in metric.display_name.lower():
                results.append(metric)
                continue
            # Check aliases
            if any(query_lower in alias.lower() for alias in metric.aliases):
                results.append(metric)

        return results

    def validate_metrics(self, metric_ids: List[str]) -> Tuple[List[str], List[str]]:
        """
        Validate a list of metric IDs and provide helpful feedback.

        Args:
            metric_ids: List of metric IDs to validate

        Returns:
            Tuple of (valid_metrics, error_messages)
            - valid_metrics: List of metrics that exist in the catalog
            - error_messages: List of helpful error messages for invalid metrics
        """
        catalog = self.get_catalog()
        valid_metrics = []
        error_messages = []

        for metric_id in metric_ids:
            if metric_id in catalog.metrics:
                valid_metrics.append(metric_id)
            else:
                # Try negotiation (e.g., gross_margin_pct → gross_margin in DCL)
                negotiated = self._negotiate_metric_id(metric_id)
                if negotiated != metric_id and negotiated in catalog.metrics:
                    valid_metrics.append(negotiated)
                else:
                    # Try to find similar metrics to suggest
                    similar = self.search_metrics(metric_id)
                    if similar:
                        suggestions = [m.id for m in similar[:3]]
                        error_messages.append(
                            f"Metric '{metric_id}' not found. Did you mean: {', '.join(suggestions)}?"
                        )
                    else:
                        # List some available metrics
                        available = list(catalog.metrics.keys())[:5]
                        error_messages.append(
                            f"Metric '{metric_id}' not found. Available metrics include: {', '.join(available)}"
                        )

        return valid_metrics, error_messages

    def get_helpful_metric_error(self, metric_id: str) -> str:
        """
        Get a helpful error message for an unknown metric.

        Suggests similar metrics or lists available ones.
        """
        similar = self.search_metrics(metric_id)
        if similar:
            suggestions = [m.display_name for m in similar[:3]]
            return f"Metric '{metric_id}' not found. Did you mean: {', '.join(suggestions)}?"
        else:
            catalog = self.get_catalog()
            available = [m.display_name for m in list(catalog.metrics.values())[:5]]
            return f"Metric '{metric_id}' not found. Available metrics include: {', '.join(available)}"

    # =========================================================================
    # METRIC NAME NEGOTIATION — translate NLQ canonical names to DCL IDs
    # =========================================================================

    # Known cross-mappings where NLQ and DCL use different canonical names.
    # DCL sometimes uses base names where NLQ uses _pct suffixed names,
    # or vice versa — and both exist in DCL catalog but only one has data.
    _NLQ_TO_DCL_CROSSMAP: Dict[str, str] = {
        # gross_churn_pct removed — NLQ now uses churn_rate_pct directly
        "net_income_pct": "net_margin_pct",
        "ltv_cac": "ltv_cac_ratio",
        "time_to_fill_days": "time_to_fill",
    }

    def _negotiate_metric_id(self, nlq_metric: str) -> str:
        """Translate an NLQ canonical metric name to the DCL metric ID.

        NLQ's synonym table resolves user terms to NLQ-canonical names
        (e.g. "gross margin" → ``gross_margin_pct``).  DCL's catalog may
        use a different ID for the same concept (e.g. ``gross_margin``).

        Resolution order:
        1. Check known cross-mappings first (explicit overrides take priority).
        2. If ``nlq_metric`` exists in DCL catalog as-is → return unchanged.
        3. If ``nlq_metric`` ends with ``_pct`` and the base name exists → return base.
        4. No match → return unchanged (let DCL return 404 if invalid).
        """
        catalog = self.get_catalog()
        available = set(catalog.metrics.keys())

        # 1. Known cross-mappings (explicit overrides — e.g., uptime_pct → uptime
        #    when both exist in DCL but only one has breakdown data)
        mapped = self._NLQ_TO_DCL_CROSSMAP.get(nlq_metric)
        if mapped and mapped in available:
            diag(f"[NLQ-DIAG] negotiate: {nlq_metric} -> {mapped} (crossmap)")
            return mapped

        # 2. Exact match — no translation needed
        if nlq_metric in available:
            return nlq_metric

        # 3. Strip _pct suffix (e.g. gross_margin_pct → gross_margin)
        if nlq_metric.endswith("_pct"):
            base = nlq_metric[:-4]
            if base in available:
                diag(f"[NLQ-DIAG] negotiate: {nlq_metric} -> {base} (stripped _pct)")
                return base

        # 4. No translation found — log loudly so mismatches don't hide
        logger.warning(
            f"METRIC NEGOTIATION MISS: NLQ metric '{nlq_metric}' has no match in DCL catalog "
            f"({len(available)} metrics available). If this is a naming mismatch, "
            f"add an entry to _NLQ_TO_DCL_CROSSMAP."
        )
        return nlq_metric

    # =========================================================================
    # DATA QUERY API - All data access goes through DCL
    # =========================================================================

    def query(
        self,
        metric: str,
        dimensions: List[str] = None,
        filters: Dict[str, Any] = None,
        time_range: Dict[str, Any] = None,
        grain: str = None,
        order_by: str = None,
        limit: int = None,
        force_local: bool = False,
        data_mode: str = None,
        tenant_id: str = None,
    ) -> Dict[str, Any]:
        """
        Execute a data query against DCL.

        This is the single entry point for all data access. NLQ holds no local data.

        Args:
            metric: Canonical metric ID (e.g., "revenue", "pipeline")
            dimensions: List of dimensions to break down by (e.g., ["region", "segment"])
            filters: Filter criteria (e.g., {"region": "AMER"})
            time_range: Time range specification (e.g., {"period": "2025", "granularity": "quarterly"})
            grain: Time granularity override (e.g., "monthly", "quarterly")
            order_by: Sort order ("asc" or "desc") for ranking queries
            limit: Number of results to return for ranking queries
            force_local: If True, skip DCL and use local fact_base.json

        Returns:
            Query result from DCL with data points

        Raises:
            DCLQueryError: If DCL returns an error or is unavailable
        """
        ctx_force = _force_local_ctx.get()
        # Auto-read data_mode from context when not explicitly provided
        if data_mode is None:
            data_mode = _data_mode_ctx.get()
        diag(f"[NLQ-DIAG] query() called: metric={metric}, force_local={force_local}, ctx_force={ctx_force}, dcl_url={bool(self.dcl_url)}, data_mode={data_mode}")

        # LIVE MODE guard: only block when DCL IS configured but caller
        # forces local — that's the real "silent fallback" scenario.
        # When DCL isn't configured at all, local data is the only source.
        if data_mode == "live" and self.dcl_url and (force_local or ctx_force):
            raise RuntimeError(
                "LIVE MODE FAILURE: force_local=True but data_mode='live' and DCL is configured. "
                "Cannot serve demo data in live mode when DCL is available. Check request configuration."
            )

        if force_local or ctx_force or not self.dcl_url:
            # Determine reason for fallback
            if force_local or ctx_force:
                reason = "Demo mode selected"
            else:
                reason = "DCL not configured (DCL_API_URL not set) — using local tenant data"
            diag(f"[NLQ-DIAG] query() -> LOCAL FALLBACK ({reason})")
            result = self._query_local_fallback(metric, dimensions, filters, time_range, grain, order_by, limit)
            result["data_source"] = "demo"
            result["data_source_reason"] = reason
            return result

        try:
            # Transform time_range from NLQ format to DCL format
            # NLQ sends: {"period": "2025-Q4", "granularity": "quarterly"}
            # DCL expects: {"start": "2025-Q4", "end": "2025-Q4"} + top-level grain
            dcl_time_range = {}
            dcl_grain = grain
            if time_range:
                period = time_range.get("period")
                if period:
                    dcl_time_range = {"start": period, "end": period}
                else:
                    # Pass through start/end if already in DCL format
                    if "start" in time_range:
                        dcl_time_range["start"] = time_range["start"]
                    if "end" in time_range:
                        dcl_time_range["end"] = time_range["end"]
                # Extract granularity and convert to DCL grain format
                granularity = time_range.get("granularity")
                if granularity and not dcl_grain:
                    dcl_grain = GRAIN_TO_DCL.get(granularity, granularity)

            # Map grain to DCL short form if provided directly
            if dcl_grain:
                dcl_grain = GRAIN_TO_DCL.get(dcl_grain, dcl_grain)

            # Negotiate metric name: NLQ canonical → DCL catalog ID
            dcl_metric = self._negotiate_metric_id(metric)

            payload = {
                "metric": dcl_metric,
                "dimensions": dimensions or [],
                "filters": filters or {},
                "time_range": dcl_time_range,
                "grain": dcl_grain,
                "tenant_id": tenant_id,
            }
            if data_mode:
                payload["data_mode"] = data_mode
            if order_by:
                payload["order_by"] = order_by
            if limit:
                payload["limit"] = limit

            diag(f"[NLQ-DIAG] query() -> DCL POST {self.dcl_url}/api/dcl/query payload={json.dumps(payload, default=str)[:300]}")
            response = self._http_client.post(
                f"{self.dcl_url}/api/dcl/query",
                json=payload
            )
            diag(f"[NLQ-DIAG] query() <- DCL status={response.status_code}, body={response.text[:500]}")

            if response.status_code == 404:
                negotiation_note = (
                    f" (negotiated from NLQ '{metric}')" if dcl_metric != metric else ""
                )
                error_msg = (
                    f"DCL returned 404 for metric '{dcl_metric}'{negotiation_note} "
                    f"at {self.dcl_url}/api/dcl/query"
                )
                logger.warning(f"DCL METRIC NOT FOUND: {error_msg}")
                return {"error": error_msg, "status": "not_found"}
            elif response.status_code == 400:
                err_body = response.json()
                error_detail = err_body.get("detail", {})
                if isinstance(error_detail, dict):
                    error_msg = error_detail.get("error", str(error_detail))
                else:
                    error_msg = str(error_detail) if error_detail else "Invalid query"
                return {"error": error_msg, "status": "bad_request"}

            response.raise_for_status()
            dcl_body = response.json()

            # When DCL explicitly reports ingest_empty (no ingested data for
            # this tenant/metric), fall back to local tenant data rather than
            # returning zeros.  This is NOT a silent fallback: DCL told us
            # explicitly that its ingest store is empty; the local tenant file
            # is the canonical data source until real data is ingested.
            dcl_meta_source = (dcl_body.get("metadata") or {}).get("source", "")
            dcl_data = dcl_body.get("data", [])
            if dcl_meta_source == "ingest_empty" and not dcl_data:
                diag(f"[NLQ-DIAG] query() DCL returned ingest_empty — falling back to local tenant data")
                result = self._query_local_fallback(metric, dimensions, filters, time_range, grain, order_by, limit)
                result["data_source"] = "demo"
                result["data_source_reason"] = "DCL ingest store empty for this tenant — using local tenant data"
                return result

            normalized = self._normalize_dcl_query_response(dcl_body)

            return normalized

        except httpx.HTTPStatusError as e:
            logger.error(f"DCL query failed: {e}")
            error_msg = f"DCL query failed with status {e.response.status_code}"
            return {"error": error_msg, "status": "error"}
        except (httpx.RequestError, json.JSONDecodeError) as e:
            logger.error(f"DCL query error: {e}")
            error_msg = f"DCL unavailable: {e}"
            return {"error": error_msg, "status": "error"}

    def _normalize_dcl_query_response(self, dcl_response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize DCL query response to the format NLQ callers expect.

        DCL returns:
          {metric, metric_name, unit, grain,
           data: [{period, value, dimensions, rank}],
           metadata: {freshness (ISO), quality_score, record_count,
                      run_id, tenant_id, snapshot_name, run_timestamp, ...},
           provenance: [{source_system, freshness ("2h"), quality_score}]}

        NLQ callers expect:
          {status: "ok", metric, data: [{period, value, ...}],
           metadata: {...}, unit, source: "dcl", ...}
        """
        # DCL returns metadata.source: "ingest" or "fact_base"
        # data_source reflects where NLQ got the data from:
        #   "live"  = DCL ingest (real ingested data)
        #   "dcl"   = DCL served it from seed/fact_base (pipeline works, data not yet ingested)
        #   "demo"  = NLQ's own local fallback (pipeline bypassed — only set in _query_local_fallback)
        dcl_source = (dcl_response.get("metadata") or {}).get("source", "")
        if dcl_source == "ingest":
            data_source = "live"
            data_source_reason = None
        else:
            # DCL returned data (fact_base or unknown source) — pipeline is working,
            # but this metric doesn't have ingested data yet
            data_source = "dcl"
            data_source_reason = f"DCL served from {dcl_source or 'unknown'} (no ingested data for this metric)" if dcl_source == "fact_base" else None

        normalized: Dict[str, Any] = {
            "status": "ok",
            "source": "dcl",
            "data_source": data_source,
            "data_source_reason": data_source_reason,
            "metric": dcl_response.get("metric"),
            "data": dcl_response.get("data", []),
        }

        # Carry over unit from DCL response (top-level, not per-row)
        if dcl_response.get("unit"):
            normalized["unit"] = dcl_response["unit"]
        if dcl_response.get("metric_name"):
            normalized["metric_name"] = dcl_response["metric_name"]

        # Preserve metadata with human-friendly freshness from provenance
        metadata = dcl_response.get("metadata", {})
        provenance = dcl_response.get("provenance") or []
        if provenance:
            # Use human-friendly freshness from provenance (e.g., "2h")
            # instead of metadata.freshness which is an ISO timestamp
            metadata["freshness_display"] = provenance[0].get("freshness", "")
            metadata["provenance"] = provenance
        else:
            metadata.setdefault("freshness_display", "")
        normalized["metadata"] = metadata

        # Derive source_systems from provenance[] OR metadata.sources[]
        # DCL may provide either: provenance[].source_system (detailed) or
        # metadata.sources (compact list, e.g. ["salesforce"])
        source_systems = [
            p.get("source_system") for p in provenance
            if p.get("source_system")
        ]
        if not source_systems and metadata.get("sources"):
            source_systems = list(metadata["sources"])

        # Build structured run provenance for UI Trust Badge
        # Include source_system (singular) for harness/API consumers
        # Prioritize SOR source (highest quality_score) over array order
        is_sor = any(
            (p.get("quality_score") or 0) >= 0.9
            for p in provenance
        ) if provenance else False
        if provenance:
            _best = max(provenance, key=lambda p: p.get("quality_score") or 0)
            primary_source = _best.get("source_system") or (source_systems[0] if source_systems else None)
        else:
            primary_source = source_systems[0] if source_systems else None
        normalized["run_provenance"] = {
            "run_id": metadata.get("run_id"),
            "tenant_id": metadata.get("tenant_id"),
            "snapshot_name": metadata.get("snapshot_name"),
            "run_timestamp": metadata.get("run_timestamp"),
            "source_systems": source_systems,
            "source_system": primary_source,
            "is_sor": is_sor,
            "freshness": metadata.get("freshness_display", ""),
            "quality_score": metadata.get("quality_score"),
            "mode": metadata.get("mode"),
        }

        # Carry over entity resolution and conflict data when present
        for key in ("entity", "conflicts", "temporal_warning"):
            if dcl_response.get(key):
                normalized[key] = dcl_response[key]

        return normalized

    def query_ranking(
        self,
        metric: str,
        dimension: str,
        order_by: str = "desc",
        limit: int = 1,
        time_range: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Execute a ranking query to find top/bottom items by a metric.

        This is specialized for superlative queries like "who is our top rep?"

        Args:
            metric: Metric to rank by (e.g., "quota_attainment_pct", "win_rate_pct", "revenue")
            dimension: Dimension to rank (e.g., "rep", "region", "service")
            order_by: "desc" for highest first, "asc" for lowest first
            limit: Number of results to return
            time_range: Optional time range filter

        Returns:
            Query result with ranked data
        """
        data_mode = _data_mode_ctx.get()

        # LIVE MODE: Never fall back to local ranking data
        if data_mode == "live" and (_force_local_ctx.get() or not self.dcl_url):
            raise RuntimeError(
                "LIVE MODE FAILURE: Cannot serve ranking query from fact_base.json. "
                "DCL must be available for live ranking queries."
            )

        if _force_local_ctx.get() or not self.dcl_url:
            return self._query_ranking_local(metric, dimension, order_by, limit, time_range)

        # DCL mode - use the general query with ranking parameters
        return self.query(
            metric=metric,
            dimensions=[dimension],
            time_range=time_range,
            order_by=order_by,
            limit=limit,
        )

    def _query_ranking_local(
        self,
        metric: str,
        dimension: str,
        order_by: str = "desc",
        limit: int = 1,
        time_range: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Local ranking query implementation for dev mode.

        Handles specialized data structures like quota_by_rep, win_rate_by_rep, etc.
        """
        from pathlib import Path

        fact_base_path = Path(__file__).parent.parent.parent.parent / "data" / "fact_base.json"
        try:
            with open(fact_base_path, 'r') as f:
                fact_base = json.load(f)
        except (FileNotFoundError, IOError, json.JSONDecodeError) as e:
            logger.warning(f"Local ranking query failed - no fact_base.json: {e}")
            return {"error": "No data available", "status": "error"}

        # Determine period to use
        period = self.get_latest_period()
        if time_range:
            period = time_range.get("period", period)

        # Map metric + dimension to data source
        data_source_map = {
            ("quota_attainment_pct", "rep"): "quota_by_rep",
            ("win_rate_pct", "rep"): "win_rate_by_rep",
            ("pipeline", "rep"): "pipeline_by_rep",
            ("slo_attainment_pct", "service"): "slo_attainment_by_service",
            ("revenue", "region"): "revenue_by_region",
            ("revenue", "segment"): "revenue_by_segment",
            ("pipeline", "region"): "pipeline_by_region",
            ("pipeline", "stage"): "pipeline_by_stage",
            ("headcount", "department"): "headcount_by_department",
            ("deal_value", "deal"): "top_deals",
        }

        # Find the data source
        data_key = data_source_map.get((metric, dimension))

        # If not in map, try constructing the key
        if not data_key:
            data_key = f"{metric}_by_{dimension}"

        if data_key not in fact_base:
            return {"error": f"No ranking data for {metric} by {dimension}", "status": "not_found"}

        raw_data = fact_base[data_key]

        # Handle different data structures
        result_data = []

        # Check if it's period-keyed data
        if isinstance(raw_data, dict):
            # For top_deals, it's different - period is a key to array of deals
            if data_key == "top_deals":
                deals = raw_data.get(period, raw_data.get(current_year(), []))
                if isinstance(deals, list):
                    result_data = [
                        {"company": d.get("company"), "value": d.get("value"),
                         "rep": d.get("rep"), "quarter": d.get("quarter")}
                        for d in deals
                    ]
            # Period-keyed dimensional data
            elif period in raw_data:
                period_data = raw_data[period]
                if isinstance(period_data, dict):
                    for name, values in period_data.items():
                        if name in ("Total", "total"):
                            continue
                        if isinstance(values, dict):
                            # Nested structure like quota_by_rep
                            value_field = "attainment_pct" if "attainment_pct" in values else "value"
                            value_field = value_field if value_field in values else list(values.keys())[0] if values else "value"
                            result_data.append({
                                dimension: name,
                                "value": values.get(value_field, values.get("value", 0)),
                                **values  # Include all fields
                            })
                        else:
                            # Simple key-value
                            result_data.append({
                                dimension: name,
                                "value": values
                            })
            else:
                # Try latest period
                periods = list(raw_data.keys())
                if periods:
                    latest_period = sorted(periods)[-1]
                    period_data = raw_data[latest_period]
                    if isinstance(period_data, dict):
                        for name, values in period_data.items():
                            if name in ("Total", "total"):
                                continue
                            if isinstance(values, dict):
                                value_field = "attainment_pct" if "attainment_pct" in values else "value"
                                result_data.append({
                                    dimension: name,
                                    "value": values.get(value_field, 0),
                                    **values
                                })
                            else:
                                result_data.append({
                                    dimension: name,
                                    "value": values
                                })
        elif isinstance(raw_data, list):
            # Already a list of items
            result_data = raw_data

        # Sort the data
        if result_data:
            reverse = (order_by.lower() == "desc")

            def get_sort_value(item):
                # Try common value field names in priority order
                for key in ("value", "attainment_pct", "pipeline", "slo_attainment_pct", "revenue", "headcount"):
                    if key in item:
                        v = item[key]
                        return v if isinstance(v, (int, float)) else 0
                return 0

            result_data = sorted(result_data, key=get_sort_value, reverse=reverse)

        # Apply limit
        if limit and limit > 0:
            result_data = result_data[:limit]

        return {
            "metric": metric,
            "dimension": dimension,
            "period": period,
            "data": result_data,
            "status": "ok",
            "source": "local_fallback"
        }

    def _apply_sorting_and_limit(
        self,
        data: List[Dict[str, Any]],
        order_by: str = None,
        limit: int = None
    ) -> List[Dict[str, Any]]:
        """
        Apply sorting and limit to query results.

        Args:
            data: List of result dicts
            order_by: "asc" or "desc"
            limit: Max number of results to return

        Returns:
            Sorted and limited data list
        """
        if not data:
            return data

        # Sort by value if order_by is specified
        if order_by:
            reverse = (order_by.lower() == "desc")
            # Get the value field - look for 'value' or other numeric fields
            def get_sort_key(item):
                # Try common value field names
                for key in ("value", "attainment_pct", "pipeline", "revenue", "slo_attainment_pct", "headcount"):
                    if key in item:
                        val = item[key]
                        return val if isinstance(val, (int, float)) else 0
                # If dict has nested value
                if isinstance(item, dict):
                    for v in item.values():
                        if isinstance(v, (int, float)):
                            return v
                        if isinstance(v, dict) and "value" in v:
                            return v["value"]
                return 0

            data = sorted(data, key=get_sort_key, reverse=reverse)

        # Apply limit
        if limit and limit > 0:
            data = data[:limit]

        return data

    def _query_local_fallback(
        self,
        metric: str,
        dimensions: List[str] = None,
        filters: Dict[str, Any] = None,
        time_range: Dict[str, Any] = None,
        grain: str = None,
        order_by: str = None,
        limit: int = None,
    ) -> Dict[str, Any]:
        """
        Local fallback for dev mode when DCL is not available.

        Reads from fact_base.json to provide mock data.
        """
        from pathlib import Path

        fact_base_path = Path(__file__).parent.parent.parent.parent / "data" / "fact_base.json"
        try:
            with open(fact_base_path, 'r') as f:
                fact_base = json.load(f)
        except (FileNotFoundError, IOError, json.JSONDecodeError) as e:
            logger.warning(f"Local fallback failed - no fact_base.json: {e}")
            return {"error": "No data available (DCL not configured, no local fallback)", "status": "error"}

        # Build response based on query type
        result = {
            "metric": metric,
            "data": [],
            "status": "ok",
            "source": "local_fallback",
            "metadata": {
                "mode": "Demo",
                "quality_score": 1.0,
                "freshness_display": "",
            },
            "run_provenance": {
                "run_id": None,
                "tenant_id": None,
                "snapshot_name": "fact_base.json",
                "run_timestamp": None,
                "source_systems": ["Local Dev"],
                "freshness": "",
                "quality_score": 1.0,
                "mode": "Demo",
            },
        }

        # Validate dimensions before attempting lookup
        if dimensions:
            for dim in dimensions:
                is_valid, error_msg = self.validate_dimension(metric, dim)
                if not is_valid:
                    return {"error": error_msg, "status": "error"}

        # Handle dimensional queries
        period_filter = time_range.get("period") if time_range else None
        default_period = self.get_latest_period()

        if dimensions:
            # Try multiple key patterns:
            # 1. {metric}_by_{dimensions} - e.g., "engagement_score_by_department"
            # 2. {base_metric}_by_{dimensions} - e.g., "engagement_by_department"
            # 3. For metrics ending in _rate/_pct/_score, try without suffix
            dim_suffix = '_'.join(dimensions)
            dim_key_variants = [
                f"{metric}_by_{dim_suffix}",
            ]
            # Add variant without common suffixes
            for suffix in ("_score", "_rate", "_pct", "_count", "_days", "_hours"):
                if metric.endswith(suffix):
                    base_metric = metric[:-len(suffix)]
                    dim_key_variants.append(f"{base_metric}_by_{dim_suffix}")
                    break

            dim_key = None
            for variant in dim_key_variants:
                if variant in fact_base:
                    dim_key = variant
                    break

            if dim_key and dim_key in fact_base:
                dim_data = fact_base[dim_key]

                # Data is keyed by period - get the right period's data
                if isinstance(dim_data, dict):
                    # Try to get specific period or default
                    period_data = None
                    if period_filter and period_filter in dim_data:
                        period_data = dim_data[period_filter]
                    elif default_period in dim_data:
                        period_data = dim_data[default_period]
                    elif dim_data:
                        # Take the latest period
                        period_data = dim_data.get(list(dim_data.keys())[-1])

                    if period_data and isinstance(period_data, dict):
                        # Convert dict {dim_value: value} to list of dicts
                        dimension = dimensions[0] if dimensions else "label"
                        result["data"] = [
                            {dimension: k, "value": v}
                            for k, v in period_data.items()
                            if k not in ("Total", "total")
                        ]
                        result["data"] = self._apply_sorting_and_limit(result["data"], order_by, limit)
                        return result

            # Try single dimension with key variants
            for dim in dimensions:
                dim_key_single_variants = [f"{metric}_by_{dim}"]
                for suffix in ("_score", "_rate", "_pct", "_count", "_days", "_hours"):
                    if metric.endswith(suffix):
                        base_metric = metric[:-len(suffix)]
                        dim_key_single_variants.append(f"{base_metric}_by_{dim}")
                        break

                dim_key = None
                for variant in dim_key_single_variants:
                    if variant in fact_base:
                        dim_key = variant
                        break

                if dim_key and dim_key in fact_base:
                    dim_data = fact_base[dim_key]

                    if isinstance(dim_data, dict):
                        period_data = None
                        if period_filter and period_filter in dim_data:
                            period_data = dim_data[period_filter]
                        elif default_period in dim_data:
                            period_data = dim_data[default_period]
                        elif dim_data:
                            period_data = dim_data.get(list(dim_data.keys())[-1])

                        if period_data and isinstance(period_data, dict):
                            result["data"] = [
                                {dim: k, "value": v}
                                for k, v in period_data.items()
                                if k not in ("Total", "total")
                            ]
                            result["data"] = self._apply_sorting_and_limit(result["data"], order_by, limit)
                            return result

        # Handle time series queries - respect time_range filter
        if "quarterly" in fact_base:
            quarterly_data = []
            period_filter = time_range.get("period") if time_range else None
            granularity = time_range.get("granularity", "quarterly") if time_range else "quarterly"

            for entry in fact_base["quarterly"]:
                if metric not in entry:
                    continue

                entry_period = entry.get("period", f"{entry.get('year')}-{entry.get('quarter')}")
                entry_year = str(entry.get("year", ""))

                # Apply period filter
                if period_filter:
                    # Year filter (e.g., "2025")
                    if period_filter.isdigit() and len(period_filter) == 4:
                        if entry_year != period_filter:
                            continue
                    # Quarter filter (e.g., "2025-Q4")
                    elif "-Q" in period_filter:
                        if entry_period != period_filter:
                            continue

                quarterly_data.append({
                    "period": entry_period,
                    "value": entry[metric]
                })

            if quarterly_data:
                result["data"] = quarterly_data
                return result

        # Try direct metric lookup
        if metric in fact_base:
            result["data"] = fact_base[metric]
            return result

        return {"error": f"Metric '{metric}' not found in local data", "status": "not_found"}

    # =========================================================================
    # GRAPH RESOLUTION API - Semantic graph traversal via DCL
    # =========================================================================

    def resolve_via_graph(
        self,
        concepts: List[str],
        dimensions: Optional[List[str]] = None,
        filters: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Resolve a query via DCL's semantic graph traversal.

        Calls POST /api/dcl/resolve with a structured QueryIntent.
        The graph engine finds data paths across systems, validates
        dimension combinations, resolves hierarchies, and returns
        confidence-scored results with full provenance.

        Args:
            concepts: List of concept names to resolve (e.g., ["revenue"])
            dimensions: Optional dimensions to slice by (e.g., ["region", "cost_center"])
            filters: Optional filters (e.g., [{"dimension": "division", "value": "Cloud"}])

        Returns:
            Graph resolution result dict with:
            - can_answer (bool): Whether the graph can resolve this query
            - confidence (float): Path confidence score
            - resolved_concepts: List of resolved concept mappings
            - provenance: Full provenance chain (systems, edges, paths)
            - warnings: List of any warnings (e.g., cross-system join issues)
            - join_paths: Cross-system join paths if applicable
            - filters_resolved: Hierarchy/overlay resolution of filter values

            Returns {"can_answer": False, "reason": "..."} on failure/unavailable.
        """
        data_mode = _data_mode_ctx.get()

        # LIVE MODE: Never use local catalog fallback for graph resolution
        if data_mode == "live" and _force_local_ctx.get():
            raise RuntimeError(
                "LIVE MODE FAILURE: Cannot resolve graph query from local catalog. "
                "DCL must be available for live graph resolution."
            )

        if _force_local_ctx.get():
            return self._resolve_via_catalog(concepts, dimensions, filters)

        # Try DCL's graph resolution endpoint first
        if self.dcl_url:
            payload = {
                "concepts": concepts,
                "dimensions": dimensions or [],
                "filters": filters or [],
            }

            try:
                response = self._http_client.post(
                    f"{self.dcl_url}/api/dcl/resolve",
                    json=payload,
                )

                if response.status_code not in (404, 405):
                    response.raise_for_status()
                    result = response.json()
                    result.setdefault("can_answer", False)
                    result.setdefault("confidence", 0.0)
                    result.setdefault("warnings", [])
                    result.setdefault("source", "dcl_graph")
                    return result

                # 404/405 = endpoint not deployed yet, fall through to catalog
                diag("[NLQ-DIAG] DCL /api/dcl/resolve not available, using catalog fallback")

            except httpx.ConnectError:
                logger.warning("DCL server unreachable for graph resolution, using catalog")
            except httpx.TimeoutException:
                logger.warning("DCL graph resolution timed out, using catalog")
            except Exception as e:
                logger.warning(f"DCL graph resolution failed: {e}, using catalog")

        # Catalog-based fallback — uses DCL's semantic catalog to resolve
        return self._resolve_via_catalog(concepts, dimensions, filters)

    # -----------------------------------------------------------------
    # Hierarchy data used by catalog-based graph resolution.
    # Maps parent dimension values to their children.  When DCL's graph
    # endpoint comes online this moves to DCL; for now NLQ mirrors the
    # contour map so the boss-query demo works end-to-end.
    # -----------------------------------------------------------------
    _HIERARCHY: Dict[str, Dict[str, List[str]]] = {
        "division": {
            "Cloud": ["Cloud East", "Cloud West"],
            "Professional Services": ["PS Americas", "PS EMEA"],
            "Platform": ["Platform Core", "Platform Edge"],
        },
        "region": {
            "North America": ["US", "Canada"],
            "EMEA": ["UK", "Germany"],
            "APAC": ["Japan", "Australia"],
        },
        "cost_center": {
            "Engineering": ["Cloud Engineering", "Platform Engineering"],
            "Sales": ["Enterprise Sales", "Mid-Market Sales"],
        },
    }

    # System-of-record mapping per metric domain
    _SYSTEM_MAP: Dict[str, Dict[str, str]] = {
        "cfo": {"primary": "netsuite_erp", "secondary": "salesforce_crm"},
        "cro": {"primary": "salesforce_crm"},
        "chro": {"primary": "workday_hcm"},
        "coo": {"primary": "netsuite_erp", "secondary": "workday_hcm"},
        "cto": {"primary": "jira_eng", "secondary": "datadog_ops"},
    }

    # Authoritative system for organizational dimensions.
    # Used to resolve cross-system joins: if a metric lives in netsuite_erp
    # but the dimension lives in workday_hcm, the join crosses systems.
    _DIMENSION_SYSTEM: Dict[str, str] = {
        "cost_center": "workday_hcm",
        "department": "workday_hcm",
        "division": "workday_hcm",
        "job_level": "workday_hcm",
        "region": "netsuite_erp",
        "segment": "netsuite_erp",
        "product": "salesforce_crm",
    }

    def _resolve_via_catalog(
        self,
        concepts: List[str],
        dimensions: Optional[List[str]] = None,
        filters: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Resolve a query using the DCL semantic catalog.

        This is a fallback for when DCL's /api/dcl/resolve endpoint is
        unavailable.  Uses the cached catalog to find concept→system
        mappings, validate dimensions, resolve hierarchy filters, and
        build cross-system join paths.
        """
        catalog = self.get_catalog()
        dims = dimensions or []
        fltrs = filters or []

        # --- Resolve concepts ---
        resolved_concepts = []
        all_warnings: List[str] = []
        provenance_systems: List[str] = []

        for concept_name in concepts:
            metric = catalog.metrics.get(concept_name)
            if not metric:
                # Try alias resolution
                metric_id = catalog.alias_to_metric.get(concept_name.lower())
                metric = catalog.metrics.get(metric_id) if metric_id else None

            if not metric:
                return {
                    "can_answer": False,
                    "reason": f"Concept '{concept_name}' not recognized in semantic catalog",
                    "source": "catalog_fallback",
                }

            pack = metric.domain.lower() if metric.domain else "unknown"
            systems = self._SYSTEM_MAP.get(pack, {})
            primary = systems.get("primary", "unknown")
            provenance_systems.append(primary)
            if systems.get("secondary"):
                provenance_systems.append(systems["secondary"])

            resolved_concepts.append({
                "concept": metric.id,
                "display_name": metric.display_name,
                "system": primary,
                "field": metric.id,
                "confidence": 0.9,
            })

        # --- Validate dimensions & build join paths ---
        join_paths = []
        for dim in dims:
            # Check if any resolved concept supports this dimension directly
            direct_match = any(
                dim in (catalog.metrics.get(rc["concept"]) or metric).allowed_dimensions
                for rc in resolved_concepts
            )

            if direct_match:
                join_paths.append({
                    "dimension": dim,
                    "type": "direct",
                    "confidence": 0.9,
                })
            else:
                # Dimension exists in catalog but needs cross-system join
                dim_exists = dim in catalog.dimensions or any(
                    dim in m.allowed_dimensions for m in catalog.metrics.values()
                )
                if dim_exists:
                    # Use authoritative dimension→system mapping first,
                    # then fall back to scanning metrics in the catalog.
                    owner_system = self._DIMENSION_SYSTEM.get(dim)
                    if not owner_system:
                        for m in catalog.metrics.values():
                            if dim in m.allowed_dimensions:
                                owner_pack = m.domain.lower() if m.domain else ""
                                owner_systems = self._SYSTEM_MAP.get(owner_pack, {})
                                owner_system = owner_systems.get("primary", "unknown")
                                break

                    join_paths.append({
                        "dimension": dim,
                        "type": "cross_system_join",
                        "source_system": provenance_systems[0] if provenance_systems else "unknown",
                        "join_system": owner_system or "unknown",
                        "confidence": 0.6,
                    })
                    all_warnings.append(
                        f"Cross-system join required for '{dim}' — "
                        f"data reconciliation between systems may affect accuracy"
                    )
                else:
                    all_warnings.append(f"Dimension '{dim}' not found in catalog")

        # --- Resolve filters (hierarchy expansion) ---
        filters_resolved = {}
        for f in fltrs:
            dim_name = f.get("dimension", "")
            value = f.get("value", "")
            hierarchy = self._HIERARCHY.get(dim_name, {})
            # Case-insensitive hierarchy lookup (query text is lowered)
            children = hierarchy.get(value)
            if not children:
                for hkey, hvals in hierarchy.items():
                    if hkey.lower() == value.lower():
                        children = hvals
                        value = hkey  # Use canonical casing
                        break
            if children:
                filters_resolved[dim_name] = {
                    "original": value,
                    "expanded": children,
                    "type": "hierarchy_expansion",
                }
            else:
                filters_resolved[dim_name] = {
                    "original": value,
                    "expanded": [value],
                    "type": "exact_match",
                }

        # --- Compute overall confidence ---
        if not join_paths:
            confidence = 0.9
        else:
            path_confidences = [jp["confidence"] for jp in join_paths]
            confidence = min(path_confidences) * 0.9  # Reduce for multi-hop

        can_answer = confidence >= 0.3 and len(resolved_concepts) > 0

        # --- Build provenance ---
        unique_systems = sorted(set(provenance_systems))
        provenance = [
            {"source_system": sys, "freshness": "catalog", "quality_score": 0.9}
            for sys in unique_systems
        ]

        return {
            "can_answer": can_answer,
            "confidence": round(confidence, 2),
            "resolved_concepts": resolved_concepts,
            "join_paths": join_paths,
            "filters_resolved": filters_resolved,
            "provenance": provenance,
            "warnings": all_warnings,
            "source": "catalog_fallback",
        }

    def close(self):
        """Close HTTP client."""
        if self._http_client:
            self._http_client.close()
            self._http_client = None


# Singleton instance
_semantic_client: Optional[DCLSemanticClient] = None


def get_semantic_client() -> DCLSemanticClient:
    global _semantic_client
    if _semantic_client is None:
        _semantic_client = DCLSemanticClient()
    return _semantic_client


def set_force_local(value: bool):
    """Legacy setter — prefer using force_local_data() context manager instead."""
    _force_local_ctx.set(value)


def set_data_mode(value: Optional[str]):
    """Set the data_mode for the current request context.

    When set to 'live', all DCL queries will include data_mode='live' so DCL
    checks the ingest buffer first.  When set to 'demo', force_local is also
    set so queries hit fact_base.json.
    """
    _data_mode_ctx.set(value)


def get_data_mode() -> Optional[str]:
    """Return the data_mode set for the current request context."""
    return _data_mode_ctx.get()


@contextlib.contextmanager
def force_local_data():
    """Context manager that forces DCL client to use local fact_base.json.

    Usage:
        with force_local_data():
            result = client.query(...)  # Uses local data

    Replaces the error-prone set_force_local(True) / finally: set_force_local(False)
    pattern. Guarantees cleanup even if the handler raises.
    """
    token = _force_local_ctx.set(True)
    try:
        yield
    finally:
        _force_local_ctx.reset(token)
