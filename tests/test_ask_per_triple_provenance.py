"""Ask per-triple provenance — AAM Blueprint v3.1 §9.2.

"NLQ Ask carries only run-level provenance — bring it to per-triple to match
Dashboards." The single capture point is DCLSemanticClient._normalize_dcl_query_
response, which builds run_provenance from a DCL query response. run_provenance
flows to the Ask NLQResponse.provenance (via get_last_provenance / _ensure_
provenance), so threading per-triple here surfaces it on every Ask answer.

Invariants:
  1. When DCL data rows carry per-triple provenance, run_provenance.per_triple
     lists one provenance dict per contributing row (the 5 canonical fields).
  2. Legacy rows (no provenance) produce NO per_triple key — never fabricated
     (A1), and the run-level provenance is unaffected.
  3. Partial per-triple provenance surfaces only the fields present (A1).
  4. Ask and the dashboard resolver use the SAME extractor (shared module), so
     they cannot drift.
"""
from __future__ import annotations

import os

os.environ.setdefault("NLQ_ALLOW_NO_DCL", "1")
os.environ.setdefault("DCL_API_URL", "http://localhost:8104")

from src.nlq.services.dcl_semantic_client import DCLSemanticClient
from src.nlq.core.dashboard_data_resolver import _extract_per_item_provenance
from src.nlq.services.provenance import PROVENANCE_FIELDS, prov_from_triple


def _normalize(resp):
    return DCLSemanticClient()._normalize_dcl_query_response(resp)


def test_per_triple_carried_when_rows_have_provenance():
    """Rows carrying the 5 canonical fields -> run_provenance.per_triple lists
    one provenance dict per row, each with all 5 fields."""
    resp = {
        "metric": "cloud_spend", "unit": "usd",
        "metadata": {"source": "ingest", "mode": "Ingest", "tenant_id": "t1", "entity_id": "E1"},
        "data": [
            {"period": "2025-Q3", "value": 12.0, "source_system": "aws_cost",
             "source_field": "UnblendedCost", "pipe_id": "pipe-1",
             "fabric_plane": "warehouse", "confidence_score": 0.97},
            {"period": "2025-Q3", "value": 3.0, "source_system": "datadog",
             "source_field": "cost", "pipe_id": "pipe-2",
             "fabric_plane": "gateway", "confidence_score": 0.90},
        ],
        "provenance": [{"source_system": "aws_cost", "freshness": "2h", "quality_score": 0.97}],
    }
    rp = _normalize(resp)["run_provenance"]
    pt = rp["per_triple"]
    assert len(pt) == 2
    assert pt[0] == {
        "source_system": "aws_cost", "source_field": "UnblendedCost",
        "pipe_id": "pipe-1", "fabric_plane": "warehouse", "confidence_score": 0.97,
    }
    assert pt[1]["source_system"] == "datadog" and pt[1]["pipe_id"] == "pipe-2"
    # Run-level provenance still present and correct alongside per-triple.
    assert rp["source_systems"] == ["aws_cost"]
    assert rp["mode"] == "Ingest"


def test_no_per_triple_when_rows_legacy():
    """Legacy rows (period/value only) -> no per_triple key. A1: never
    fabricate per-triple provenance; run-level provenance is unaffected."""
    resp = {
        "metric": "revenue",
        "metadata": {"source": "ingest", "mode": "Ingest"},
        "data": [{"period": "2025-Q3", "value": 50.0}],
        "provenance": [{"source_system": "netsuite", "quality_score": 0.9}],
    }
    rp = _normalize(resp)["run_provenance"]
    assert "per_triple" not in rp
    assert rp["source_systems"] == ["netsuite"]


def test_per_triple_partial_does_not_fabricate():
    """A row with only some provenance fields surfaces just those fields."""
    resp = {
        "metric": "cloud_spend",
        "metadata": {"source": "ingest", "mode": "Ingest"},
        "data": [{"period": "2025-Q3", "value": 9.0,
                  "source_system": "aws_cost", "confidence_score": 0.8}],
        "provenance": [{"source_system": "aws_cost", "quality_score": 0.8}],
    }
    rp = _normalize(resp)["run_provenance"]
    assert rp["per_triple"] == [{"source_system": "aws_cost", "confidence_score": 0.8}]
    assert "source_field" not in rp["per_triple"][0]


def test_ask_and_dashboard_use_same_extractor():
    """Ask (prov_from_triple, 5 canonical) and the dashboard resolver
    (_extract_per_item_provenance, canonical + R5) share one extractor, so a
    row's canonical fields extract identically on both surfaces."""
    row = {
        "value": 1, "source_system": "aws_cost", "source_field": "cost",
        "pipe_id": "p1", "fabric_plane": "warehouse", "confidence_score": 0.95,
    }
    ask_prov = prov_from_triple(row)
    dash_prov = _extract_per_item_provenance(row)
    for f in PROVENANCE_FIELDS:
        assert ask_prov[f] == dash_prov[f] == row[f]
