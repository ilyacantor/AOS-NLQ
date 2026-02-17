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
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

_force_local_ctx: contextvars.ContextVar[bool] = contextvars.ContextVar('_force_local_ctx', default=False)

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
class SemanticCatalog:
    """Complete semantic catalog from DCL."""
    metrics: Dict[str, MetricDefinition] = field(default_factory=dict)
    dimensions: Dict[str, List[str]] = field(default_factory=dict)  # dimension -> valid values
    alias_to_metric: Dict[str, str] = field(default_factory=dict)  # alias -> metric_id

    def build_alias_index(self):
        """Build reverse lookup from aliases to metric IDs.

        Two-pass approach ensures aliases take precedence over canonical IDs.
        This allows "attrition" (alias) to map to "attrition_rate" even though
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

    def __init__(self, dcl_base_url: Optional[str] = None):
        raw_url = dcl_base_url or os.environ.get("DCL_API_URL")
        self.dcl_url = raw_url.rstrip("/") if raw_url else None
        self._catalog: Optional[SemanticCatalog] = None
        self._cache_time: float = 0
        self._http_client: Optional[httpx.Client] = None
        self._mode: str = "dcl" if self.dcl_url else "local"

        # H4: Explicit data source tracking — callers can inspect this
        self._catalog_source: str = "none"  # "dcl", "local", "local_fallback"

        if self.dcl_url:
            logger.info(f"DCL semantic client initialized - DCL mode (endpoint: {self.dcl_url})")
        else:
            logger.info("DCL semantic client initialized - LOCAL DEV mode (using fact_base.json)")

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
        if force_local or _force_local_ctx.get():
            catalog = self._build_local_catalog()
            return catalog

        current_time = time.time()

        # Return cached if valid
        if (not force_refresh
            and self._catalog is not None
            and current_time - self._cache_time < CACHE_TTL_SECONDS):
            return self._catalog

        # Try to fetch from DCL if configured
        if self.dcl_url:
            try:
                catalog = self._fetch_from_dcl()
                if catalog:
                    self._catalog = catalog
                    self._cache_time = current_time
                    self._catalog_source = "dcl"
                    logger.info(f"Loaded semantic catalog from DCL ({len(catalog.metrics)} metrics)")
                    return catalog
            except (httpx.RequestError, httpx.HTTPStatusError, json.JSONDecodeError, KeyError) as e:
                logger.warning(
                    f"DCL catalog fetch failed: {e} — falling back to local fact_base.json. "
                    f"Data may be stale. Check DCL_API_URL or DCL service health."
                )

        # Local dev mode or DCL fallback
        catalog = self._build_local_catalog()
        self._catalog = catalog
        self._cache_time = current_time

        if self.dcl_url:
            # DCL was configured but unavailable — this is a fallback
            self._catalog_source = "local_fallback"
            logger.warning(
                f"Using local_fallback catalog ({len(catalog.metrics)} metrics). "
                f"DCL was configured but unavailable."
            )
        else:
            self._catalog_source = "local"
            logger.debug(f"Using local catalog ({len(catalog.metrics)} metrics)")

        return catalog

    def _fetch_from_dcl(self) -> Optional[SemanticCatalog]:
        """Fetch semantic catalog from DCL's semantic-export endpoint."""
        if not self._http_client:
            self._http_client = httpx.Client(timeout=10.0, follow_redirects=True)

        try:
            response = self._http_client.get(f"{self.dcl_url}/api/dcl/semantic-export")
            response.raise_for_status()
            data = response.json()
            return self._parse_dcl_response(data)
        except (httpx.RequestError, httpx.HTTPStatusError, json.JSONDecodeError, KeyError) as e:
            logger.warning(f"DCL fetch failed: {e}")
            return None

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

        # Log mode information from DCL
        mode_info = data.get("mode", {})
        if mode_info:
            data_mode = mode_info.get("data_mode", "unknown")
            run_mode = mode_info.get("run_mode", "unknown")
            last_updated = mode_info.get("last_updated", "")
            logger.info(f"DCL mode: {data_mode}/{run_mode} (updated: {last_updated})")

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
            "win_rate": ["close rate", "conversion rate"],
            "quota_attainment": ["quota", "attainment"],
            "gross_churn_pct": ["churn", "churn rate", "customer churn"],

            # Operations/HR (with common misspellings)
            "headcount": ["employees", "staff", "team size", "hc", "people", "fte",
                          "employess", "employes", "emplyees",  # misspellings
                          "personnel", "personnel hires", "hires", "workforce",  # additional aliases
                          "hiring", "hiring trend"],  # map hiring to headcount trend
            "attrition_rate": ["attrition", "attrition rate", "turnover rate", "employee turnover", "turnover",
                               "attriton", "attrtion", "attriton rate"],  # misspellings
            "engagement_score": ["engagement", "engagment", "engagmnet"],  # misspellings
            "cac": ["customer acquisition cost", "acquisition cost"],
            "ltv_cac": ["ltv/cac", "lifetime value to cac"],
            "magic_number": ["sales efficiency", "efficiency", "efficient"],  # yes/no query support

            # Tech
            "uptime_pct": ["uptime", "availability"],
            "p1_incidents": ["incidents", "p1s", "outages"],
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
            "pipeline": "CRO", "arr": "CRO", "nrr": "CRO", "win_rate": "CRO",
            "quota_attainment": "CRO", "gross_churn_pct": "CRO", "bookings": "CRO",
            "sales_cycle_days": "CRO", "avg_deal_size": "CRO",

            # COO
            "headcount": "COO", "cac": "COO", "ltv_cac": "COO", "magic_number": "COO",
            "revenue_per_employee": "COO", "cac_payback_months": "COO",

            # CTO
            "uptime_pct": "CTO", "p1_incidents": "CTO", "deploys_per_week": "CTO",
            "sprint_velocity": "CTO", "code_coverage_pct": "CTO", "tech_debt_pct": "CTO",

            # CHRO
            "attrition_rate": "CHRO", "engagement_score": "CHRO",
            "time_to_fill_days": "CHRO", "offer_acceptance_rate": "CHRO",
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
            "gross_margin_pct": "%", "net_income_pct": "%", "gross_churn_pct": "%",
            "nrr": "%", "win_rate": "%", "quota_attainment": "%", "uptime_pct": "%",
            "code_coverage_pct": "%", "attrition_rate": "%",

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

    def resolve_metric(self, user_term: str) -> Optional[MetricDefinition]:
        """
        Find metric by name or alias.

        Uses DCL's resolution endpoint when available, falls back to local matching.

        Args:
            user_term: What the user said (e.g., "AR", "accounts receivable", "revenue")

        Returns:
            MetricDefinition if found, None otherwise
        """
        if not user_term:
            return None

        # Try DCL resolution endpoint first (if configured)
        if self.dcl_url:
            try:
                result = self._resolve_metric_via_dcl(user_term)
                if result:
                    return result
            except (httpx.RequestError, httpx.HTTPStatusError, json.JSONDecodeError, KeyError) as e:
                logger.debug(f"DCL metric resolution failed for '{user_term}': {e}")

        # Fall back to local catalog resolution
        return self._resolve_metric_locally(user_term)

    def _resolve_metric_via_dcl(self, user_term: str) -> Optional[MetricDefinition]:
        """Call DCL's metric resolution endpoint."""
        if not self._http_client:
            self._http_client = httpx.Client(timeout=5.0, follow_redirects=True)

        try:
            response = self._http_client.get(
                f"{self.dcl_url}/api/dcl/semantic-export/resolve/metric",
                params={"q": user_term}
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()

            data = response.json()
            metric_id = data["id"]
            local_units = self._get_metric_units()
            # DCL uses 'name' for display, 'pack' for domain
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
            return None
        except (httpx.RequestError, json.JSONDecodeError, KeyError) as e:
            logger.warning(f"DCL metric resolution failed: {e}")
            return None

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

        if not self._http_client:
            self._http_client = httpx.Client(timeout=5.0, follow_redirects=True)

        try:
            response = self._http_client.get(
                f"{self.dcl_url}/api/dcl/semantic-export/resolve/entity",
                params={"q": user_term}
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
        if force_local or _force_local_ctx.get() or not self.dcl_url:
            return self._query_local_fallback(metric, dimensions, filters, time_range, grain, order_by, limit)

        if not self._http_client:
            self._http_client = httpx.Client(timeout=30.0)

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

            payload = {
                "metric": metric,
                "dimensions": dimensions or [],
                "filters": filters or {},
                "time_range": dcl_time_range,
                "grain": dcl_grain,
            }
            if order_by:
                payload["order_by"] = order_by
            if limit:
                payload["limit"] = limit

            response = self._http_client.post(
                f"{self.dcl_url}/api/dcl/query",
                json=payload
            )

            if response.status_code == 404:
                return {"error": f"Unknown metric: {metric}", "status": "not_found"}
            elif response.status_code == 400:
                err_body = response.json()
                error_msg = err_body.get("message", err_body.get("detail", "Invalid query"))
                return {"error": error_msg, "status": "bad_request"}

            response.raise_for_status()
            return self._normalize_dcl_query_response(response.json())

        except httpx.HTTPStatusError as e:
            logger.error(f"DCL query failed: {e}")
            return {"error": f"DCL query failed: {e}", "status": "error"}
        except (httpx.RequestError, json.JSONDecodeError) as e:
            logger.error(f"DCL query error: {e}")
            return {"error": f"DCL unavailable: {e}", "status": "error"}

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
        normalized: Dict[str, Any] = {
            "status": "ok",
            "source": "dcl",
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
        provenance = dcl_response.get("provenance", [])
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
        normalized["run_provenance"] = {
            "run_id": metadata.get("run_id"),
            "tenant_id": metadata.get("tenant_id"),
            "snapshot_name": metadata.get("snapshot_name"),
            "run_timestamp": metadata.get("run_timestamp"),
            "source_systems": source_systems,
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
            metric: Metric to rank by (e.g., "quota_attainment", "win_rate", "revenue")
            dimension: Dimension to rank (e.g., "rep", "region", "service")
            order_by: "desc" for highest first, "asc" for lowest first
            limit: Number of results to return
            time_range: Optional time range filter

        Returns:
            Query result with ranked data
        """
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
        period = "2026-Q4"  # Default to current period
        if time_range:
            period = time_range.get("period", period)

        # Map metric + dimension to data source
        data_source_map = {
            ("quota_attainment", "rep"): "quota_by_rep",
            ("win_rate", "rep"): "win_rate_by_rep",
            ("pipeline", "rep"): "pipeline_by_rep",
            ("slo_attainment", "service"): "slo_attainment_by_service",
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
                deals = raw_data.get(period, raw_data.get("2026", []))
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
                for key in ("value", "attainment_pct", "pipeline", "slo_attainment", "revenue", "headcount"):
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
                for key in ("value", "attainment_pct", "pipeline", "revenue", "slo_attainment", "headcount"):
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

        # Handle dimensional queries
        period_filter = time_range.get("period") if time_range else None
        default_period = "2026-Q4"  # Current period

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
