"""
PR 7 negative + positive tests: the fixture-backed provenance is gone.

Background: the NLQ /query response used to attach a static provenance
lineage sourced from data/entity_test_scenarios.json. That lineage was
keyed only by metric name, entity-blind, and masked the real DCL ingestion
metadata available in the client ctx vars. PR 7 removed the enrichment
wrapper (get_provenance_for_metric) so real run_provenance now wins.

These tests assert both the absence of fixture shape and presence of the
real run_provenance shape on the response.

Requires NLQ backend running at http://localhost:8005.
"""

import json
import os
import re

import httpx
import pytest

NLQ_BASE = "http://localhost:8005"

# UUID v4 / generic UUID regex — response.tenant_id must match this (I2).
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# Fixture keys — if any appear in response.provenance, PR 7 has regressed.
FIXTURE_PROVENANCE_KEYS = ("lineage", "system_of_record", "trust_score")

# Fixture strings — if any appear anywhere in the response body, PR 7 has
# regressed. These are the identifiers baked into
# data/entity_test_scenarios.json's provenance block.
FIXTURE_STRINGS = ("sap_erp", "BSEG", "DMBTR", "netsuite_erp")

# Real run_provenance modes (old-client DCL ingestion path) and v2 triples mode.
REAL_MODE_VALUES = {"ingest", "live", "farm"}


@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=NLQ_BASE, timeout=30.0)


@pytest.fixture(scope="module")
def first_entity_id(client):
    resp = client.get("/api/v1/entities")
    assert resp.status_code == 200, f"entities endpoint failed: {resp.text}"
    entities = resp.json().get("entities", [])
    assert entities, "no entities registered — cannot run provenance tests"
    return entities[0]["entity_id"]


def _post_revenue_query(client, entity_id):
    resp = client.post(
        "/api/v1/query",
        json={
            "question": f"What is {entity_id} revenue for 2026 Q2?",
            "entity_id": entity_id,
            "reference_date": "2026-04-08",
        },
    )
    assert resp.status_code == 200, f"/query failed: {resp.status_code} {resp.text}"
    return resp.json()


def test_response_provenance_has_no_fixture_keys(client, first_entity_id):
    """provenance dict must not carry the static fixture shape keys."""
    data = _post_revenue_query(client, first_entity_id)
    prov = data.get("provenance") or {}
    offenders = [k for k in FIXTURE_PROVENANCE_KEYS if k in prov]
    assert not offenders, (
        f"Fixture provenance keys leaked into response.provenance: {offenders} — "
        f"got provenance={prov!r}"
    )


def test_provenance_subtree_contains_no_fixture_strings(client, first_entity_id):
    """Static fixture identifiers must not appear anywhere in the provenance
    subtree of the response. Scoped to provenance only — the conflicts enrichment
    step is still fixture-backed and is a separate cleanup outside PR 7 scope."""
    data = _post_revenue_query(client, first_entity_id)
    prov = data.get("provenance") or {}
    body = json.dumps(prov)
    offenders = [s for s in FIXTURE_STRINGS if s in body]
    assert not offenders, (
        f"Fixture strings appeared in response.provenance: {offenders}. "
        f"Full provenance: {prov!r}"
    )


def test_response_provenance_has_real_mode(client, first_entity_id):
    """provenance.mode must be set and match one of the real modes."""
    data = _post_revenue_query(client, first_entity_id)
    prov = data.get("provenance") or {}
    mode = (prov.get("mode") or "").lower()
    assert mode in REAL_MODE_VALUES, (
        f"provenance.mode must be one of {REAL_MODE_VALUES}, got {mode!r}. "
        f"full provenance={prov!r}"
    )


def test_response_provenance_source_systems_is_list(client, first_entity_id):
    """provenance.source_systems must be a list (possibly empty), never None or a string."""
    data = _post_revenue_query(client, first_entity_id)
    prov = data.get("provenance") or {}
    sources = prov.get("source_systems")
    assert isinstance(sources, list), (
        f"provenance.source_systems must be a list, got {type(sources).__name__}: "
        f"{sources!r}"
    )


def test_response_carries_tenant_id(client, first_entity_id):
    """I2: every /query response must carry a non-empty tenant_id UUID.

    Sourced from AOS_TENANT_ID env var via config.get_tenant_id() and
    backfilled at the routes.py boundary symmetric to entity_id.

    Requires AOS_TENANT_ID to be set in the test environment. A bare
    dev machine without the env var cannot verify the backfill source,
    so the test fails loud on setup rather than silently skipping the
    cross-check (B4 — no passing on technicality).
    """
    env_tid = os.environ.get("AOS_TENANT_ID", "").strip()
    assert env_tid, (
        "AOS_TENANT_ID env var is required to run this test — it is the "
        "canonical source per I6 rule 4 and this test verifies the backfill "
        "stamps the env var value onto the response. Set AOS_TENANT_ID "
        "before running pytest."
    )
    data = _post_revenue_query(client, first_entity_id)
    tid = data.get("tenant_id")
    assert tid, f"response.tenant_id must be non-empty (I2). got {tid!r}"
    assert _UUID_RE.match(tid), (
        f"response.tenant_id must be a UUID, got {tid!r}"
    )
    assert tid == env_tid, (
        f"response.tenant_id ({tid!r}) must match AOS_TENANT_ID env var "
        f"({env_tid!r}). Mismatch indicates a backfill source drift."
    )
