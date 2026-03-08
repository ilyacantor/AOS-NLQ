"""
Response models for AOS-NLQ.

Contains Pydantic models for:
- API response structure (NLQResponse)
- Internal query execution results (QueryResult)
- Galaxy visualization models (IntentNode, IntentMapResponse)

CRITICAL: Confidence scores are bounded [0.0, 1.0] using Pydantic Field constraints.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, field_validator

if TYPE_CHECKING:
    from src.nlq.models.dashboard_schema import DashboardSchema


class MatchType(str, Enum):
    """Orbital ring assignment for Galaxy visualization."""
    EXACT = "exact"           # Inner ring - direct answer
    POTENTIAL = "potential"   # Middle ring - likely interpretation
    HYPOTHESIS = "hypothesis" # Outer ring - contextual


class Domain(str, Enum):
    """Domain colors for Galaxy visualization."""
    FINANCE = "finance"       # Blue
    GROWTH = "growth"         # Pink
    OPS = "ops"               # Green
    PRODUCT = "product"       # Purple
    PEOPLE = "people"         # Orange


class AmbiguityType(str, Enum):
    """Types of query ambiguity."""
    NONE = "none"
    INCOMPLETE = "incomplete"
    VAGUE_METRIC = "vague_metric"
    CASUAL_LANGUAGE = "casual"
    YES_NO = "yes_no"
    BROAD_REQUEST = "broad"
    IMPLIED_CONTEXT = "implied"
    JUDGMENT_CALL = "judgment"
    SHORTHAND = "shorthand"
    CONTEXT_DEPENDENT = "context"
    COMPARISON = "comparison"
    SUMMARY = "summary"
    NOT_APPLICABLE = "not_applicable"
    BURN_RATE = "burn_rate"


class IntentNode(BaseModel):
    """Single node on the Galaxy visualization."""

    # Identity
    id: str = Field(..., description="Unique node identifier")
    metric: str = Field(..., description="Canonical metric name")
    display_name: str = Field(..., description="Human-readable label")

    # Visual positioning
    match_type: MatchType = Field(..., description="Orbital ring assignment")
    domain: Domain = Field(..., description="Circle color based on domain")

    # Visual sizing & indicators
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Circle size (larger = higher confidence)"
    )
    data_quality: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Arc completion percentage"
    )
    freshness: str = Field(
        ...,
        description="Data age indicator (e.g., '2h', '24h', '48h')"
    )

    # Data
    value: Optional[Any] = Field(default=None, description="Raw value")
    formatted_value: Optional[str] = Field(
        default=None,
        description="Formatted value (e.g., '$150.0M', '65.0%')"
    )
    period: Optional[str] = Field(
        default=None,
        description="Time period (e.g., '2025', 'Q4 2025')"
    )

    # Metadata
    rationale: Optional[str] = Field(
        default=None,
        description="Why this node is included"
    )
    semantic_label: Optional[str] = Field(
        default=None,
        description="Semantic classification (e.g., 'Exact Match', 'Likely')"
    )

    # Provenance (DCL integration)
    source_system: Optional[str] = Field(
        default=None,
        description="Source system name (e.g., 'Salesforce CRM', 'SAP ERP')"
    )

    # Conflict indicator (DCL integration)
    has_conflict: Optional[bool] = Field(
        default=None,
        description="Whether this metric has conflicting values across systems"
    )
    conflict_details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Conflict details: systems, values, delta, root cause"
    )


class IntentMapResponse(BaseModel):
    """Full response for Galaxy visualization."""

    # Query info
    query: str = Field(..., description="Original question")
    query_type: str = Field(
        ...,
        description="POINT_QUERY, COMPARISON_QUERY, AMBIGUOUS, etc."
    )
    ambiguity_type: Optional[AmbiguityType] = Field(
        default=None,
        description="Type of ambiguity if query is ambiguous"
    )

    # Persona (displayed at center)
    persona: Optional[str] = Field(
        default=None,
        description="Query persona (e.g., 'CFO', 'CEO')"
    )

    # Overall metrics (displayed in header)
    overall_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Aggregate confidence score"
    )
    overall_data_quality: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Aggregate data quality score"
    )
    node_count: int = Field(..., description="Total number of nodes")

    # All nodes for visualization
    nodes: List[IntentNode] = Field(..., description="Nodes for the Galaxy view")

    # Primary answer
    primary_node_id: Optional[str] = Field(
        default=None,
        description="ID of the primary answer node"
    )
    primary_answer: Optional[str] = Field(
        default=None,
        description="Main answer text"
    )

    # Text response
    text_response: str = Field(..., description="Full text response")

    # Disambiguation
    needs_clarification: bool = Field(
        default=False,
        description="Whether clarification is needed"
    )
    clarification_prompt: Optional[str] = Field(
        default=None,
        description="Question to ask for clarification"
    )

    # Dashboard response (for visualization queries in galaxy mode)
    dashboard: Optional[Any] = Field(
        default=None,
        description="Dashboard schema when visualization is requested"
    )
    dashboard_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Pre-resolved widget data for the dashboard"
    )
    response_type: Optional[str] = Field(
        default="galaxy",
        description="Response type: 'galaxy' for nodes, 'dashboard' for visualization"
    )

    # Debug info for development (tracks all decisions made during processing)
    debug_info: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Debug information showing all decisions made during dashboard generation (only in strict mode)"
    )

    # Entity resolution fields (DCL integration)
    entity: Optional[str] = Field(
        default=None,
        description="Resolved entity name"
    )
    entity_id: Optional[str] = Field(
        default=None,
        description="DCL global entity ID"
    )
    entity_resolution: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Entity resolution details"
    )

    # Data source transparency (H4/H5: never silent about where data comes from)
    data_source: Optional[str] = Field(
        default=None,
        description="Where data was sourced: 'dcl', 'local', or 'local_fallback'"
    )

    # Provenance (DCL integration)
    provenance: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Data provenance for the primary metric"
    )

    # Conflicts (DCL integration)
    conflicts: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Data conflicts for this query"
    )

    # Temporal warnings (DCL integration)
    temporal_warning: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Warning if comparison crosses definition change"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "What was revenue in 2025?",
                "query_type": "POINT_QUERY",
                "ambiguity_type": None,
                "persona": "CFO",
                "overall_confidence": 0.95,
                "overall_data_quality": 0.95,
                "node_count": 4,
                "nodes": [
                    {
                        "id": "revenue-primary",
                        "metric": "revenue",
                        "display_name": "Revenue",
                        "match_type": "exact",
                        "domain": "finance",
                        "confidence": 0.95,
                        "data_quality": 0.95,
                        "freshness": "24h",
                        "value": 150.0,
                        "formatted_value": "$150.0M",
                        "period": "2025",
                        "rationale": "Direct answer",
                        "semantic_label": "Exact Match"
                    }
                ],
                "primary_node_id": "revenue-primary",
                "primary_answer": "Revenue for 2025 was $150.0 million",
                "text_response": "Revenue for 2025 was $150.0 million",
                "needs_clarification": False,
                "clarification_prompt": None
            }
        }
    )


class QueryResult(BaseModel):
    """Internal model for query execution results."""

    success: bool = Field(
        ...,
        description="Whether the query executed successfully"
    )

    value: Optional[Any] = Field(
        default=None,
        description="Raw query result value"
    )

    error: Optional[str] = Field(
        default=None,
        description="Error code if query failed"
    )

    message: Optional[str] = Field(
        default=None,
        description="Human-readable message"
    )

    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score, always bounded [0.0, 1.0]"
    )

    query_type: Optional[str] = Field(
        default=None,
        description="Query execution type (e.g., 'trend', 'graph_resolution')"
    )

    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional execution metadata (provenance, warnings, etc.)"
    )

    data_source: Optional[str] = Field(
        default=None,
        description="Data source: 'live' (ingested), 'demo' (fact_base), or 'dcl'"
    )


class RelatedMetric(BaseModel):
    """A related metric for Text View (equivalent to Galaxy View node)."""

    metric: str = Field(..., description="Canonical metric name")
    display_name: str = Field(..., description="Human-readable label")
    value: Optional[float] = Field(default=None, description="Metric value")
    formatted_value: str = Field(..., description="Formatted display value")
    period: str = Field(..., description="Time period")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    match_type: str = Field(..., description="exact, potential, or hypothesis")
    rationale: Optional[str] = Field(default=None, description="Why this metric is related")
    domain: Optional[str] = Field(default=None, description="Domain: finance, growth, ops, product, people")


class BridgeChartBar(BaseModel):
    """Single bar in a waterfall/bridge chart."""
    label: str = Field(..., description="Bar label (e.g., 'FY 2024 Revenue')")
    value: Optional[float] = Field(default=None, description="Bar value (signed delta for drivers)")
    type: str = Field(..., description="'total', 'increase', or 'decrease'")
    running_total: Optional[float] = Field(default=None, description="Cumulative total at this point")


class BridgeChartData(BaseModel):
    """Structured bridge/waterfall chart data for rendering."""
    bridge_type: str = Field(default="revenue", description="Type of bridge")
    title: str = Field(..., description="Chart title")
    subtitle: str = Field(default="All amounts in $M", description="Chart subtitle")
    period_start: str = Field(..., description="Start period label")
    period_end: str = Field(..., description="End period label")
    start_value: Optional[float] = Field(default=None, description="Start total value")
    end_value: Optional[float] = Field(default=None, description="End total value")
    unit: str = "usd_millions"
    format: str = "currency"
    bars: List[BridgeChartBar] = Field(default_factory=list)
    data_source: Optional[str] = None
    downloadable: bool = True


class FinancialStatementLineItem(BaseModel):
    """Single line item in a financial statement."""
    label: str = Field(..., description="Display label (e.g., 'Revenue', 'Cost of Goods Sold')")
    key: str = Field(..., description="Canonical metric key (e.g., 'revenue', 'cogs')")
    indent: int = Field(default=0, description="Indentation level: 0=top-level, 1=sub-item")
    format: str = Field(default="currency", description="Display format: 'currency' or 'percent'")
    is_subtotal: bool = Field(default=False, description="True for subtotal rows (bold, border)")
    values: Dict[str, Optional[float]] = Field(default_factory=dict, description="Period -> value mapping")


class FinancialStatementData(BaseModel):
    """Structured financial statement for rendering."""
    title: str = Field(default="Income Statement", description="Statement title")
    entity: str = Field(default="Meridian Partners", description="Entity name")
    periods: List[str] = Field(default_factory=list, description="Column headers in display order")
    line_items: List[FinancialStatementLineItem] = Field(default_factory=list)
    currency: str = "USD"
    unit: str = "millions"


class NLQResponse(BaseModel):
    """Output model for natural language query responses."""

    success: bool = Field(
        ...,
        description="Whether the query was successful"
    )

    answer: Optional[str] = Field(
        default=None,
        description="Human-readable answer"
    )

    value: Optional[Any] = Field(
        default=None,
        description="Raw numeric value"
    )

    unit: Optional[str] = Field(
        default=None,
        description="Unit of measurement in DCL canonical form (pct, usd_millions, count, ratio, etc.)"
    )

    # Normalize display units → DCL canonical units at the model boundary
    @field_validator("unit", mode="before")
    @classmethod
    def _normalize_unit(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        _CANONICAL = {
            "%": "pct", "percent": "pct", "percentage": "pct",
            "USD millions": "usd_millions", "$M": "usd_millions", "usd millions": "usd_millions",
            "USD": "usd", "$": "usd",
            "millions/month": "usd_millions",
            "people": "count", "customers": "count", "tickets": "count",
            "bugs": "count", "vulnerabilities": "count", "incidents": "count",
            "deploys": "count", "features": "count", "points": "count",
            "x": "ratio",
        }
        return _CANONICAL.get(v, v)

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score, ALWAYS bounded [0.0, 1.0]"
    )

    # Debugging/transparency fields
    parsed_intent: Optional[str] = Field(
        default=None,
        description="Detected query intent"
    )

    resolved_metric: Optional[str] = Field(
        default=None,
        description="Canonical metric name after normalization"
    )

    resolved_period: Optional[str] = Field(
        default=None,
        description="Absolute period after resolution"
    )

    # Related metrics (same as Galaxy View nodes, but for Text View)
    related_metrics: Optional[List["RelatedMetric"]] = Field(
        default=None,
        description="Related metrics with values and context (equivalent to Galaxy View nodes)"
    )

    # Error handling
    error_code: Optional[str] = Field(
        default=None,
        description="Error code for failed queries"
    )

    error_message: Optional[str] = Field(
        default=None,
        description="Human-readable error message"
    )

    # Disambiguation
    needs_clarification: bool = Field(
        default=False,
        description="Whether clarification is needed from the user"
    )
    clarification_prompt: Optional[str] = Field(
        default=None,
        description="Question to ask the user for clarification"
    )

    # Financial statement response
    financial_statement_data: Optional[FinancialStatementData] = Field(
        default=None,
        description="Structured financial statement data for rendering"
    )

    # Bridge/waterfall chart response
    bridge_chart_data: Optional[BridgeChartData] = Field(
        default=None,
        description="Structured bridge/waterfall chart data for rendering"
    )

    # Dashboard response (for visualization queries)
    dashboard: Optional[Any] = Field(
        default=None,
        description="Dashboard schema when visualization is requested"
    )

    dashboard_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Pre-resolved widget data for the dashboard"
    )

    response_type: Optional[str] = Field(
        default="text",
        description="Response type: 'text' for simple answer, 'dashboard' for visualization, 'clarification' for disambiguation"
    )

    active_filters: Optional[Dict[str, str]] = Field(
        default=None,
        description="Active cross-widget filters (dimension -> value)"
    )

    # Error details for debugging
    error_details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Detailed error information for debugging"
    )

    # Debug info for development (tracks all decisions made during processing)
    debug_info: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Debug information showing all decisions made during dashboard generation (only in strict mode)"
    )

    # Entity resolution fields (DCL integration)
    entity: Optional[str] = Field(
        default=None,
        description="Resolved entity name (e.g., 'Acme Corp')"
    )
    entity_id: Optional[str] = Field(
        default=None,
        description="DCL global entity ID"
    )
    entity_resolution: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Entity resolution details: matched systems, confidence, candidates"
    )

    # Provenance fields (DCL integration)
    provenance: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Data provenance: source system, table, field, freshness, trust score"
    )

    # Conflict fields (DCL integration)
    conflicts: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Data conflicts between systems for this metric/entity"
    )

    # Temporal warning fields (DCL integration)
    temporal_warning: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Warning when comparison crosses a definition change boundary"
    )

    # Data source transparency (H4/H5: never silent about where data comes from)
    data_source: Optional[str] = Field(
        default=None,
        description="Where data was sourced: 'dcl', 'local', or 'local_fallback'"
    )

    # Persona context
    persona: Optional[str] = Field(
        default=None,
        description="Detected persona (CFO, CRO, COO, etc.)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "answer": "Revenue for 2025 was $125.5 million",
                "value": 125.5,
                "unit": "USD millions",
                "confidence": 0.95,
                "parsed_intent": "POINT_QUERY",
                "resolved_metric": "revenue",
                "resolved_period": "2025",
                "related_metrics": [
                    {
                        "metric": "net_income",
                        "display_name": "Net Income",
                        "value": 28.13,
                        "formatted_value": "$28.13M",
                        "period": "2025",
                        "confidence": 0.85,
                        "match_type": "potential",
                        "rationale": "Related profitability metric"
                    }
                ],
                "error_code": None,
                "error_message": None
            }
        }
    )
