"""WS-5 B1 — persona dashboard authoring infrastructure.

B1 invariants:
  1. load_persona_dashboards() reads every YAML under config/personas/
     and returns {id: DashboardSchema}.
  2. Each loaded dashboard is a fully-validated DashboardSchema —
     malformed YAMLs raise at load time, not at request time.
  3. populate_persona_cache() seeds _dashboard_cache; the existing
     GET /api/v1/dashboard/{id} endpoint serves persona IDs identically
     to the dynamic dash_<8hex> IDs.
  4. Empty OR missing config dir → empty dict. No file-based persona
     dashboards is a valid state: FinOps is a domain, not a persona
     (AAM Blueprint v3.1 decision (d)), and the persona-dashboard model is
     runtime-generated. Not a silent fallback (A1) — there is genuinely
     nothing to load and dashboards are served by the runtime path.
  5. Duplicate dashboard ID across YAML files raises ValueError loudly.
  6. Malformed / schema-invalid persona YAMLs that DO exist still raise at
     load time (author gap), not at request time.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.nlq.api.dashboard_routes import _dashboard_cache, populate_persona_cache
from src.nlq.models.dashboard_schema import DashboardSchema
from src.nlq.services import persona_dashboards as pd_mod
from src.nlq.services.persona_dashboards import load_persona_dashboards


def test_no_file_based_personas_shipped():
    """finops.yaml was deleted (AAM Blueprint v3.1 decision (d): FinOps is a
    domain, not a persona). No persona YAMLs ship by default, so loading the
    real config/personas dir yields {} — and never the deleted persona_finops."""
    loaded = load_persona_dashboards()
    assert loaded == {}
    assert "persona_finops" not in loaded


def test_populate_persona_cache_seeds_dashboard_cache():
    """populate_persona_cache seeds _dashboard_cache so GET /api/v1/dashboard/
    {id} can serve a persona dashboard. Uses a synthetic schema since no
    persona YAMLs ship after the finops.yaml deletion."""
    _dashboard_cache.clear()
    synthetic = {
        "persona_demo": DashboardSchema(
            id="persona_demo", title="Demo", source_query="x", widgets=[],
        )
    }
    populate_persona_cache(synthetic)
    assert "persona_demo" in _dashboard_cache
    assert isinstance(_dashboard_cache["persona_demo"], DashboardSchema)


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
    persona = {
        "persona_demo": DashboardSchema(
            id="persona_demo", title="Demo", source_query="x", widgets=[],
        )
    }
    populate_persona_cache(persona)
    assert "dash_abc12345" in _dashboard_cache  # dynamic preserved
    assert "persona_demo" in _dashboard_cache    # persona added


def test_missing_config_dir_returns_empty_dict(tmp_path, monkeypatch):
    """A missing personas dir is a valid state, not an infra gap: no file-based
    persona dashboards ship after the finops.yaml deletion and dashboards are
    runtime-generated (AAM Blueprint v3.1 decision (d)). The loader returns {}
    instead of raising. This is the intentional contract change, not a weakened
    assertion — an absent dir genuinely means 'no persona YAMLs', which is
    correct now. YAMLs that DO exist but are malformed still raise (below)."""
    monkeypatch.setattr(pd_mod, "_PERSONA_CONFIG_DIR", tmp_path / "does_not_exist")
    assert load_persona_dashboards() == {}


def test_empty_config_dir_returns_empty_dict(tmp_path, monkeypatch):
    """Empty (but present) config dir is acceptable — no persona dashboards
    loaded, no error (info log)."""
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
