"""PR 2: _resolve_entity_id no longer silent-falls back to entity_ids[0].

The NLQ /api/v1/query endpoint used to substitute the first registered entity
whenever the caller didn't supply one and the question text didn't name one.
That masked "unknown entity" questions behind a plausible-looking answer for
a different entity (the BlueLogic hallucination bug).

After PR 2:
  - Request with explicit entity_id → 200 (positive control).
  - Question naming a registered entity in text → 200 (_detect_entity_id).
  - Question naming an unknown entity, no entity_id → 422 with error body
    naming the question and listing registered entities.

Requires NLQ backend running at http://localhost:8005.
"""

import httpx
import pytest

NLQ_BASE = "http://localhost:8005"


@pytest.fixture(scope="module")
def client():
    return httpx.Client(base_url=NLQ_BASE, timeout=30.0)


@pytest.fixture(scope="module")
def registered_entities(client):
    resp = client.get("/api/v1/entities")
    assert resp.status_code == 200, f"entities endpoint failed: {resp.text}"
    entities = resp.json().get("entities", [])
    assert entities, "no entities registered — PR 2 tests require at least one"
    return entities


@pytest.fixture(scope="module")
def first_entity_id(registered_entities):
    return registered_entities[0]["entity_id"]


def test_unknown_entity_in_question_returns_422(client, first_entity_id):
    """Question names BlueLogic (unregistered) with no entity_id → 422.

    This is the root bug PR 2 fixes. Before PR 2 this returned 200 with a
    silently-substituted answer for the first registered entity.
    """
    resp = client.post(
        "/api/v1/query",
        json={"question": "What is BlueLogic revenue for 2026 Q2?"},
    )
    assert resp.status_code == 422, (
        f"expected 422 for unknown entity, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    detail = body.get("detail")
    assert isinstance(detail, dict), f"detail must be a dict, got {type(detail).__name__}"
    assert detail.get("error") == "entity_unresolved"
    assert "BlueLogic" in detail.get("question", "")
    registered = detail.get("registered_entities")
    assert isinstance(registered, list) and registered, (
        f"registered_entities must be a non-empty list, got {registered!r}"
    )
    assert first_entity_id in registered
    assert "hint" in detail and detail["hint"]


def test_explicit_entity_id_returns_200(client, first_entity_id):
    """Same BlueLogic question but with explicit entity_id → 200 (positive control).

    Explicit entity_id always wins. The question text is irrelevant once the
    caller has declared which entity they want.
    """
    resp = client.post(
        "/api/v1/query",
        json={
            "question": "What is BlueLogic revenue for 2026 Q2?",
            "entity_id": first_entity_id,
        },
    )
    assert resp.status_code == 200, (
        f"explicit entity_id must succeed, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body.get("entity_id") == first_entity_id


def test_text_detected_entity_returns_200(client, first_entity_id):
    """Question names a registered entity in text, no entity_id → 200.

    _detect_entity_id matches the entity_id against the question string. This
    path must still work after PR 2 — the 422 only fires when _detect fails.
    """
    resp = client.post(
        "/api/v1/query",
        json={"question": f"What is {first_entity_id} revenue for 2026 Q2?"},
    )
    assert resp.status_code == 200, (
        f"text-detected entity must succeed, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body.get("entity_id") == first_entity_id


def test_consolidate_flag_returns_200(client):
    """consolidate=True bypasses entity resolution → 200.

    The combined view path predates PR 2 and is unchanged. If consolidate=True
    the resolver returns "combined" and the caller never hits the 422.
    """
    resp = client.post(
        "/api/v1/query",
        json={
            "question": "What is BlueLogic revenue for 2026 Q2?",
            "consolidate": True,
        },
    )
    # May return 200 or a non-422 error from downstream (combined view may not
    # have data for a single-entity registry). PR 2 asserts only that
    # _resolve_entity_id does NOT raise 422 when consolidate is set.
    assert resp.status_code != 422, (
        f"consolidate=True must not trigger the entity-unresolved 422, "
        f"got {resp.status_code}: {resp.text}"
    )
