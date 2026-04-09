"""
Unit tests for DCLSemanticClientV2._propagate_provenance.

Pure unit tests — no HTTP, no DCL. Verify the _live_triple sentinel
contract: only result dicts whose fields came from a live
/api/dcl/triples/browse round-trip get mode="Ingest". Everything else
gets mode=None so the ProvenanceBadge renders "No Data" instead of
lying about the source.
"""

from src.nlq.services.dcl_semantic_client_v2 import (
    DCLSemanticClientV2,
    _last_data_source_ctx,
    _last_provenance_ctx,
)


def _reset_ctx():
    _last_data_source_ctx.set(None)
    _last_provenance_ctx.set(None)


def test_propagate_provenance_without_sentinel_emits_mode_none():
    """Result dict without _live_triple → mode is None (not "Ingest", not "Farm")."""
    _reset_ctx()
    DCLSemanticClientV2._propagate_provenance({
        "value": 100.0,
        "entity_id": "TestCo",
        "source_system": "Farm",
        "confidence_score": 0.95,
    })
    ctx = _last_provenance_ctx.get()
    assert ctx is not None, "provenance ctx must be set"
    assert ctx["mode"] is None, (
        f"missing _live_triple must produce mode=None, got {ctx['mode']!r}"
    )


def test_propagate_provenance_with_sentinel_emits_ingest():
    """Result dict with _live_triple=True → mode == 'Ingest'."""
    _reset_ctx()
    DCLSemanticClientV2._propagate_provenance({
        "value": 100.0,
        "entity_id": "TestCo",
        "source_system": "Farm",
        "confidence_score": 0.95,
        "_live_triple": True,
    })
    ctx = _last_provenance_ctx.get()
    assert ctx is not None
    assert ctx["mode"] == "Ingest", (
        f"_live_triple=True must produce mode='Ingest', got {ctx['mode']!r}"
    )
    assert ctx["is_sor"] is True, "confidence_score >= 0.9 must set is_sor=True"
    assert ctx["source_systems"] == ["Farm"]


def test_propagate_provenance_none_value_is_no_op():
    """Result dict with value=None → early return, no ctx mutation."""
    _reset_ctx()
    DCLSemanticClientV2._propagate_provenance({
        "value": None,
        "error": "no data",
        "_live_triple": True,
    })
    assert _last_provenance_ctx.get() is None, (
        "value=None results must not touch provenance ctx"
    )
    assert _last_data_source_ctx.get() is None
