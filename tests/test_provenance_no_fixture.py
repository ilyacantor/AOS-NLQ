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


def _entity_tenant_from_dcl(entity_id):
    """Ground truth: the tenant an entity's triples live under, read from DCL's
    runs at test time. Runs come back most-recent-first, so the first run naming the
    entity is its current tenant (entity↔tenant 1:1). Returns None if DCL has no run
    for it. This is the expected value the response must echo — never hardcoded, never
    AOS_TENANT_ID (B8/B10)."""
    dcl_url = os.environ.get("DCL_API_URL", "http://localhost:8104").rstrip("/")
    resp = httpx.get(f"{dcl_url}/api/dcl/triples/runs", timeout=10.0)
    resp.raise_for_status()
    for run in resp.json().get("runs", []):
        if entity_id in (run.get("entity_summary") or {}):
            return run.get("tenant_id")
    return None


def test_response_carries_tenant_id(client, first_entity_id):
    """I2 + tenant-from-entity: a /query response carries the QUERIED entity's tenant.

    NLQ answers any named entity by resolving its tenant (entity↔tenant 1:1) and
    echoes it on the response. The expected tenant is DCL ground truth — the tenant
    the entity's triples actually live under, read from /api/dcl/triples/runs at test
    time (never hardcoded, never the AOS_TENANT_ID env pin, which is now only a
    DCL-unreachable fallback). A mismatch means NLQ scoped the query to the wrong
    tenant — e.g. whichever entity DCL currently shows — the exact bug
    tenant-from-entity fixes.
    """
    expected_tid = _entity_tenant_from_dcl(first_entity_id)
    assert expected_tid, (
        f"DCL has no run for entity {first_entity_id!r} — cannot establish the "
        f"ground-truth tenant. Ingest the entity before running this test."
    )
    data = _post_revenue_query(client, first_entity_id)
    tid = data.get("tenant_id")
    assert tid, f"response.tenant_id must be non-empty (I2). got {tid!r}"
    assert _UUID_RE.match(tid), (
        f"response.tenant_id must be a UUID, got {tid!r}"
    )
    assert tid == expected_tid, (
        f"User queried entity {first_entity_id!r}. Its tenant in DCL is "
        f"{expected_tid!r}, but the response carried {tid!r}. NLQ scoped the query "
        f"to the wrong tenant — tenant-from-entity resolution failed (I2/I6)."
    )
