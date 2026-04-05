"""
Sweep 2 — NLQ → DCL End-to-End Integration Test

Verifies the NLQ ↔ DCL integration plumbing:
- Entity discovery (EntityRegistry → DCL resolution/v2/stats)
- Query pipeline (POST /api/v1/query → DCL → response)
- Error handling (unknown entities, graceful failures)
- Provenance and response structure

NOTE: Actual data value assertions (revenue == ground truth) are deferred
until Sweep 5 cutover, which wires DCL's /api/dcl/query to the v2 engine stack.
Currently NLQ queries the old ingest buffer, not semantic_triples.
"""

import pytest
import httpx

NLQ_BASE = "http://localhost:8005"
DCL_BASE = "http://localhost:8004"


@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=NLQ_BASE, timeout=30.0)


@pytest.fixture(scope="module")
def dcl_client():
    return httpx.Client(base_url=DCL_BASE, timeout=30.0)


# --- Test 1: Simple revenue query returns valid response ---
def test_revenue_query_response(client):
    """NLQ accepts a revenue query and returns a well-formed response."""
    resp = client.post("/api/v1/query", json={"question": "What is revenue?"})
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "confidence" in data
    assert "provenance" in data
    assert isinstance(data["answer"], str)
    assert len(data["answer"]) > 0


# --- Test 2: Entity-scoped query accepted ---
def test_entity_scoped_query(client):
    """NLQ accepts an entity-scoped query and returns a response (not crash)."""
    # B10: resolve entity dynamically, not hardcoded
    ent_resp = client.get("/api/v1/entities")
    assert ent_resp.status_code == 200, f"Entity list failed: {ent_resp.text}"
    entities = ent_resp.json().get("entities", [])
    assert len(entities) > 0, "No entities available for entity-scoped test"
    entity_id = entities[0]["entity_id"]

    resp = client.post(
        "/api/v1/query",
        json={"question": f"What is {entity_id}'s revenue?", "entity_id": entity_id},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "confidence" in data


# --- Test 3: Combined query accepted ---
def test_combined_query(client):
    """NLQ accepts a combined entity query."""
    resp = client.post(
        "/api/v1/query",
        json={"question": "What is combined revenue?", "entity_id": "combined"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data


# --- Test 4: Entity detection — dynamic from DCL ---
@pytest.mark.skipif(
    not __import__("os").environ.get("NLQ_INTEGRATION"),
    reason="Integration test — requires running NLQ + DCL services (NLQ_INTEGRATION=1)",
)
def test_entity_detection_dynamic(client, dcl_client):
    """NLQ discovers entities dynamically from DCL EntityRegistry, not hardcoded."""
    resp = client.get("/api/v1/entities")
    assert resp.status_code == 200
    data = resp.json()
    assert "entities" in data
    entities = data["entities"]
    assert len(entities) >= 2, f"Expected at least 2 entities, got {len(entities)}"

    # B10: cross-check against DCL ground truth, not hardcoded names
    entity_ids = [e["entity_id"] for e in entities]
    dcl_overview = dcl_client.get("/api/dcl/triples/overview").json()
    dcl_entity_ids = [e["entity_id"] for e in dcl_overview.get("entities", [])]
    for dcl_eid in dcl_entity_ids:
        assert dcl_eid in entity_ids, (
            f"DCL entity '{dcl_eid}' not found in NLQ entity list: {entity_ids}"
        )

    # Each entity has required fields
    for entity in entities:
        assert "entity_id" in entity
        assert "display_name" in entity
        assert "role" in entity

    # Combined should be available
    assert data.get("combined_available") is True


# --- Test 5: CHRO persona routing ---
def test_chro_query_routes(client):
    """CHRO-persona query doesn't crash or 404."""
    resp = client.post(
        "/api/v1/query",
        json={"question": "Show me the CHRO dashboard"},
    )
    # Should NOT be 404 or 500
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data


# --- Test 6: Provenance structure ---
@pytest.mark.skipif(
    not __import__("os").environ.get("NLQ_INTEGRATION"),
    reason="Integration test — requires running NLQ + DCL services (NLQ_INTEGRATION=1)",
)
def test_provenance_structure(client):
    """Query response includes provenance with required fields."""
    resp = client.post("/api/v1/query", json={"question": "What is revenue?"})
    assert resp.status_code == 200
    data = resp.json()
    assert "provenance" in data
    prov = data["provenance"]
    assert prov is not None, "Provenance must not be null"
    # Provenance should have source information
    assert "source_systems" in prov or "source_system" in prov
    assert "mode" in prov


# --- Test 7: Unknown entity handled gracefully ---
def test_unknown_entity_graceful(client):
    """Unknown entity_id returns a helpful error, not a crash."""
    resp = client.post(
        "/api/v1/query",
        json={"question": "What is foobar's revenue?", "entity_id": "foobar"},
    )
    # Should NOT be 500 (server crash)
    assert resp.status_code != 500, f"Server crashed on unknown entity: {resp.text}"
    # Should be either 200 with error info or 4xx with detail
    if resp.status_code == 200:
        data = resp.json()
        assert "answer" in data
    else:
        # 400/422 with detail is also acceptable
        assert resp.status_code in (400, 404, 422)
