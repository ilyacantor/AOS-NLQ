"""WS-5 B3 — PersonaDashboardResolver wires tile data to AAM cross-source-query.

B3 invariants:
  1. PersonaDashboardResolver.resolve() returns {widget_id: data_dict}.
  2. KPI widget aggregates `amount` triples across all sources into one
     total + per-source provenance samples.
  3. Dimensional widgets (bar / donut) group by dimension and preserve
     per-bucket provenance.
  4. Special dimension 'source_system' groups by the provenance tag,
     not by a same-name property.
  5. Data-table widget reconstructs records by entity_id-joining
     triples and applies filters from the widget config.
  6. AAM_BASE_URL unset raises RuntimeError loudly at construction (A1).
  7. Missing source surfaces in widget.sources with missing_sources
     populated — does not silently drop.
  8. Per-widget failure does not nuke the whole dashboard — widget
     error surfaces in widget.error, other widgets still resolve.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("NLQ_ALLOW_NO_DCL", "1")
os.environ.setdefault("DCL_API_URL", "http://localhost:8104")

from src.nlq.models.dashboard_schema import (
    DashboardSchema, Widget, WidgetType,
    DataBinding, MetricBinding, DimensionBinding, TimeBinding, TimeGranularity,
    GridPosition,
)


def _widget(*, id, type, metric, dimension=None, period="Q3 2025", filters=None):
    data = DataBinding(
        metrics=[MetricBinding(metric=metric)],
        dimensions=[DimensionBinding(dimension=dimension)] if dimension else [],
        time=TimeBinding(period=period, granularity=TimeGranularity.QUARTERLY),
        filters=filters or {},
    )
    return Widget(
        id=id, type=type, title=id, data=data,
        position=GridPosition(column=1, row=1, col_span=4, row_span=2),
    )


def _mock_aam_response(triples, missing=None, sources=None):
    return {
        "domain": "invoice",
        "period": "Q3 2025",
        "sources": sources or {"NetSuite": {"vendor": "workato", "batch_id": "b1"},
                                "Sage Intacct": {"vendor": "boomi", "batch_id": "b2"}},
        "missing_sources": missing or [],
        "triples": triples,
        "count": len(triples),
    }


def _triple(*, entity_id, prop, value, source_system="NetSuite", source_field=None):
    return {
        "entity_id": entity_id, "property": prop, "value": value,
        "concept": "invoice", "period": "Q3 2025",
        "source_system": source_system,
        "source_field": source_field or prop,
        "pipe_id": f"pipe-{source_system.lower().replace(' ','_')}",
        "fabric_plane": "workato" if source_system == "NetSuite" else "boomi",
        "confidence_score": 0.95,
        "_source_system_display": source_system,
        "_vendor": "workato" if source_system == "NetSuite" else "boomi",
        "_batch_id": "b1" if source_system == "NetSuite" else "b2",
    }


def test_constructor_requires_aam_base_url():
    """A1: missing AAM_BASE_URL raises at construction, not at first call."""
    from src.nlq.services.persona_dashboard_resolver import PersonaDashboardResolver
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("AAM_BASE_URL", None)
        with pytest.raises(RuntimeError, match="AAM_BASE_URL not set"):
            PersonaDashboardResolver()


@patch("src.nlq.services.persona_dashboard_resolver.httpx.Client")
def test_kpi_widget_sums_across_sources(mock_httpx):
    from src.nlq.services.persona_dashboard_resolver import PersonaDashboardResolver
    triples = [
        _triple(entity_id="INV-1", prop="amount", value="1000", source_system="NetSuite"),
        _triple(entity_id="INV-2", prop="amount", value="2500", source_system="NetSuite"),
        _triple(entity_id="INV-A", prop="amount", value="500", source_system="Sage Intacct"),
    ]
    client = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value=_mock_aam_response(triples))
    client.get = MagicMock(return_value=response)
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    mock_httpx.return_value = client

    schema = DashboardSchema(
        id="persona_finops", title="x", source_query="x",
        widgets=[_widget(id="total_kpi", type=WidgetType.KPI_CARD, metric="ar_outstanding_usd")],
    )
    resolver = PersonaDashboardResolver(aam_base_url="http://test")
    data = resolver.resolve(schema)
    assert data["total_kpi"]["value"] == 4000.0
    samples = data["total_kpi"]["provenance_samples"]
    assert "NetSuite" in samples
    assert "Sage Intacct" in samples
    assert samples["NetSuite"]["source_system"] == "NetSuite"


@patch("src.nlq.services.persona_dashboard_resolver.httpx.Client")
def test_dimensional_widget_groups_by_property_dimension(mock_httpx):
    """Bar chart on aging_bucket: triples are amount + aging_bucket per
    invoice; resolver joins by entity_id."""
    from src.nlq.services.persona_dashboard_resolver import PersonaDashboardResolver
    triples = [
        _triple(entity_id="INV-1", prop="amount", value="1000"),
        _triple(entity_id="INV-1", prop="aging_bucket", value="30-60"),
        _triple(entity_id="INV-2", prop="amount", value="2500"),
        _triple(entity_id="INV-2", prop="aging_bucket", value="90+"),
        _triple(entity_id="INV-3", prop="amount", value="500"),
        _triple(entity_id="INV-3", prop="aging_bucket", value="30-60"),
    ]
    client = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value=_mock_aam_response(triples))
    client.get = MagicMock(return_value=response)
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    mock_httpx.return_value = client

    schema = DashboardSchema(
        id="persona_finops", title="x", source_query="x",
        widgets=[_widget(id="aging_bar", type=WidgetType.BAR_CHART,
                          metric="ar_outstanding_usd", dimension="aging_bucket")],
    )
    resolver = PersonaDashboardResolver(aam_base_url="http://test")
    data = resolver.resolve(schema)
    breakdown = data["aging_bar"]["breakdown"]
    by_label = {b["label"]: b["value"] for b in breakdown}
    assert by_label["30-60"] == 1500.0  # 1000 + 500
    assert by_label["90+"] == 2500.0
    # Provenance preserved on each bucket
    for row in breakdown:
        assert row.get("provenance") is not None


@patch("src.nlq.services.persona_dashboard_resolver.httpx.Client")
def test_donut_widget_groups_by_source_system(mock_httpx):
    """source_system is a provenance tag, not a property — resolver
    must use the special-case grouping path."""
    from src.nlq.services.persona_dashboard_resolver import PersonaDashboardResolver
    triples = [
        _triple(entity_id="INV-1", prop="amount", value="1000", source_system="NetSuite"),
        _triple(entity_id="INV-2", prop="amount", value="2500", source_system="NetSuite"),
        _triple(entity_id="INV-A", prop="amount", value="500", source_system="Sage Intacct"),
    ]
    client = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value=_mock_aam_response(triples))
    client.get = MagicMock(return_value=response)
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    mock_httpx.return_value = client

    schema = DashboardSchema(
        id="persona_finops", title="x", source_query="x",
        widgets=[_widget(id="source_donut", type=WidgetType.DONUT_CHART,
                          metric="ar_outstanding_usd", dimension="source_system")],
    )
    resolver = PersonaDashboardResolver(aam_base_url="http://test")
    data = resolver.resolve(schema)
    breakdown = data["source_donut"]["breakdown"]
    by_label = {b["label"]: b["value"] for b in breakdown}
    assert by_label["NetSuite"] == 3500.0
    assert by_label["Sage Intacct"] == 500.0


@patch("src.nlq.services.persona_dashboard_resolver.httpx.Client")
def test_table_widget_filters_by_widget_config(mock_httpx):
    """Data-table widget with filter aging_bucket='90+' returns only
    overdue invoices."""
    from src.nlq.services.persona_dashboard_resolver import PersonaDashboardResolver
    triples = [
        _triple(entity_id="INV-1", prop="amount", value="1000"),
        _triple(entity_id="INV-1", prop="aging_bucket", value="30-60"),
        _triple(entity_id="INV-1", prop="customer_name", value="ACME"),
        _triple(entity_id="INV-2", prop="amount", value="2500"),
        _triple(entity_id="INV-2", prop="aging_bucket", value="90+"),
        _triple(entity_id="INV-2", prop="customer_name", value="Globex"),
    ]
    client = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value=_mock_aam_response(triples))
    client.get = MagicMock(return_value=response)
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    mock_httpx.return_value = client

    schema = DashboardSchema(
        id="persona_finops", title="x", source_query="x",
        widgets=[Widget(
            id="overdue_table", type=WidgetType.DATA_TABLE, title="x",
            data=DataBinding(
                metrics=[MetricBinding(metric="invoice_amount_usd")],
                dimensions=[
                    DimensionBinding(dimension="customer_name"),
                    DimensionBinding(dimension="aging_bucket"),
                ],
                filters={"aging_bucket": "90+"},
            ),
            position=GridPosition(column=1, row=1, col_span=4, row_span=2),
        )],
    )
    resolver = PersonaDashboardResolver(aam_base_url="http://test")
    data = resolver.resolve(schema)
    rows = data["overdue_table"]["rows"]
    assert len(rows) == 1
    assert rows[0]["customer_name"] == "Globex"
    assert rows[0]["amount"] == "2500"
    assert rows[0]["provenance"] is not None


@patch("src.nlq.services.persona_dashboard_resolver.httpx.Client")
def test_missing_sources_surfaces_per_widget(mock_httpx):
    """When AAM reports a missing source, the widget keeps the
    missing_sources list visible — operator sees the gap."""
    from src.nlq.services.persona_dashboard_resolver import PersonaDashboardResolver
    client = MagicMock()
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json = MagicMock(return_value=_mock_aam_response(
        triples=[_triple(entity_id="INV-1", prop="amount", value="100")],
        missing=["Sage Intacct"],
        sources={"NetSuite": {"vendor": "workato", "batch_id": "b1"}},
    ))
    client.get = MagicMock(return_value=response)
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    mock_httpx.return_value = client

    schema = DashboardSchema(
        id="persona_finops", title="x", source_query="x",
        widgets=[_widget(id="kpi", type=WidgetType.KPI_CARD, metric="ar_outstanding_usd")],
    )
    resolver = PersonaDashboardResolver(aam_base_url="http://test")
    data = resolver.resolve(schema)
    assert data["kpi"]["missing_sources"] == ["Sage Intacct"]
    assert "NetSuite" in data["kpi"]["sources"]


@patch("src.nlq.services.persona_dashboard_resolver.httpx.Client")
def test_per_widget_failure_isolated(mock_httpx):
    """One failing widget should not nuke other widgets in the same
    dashboard. The failure surfaces in widget.error."""
    from src.nlq.services.persona_dashboard_resolver import PersonaDashboardResolver
    call_count = {"n": 0}

    def _client_factory(*args, **kwargs):
        client = MagicMock()
        def _get(url, params=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # First widget raises mid-call
                raise RuntimeError("simulated AAM 500")
            response = MagicMock()
            response.raise_for_status = MagicMock()
            response.json = MagicMock(return_value=_mock_aam_response(
                triples=[_triple(entity_id="INV-1", prop="amount", value="100")],
            ))
            return response
        client.get = _get
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        return client
    mock_httpx.side_effect = _client_factory

    schema = DashboardSchema(
        id="persona_finops", title="x", source_query="x",
        widgets=[
            _widget(id="kpi1", type=WidgetType.KPI_CARD, metric="ar_outstanding_usd"),
            _widget(id="kpi2", type=WidgetType.KPI_CARD, metric="ar_outstanding_usd"),
        ],
    )
    resolver = PersonaDashboardResolver(aam_base_url="http://test")
    data = resolver.resolve(schema)
    assert "error" in data["kpi1"]
    assert data["kpi2"].get("value") == 100.0  # second widget succeeded


def test_unknown_metric_surfaces_per_widget():
    """A metric name with no domain mapping must surface as a widget
    error, not crash the resolver."""
    from src.nlq.services.persona_dashboard_resolver import PersonaDashboardResolver
    schema = DashboardSchema(
        id="persona_finops", title="x", source_query="x",
        widgets=[_widget(id="kpi", type=WidgetType.KPI_CARD,
                          metric="not_a_real_metric")],
    )
    resolver = PersonaDashboardResolver(aam_base_url="http://test")
    data = resolver.resolve(schema)
    assert "no domain mapping" in data["kpi"]["error"]
