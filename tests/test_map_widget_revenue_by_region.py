"""Revenue-by-Region map widget — period scoping + currency scale.

Two bugs this suite locks down in DashboardDataResolver._resolve_map_data:

  Bug A (period): the map summed revenue.by_region.{region} triples across
    ALL 12 quarters, ignoring the reference_year parameter. The KPI card
    path scopes to a single year; the map must too.

  Bug B (scale): the resolver emitted metric-native values (revenue triples
    are denominated in millions). The frontend MapWidget formats client-side
    via formatCurrency(), which treats its argument as whole dollars — so a
    value of ~390 (meaning $390M) rendered as "$390", and a yearly total of
    ~1240 rendered as "$1.2K". Millions-denominated metrics must be scaled
    to whole dollars before reaching a client-side currency formatter.

Operator-visible outcome: with reference year 2025, the Revenue by Region
map's total reads on the order of "$1.2B" (matching that year's revenue
total to the cent), not "$4K"; AMER/EMEA/APAC bubbles each read in the
hundreds of millions.

Ground truth is pulled from DCL at test runtime (B8/B10) — no hardcoded
expected values. Live-services test: exercises the real resolver against a
running DCL. Skips cleanly if DCL is unreachable or carries no region data.
"""
from __future__ import annotations

import os

import httpx
import pytest

os.environ.setdefault("DCL_API_URL", "http://localhost:8104")

from src.nlq.core.dashboard_data_resolver import (
    DashboardDataResolver,
    _to_display_dollars,
    _year_quarters,
)
from src.nlq.models.dashboard_schema import (
    DataBinding, GridPosition, MetricBinding, Widget, WidgetType,
)
from src.nlq.services.dcl_semantic_client import set_entity_id

DCL_URL = os.environ["DCL_API_URL"]
REFERENCE_YEAR = "2025"
REGION_PREFIX = "revenue.by_region."


def _active_runs() -> list[dict]:
    """DCL's active ingest runs (runs-API) — a STABLE source for the entity↔tenant
    pair. get_tenant_id()'s follow-cache can be poisoned by other tests via the
    AOS_TENANT_ID fallback (then this module browses the wrong tenant and 422s),
    so we read identity straight from the runs surface, the same pairing the
    resolver resolves via tenant_for_query."""
    resp = httpx.get(f"{DCL_URL}/api/dcl/triples/runs", params={"limit": 500}, timeout=20.0)
    resp.raise_for_status()
    runs = resp.json().get("runs", [])
    if not runs:
        pytest.skip("DCL has no ingest runs — run the pipeline first")
    return runs


def _tenant_for_entity(entity_id: str) -> str:
    """Entity's tenant (entity↔tenant 1:1) from the active runs — order-independent."""
    for run in _active_runs():
        if run.get("is_active") and entity_id in (run.get("entity_summary") or {}):
            return run["tenant_id"]
    raise AssertionError(f"No active DCL run names entity {entity_id!r}")


def _dcl_revenue_triples(entity_id: str) -> list[dict]:
    """Pull every revenue-domain triple for an entity straight from DCL, scoped to
    the entity's own tenant (1:1, identity-enforced browse — matches the resolver)."""
    resp = httpx.get(
        f"{DCL_URL}/api/dcl/triples/browse",
        params={
            "tenant_id": _tenant_for_entity(entity_id),
            "entity_id": entity_id,
            "domain": "revenue",
            "limit": 500,
        },
        timeout=20.0,
    )
    resp.raise_for_status()
    return resp.json().get("triples", [])


def _discover_region_entity() -> str:
    """The current-run entity (what NLQ defaults to), provided it carries
    revenue.by_region triples. Read from the runs API so it is stable across test
    ordering. Skips if DCL is down or the current entity has no region data.
    """
    try:
        runs = _active_runs()
    except (httpx.HTTPError, OSError) as exc:
        pytest.skip(f"DCL not reachable at {DCL_URL}: {exc}")
    ents = [e for e in (runs[0].get("entity_summary") or {}) if e != "combined"]
    if not ents:
        pytest.skip("Current DCL run names no single entity")
    entity = ents[0]
    for t in _dcl_revenue_triples(entity):
        concept = t.get("concept") or ""
        # revenue.by_region.{region} has exactly two dots; exclude the
        # nested revenue.new_logo.by_region.* family (three dots).
        if concept.startswith(REGION_PREFIX) and concept.count(".") == 2:
            return entity
    pytest.skip(f"Current entity {entity} carries no revenue.by_region triples")


@pytest.fixture(scope="module")
def region_entity() -> str:
    return _discover_region_entity()


@pytest.fixture(scope="module")
def ground_truth(region_entity: str) -> dict:
    """Year-2025 revenue ground truth, computed from raw DCL triples.

    Returns the per-region totals and the revenue.total sum for 2025 —
    the values the map must reproduce.
    """
    triples = _dcl_revenue_triples(region_entity)
    year_q = _year_quarters(REFERENCE_YEAR)

    region_totals: dict[str, float] = {}
    total_2025 = 0.0
    region_total_all_12q = 0.0
    for t in triples:
        concept = t.get("concept") or ""
        period = t.get("period")
        val = t.get("value")
        if val is None:
            continue
        if concept == "revenue.total" and period in year_q:
            total_2025 += float(val)
        if concept.startswith(REGION_PREFIX) and concept.count(".") == 2:
            region = concept[len(REGION_PREFIX):]
            if (period or "").endswith(("-Q1", "-Q2", "-Q3", "-Q4")):
                region_total_all_12q += float(val)
            if period in year_q:
                region_totals[region.upper()] = (
                    region_totals.get(region.upper(), 0.0) + float(val)
                )

    assert region_totals, "Expected revenue.by_region triples for 2025"
    return {
        "region_totals_millions": region_totals,
        "total_2025_millions": total_2025,
        "region_sum_all_12q_millions": region_total_all_12q,
    }


def _map_widget() -> Widget:
    return Widget(
        id="w-revenue-by-region",
        type=WidgetType.MAP,
        title="Revenue by Region",
        data=DataBinding(metrics=[MetricBinding(metric="revenue")]),
        position=GridPosition(column=1, row=1, col_span=6, row_span=3),
    )


@pytest.fixture
def map_result(region_entity: str) -> dict:
    set_entity_id(region_entity)
    resolver = DashboardDataResolver()
    return resolver._resolve_map_data(_map_widget(), REFERENCE_YEAR, {})


# --------------------------------------------------------------------------
# _year_quarters / _to_display_dollars unit coverage
# --------------------------------------------------------------------------

def test_year_quarters_returns_four_quarters_of_the_year():
    assert _year_quarters("2025") == {"2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"}


def test_to_display_dollars_scales_millions_metric():
    # revenue is a "USD millions" metric: 318.89 means $318.89M.
    assert _to_display_dollars("revenue", 318.89) == pytest.approx(318_890_000.0)


def test_to_display_dollars_passes_through_non_millions_metric():
    # headcount is denominated in people, not millions — no scale change.
    assert _to_display_dollars("headcount", 500.0) == 500.0


# --------------------------------------------------------------------------
# Bug A — period scoping
# --------------------------------------------------------------------------

def test_map_total_scoped_to_reference_year_not_all_quarters(map_result, ground_truth):
    """Map total equals revenue.total for 2025 — proving the year filter.

    Pre-fix the map summed all 12 quarters. We assert the map total is the
    2025 figure AND is strictly less than the all-12-quarter sum, so a
    regression to the old all-quarters behavior fails this test.
    """
    map_total_millions = map_result["map_data"]["total"] / 1_000_000
    assert map_total_millions == pytest.approx(
        ground_truth["total_2025_millions"], abs=0.01
    ), (
        f"Map total {map_total_millions:.2f}M should equal revenue.total for "
        f"{REFERENCE_YEAR} = {ground_truth['total_2025_millions']:.2f}M"
    )
    # all-12-quarter sum is the pre-fix wrong value — must be larger.
    assert map_total_millions < ground_truth["region_sum_all_12q_millions"] - 0.01, (
        "Map total still equals the all-12-quarter sum — period filter not applied"
    )


def test_map_per_region_values_match_year_2025_ground_truth(map_result, ground_truth):
    """Each region's map value equals that region's 2025 revenue, scaled."""
    by_region = {r["region"]: r["value"] for r in map_result["map_data"]["regions"]}
    expected = ground_truth["region_totals_millions"]
    assert set(by_region) == set(expected), (
        f"Map regions {sorted(by_region)} != ground truth {sorted(expected)}"
    )
    for region, gt_millions in expected.items():
        got_millions = by_region[region] / 1_000_000
        assert got_millions == pytest.approx(gt_millions, abs=0.01), (
            f"{region}: map shows {got_millions:.2f}M, "
            f"DCL ground truth for {REFERENCE_YEAR} is {gt_millions:.2f}M"
        )


# --------------------------------------------------------------------------
# Bug B — currency scale (whole dollars for client-side formatCurrency)
# --------------------------------------------------------------------------

def test_map_values_are_whole_dollars_not_raw_millions(map_result, ground_truth):
    """Map values are scaled to whole dollars.

    formatCurrency() in MapWidget renders 1_241_840_000 as "$1.2B" but a raw
    1241.84 as "$1.2K" — the reported bug. The map total for 2025 must be in
    the hundreds-of-millions / billions range, not the low thousands.
    """
    total = map_result["map_data"]["total"]
    assert total > 100_000_000, (
        f"Map total {total} is not whole-dollar scaled — raw millions value "
        f"would render as a few thousand dollars via formatCurrency"
    )
    # The map total is the sum of the regions it displays (enforced by
    # test_map_regions_sum_to_map_total), so its ground truth is the sum of the
    # by_region values — NOT revenue.total. Farm allocates per-region revenue
    # with independent 2dp rounding, so Σ(by_region) sits ~$10K under
    # revenue.total at $1.3B scale; the by-region map legitimately totals its
    # regions, and asserting against revenue.total would chase Farm's rounding.
    expected_region_sum = sum(ground_truth["region_totals_millions"].values())
    assert total == pytest.approx(expected_region_sum * 1_000_000, abs=1.0)
    for region in map_result["map_data"]["regions"]:
        assert region["value"] > 1_000_000, (
            f"{region['region']} value {region['value']} not whole-dollar scaled"
        )


def test_map_regions_sum_to_map_total(map_result):
    """Internal consistency: per-region values sum to the declared total."""
    region_sum = sum(r["value"] for r in map_result["map_data"]["regions"])
    assert region_sum == pytest.approx(map_result["map_data"]["total"], abs=1.0)


def test_map_series_data_matches_region_values(map_result):
    """The series payload (MapWidget fallback path) carries the same scaled
    values as map_data.regions — no unscaled leak through the alt path."""
    region_values = {r["region"]: r["value"] for r in map_result["map_data"]["regions"]}
    series_values = {
        d["label"]: d["value"] for d in map_result["series"][0]["data"]
    }
    assert series_values == region_values


# --------------------------------------------------------------------------
# Negative — no regional data must surface an honest error, not a wrong number
# --------------------------------------------------------------------------

def test_map_no_region_data_surfaces_error(region_entity):
    """A metric with no .by_region triples returns the 'No regional data'
    error branch — it does not silently emit a zero or bogus total (A1)."""
    set_entity_id(region_entity)
    resolver = DashboardDataResolver()
    widget = Widget(
        id="w-headcount-map",
        type=WidgetType.MAP,
        title="Headcount by Region",
        data=DataBinding(metrics=[MetricBinding(metric="headcount")]),
        position=GridPosition(column=1, row=1, col_span=6, row_span=3),
    )
    result = resolver._resolve_map_data(widget, REFERENCE_YEAR, {})
    assert "map_data" not in result
    assert result.get("error") == "No regional data for 'headcount'"


def test_map_year_with_no_quarters_surfaces_error(region_entity):
    """A reference year DCL has no quarters for surfaces the no-data error
    rather than falling back to summing every period (A1)."""
    set_entity_id(region_entity)
    resolver = DashboardDataResolver()
    result = resolver._resolve_map_data(_map_widget(), "2099", {})
    assert "map_data" not in result
    assert result.get("error") == "No regional data for 'revenue'"
