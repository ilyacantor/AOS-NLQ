import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { createPortal } from "react-dom";
import { fetchReport, fetchDimensionalDetail, fetchReconciliation, fetchCombiningStatement, fetchOverlapData, fetchCrossSell, fetchRevenueByCustomer, fetchEBITDABridge, fetchWhatIf, fetchQofE, fetchDashboard, sendMaestraChat, fetchReportDimensions, fetchPipelineReport } from "./api";
import type { PeriodDimension, DimensionalDetailResponse, DimensionalSection } from "./api";
import React from "react";
import type { ReportData, ReconReport, ReconCheck, ReconCoverage, ReportVariant, EntitySelection, CombiningStatementData, OverlapData, CrossSellData, RevenueByCustomerData, EBITDABridgeData, BridgeAdjustment, WhatIfResult, QofEData, DashboardData, DashboardPersona, FinancialStatementData, FinancialStatementLineItem, PipelineReportData } from "./types";

const SalesFunnel = React.lazy(() => import("../sales-funnel/SalesFunnel"));

// ============================================================
// FORMATTING
// ============================================================
function fmt(n: number | null | undefined, isPercent = false): string {
  if (n === null || n === undefined) return "";
  if (isPercent) return n.toFixed(1) + "%";
  const abs = Math.abs(n);
  const s = abs.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  return n < 0 ? `(${s})` : s;
}

function fmtFull(n: number | null | undefined): string {
  if (n === null || n === undefined) return "";
  const abs = Math.abs(n);
  const s = abs.toLocaleString("en-US", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  });
  return n < 0 ? `($${s})` : `$${s}`;
}

function variancePct(act: number, py: number): string {
  if (!py || py === 0) return "\u2014";
  const pct = ((act - py) / Math.abs(py)) * 100;
  return (pct >= 0 ? "+" : "") + pct.toFixed(1) + "%";
}

function fmtDollar(n: number | null | undefined): string {
  if (n === null || n === undefined || n === 0) return "\u2014";
  // DCL returns all financial values in $M. Auto-scale for display.
  const absM = Math.abs(n);
  let formatted: string;
  if (absM >= 1000) {
    const b = absM / 1000;
    formatted = `$${b.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}B`;
  } else if (absM >= 0.1) {
    const mDec = absM < 10 ? 1 : 0;
    formatted = `$${absM.toLocaleString("en-US", { minimumFractionDigits: mDec, maximumFractionDigits: mDec })}M`;
  } else {
    const k = absM * 1000;
    formatted = `$${k.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}K`;
  }
  return n < 0 ? `(${formatted})` : formatted;
}

function fmtScore(n: number): string {
  if (n >= 80) return "HIGH";
  if (n >= 60) return "MED";
  return "LOW";
}

function confidenceColor(c: string): string {
  if (c === "high") return COLORS.green;
  if (c === "medium") return COLORS.accent;
  return COLORS.red;
}

// ============================================================
// CONSTANTS
// ============================================================
// QUARTERS and SEGMENTS are now fetched dynamically from /api/v1/report-dimensions
const SEGMENTS_FALLBACK = ["Strategy", "Operations", "Technology", "Risk", "Digital/AI", "Commercial"];

function wallClockDate() { return new Date(); }

const COLORS = {
  bg: "#0F1117",
  surface: "#181B25",
  surfaceHover: "#1E2230",
  border: "#2A2E3B",
  borderLight: "#353945",
  text: "#E8E9ED",
  textMuted: "#8B8F9E",
  textDim: "#5A5E6E",
  accent: "#C77840",
  accentLight: "#D4915A",
  green: "#4CAF50",
  greenBg: "rgba(76,175,80,0.08)",
  red: "#EF5350",
  redBg: "rgba(239,83,80,0.08)",
  blue: "#5B8DEF",
  highlight: "rgba(199,120,64,0.06)",
  headerBg: "#141720",
  totalBg: "rgba(255,255,255,0.02)",
};

const CONTENT_MAX_WIDTH = 1024;

// ============================================================
// VARIANT MAPPING — portal variant keys → API ReportVariant
// ============================================================
function mapVariant(v: string): ReportVariant {
  switch (v) {
    case "act_vs_py": return "full_year_act_vs_py";
    case "q_act_vs_py": return "quarterly_act_vs_py";
    case "cf_vs_py": return "full_year_cf_vs_py_act";
    case "q_cf_vs_py": return "quarterly_cf_vs_py";
    case "quarterly": return "quarterly_act_vs_py";
    default: return "full_year_act_vs_py";
  }
}

function tabToStatement(tab: string): "income_statement" | "balance_sheet" | "cash_flow" {
  if (tab === "bs") return "balance_sheet";
  if (tab === "cf") return "cash_flow";
  return "income_statement";
}

// ============================================================
// SUB-COMPONENTS
// ============================================================

interface SelectProps {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  label?: string;
  width?: number;
}

function Select({ value, onChange, options, label, width = 180 }: SelectProps) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {label && (
        <span style={{ fontSize: 15, color: COLORS.textMuted, letterSpacing: "0.05em", textTransform: "uppercase", fontFamily: "'JetBrains Mono',monospace" }}>
          {label}
        </span>
      )}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          width, padding: "8px 12px", background: COLORS.surface, color: COLORS.text, border: `1px solid ${COLORS.border}`,
          borderRadius: 6, fontSize: 15, fontFamily: "'IBM Plex Sans',sans-serif", cursor: "pointer", outline: "none",
          appearance: "none" as const,
          backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%238B8F9E' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E")`,
          backgroundRepeat: "no-repeat", backgroundPosition: "right 10px center", paddingRight: 30,
        }}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}

function TabBar({ tabs, active, onChange, noBorder }: { tabs: { id: string; label: string; title?: string }[]; active: string; onChange: (id: string) => void; noBorder?: boolean }) {
  return (
    <div style={{ position: "relative", flex: 1, minWidth: 0 }}>
      <div style={{
        display: "flex", gap: 2,
        borderBottom: noBorder ? "none" : `1px solid ${COLORS.border}`,
        overflowX: "auto", scrollbarWidth: "none", msOverflowStyle: "none" as any,
      }}>
        {tabs.map((t) => (
          <button key={t.id} onClick={() => onChange(t.id)} title={t.title || t.label} style={{
            padding: "8px 14px", background: active === t.id ? COLORS.surface : "transparent",
            color: active === t.id ? COLORS.accent : COLORS.textMuted, border: "none",
            borderBottom: active === t.id ? `2px solid ${COLORS.accent}` : "2px solid transparent",
            cursor: "pointer", fontSize: 15, fontFamily: "'IBM Plex Sans',sans-serif",
            fontWeight: active === t.id ? 600 : 400, transition: "all 0.15s", letterSpacing: "0.02em",
            whiteSpace: "nowrap",
          }}>
            {t.label}
          </button>
        ))}
      </div>
      <div style={{
        position: "absolute", right: 0, top: 0, bottom: 0, width: 40,
        background: `linear-gradient(to right, transparent, ${COLORS.headerBg})`,
        pointerEvents: "none",
      }} />
    </div>
  );
}

function unitLabel(unit?: string): string {
  if (!unit) return "";
  const u = unit.toLowerCase();
  if (u === "millions") return "($MM)";
  if (u === "billions") return "($BN)";
  if (u === "thousands") return "($K)";
  return `(${unit})`;
}

function StatementTable({ data, pyData, showVariance = true, onDrillLine }: { data: ReportData | null; pyData: ReportData | null; showVariance?: boolean; onDrillLine?: (lineId: string, lineName: string) => void }) {
  if (!data) return null;
  const denomLabel = unitLabel(data.metadata.unit);
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "'IBM Plex Mono','JetBrains Mono',monospace", fontSize: 15 }}>
        <thead>
          <tr style={{ borderBottom: `2px solid ${COLORS.accent}` }}>
            <th style={{ textAlign: "left", padding: "10px 16px", color: COLORS.textMuted, fontWeight: 500, width: "40%", fontSize: 15, letterSpacing: "0.06em", textTransform: "uppercase" }}>
              {denomLabel && <span style={{ fontWeight: 400, fontSize: 14, fontStyle: "italic", letterSpacing: "0.04em", color: COLORS.textDim }}>{denomLabel}</span>}
            </th>
            <th style={{ textAlign: "right", padding: "10px 16px", color: COLORS.textMuted, fontWeight: 500, fontSize: 15, letterSpacing: "0.06em", textTransform: "uppercase" }}>
              {data.metadata.periodType === "forecast" ? "CF " : ""}{data.metadata.quarter}
            </th>
            {showVariance && pyData && (
              <>
                <th style={{ textAlign: "right", padding: "10px 16px", color: COLORS.textMuted, fontWeight: 500, fontSize: 15, letterSpacing: "0.06em", textTransform: "uppercase" }}>PY</th>
                <th style={{ textAlign: "right", padding: "10px 16px", color: COLORS.textMuted, fontWeight: 500, fontSize: 15, letterSpacing: "0.06em", textTransform: "uppercase" }}>Var $</th>
                <th style={{ textAlign: "right", padding: "10px 16px", color: COLORS.textMuted, fontWeight: 500, fontSize: 15, letterSpacing: "0.06em", textTransform: "uppercase" }}>Var %</th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {data.lines.map((line, i) => {
            const pyLine = pyData?.lines?.[i];
            const varAmt = line.amount !== null && pyLine?.amount !== null && pyLine?.amount !== undefined ? line.amount - pyLine.amount : null;
            const isNeg = varAmt !== null && varAmt < 0;
            const rowBg = line.isTotal ? COLORS.totalBg : line.highlight ? COLORS.highlight : "transparent";
            const canDrill = line.drillable && onDrillLine;
            return (
              <tr key={line.id} style={{
                borderBottom: line.isFinal ? `2px double ${COLORS.accent}` : line.isTotal ? `1px solid ${COLORS.borderLight}` : `1px solid ${COLORS.border}22`,
                background: rowBg,
                cursor: canDrill ? "pointer" : "default",
              }}
                onClick={() => { if (canDrill) onDrillLine(line.id, line.name); }}
              >
                <td style={{
                  padding: line.isHeader ? "14px 16px 6px" : "8px 16px",
                  paddingLeft: line.level === 1 ? 40 : 16,
                  color: line.isHeader ? COLORS.accent : line.bold ? COLORS.text : line.isPercent ? COLORS.textMuted : COLORS.text,
                  fontWeight: line.bold || line.isHeader ? 600 : 400,
                  fontSize: line.isHeader ? 14 : 15,
                  letterSpacing: line.isHeader ? "0.06em" : "0",
                  textTransform: line.isHeader ? "uppercase" as const : "none" as const,
                  fontFamily: "'IBM Plex Sans',sans-serif",
                  cursor: canDrill ? "pointer" : "default",
                }}>
                  {canDrill && <span style={{ color: COLORS.accent, marginRight: 6, fontSize: 14 }}>{"\u25B8"}</span>}
                  {line.name}
                  {line.highlight && <span style={{ marginLeft: 8, fontSize: 14, color: COLORS.accent, background: "rgba(199,120,64,0.12)", padding: "2px 6px", borderRadius: 3 }}>SYNERGY</span>}
                </td>
                <td style={{ textAlign: "right", padding: "8px 16px", color: line.isPercent ? COLORS.textMuted : COLORS.text, fontWeight: line.bold ? 600 : 400 }}>
                  {line.isHeader ? "" : fmt(line.amount, line.isPercent)}
                  {data.metadata.periodType === "forecast" && !line.isHeader && !line.isPercent && (
                    <span style={{ marginLeft: 4, fontSize: 11, color: COLORS.textDim }}>CF</span>
                  )}
                </td>
                {showVariance && pyData && (
                  <>
                    <td style={{ textAlign: "right", padding: "8px 16px", color: COLORS.textMuted }}>
                      {line.isHeader ? "" : fmt(pyLine?.amount, line.isPercent)}
                    </td>
                    <td style={{ textAlign: "right", padding: "8px 16px", color: varAmt === null ? COLORS.textDim : isNeg ? COLORS.red : COLORS.green }}>
                      {line.isHeader || line.isPercent || varAmt === null ? "" : fmt(varAmt)}
                    </td>
                    <td style={{ textAlign: "right", padding: "8px 16px", color: varAmt === null ? COLORS.textDim : isNeg ? COLORS.red : COLORS.green }}>
                      {line.isHeader || line.isPercent || !pyLine?.amount ? "" : variancePct(line.amount!, pyLine.amount)}
                    </td>
                  </>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ============================================================
// DIMENSIONAL DETAIL (drill-through for P&L line items)
// ============================================================

function DimensionTable({ section }: { section: DimensionalSection }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 11, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6, fontFamily: "'JetBrains Mono',monospace" }}>{section.name}</div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "'IBM Plex Mono',monospace", fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
            <th style={{ textAlign: "left", padding: "8px 12px", color: COLORS.textMuted, fontWeight: 500, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>Name</th>
            <th style={{ textAlign: "right", padding: "8px 12px", color: COLORS.textMuted, fontWeight: 500, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>Amount</th>
            <th style={{ textAlign: "right", padding: "8px 12px", color: COLORS.textMuted, fontWeight: 500, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>% of Total</th>
          </tr>
        </thead>
        <tbody>
          {section.items.map((item) => (
            <tr key={item.property} style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
              <td style={{ padding: "8px 12px", color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif", fontSize: 13 }}>{item.property}</td>
              <td style={{ textAlign: "right", padding: "8px 12px", color: COLORS.text }}>{fmtFull(item.value)}</td>
              <td style={{ textAlign: "right", padding: "8px 12px", color: COLORS.textMuted }}>{item.pct_of_total !== null ? item.pct_of_total.toFixed(1) + "%" : "\u2014"}</td>
            </tr>
          ))}
          <tr style={{ borderTop: `2px solid ${COLORS.accent}`, background: COLORS.totalBg }}>
            <td style={{ padding: "8px 12px", fontWeight: 600, color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif", fontSize: 13 }}>Total</td>
            <td style={{ textAlign: "right", padding: "8px 12px", fontWeight: 600, color: COLORS.text }}>{fmtFull(section.total)}</td>
            <td style={{ textAlign: "right", padding: "8px 12px", fontWeight: 600, color: COLORS.textMuted }}>100.0%</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function DimensionalDetail({ lineKey, lineName, entityId, period, fsData, onClose }: {
  lineKey: string; lineName: string; entityId: string; period: string;
  fsData: FinancialStatementData; onClose: () => void;
}) {
  const [dimData, setDimData] = useState<DimensionalDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchDimensionalDetail(lineKey, entityId, period)
      .then((data) => { if (!cancelled) setDimData(data); })
      .catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : String(err)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [lineKey, entityId, period]);

  // Fallback: component breakdown from FS data (for lines without dimensional triples)
  const lineItem = fsData.line_items.find((li) => li.key === lineKey);
  const children: FinancialStatementLineItem[] = [];
  if (lineItem) {
    const idx = fsData.line_items.indexOf(lineItem);
    const periods = fsData.periods.filter((p) => !p.toLowerCase().includes('variance'));
    if (lineItem.is_subtotal) {
      for (let i = idx - 1; i >= 0; i--) {
        const li = fsData.line_items[i];
        if (li.is_subtotal || (li.indent === 0 && !li.key)) break;
        if (li.format !== 'percent') children.unshift(li);
      }
    } else {
      for (let i = idx + 1; i < fsData.line_items.length; i++) {
        const li = fsData.line_items[i];
        if (li.indent <= lineItem.indent) break;
        if (li.format !== 'percent') children.push(li);
      }
    }
    // Build fallback periods for component breakdown table
    var fallbackPeriods = periods;
  }

  const hasDimensions = dimData && dimData.dimensions.length > 0;
  const hasChildren = children.length > 0 && lineItem;

  return (
    <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, overflow: "hidden" }}>
      <div style={{ padding: "12px 20px", borderBottom: `1px solid ${COLORS.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: COLORS.text }}>{lineName} — Detail</span>
        <button onClick={onClose} style={{ background: "transparent", border: "none", color: COLORS.textMuted, cursor: "pointer", fontSize: 18 }}>{"\u2715"}</button>
      </div>

      <div style={{ padding: "12px 20px" }}>
        {loading && (
          <div style={{ padding: "20px 0", textAlign: "center" }}>
            <span style={{ fontSize: 13, color: COLORS.textMuted }}>Loading dimensional detail...</span>
          </div>
        )}

        {error && !loading && (
          <div style={{ padding: "12px", background: COLORS.redBg, borderRadius: 6, marginBottom: 12 }}>
            <p style={{ fontSize: 13, color: COLORS.red, margin: 0 }}>Error: {error}</p>
          </div>
        )}

        {!loading && hasDimensions && dimData.dimensions.map((section) => (
          <DimensionTable key={section.name} section={section} />
        ))}

        {!loading && !hasDimensions && hasChildren && (
          <div>
            <div style={{ fontSize: 11, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 6, fontFamily: "'JetBrains Mono',monospace" }}>Component Breakdown</div>
            <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "'IBM Plex Mono',monospace", fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                  <th style={{ textAlign: "left", padding: "8px 12px", color: COLORS.textMuted, fontWeight: 500, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>Item</th>
                  {fallbackPeriods!.map((p) => (
                    <th key={p} style={{ textAlign: "right", padding: "8px 12px", color: COLORS.textMuted, fontWeight: 500, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>{p}</th>
                  ))}
                  <th style={{ textAlign: "right", padding: "8px 12px", color: COLORS.textMuted, fontWeight: 500, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>% of Total</th>
                </tr>
              </thead>
              <tbody>
                {children.map((child) => {
                  const parentVal = lineItem!.values[fallbackPeriods![0]];
                  const childVal = child.values[fallbackPeriods![0]];
                  const pctOfTotal = parentVal && childVal ? (childVal / Math.abs(parentVal)) * 100 : null;
                  return (
                    <tr key={child.key} style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                      <td style={{ padding: "8px 12px", color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif", fontSize: 13 }}>{child.label}</td>
                      {fallbackPeriods!.map((p) => (
                        <td key={p} style={{ textAlign: "right", padding: "8px 12px", color: COLORS.text }}>{fmt(child.values[p])}</td>
                      ))}
                      <td style={{ textAlign: "right", padding: "8px 12px", color: COLORS.textMuted }}>{pctOfTotal !== null ? pctOfTotal.toFixed(1) + "%" : "\u2014"}</td>
                    </tr>
                  );
                })}
                <tr style={{ borderTop: `2px solid ${COLORS.accent}`, background: COLORS.totalBg }}>
                  <td style={{ padding: "8px 12px", fontWeight: 600, color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif", fontSize: 13 }}>{lineName}</td>
                  {fallbackPeriods!.map((p) => (
                    <td key={p} style={{ textAlign: "right", padding: "8px 12px", fontWeight: 600, color: COLORS.text }}>{fmt(lineItem!.values[p])}</td>
                  ))}
                  <td style={{ textAlign: "right", padding: "8px 12px", fontWeight: 600, color: COLORS.textMuted }}>100.0%</td>
                </tr>
              </tbody>
            </table>
          </div>
        )}

        {!loading && !hasDimensions && !hasChildren && (
          <div style={{ padding: "12px 0", fontSize: 13, color: COLORS.textMuted }}>
            No dimensional breakdown available for this line item.
          </div>
        )}
      </div>
    </div>
  );
}

function CheckDetail({ check }: { check: ReconCheck }) {
  if (!check.mismatches || check.mismatches.length === 0) {
    return (
      <div style={{ padding: "16px 20px", display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ fontSize: 18, color: COLORS.green }}>&#10003;</span>
        <span style={{ fontSize: 15, color: COLORS.green, fontFamily: "'IBM Plex Sans',sans-serif", fontWeight: 500 }}>
          All {check.total} metrics reconciled — no variances
        </span>
      </div>
    );
  }

  return (
    <div style={{ padding: "0 8px 12px", maxHeight: 300, overflowY: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "'IBM Plex Mono',monospace", fontSize: 14 }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
            <th style={{ textAlign: "left", padding: "6px 12px", color: COLORS.textDim, fontSize: 14, letterSpacing: "0.06em", textTransform: "uppercase" }}>Metric</th>
            <th style={{ textAlign: "left", padding: "6px 12px", color: COLORS.textDim, fontSize: 14, letterSpacing: "0.06em", textTransform: "uppercase" }}>Status</th>
            <th style={{ textAlign: "right", padding: "6px 12px", color: COLORS.textDim, fontSize: 14, letterSpacing: "0.06em", textTransform: "uppercase" }}>Expected</th>
            <th style={{ textAlign: "right", padding: "6px 12px", color: COLORS.textDim, fontSize: 14, letterSpacing: "0.06em", textTransform: "uppercase" }}>Actual</th>
            <th style={{ textAlign: "right", padding: "6px 12px", color: COLORS.textDim, fontSize: 14, letterSpacing: "0.06em", textTransform: "uppercase" }}>Delta</th>
            <th style={{ textAlign: "right", padding: "6px 12px", color: COLORS.textDim, fontSize: 14, letterSpacing: "0.06em", textTransform: "uppercase" }}>% Off</th>
          </tr>
        </thead>
        <tbody>
          {check.mismatches.map((m, i) => (
            <tr key={i} style={{ borderBottom: `1px solid ${COLORS.border}15` }}>
              <td style={{ padding: "6px 12px", color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif", fontSize: 14 }}>
                {m.metric.replace(/_/g, " ")}
              </td>
              <td style={{ padding: "6px 12px" }}>
                <span style={{
                  fontSize: 14, padding: "2px 6px", borderRadius: 3, fontWeight: 600,
                  background: m.status === "mismatch" ? COLORS.redBg : m.status === "missing" ? "rgba(91,141,239,0.08)" : "rgba(255,165,0,0.08)",
                  color: m.status === "mismatch" ? COLORS.red : m.status === "missing" ? COLORS.blue : "#FFA500",
                }}>
                  {m.status === "mismatch" ? "VARIANCE" : m.status === "missing" ? "MISSING" : "ERROR"}
                </span>
              </td>
              <td style={{ textAlign: "right", padding: "6px 12px", color: COLORS.textMuted }}>
                {m.expected !== null ? m.expected.toFixed(2) : "\u2014"}
              </td>
              <td style={{ textAlign: "right", padding: "6px 12px", color: m.status === "mismatch" ? COLORS.red : COLORS.textDim }}>
                {m.actual !== null ? m.actual.toFixed(2) : "\u2014"}
              </td>
              <td style={{ textAlign: "right", padding: "6px 12px", color: COLORS.red }}>
                {m.delta !== null ? m.delta.toFixed(2) : "\u2014"}
              </td>
              <td style={{ textAlign: "right", padding: "6px 12px", color: COLORS.red }}>
                {m.pct_delta !== null ? `${m.pct_delta.toFixed(1)}%` : "\u2014"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ReconView() {
  const [recon, setRecon] = useState<ReconReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const loadRecon = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchReconciliation()
      .then(setRecon)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { loadRecon(); }, [loadRecon]);

  function toggleExpand(i: number) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  }

  if (loading) {
    return (
      <div style={{ padding: "40px 20px", textAlign: "center" }}>
        <span style={{ fontSize: 15, color: COLORS.textMuted, fontFamily: "'IBM Plex Sans',sans-serif" }}>Loading reconciliation data...</span>
      </div>
    );
  }

  if (error || !recon) {
    return (
      <div style={{ maxWidth: CONTENT_MAX_WIDTH, margin: "20px auto" }}>
        <div style={{ padding: "40px 32px", background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, textAlign: "center" }}>
          <div style={{ width: 40, height: 40, borderRadius: "50%", background: COLORS.redBg, border: `1px solid ${COLORS.red}44`, display: "flex", alignItems: "center", justifyContent: "center", margin: "0 auto 16px", fontSize: 22, fontWeight: 700, color: COLORS.red }}>!</div>
          <p style={{ fontSize: 17, fontWeight: 600, color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif", margin: "0 0 8px" }}>
            Unable to load reconciliation data
          </p>
          <p style={{ fontSize: 14, color: COLORS.textMuted, fontFamily: "'IBM Plex Mono',monospace", margin: "0 0 20px", whiteSpace: "pre-wrap", maxWidth: 500, marginLeft: "auto", marginRight: "auto" }}>
            {error || "No data returned from reconciliation engine"}
          </p>
          <button onClick={loadRecon} style={{
            fontSize: 15, color: COLORS.text, background: COLORS.surfaceHover,
            border: `1px solid ${COLORS.border}`, padding: "8px 20px",
            borderRadius: 6, cursor: "pointer", fontWeight: 500,
            fontFamily: "'IBM Plex Sans',sans-serif", transition: "all 0.15s",
          }}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 24, marginBottom: 24 }}>
        <div style={{ background: recon.totalRed === 0 ? COLORS.greenBg : COLORS.redBg, border: `1px solid ${recon.totalRed === 0 ? COLORS.green : COLORS.red}33`, borderRadius: 8, padding: "16px 24px", flex: 1 }}>
          <div style={{ fontSize: 34, fontWeight: 700, color: recon.totalRed === 0 ? COLORS.green : COLORS.red, fontFamily: "'IBM Plex Mono',monospace" }}>{recon.totalRed === 0 ? "PASS" : "FAIL"}</div>
          <div style={{ fontSize: 15, color: COLORS.textMuted, marginTop: 4 }}>{recon.totalChecks.toLocaleString()} checks</div>
        </div>
        <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "16px 24px", flex: 1 }}>
          <div style={{ fontSize: 34, fontWeight: 700, color: COLORS.green, fontFamily: "'IBM Plex Mono',monospace" }}>{recon.totalGreen.toLocaleString()}</div>
          <div style={{ fontSize: 15, color: COLORS.textMuted, marginTop: 4 }}>GREEN (matched)</div>
        </div>
        <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "16px 24px", flex: 1 }}>
          <div style={{ fontSize: 34, fontWeight: 700, color: recon.totalRed > 0 ? COLORS.red : COLORS.textDim, fontFamily: "'IBM Plex Mono',monospace" }}>{recon.totalRed}</div>
          <div style={{ fontSize: 15, color: COLORS.textMuted, marginTop: 4 }}>RED (variance)</div>
        </div>
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "'IBM Plex Mono',monospace", fontSize: 15 }}>
        <thead>
          <tr style={{ borderBottom: `2px solid ${COLORS.accent}` }}>
            <th style={{ textAlign: "left", padding: "8px 16px", color: COLORS.textMuted, fontSize: 15, letterSpacing: "0.06em", textTransform: "uppercase", width: 24 }}></th>
            <th style={{ textAlign: "left", padding: "8px 16px", color: COLORS.textMuted, fontSize: 15, letterSpacing: "0.06em", textTransform: "uppercase" }}>Statement</th>
            <th style={{ textAlign: "left", padding: "8px 16px", color: COLORS.textMuted, fontSize: 15, letterSpacing: "0.06em", textTransform: "uppercase" }}>Period</th>
            <th style={{ textAlign: "right", padding: "8px 16px", color: COLORS.textMuted, fontSize: 15, letterSpacing: "0.06em", textTransform: "uppercase" }}>Checks</th>
            <th style={{ textAlign: "right", padding: "8px 16px", color: COLORS.textMuted, fontSize: 15, letterSpacing: "0.06em", textTransform: "uppercase" }}>Green</th>
            <th style={{ textAlign: "right", padding: "8px 16px", color: COLORS.textMuted, fontSize: 15, letterSpacing: "0.06em", textTransform: "uppercase" }}>Red</th>
            <th style={{ textAlign: "center", padding: "8px 16px", color: COLORS.textMuted, fontSize: 15, letterSpacing: "0.06em", textTransform: "uppercase" }}>Status</th>
          </tr>
        </thead>
        <tbody>
          {recon.checks.map((c, i) => {
            const isExpanded = expanded.has(i);
            return (
              <>
                <tr key={i} onClick={() => toggleExpand(i)} style={{
                  borderBottom: isExpanded ? "none" : `1px solid ${COLORS.border}22`,
                  cursor: "pointer",
                  transition: "background 0.1s",
                  background: isExpanded ? COLORS.surfaceHover : "transparent",
                }}
                  onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = COLORS.surfaceHover; }}
                  onMouseLeave={(e) => { if (!isExpanded) (e.currentTarget as HTMLElement).style.background = "transparent"; }}
                >
                  <td style={{ padding: "8px 8px 8px 16px", color: COLORS.accent, fontSize: 15, width: 24 }}>
                    {isExpanded ? "\u25BE" : "\u25B8"}
                  </td>
                  <td style={{ padding: "8px 16px", color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>{c.statement}</td>
                  <td style={{ padding: "8px 16px", color: COLORS.textMuted }}>{c.period}</td>
                  <td style={{ textAlign: "right", padding: "8px 16px", color: COLORS.textMuted }}>{c.total}</td>
                  <td style={{ textAlign: "right", padding: "8px 16px", color: COLORS.green }}>{c.green}</td>
                  <td style={{ textAlign: "right", padding: "8px 16px", color: c.red > 0 ? COLORS.red : COLORS.textDim }}>{c.red}</td>
                  <td style={{ textAlign: "center", padding: "8px 16px" }}>
                    <span style={{
                      fontSize: 15, padding: "3px 10px", borderRadius: 4, fontWeight: 600,
                      background: c.red === 0 ? COLORS.greenBg : COLORS.redBg, color: c.red === 0 ? COLORS.green : COLORS.red,
                    }}>{c.red === 0 ? "PASS" : "FAIL"}</span>
                  </td>
                </tr>
                {isExpanded && (
                  <tr key={`${i}-detail`} style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                    <td colSpan={7} style={{ padding: 0, background: COLORS.surface }}>
                      <CheckDetail check={c} />
                    </td>
                  </tr>
                )}
              </>
            );
          })}
        </tbody>
      </table>
      {recon.coverage && <CoverageSummary coverage={recon.coverage} />}
    </div>
  );
}

function CoverageSummary({ coverage }: { coverage: ReconCoverage }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div style={{ marginTop: 24, padding: "16px 20px", background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontFamily: "'IBM Plex Sans',sans-serif", fontSize: 15, color: COLORS.text }}>
          Coverage: <span style={{ fontWeight: 600, fontFamily: "'IBM Plex Mono',monospace" }}>{coverage.in_scope}</span> of{" "}
          <span style={{ fontFamily: "'IBM Plex Mono',monospace" }}>{coverage.total_farm_metrics}</span> Farm metrics reconciled
          <span style={{ color: COLORS.textMuted }}> (financial statements only)</span>
        </div>
        {coverage.out_of_scope > 0 && (
          <button
            onClick={() => setExpanded((p) => !p)}
            style={{
              fontSize: 14, color: COLORS.accent, background: "transparent",
              border: "none", cursor: "pointer", textDecoration: "underline",
            }}
          >
            {expanded ? "Hide" : "Show"} {coverage.out_of_scope} out-of-scope metrics
          </button>
        )}
      </div>
      {expanded && coverage.out_of_scope_categories && (
        <div style={{ marginTop: 12 }}>
          {Object.entries(coverage.out_of_scope_categories).map(([cat, metrics]) => (
            <div key={cat} style={{ marginBottom: 8 }}>
              <div style={{
                fontSize: 15, fontWeight: 600, color: COLORS.textMuted,
                textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 2,
              }}>
                {cat} ({metrics.length})
              </div>
              <div style={{ fontSize: 14, color: COLORS.textDim, fontFamily: "'IBM Plex Mono',monospace" }}>
                {metrics.join(", ")}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ============================================================
// DEAL SELECTOR (Deal dropdown + Acquiror/Target/Combined toggle)
// ============================================================

interface DealInfo {
  acquirer: { id: string; label: string } | null;
  target: { id: string; label: string } | null;
  combinedAvailable: boolean;
}

function DealSelector({ selected, onChange, onDealLoaded }: { selected: EntitySelection; onChange: (e: EntitySelection) => void; onDealLoaded?: (names: Record<string, string>) => void }) {
  const [deals, setDeals] = React.useState<{ value: string; label: string; deal: DealInfo }[]>([]);
  const [activeDeal, setActiveDeal] = React.useState<DealInfo | null>(null);

  React.useEffect(() => {
    fetch("/api/v1/entities")
      .then((r) => r.json())
      .then((data) => {
        const all = data.entities || [];
        const acq = all.find((e: { role: string }) => e.role === "acquirer");
        const tgt = all.find((e: { role: string }) => e.role === "target");
        const deal: DealInfo = {
          acquirer: acq ? { id: acq.entity_id, label: acq.display_name } : null,
          target: tgt ? { id: tgt.entity_id, label: tgt.display_name } : null,
          combinedAvailable: !!data.combined_available,
        };
        const dealLabel = [deal.acquirer?.label, deal.target?.label].filter(Boolean).join(" / ");
        const dealValue = [deal.acquirer?.id, deal.target?.id].filter(Boolean).join("_");
        if (dealLabel) {
          setDeals([{ value: dealValue, label: dealLabel, deal }]);
          setActiveDeal(deal);
          if (onDealLoaded) {
            const names: Record<string, string> = { combined: "Combined" };
            if (deal.acquirer) names[deal.acquirer.id] = deal.acquirer.label;
            if (deal.target) names[deal.target.id] = deal.target.label;
            onDealLoaded(names);
          }
        }
      })
      .catch(() => {
        // If fetch fails, no deals available — degrade gracefully
      });
  }, []);

  if (!activeDeal) return null;

  const viewButtons: { key: string; label: string; entityId: string }[] = [];
  if (activeDeal.acquirer) {
    viewButtons.push({ key: "acquirer", label: "Acquiror", entityId: activeDeal.acquirer.id });
  }
  if (activeDeal.target) {
    viewButtons.push({ key: "target", label: "Target", entityId: activeDeal.target.id });
  }
  if (activeDeal.combinedAvailable) {
    viewButtons.push({ key: "combined", label: "Combined", entityId: "combined" });
  }

  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 12, flexShrink: 0 }}>
      {deals.length > 0 && (
        <Select
          label="Deal"
          value={deals[0].value}
          onChange={() => {}}
          options={deals.map((d) => ({ value: d.value, label: d.label }))}
          width={200}
        />
      )}
      <div style={{ display: "flex", alignItems: "center", gap: 2, paddingBottom: 2 }}>
        {viewButtons.map((b) => {
          const isActive = selected === b.entityId;
          return (
            <button key={b.key} onClick={() => onChange(b.entityId)} style={{
              padding: "6px 14px", fontSize: 12, fontWeight: isActive ? 600 : 400,
              fontFamily: "'IBM Plex Sans',sans-serif", letterSpacing: "0.03em", cursor: "pointer",
              transition: "all 0.15s", borderRadius: 4,
              background: isActive ? COLORS.surface : "transparent",
              color: isActive ? COLORS.text : COLORS.textMuted,
              border: isActive
                ? `1px solid ${COLORS.borderLight}`
                : `1px solid transparent`,
              whiteSpace: "nowrap" as const,
            }}>
              {b.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ============================================================
// COMBINING STATEMENT (four-column layout)
// ============================================================

function fmtCombining(n: number | null | undefined): string {
  if (n === null || n === undefined) return "";
  const abs = Math.abs(n);
  const s = abs.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  return n < 0 ? `(${s})` : s;
}

function CombiningStatement({ data, loading, error, onRetry }: {
  data: CombiningStatementData | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}) {
  if (loading) return <LoadingState message="Loading combining statement..." />;
  if (error) return <ErrorState error={error} onRetry={onRetry} />;
  if (!data) return null;

  const thStyle: React.CSSProperties = {
    textAlign: "right", padding: "10px 16px", color: COLORS.textMuted, fontWeight: 500,
    fontSize: 15, letterSpacing: "0.06em", textTransform: "uppercase",
    fontFamily: "'JetBrains Mono',monospace",
  };

  return (
    <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, overflow: "hidden" }}>
      <div style={{ padding: "12px 20px", borderBottom: `1px solid ${COLORS.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 16, fontWeight: 600, color: COLORS.text }}>Combining Income Statement</span>
        <span style={{ fontSize: 14, color: COLORS.textMuted }}>{data.period}</span>
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "'IBM Plex Mono','JetBrains Mono',monospace", fontSize: 15 }}>
          <thead>
            <tr style={{ borderBottom: `2px solid ${COLORS.accent}` }}>
              <th style={{ ...thStyle, textAlign: "left", width: "30%" }}>
                Line Item
                {" "}
                <span style={{ fontWeight: 400, fontSize: 14, fontStyle: "italic", letterSpacing: "0.04em", color: COLORS.textDim }}>($MM)</span>
              </th>
              <th style={thStyle}>Meridian</th>
              <th style={thStyle}>Cascadia</th>
              <th style={{ ...thStyle, background: "rgba(255,235,59,0.06)" }}>Adjustments</th>
              <th style={thStyle}>Combined</th>
            </tr>
          </thead>
          <tbody>
            {data.line_items.map((item, i) => {
              const isTotal = item.line_item.startsWith("Total");
              const isBold = isTotal || item.line_item.includes("Net Income") || item.line_item.includes("EBITDA");
              const numStyle = (val: number, isAdj = false): React.CSSProperties => ({
                textAlign: "right", padding: "8px 16px",
                fontWeight: isBold ? 600 : 400,
                color: val < 0 ? COLORS.red : COLORS.text,
                background: isAdj ? "rgba(255,235,59,0.04)" : "transparent",
              });
              return (
                <tr key={i} style={{
                  borderTop: isTotal ? `1px solid ${COLORS.borderLight}` : "none",
                  borderBottom: `1px solid ${COLORS.border}22`,
                  background: isBold ? COLORS.totalBg : "transparent",
                }}>
                  <td style={{
                    padding: "8px 16px", fontFamily: "'IBM Plex Sans',sans-serif",
                    fontWeight: isBold ? 600 : 400, color: COLORS.text,
                  }}>
                    {item.line_item}
                  </td>
                  <td style={numStyle(item.meridian)}>{fmtCombining(item.meridian)}</td>
                  <td style={numStyle(item.cascadia)}>{fmtCombining(item.cascadia)}</td>
                  <td style={numStyle(item.adjustments, true)}>{fmtCombining(item.adjustments)}</td>
                  <td style={numStyle(item.combined)}>{fmtCombining(item.combined)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ============================================================
// OVERLAP REPORT
// ============================================================

function OverlapReport({ data, loading, error, onRetry }: {
  data: OverlapData | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}) {
  const [custExpanded, setCustExpanded] = useState(false);
  const [vendExpanded, setVendExpanded] = useState(false);
  const [custDetail, setCustDetail] = useState<string | null>(null);
  const [vendDetail, setVendDetail] = useState<string | null>(null);
  const [peopleExpanded, setPeopleExpanded] = useState(false);
  const [funcDetail, setFuncDetail] = useState<string | null>(null);


  if (loading) return <LoadingState message="Loading entity overlap data..." />;
  if (error) return <ErrorState error={error} onRetry={onRetry} />;
  if (!data) return null;

  const co = data.customer_overlap;
  const vo = data.vendor_overlap;
  const po = data.people_overlap;

  const matchCounts = { exact: 0, fuzzy: 0, manual: 0 };
  for (const m of co.matches) {
    if (m.match_type === "exact") matchCounts.exact++;
    else if (m.match_type === "fuzzy") matchCounts.fuzzy++;
    else matchCounts.manual++;
  }

  const thS: React.CSSProperties = { textAlign: "left", padding: "6px 10px", color: COLORS.textMuted, fontSize: 14, letterSpacing: "0.06em", textTransform: "uppercase", fontFamily: "'JetBrains Mono',monospace" };
  const thR: React.CSSProperties = { ...thS, textAlign: "right" };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* Customer Overlap */}
      <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, overflow: "hidden" }}>
        <div style={{ padding: "12px 20px", borderBottom: `1px solid ${COLORS.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: 16, fontWeight: 600, color: COLORS.text }}>Customer Overlap</span>
          <button onClick={() => setCustExpanded(!custExpanded)} style={{ background: "rgba(199,120,64,0.08)", border: `1px solid ${COLORS.accent}33`, borderRadius: 4, color: COLORS.accent, fontSize: 15, padding: "4px 12px", cursor: "pointer", fontWeight: 600 }}>
            {custExpanded ? "Collapse" : `View All ${co.total_overlapping} Matches`}
          </button>
        </div>
        {/* Summary cards — all clickable */}
        <div style={{ padding: "16px 20px", display: "flex", gap: 16, cursor: "pointer" }} onClick={() => setCustExpanded(!custExpanded)}>
          <div style={{ background: COLORS.bg, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 20px", flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: 30, fontWeight: 700, color: COLORS.accent, fontFamily: "'IBM Plex Mono',monospace" }}>{co.total_overlapping}</div>
            <div style={{ fontSize: 15, color: COLORS.textMuted, marginTop: 4 }}>Overlapping Customers</div>
          </div>
          <div style={{ background: COLORS.bg, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 20px", flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: 30, fontWeight: 700, color: COLORS.textDim, fontFamily: "'IBM Plex Mono',monospace" }}>{co.overlap_pct_of_combined.toFixed(1)}%</div>
            <div style={{ fontSize: 15, color: COLORS.textMuted, marginTop: 4 }}>of Combined Revenue</div>
          </div>
          <div style={{ background: COLORS.bg, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 20px", flex: 2 }}>
            <div style={{ fontSize: 15, color: COLORS.textMuted, marginBottom: 6 }}>Match Type Breakdown</div>
            <div style={{ display: "flex", gap: 16, fontSize: 15, fontFamily: "'IBM Plex Mono',monospace" }}>
              <span style={{ color: COLORS.green }}>Exact: {matchCounts.exact}</span>
              <span style={{ color: COLORS.accent }}>Fuzzy: {matchCounts.fuzzy}</span>
              <span style={{ color: COLORS.red }}>Manual: {matchCounts.manual}</span>
            </div>
          </div>
        </div>

        {/* Expanded match table */}
        {custExpanded && (
          <div style={{ borderTop: `1px solid ${COLORS.border}` }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                  <th style={thS}>Customer</th>
                  <th style={thS}>Match</th>
                  <th style={thR}>M Rev ($M)</th>
                  <th style={thR}>C Rev ($M)</th>
                  <th style={thR}>Combined ($M)</th>
                  <th style={thR}>% of Total</th>
                  <th style={thS}>Industry</th>
                  <th style={thS}>Flag</th>
                </tr>
              </thead>
              <tbody>
                {co.matches.map((m) => {
                  const isExp = custDetail === m.canonical_name;
                  return (
                    <React.Fragment key={m.canonical_name}>
                      <tr onClick={() => setCustDetail(isExp ? null : m.canonical_name)} style={{ borderBottom: `1px solid ${COLORS.border}15`, cursor: "pointer", background: isExp ? COLORS.surfaceHover : "transparent" }}>
                        <td style={{ padding: "6px 10px", color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>
                          <span style={{ color: COLORS.accent, marginRight: 6, fontSize: 11 }}>{isExp ? "\u25BE" : "\u25B8"}</span>
                          {m.canonical_name}
                        </td>
                        <td style={{ padding: "6px 10px" }}>
                          <span style={{ fontSize: 14, padding: "2px 6px", borderRadius: 3, fontWeight: 600, color: m.match_type === "exact" ? COLORS.green : m.match_type === "fuzzy" ? COLORS.accent : COLORS.red, background: m.match_type === "exact" ? COLORS.greenBg : m.match_type === "fuzzy" ? "rgba(199,120,64,0.08)" : COLORS.redBg }}>
                            {m.match_type.toUpperCase()}
                          </span>
                        </td>
                        <td style={{ textAlign: "right", padding: "6px 10px", color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{m.meridian_revenue_M.toFixed(1)}</td>
                        <td style={{ textAlign: "right", padding: "6px 10px", color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{m.cascadia_revenue_M.toFixed(1)}</td>
                        <td style={{ textAlign: "right", padding: "6px 10px", color: COLORS.text, fontWeight: 600, fontFamily: "'IBM Plex Mono',monospace" }}>{m.combined_revenue_M.toFixed(1)}</td>
                        <td style={{ textAlign: "right", padding: "6px 10px", color: COLORS.textMuted, fontFamily: "'IBM Plex Mono',monospace" }}>{m.combined_pct_of_total.toFixed(2)}%</td>
                        <td style={{ padding: "6px 10px", color: COLORS.textMuted, fontFamily: "'IBM Plex Sans',sans-serif", fontSize: 15 }}>{m.industry}</td>
                        <td style={{ padding: "6px 10px" }}>
                          {m.concentration_flag && <span style={{ fontSize: 14, padding: "2px 6px", borderRadius: 3, fontWeight: 600, color: COLORS.red, background: COLORS.redBg }}>CONC</span>}
                        </td>
                      </tr>
                      {isExp && (
                        <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                          <td colSpan={8} style={{ padding: "10px 20px 14px 32px", background: COLORS.surface }}>
                            <div style={{ fontSize: 14, color: COLORS.textMuted, lineHeight: 1.6, fontFamily: "'IBM Plex Sans',sans-serif" }}>
                              <div><span style={{ color: COLORS.textDim }}>Meridian Name:</span> {m.meridian_name}</div>
                              <div><span style={{ color: COLORS.textDim }}>Cascadia Name:</span> {m.cascadia_name}</div>
                              <div><span style={{ color: COLORS.textDim }}>Confidence:</span> {(m.confidence * 100).toFixed(0)}%</div>
                              <div><span style={{ color: COLORS.textDim }}>Notes:</span> {m.notes}</div>
                              {m.engagement_detail && m.engagement_detail.length > 0 && (
                                <div style={{ marginTop: 8 }}>
                                  <div style={{ fontWeight: 600, color: COLORS.text, marginBottom: 4 }}>Engagement Detail:</div>
                                  {m.engagement_detail.map((ed, i) => (
                                    <div key={i} style={{ marginLeft: 12, marginBottom: 4, fontSize: 15 }}>
                                      <span style={{ fontWeight: 600, color: COLORS.accent }}>{ed.entity}:</span> {ed.service_types?.join(", ")}
                                      {Object.entries(ed).filter(([k]) => !["entity", "service_types"].includes(k)).map(([k, v]) => (
                                        <span key={k} style={{ marginLeft: 8, color: COLORS.textDim }}>{k}: {typeof v === "number" ? v.toLocaleString() : String(v)}</span>
                                      ))}
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Vendor Overlap */}
      <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, overflow: "hidden" }}>
        <div style={{ padding: "12px 20px", borderBottom: `1px solid ${COLORS.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: 16, fontWeight: 600, color: COLORS.text }}>Vendor Overlap</span>
          <button onClick={() => setVendExpanded(!vendExpanded)} style={{ background: "rgba(199,120,64,0.08)", border: `1px solid ${COLORS.accent}33`, borderRadius: 4, color: COLORS.accent, fontSize: 15, padding: "4px 12px", cursor: "pointer", fontWeight: 600 }}>
            {vendExpanded ? "Collapse" : `View All ${vo.total_overlapping} Matches`}
          </button>
        </div>
        <div style={{ padding: "16px 20px", display: "flex", gap: 16, cursor: "pointer" }} onClick={() => setVendExpanded(!vendExpanded)}>
          <div style={{ background: COLORS.bg, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 20px", flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: 30, fontWeight: 700, color: COLORS.accent, fontFamily: "'IBM Plex Mono',monospace" }}>{vo.total_overlapping}</div>
            <div style={{ fontSize: 15, color: COLORS.textMuted, marginTop: 4 }}>Overlapping Vendors</div>
          </div>
          <div style={{ background: COLORS.bg, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 20px", flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: 30, fontWeight: 700, color: COLORS.textDim, fontFamily: "'IBM Plex Mono',monospace" }}>{vo.overlap_pct_of_combined.toFixed(1)}%</div>
            <div style={{ fontSize: 15, color: COLORS.textMuted, marginTop: 4 }}>of Combined Spend</div>
          </div>
        </div>

        {vendExpanded && (
          <div style={{ borderTop: `1px solid ${COLORS.border}` }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                  <th style={thS}>Vendor</th>
                  <th style={thS}>Category</th>
                  <th style={thS}>Match</th>
                  <th style={thR}>M Spend ($M)</th>
                  <th style={thR}>C Spend ($M)</th>
                  <th style={thR}>Combined ($M)</th>
                  <th style={thS}>Consolidation</th>
                </tr>
              </thead>
              <tbody>
                {vo.matches.map((v) => {
                  const isExp = vendDetail === v.canonical_name;
                  return (
                    <React.Fragment key={v.canonical_name}>
                      <tr onClick={() => setVendDetail(isExp ? null : v.canonical_name)} style={{ borderBottom: `1px solid ${COLORS.border}15`, cursor: "pointer", background: isExp ? COLORS.surfaceHover : "transparent" }}>
                        <td style={{ padding: "6px 10px", color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>
                          <span style={{ color: COLORS.accent, marginRight: 6, fontSize: 11 }}>{isExp ? "\u25BE" : "\u25B8"}</span>
                          {v.canonical_name}
                        </td>
                        <td style={{ padding: "6px 10px", color: COLORS.textMuted, fontSize: 15 }}>{v.category?.replace(/_/g, " ")}</td>
                        <td style={{ padding: "6px 10px" }}>
                          <span style={{ fontSize: 14, padding: "2px 6px", borderRadius: 3, fontWeight: 600, color: v.match_type === "exact" ? COLORS.green : COLORS.accent, background: v.match_type === "exact" ? COLORS.greenBg : "rgba(199,120,64,0.08)" }}>
                            {v.match_type.toUpperCase()}
                          </span>
                        </td>
                        <td style={{ textAlign: "right", padding: "6px 10px", color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{v.meridian_spend_M.toFixed(1)}</td>
                        <td style={{ textAlign: "right", padding: "6px 10px", color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{v.cascadia_spend_M.toFixed(1)}</td>
                        <td style={{ textAlign: "right", padding: "6px 10px", color: COLORS.text, fontWeight: 600, fontFamily: "'IBM Plex Mono',monospace" }}>{v.combined_spend_M.toFixed(1)}</td>
                        <td style={{ padding: "6px 10px" }}>
                          {v.consolidation_opportunity && <span style={{ fontSize: 14, padding: "2px 6px", borderRadius: 3, fontWeight: 600, color: COLORS.green, background: COLORS.greenBg }}>YES</span>}
                        </td>
                      </tr>
                      {isExp && !!v.consolidation_detail && (() => {
                        const d = v.consolidation_detail as Record<string, unknown>;
                        const savPct = typeof d.estimated_savings_pct === "number" ? d.estimated_savings_pct : null;
                        const savM = typeof d.estimated_savings_M === "number" ? d.estimated_savings_M : null;
                        const subcats = Array.isArray(d.service_subcategories) ? d.service_subcategories as string[] : [];
                        return (
                          <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                            <td colSpan={7} style={{ padding: "12px 20px 16px 32px", background: COLORS.surface }}>
                              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, marginBottom: 10 }}>
                                <div>
                                  <div style={{ fontSize: 14, color: COLORS.textDim, marginBottom: 2 }}>Meridian Contract</div>
                                  <div style={{ fontSize: 14, color: COLORS.text }}>{String(d.meridian_contract_type || "—")} · ends {String(d.meridian_contract_end || "—")}</div>
                                </div>
                                <div>
                                  <div style={{ fontSize: 14, color: COLORS.textDim, marginBottom: 2 }}>Cascadia Contract</div>
                                  <div style={{ fontSize: 14, color: COLORS.text }}>{String(d.cascadia_contract_type || "—")} · ends {String(d.cascadia_contract_end || "—")}</div>
                                </div>
                                {savM !== null && (
                                  <div>
                                    <div style={{ fontSize: 14, color: COLORS.textDim, marginBottom: 2 }}>Est. Savings</div>
                                    <div style={{ fontSize: 15, color: COLORS.green, fontWeight: 700, fontFamily: "'IBM Plex Mono',monospace" }}>
                                      ${savM.toFixed(1)}M{savPct !== null && <span style={{ fontWeight: 400, fontSize: 15, marginLeft: 4 }}>({savPct.toFixed(1)}%)</span>}
                                    </div>
                                  </div>
                                )}
                              </div>
                              {!!d.savings_rationale && (
                                <div style={{ fontSize: 15, color: COLORS.textMuted, marginBottom: 8, fontStyle: "italic" }}>{String(d.savings_rationale)}</div>
                              )}
                              {subcats.length > 0 && (
                                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                                  {subcats.map((s) => (
                                    <span key={s} style={{ fontSize: 14, padding: "2px 8px", borderRadius: 3, background: `${COLORS.accent}15`, color: COLORS.accent, border: `1px solid ${COLORS.accent}30` }}>{s}</span>
                                  ))}
                                </div>
                              )}
                            </td>
                          </tr>
                        );
                      })()}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* People Overlap */}
      <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, overflow: "hidden" }}>
        <div style={{ padding: "12px 20px", borderBottom: `1px solid ${COLORS.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: 16, fontWeight: 600, color: COLORS.text }}>People Overlap</span>
          <button onClick={() => setPeopleExpanded(!peopleExpanded)} style={{ background: "rgba(199,120,64,0.08)", border: `1px solid ${COLORS.accent}33`, borderRadius: 4, color: COLORS.accent, fontSize: 15, padding: "4px 12px", cursor: "pointer", fontWeight: 600 }}>
            {peopleExpanded ? "Collapse" : `View All ${po.functions.length} Functions`}
          </button>
        </div>
        {/* Summary cards */}
        <div style={{ padding: "16px 20px", display: "flex", gap: 16, cursor: "pointer" }} onClick={() => setPeopleExpanded(!peopleExpanded)}>
          <div style={{ background: COLORS.bg, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 20px", flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: 30, fontWeight: 700, color: COLORS.accent, fontFamily: "'IBM Plex Mono',monospace" }}>{po.total_meridian_corporate.toLocaleString()}</div>
            <div style={{ fontSize: 15, color: COLORS.textMuted, marginTop: 4 }}>Meridian Headcount</div>
          </div>
          <div style={{ background: COLORS.bg, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 20px", flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: 30, fontWeight: 700, color: COLORS.accent, fontFamily: "'IBM Plex Mono',monospace" }}>{po.total_cascadia_corporate.toLocaleString()}</div>
            <div style={{ fontSize: 15, color: COLORS.textMuted, marginTop: 4 }}>Cascadia Headcount</div>
          </div>
          <div style={{ background: COLORS.bg, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 20px", flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: 30, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{po.total_combined_corporate.toLocaleString()}</div>
            <div style={{ fontSize: 15, color: COLORS.textMuted, marginTop: 4 }}>Combined Corporate</div>
          </div>
          <div style={{ background: COLORS.bg, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 20px", flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: 30, fontWeight: 700, color: COLORS.green, fontFamily: "'IBM Plex Mono',monospace" }}>{po.functions.length}</div>
            <div style={{ fontSize: 15, color: COLORS.textMuted, marginTop: 4 }}>Functions Analyzed</div>
          </div>
        </div>

        {/* Expanded function table */}
        {peopleExpanded && (
          <div style={{ borderTop: `1px solid ${COLORS.border}` }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                  <th style={thS}>Function</th>
                  <th style={thR}>Meridian</th>
                  <th style={thR}>Cascadia</th>
                  <th style={thR}>Combined</th>
                  <th style={thS}>Key Roles</th>
                </tr>
              </thead>
              <tbody>
                {po.functions.map((fn) => {
                  const isFuncExp = funcDetail === fn.function;
                  return (
                    <React.Fragment key={fn.function}>
                      <tr onClick={() => setFuncDetail(isFuncExp ? null : fn.function)} style={{ borderBottom: `1px solid ${COLORS.border}15`, cursor: "pointer", background: isFuncExp ? COLORS.surfaceHover : "transparent" }}>
                        <td style={{ padding: "6px 10px", color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>
                          <span style={{ color: COLORS.accent, marginRight: 6, fontSize: 11 }}>{isFuncExp ? "\u25BE" : "\u25B8"}</span>
                          {fn.function}
                        </td>
                        <td style={{ textAlign: "right", padding: "6px 10px", color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{fn.meridian_headcount.toLocaleString()}</td>
                        <td style={{ textAlign: "right", padding: "6px 10px", color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{fn.cascadia_headcount.toLocaleString()}</td>
                        <td style={{ textAlign: "right", padding: "6px 10px", color: COLORS.text, fontWeight: 600, fontFamily: "'IBM Plex Mono',monospace" }}>{fn.combined_headcount.toLocaleString()}</td>
                        <td style={{ padding: "6px 10px", color: COLORS.textMuted, fontSize: 15 }}>{fn.role_overlap_examples.slice(0, 3).join(", ")}{fn.role_overlap_examples.length > 3 ? "..." : ""}</td>
                      </tr>
                      {isFuncExp && (
                        <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                          <td colSpan={5} style={{ padding: "10px 20px 14px 32px", background: COLORS.surface }}>
                            <div style={{ fontSize: 15, color: COLORS.textDim, fontStyle: "italic", marginBottom: 8 }}>{fn.definitional_note}</div>
                            {fn.role_detail && fn.role_detail.length > 0 && (
                              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 15 }}>
                                <thead>
                                  <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                                    <th style={thS}>Role</th>
                                    <th style={thR}>Meridian</th>
                                    <th style={thR}>Cascadia</th>
                                    <th style={thR}>Combined</th>
                                    <th style={thS}>Action</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {fn.role_detail.map((rd) => (
                                    <tr key={rd.title} style={{ borderBottom: `1px solid ${COLORS.border}10` }}>
                                      <td style={{ padding: "4px 10px", color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>{rd.title}</td>
                                      <td style={{ textAlign: "right", padding: "4px 10px", color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{rd.meridian_count}</td>
                                      <td style={{ textAlign: "right", padding: "4px 10px", color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{rd.cascadia_count}</td>
                                      <td style={{ textAlign: "right", padding: "4px 10px", color: COLORS.text, fontWeight: 600, fontFamily: "'IBM Plex Mono',monospace" }}>{rd.combined_count}</td>
                                      <td style={{ padding: "4px 10px" }}>
                                        <span style={{ fontSize: 11, padding: "1px 6px", borderRadius: 3, fontWeight: 600,
                                          color: rd.consolidation_action === "eliminate" ? COLORS.red : rd.consolidation_action === "merge" || rd.consolidation_action === "consolidate" ? COLORS.accent : COLORS.green,
                                          background: rd.consolidation_action === "eliminate" ? COLORS.redBg : rd.consolidation_action === "merge" || rd.consolidation_action === "consolidate" ? "rgba(199,120,64,0.08)" : COLORS.greenBg,
                                        }}>{rd.consolidation_action?.toUpperCase()}</span>
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            )}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================
// Loading spinner (themed)
// ============================================================
function LoadingState({ message = "Loading..." }: { message?: string }) {
  return (
    <div style={{ padding: "60px 20px", textAlign: "center" }}>
      <div style={{ fontSize: 16, color: COLORS.textMuted, fontFamily: "'IBM Plex Sans',sans-serif" }}>{message}</div>
    </div>
  );
}

function ErrorState({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <div style={{ margin: "20px 0", padding: "20px", background: COLORS.redBg, borderRadius: 8, border: `1px solid ${COLORS.red}33` }}>
      <p style={{ fontSize: 15, fontWeight: 600, color: COLORS.red, fontFamily: "'IBM Plex Sans',sans-serif", margin: 0 }}>Error loading report data</p>
      <p style={{ fontSize: 14, color: COLORS.red, fontFamily: "'IBM Plex Mono',monospace", margin: "8px 0 0", whiteSpace: "pre-wrap", opacity: 0.85 }}>{error}</p>
      <button onClick={onRetry} style={{ marginTop: 12, fontSize: 14, color: COLORS.red, background: "transparent", border: `1px solid ${COLORS.red}44`, padding: "4px 12px", borderRadius: 4, cursor: "pointer" }}>Retry</button>
    </div>
  );
}

// ============================================================
// CROSS-SELL TAB
// ============================================================

function CrossSellTab() {
  const [data, setData] = useState<CrossSellData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [direction, setDirection] = useState<"m_to_c" | "c_to_m">("m_to_c");
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    fetchCrossSell()
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingState message="Loading cross-sell pipeline..." />;
  if (error || !data) return <ErrorState error={error || "No data"} onRetry={() => { setLoading(true); setError(null); fetchCrossSell().then(setData).catch((e) => setError(String(e))).finally(() => setLoading(false)); }} />;

  const s = data.summary;
  const candidates = direction === "m_to_c" ? data.m_to_c : data.c_to_m;
  const thS: React.CSSProperties = { textAlign: "left", padding: "8px 12px", color: COLORS.textMuted, fontWeight: 500, fontSize: 14, letterSpacing: "0.06em", textTransform: "uppercase", fontFamily: "'JetBrains Mono',monospace" };
  const thR: React.CSSProperties = { ...thS, textAlign: "right" };

  return (
    <div>
      {/* Summary cards */}
      <div style={{ display: "flex", gap: 16, marginBottom: 24, flexWrap: "wrap" }}>
        {[
          { label: "Total Pipeline", value: fmtDollar(s.total_pipeline_acv), sub: `${s.total_candidates} candidates` },
          { label: "High Confidence", value: fmtDollar(s.total_high_conf_acv), sub: "Score > 80" },
          { label: "M \u2192 C Candidates", value: String(s.m_to_c_candidates), sub: fmtDollar(s.m_to_c_total_acv) },
          { label: "C \u2192 M Candidates", value: String(s.c_to_m_candidates), sub: fmtDollar(s.c_to_m_total_acv) },
        ].map((card) => (
          <div key={card.label} style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "16px 20px", flex: "1 1 180px", minWidth: 180 }}>
            <div style={{ fontSize: 15, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono',monospace" }}>{card.label}</div>
            <div style={{ fontSize: 26, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace", marginTop: 4 }}>{card.value}</div>
            <div style={{ fontSize: 14, color: COLORS.textDim, marginTop: 2 }}>{card.sub}</div>
          </div>
        ))}
      </div>

      {/* Direction toggle */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {(["m_to_c", "c_to_m"] as const).map((d) => (
          <button key={d} onClick={() => setDirection(d)} style={{
            padding: "6px 16px", fontSize: 14, fontWeight: direction === d ? 600 : 400,
            background: direction === d ? "rgba(199,120,64,0.12)" : "transparent",
            color: direction === d ? COLORS.accent : COLORS.textMuted,
            border: `1px solid ${direction === d ? COLORS.accent + "44" : COLORS.border}`,
            borderRadius: 4, cursor: "pointer", fontFamily: "'IBM Plex Sans',sans-serif",
          }}>
            {d === "m_to_c" ? "Meridian Advisory \u2192 Cascadia Clients" : "Cascadia BPM \u2192 Meridian Clients"}
          </button>
        ))}
      </div>

      {/* Pipeline table */}
      <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "'IBM Plex Mono','JetBrains Mono',monospace", fontSize: 14 }}>
          <thead>
            <tr style={{ borderBottom: `2px solid ${COLORS.accent}` }}>
              <th style={thS}>Customer</th>
              <th style={thS}>Recommended Service</th>
              <th style={thR}>Score</th>
              <th style={thR}>Est. ACV</th>
              <th style={thS}>Industry</th>
              <th style={thS}>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {candidates.map((c) => {
              const isExp = expanded === c.customer_id;
              return (
                <React.Fragment key={c.customer_id}>
                  <tr onClick={() => setExpanded(isExp ? null : c.customer_id)} style={{
                    borderBottom: `1px solid ${COLORS.border}22`, cursor: "pointer",
                    background: isExp ? COLORS.surfaceHover : "transparent",
                  }}>
                    <td style={{ padding: "8px 12px", color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>
                      <span style={{ color: COLORS.accent, marginRight: 6, fontSize: 14 }}>{isExp ? "\u25BE" : "\u25B8"}</span>
                      {c.customer_name}
                    </td>
                    <td style={{ padding: "8px 12px", color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>{c.recommended_service}</td>
                    <td style={{ textAlign: "right", padding: "8px 12px", fontWeight: 600, color: c.propensity_score >= 80 ? COLORS.green : c.propensity_score >= 60 ? COLORS.accent : COLORS.textMuted }}>
                      {c.propensity_score}
                    </td>
                    <td style={{ textAlign: "right", padding: "8px 12px", color: COLORS.text }}>{fmtDollar(c.estimated_acv)}</td>
                    <td style={{ padding: "8px 12px", color: COLORS.textMuted, fontFamily: "'IBM Plex Sans',sans-serif", fontSize: 15 }}>{c.industry}</td>
                    <td style={{ padding: "8px 12px" }}>
                      <span style={{ fontSize: 14, padding: "2px 8px", borderRadius: 3, fontWeight: 600,
                        background: c.propensity_score >= 80 ? COLORS.greenBg : c.propensity_score >= 60 ? "rgba(199,120,64,0.08)" : COLORS.redBg,
                        color: c.propensity_score >= 80 ? COLORS.green : c.propensity_score >= 60 ? COLORS.accent : COLORS.red,
                      }}>{fmtScore(c.propensity_score)}</span>
                    </td>
                  </tr>
                  {isExp && (
                    <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                      <td colSpan={6} style={{ padding: "12px 20px 16px", background: COLORS.surface }}>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, fontSize: 14, fontFamily: "'IBM Plex Sans',sans-serif" }}>
                          <div><span style={{ color: COLORS.textDim }}>Buyer Persona:</span> <span style={{ color: COLORS.text }}>{c.buyer_persona}</span></div>
                          <div><span style={{ color: COLORS.textDim }}>Years as Client:</span> <span style={{ color: COLORS.text }}>{c.years_as_client}</span></div>
                          <div><span style={{ color: COLORS.textDim }}>Industry Match:</span> <span style={{ color: COLORS.text }}>{c.industry_match}/25</span></div>
                          <div><span style={{ color: COLORS.textDim }}>Size Match:</span> <span style={{ color: COLORS.text }}>{c.size_match}/20</span></div>
                          <div><span style={{ color: COLORS.textDim }}>Behavioral:</span> <span style={{ color: COLORS.text }}>{c.behavioral_score}/30</span></div>
                          <div><span style={{ color: COLORS.textDim }}>Engagement Fit:</span> <span style={{ color: COLORS.text }}>{c.engagement_fit}/15</span></div>
                          <div><span style={{ color: COLORS.textDim }}>Relationship:</span> <span style={{ color: COLORS.text }}>{c.relationship_strength}/10</span></div>
                          <div><span style={{ color: COLORS.textDim }}>Current Engagement:</span> <span style={{ color: COLORS.text }}>{fmtDollar(c.customer_engagement_M)}</span></div>
                        </div>
                        <div style={{ marginTop: 12, padding: "10px 14px", background: COLORS.bg, borderRadius: 6, fontSize: 14, color: COLORS.textMuted, lineHeight: 1.5 }}>
                          <span style={{ fontWeight: 600, color: COLORS.text }}>Rationale:</span> {c.rationale}
                        </div>
                        {c.comparable_customers.length > 0 && (
                          <div style={{ marginTop: 8, fontSize: 15, color: COLORS.textDim }}>
                            <span style={{ fontWeight: 600 }}>Comparable:</span> {c.comparable_customers.join(", ")}
                          </div>
                        )}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ============================================================
// REVENUE BY CUSTOMER TAB
// ============================================================

function RevenueByCustomerTab({ entityId }: { entityId: string }) {
  const [data, setData] = useState<RevenueByCustomerData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchRevenueByCustomer(entityId)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [entityId]);

  if (loading) return <LoadingState message="Loading revenue by customer..." />;
  if (error || !data) return <ErrorState error={error || "No data"} onRetry={() => { setLoading(true); setError(null); fetchRevenueByCustomer(entityId).then(setData).catch((e) => setError(String(e))).finally(() => setLoading(false)); }} />;

  const thS: React.CSSProperties = { textAlign: "left", padding: "8px 12px", color: COLORS.textMuted, fontWeight: 500, fontSize: 14, letterSpacing: "0.06em", textTransform: "uppercase", fontFamily: "'JetBrains Mono',monospace" };
  const thR: React.CSSProperties = { ...thS, textAlign: "right" };
  const tdR: React.CSSProperties = { textAlign: "right", padding: "8px 12px", fontFamily: "'IBM Plex Mono',monospace", fontSize: 14 };

  const top20 = data.customers.slice(0, 20);
  const top20Total = top20.reduce((s, c) => s + c.total, 0);
  const coverageRatio = data.total_revenue > 0 ? (top20Total / data.total_revenue * 100) : 0;

  // Format quarter label: "2024-Q1" -> "Q1 '24"
  const fmtQ = (q: string) => {
    const [y, qn] = q.split("-");
    return `${qn} '${y.slice(2)}`;
  };

  const provMode = data.provenance?.mode?.toLowerCase();
  const isVerified = provMode === "ingest" || provMode === "live";

  return (
    <div>
      {/* Summary row */}
      <div style={{ display: "flex", gap: 16, marginBottom: 24, flexWrap: "wrap" }}>
        {[
          { label: "Total Revenue", value: `$${data.total_revenue.toFixed(1)}M` },
          { label: "Customers", value: String(data.customer_count) },
          { label: "Top 20 Coverage", value: `${coverageRatio.toFixed(1)}%`, sub: `$${top20Total.toFixed(1)}M of $${data.total_revenue.toFixed(1)}M` },
          { label: "Data Source", value: isVerified ? "Verified" : data.provenance?.mode || "Unknown", sub: data.provenance?.run_id ? `Run: ${data.provenance.run_id.slice(0, 20)}...` : undefined },
        ].map((card) => (
          <div key={card.label} style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "16px 20px", flex: "1 1 180px", minWidth: 180 }}>
            <div style={{ fontSize: 15, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono',monospace" }}>{card.label}</div>
            <div style={{ fontSize: 26, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace", marginTop: 4 }}>{card.value}</div>
            {card.sub && <div style={{ fontSize: 14, color: COLORS.textDim, marginTop: 2 }}>{card.sub}</div>}
          </div>
        ))}
      </div>

      {/* Quarterly revenue table */}
      <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, overflow: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "'IBM Plex Mono','JetBrains Mono',monospace", fontSize: 14 }}>
          <thead>
            <tr style={{ borderBottom: `2px solid ${COLORS.accent}` }}>
              <th style={thS}>Customer</th>
              {data.quarters.map((q) => <th key={q} style={thR}>{fmtQ(q)}</th>)}
              <th style={{ ...thR, fontWeight: 700 }}>Total</th>
            </tr>
          </thead>
          <tbody>
            {top20.map((c) => (
              <tr key={c.name} style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                <td style={{ padding: "8px 12px", color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>{c.name}</td>
                {data.quarters.map((q) => {
                  const v = c[q] as number;
                  return <td key={q} style={{ ...tdR, color: v > 0 ? COLORS.text : COLORS.textDim }}>{v > 0 ? v.toFixed(2) : "\u2014"}</td>;
                })}
                <td style={{ ...tdR, fontWeight: 600, color: COLORS.text }}>{c.total.toFixed(2)}</td>
              </tr>
            ))}
            {/* Reconciliation row */}
            <tr style={{ borderTop: `2px solid ${COLORS.accent}`, background: COLORS.surfaceHover }}>
              <td style={{ padding: "8px 12px", fontWeight: 700, color: COLORS.accent, fontFamily: "'IBM Plex Sans',sans-serif" }}>Top 20 Subtotal</td>
              {data.quarters.map((q) => {
                const qTotal = top20.reduce((s, c) => s + ((c[q] as number) || 0), 0);
                return <td key={q} style={{ ...tdR, fontWeight: 600, color: COLORS.accent }}>{qTotal.toFixed(2)}</td>;
              })}
              <td style={{ ...tdR, fontWeight: 700, color: COLORS.accent }}>{top20Total.toFixed(2)}</td>
            </tr>
            <tr style={{ background: COLORS.surfaceHover }}>
              <td style={{ padding: "8px 12px", fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>Total Revenue</td>
              {data.quarters.map((q) => {
                const qTotal = data.customers.reduce((s, c) => s + ((c[q] as number) || 0), 0);
                return <td key={q} style={{ ...tdR, fontWeight: 600, color: COLORS.text }}>{qTotal.toFixed(2)}</td>;
              })}
              <td style={{ ...tdR, fontWeight: 700, color: COLORS.text }}>{data.total_revenue.toFixed(2)}</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* AR by Customer note */}
      <div style={{ marginTop: 16, padding: "12px 16px", background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, fontSize: 14, color: COLORS.textMuted }}>
        <strong>Note:</strong> AR by Customer data is not available. Farm does not generate accounts receivable at customer granularity.
      </div>
    </div>
  );
}

// ============================================================
// EBITDA BRIDGE TAB
// ============================================================

function EBITDABridgeTab() {
  const [data, setData] = useState<EBITDABridgeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedAdj, setExpandedAdj] = useState<string | null>(null);
  const [expandedKpi, setExpandedKpi] = useState<string | null>(null);

  useEffect(() => {
    fetchEBITDABridge()
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingState message="Loading EBITDA bridge..." />;
  if (error || !data) return <ErrorState error={error || "No data"} onRetry={() => { setLoading(true); setError(null); fetchEBITDABridge().then(setData).catch((e) => setError(String(e))).finally(() => setLoading(false)); }} />;

  const rep = data.reported_ebitda;
  const ea = data.entity_adjusted_ebitda;
  const pf = data.pro_forma_ebitda;
  const ev = data.ev_impact;

  function BridgeLine({ adj, isSubtract }: { adj: BridgeAdjustment; isSubtract?: boolean }) {
    const isExp = expandedAdj === adj.name;
    return (
      <>
        <tr onClick={() => setExpandedAdj(isExp ? null : adj.name)} style={{ cursor: "pointer", borderBottom: `1px solid ${COLORS.border}22`, background: isExp ? COLORS.surfaceHover : "transparent" }}>
          <td style={{ padding: "8px 16px 8px 32px", color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif", fontSize: 15 }}>
            <span style={{ color: COLORS.accent, marginRight: 6, fontSize: 14 }}>{isExp ? "\u25BE" : "\u25B8"}</span>
            {isSubtract ? "\u2212 " : "+ "}{adj.name}
          </td>
          <td style={{ textAlign: "right", padding: "8px 16px", color: isSubtract ? COLORS.red : COLORS.green, fontSize: 15, fontFamily: "'IBM Plex Mono',monospace" }}>
            {isSubtract ? `(${fmtDollar(Math.abs(adj.amount))})` : fmtDollar(adj.amount)}
          </td>
          <td style={{ textAlign: "center", padding: "8px 12px" }}>
            <span style={{ fontSize: 14, padding: "2px 8px", borderRadius: 3, fontWeight: 600, color: confidenceColor(adj.confidence), background: adj.confidence === "high" ? COLORS.greenBg : adj.confidence === "medium" ? "rgba(199,120,64,0.08)" : COLORS.redBg }}>
              {adj.confidence.toUpperCase()}
            </span>
          </td>
        </tr>
        {isExp && (
          <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
            <td colSpan={3} style={{ padding: "8px 20px 12px 48px", background: COLORS.surface }}>
              <div style={{ fontSize: 14, color: COLORS.textMuted, lineHeight: 1.5, fontFamily: "'IBM Plex Sans',sans-serif" }}>
                <div><span style={{ color: COLORS.textDim }}>Range:</span> {fmtDollar(adj.amount_low)} — {fmtDollar(adj.amount_high)}</div>
                <div><span style={{ color: COLORS.textDim }}>Category:</span> {adj.category.replace(/_/g, " ")}</div>
                {adj.lever && <div><span style={{ color: COLORS.textDim }}>Lever:</span> {adj.lever}</div>}
                <div style={{ marginTop: 6 }}><span style={{ color: COLORS.textDim }}>Support:</span> {adj.support_reference}</div>
                <div style={{ marginTop: 4 }}>{adj.rationale}</div>
              </div>
            </td>
          </tr>
        )}
      </>
    );
  }

  const bridgeThS: React.CSSProperties = { textAlign: "left", padding: "8px 16px", color: COLORS.textMuted, fontWeight: 500, fontSize: 14, letterSpacing: "0.06em", textTransform: "uppercase", fontFamily: "'JetBrains Mono',monospace" };

  return (
    <div>
      {/* Summary KPIs — drillable */}
      <div style={{ display: "flex", flexDirection: "column", gap: 0, marginBottom: 24 }}>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
          {([
            { id: "reported", label: "Reported EBITDA", value: fmtDollar(rep.combined_reported) },
            { id: "adjusted", label: "Entity Adjusted", value: fmtDollar(ea.combined) },
            { id: "pf_yr1", label: "Pro Forma Yr 1", value: fmtDollar(pf.year_1.current) },
            { id: "pf_ss", label: "Pro Forma Steady State", value: fmtDollar(pf.steady_state.current) },
            { id: "ev", label: `EV @ ${ev.multiple}x`, value: fmtDollar(ev.steady_state_ev.current) },
          ] as const).map((kpi) => {
            const isExp = expandedKpi === kpi.id;
            return (
              <div key={kpi.id} onClick={() => setExpandedKpi(isExp ? null : kpi.id)} style={{ background: isExp ? COLORS.surfaceHover : COLORS.surface, border: `1px solid ${isExp ? COLORS.accent : COLORS.border}`, borderRadius: 8, padding: "14px 18px", flex: "1 1 160px", cursor: "pointer", transition: "border-color 0.15s" }}>
                <div style={{ fontSize: 14, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono',monospace" }}>
                  <span style={{ color: COLORS.accent, marginRight: 4, fontSize: 10 }}>{isExp ? "\u25BE" : "\u25B8"}</span>
                  {kpi.label}
                </div>
                <div style={{ fontSize: 22, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace", marginTop: 4 }}>{kpi.value}</div>
              </div>
            );
          })}
        </div>

        {/* KPI drill-through panel */}
        {expandedKpi && (
          <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.accent}`, borderTop: "none", borderRadius: "0 0 8px 8px", padding: "16px 20px", marginTop: -1 }}>
            {expandedKpi === "reported" && (
              <div>
                <div style={{ fontSize: 15, fontWeight: 600, color: COLORS.accent, marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Reported EBITDA by Entity</div>
                <table style={{ width: "100%", maxWidth: 400, borderCollapse: "collapse", fontSize: 14 }}>
                  <tbody>
                    <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                      <td style={{ padding: "6px 0", color: COLORS.textMuted }}>Meridian</td>
                      <td style={{ textAlign: "right", padding: "6px 0", color: COLORS.text, fontWeight: 600, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(rep.meridian)}</td>
                    </tr>
                    <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                      <td style={{ padding: "6px 0", color: COLORS.textMuted }}>Cascadia</td>
                      <td style={{ textAlign: "right", padding: "6px 0", color: COLORS.text, fontWeight: 600, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(rep.cascadia)}</td>
                    </tr>
                    <tr style={{ borderTop: `1px solid ${COLORS.borderLight}` }}>
                      <td style={{ padding: "6px 0", color: COLORS.text, fontWeight: 700 }}>Combined</td>
                      <td style={{ textAlign: "right", padding: "6px 0", color: COLORS.text, fontWeight: 700, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(rep.combined_reported)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
            {expandedKpi === "adjusted" && (
              <div>
                <div style={{ fontSize: 15, fontWeight: 600, color: COLORS.accent, marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Entity-Adjusted EBITDA</div>
                <table style={{ width: "100%", maxWidth: 500, borderCollapse: "collapse", fontSize: 14 }}>
                  <thead>
                    <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                      <th style={{ textAlign: "left", padding: "4px 0", color: COLORS.textDim, fontSize: 14 }}></th>
                      <th style={{ textAlign: "right", padding: "4px 8px", color: COLORS.textDim, fontSize: 14 }}>MERIDIAN</th>
                      <th style={{ textAlign: "right", padding: "4px 8px", color: COLORS.textDim, fontSize: 14 }}>CASCADIA</th>
                      <th style={{ textAlign: "right", padding: "4px 0", color: COLORS.textDim, fontSize: 14 }}>COMBINED</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                      <td style={{ padding: "6px 0", color: COLORS.textMuted }}>Reported</td>
                      <td style={{ textAlign: "right", padding: "6px 8px", color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(rep.meridian)}</td>
                      <td style={{ textAlign: "right", padding: "6px 8px", color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(rep.cascadia)}</td>
                      <td style={{ textAlign: "right", padding: "6px 0", color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(rep.combined_reported)}</td>
                    </tr>
                    {data.entity_adjustments.map((adj) => (
                      <tr key={adj.name} style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                        <td style={{ padding: "6px 0", color: COLORS.textMuted, fontSize: 15 }}>{adj.name}</td>
                        <td colSpan={2} style={{ textAlign: "center", padding: "6px 8px", color: COLORS.textDim, fontSize: 14 }}>{adj.entity}</td>
                        <td style={{ textAlign: "right", padding: "6px 0", color: adj.amount >= 0 ? COLORS.green : COLORS.red, fontFamily: "'IBM Plex Mono',monospace" }}>{adj.amount >= 0 ? "+" : ""}{fmtDollar(adj.amount)}</td>
                      </tr>
                    ))}
                    <tr style={{ borderTop: `1px solid ${COLORS.borderLight}` }}>
                      <td style={{ padding: "6px 0", color: COLORS.text, fontWeight: 700 }}>Adjusted</td>
                      <td style={{ textAlign: "right", padding: "6px 8px", color: COLORS.text, fontWeight: 700, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(ea.meridian)}</td>
                      <td style={{ textAlign: "right", padding: "6px 8px", color: COLORS.text, fontWeight: 700, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(ea.cascadia)}</td>
                      <td style={{ textAlign: "right", padding: "6px 0", color: COLORS.text, fontWeight: 700, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(ea.combined)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
            {expandedKpi === "pf_yr1" && (
              <div>
                <div style={{ fontSize: 15, fontWeight: 600, color: COLORS.accent, marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Pro Forma Year 1 — Range</div>
                <div style={{ display: "flex", gap: 32, alignItems: "center" }}>
                  <div>
                    <div style={{ fontSize: 14, color: COLORS.textDim }}>LOW</div>
                    <div style={{ fontSize: 18, fontWeight: 600, color: COLORS.red, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(pf.year_1.low)}</div>
                  </div>
                  <div style={{ flex: 1, height: 6, background: COLORS.bg, borderRadius: 3, position: "relative", maxWidth: 200 }}>
                    <div style={{ position: "absolute", left: 0, top: 0, height: 6, borderRadius: 3, background: `linear-gradient(90deg, ${COLORS.red}, ${COLORS.green})`, width: "100%" }} />
                    <div style={{ position: "absolute", top: -4, height: 14, width: 3, background: COLORS.accent, borderRadius: 1, left: `${pf.year_1.high === pf.year_1.low ? 50 : ((pf.year_1.current - pf.year_1.low) / (pf.year_1.high - pf.year_1.low)) * 100}%` }} />
                  </div>
                  <div>
                    <div style={{ fontSize: 14, color: COLORS.textDim }}>HIGH</div>
                    <div style={{ fontSize: 18, fontWeight: 600, color: COLORS.green, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(pf.year_1.high)}</div>
                  </div>
                  <div style={{ borderLeft: `1px solid ${COLORS.border}`, paddingLeft: 24 }}>
                    <div style={{ fontSize: 14, color: COLORS.textDim }}>CURRENT</div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(pf.year_1.current)}</div>
                  </div>
                </div>
                <div style={{ marginTop: 12, fontSize: 15, color: COLORS.textMuted }}>
                  Synergies applied: {data.combination_synergies.length} items totaling {fmtDollar(data.combination_synergies.reduce((s, a) => s + a.amount, 0))}
                </div>
              </div>
            )}
            {expandedKpi === "pf_ss" && (
              <div>
                <div style={{ fontSize: 15, fontWeight: 600, color: COLORS.accent, marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Pro Forma Steady State — Range</div>
                <div style={{ display: "flex", gap: 32, alignItems: "center" }}>
                  <div>
                    <div style={{ fontSize: 14, color: COLORS.textDim }}>LOW</div>
                    <div style={{ fontSize: 18, fontWeight: 600, color: COLORS.red, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(pf.steady_state.low)}</div>
                  </div>
                  <div style={{ flex: 1, height: 6, background: COLORS.bg, borderRadius: 3, position: "relative", maxWidth: 200 }}>
                    <div style={{ position: "absolute", left: 0, top: 0, height: 6, borderRadius: 3, background: `linear-gradient(90deg, ${COLORS.red}, ${COLORS.green})`, width: "100%" }} />
                    <div style={{ position: "absolute", top: -4, height: 14, width: 3, background: COLORS.accent, borderRadius: 1, left: `${pf.steady_state.high === pf.steady_state.low ? 50 : ((pf.steady_state.current - pf.steady_state.low) / (pf.steady_state.high - pf.steady_state.low)) * 100}%` }} />
                  </div>
                  <div>
                    <div style={{ fontSize: 14, color: COLORS.textDim }}>HIGH</div>
                    <div style={{ fontSize: 18, fontWeight: 600, color: COLORS.green, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(pf.steady_state.high)}</div>
                  </div>
                  <div style={{ borderLeft: `1px solid ${COLORS.border}`, paddingLeft: 24 }}>
                    <div style={{ fontSize: 14, color: COLORS.textDim }}>CURRENT</div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(pf.steady_state.current)}</div>
                  </div>
                </div>
                <div style={{ marginTop: 12, fontSize: 15, color: COLORS.textMuted }}>
                  Full synergy realization assumed at steady state
                </div>
              </div>
            )}
            {expandedKpi === "ev" && (
              <div>
                <div style={{ fontSize: 15, fontWeight: 600, color: COLORS.accent, marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Enterprise Value Impact @ {ev.multiple}x Multiple</div>
                <table style={{ width: "100%", maxWidth: 500, borderCollapse: "collapse", fontSize: 14 }}>
                  <thead>
                    <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                      <th style={{ textAlign: "left", padding: "4px 0", color: COLORS.textDim, fontSize: 14 }}></th>
                      <th style={{ textAlign: "right", padding: "4px 8px", color: COLORS.textDim, fontSize: 14 }}>LOW</th>
                      <th style={{ textAlign: "right", padding: "4px 8px", color: COLORS.textDim, fontSize: 14 }}>CURRENT</th>
                      <th style={{ textAlign: "right", padding: "4px 0", color: COLORS.textDim, fontSize: 14 }}>HIGH</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                      <td style={{ padding: "6px 0", color: COLORS.textMuted }}>Year 1 EV</td>
                      <td style={{ textAlign: "right", padding: "6px 8px", color: COLORS.red, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(ev.year_1_ev.low)}</td>
                      <td style={{ textAlign: "right", padding: "6px 8px", color: COLORS.text, fontWeight: 600, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(ev.year_1_ev.current)}</td>
                      <td style={{ textAlign: "right", padding: "6px 0", color: COLORS.green, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(ev.year_1_ev.high)}</td>
                    </tr>
                    <tr>
                      <td style={{ padding: "6px 0", color: COLORS.text, fontWeight: 600 }}>Steady State EV</td>
                      <td style={{ textAlign: "right", padding: "6px 8px", color: COLORS.red, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(ev.steady_state_ev.low)}</td>
                      <td style={{ textAlign: "right", padding: "6px 8px", color: COLORS.text, fontWeight: 700, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(ev.steady_state_ev.current)}</td>
                      <td style={{ textAlign: "right", padding: "6px 0", color: COLORS.green, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(ev.steady_state_ev.high)}</td>
                    </tr>
                  </tbody>
                </table>
                <div style={{ marginTop: 10, fontSize: 15, color: COLORS.textMuted }}>
                  EV delta from reported: {fmtDollar(ev.steady_state_ev.current - rep.combined_reported * ev.multiple)} incremental value created
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Bridge waterfall table */}
      <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 15 }}>
          <thead>
            <tr style={{ borderBottom: `2px solid ${COLORS.accent}` }}>
              <th style={bridgeThS}>EBITDA Bridge</th>
              <th style={{ ...bridgeThS, textAlign: "right" }}>Amount</th>
              <th style={{ ...bridgeThS, textAlign: "center" }}>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {/* Reported */}
            <tr style={{ background: COLORS.totalBg, borderBottom: `1px solid ${COLORS.borderLight}` }}>
              <td style={{ padding: "10px 16px", fontWeight: 600, color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>Reported EBITDA (Combined)</td>
              <td style={{ textAlign: "right", padding: "10px 16px", fontWeight: 600, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(rep.combined_reported)}</td>
              <td></td>
            </tr>

            {/* Entity adjustments header */}
            <tr><td colSpan={3} style={{ padding: "12px 16px 4px", fontSize: 15, fontWeight: 600, color: COLORS.accent, letterSpacing: "0.06em", textTransform: "uppercase", fontFamily: "'JetBrains Mono',monospace" }}>Entity-Level Adjustments</td></tr>
            {data.entity_adjustments.map((adj) => <BridgeLine key={adj.name} adj={adj} />)}

            {/* Entity adjusted subtotal */}
            <tr style={{ background: COLORS.totalBg, borderTop: `1px solid ${COLORS.borderLight}`, borderBottom: `1px solid ${COLORS.borderLight}` }}>
              <td style={{ padding: "10px 16px", fontWeight: 600, color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>Entity-Level Adjusted EBITDA</td>
              <td style={{ textAlign: "right", padding: "10px 16px", fontWeight: 600, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(ea.combined)}</td>
              <td></td>
            </tr>

            {/* Combination synergies header */}
            <tr><td colSpan={3} style={{ padding: "12px 16px 4px", fontSize: 15, fontWeight: 600, color: COLORS.accent, letterSpacing: "0.06em", textTransform: "uppercase", fontFamily: "'JetBrains Mono',monospace" }}>Combination Synergies</td></tr>
            {data.combination_synergies.map((syn) => (
              <BridgeLine key={syn.name} adj={syn} isSubtract={syn.category === "dis_synergy"} />
            ))}

            {/* Pro forma */}
            <tr style={{ background: COLORS.totalBg, borderTop: `2px solid ${COLORS.accent}` }}>
              <td style={{ padding: "10px 16px", fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>Pro Forma Adjusted EBITDA (Yr 1)</td>
              <td style={{ textAlign: "right", padding: "10px 16px", fontWeight: 700, color: COLORS.green, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(pf.year_1.current)}</td>
              <td></td>
            </tr>
            <tr style={{ background: COLORS.totalBg }}>
              <td style={{ padding: "10px 16px", fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>Pro Forma Adjusted EBITDA (Steady State)</td>
              <td style={{ textAlign: "right", padding: "10px 16px", fontWeight: 700, color: COLORS.green, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(pf.steady_state.current)}</td>
              <td></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ============================================================
// PIPELINE TAB
// ============================================================

function PipelineTab({ period }: { period: string }) {
  const [data, setData] = useState<PipelineReportData[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchPipelineReport(period)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, [period]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingState message="Loading pipeline data..." />;
  if (error || !data) return <ErrorState error={error || "No data"} onRetry={load} />;

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 24 }}>
      {data.map((panel) => (
        <div key={panel.entity_id} style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, padding: 20 }}>
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 16, fontWeight: 600, color: COLORS.text }}>{panel.entity_name}</div>
            <div style={{ fontSize: 15, color: COLORS.textDim }}>{panel.period}</div>
          </div>
          {panel.stages.length > 0 ? (
            <React.Suspense fallback={<div style={{ height: 120, background: COLORS.bg, borderRadius: 4 }} />}>
              <SalesFunnel data={{ title: '', stages: panel.stages, unit: "usd_millions", format: "currency" }} />
            </React.Suspense>
          ) : (
            <div style={{ padding: 24, textAlign: "center", color: COLORS.textMuted, fontSize: 15 }}>
              Pipeline data not available for {panel.entity_name}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

// ============================================================
// WHAT-IF TAB
// ============================================================

function WhatIfTab() {
  const [result, setResult] = useState<WhatIfResult | null>(null);
  const [levers, setLevers] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [wiKpi, setWiKpi] = useState<string | null>(null);

  useEffect(() => {
    fetchWhatIf()
      .then((r) => { setResult(r); setLevers(r.levers); })
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, []);

  const applyPreset = useCallback(async (preset: string) => {
    setLoading(true);
    try {
      const r = await fetchWhatIf(undefined, preset);
      setResult(r);
      setLevers(r.levers);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  const applyLevers = useCallback(async (newLevers: Record<string, number>) => {
    setLevers(newLevers);
    try {
      const r = await fetchWhatIf(newLevers);
      setResult(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  if (loading && !result) return <LoadingState message="Loading what-if engine..." />;
  if (error && !result) return <ErrorState error={error} onRetry={() => { setLoading(true); setError(null); fetchWhatIf().then((r) => { setResult(r); setLevers(r.levers); }).catch((e) => setError(String(e))).finally(() => setLoading(false)); }} />;
  if (!result) return null;

  const defs = result.lever_definitions || [];
  const presetNames = result.presets ? Object.keys(result.presets) : [];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "340px 1fr", gap: 24 }}>
      {/* Left: Levers */}
      <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, padding: "16px 20px", maxHeight: "70vh", overflowY: "auto" }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: COLORS.accent, marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono',monospace" }}>Sensitivity Levers</div>

        {/* Presets */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 16 }}>
          {presetNames.map((p) => (
            <button key={p} onClick={() => applyPreset(p)} style={{
              padding: "4px 10px", fontSize: 14, fontWeight: 600, cursor: "pointer",
              background: "rgba(199,120,64,0.08)", color: COLORS.accent,
              border: `1px solid ${COLORS.accent}33`, borderRadius: 3,
              fontFamily: "'JetBrains Mono',monospace", textTransform: "uppercase",
            }}>{p.replace(/_/g, " ")}</button>
          ))}
        </div>

        {defs.map((d) => (
          <div key={d.name} style={{ marginBottom: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
              <span style={{ fontSize: 15, color: COLORS.textMuted, fontFamily: "'IBM Plex Sans',sans-serif" }}>{d.label}</span>
              <span style={{ fontSize: 14, fontWeight: 600, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>
                {levers[d.name] ?? d.default}{d.unit === "%" ? "%" : d.unit === "x" ? "x" : d.unit === "$M" ? "M" : d.unit === "months" ? "mo" : ""}
              </span>
            </div>
            <input type="range" min={d.min} max={d.max} step={d.unit === "x" ? 0.5 : 1}
              value={levers[d.name] ?? d.default}
              onChange={(e) => {
                const val = parseFloat(e.target.value);
                const next = { ...levers, [d.name]: val };
                applyLevers(next);
              }}
              style={{ width: "100%", accentColor: COLORS.accent }}
            />
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 14, color: COLORS.textDim }}>
              <span>{d.min}{d.unit === "%" ? "%" : ""}</span>
              <span>{d.max}{d.unit === "%" ? "%" : ""}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Right: Results */}
      <div>
        {/* KPI boxes — drillable */}
        <div style={{ display: "flex", flexDirection: "column", gap: 0, marginBottom: 20 }}>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            {([
              { id: "wi_reported", label: "Reported EBITDA", value: fmtDollar(result.reported_ebitda) },
              { id: "wi_adjusted", label: "Entity Adjusted", value: fmtDollar(result.entity_adjusted_ebitda) },
              { id: "wi_pf1", label: "Pro Forma Yr 1", value: fmtDollar(result.pro_forma_ebitda.year_1) },
              { id: "wi_pfss", label: "Pro Forma SS", value: fmtDollar(result.pro_forma_ebitda.steady_state) },
              { id: "wi_ev1", label: "EV (Yr 1)", value: fmtDollar(result.ev_impact.year_1) },
              { id: "wi_evss", label: "EV (SS)", value: fmtDollar(result.ev_impact.steady_state) },
            ] as const).map((kpi) => {
              const isExp = wiKpi === kpi.id;
              return (
                <div key={kpi.id} onClick={() => setWiKpi(isExp ? null : kpi.id)} style={{ background: isExp ? COLORS.surfaceHover : COLORS.surface, border: `1px solid ${isExp ? COLORS.accent : COLORS.border}`, borderRadius: 8, padding: "12px 16px", flex: "1 1 140px", cursor: "pointer", transition: "border-color 0.15s" }}>
                  <div style={{ fontSize: 14, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono',monospace" }}>
                    <span style={{ color: COLORS.accent, marginRight: 4, fontSize: 10 }}>{isExp ? "\u25BE" : "\u25B8"}</span>
                    {kpi.label}
                  </div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace", marginTop: 2 }}>{kpi.value}</div>
                </div>
              );
            })}
          </div>

          {/* Drill-through panel */}
          {wiKpi && (() => {
            const adjTotal = (result.adjustments || []).reduce((s, a) => s + a.amount, 0);
            const synTotal = (result.synergies || []).reduce((s, a) => s + a.amount, 0);
            const adjRows = result.adjustments || [];
            const synRows = result.synergies || [];
            const thD: React.CSSProperties = { textAlign: "left", padding: "4px 12px", color: COLORS.textDim, fontSize: 14, fontWeight: 500 };
            const thDR: React.CSSProperties = { ...thD, textAlign: "right" };

            const adjTable = (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                    <th style={thD}>Adjustment</th>
                    <th style={thDR}>Amount</th>
                    <th style={{ ...thD, textAlign: "center" }}>Conf.</th>
                    <th style={thD}>Lever</th>
                  </tr>
                </thead>
                <tbody>
                  {adjRows.map((a) => (
                    <tr key={a.name} style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                      <td style={{ padding: "5px 12px", color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>{a.name}</td>
                      <td style={{ textAlign: "right", padding: "5px 12px", color: a.amount >= 0 ? COLORS.green : COLORS.red, fontFamily: "'IBM Plex Mono',monospace" }}>{a.amount >= 0 ? "+" : ""}{fmtDollar(a.amount)}</td>
                      <td style={{ textAlign: "center", padding: "5px 8px" }}>
                        <span style={{ fontSize: 11, padding: "1px 6px", borderRadius: 3, fontWeight: 600, color: confidenceColor(a.confidence), background: a.confidence === "high" ? COLORS.greenBg : a.confidence === "medium" ? "rgba(199,120,64,0.08)" : COLORS.redBg }}>{a.confidence.toUpperCase()}</span>
                      </td>
                      <td style={{ padding: "5px 12px", color: COLORS.textMuted, fontSize: 15 }}>{a.lever || "—"}</td>
                    </tr>
                  ))}
                  <tr style={{ borderTop: `1px solid ${COLORS.borderLight}` }}>
                    <td style={{ padding: "5px 12px", color: COLORS.text, fontWeight: 700 }}>Total Adjustments</td>
                    <td style={{ textAlign: "right", padding: "5px 12px", color: COLORS.text, fontWeight: 700, fontFamily: "'IBM Plex Mono',monospace" }}>{adjTotal >= 0 ? "+" : ""}{fmtDollar(adjTotal)}</td>
                    <td colSpan={2}></td>
                  </tr>
                </tbody>
              </table>
            );

            const synTable = (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                    <th style={thD}>Synergy</th>
                    <th style={thDR}>Amount</th>
                    <th style={{ ...thD, textAlign: "center" }}>Conf.</th>
                    <th style={thD}>Category</th>
                  </tr>
                </thead>
                <tbody>
                  {synRows.map((s) => (
                    <tr key={s.name} style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                      <td style={{ padding: "5px 12px", color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>{s.name}</td>
                      <td style={{ textAlign: "right", padding: "5px 12px", color: s.category === "dis_synergy" ? COLORS.red : COLORS.green, fontFamily: "'IBM Plex Mono',monospace" }}>
                        {s.category === "dis_synergy" ? `(${fmtDollar(Math.abs(s.amount))})` : `+${fmtDollar(s.amount)}`}
                      </td>
                      <td style={{ textAlign: "center", padding: "5px 8px" }}>
                        <span style={{ fontSize: 11, padding: "1px 6px", borderRadius: 3, fontWeight: 600, color: confidenceColor(s.confidence), background: s.confidence === "high" ? COLORS.greenBg : s.confidence === "medium" ? "rgba(199,120,64,0.08)" : COLORS.redBg }}>{s.confidence.toUpperCase()}</span>
                      </td>
                      <td style={{ padding: "5px 12px", color: COLORS.textMuted, fontSize: 15 }}>{s.category.replace(/_/g, " ")}</td>
                    </tr>
                  ))}
                  <tr style={{ borderTop: `1px solid ${COLORS.borderLight}` }}>
                    <td style={{ padding: "5px 12px", color: COLORS.text, fontWeight: 700 }}>Net Synergies</td>
                    <td style={{ textAlign: "right", padding: "5px 12px", color: COLORS.text, fontWeight: 700, fontFamily: "'IBM Plex Mono',monospace" }}>{synTotal >= 0 ? "+" : ""}{fmtDollar(synTotal)}</td>
                    <td colSpan={2}></td>
                  </tr>
                </tbody>
              </table>
            );

            return (
              <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.accent}`, borderTop: "none", borderRadius: "0 0 8px 8px", padding: "16px 20px", marginTop: -1 }}>
                {wiKpi === "wi_reported" && (
                  <div>
                    <div style={{ fontSize: 15, fontWeight: 600, color: COLORS.accent, marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.06em" }}>Reported EBITDA — Baseline</div>
                    <div style={{ fontSize: 14, color: COLORS.textMuted, lineHeight: 1.6 }}>
                      <div>This is the unadjusted, as-reported combined EBITDA before any normalization adjustments or synergy assumptions.</div>
                      <div style={{ marginTop: 8, display: "flex", gap: 24 }}>
                        <div><span style={{ color: COLORS.textDim }}>Value:</span> <span style={{ fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(result.reported_ebitda)}</span></div>
                        <div><span style={{ color: COLORS.textDim }}>Adjustments pending:</span> <span style={{ fontWeight: 600, color: COLORS.accent }}>{adjRows.length} items ({adjTotal >= 0 ? "+" : ""}{fmtDollar(adjTotal)})</span></div>
                      </div>
                    </div>
                  </div>
                )}
                {wiKpi === "wi_adjusted" && (
                  <div>
                    <div style={{ fontSize: 15, fontWeight: 600, color: COLORS.accent, marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Entity-Adjusted EBITDA Build-Up</div>
                    <div style={{ fontSize: 14, color: COLORS.textMuted, marginBottom: 10 }}>
                      Reported {fmtDollar(result.reported_ebitda)} + adjustments {adjTotal >= 0 ? "+" : ""}{fmtDollar(adjTotal)} = <span style={{ fontWeight: 700, color: COLORS.text }}>{fmtDollar(result.entity_adjusted_ebitda)}</span>
                    </div>
                    {adjTable}
                  </div>
                )}
                {wiKpi === "wi_pf1" && (
                  <div>
                    <div style={{ fontSize: 15, fontWeight: 600, color: COLORS.accent, marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Pro Forma Year 1 Build-Up</div>
                    <div style={{ fontSize: 14, color: COLORS.textMuted, marginBottom: 10 }}>
                      Adjusted {fmtDollar(result.entity_adjusted_ebitda)} + net synergies {synTotal >= 0 ? "+" : ""}{fmtDollar(synTotal)} = <span style={{ fontWeight: 700, color: COLORS.green }}>{fmtDollar(result.pro_forma_ebitda.year_1)}</span>
                    </div>
                    {synTable}
                  </div>
                )}
                {wiKpi === "wi_pfss" && (
                  <div>
                    <div style={{ fontSize: 15, fontWeight: 600, color: COLORS.accent, marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Pro Forma Steady State Build-Up</div>
                    <div style={{ fontSize: 14, color: COLORS.textMuted, marginBottom: 10 }}>
                      Adjusted {fmtDollar(result.entity_adjusted_ebitda)} + full synergy realization {synTotal >= 0 ? "+" : ""}{fmtDollar(synTotal)} = <span style={{ fontWeight: 700, color: COLORS.green }}>{fmtDollar(result.pro_forma_ebitda.steady_state)}</span>
                    </div>
                    <div style={{ marginBottom: 12 }}>{synTable}</div>
                    <div style={{ fontSize: 15, color: COLORS.textMuted, fontStyle: "italic" }}>Steady state assumes 100% synergy realization (typically 24–36 months post-close)</div>
                  </div>
                )}
                {wiKpi === "wi_ev1" && (
                  <div>
                    <div style={{ fontSize: 15, fontWeight: 600, color: COLORS.accent, marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Enterprise Value — Year 1</div>
                    <div style={{ fontSize: 14, color: COLORS.textMuted, marginBottom: 12 }}>
                      Pro Forma Yr 1 EBITDA {fmtDollar(result.pro_forma_ebitda.year_1)} applied at current lever multiple
                    </div>
                    <table style={{ borderCollapse: "collapse", fontSize: 14 }}>
                      <tbody>
                        <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                          <td style={{ padding: "5px 16px 5px 0", color: COLORS.textMuted }}>Pro Forma EBITDA (Yr 1)</td>
                          <td style={{ textAlign: "right", padding: "5px 0", color: COLORS.text, fontWeight: 600, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(result.pro_forma_ebitda.year_1)}</td>
                        </tr>
                        <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                          <td style={{ padding: "5px 16px 5px 0", color: COLORS.textMuted }}>Multiple (from lever)</td>
                          <td style={{ textAlign: "right", padding: "5px 0", color: COLORS.accent, fontWeight: 600, fontFamily: "'IBM Plex Mono',monospace" }}>{levers["ev_multiple"] ?? "—"}x</td>
                        </tr>
                        <tr style={{ borderTop: `1px solid ${COLORS.borderLight}` }}>
                          <td style={{ padding: "5px 16px 5px 0", color: COLORS.text, fontWeight: 700 }}>EV (Year 1)</td>
                          <td style={{ textAlign: "right", padding: "5px 0", color: COLORS.green, fontWeight: 700, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(result.ev_impact.year_1)}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                )}
                {wiKpi === "wi_evss" && (
                  <div>
                    <div style={{ fontSize: 15, fontWeight: 600, color: COLORS.accent, marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Enterprise Value — Steady State</div>
                    <div style={{ fontSize: 14, color: COLORS.textMuted, marginBottom: 12 }}>
                      Pro Forma SS EBITDA {fmtDollar(result.pro_forma_ebitda.steady_state)} applied at current lever multiple
                    </div>
                    <table style={{ borderCollapse: "collapse", fontSize: 14 }}>
                      <tbody>
                        <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                          <td style={{ padding: "5px 16px 5px 0", color: COLORS.textMuted }}>Pro Forma EBITDA (SS)</td>
                          <td style={{ textAlign: "right", padding: "5px 0", color: COLORS.text, fontWeight: 600, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(result.pro_forma_ebitda.steady_state)}</td>
                        </tr>
                        <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                          <td style={{ padding: "5px 16px 5px 0", color: COLORS.textMuted }}>Multiple (from lever)</td>
                          <td style={{ textAlign: "right", padding: "5px 0", color: COLORS.accent, fontWeight: 600, fontFamily: "'IBM Plex Mono',monospace" }}>{levers["ev_multiple"] ?? "—"}x</td>
                        </tr>
                        <tr style={{ borderTop: `1px solid ${COLORS.borderLight}` }}>
                          <td style={{ padding: "5px 16px 5px 0", color: COLORS.text, fontWeight: 700 }}>EV (Steady State)</td>
                          <td style={{ textAlign: "right", padding: "5px 0", color: COLORS.green, fontWeight: 700, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtDollar(result.ev_impact.steady_state)}</td>
                        </tr>
                        <tr style={{ borderTop: `1px solid ${COLORS.border}22` }}>
                          <td style={{ padding: "5px 16px 5px 0", color: COLORS.textMuted, fontSize: 15 }}>Incremental vs Reported</td>
                          <td style={{ textAlign: "right", padding: "5px 0", color: COLORS.accent, fontWeight: 600, fontFamily: "'IBM Plex Mono',monospace", fontSize: 15 }}>+{fmtDollar(result.ev_impact.steady_state - result.ev_impact.year_1)}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            );
          })()}
        </div>
      </div>
    </div>
  );
}

// ============================================================
// QofE TAB
// ============================================================

type QofESubView = "bridge" | "sustainability" | "revenue" | "working_capital" | "new_items";

function QofETab() {
  const [data, setData] = useState<QofEData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [subView, setSubView] = useState<QofESubView>("bridge");
  const [expandedAdj, setExpandedAdj] = useState<string | null>(null);

  useEffect(() => {
    fetchQofE()
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingState message="Loading Quality of Earnings..." />;
  if (error || !data) return <ErrorState error={error || "No data"} onRetry={() => { setLoading(true); setError(null); fetchQofE().then(setData).catch((e) => setError(String(e))).finally(() => setLoading(false)); }} />;

  const sus = data.sustainability_score;
  const rq = data.revenue_quality;
  const wc = data.working_capital;
  const summary = data.summary;

  const subTabs: { id: QofESubView; label: string }[] = [
    { id: "bridge", label: "Bridge" },
    { id: "sustainability", label: "Sustainability" },
    { id: "revenue", label: "Revenue Quality" },
    { id: "working_capital", label: "Working Capital" },
    { id: "new_items", label: `New Items (${data.new_items.length})` },
  ];

  const statusColor = (s: string) => s === "active" ? COLORS.green : s === "resolved" ? COLORS.textDim : s === "new" ? COLORS.accent : COLORS.red;
  const statusBg = (s: string) => s === "active" ? COLORS.greenBg : s === "resolved" ? `${COLORS.textDim}15` : s === "new" ? "rgba(199,120,64,0.08)" : COLORS.redBg;
  const trendIcon = (t: string) => t === "improving" ? "↑" : t === "worsening" ? "↓" : "→";
  const trendColor = (t: string) => t === "improving" ? COLORS.green : t === "worsening" ? COLORS.red : COLORS.textMuted;

  return (
    <div>
      {/* Top KPIs */}
      <div style={{ display: "flex", gap: 16, marginBottom: 20, flexWrap: "wrap" }}>
        <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 18px", flex: "1 1 160px" }}>
          <div style={{ fontSize: 14, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono',monospace" }}>Sustainability Score</div>
          <div style={{ fontSize: 30, fontWeight: 700, color: sus.overall >= 65 ? COLORS.green : sus.overall >= 50 ? COLORS.accent : COLORS.red, fontFamily: "'IBM Plex Mono',monospace", marginTop: 4 }}>{sus.overall.toFixed(0)}<span style={{ fontSize: 16, fontWeight: 400, color: COLORS.textMuted }}>/100</span></div>
          <div style={{ fontSize: 14, fontWeight: 600, color: COLORS.textDim, marginTop: 2 }}>Grade: {sus.grade}</div>
        </div>
        <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 18px", flex: "1 1 160px" }}>
          <div style={{ fontSize: 14, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono',monospace" }}>Adjusted EBITDA</div>
          <div style={{ fontSize: 22, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace", marginTop: 4 }}>{fmtDollar(summary.entity_adjusted_ebitda)}</div>
        </div>
        <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 18px", flex: "1 1 160px" }}>
          <div style={{ fontSize: 14, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono',monospace" }}>Adjustments</div>
          <div style={{ display: "flex", gap: 8, marginTop: 4, fontSize: 14, fontFamily: "'IBM Plex Mono',monospace" }}>
            <span style={{ color: COLORS.green }}>{summary.active_adjustments} active</span>
            <span style={{ color: COLORS.textDim }}>{summary.resolved_adjustments} resolved</span>
            <span style={{ color: COLORS.accent }}>{summary.new_adjustments} new</span>
            <span style={{ color: COLORS.red }}>{summary.changed_adjustments} changed</span>
          </div>
        </div>
        <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 18px", flex: "1 1 160px" }}>
          <div style={{ fontSize: 14, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono',monospace" }}>Period</div>
          <div style={{ fontSize: 18, fontWeight: 600, color: COLORS.text, marginTop: 4 }}>{data.period}</div>
          <div style={{ fontSize: 14, color: COLORS.textDim, marginTop: 2 }}>{data.is_initial_diligence ? "Initial Diligence" : "Ongoing QofE"}</div>
        </div>
      </div>

      {/* Sub-view tabs */}
      <div style={{ display: "flex", gap: 4, marginBottom: 20 }}>
        {subTabs.map((st) => (
          <button key={st.id} onClick={() => setSubView(st.id)} style={{
            padding: "6px 16px", fontSize: 15, fontWeight: subView === st.id ? 700 : 400,
            background: subView === st.id ? "rgba(199,120,64,0.12)" : "transparent",
            color: subView === st.id ? COLORS.accent : COLORS.textMuted,
            border: subView === st.id ? `1px solid ${COLORS.accent}44` : `1px solid ${COLORS.border}`,
            borderRadius: 6, cursor: "pointer", fontFamily: "'IBM Plex Sans',sans-serif",
          }}>{st.label}</button>
        ))}
      </div>

      {/* Sub-view content */}
      {subView === "bridge" && (
        <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                <th style={{ textAlign: "left", padding: "6px 12px", color: COLORS.textDim, fontSize: 14, textTransform: "uppercase" }}>Adjustment</th>
                <th style={{ textAlign: "right", padding: "6px 12px", color: COLORS.textDim, fontSize: 14 }}>Current</th>
                <th style={{ textAlign: "right", padding: "6px 12px", color: COLORS.textDim, fontSize: 14 }}>Diligence</th>
                <th style={{ textAlign: "right", padding: "6px 12px", color: COLORS.textDim, fontSize: 14 }}>Prior</th>
                <th style={{ textAlign: "center", padding: "6px 8px", color: COLORS.textDim, fontSize: 14 }}>Status</th>
                <th style={{ textAlign: "center", padding: "6px 8px", color: COLORS.textDim, fontSize: 14 }}>Trend</th>
                <th style={{ textAlign: "center", padding: "6px 8px", color: COLORS.textDim, fontSize: 14 }}>Conf.</th>
              </tr>
            </thead>
            <tbody>
              {data.ebitda_bridge.map((row) => {
                const isExp = expandedAdj === row.name;
                return (
                  <React.Fragment key={row.name}>
                    <tr onClick={() => setExpandedAdj(isExp ? null : row.name)} style={{ cursor: "pointer", borderBottom: `1px solid ${COLORS.border}15`, background: isExp ? COLORS.surfaceHover : "transparent" }}>
                      <td style={{ padding: "6px 12px", color: COLORS.text }}>
                        <span style={{ color: COLORS.accent, marginRight: 6, fontSize: 11 }}>{isExp ? "\u25BE" : "\u25B8"}</span>
                        {row.name}
                      </td>
                      <td style={{ textAlign: "right", padding: "6px 12px", fontFamily: "'IBM Plex Mono',monospace", color: COLORS.text }}>{fmtDollar(row.current_amount)}</td>
                      <td style={{ textAlign: "right", padding: "6px 12px", fontFamily: "'IBM Plex Mono',monospace", color: COLORS.textMuted }}>{row.diligence_amount !== null ? fmtDollar(row.diligence_amount) : "—"}</td>
                      <td style={{ textAlign: "right", padding: "6px 12px", fontFamily: "'IBM Plex Mono',monospace", color: COLORS.textMuted }}>{row.prior_amount !== null ? fmtDollar(row.prior_amount) : "—"}</td>
                      <td style={{ textAlign: "center", padding: "6px 8px" }}>
                        <span style={{ fontSize: 11, padding: "1px 6px", borderRadius: 3, fontWeight: 600, color: statusColor(row.status), background: statusBg(row.status) }}>{row.status.toUpperCase()}</span>
                      </td>
                      <td style={{ textAlign: "center", padding: "6px 8px", color: trendColor(row.trend), fontWeight: 600, fontSize: 16 }}>{trendIcon(row.trend)}</td>
                      <td style={{ textAlign: "center", padding: "6px 8px" }}>
                        <span style={{ fontSize: 11, padding: "1px 6px", borderRadius: 3, fontWeight: 600, color: confidenceColor(row.confidence), background: row.confidence === "high" ? COLORS.greenBg : row.confidence === "medium" ? "rgba(199,120,64,0.08)" : COLORS.redBg }}>{row.confidence.toUpperCase()}</span>
                      </td>
                    </tr>
                    {isExp && (
                      <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                        <td colSpan={7} style={{ padding: "8px 20px 12px 36px", background: COLORS.surface }}>
                          <div style={{ fontSize: 15, color: COLORS.textMuted, lineHeight: 1.6 }}>
                            <div><span style={{ color: COLORS.textDim }}>Range:</span> {fmtDollar(row.amount_low)} — {fmtDollar(row.amount_high)}</div>
                            <div><span style={{ color: COLORS.textDim }}>Category:</span> {row.category.replace(/_/g, " ")}</div>
                            <div><span style={{ color: COLORS.textDim }}>Entity:</span> {row.entity}</div>
                            <div><span style={{ color: COLORS.textDim }}>Lifecycle:</span> {row.lifecycle_stage}</div>
                            {row.lever && <div><span style={{ color: COLORS.textDim }}>Lever:</span> {row.lever}</div>}
                            <div style={{ marginTop: 4 }}><span style={{ color: COLORS.textDim }}>Support:</span> {row.support_reference}</div>
                            <div style={{ marginTop: 4, fontStyle: "italic" }}>{row.rationale}</div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {subView === "sustainability" && (
        <div>
          <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, padding: "20px", marginBottom: 16 }}>
            <div style={{ textAlign: "center", marginBottom: 16 }}>
              <div style={{ fontSize: 50, fontWeight: 700, color: sus.overall >= 65 ? COLORS.green : sus.overall >= 50 ? COLORS.accent : COLORS.red, fontFamily: "'IBM Plex Mono',monospace" }}>{sus.overall.toFixed(0)}</div>
              <div style={{ fontSize: 15, color: COLORS.textMuted }}>Earnings Sustainability Score</div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {sus.components.map((c) => (
                <div key={c.name} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{ width: 160, fontSize: 15, color: COLORS.textMuted }}>{c.name}</div>
                  <div style={{ flex: 1, height: 8, background: COLORS.bg, borderRadius: 4, overflow: "hidden" }}>
                    <div style={{ width: `${c.score}%`, height: "100%", borderRadius: 4, background: c.score >= 70 ? COLORS.green : c.score >= 50 ? COLORS.accent : COLORS.red, transition: "width 0.3s" }} />
                  </div>
                  <div style={{ width: 50, textAlign: "right", fontSize: 14, fontWeight: 600, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{c.score.toFixed(0)}</div>
                  <div style={{ width: 30, textAlign: "right", fontSize: 14, color: COLORS.textDim }}>/{c.max_points}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {subView === "revenue" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Concentration */}
          <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, padding: "16px 20px" }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: COLORS.accent, marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.06em" }}>Customer Concentration</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 12 }}>
              <div><div style={{ fontSize: 14, color: COLORS.textDim }}>HHI Index</div><div style={{ fontSize: 20, fontWeight: 700, color: rq.customer_concentration.hhi < 1500 ? COLORS.green : COLORS.red, fontFamily: "'IBM Plex Mono',monospace" }}>{rq.customer_concentration.hhi.toFixed(0)}</div></div>
              <div><div style={{ fontSize: 14, color: COLORS.textDim }}>Top 10 %</div><div style={{ fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{rq.customer_concentration.top_10_pct.toFixed(1)}%</div></div>
              <div><div style={{ fontSize: 14, color: COLORS.textDim }}>Top 20 %</div><div style={{ fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{rq.customer_concentration.top_20_pct.toFixed(1)}%</div></div>
              <div><div style={{ fontSize: 14, color: COLORS.textDim }}>Customers</div><div style={{ fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{rq.customer_concentration.total_customers.toLocaleString()}</div></div>
            </div>
            {rq.customer_concentration.threshold_alerts.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: COLORS.red, marginBottom: 4 }}>THRESHOLD ALERTS</div>
                {rq.customer_concentration.threshold_alerts.map((a) => (
                  <div key={a.customer} style={{ fontSize: 15, color: COLORS.textMuted }}>{a.customer}: {a.pct}% (crossed {a.threshold})</div>
                ))}
              </div>
            )}
          </div>

          {/* Contract quality */}
          <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, padding: "16px 20px" }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: COLORS.accent, marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.06em" }}>Contract Quality</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
              <div><div style={{ fontSize: 14, color: COLORS.textDim }}>MSA %</div><div style={{ fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{rq.contract_quality.msa_pct}%</div></div>
              <div><div style={{ fontSize: 14, color: COLORS.textDim }}>SOW %</div><div style={{ fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{rq.contract_quality.sow_pct}%</div></div>
              <div><div style={{ fontSize: 14, color: COLORS.textDim }}>T&M %</div><div style={{ fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{rq.contract_quality.t_and_m_pct}%</div></div>
              <div><div style={{ fontSize: 14, color: COLORS.textDim }}>Avg Tenure</div><div style={{ fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{rq.contract_quality.avg_tenure_years} yrs</div></div>
            </div>
          </div>

          {/* Revenue mix */}
          <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, padding: "16px 20px" }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: COLORS.accent, marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.06em" }}>Revenue Mix (Quarterly)</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <div style={{ fontSize: 14, color: COLORS.textDim }}>Recurring</div>
                <div style={{ fontSize: 20, fontWeight: 700, color: COLORS.green, fontFamily: "'IBM Plex Mono',monospace" }}>{rq.revenue_mix.recurring_pct}%</div>
                <div style={{ fontSize: 14, color: COLORS.textMuted }}>Managed ${rq.revenue_mix.managed_services_M}M · Per-FTE ${rq.revenue_mix.per_fte_M}M · Per-Txn ${rq.revenue_mix.per_transaction_M}M</div>
              </div>
              <div>
                <div style={{ fontSize: 14, color: COLORS.textDim }}>Non-Recurring</div>
                <div style={{ fontSize: 20, fontWeight: 700, color: COLORS.accent, fontFamily: "'IBM Plex Mono',monospace" }}>{rq.revenue_mix.non_recurring_pct}%</div>
                <div style={{ fontSize: 14, color: COLORS.textMuted }}>Advisory & Consulting ${rq.revenue_mix.advisory_consulting_M}M</div>
              </div>
            </div>
          </div>

          {/* Cross-sell penetration */}
          <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, padding: "16px 20px" }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: COLORS.accent, marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.06em" }}>Cross-Sell Penetration</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
              <div><div style={{ fontSize: 14, color: COLORS.textDim }}>Candidates</div><div style={{ fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{rq.cross_sell_penetration.total_candidates}</div></div>
              <div><div style={{ fontSize: 14, color: COLORS.textDim }}>Pipeline ACV</div><div style={{ fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>${rq.cross_sell_penetration.total_pipeline_acv_M}M</div></div>
              <div><div style={{ fontSize: 14, color: COLORS.textDim }}>Converted</div><div style={{ fontSize: 20, fontWeight: 700, color: rq.cross_sell_penetration.converted_count > 0 ? COLORS.green : COLORS.textDim, fontFamily: "'IBM Plex Mono',monospace" }}>{rq.cross_sell_penetration.converted_count}</div></div>
            </div>
          </div>
        </div>
      )}

      {subView === "working_capital" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* DSO trend */}
          {([
            { label: "DSO (Days Sales Outstanding)", data: wc.dso_trend, unit: " days" },
            { label: "DPO (Days Payable Outstanding)", data: wc.dpo_trend, unit: " days" },
            { label: "Bench Cost ($M)", data: wc.bench_cost_trend, unit: "M" },
          ] as const).map((metric) => (
            <div key={metric.label} style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, padding: "16px 20px" }}>
              <div style={{ fontSize: 15, fontWeight: 600, color: COLORS.accent, marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.06em" }}>{metric.label}</div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {metric.data.map((d, i) => (
                  <div key={d.period} style={{ textAlign: "center", minWidth: 60 }}>
                    <div style={{ fontSize: 15, fontWeight: 600, color: i === metric.data.length - 1 ? COLORS.accent : COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{d.value.toFixed(1)}{metric.unit}</div>
                    <div style={{ fontSize: 11, color: COLORS.textDim }}>{d.period}</div>
                  </div>
                ))}
              </div>
            </div>
          ))}

          {/* Margin trend */}
          <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, padding: "16px 20px" }}>
            <div style={{ fontSize: 15, fontWeight: 600, color: COLORS.accent, marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.06em" }}>Margin Trend</div>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                  <th style={{ textAlign: "left", padding: "4px 8px", color: COLORS.textDim, fontSize: 14 }}>Period</th>
                  <th style={{ textAlign: "right", padding: "4px 8px", color: COLORS.textDim, fontSize: 14 }}>Gross Margin</th>
                  <th style={{ textAlign: "right", padding: "4px 8px", color: COLORS.textDim, fontSize: 14 }}>EBITDA Margin</th>
                </tr>
              </thead>
              <tbody>
                {wc.margin_trend.map((m, i) => (
                  <tr key={m.period} style={{ borderBottom: `1px solid ${COLORS.border}15` }}>
                    <td style={{ padding: "4px 8px", color: i === wc.margin_trend.length - 1 ? COLORS.accent : COLORS.textMuted }}>{m.period}</td>
                    <td style={{ textAlign: "right", padding: "4px 8px", fontFamily: "'IBM Plex Mono',monospace", color: COLORS.text }}>{m.gross_margin_pct.toFixed(1)}%</td>
                    <td style={{ textAlign: "right", padding: "4px 8px", fontFamily: "'IBM Plex Mono',monospace", color: COLORS.text }}>{m.ebitda_margin_pct.toFixed(1)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {subView === "new_items" && (
        <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, overflow: "hidden" }}>
          {data.new_items.length === 0 ? (
            <div style={{ padding: 20, textAlign: "center", color: COLORS.textMuted, fontSize: 15 }}>No new items detected this period.</div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                  <th style={{ textAlign: "left", padding: "6px 12px", color: COLORS.textDim, fontSize: 14, textTransform: "uppercase" }}>Description</th>
                  <th style={{ textAlign: "right", padding: "6px 12px", color: COLORS.textDim, fontSize: 14 }}>Amount</th>
                  <th style={{ textAlign: "center", padding: "6px 8px", color: COLORS.textDim, fontSize: 14 }}>Classification</th>
                  <th style={{ textAlign: "center", padding: "6px 8px", color: COLORS.textDim, fontSize: 14 }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {data.new_items.map((item, i) => (
                  <tr key={i} style={{ borderBottom: `1px solid ${COLORS.border}15` }}>
                    <td style={{ padding: "6px 12px", color: COLORS.text }}>{item.description}</td>
                    <td style={{ textAlign: "right", padding: "6px 12px", fontFamily: "'IBM Plex Mono',monospace", color: item.amount >= 0 ? COLORS.green : COLORS.red }}>{fmtDollar(item.amount)}</td>
                    <td style={{ textAlign: "center", padding: "6px 8px" }}>
                      <span style={{ fontSize: 11, padding: "1px 6px", borderRadius: 3, fontWeight: 600, color: COLORS.accent, background: "rgba(199,120,64,0.08)" }}>{item.classification_suggestion.toUpperCase()}</span>
                    </td>
                    <td style={{ textAlign: "center", padding: "6px 8px" }}>
                      <span style={{ fontSize: 11, padding: "1px 6px", borderRadius: 3, fontWeight: 600, color: item.recommended_action === "add_to_bridge" ? COLORS.green : COLORS.textMuted, background: item.recommended_action === "add_to_bridge" ? COLORS.greenBg : `${COLORS.textDim}15` }}>{item.recommended_action.replace(/_/g, " ").toUpperCase()}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

// ============================================================
// DASHBOARDS TAB
// ============================================================

function formatDashVal(v: unknown): string {
  if (v === null || v === undefined) return "\u2014";
  if (typeof v === "number") return fmtDollar(v);
  if (typeof v === "boolean") return v ? "Yes" : "No";
  return String(v);
}

function DashboardValue({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value === null || value === undefined) return <span>{"\u2014"}</span>;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return <span style={{ color: COLORS.text, fontFamily: typeof value === "number" ? "'IBM Plex Mono',monospace" : "'IBM Plex Sans',sans-serif" }}>{formatDashVal(value)}</span>;
  }

  // Array of primitives
  if (Array.isArray(value) && value.length > 0 && typeof value[0] !== "object") {
    return <span style={{ color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>{value.join(", ")}</span>;
  }

  // Array of objects → table
  if (Array.isArray(value) && value.length > 0 && typeof value[0] === "object" && value[0] !== null) {
    const first = value[0] as Record<string, unknown>;
    // Separate scalar columns from nested columns
    const scalarKeys = Object.keys(first).filter((k) => typeof first[k] !== "object" || first[k] === null);
    const nestedKeys = Object.keys(first).filter((k) => typeof first[k] === "object" && first[k] !== null);

    return (
      <div>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
              {scalarKeys.map((h) => (
                <th key={h} style={{ textAlign: typeof first[h] === "number" ? "right" : "left", padding: "4px 8px", fontSize: 14, color: COLORS.textDim, textTransform: "uppercase", letterSpacing: "0.04em" }}>
                  {h.replace(/_/g, " ")}
                </th>
              ))}
              {nestedKeys.length > 0 && <th style={{ padding: "4px 8px", fontSize: 14, color: COLORS.textDim }}></th>}
            </tr>
          </thead>
          <tbody>
            {value.map((row, ri) => {
              const r = row as Record<string, unknown>;
              return (
                <React.Fragment key={ri}>
                  <tr style={{ borderBottom: `1px solid ${COLORS.border}15` }}>
                    {scalarKeys.map((k) => (
                      <td key={k} style={{ textAlign: typeof r[k] === "number" ? "right" : "left", padding: "4px 8px", color: COLORS.text, fontFamily: typeof r[k] === "number" ? "'IBM Plex Mono',monospace" : "'IBM Plex Sans',sans-serif" }}>
                        {formatDashVal(r[k])}
                      </td>
                    ))}
                    {nestedKeys.length > 0 && (
                      <td style={{ padding: "4px 8px" }}>
                        {nestedKeys.map((nk) => !!r[nk] && (
                          <div key={nk} style={{ fontSize: 15, color: COLORS.textMuted }}>
                            <span style={{ color: COLORS.textDim, fontSize: 14 }}>{nk.replace(/_/g, " ")}: </span>
                            {Array.isArray(r[nk]) && r[nk].every((x: unknown) => typeof x !== "object")
                              ? (r[nk] as unknown[]).join(", ")
                              : <DashboardValue value={r[nk]} depth={depth + 1} />}
                          </div>
                        ))}
                      </td>
                    )}
                  </tr>
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  }

  // Plain object → check if values are all scalars or contain nested objects
  if (typeof value === "object" && !Array.isArray(value)) {
    const entries = Object.entries(value as Record<string, unknown>);
    const hasNestedValues = entries.some(([, v]) => typeof v === "object" && v !== null);

    if (!hasNestedValues) {
      // All scalar values → simple key-value grid
      return (
        <div style={{ display: "grid", gridTemplateColumns: depth > 0 ? "1fr" : "1fr 1fr", gap: 6 }}>
          {entries.map(([k, v]) => (
            <div key={k}>
              <span style={{ color: COLORS.textDim, fontSize: 15 }}>{k.replace(/_/g, " ")}:</span>{" "}
              <span style={{ color: COLORS.text, fontFamily: typeof v === "number" ? "'IBM Plex Mono',monospace" : "'IBM Plex Sans',sans-serif" }}>{formatDashVal(v)}</span>
            </div>
          ))}
        </div>
      );
    }

    // Has nested values → render each as a subsection
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {entries.map(([k, v]) => {
          if (typeof v !== "object" || v === null) {
            return (
              <div key={k}>
                <span style={{ color: COLORS.textDim, fontSize: 15 }}>{k.replace(/_/g, " ")}:</span>{" "}
                <span style={{ color: COLORS.text, fontFamily: typeof v === "number" ? "'IBM Plex Mono',monospace" : "'IBM Plex Sans',sans-serif" }}>{formatDashVal(v)}</span>
              </div>
            );
          }
          return (
            <div key={k} style={{ background: depth < 1 ? COLORS.bg : "transparent", borderRadius: 6, padding: depth < 1 ? "10px 14px" : "0 0 0 12px", borderLeft: depth < 1 ? "none" : `2px solid ${COLORS.border}` }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: COLORS.accent, marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.04em" }}>{k.replace(/_/g, " ")}</div>
              <DashboardValue value={v} depth={depth + 1} />
            </div>
          );
        })}
      </div>
    );
  }

  return <span style={{ color: COLORS.text }}>{String(value)}</span>;
}

function DashboardsTab() {
  const [persona, setPersona] = useState<DashboardPersona>("cfo");
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = useCallback(async (p: DashboardPersona) => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchDashboard(p);
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadDashboard(persona); }, [persona, loadDashboard]);

  const personas: { id: DashboardPersona; label: string }[] = [
    { id: "cfo", label: "CFO" }, { id: "cro", label: "CRO" }, { id: "coo", label: "COO" },
    { id: "cto", label: "CTO" }, { id: "chro", label: "CHRO" },
  ];

  return (
    <div>
      {/* Persona selector */}
      <div style={{ display: "flex", gap: 4, marginBottom: 20 }}>
        {personas.map((p) => (
          <button key={p.id} onClick={() => setPersona(p.id)} style={{
            padding: "8px 20px", fontSize: 14, fontWeight: persona === p.id ? 700 : 400,
            background: persona === p.id ? "rgba(199,120,64,0.12)" : "transparent",
            color: persona === p.id ? COLORS.accent : COLORS.textMuted,
            border: persona === p.id ? `1px solid ${COLORS.accent}44` : `1px solid ${COLORS.border}`,
            borderRadius: 6, cursor: "pointer", fontFamily: "'IBM Plex Sans',sans-serif",
            letterSpacing: "0.04em",
          }}>{p.label}</button>
        ))}
      </div>

      {loading && <LoadingState message={`Loading ${persona.toUpperCase()} dashboard...`} />}
      {error && !loading && <ErrorState error={error} onRetry={() => loadDashboard(persona)} />}

      {!loading && !error && data && (
        <div>
          <div style={{ fontSize: 18, fontWeight: 600, color: COLORS.text, marginBottom: 20, fontFamily: "'IBM Plex Sans',sans-serif" }}>{data.title}</div>

          {/* KPI cards */}
          <div style={{ display: "flex", gap: 16, marginBottom: 24, flexWrap: "wrap" }}>
            {Object.entries(data.kpis).map(([key, val]) => (
              <div key={key} style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 18px", flex: "1 1 180px", minWidth: 180 }}>
                <div style={{ fontSize: 14, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono',monospace" }}>
                  {key.replace(/_/g, " ")}
                </div>
                <div style={{ fontSize: 22, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace", marginTop: 4 }}>
                  {typeof val === "number" ? fmtDollar(val) : String(val)}
                </div>
              </div>
            ))}
          </div>

          {/* Render detail sections dynamically based on persona data */}
          {Object.entries(data).map(([key, val]) => {
            if (["persona", "title", "kpis"].includes(key)) return null;
            if (!val || (typeof val === "object" && !Array.isArray(val) && Object.keys(val as Record<string, unknown>).length === 0)) return null;

            return (
              <div key={key} style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, overflow: "hidden", marginBottom: 16 }}>
                <div style={{ padding: "10px 16px", borderBottom: `1px solid ${COLORS.border}`, fontSize: 15, fontWeight: 600, color: COLORS.accent, letterSpacing: "0.06em", textTransform: "uppercase", fontFamily: "'JetBrains Mono',monospace" }}>
                  {key.replace(/_/g, " ")}
                </div>
                <div style={{ padding: "12px 16px", fontSize: 14, color: COLORS.textMuted, maxHeight: 400, overflowY: "auto" }}>
                  <DashboardValue value={val} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ============================================================
// MAESTRA TAB
// ============================================================

// ── Rich Content Renderers ──────────────────────────────────────────────
function InlineTable({ title, headers, rows }: { title?: string; headers?: string[]; rows?: string[][] }) {
  if (!headers || !rows) return null;
  return (
    <div style={{ margin: "8px 0", borderRadius: 6, overflow: "hidden", border: `1px solid ${COLORS.border}` }}>
      {title && <div style={{ padding: "6px 10px", fontSize: 15, fontWeight: 600, color: COLORS.accent, background: COLORS.headerBg, borderBottom: `1px solid ${COLORS.border}`, fontFamily: "'JetBrains Mono',monospace" }}>{title}</div>}
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
        <thead>
          <tr>{headers.map((h, i) => <th key={i} style={{ padding: "6px 10px", textAlign: "left", color: COLORS.textMuted, borderBottom: `1px solid ${COLORS.border}`, fontWeight: 600, background: COLORS.headerBg }}>{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri} style={{ background: ri % 2 === 0 ? "transparent" : COLORS.totalBg }}>
              {row.map((cell, ci) => <td key={ci} style={{ padding: "5px 10px", color: COLORS.text, borderBottom: `1px solid ${COLORS.border}22` }}>{cell}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function HierarchyNodeView({ node, depth = 0 }: { node: { name: string; children?: any[] }; depth?: number }) {
  const [expanded, setExpanded] = useState(depth < 2);
  const hasChildren = node.children && node.children.length > 0;
  return (
    <div style={{ marginLeft: depth * 16 }}>
      <div
        onClick={() => hasChildren && setExpanded(!expanded)}
        style={{ display: "flex", alignItems: "center", gap: 4, padding: "3px 0", cursor: hasChildren ? "pointer" : "default", fontSize: 14, color: COLORS.text }}
      >
        <span style={{ width: 14, textAlign: "center", color: COLORS.textDim, fontSize: 14 }}>{hasChildren ? (expanded ? "\u25BC" : "\u25B6") : "\u2022"}</span>
        <span>{node.name}</span>
      </div>
      {expanded && hasChildren && node.children!.map((child: any, i: number) => (
        <HierarchyNodeView key={i} node={child} depth={depth + 1} />
      ))}
    </div>
  );
}

function InlineHierarchy({ title, root }: { title?: string; root?: { name: string; children?: any[] } }) {
  if (!root) return null;
  return (
    <div style={{ margin: "8px 0", padding: "8px 12px", borderRadius: 6, border: `1px solid ${COLORS.border}`, background: COLORS.bg }}>
      {title && <div style={{ fontSize: 15, fontWeight: 600, color: COLORS.accent, marginBottom: 6, fontFamily: "'JetBrains Mono',monospace" }}>{title}</div>}
      <HierarchyNodeView node={root} />
    </div>
  );
}

function InlineComparison({ dimension, systems }: { dimension?: string; systems?: { system: string; value: string; is_match?: boolean }[] }) {
  if (!systems) return null;
  return (
    <div style={{ margin: "8px 0", borderRadius: 6, overflow: "hidden", border: `1px solid ${COLORS.border}` }}>
      {dimension && <div style={{ padding: "6px 10px", fontSize: 15, fontWeight: 600, color: COLORS.accent, background: COLORS.headerBg, borderBottom: `1px solid ${COLORS.border}`, fontFamily: "'JetBrains Mono',monospace" }}>Comparison: {dimension}</div>}
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${systems.length}, 1fr)`, gap: 0 }}>
        {systems.map((s, i) => (
          <div key={i} style={{
            padding: "8px 12px", textAlign: "center",
            borderRight: i < systems.length - 1 ? `1px solid ${COLORS.border}` : "none",
            background: s.is_match === false ? COLORS.redBg : s.is_match === true ? COLORS.greenBg : "transparent",
          }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: COLORS.textMuted, marginBottom: 4 }}>{s.system}</div>
            <div style={{ fontSize: 15, color: COLORS.text, fontWeight: 600 }}>{s.value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function InlineScopeChecklist({ deliverables, reconciliation_objects, synergy_targets }: {
  deliverables?: { id: string; name: string; description: string; selected: boolean }[];
  reconciliation_objects?: string[];
  synergy_targets?: { revenue_synergy?: number; cost_synergy?: number; integration_budget?: number };
}) {
  if (!deliverables) return null;
  return (
    <div style={{ margin: "8px 0", borderRadius: 6, border: `1px solid ${COLORS.border}`, background: COLORS.bg, overflow: "hidden" }}>
      <div style={{ padding: "8px 12px", background: COLORS.headerBg, borderBottom: `1px solid ${COLORS.border}` }}>
        <span style={{ fontSize: 15, fontWeight: 600, color: COLORS.accent, fontFamily: "'JetBrains Mono',monospace", letterSpacing: "0.06em" }}>DD DELIVERABLES</span>
      </div>
      <div style={{ padding: "8px 12px" }}>
        {deliverables.map((d) => (
          <div key={d.id} style={{ padding: "4px 0", display: "flex", alignItems: "flex-start", gap: 8 }}>
            <span style={{ fontSize: 16, lineHeight: "18px", color: d.selected ? COLORS.green : COLORS.textDim, flexShrink: 0 }}>{d.selected ? "\u2611" : "\u2610"}</span>
            <div>
              <div style={{ fontSize: 14, fontWeight: 600, color: COLORS.text }}>{d.name}</div>
              <div style={{ fontSize: 15, color: COLORS.textMuted }}>{d.description}</div>
            </div>
          </div>
        ))}
      </div>
      {reconciliation_objects && (
        <>
          <div style={{ padding: "8px 12px", background: COLORS.headerBg, borderTop: `1px solid ${COLORS.border}`, borderBottom: `1px solid ${COLORS.border}` }}>
            <span style={{ fontSize: 15, fontWeight: 600, color: COLORS.accent, fontFamily: "'JetBrains Mono',monospace", letterSpacing: "0.06em" }}>RECONCILIATION OBJECTS (always included)</span>
          </div>
          <div style={{ padding: "8px 12px" }}>
            {reconciliation_objects.map((obj, i) => (
              <div key={i} style={{ padding: "2px 0", fontSize: 14, color: COLORS.text, display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ color: COLORS.green, fontSize: 14 }}>{"\u2713"}</span> {obj}
              </div>
            ))}
          </div>
        </>
      )}
      {synergy_targets && (
        <>
          <div style={{ padding: "8px 12px", background: COLORS.headerBg, borderTop: `1px solid ${COLORS.border}`, borderBottom: `1px solid ${COLORS.border}` }}>
            <span style={{ fontSize: 15, fontWeight: 600, color: COLORS.accent, fontFamily: "'JetBrains Mono',monospace", letterSpacing: "0.06em" }}>DEAL MODEL TARGETS</span>
          </div>
          <div style={{ padding: "8px 12px", fontSize: 14, color: COLORS.text }}>
            {synergy_targets.revenue_synergy != null && <div>Revenue synergy: ${(synergy_targets.revenue_synergy / 1e6).toFixed(0)}M</div>}
            {synergy_targets.cost_synergy != null && <div>Cost synergy: ${(synergy_targets.cost_synergy / 1e6).toFixed(0)}M</div>}
            {synergy_targets.integration_budget != null && <div>Integration budget: ${(synergy_targets.integration_budget / 1e6).toFixed(0)}M</div>}
          </div>
        </>
      )}
    </div>
  );
}

function InlineRoadmap({ title, message, sections, onSectionClick }: {
  title?: string;
  message?: string;
  sections?: { id: string; number: number; name: string; duration: string; status: string }[];
  onSectionClick?: (sectionName: string) => void;
}) {
  if (!sections) return null;
  return (
    <div style={{ margin: "8px 0", borderRadius: 6, border: `1px solid ${COLORS.border}`, background: COLORS.bg, overflow: "hidden" }}>
      {title && <div style={{ padding: "8px 12px", background: COLORS.headerBg, borderBottom: `1px solid ${COLORS.border}` }}>
        <span style={{ fontSize: 15, fontWeight: 600, color: COLORS.accent, fontFamily: "'JetBrains Mono',monospace", letterSpacing: "0.06em" }}>{title.toUpperCase()}</span>
      </div>}
      {message && <div style={{ padding: "8px 12px", fontSize: 14, color: COLORS.textMuted, borderBottom: `1px solid ${COLORS.border}22` }}>{message}</div>}
      <div>
        {sections.map((s) => (
          <div
            key={s.id}
            onClick={() => onSectionClick && onSectionClick(`Jump to ${s.name}`)}
            style={{
              display: "flex", alignItems: "center", gap: 10, padding: "8px 12px",
              cursor: onSectionClick ? "pointer" : "default",
              borderBottom: `1px solid ${COLORS.border}22`,
              transition: "background 0.15s",
            }}
            onMouseEnter={(e) => { if (onSectionClick) e.currentTarget.style.background = COLORS.surfaceHover; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
          >
            <span style={{ width: 22, height: 22, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 15, fontWeight: 700, flexShrink: 0,
              background: s.status === "Current" ? COLORS.accent : s.status === "Complete" ? COLORS.green : COLORS.surface,
              color: s.status === "Current" || s.status === "Complete" ? "#fff" : COLORS.textMuted,
              border: s.status === "Current" || s.status === "Complete" ? "none" : `1px solid ${COLORS.border}`,
            }}>{s.number}</span>
            <div style={{ flex: 1 }}>
              <span style={{ fontSize: 14, fontWeight: 600, color: COLORS.text }}>{s.name}</span>
              <span style={{ fontSize: 15, color: COLORS.textDim, marginLeft: 8 }}>{s.duration}</span>
            </div>
            <span style={{ fontSize: 14, color: s.status === "Complete" ? COLORS.green : s.status === "Current" ? COLORS.accent : COLORS.textDim, fontWeight: 600 }}>{s.status}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function RichContentRenderer({ content, onSendMessage }: { content: any; onSendMessage?: (msg: string) => void }) {
  if (!content || !content.type) return null;
  switch (content.type) {
    case "table": return <InlineTable title={content.title} headers={content.headers} rows={content.rows} />;
    case "hierarchy": return <InlineHierarchy title={content.title} root={content.root} />;
    case "comparison": return <InlineComparison dimension={content.dimension} systems={content.systems} />;
    case "scope_checklist": return <InlineScopeChecklist deliverables={content.deliverables} reconciliation_objects={content.reconciliation_objects} synergy_targets={content.synergy_targets} />;
    case "roadmap": return <InlineRoadmap title={content.title} message={content.message} sections={content.sections} onSectionClick={onSendMessage} />;
    default: return null;
  }
}

// ── Maestra Floating Chat ──────────────────────────────────────────────────
type ChatMsg = { role: "user" | "maestra"; text: string };

function MaestraFloatingChat({ onNavigate, onEntityChange }: { onNavigate?: (tab: string) => void; onEntityChange?: (entity: EntitySelection) => void }) {
  const [expanded, setExpanded] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const chatEndRef = React.useRef<HTMLDivElement>(null);

  // Draggable position for expanded panel
  const [panelPos, setPanelPos] = useState<{ x: number; y: number } | null>(null);
  const dragRef = React.useRef<{ startX: number; startY: number; origX: number; origY: number } | null>(null);

  const handleDragStart = useCallback((e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest("button")) return;
    e.preventDefault();
    const panel = (e.currentTarget as HTMLElement).parentElement!;
    const rect = panel.getBoundingClientRect();
    dragRef.current = { startX: e.clientX, startY: e.clientY, origX: rect.left, origY: rect.top };

    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return;
      const dx = ev.clientX - dragRef.current.startX;
      const dy = ev.clientY - dragRef.current.startY;
      setPanelPos({ x: dragRef.current.origX + dx, y: dragRef.current.origY + dy });
    };
    const onUp = () => {
      dragRef.current = null;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }, []);

  const scrollToBottom = useCallback(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages, loading]);

  // Clear unread when expanded
  useEffect(() => {
    if (expanded) setUnreadCount(0);
  }, [expanded]);

  const handleNavigate = useCallback((tab: string) => {
    if (onNavigate) onNavigate(tab);
    const combinedTabs = ["combining", "overlap", "crosssell", "cross_sell", "bridge", "ebitda", "whatif", "what_if", "qoe", "dashboards"];
    if (onEntityChange && combinedTabs.includes(tab)) {
      onEntityChange("combined");
    }
  }, [onNavigate, onEntityChange]);

  const sendMessage = useCallback(async (overrideMsg?: string) => {
    const msg = (overrideMsg || input).trim();
    if (!msg) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: msg }]);
    setLoading(true);
    try {
      const resp = await sendMaestraChat(msg, sessionId || undefined);
      if (!sessionId) setSessionId(resp.session_id);
      setMessages((prev) => [...prev, { role: "maestra", text: resp.text }]);
      if (!expanded) setUnreadCount((c) => c + 1);
    } catch (err) {
      setMessages((prev) => [...prev, { role: "maestra", text: `Error: ${err instanceof Error ? err.message : String(err)}` }]);
    } finally {
      setLoading(false);
    }
  }, [sessionId, input, expanded]);

  // Collapsed state — floating icon
  if (!expanded) {
    return createPortal(
      <div
        onClick={() => setExpanded(true)}
        style={{
          position: "fixed", bottom: 24, right: 24, width: 56, height: 56,
          borderRadius: "50%", background: COLORS.accent, cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center",
          boxShadow: "0 4px 20px rgba(0,0,0,0.4)", zIndex: 10000,
          transition: "transform 0.15s ease",
        }}
        onMouseEnter={(e) => (e.currentTarget.style.transform = "scale(1.08)")}
        onMouseLeave={(e) => (e.currentTarget.style.transform = "scale(1)")}
        title="Open Maestra"
      >
        <span style={{ fontSize: 24, fontWeight: 700, color: "#fff", fontFamily: "'IBM Plex Sans',sans-serif", lineHeight: 1 }}>M</span>
        {unreadCount > 0 && (
          <span style={{
            position: "absolute", top: -2, right: -2, minWidth: 18, height: 18,
            borderRadius: 9, background: COLORS.red, color: "#fff",
            fontSize: 14, fontWeight: 700, display: "flex", alignItems: "center",
            justifyContent: "center", padding: "0 4px",
          }}>{unreadCount}</span>
        )}
      </div>,
      document.body,
    );
  }

  // Expanded state — full chat panel
  return createPortal(
    <div style={{
      position: "fixed",
      ...(panelPos ? { left: panelPos.x, top: panelPos.y } : { bottom: 24, right: 24 }),
      width: 420, height: 580,
      borderRadius: 12, background: COLORS.surface, border: `1px solid ${COLORS.border}`,
      display: "flex", flexDirection: "column", overflow: "hidden",
      boxShadow: "0 8px 40px rgba(0,0,0,0.5)", zIndex: 10000,
      fontFamily: "'IBM Plex Sans',sans-serif",
    }}>
      {/* Header — drag handle */}
      <div
        onMouseDown={handleDragStart}
        style={{
        padding: "12px 16px", background: COLORS.headerBg,
        borderBottom: `1px solid ${COLORS.border}`,
        display: "flex", justifyContent: "space-between", alignItems: "center",
        cursor: "grab", userSelect: "none",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ width: 28, height: 28, borderRadius: "50%", background: COLORS.accent, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <span style={{ fontSize: 16, fontWeight: 700, color: "#fff" }}>M</span>
          </span>
          <div>
            <div style={{ fontSize: 15, fontWeight: 600, color: COLORS.text }}>Maestra</div>
            <div style={{ fontSize: 14, color: COLORS.textMuted }}>
              {loading ? "Thinking..." : "Engagement Lead"}
            </div>
          </div>
        </div>
        <button
          onClick={() => { setExpanded(false); setPanelPos(null); }}
          style={{ background: "transparent", border: "none", color: COLORS.textMuted, cursor: "pointer", fontSize: 20, padding: "0 4px", lineHeight: 1 }}
          title="Minimize"
        >{"\u2013"}</button>
      </div>

      {/* Chat interface — always available, no engagement gate */}
      <>
        <div style={{ flex: 1, overflowY: "auto", padding: "12px 16px" }}>
          {messages.length === 0 && !loading && (
            <div style={{ textAlign: "center", padding: "40px 16px", color: COLORS.textMuted, fontSize: 14, lineHeight: 1.6 }}>
              I'm Maestra, your engagement lead for this deal. Ask me about the Meridian/Cascadia convergence — pipeline health, module status, overlap reports, or anything else.
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} style={{ marginBottom: 12, textAlign: m.role === "user" ? "right" : "left" }}>
              <div style={{
                display: "inline-block", maxWidth: "88%", padding: "8px 14px", borderRadius: 8,
                background: m.role === "user" ? "rgba(199,120,64,0.12)" : COLORS.bg,
                color: COLORS.text, fontSize: 15, lineHeight: 1.5,
                textAlign: "left", whiteSpace: "pre-wrap",
              }}>{m.text}</div>
            </div>
          ))}
          {loading && (
            <div style={{ fontSize: 14, color: COLORS.textDim, fontStyle: "italic", display: "flex", alignItems: "center", gap: 6, padding: "4px 0" }}>
              <span style={{ display: "inline-flex", gap: 3 }}>
                {[0, 1, 2].map(d => <span key={d} style={{ width: 4, height: 4, borderRadius: "50%", background: COLORS.accent, animation: `bounce 1.4s ${d * 0.16}s infinite ease-in-out both` }} />)}
              </span>
              Maestra is thinking...
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        {/* Input */}
        <div style={{ padding: "10px 12px", borderTop: `1px solid ${COLORS.border}`, display: "flex", gap: 8 }}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
            placeholder="Ask Maestra..."
            style={{
              flex: 1, padding: "8px 12px", fontSize: 15, background: COLORS.bg, color: COLORS.text,
              border: `1px solid ${COLORS.border}`, borderRadius: 6, outline: "none",
            }}
          />
          <button onClick={() => sendMessage()} disabled={loading || !input.trim()} style={{
            padding: "8px 16px", fontSize: 14, fontWeight: 600, cursor: "pointer",
            background: COLORS.accent, color: "#fff", border: "none", borderRadius: 6,
            opacity: loading || !input.trim() ? 0.5 : 1,
          }}>Send</button>
        </div>
      </>
    </div>,
    document.body,
  );
}

// ============================================================
// MAIN COMPONENT
// ============================================================
export function ReportPortal({ onClose }: { onClose: () => void }) {
  const [entity, setEntity] = useState<EntitySelection>("combined");
  const [entityNames, setEntityNames] = useState<Record<string, string>>({});
  const [tab, setTab] = useState("pl");
  const [variant, setVariant] = useState("act_vs_py");
  const [quarter, setQuarter] = useState("2025-Q3");
  const [segment, setSegment] = useState("all");

  // Dimension state — fetched from API on mount
  const [dimensions, setDimensions] = useState<{ periods: PeriodDimension[]; segments: string[] } | null>(null);
  const [dimensionsError, setDimensionsError] = useState<string | null>(null);
  const [dimensionsLoading, setDimensionsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setDimensionsLoading(true);
    fetchReportDimensions()
      .then((dims) => {
        if (!cancelled) {
          setDimensions(dims);
          setDimensionsError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setDimensionsError(err.message || "Failed to load report dimensions");
        }
      })
      .finally(() => { if (!cancelled) setDimensionsLoading(false); });
    return () => { cancelled = true; };
  }, []);

  // Data states
  const [currentData, setCurrentData] = useState<ReportData | null>(null);
  const [pyData, setPyData] = useState<ReportData | null>(null);
  const [rawFSData, setRawFSData] = useState<FinancialStatementData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Combining statement data states
  const [combiningData, setCombiningData] = useState<CombiningStatementData | null>(null);
  const [combiningLoading, setCombiningLoading] = useState(false);
  const [combiningError, setCombiningError] = useState<string | null>(null);
  const [combiningVariant, setCombiningVariant] = useState("act_vs_py");
  const [combiningQuarter, setCombiningQuarter] = useState("2025-Q3");
  const [combiningSegment, setCombiningSegment] = useState("all");

  // Overlap report data states
  const [overlapData, setOverlapData] = useState<OverlapData | null>(null);
  const [overlapLoading, setOverlapLoading] = useState(false);
  const [overlapError, setOverlapError] = useState<string | null>(null);

  // Derive available quarters from API dimensions, filtering by entity data availability
  const entityKey = entity === "combined" ? null : entity;
  const actQuarters = useMemo(() => {
    if (!dimensions) return [];
    return dimensions.periods
      .filter((p) => {
        if (p.period_type !== "actual") return false;
        if (!entityKey) return Object.values(p.has_data).some(Boolean);
        return p.has_data[entityKey];
      })
      .map((p) => p.label);
  }, [dimensions, entityKey]);
  const cfQuarters = useMemo(() => {
    if (!dimensions) return [];
    const cy = wallClockDate().getFullYear();
    return dimensions.periods
      .filter((p) => p.period_type === "forecast" && p.year === cy)
      .map((p) => p.label);
  }, [dimensions]);
  const availableSegments = dimensions?.segments ?? SEGMENTS_FALLBACK;
  const lastFullYear = wallClockDate().getFullYear() - 1;
  const pyYear = lastFullYear - 1;

  // Sync quarter selectors to latest actual quarter when dimensions load
  useEffect(() => {
    if (actQuarters.length > 0) {
      const latest = actQuarters[actQuarters.length - 1];
      setQuarter(latest);
      setCombiningQuarter(latest);
    }
  }, [actQuarters]);

  const handleEntityChange = useCallback((e: EntitySelection) => {
    setEntity(e);
    // Reset to a valid tab when switching entity mode
    const combinedOnlyTabs = ["combining", "overlap", "crosssell", "bridge", "whatif", "qoe", "dashboards"];
    if (e !== "combined" && combinedOnlyTabs.includes(tab)) {
      setTab("pl");
    }
  }, [tab]);

  const handleTabChange = useCallback((t: string) => {
    setTab(t);
    setDrillLine(null);
    if (t === "bs" && variant !== "act_vs_py" && variant !== "quarterly") {
      setVariant("act_vs_py");
    }
  }, [variant]);

  // ── Parent iframe navigation via custom events ────────────────────
  // Dispatched by App.tsx postMessage handler when it receives 'reportNavigate'
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail
      if (!detail) return
      console.log('[ReportPortal] aos-report-navigate:', detail)
      if (detail.entity) {
        handleEntityChange(detail.entity)
      }
      if (detail.tab) {
        // Small delay so entity change settles first (tab list depends on entity)
        setTimeout(() => handleTabChange(detail.tab), 50)
      }
    }
    window.addEventListener('aos-report-navigate', handler)
    return () => window.removeEventListener('aos-report-navigate', handler)
  }, [handleEntityChange, handleTabChange])

  // Drill-through state (inline under FS table)
  const [drillLine, setDrillLine] = useState<{ id: string; name: string } | null>(null);

  const statementTabs = useMemo(() => {
    const base = [
      { id: "pl", label: "P&L", title: "Income Statement" },
      { id: "bs", label: "BS", title: "Balance Sheet" },
      { id: "cf", label: "CF", title: "Cash Flow Statement" },
      { id: "recon", label: "Recon", title: "Reconciliation" },
    ];
    if (entity === "combined") {
      return [
        ...base,
        { id: "combining", label: "Combining" },
        { id: "overlap", label: "Overlap" },
        { id: "crosssell", label: "X-Sell", title: "Cross-Sell Pipeline" },
        { id: "pipeline", label: "Pipeline" },
        { id: "bridge", label: "Bridge", title: "EBITDA Bridge" },
        { id: "whatif", label: "What-If" },
        { id: "qoe", label: "QofE", title: "Quality of Earnings" },
      ];
    }
    return [
      ...base,
      { id: "rev_by_customer", label: "Rev/Cust", title: "Revenue by Customer" },
      { id: "pipeline", label: "Pipeline" },
    ];
  }, [entity]);

  const variantOptions = tab === "bs" ? [
    { value: "act_vs_py", label: `FY${lastFullYear} Act vs FY${pyYear}` },
    { value: "quarterly", label: "Quarterly Actuals" },
  ] : [
    { value: "act_vs_py", label: `FY${lastFullYear} Act vs FY${pyYear}` },
    { value: "q_act_vs_py", label: "Quarterly Act vs PY" },
    { value: "cf_vs_py", label: `FY${wallClockDate().getFullYear()} CF vs FY${lastFullYear}` },
    { value: "q_cf_vs_py", label: "Quarterly CF vs PY" },
  ];

  const showQuarterSelect = variant === "q_act_vs_py" || variant === "q_cf_vs_py" || variant === "quarterly";
  const quarterOptions = variant === "q_cf_vs_py"
    ? cfQuarters.map((q) => ({ value: q, label: q }))
    : actQuarters.map((q) => ({ value: q, label: q }));

  const seg = segment === "all" ? null : segment;
  const isStatementTab = tab === "pl" || tab === "bs" || tab === "cf";

  // Determine the quarter to pass to the API based on the variant
  const effectiveQuarter = useMemo(() => {
    if (variant === "act_vs_py") return `${lastFullYear}-Q4`;
    if (variant === "q_act_vs_py") return quarter;
    if (variant === "cf_vs_py") {
      const cq = Math.ceil((wallClockDate().getMonth() + 1) / 3);
      return `${wallClockDate().getFullYear()}-Q${cq}`;
    }
    if (variant === "q_cf_vs_py") return quarter || cfQuarters[0];
    if (variant === "quarterly") return quarter;
    return `${lastFullYear}-Q4`;
  }, [variant, quarter, lastFullYear, cfQuarters]);

  // Combining period mirrors IS variant logic
  const combiningPeriod = useMemo(() => {
    if (combiningVariant === "act_vs_py") return String(lastFullYear);
    if (combiningVariant === "q_act_vs_py") return combiningQuarter;
    if (combiningVariant === "cf_vs_py") return String(wallClockDate().getFullYear());
    if (combiningVariant === "q_cf_vs_py") return combiningQuarter || cfQuarters[0];
    return String(lastFullYear);
  }, [combiningVariant, combiningQuarter, lastFullYear, cfQuarters]);

  // Fetch report data when tab/variant/quarter/segment/entity changes.
  // Uses a fetchId counter to discard stale responses — when the user switches
  // tabs before the previous fetch completes, the old response is ignored
  // because its fetchId no longer matches the current ref value.
  const fetchIdRef = useRef(0);

  const loadReport = useCallback(async () => {
    if (!isStatementTab) return;
    const fetchId = ++fetchIdRef.current;

    if (dimensionsError) {
      setError("Cannot load report: dimensions failed to load. Refresh the page to retry.");
      return;
    }

    // Segment-level data not yet available in triple store
    if (seg) {
      setError("Segment-level data not yet available. Select 'All Segments' to view the full statement.");
      setCurrentData(null);
      setPyData(null);
      setRawFSData(null);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    const statement = tabToStatement(tab);
    const apiVariant = mapVariant(variant);

    try {
      const result = await fetchReport(statement, apiVariant, effectiveQuarter, seg, entity);
      if (fetchIdRef.current !== fetchId) return; // stale response — discard
      setCurrentData(result.reportData);
      setRawFSData(result.rawFSData);

      // PY data is already extracted from the same backend response (periods[1])
      // No need for a second API call — the backend returns both CY and PY.
      if (variant !== "quarterly") {
        setPyData(result.pyReportData);
      } else {
        setPyData(null);
      }
    } catch (err) {
      if (fetchIdRef.current !== fetchId) return; // stale error — discard
      setError(err instanceof Error ? err.message : String(err));
      setCurrentData(null);
      setPyData(null);
      setRawFSData(null);
    } finally {
      if (fetchIdRef.current === fetchId) {
        setLoading(false);
      }
    }
  }, [tab, variant, effectiveQuarter, seg, isStatementTab, pyYear, lastFullYear, quarter, cfQuarters, entity, dimensionsError]);

  useEffect(() => {
    if (isStatementTab) {
      loadReport();
    }
  }, [loadReport, isStatementTab]);

  // Load combining statement data when the combining tab is active
  const combSeg = combiningSegment === "all" ? null : combiningSegment;
  const loadCombining = useCallback(async () => {
    if (tab !== "combining" || entity !== "combined") return;

    // Segment-level data not yet available in triple store
    if (combSeg) {
      setCombiningError("Segment-level data not yet available. Select 'All Segments' to view the combining statement.");
      setCombiningData(null);
      setCombiningLoading(false);
      return;
    }

    setCombiningLoading(true);
    setCombiningError(null);
    try {
      const result = await fetchCombiningStatement(combiningPeriod, combSeg);
      setCombiningData(result);
    } catch (err) {
      setCombiningError(err instanceof Error ? err.message : String(err));
      setCombiningData(null);
    } finally {
      setCombiningLoading(false);
    }
  }, [tab, entity, combiningPeriod, combSeg]);

  useEffect(() => {
    if (tab === "combining" && entity === "combined") {
      loadCombining();
    }
  }, [loadCombining, tab, entity]);

  // Load overlap data when the overlap tab is active
  const loadOverlap = useCallback(async () => {
    if (tab !== "overlap" || entity !== "combined") return;
    setOverlapLoading(true);
    setOverlapError(null);
    try {
      const result = await fetchOverlapData();
      setOverlapData(result);
    } catch (err) {
      setOverlapError(err instanceof Error ? err.message : String(err));
      setOverlapData(null);
    } finally {
      setOverlapLoading(false);
    }
  }, [tab, entity]);

  useEffect(() => {
    if (tab === "overlap" && entity === "combined") {
      loadOverlap();
    }
  }, [loadOverlap, tab, entity]);

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", background: COLORS.bg, color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif", padding: 0, overflow: "hidden" }}>
      <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet" />

      {/* Filter bar: Deal selector (left) + statement filters (right) */}
      <div style={{ padding: "8px 32px", borderBottom: `1px solid ${COLORS.border}`, display: "flex", justifyContent: "space-between", alignItems: "flex-end", background: COLORS.headerBg, gap: 12 }}>
        <DealSelector selected={entity} onChange={handleEntityChange} onDealLoaded={setEntityNames} />
        {isStatementTab && !dimensionsError && (
          <div style={{ display: "flex", alignItems: "flex-end", gap: 12 }}>
            <Select value={variant} onChange={setVariant} options={variantOptions} width={180} />
            {showQuarterSelect && <Select value={quarter} onChange={setQuarter} options={quarterOptions} width={120} />}
            <Select value={segment} onChange={setSegment} width={150} options={[
              { value: "all", label: "All Segments" },
              ...availableSegments.map((s) => ({ value: s, label: s })),
            ]} />
          </div>
        )}
      </div>

      {/* Tab bar */}
      <div style={{ display: "flex", alignItems: "center", padding: "0 32px", background: COLORS.headerBg, borderBottom: `1px solid ${COLORS.border}` }}>
        <TabBar tabs={statementTabs} active={tab} onChange={handleTabChange} noBorder />
      </div>

      <div style={{ flex: 1, overflow: "auto", padding: "24px 32px" }}>

        {isStatementTab && (
          <div style={{ maxWidth: CONTENT_MAX_WIDTH, margin: "0 auto" }}>
            {dimensionsLoading && (
              <div style={{ padding: "12px 16px", marginBottom: 16, background: "rgba(199,120,64,0.1)", border: `1px solid ${COLORS.accent}`, borderRadius: 6, fontSize: 15, color: COLORS.textMuted }}>
                Loading available periods and segments...
              </div>
            )}
            {dimensionsError && (
              <div style={{ padding: "12px 16px", marginBottom: 16, background: "rgba(220,60,60,0.1)", border: "1px solid rgba(220,60,60,0.5)", borderRadius: 6, fontSize: 15, color: "#e55" }}>
                Failed to load report dimensions: {dimensionsError}. Report filters are unavailable.
              </div>
            )}

            {loading && <LoadingState message={`Loading ${tab === "pl" ? "Income Statement" : tab === "bs" ? "Balance Sheet" : "Cash Flow"}...`} />}

            {error && !loading && <ErrorState error={error} onRetry={loadReport} />}

            {!loading && !error && currentData && (
              <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, overflow: "hidden" }}>
                <div style={{ padding: "12px 20px", borderBottom: `1px solid ${COLORS.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 16, fontWeight: 600, color: COLORS.text }}>
                    {tab === "pl" ? "Income Statement" : tab === "bs" ? "Balance Sheet" : "Statement of Cash Flows"}
                  </span>
                  <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                    <span style={{ fontSize: 13, padding: "3px 10px", background: "rgba(199,120,64,0.12)", color: COLORS.accent, borderRadius: 4, fontWeight: 600 }}>
                      {entityNames[entity] || (entity === "combined" ? "Combined" : entity)}
                    </span>
                    {currentData.metadata.periodType === "forecast" && (
                      <span style={{ fontSize: 15, padding: "3px 8px", background: "rgba(91,141,239,0.12)", color: COLORS.blue, borderRadius: 4, fontWeight: 600 }}>CONTAINS FORECAST</span>
                    )}
                    {segment !== "all" && (
                      <span style={{ fontSize: 15, padding: "3px 8px", background: "rgba(199,120,64,0.12)", color: COLORS.accent, borderRadius: 4, fontWeight: 600 }}>FILTERED: {segment}</span>
                    )}
                  </div>
                </div>
                {/* Dimensional drill-through — above the table so it's immediately visible */}
                {!loading && drillLine && rawFSData && (
                  <div style={{ margin: "0 20px 12px" }}>
                    <DimensionalDetail
                      lineKey={drillLine.id}
                      lineName={drillLine.name}
                      entityId={entity}
                      period={effectiveQuarter}
                      fsData={rawFSData}
                      onClose={() => setDrillLine(null)}
                    />
                  </div>
                )}
                <StatementTable data={currentData} pyData={pyData} showVariance={variant !== "quarterly"} onDrillLine={(id, name) => setDrillLine(drillLine?.id === id ? null : { id, name })} />
              </div>
            )}
          </div>
        )}

        {tab === "recon" && <ReconView />}
        {tab === "combining" && entity === "combined" && (
          <div style={{ maxWidth: CONTENT_MAX_WIDTH, margin: "0 auto" }}>
            <div style={{ display: "flex", gap: 16, marginBottom: 24, flexWrap: "wrap" }}>
              <Select label="Report Variant" value={combiningVariant} onChange={setCombiningVariant} options={[
                { value: "act_vs_py", label: `FY${lastFullYear} Act vs FY${pyYear}` },
                { value: "q_act_vs_py", label: "Quarterly Act vs PY" },
                { value: "cf_vs_py", label: `FY${wallClockDate().getFullYear()} CF vs FY${lastFullYear}` },
                { value: "q_cf_vs_py", label: "Quarterly CF vs PY" },
              ]} width={220} />
              {(combiningVariant === "q_act_vs_py" || combiningVariant === "q_cf_vs_py") && (
                <Select label="Quarter" value={combiningQuarter} onChange={setCombiningQuarter} options={
                  combiningVariant === "q_cf_vs_py"
                    ? cfQuarters.map((q) => ({ value: q, label: q }))
                    : actQuarters.map((q) => ({ value: q, label: q }))
                } width={140} />
              )}
              <Select label="Segment" value={combiningSegment} onChange={setCombiningSegment} width={180} options={[
                { value: "all", label: "All Segments" },
                ...availableSegments.map((s) => ({ value: s, label: s })),
              ]} />
            </div>
            <CombiningStatement data={combiningData} loading={combiningLoading} error={combiningError} onRetry={loadCombining} />
          </div>
        )}
        {tab === "overlap" && entity === "combined" && (
          <OverlapReport data={overlapData} loading={overlapLoading} error={overlapError} onRetry={loadOverlap} />
        )}
        {tab === "crosssell" && entity === "combined" && (
          <div style={{ maxWidth: CONTENT_MAX_WIDTH, margin: "0 auto" }}><CrossSellTab /></div>
        )}
        {tab === "pipeline" && <PipelineTab period={String(lastFullYear)} />}
        {tab === "bridge" && entity === "combined" && (
          <div style={{ maxWidth: CONTENT_MAX_WIDTH, margin: "0 auto" }}><EBITDABridgeTab /></div>
        )}
        {tab === "whatif" && entity === "combined" && <WhatIfTab />}
        {tab === "qoe" && entity === "combined" && (
          <div style={{ maxWidth: CONTENT_MAX_WIDTH, margin: "0 auto" }}><QofETab /></div>
        )}

        {tab === "rev_by_customer" && entity !== "combined" && <RevenueByCustomerTab entityId={entity} />}
      </div>

      {/* Maestra floating chat — always visible */}
      <MaestraFloatingChat
        onNavigate={(t) => { setTab(t); }}
        onEntityChange={(e) => { setEntity(e); }}
      />
    </div>
  );
}

export default ReportPortal;
