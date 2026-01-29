"""
Seed Data for RAG Cache

Common queries with pre-parsed structures for bootstrapping the cache.
These queries are designed to cover the most frequent user questions
across all personas.

Usage:
    python -m scripts.seed_data  # Dry run - print queries
    python -m scripts.seed_data --execute  # Actually seed the cache
"""

# =============================================================================
# CFO PERSONA SEED QUERIES
# =============================================================================

CFO_QUERIES = [
    # Revenue queries
    {
        "query": "what is our revenue",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "revenue",
            "period_type": "FULL_YEAR",
            "period_reference": "CURRENT",
            "period_year": 2025,
        },
        "persona": "CFO",
        "confidence": 0.98,
    },
    {
        "query": "what was revenue last year",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "revenue",
            "period_type": "FULL_YEAR",
            "period_reference": "PRIOR",
            "period_year": 2024,
        },
        "persona": "CFO",
        "confidence": 0.97,
    },
    {
        "query": "revenue ytd",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "revenue",
            "period_type": "YTD",
            "period_reference": "CURRENT",
        },
        "persona": "CFO",
        "confidence": 0.96,
    },
    {
        "query": "q4 revenue",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "revenue",
            "period_type": "QUARTER",
            "period_reference": "Q4",
            "period_year": 2025,
        },
        "persona": "CFO",
        "confidence": 0.95,
    },
    # Margin queries
    {
        "query": "what is our margin",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "gross_margin",
            "period_type": "FULL_YEAR",
            "period_reference": "CURRENT",
        },
        "persona": "CFO",
        "confidence": 0.95,
    },
    {
        "query": "gross margin",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "gross_margin",
            "period_type": "FULL_YEAR",
            "period_reference": "CURRENT",
        },
        "persona": "CFO",
        "confidence": 0.97,
    },
    {
        "query": "whats the margin",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "gross_margin",
            "period_type": "FULL_YEAR",
            "period_reference": "CURRENT",
        },
        "persona": "CFO",
        "confidence": 0.94,
    },
    # Burn rate and runway
    {
        "query": "burn rate",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "burn_rate",
            "period_type": "MONTHLY",
            "period_reference": "CURRENT",
        },
        "persona": "CFO",
        "confidence": 0.98,
    },
    {
        "query": "what is our runway",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "runway",
            "period_type": "CURRENT",
            "period_reference": "CURRENT",
        },
        "persona": "CFO",
        "confidence": 0.97,
    },
    {
        "query": "cash runway",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "runway",
            "period_type": "CURRENT",
            "period_reference": "CURRENT",
        },
        "persona": "CFO",
        "confidence": 0.96,
    },
    # Profitability
    {
        "query": "are we profitable",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "net_income",
            "period_type": "FULL_YEAR",
            "period_reference": "CURRENT",
        },
        "persona": "CFO",
        "confidence": 0.90,
    },
    {
        "query": "ebitda",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "ebitda",
            "period_type": "FULL_YEAR",
            "period_reference": "CURRENT",
        },
        "persona": "CFO",
        "confidence": 0.98,
    },
    # Comparison queries
    {
        "query": "revenue vs last year",
        "parsed": {
            "intent": "COMPARISON_QUERY",
            "metric": "revenue",
            "period_type": "FULL_YEAR",
            "period_reference": "CURRENT",
            "comparison_type": "YOY",
            "comparison_period": "PRIOR_YEAR",
        },
        "persona": "CFO",
        "confidence": 0.93,
    },
    {
        "query": "how is revenue trending",
        "parsed": {
            "intent": "TREND_QUERY",
            "metric": "revenue",
            "period_type": "L12M",
            "period_reference": "CURRENT",
        },
        "persona": "CFO",
        "confidence": 0.88,
    },
]

# =============================================================================
# CRO PERSONA SEED QUERIES
# =============================================================================

CRO_QUERIES = [
    # Pipeline
    {
        "query": "pipeline",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "pipeline_value",
            "period_type": "CURRENT",
            "period_reference": "CURRENT",
        },
        "persona": "CRO",
        "confidence": 0.95,
    },
    {
        "query": "how's pipeline looking",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "pipeline_value",
            "period_type": "CURRENT",
            "period_reference": "CURRENT",
        },
        "persona": "CRO",
        "confidence": 0.90,
    },
    {
        "query": "pipeline coverage",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "pipeline_coverage",
            "period_type": "CURRENT",
            "period_reference": "CURRENT",
        },
        "persona": "CRO",
        "confidence": 0.96,
    },
    # Win rate and deals
    {
        "query": "win rate",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "win_rate",
            "period_type": "FULL_YEAR",
            "period_reference": "CURRENT",
        },
        "persona": "CRO",
        "confidence": 0.97,
    },
    {
        "query": "deals closed this quarter",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "deals_closed",
            "period_type": "QUARTER",
            "period_reference": "CURRENT",
        },
        "persona": "CRO",
        "confidence": 0.92,
    },
    # Churn
    {
        "query": "churn",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "churn_rate",
            "period_type": "FULL_YEAR",
            "period_reference": "CURRENT",
        },
        "persona": "CRO",
        "confidence": 0.95,
    },
    {
        "query": "churn?",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "churn_rate",
            "period_type": "FULL_YEAR",
            "period_reference": "CURRENT",
        },
        "persona": "CRO",
        "confidence": 0.94,
    },
    {
        "query": "customer churn rate",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "churn_rate",
            "period_type": "FULL_YEAR",
            "period_reference": "CURRENT",
        },
        "persona": "CRO",
        "confidence": 0.97,
    },
    # ARR and NRR
    {
        "query": "arr",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "arr",
            "period_type": "CURRENT",
            "period_reference": "CURRENT",
        },
        "persona": "CRO",
        "confidence": 0.98,
    },
    {
        "query": "nrr",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "nrr",
            "period_type": "FULL_YEAR",
            "period_reference": "CURRENT",
        },
        "persona": "CRO",
        "confidence": 0.97,
    },
    {
        "query": "net revenue retention",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "nrr",
            "period_type": "FULL_YEAR",
            "period_reference": "CURRENT",
        },
        "persona": "CRO",
        "confidence": 0.98,
    },
]

# =============================================================================
# COO PERSONA SEED QUERIES
# =============================================================================

COO_QUERIES = [
    # Efficiency
    {
        "query": "are we efficient",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "operating_efficiency",
            "period_type": "FULL_YEAR",
            "period_reference": "CURRENT",
        },
        "persona": "COO",
        "confidence": 0.85,
    },
    {
        "query": "magic number",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "magic_number",
            "period_type": "FULL_YEAR",
            "period_reference": "CURRENT",
        },
        "persona": "COO",
        "confidence": 0.95,
    },
    {
        "query": "cac payback",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "cac_payback_months",
            "period_type": "FULL_YEAR",
            "period_reference": "CURRENT",
        },
        "persona": "COO",
        "confidence": 0.96,
    },
    # LTV and CAC
    {
        "query": "ltv to cac",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "ltv_cac_ratio",
            "period_type": "FULL_YEAR",
            "period_reference": "CURRENT",
        },
        "persona": "COO",
        "confidence": 0.95,
    },
    {
        "query": "customer acquisition cost",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "cac",
            "period_type": "FULL_YEAR",
            "period_reference": "CURRENT",
        },
        "persona": "COO",
        "confidence": 0.97,
    },
    # Headcount
    {
        "query": "headcount",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "headcount",
            "period_type": "CURRENT",
            "period_reference": "CURRENT",
        },
        "persona": "COO",
        "confidence": 0.98,
    },
    {
        "query": "revenue per employee",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "revenue_per_employee",
            "period_type": "FULL_YEAR",
            "period_reference": "CURRENT",
        },
        "persona": "COO",
        "confidence": 0.95,
    },
]

# =============================================================================
# CTO PERSONA SEED QUERIES
# =============================================================================

CTO_QUERIES = [
    # Platform stability
    {
        "query": "platform stable?",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "uptime",
            "period_type": "MONTHLY",
            "period_reference": "CURRENT",
        },
        "persona": "CTO",
        "confidence": 0.88,
    },
    {
        "query": "uptime",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "uptime",
            "period_type": "MONTHLY",
            "period_reference": "CURRENT",
        },
        "persona": "CTO",
        "confidence": 0.98,
    },
    {
        "query": "system availability",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "uptime",
            "period_type": "MONTHLY",
            "period_reference": "CURRENT",
        },
        "persona": "CTO",
        "confidence": 0.92,
    },
    # Engineering velocity
    {
        "query": "how's velocity",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "sprint_velocity",
            "period_type": "SPRINT",
            "period_reference": "CURRENT",
        },
        "persona": "CTO",
        "confidence": 0.88,
    },
    {
        "query": "sprint velocity",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "sprint_velocity",
            "period_type": "SPRINT",
            "period_reference": "CURRENT",
        },
        "persona": "CTO",
        "confidence": 0.97,
    },
    {
        "query": "deployment frequency",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "deployment_frequency",
            "period_type": "WEEKLY",
            "period_reference": "CURRENT",
        },
        "persona": "CTO",
        "confidence": 0.95,
    },
    # Incidents
    {
        "query": "incidents last month",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "incident_count",
            "period_type": "MONTHLY",
            "period_reference": "PRIOR",
        },
        "persona": "CTO",
        "confidence": 0.93,
    },
    {
        "query": "mttr",
        "parsed": {
            "intent": "POINT_QUERY",
            "metric": "mttr",
            "period_type": "MONTHLY",
            "period_reference": "CURRENT",
        },
        "persona": "CTO",
        "confidence": 0.97,
    },
]

# =============================================================================
# DASHBOARD QUERIES
# =============================================================================

DASHBOARD_QUERIES = [
    {
        "query": "2025 results",
        "parsed": {
            "intent": "DASHBOARD",
            "metric": None,
            "period_type": "FULL_YEAR",
            "period_reference": "CURRENT",
            "period_year": 2025,
        },
        "persona": "CFO",
        "confidence": 0.92,
    },
    {
        "query": "2025 kpis",
        "parsed": {
            "intent": "DASHBOARD",
            "metric": None,
            "period_type": "FULL_YEAR",
            "period_reference": "CURRENT",
            "period_year": 2025,
        },
        "persona": "CFO",
        "confidence": 0.93,
    },
    {
        "query": "year to date performance",
        "parsed": {
            "intent": "DASHBOARD",
            "metric": None,
            "period_type": "YTD",
            "period_reference": "CURRENT",
        },
        "persona": "CFO",
        "confidence": 0.90,
    },
]

# =============================================================================
# COMBINED SEED DATA
# =============================================================================

SEED_QUERIES = (
    CFO_QUERIES +
    CRO_QUERIES +
    COO_QUERIES +
    CTO_QUERIES +
    DASHBOARD_QUERIES
)


def print_seed_summary():
    """Print a summary of seed data."""
    print("\nRAG Cache Seed Data Summary")
    print("=" * 50)
    print(f"CFO queries:       {len(CFO_QUERIES)}")
    print(f"CRO queries:       {len(CRO_QUERIES)}")
    print(f"COO queries:       {len(COO_QUERIES)}")
    print(f"CTO queries:       {len(CTO_QUERIES)}")
    print(f"Dashboard queries: {len(DASHBOARD_QUERIES)}")
    print("-" * 50)
    print(f"Total queries:     {len(SEED_QUERIES)}")
    print()

    # Sample queries
    print("Sample queries:")
    for persona in ["CFO", "CRO", "COO", "CTO"]:
        queries = [q for q in SEED_QUERIES if q.get("persona") == persona]
        if queries:
            sample = queries[0]
            print(f"  [{persona}] \"{sample['query']}\" -> {sample['parsed'].get('metric')}")


if __name__ == "__main__":
    import sys

    if "--execute" in sys.argv:
        print("Executing seed...")
        try:
            import os
            from src.nlq.services.query_cache_service import QueryCacheService, CacheConfig

            config = CacheConfig(
                pinecone_api_key=os.getenv("PINECONE_API_KEY", ""),
                pinecone_index=os.getenv("PINECONE_INDEX", "aos-nlq"),
                openai_api_key=os.getenv("OPENAI_API_KEY", ""),
            )

            cache = QueryCacheService(config)
            if not cache.is_available:
                print("ERROR: Cache service not available. Check API keys.")
                sys.exit(1)

            count = cache.bulk_store(SEED_QUERIES)
            print(f"Successfully seeded {count} queries to cache")
        except Exception as e:
            print(f"ERROR: {e}")
            sys.exit(1)
    else:
        print_seed_summary()
        print("\nTo execute seed, run: python -m scripts.seed_data --execute")
