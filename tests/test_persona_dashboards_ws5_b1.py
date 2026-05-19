"""WS-5 B1 — persona dashboard authoring infrastructure.

B1 invariants:
  1. load_persona_dashboards() reads every YAML under config/personas/
     and returns {id: DashboardSchema}.
  2. Each loaded dashboard is a fully-validated DashboardSchema —
     malformed YAMLs raise at load time, not at request time.
  3. populate_persona_cache() seeds _dashboard_cache; the existing
     GET /api/v1/dashboard/{id} endpoint serves persona IDs identically
     to the dynamic dash_<8hex> IDs.
  4. Empty config dir → empty dict + warning log; missing config dir →
     FileNotFoundError (A1, fail-loud on infra gap vs author gap).
  5. Duplicate dashboard ID across YAML files raises ValueError loudly.
  6. The shipped finops.yaml validates and has the expected tile count
     for the canonical AR-aging demo question.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.nlq.api.dashboard_routes import _dashboard_cache, populate_persona_cache
from src.nlq.models.dashboard_schema import DashboardSchema
from src.nlq.services import persona_dashboards as pd_mod
from src.nlq.services.persona_dashboards import load_persona_dashboards


def test_load_finops_persona_dashboard():
    """The shipped config/personas/finops.yaml loads cleanly."""
    loaded = load_persona_dashboards()
    assert "persona_finops" in loaded
    finops = loaded["persona_finops"]
    assert isinstance(finops, DashboardSchema)
    assert finops.title.startswith("FinOps")
    # AR aging dashboard has at least one KPI + one chart + drill table
    widget_types = {w.type for w in finops.widgets}
    assert "kpi_card" in widget_types
    assert "bar_chart" in widget_types
    assert "data_table" in widget_types
    assert len(finops.widgets) >= 4


def test_populate_persona_cache_seeds_dashboard_cache():
    """After populate_persona_cache, GET /api/v1/dashboard/{id} can
    return the persona dashboard."""
    _dashboard_cache.clear()
    populate_persona_cache(load_persona_dashboards())
    assert "persona_finops" in _dashboard_cache
    cached = _dashboard_cache["persona_finops"]
    assert isinstance(cached, DashboardSchema)


def test_populate_persona_cache_preserves_dynamic_entries():
    """Populating the persona cache does NOT clear dynamic dash_<8hex>
    entries — the two coexist."""
    _dashboard_cache.clear()
    # Simulate a dynamic dashboard already in cache
    dyn = DashboardSchema(
        id="dash_abc12345", title="dyn", source_query="x",
        widgets=[],
    )
    _dashboard_cache["dash_abc12345"] = dyn
    populate_persona_cache(load_persona_dashboards())
    assert "dash_abc12345" in _dashboard_cache  # dynamic preserved
    assert "persona_finops" in _dashboard_cache  # persona added


def test_missing_config_dir_raises(tmp_path, monkeypatch):
    """Pointing the loader at a non-existent dir must fail loudly per A1."""
    monkeypatch.setattr(pd_mod, "_PERSONA_CONFIG_DIR", tmp_path / "does_not_exist")
    with pytest.raises(FileNotFoundError, match="persona config dir missing"):
        load_persona_dashboards()


def test_empty_config_dir_returns_empty_dict(tmp_path, monkeypatch):
    """Empty (but present) config dir is acceptable — no persona
    dashboards loaded, but no error. Operator gets a warning log."""
    monkeypatch.setattr(pd_mod, "_PERSONA_CONFIG_DIR", tmp_path)
    result = load_persona_dashboards()
    assert result == {}


def test_malformed_yaml_raises(tmp_path, monkeypatch):
    """A YAML that doesn't parse as a mapping raises clearly."""
    bad = tmp_path / "broken.yaml"
    bad.write_text("- this\n- is\n- a\n- list\n")
    monkeypatch.setattr(pd_mod, "_PERSONA_CONFIG_DIR", tmp_path)
    with pytest.raises(ValueError, match="top-level must be a mapping"):
        load_persona_dashboards()


def test_duplicate_id_across_yamls_raises(tmp_path, monkeypatch):
    """Two YAMLs declaring the same id is an authoring error — raise."""
    body = textwrap.dedent("""\
        id: persona_dup
        title: First
        source_query: x
        widgets: []
    """)
    (tmp_path / "a.yaml").write_text(body)
    (tmp_path / "b.yaml").write_text(body)
    monkeypatch.setattr(pd_mod, "_PERSONA_CONFIG_DIR", tmp_path)
    with pytest.raises(ValueError, match="duplicate id"):
        load_persona_dashboards()


def test_invalid_schema_raises(tmp_path, monkeypatch):
    """A YAML missing a required DashboardSchema field raises."""
    bad = tmp_path / "incomplete.yaml"
    # Missing required `source_query` field.
    bad.write_text("id: persona_incomplete\ntitle: x\nwidgets: []\n")
    monkeypatch.setattr(pd_mod, "_PERSONA_CONFIG_DIR", tmp_path)
    with pytest.raises(Exception):
        load_persona_dashboards()
