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

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

logger = logging.getLogger(__name__)

# Cache TTL in seconds (5 minutes)
CACHE_TTL_SECONDS = 300


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
        """Build reverse lookup from aliases to metric IDs."""
        self.alias_to_metric = {}
        for metric_id, metric in self.metrics.items():
            # Add canonical ID
            self.alias_to_metric[metric_id.lower()] = metric_id
            # Add all aliases
            for alias in metric.aliases:
                self.alias_to_metric[alias.lower()] = metric_id


class DCLSemanticClient:
    """
    Client for fetching and querying DCL's semantic catalog.

    Provides metric resolution and dimension validation with caching.
    Falls back to local catalog if DCL is unavailable.
    """

    def __init__(self, dcl_base_url: Optional[str] = None):
        self.dcl_url = dcl_base_url or os.environ.get("DCL_API_URL", "")
        self._catalog: Optional[SemanticCatalog] = None
        self._cache_time: float = 0
        self._http_client: Optional[httpx.Client] = None

    @property
    def catalog(self) -> SemanticCatalog:
        """Get the semantic catalog, fetching/refreshing if needed."""
        return self.get_catalog()

    def get_catalog(self, force_refresh: bool = False) -> SemanticCatalog:
        """
        Fetch semantic catalog from DCL, with caching.

        Args:
            force_refresh: If True, bypass cache and fetch fresh

        Returns:
            SemanticCatalog with all metric definitions
        """
        current_time = time.time()

        # Return cached if valid
        if (not force_refresh
            and self._catalog is not None
            and current_time - self._cache_time < CACHE_TTL_SECONDS):
            return self._catalog

        # Try to fetch from DCL
        if self.dcl_url:
            try:
                catalog = self._fetch_from_dcl()
                if catalog:
                    self._catalog = catalog
                    self._cache_time = current_time
                    logger.info("Loaded semantic catalog from DCL")
                    return catalog
            except Exception as e:
                logger.warning(f"Failed to fetch from DCL: {e}, using local catalog")

        # Fall back to local catalog
        catalog = self._build_local_catalog()
        self._catalog = catalog
        self._cache_time = current_time
        logger.info("Built semantic catalog from local fact_base")
        return catalog

    def _fetch_from_dcl(self) -> Optional[SemanticCatalog]:
        """Fetch semantic catalog from DCL's semantic-export endpoint."""
        if not self._http_client:
            self._http_client = httpx.Client(timeout=10.0)

        try:
            response = self._http_client.get(f"{self.dcl_url}/api/dcl/semantic-export")
            response.raise_for_status()
            data = response.json()
            return self._parse_dcl_response(data)
        except Exception as e:
            logger.warning(f"DCL fetch failed: {e}")
            return None

    def _parse_dcl_response(self, data: Dict[str, Any]) -> SemanticCatalog:
        """Parse DCL's semantic-export response into our catalog format."""
        catalog = SemanticCatalog()

        # Parse metrics
        for metric_data in data.get("metrics", []):
            metric = MetricDefinition(
                id=metric_data["id"],
                display_name=metric_data.get("display_name", metric_data["id"]),
                aliases=metric_data.get("aliases", []),
                unit=metric_data.get("unit", ""),
                allowed_dimensions=metric_data.get("allowed_dims", []),
                allowed_grains=metric_data.get("allowed_grains", ["quarterly"]),
                domain=metric_data.get("domain", ""),
            )
            catalog.metrics[metric.id] = metric

        # Parse dimensions
        catalog.dimensions = data.get("dimensions", {})

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
        except Exception as e:
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
        """Get common aliases for metrics."""
        return {
            # Financial
            "revenue": ["sales", "top line", "topline", "turnover", "total revenue"],
            "ar": ["accounts receivable", "receivables", "a/r"],
            "ap": ["accounts payable", "payables", "a/p"],
            "ebitda": ["earnings before interest taxes depreciation amortization"],
            "gross_margin_pct": ["gross margin", "gm", "margin"],
            "net_income": ["profit", "net profit", "bottom line"],
            "operating_profit": ["ebit", "operating income"],
            "cogs": ["cost of goods sold", "cost of sales", "cos"],

            # Sales
            "pipeline": ["sales pipeline", "pipe", "opportunities", "deals"],
            "arr": ["annual recurring revenue", "recurring revenue"],
            "nrr": ["net revenue retention", "net retention"],
            "win_rate": ["close rate", "conversion rate"],
            "quota_attainment": ["quota", "attainment"],
            "gross_churn_pct": ["churn", "churn rate", "customer churn"],

            # Operations
            "headcount": ["employees", "staff", "team size", "hc"],
            "cac": ["customer acquisition cost", "acquisition cost"],
            "ltv_cac": ["ltv/cac", "lifetime value to cac"],
            "magic_number": ["sales efficiency", "efficiency"],

            # Tech
            "uptime_pct": ["uptime", "availability"],
            "p1_incidents": ["incidents", "p1s", "outages"],
            "deployment_success_pct": ["deploy success", "deployment success"],
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

        Args:
            user_term: What the user said (e.g., "AR", "accounts receivable", "revenue")

        Returns:
            MetricDefinition if found, None otherwise
        """
        catalog = self.get_catalog()
        normalized = user_term.lower().strip()

        # Try exact match first
        if normalized in catalog.alias_to_metric:
            metric_id = catalog.alias_to_metric[normalized]
            return catalog.metrics.get(metric_id)

        # Try fuzzy match on aliases
        for alias, metric_id in catalog.alias_to_metric.items():
            if normalized in alias or alias in normalized:
                return catalog.metrics.get(metric_id)

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

    def close(self):
        """Close HTTP client."""
        if self._http_client:
            self._http_client.close()
            self._http_client = None


# Singleton instance
_semantic_client: Optional[DCLSemanticClient] = None


def get_semantic_client() -> DCLSemanticClient:
    """Get the singleton DCL semantic client instance."""
    global _semantic_client
    if _semantic_client is None:
        _semantic_client = DCLSemanticClient()
    return _semantic_client
