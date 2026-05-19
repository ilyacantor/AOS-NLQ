"""WS-5 B2 — per-triple provenance threading in NLQ widget resolver.

B2 invariants:
  1. _extract_per_item_provenance() returns a dict with the 5 provenance
     fields when the DCL response item carries them.
  2. None when the item carries no provenance (legacy / aggregated row).
  3. Partial provenance (some fields present, others missing) returns
     just what's present — does NOT fabricate the missing fields.
  4. _extract_dimensional_data integrates provenance into each
     breakdown row when present, leaves rows clean when absent.
"""
from __future__ import annotations

import os

import pytest

# DashboardDataResolver.__init__ instantiates the DCL semantic client,
# which requires DCL_API_URL OR NLQ_ALLOW_NO_DCL=1. These tests don't
# call into DCL — they test the resolver's pure extraction helpers —
# so the degraded-mode flag is the right gate.
os.environ.setdefault("NLQ_ALLOW_NO_DCL", "1")
os.environ.setdefault("DCL_API_URL", "http://localhost:8104")

from src.nlq.core.dashboard_data_resolver import (
    DashboardDataResolver,
    _extract_per_item_provenance,
)


def test_provenance_extracted_when_all_fields_present():
    item = {
        "label": "NetSuite", "value": 100,
        "source_system": "NetSuite",
        "source_field": "amount",
        "pipe_id": "pipe-abc",
        "fabric_plane": "workato",
        "confidence_score": 0.95,
    }
    prov = _extract_per_item_provenance(item)
    assert prov == {
        "source_system": "NetSuite", "source_field": "amount",
        "pipe_id": "pipe-abc", "fabric_plane": "workato",
        "confidence_score": 0.95,
    }


def test_provenance_returns_none_when_absent():
    """Legacy or aggregated rows carry no provenance — return None,
    not an empty dict (signals "no provenance available")."""
    item = {"label": "Total", "value": 1000}
    assert _extract_per_item_provenance(item) is None


def test_provenance_partial_does_not_fabricate():
    """Only fields actually present make it into the result. A1: don't
    invent 'unknown' for missing fields — let the consumer see the gap."""
    item = {
        "label": "X", "value": 5,
        "source_system": "Sage Intacct",
        "fabric_plane": "boomi",
        # source_field, pipe_id, confidence_score deliberately absent
    }
    prov = _extract_per_item_provenance(item)
    assert prov == {"source_system": "Sage Intacct", "fabric_plane": "boomi"}
    assert "source_field" not in prov
    assert "pipe_id" not in prov


def test_extract_dimensional_data_threads_provenance():
    """When DCL items carry provenance, the breakdown rows include it."""
    resolver = DashboardDataResolver()
    result = {
        "data": [
            {"dimensions": {"region": "AMER"}, "value": 100,
             "source_system": "NetSuite", "source_field": "amount",
             "pipe_id": "pipe-a", "fabric_plane": "workato",
             "confidence_score": 0.95},
            {"dimensions": {"region": "EMEA"}, "value": 50,
             "source_system": "Sage Intacct", "source_field": "amount",
             "pipe_id": "pipe-b", "fabric_plane": "boomi",
             "confidence_score": 0.97},
        ],
    }
    breakdown = resolver._extract_dimensional_data(result, dimension="region")
    assert len(breakdown) == 2
    assert breakdown[0]["provenance"]["source_system"] == "NetSuite"
    assert breakdown[1]["provenance"]["source_system"] == "Sage Intacct"
    # Ratio still computed correctly with provenance present
    assert breakdown[0]["ratio"] + breakdown[1]["ratio"] == 1.00


def test_extract_dimensional_data_omits_provenance_when_absent():
    """Legacy DCL response items (no per-triple provenance) produce
    clean breakdown rows without a provenance key — does not add
    `provenance: None` as noise."""
    resolver = DashboardDataResolver()
    result = {
        "data": [
            {"dimensions": {"region": "AMER"}, "value": 100},
        ],
    }
    breakdown = resolver._extract_dimensional_data(result, dimension="region")
    assert len(breakdown) == 1
    assert "provenance" not in breakdown[0]
    assert breakdown[0]["label"] == "AMER"
    assert breakdown[0]["value"] == 100
