"""WS-5 B1: persona dashboard authoring infrastructure.

Optional file-based persona dashboards may be authored in YAML under
`src/nlq/config/personas/<persona>.yaml`. Each file produces one
DashboardSchema that loads into `_dashboard_cache` on NLQ startup,
keyed by its stable id. The existing `GET /api/v1/dashboard/{id}`
endpoint serves them — no new endpoint, no change to the dynamic
`dash_<8hex>` path.

As of AAM Blueprint v3.1 decision (d), the only file-based persona
(`finops.yaml`) was deleted — FinOps is a domain, not a persona — and
no persona YAMLs ship by default. The persona-dashboard model is
runtime-generated, so an absent/empty personas dir is the normal state
and load_persona_dashboards() returns {} (see the loader for why this
is correct and not a silent fallback).

Per WS-5 B1:
  - This module defines load_persona_dashboards() — reads every YAML
    under config/personas/, parses each via DashboardSchema, returns
    a {id: DashboardSchema} dict.
  - The loader is called from main.py startup_event.
  - Failures (missing config dir, malformed YAML, schema validation
    error) raise loudly per A1 — no silent fallback to "no persona
    dashboards loaded."

B3 wires tile data to live cross-source DCL queries; for B1 the
DashboardSchema is the shell only.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict

import yaml
from pydantic import ValidationError

from src.nlq.models.dashboard_schema import DashboardSchema

logger = logging.getLogger(__name__)


_PERSONA_CONFIG_DIR = Path(__file__).resolve().parents[1] / "config" / "personas"


def load_persona_dashboards() -> Dict[str, DashboardSchema]:
    """Read every persona YAML and parse into DashboardSchema.

    Returns {id: DashboardSchema}. The id is taken from the YAML's `id`
    field, NOT the filename — operator can have multiple YAMLs for one
    persona variant if needed (e.g. finops.yaml + finops_lite.yaml).

    Raises:
      FileNotFoundError if the config directory itself is missing.
      ValidationError if any YAML fails DashboardSchema validation.
      yaml.YAMLError on malformed YAML.

    A1 compliance: failures raise loudly. Caller (main.py startup) can
    choose to catch and log if desired, but the default is fail-loud.
    """
    loaded: Dict[str, DashboardSchema] = {}
    # Per AAM Blueprint v3.1 decision (d): FinOps is a domain, not a persona.
    # finops.yaml — the lone file-based persona dashboard — was deleted, and
    # the persona-dashboard model is runtime-generated (the operator asks a
    # question, NLQ renders it as a dashboard). Zero file-based persona YAMLs
    # is therefore a valid state, not an error: a missing or empty personas
    # dir returns {} (no pre-populated persona dashboards). This is NOT a
    # silent fallback (A1) — there is genuinely nothing to load and dashboards
    # are served by the runtime path; the empty result is logged plainly.
    if not _PERSONA_CONFIG_DIR.exists():
        logger.info(
            "persona_dashboards: no personas dir at %s — no file-based persona "
            "dashboards (runtime-generated model).", _PERSONA_CONFIG_DIR,
        )
        return loaded
    yaml_files = sorted(_PERSONA_CONFIG_DIR.glob("*.yaml"))
    if not yaml_files:
        logger.info(
            "persona_dashboards: no persona YAMLs in %s — no file-based persona "
            "dashboards (runtime-generated model).", _PERSONA_CONFIG_DIR,
        )
        return loaded
    for path in yaml_files:
        with path.open() as f:
            raw = yaml.safe_load(f)
        if not isinstance(raw, dict):
            raise ValueError(
                f"persona_dashboards: {path.name} top-level must be a mapping "
                f"(got {type(raw).__name__})"
            )
        try:
            dashboard = DashboardSchema(**raw)
        except ValidationError as exc:
            raise ValidationError(
                f"persona_dashboards: {path.name} failed DashboardSchema validation: {exc}"
            ) from exc
        if dashboard.id in loaded:
            raise ValueError(
                f"persona_dashboards: duplicate id {dashboard.id!r} between "
                f"{path.name} and a previously loaded file"
            )
        loaded[dashboard.id] = dashboard
        logger.info(
            "persona_dashboards: loaded %s from %s (%d widgets)",
            dashboard.id, path.name, len(dashboard.widgets),
        )
    return loaded
