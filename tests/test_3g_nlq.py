"""
Stage 3G Harness — NLQ De-hardcoding
Verifies that all hardcoded entity references are removed from app code.
"""
import asyncio
import subprocess
import pytest
from pathlib import Path

NLQ_SRC = Path(__file__).parent.parent / "src" / "nlq"

# Files that are ALLOWED to contain entity names (demo data, tests, docs)
EXCLUDED_FILES = {
    "seed_data.py",
    "constitution",
    "ONGOING_PROMPTS",
    "__pycache__",
}


def _grep_entity(entity_name: str) -> list[str]:
    """Find hardcoded entity references in NLQ Python source."""
    hits = []
    for py_file in NLQ_SRC.rglob("*.py"):
        # Skip excluded files
        if any(exc in str(py_file) for exc in EXCLUDED_FILES):
            continue
        if "test_" in py_file.name:
            continue
        content = py_file.read_text()
        for i, line in enumerate(content.splitlines(), 1):
            if entity_name.lower() in line.lower():
                # Skip comments and strings that are clearly not hardcoded logic
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                hits.append(f"{py_file.relative_to(NLQ_SRC)}:{i}: {stripped}")
    return hits


# --- Test 1: No hardcoded "meridian" in app code ---
def test_no_hardcoded_meridian():
    hits = _grep_entity("meridian")
    assert len(hits) == 0, f"Found hardcoded 'meridian' in:\n" + "\n".join(hits)

# --- Test 2: No hardcoded "cascadia" in app code ---
def test_no_hardcoded_cascadia():
    hits = _grep_entity("cascadia")
    assert len(hits) == 0, f"Found hardcoded 'cascadia' in:\n" + "\n".join(hits)

# --- Test 3: EntityRegistry module exists ---
def test_entity_registry_exists():
    from nlq.core.entity_registry import EntityRegistry
    registry = EntityRegistry()
    assert registry is not None

# --- Test 4: EntityRegistry has required methods ---
def test_entity_registry_interface():
    from nlq.core.entity_registry import EntityRegistry
    registry = EntityRegistry()
    assert hasattr(registry, "get_entities")
    assert hasattr(registry, "get_entity_name")
    assert hasattr(registry, "get_entity_ids")
    assert hasattr(registry, "is_valid_entity")
    assert hasattr(registry, "invalidate_cache")

# --- Test 5: "combined" is always valid ---
def test_combined_always_valid():
    from nlq.core.entity_registry import EntityRegistry
    registry = EntityRegistry()
    result = asyncio.get_event_loop().run_until_complete(registry.is_valid_entity("combined"))
    assert result is True

# --- Test 6: _ENTITY_NAMES dict removed ---
def test_entity_names_removed():
    from nlq.core import composite_query
    assert not hasattr(composite_query, "_ENTITY_NAMES"), \
        "_ENTITY_NAMES dict still exists in composite_query.py — must be removed"

# --- Test 7: No _ENTITY_IDS constant ---
def test_no_entity_ids_constant():
    """Ensure there's no _ENTITY_IDS or similar hardcoded list."""
    source = (NLQ_SRC / "core" / "composite_query.py").read_text()
    assert "_ENTITY_IDS" not in source
    assert "'meridian'" not in source
    assert "'cascadia'" not in source

# --- Test 8: /api/v1/entities endpoint exists ---
def test_entities_endpoint_exists():
    """Verify the entities endpoint is registered in routes."""
    from nlq.api import routes
    source = Path(routes.__file__).read_text()
    assert "/entities" in source or "entities" in source

# --- Test 9: Frontend fetches entities dynamically ---
def test_frontend_dynamic_entities():
    """Check App.tsx doesn't hardcode entity list."""
    app_tsx = Path(__file__).parent.parent / "src" / "App.tsx"
    if app_tsx.exists():
        content = app_tsx.read_text()
        # Should NOT have a hardcoded entity array
        assert '"meridian"' not in content or "fetch" in content.lower(), \
            "App.tsx still has hardcoded meridian without dynamic fetch"

# --- Test 10: DCL unreachable raises error, not silent fallback ---
def test_dcl_unreachable_raises():
    from nlq.core.entity_registry import EntityRegistry
    registry = EntityRegistry(dcl_base_url="http://localhost:99999")
    with pytest.raises((ConnectionError, Exception)):
        asyncio.get_event_loop().run_until_complete(registry.get_entities())

# --- Test 11: Entity name resolution ---
def test_entity_name_resolution():
    """If DCL is running, entity names should resolve."""
    from nlq.core.entity_registry import EntityRegistry
    registry = EntityRegistry()
    try:
        loop = asyncio.get_event_loop()
        entities = loop.run_until_complete(registry.get_entities())
        if entities:
            name = loop.run_until_complete(registry.get_entity_name(entities[0]["entity_id"]))
            assert isinstance(name, str)
            assert len(name) > 0
    except ConnectionError:
        pytest.skip("DCL not running — skip live test")

# --- Test 12: No hardcoded CHRO/People routing ---
def test_no_hardcoded_persona_routing():
    """Ensure persona routing doesn't reference specific entity IDs."""
    for py_file in NLQ_SRC.rglob("*.py"):
        if any(exc in str(py_file) for exc in EXCLUDED_FILES):
            continue
        if "test_" in py_file.name:
            continue
        content = py_file.read_text()
        # Check for hardcoded persona->entity routing
        if "chro" in content.lower() and ("meridian" in content.lower() or "cascadia" in content.lower()):
            # Only flag if it's in executable code, not comments
            for i, line in enumerate(content.splitlines(), 1):
                if "chro" in line.lower() and ("meridian" in line.lower() or "cascadia" in line.lower()):
                    if not line.strip().startswith("#"):
                        pytest.fail(f"Hardcoded CHRO routing: {py_file}:{i}: {line.strip()}")
