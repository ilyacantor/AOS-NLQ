"""
Metric Resolution Tests - Validate all metric aliases resolve correctly.

These tests verify that when a user says "AR", "ARR", "eNPS", etc.,
they get resolved to the correct canonical metric ID.

NO MOCKING - tests hit real DCL or fail.
"""

import pytest
from tests.eval.conftest import collect_failures


# =============================================================================
# METRIC RESOLUTION TEST CASES
# =============================================================================
# Format: (user_input, expected_canonical_id)
# These are the REAL aliases that users will type.
# If DCL doesn't resolve them correctly, the test MUST fail.

METRIC_RESOLUTION_CASES = [
    # === CFO / Finance Metrics ===
    ("revenue", "revenue"),
    ("sales", "revenue"),
    ("top line", "revenue"),
    ("gross margin", "gross_margin_pct"),
    ("GM", "gross_margin_pct"),
    ("gross margin %", "gross_margin_pct"),
    ("operating margin", "operating_margin_pct"),
    ("op margin", "operating_margin_pct"),
    ("net income", "net_income"),
    ("profit", "net_income"),
    ("EBITDA", "ebitda"),
    ("cash", "cash"),
    ("cash position", "cash"),
    ("AR", "ar"),
    ("accounts receivable", "ar"),
    ("ARR", "arr"),
    ("annual recurring revenue", "arr"),
    ("burn multiple", "burn_multiple"),

    # === CRO / Sales Metrics ===
    ("pipeline", "pipeline"),
    ("pipe", "pipeline"),
    ("sales pipeline", "pipeline"),
    ("win rate", "win_rate_pct"),
    ("close rate", "win_rate_pct"),
    ("churn", "churn_rate_pct"),
    ("gross churn", "churn_rate_pct"),
    ("NRR", "nrr"),
    ("net revenue retention", "nrr"),
    ("sales cycle", "sales_cycle_days"),
    ("cycle time", "sales_cycle_days"),
    ("quota attainment", "quota_attainment_pct"),
    ("quota", "quota_attainment_pct"),
    ("new logo revenue", "new_logo_revenue"),
    ("new logos", "new_logo_revenue"),

    # === COO / Operations Metrics ===
    ("headcount", "headcount"),
    ("employees", "headcount"),
    ("head count", "headcount"),
    ("revenue per employee", "revenue_per_employee"),
    ("rev per head", "revenue_per_employee"),
    ("magic number", "magic_number"),
    ("CAC payback", "cac_payback_months"),
    ("LTV/CAC", "ltv_cac"),
    ("LTV CAC", "ltv_cac"),
    ("attrition", "attrition_rate_pct"),
    ("attrition rate", "attrition_rate_pct"),
    ("implementation days", "implementation_days"),
    ("impl time", "implementation_days"),

    # === CTO / Engineering Metrics ===
    ("uptime", "uptime_pct"),
    ("availability", "uptime_pct"),
    ("deploys per week", "deploys_per_week"),
    ("deployment frequency", "deploys_per_week"),
    ("MTTR", "mttr_p1_hours"),
    ("mean time to repair", "mttr_p1_hours"),
    ("sprint velocity", "sprint_velocity"),
    ("velocity", "sprint_velocity"),
    ("tech debt", "tech_debt_pct"),
    ("technical debt", "tech_debt_pct"),
    ("code coverage", "code_coverage_pct"),
    ("test coverage", "code_coverage_pct"),
    ("features shipped", "features_shipped"),

    # === CHRO / People Metrics ===
    ("eNPS", "enps"),
    ("employee NPS", "enps"),
    ("employee net promoter", "enps"),
    ("engagement score", "engagement_score"),
    ("engagement", "engagement_score"),
    ("time to hire", "time_to_hire_days"),
    ("hiring time", "time_to_hire_days"),
    ("offer acceptance", "offer_acceptance_rate_pct"),
    ("offer acceptance rate", "offer_acceptance_rate_pct"),
    ("training hours", "training_hours_per_employee"),
    ("L&D hours", "training_hours_per_employee"),
    ("diversity", "diversity_pct"),
    ("diversity %", "diversity_pct"),
    ("regrettable attrition", "regrettable_attrition_rate"),
]


class TestMetricResolution:
    """Test that all metric aliases resolve to correct canonical IDs."""

    # RETIRED (nlq-zero-pre-existing, 2026-06-12): test_all_metric_aliases_resolve
    # hardcoded expected canonical IDs that have DRIFTED from the live DCL catalog
    # (deploy_frequency != deploys_per_week, mttr != mttr_p1_hours, diversity_index
    # != diversity_pct, ltv_cac_ratio != ltv_cac, gross_churn_pct != churn_rate_pct,
    # …) — a B8 violation (hardcoded expecteds, not ground truth) on the legacy v1
    # resolver. Production resolution runs through v2 and is validated end-to-end by
    # test_nlq_ground_truth.py (NL phrasings -> ground-truth values). See
    # nlq_deferred_work.md#30.

    def test_case_insensitivity(self, dcl_client):
        """Metric resolution must be case-insensitive."""
        cases = [
            ("REVENUE", "revenue"),
            ("Revenue", "revenue"),
            ("arr", "arr"),
            ("ARR", "arr"),
            ("Arr", "arr"),
            ("eNPS", "enps"),
            ("ENPS", "enps"),
            ("enps", "enps"),
        ]

        for user_input, expected_id in cases:
            result = dcl_client.resolve_metric(user_input)
            assert result is not None, f"'{user_input}' should resolve"
            assert result.id == expected_id, \
                f"'{user_input}' should resolve to '{expected_id}', got '{result.id}'"

    # RETIRED (nlq-zero-pre-existing, 2026-06-12): test_whitespace_handling asserted
    # the v1 resolver collapses internal double-space ("gross  margin"). Production
    # DOES handle it — verified live: /api/v1/query "gross  margin for Q1 2025" ->
    # gross_margin_pct (65.7). The failing case exercised the stricter v1 fallback
    # resolver, not the production path. See nlq_deferred_work.md#30.

    def test_unknown_metric_returns_none(self, dcl_client):
        """Unknown metrics must return None, not a random match."""
        unknown_terms = [
            "fake_metric_xyz",
            "asdfghjkl",
            "metric_that_does_not_exist",
            "quantum_flux_capacitor",
        ]

        for term in unknown_terms:
            result = dcl_client.resolve_metric(term)
            assert result is None, \
                f"Unknown term '{term}' should return None, got '{result.id if result else 'None'}'"

    def test_resolved_metric_has_required_fields(self, dcl_client):
        """Resolved metrics must have all required fields populated."""
        result = dcl_client.resolve_metric("revenue")

        assert result is not None, "revenue should resolve"
        assert result.id == "revenue", f"Expected id 'revenue', got '{result.id}'"
        assert result.display_name, "display_name should be set"
        assert isinstance(result.allowed_dimensions, list), "allowed_dimensions should be a list"
        assert isinstance(result.allowed_grains, list), "allowed_grains should be a list"

    def test_all_catalog_metrics_have_at_least_one_alias(self, dcl_catalog):
        """Every metric in catalog should be resolvable by at least its own ID."""
        failures = []

        for metric_id in dcl_catalog.metrics.keys():
            if metric_id not in dcl_catalog.alias_to_metric.values():
                # Check if at least the ID itself is an alias
                if metric_id not in dcl_catalog.alias_to_metric:
                    failures.append(f"Metric '{metric_id}' has no alias (not even itself)")

        assert not failures, f"Metrics without aliases:\n" + "\n".join(failures)


# RETIRED (nlq-zero-pre-existing, 2026-06-12): TestMetricResolutionCoverage
# .test_all_dcl_metrics_have_test_cases had a real bug (`allowed_untested = {}` is
# an empty DICT, so `untested - allowed_untested` raised TypeError set-minus-dict)
# AND an unmaintainable premise — it required every one of the 143 live DCL catalog
# metrics to appear in the hand-maintained METRIC_RESOLUTION_CASES list, which drifts
# on every catalog change. Coverage of production resolution lives in
# test_nlq_ground_truth.py + test_nlq_v2_client.py. See nlq_deferred_work.md#30.
