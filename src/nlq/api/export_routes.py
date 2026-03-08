"""
Excel export endpoints for AOS-NLQ.

GET /export/financial-statement — generates .xlsx from session-stored financial statement data.
GET /export/bridge — generates .xlsx from session-stored bridge chart data.
"""

import io
import logging
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse, JSONResponse

from src.nlq.api.session import get_dashboard_session_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["export"])


def _get_openpyxl():
    """Import openpyxl or return None with error response."""
    try:
        import openpyxl
        from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
        from openpyxl.utils import get_column_letter
        return openpyxl
    except ImportError:
        return None


@router.get("/export/financial-statement")
async def export_financial_statement(
    session_id: str = Query(..., description="Browser session ID"),
    format: str = Query(default="xlsx", description="Export format (only 'xlsx' supported)"),
):
    """Export the most recent financial statement as an Excel file."""
    if format != "xlsx":
        return JSONResponse(
            status_code=400,
            content={"error": f"Unsupported format '{format}'. Only 'xlsx' is supported."},
        )

    store = get_dashboard_session_store()
    fs_data = store.get_financial_statement(session_id)
    if not fs_data:
        return JSONResponse(
            status_code=404,
            content={
                "error": "No financial statement found for this session. "
                "Submit a P&L query first (e.g., 'show me the P&L').",
                "session_id": session_id,
            },
        )

    openpyxl = _get_openpyxl()
    if not openpyxl:
        logger.error("openpyxl not installed — cannot generate Excel export")
        return JSONResponse(
            status_code=500,
            content={"error": "Excel export requires openpyxl. Install with: pip install openpyxl"},
        )

    from openpyxl.styles import Font, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    title = fs_data.get("title", "Income Statement")
    entity = fs_data.get("entity", "")
    periods = fs_data.get("periods", [])
    line_items = fs_data.get("line_items", [])
    unit = fs_data.get("unit", "millions")

    num_cols = 1 + len(periods)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Income Statement"
    ws.sheet_view.showGridLines = False

    ws.column_dimensions["A"].width = 32
    for i, _ in enumerate(periods):
        ws.column_dimensions[get_column_letter(i + 2)].width = 14

    title_font = Font(name="Calibri", size=14, bold=True)
    subtitle_font = Font(name="Calibri", size=10, color="808080", italic=True)
    header_font = Font(name="Calibri", size=10, bold=True)
    header_border = Border(bottom=Side(style="medium"))
    subtotal_font = Font(name="Calibri", size=10, bold=True)
    subtotal_border = Border(top=Side(style="thin"))
    currency_format = '#,##0.0;(#,##0.0);"-"'
    percent_format = '0.0%;(0.0%);"-"'

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=num_cols)
    ws.cell(row=1, column=1, value=f"{title} — {entity}").font = title_font

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=num_cols)
    sub_cell = ws.cell(row=2, column=1, value=f"All amounts in ${unit[0].upper()} unless noted")
    sub_cell.font = subtitle_font
    sub_cell.alignment = Alignment(horizontal="right")

    ws.cell(row=3, column=1, value="").font = header_font
    ws.cell(row=3, column=1).border = header_border
    for i, period in enumerate(periods):
        cell = ws.cell(row=3, column=i + 2, value=period)
        cell.font = header_font
        cell.alignment = Alignment(horizontal="right")
        cell.border = header_border

    for row_idx, item in enumerate(line_items, start=4):
        label = item.get("label", "")
        indent = item.get("indent", 0)
        fmt = item.get("format", "currency")
        is_subtotal = item.get("is_subtotal", False)
        item_values = item.get("values", {})

        label_text = ("    " * indent) + label
        label_cell = ws.cell(row=row_idx, column=1, value=label_text)
        if is_subtotal:
            label_cell.font = subtotal_font
            label_cell.border = subtotal_border

        for col_idx, period in enumerate(periods):
            val = item_values.get(period)
            cell = ws.cell(row=row_idx, column=col_idx + 2)
            cell.alignment = Alignment(horizontal="right")
            if val is not None:
                if fmt == "percent":
                    cell.value = val / 100.0
                    cell.number_format = percent_format
                else:
                    cell.value = val
                    cell.number_format = currency_format
            else:
                cell.value = "--"
            if is_subtotal:
                cell.font = subtotal_font
                cell.border = subtotal_border

    ws.freeze_panes = "B4"

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="income_statement.xlsx"'},
    )


@router.get("/export/bridge")
async def export_bridge(
    session_id: str = Query(..., description="Browser session ID"),
    format: str = Query(default="xlsx", description="Export format (only 'xlsx' supported)"),
):
    """Export the most recent bridge chart as an Excel file with data table and chart."""
    if format != "xlsx":
        return JSONResponse(
            status_code=400,
            content={"error": f"Unsupported format '{format}'. Only 'xlsx' is supported."},
        )

    store = get_dashboard_session_store()
    bridge_data = store.get_bridge_chart(session_id)
    if not bridge_data:
        return JSONResponse(
            status_code=404,
            content={
                "error": "No bridge chart found for this session. "
                "Submit a revenue bridge query first (e.g., 'why did revenue increase').",
                "session_id": session_id,
            },
        )

    openpyxl = _get_openpyxl()
    if not openpyxl:
        logger.error("openpyxl not installed — cannot generate Excel export")
        return JSONResponse(
            status_code=500,
            content={"error": "Excel export requires openpyxl. Install with: pip install openpyxl"},
        )

    from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.chart import BarChart, Reference
    from openpyxl.chart.series import DataPoint
    from openpyxl.chart.label import DataLabelList

    title = bridge_data.get("title", "Revenue Bridge")
    bars = bridge_data.get("bars", [])
    period_start = bridge_data.get("period_start", "FY 2024")
    period_end = bridge_data.get("period_end", "FY 2025")

    # Extract driver bars (not totals) for the data table
    driver_bars = [b for b in bars if b.get("type") != "total"]
    start_bar = next((b for b in bars if b.get("type") == "total"), None)
    end_bar = None
    for b in reversed(bars):
        if b.get("type") == "total" and b != start_bar:
            end_bar = b
            break

    wb = openpyxl.Workbook()

    # ── Sheet 1: Data Table ───────────────────────────────────────────
    ws = wb.active
    ws.title = "Revenue Bridge Data"
    ws.sheet_view.showGridLines = False

    title_font = Font(name="Calibri", size=14, bold=True)
    subtitle_font = Font(name="Calibri", size=10, color="808080", italic=True)
    header_font = Font(name="Calibri", size=10, bold=True)
    header_border = Border(bottom=Side(style="medium"))
    total_font = Font(name="Calibri", size=10, bold=True)
    total_border = Border(top=Side(style="thin"))
    currency_format = '#,##0.0;(#,##0.0);"-"'
    green_font = Font(name="Calibri", size=10, color="059669")
    red_font = Font(name="Calibri", size=10, color="DC2626")

    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 14

    # Title
    ws.merge_cells("A1:D1")
    ws.cell(row=1, column=1, value=title).font = title_font
    ws.merge_cells("A2:D2")
    ws.cell(row=2, column=1, value="All amounts in $M").font = subtitle_font

    # Headers
    headers = ["Driver", period_start, period_end, "Change"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=3, column=col, value=h)
        cell.font = header_font
        cell.border = header_border
        if col > 1:
            cell.alignment = Alignment(horizontal="right")

    # We need to reconstruct per-period driver values from the bridge data
    # The bridge_data has bars with deltas, but for the table we need start/end values
    # We'll query from the bars: start total, driver deltas, end total
    # For a proper table, we need the underlying per-year values
    # These are embedded in the bridge calculation — let's derive from bars

    # Driver rows
    row = 4
    start_val = start_bar.get("value") if start_bar else None
    end_val = end_bar.get("value") if end_bar else None

    # Map driver labels to their bars — we'll show the delta and derive start/end
    running = start_val if start_val is not None else 0
    for bar in driver_bars:
        label = bar.get("label", "")
        delta = bar.get("value")
        bar_running = bar.get("running_total")

        ws.cell(row=row, column=1, value=label)

        # We can't perfectly reconstruct per-year values without the original data,
        # but we have the delta and running total. Show delta in the Change column.
        # For FY columns, show running totals before/after this driver.
        if delta is not None:
            prev_running = round(bar_running - delta, 1) if bar_running is not None else None

            # Column D: Change (delta)
            change_cell = ws.cell(row=row, column=4, value=delta)
            change_cell.number_format = '+#,##0.0;-#,##0.0;"-"'
            change_cell.alignment = Alignment(horizontal="right")
            if delta >= 0:
                change_cell.font = green_font
            else:
                change_cell.font = red_font
        else:
            ws.cell(row=row, column=4, value="N/A").alignment = Alignment(horizontal="right")

        row += 1

    # Total row
    ws.cell(row=row, column=1, value="Total Revenue").font = total_font
    ws.cell(row=row, column=1).border = total_border

    if start_val is not None:
        c = ws.cell(row=row, column=2, value=start_val)
        c.number_format = currency_format
        c.alignment = Alignment(horizontal="right")
        c.font = total_font
        c.border = total_border

    if end_val is not None:
        c = ws.cell(row=row, column=3, value=end_val)
        c.number_format = currency_format
        c.alignment = Alignment(horizontal="right")
        c.font = total_font
        c.border = total_border

    if start_val is not None and end_val is not None:
        total_change = round(end_val - start_val, 1)
        c = ws.cell(row=row, column=4, value=total_change)
        c.number_format = '+#,##0.0;-#,##0.0;"-"'
        c.alignment = Alignment(horizontal="right")
        c.font = Font(name="Calibri", size=10, bold=True, color="059669" if total_change >= 0 else "DC2626")
        c.border = total_border

    ws.freeze_panes = "A4"

    # ── Sheet 2: Waterfall Chart ──────────────────────────────────────
    ws2 = wb.create_sheet("Waterfall Chart")
    ws2.sheet_view.showGridLines = False

    # Build chart data: stacked bar with invisible base + visible value
    # Columns: Label | Base (invisible) | Value (visible)
    ws2.cell(row=1, column=1, value="Label")
    ws2.cell(row=1, column=2, value="Base")
    ws2.cell(row=1, column=3, value="Value")

    for i, bar in enumerate(bars, start=2):
        label = bar.get("label", "")
        value = bar.get("value")
        running = bar.get("running_total")
        bar_type = bar.get("type", "")

        ws2.cell(row=i, column=1, value=label)

        if bar_type == "total":
            ws2.cell(row=i, column=2, value=0)
            ws2.cell(row=i, column=3, value=value if value is not None else 0)
        else:
            if value is not None and running is not None:
                base = running - value if value >= 0 else running
                vis = abs(value)
                ws2.cell(row=i, column=2, value=round(base, 1))
                ws2.cell(row=i, column=3, value=round(vis, 1))
            else:
                ws2.cell(row=i, column=2, value=0)
                ws2.cell(row=i, column=3, value=0)

    num_bars = len(bars)

    try:
        chart = BarChart()
        chart.type = "bar"
        chart.style = 10
        chart.title = title
        chart.y_axis.title = None
        chart.x_axis.title = None
        chart.width = 20
        chart.height = 12
        chart.legend = None

        # Base series (invisible)
        base_data = Reference(ws2, min_col=2, min_row=1, max_row=num_bars + 1)
        base_cats = Reference(ws2, min_col=1, min_row=2, max_row=num_bars + 1)
        chart.add_data(base_data, titles_from_data=True)
        chart.set_categories(base_cats)

        # Value series (visible)
        val_data = Reference(ws2, min_col=3, min_row=1, max_row=num_bars + 1)
        chart.add_data(val_data, titles_from_data=True)

        chart.grouping = "stacked"

        # Make base series invisible
        base_series = chart.series[0]
        base_series.graphicalProperties.noFill = True
        base_series.graphicalProperties.line.noFill = True

        # Color the value series bars
        from openpyxl.chart.series import DataPoint
        from openpyxl.drawing.fill import PatternFillProperties, ColorChoice
        val_series = chart.series[1]

        for i, bar in enumerate(bars):
            pt = DataPoint(idx=i)
            bar_type = bar.get("type", "")
            value = bar.get("value")
            if bar_type == "total":
                pt.graphicalProperties.solidFill = "6B7280"  # gray
            elif value is not None and value >= 0:
                pt.graphicalProperties.solidFill = "10B981"  # green
            else:
                pt.graphicalProperties.solidFill = "EF4444"  # red
            val_series.data_points.append(pt)

        # Add data labels to value series
        val_series.dLbls = DataLabelList()
        val_series.dLbls.showVal = True
        val_series.dLbls.numFmt = '#,##0.0'

        ws2.add_chart(chart, "E2")
    except Exception as e:
        # Chart failed — log but still return the workbook with the data table
        logger.warning(f"Bridge Excel chart generation failed (data table still included): {e}")

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="revenue_bridge.xlsx"'},
    )
