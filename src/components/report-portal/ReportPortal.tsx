import { useState, useEffect, useCallback, useMemo } from "react";
import { createPortal } from "react-dom";
import { fetchReport, fetchDrillThrough, fetchReconciliation, fetchCombiningStatement, fetchOverlapData, fetchCrossSell, fetchEBITDABridge, fetchWhatIf, fetchQofE, fetchDashboard, createMaestraEngagement, sendMaestraMessage, fetchMaestraStatus } from "./api";
import React from "react";
import type { ReportData, ReconReport, ReconCheck, DrillThroughItem, ReportVariant, EntitySelection, CombiningStatementData, OverlapData, CrossSellData, EBITDABridgeData, BridgeAdjustment, WhatIfResult, QofEData, DashboardData, DashboardPersona, MaestraStatus, FinancialStatementData, FinancialStatementLineItem } from "./types";

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

function fmtM(n: number | null | undefined): string {
  if (n === null || n === undefined) return "\u2014";
  const m = n / 1_000_000;
  const abs = Math.abs(m);
  const s = abs.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 });
  return n < 0 ? `($${s}M)` : `$${s}M`;
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
const QUARTERS = [
  "2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4",
  "2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4",
  "2026-Q1", "2026-Q2", "2026-Q3", "2026-Q4",
];
const SEGMENTS = ["Strategy", "Operations", "Technology", "Risk", "Digital/AI", "Commercial"];

function wallClockDate() { return new Date(); }
function isActual(q: string) {
  const [y, qn] = q.split("-");
  const qEnd = new Date(parseInt(y), parseInt(qn.replace("Q", "")) * 3, 0);
  return qEnd < wallClockDate();
}

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
        <span style={{ fontSize: 11, color: COLORS.textMuted, letterSpacing: "0.05em", textTransform: "uppercase", fontFamily: "'JetBrains Mono',monospace" }}>
          {label}
        </span>
      )}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          width, padding: "8px 12px", background: COLORS.surface, color: COLORS.text, border: `1px solid ${COLORS.border}`,
          borderRadius: 6, fontSize: 13, fontFamily: "'IBM Plex Sans',sans-serif", cursor: "pointer", outline: "none",
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

function TabBar({ tabs, active, onChange }: { tabs: { id: string; label: string }[]; active: string; onChange: (id: string) => void }) {
  return (
    <div style={{ display: "flex", gap: 2, borderBottom: `1px solid ${COLORS.border}`, marginBottom: 20 }}>
      {tabs.map((t) => (
        <button key={t.id} onClick={() => onChange(t.id)} style={{
          padding: "10px 20px", background: active === t.id ? COLORS.surface : "transparent",
          color: active === t.id ? COLORS.accent : COLORS.textMuted, border: "none",
          borderBottom: active === t.id ? `2px solid ${COLORS.accent}` : "2px solid transparent",
          cursor: "pointer", fontSize: 13, fontFamily: "'IBM Plex Sans',sans-serif",
          fontWeight: active === t.id ? 600 : 400, transition: "all 0.15s", letterSpacing: "0.02em",
        }}>
          {t.label}
        </button>
      ))}
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
      <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "'IBM Plex Mono','JetBrains Mono',monospace", fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: `2px solid ${COLORS.accent}` }}>
            <th style={{ textAlign: "left", padding: "10px 16px", color: COLORS.textMuted, fontWeight: 500, width: "40%", fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>
              {denomLabel && <span style={{ fontWeight: 400, fontSize: 10, fontStyle: "italic", letterSpacing: "0.04em", color: COLORS.textDim }}>{denomLabel}</span>}
            </th>
            <th style={{ textAlign: "right", padding: "10px 16px", color: COLORS.textMuted, fontWeight: 500, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>
              {data.metadata.periodType === "forecast" ? "CF " : ""}{data.metadata.quarter}
            </th>
            {showVariance && pyData && (
              <>
                <th style={{ textAlign: "right", padding: "10px 16px", color: COLORS.textMuted, fontWeight: 500, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>PY</th>
                <th style={{ textAlign: "right", padding: "10px 16px", color: COLORS.textMuted, fontWeight: 500, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>Var $</th>
                <th style={{ textAlign: "right", padding: "10px 16px", color: COLORS.textMuted, fontWeight: 500, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>Var %</th>
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
                  fontSize: line.isHeader ? 12 : 13,
                  letterSpacing: line.isHeader ? "0.06em" : "0",
                  textTransform: line.isHeader ? "uppercase" as const : "none" as const,
                  fontFamily: "'IBM Plex Sans',sans-serif",
                  cursor: canDrill ? "pointer" : "default",
                }}>
                  {canDrill && <span style={{ color: COLORS.accent, marginRight: 6, fontSize: 10 }}>{"\u25B8"}</span>}
                  {line.name}
                  {line.highlight && <span style={{ marginLeft: 8, fontSize: 10, color: COLORS.accent, background: "rgba(199,120,64,0.12)", padding: "2px 6px", borderRadius: 3 }}>SYNERGY</span>}
                </td>
                <td style={{ textAlign: "right", padding: "8px 16px", color: line.isPercent ? COLORS.textMuted : COLORS.text, fontWeight: line.bold ? 600 : 400 }}>
                  {line.isHeader ? "" : fmt(line.amount, line.isPercent)}
                  {data.metadata.periodType === "forecast" && !line.isHeader && !line.isPercent && (
                    <span style={{ marginLeft: 4, fontSize: 9, color: COLORS.textDim }}>CF</span>
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

function DrillThrough({ onClose }: { onClose: () => void }) {
  const [path, setPath] = useState<{ level: string; parent: string | null; label: string }[]>([{ level: "region", parent: null, label: "Revenue" }]);
  const [data, setData] = useState<DrillThroughItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const current = path[path.length - 1];

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchDrillThrough(current.level as "region" | "rep" | "customer" | "project", current.parent || undefined)
      .then((items) => { if (!cancelled) setData(items); })
      .catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : String(err)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [current.level, current.parent]);

  const total = data.reduce((s, d) => s + d.revenue, 0);

  function drillIn(item: DrillThroughItem) {
    if (!item.children) return;
    const levels: Record<string, string> = { region: "rep", rep: "customer", customer: "project" };
    setPath([...path, { level: levels[current.level], parent: item.name, label: item.name }]);
  }

  return (
    <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, overflow: "hidden" }}>
      <div style={{ padding: "16px 20px", borderBottom: `1px solid ${COLORS.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>Revenue Drill-Through</span>
          <div style={{ display: "flex", gap: 4, marginLeft: 12 }}>
            {path.map((p, i) => (
              <span key={i} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                {i > 0 && <span style={{ color: COLORS.textDim }}>{"\u203A"}</span>}
                <button onClick={() => setPath(path.slice(0, i + 1))} style={{
                  background: i === path.length - 1 ? "rgba(199,120,64,0.12)" : "transparent",
                  color: i === path.length - 1 ? COLORS.accent : COLORS.textMuted,
                  border: "none", cursor: "pointer", padding: "3px 8px", borderRadius: 4, fontSize: 12,
                  fontFamily: "'IBM Plex Sans',sans-serif",
                }}>
                  {p.label}
                </button>
              </span>
            ))}
          </div>
        </div>
        <button onClick={onClose} style={{ background: "transparent", border: "none", color: COLORS.textMuted, cursor: "pointer", fontSize: 16 }}>{"\u2715"}</button>
      </div>

      {loading && (
        <div style={{ padding: "40px 20px", textAlign: "center" }}>
          <span style={{ fontSize: 13, color: COLORS.textMuted, fontFamily: "'IBM Plex Sans',sans-serif" }}>Loading drill-through data...</span>
        </div>
      )}

      {error && !loading && (
        <div style={{ padding: "20px", background: COLORS.redBg, borderTop: `1px solid ${COLORS.red}33` }}>
          <p style={{ fontSize: 13, color: COLORS.red, fontFamily: "'IBM Plex Sans',sans-serif", margin: 0 }}>Error: {error}</p>
          <button onClick={() => setPath([...path])} style={{ marginTop: 8, fontSize: 12, color: COLORS.red, background: "transparent", border: "none", cursor: "pointer", textDecoration: "underline" }}>Retry</button>
        </div>
      )}

      {!loading && !error && (
        <div style={{ padding: "0 4px" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "'IBM Plex Mono',monospace", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                <th style={{ textAlign: "left", padding: "10px 16px", color: COLORS.textMuted, fontWeight: 500, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>
                  {current.level === "region" ? "Region" : current.level === "rep" ? "Rep" : current.level === "customer" ? "Customer" : "Project"}
                </th>
                <th style={{ textAlign: "right", padding: "10px 16px", color: COLORS.textMuted, fontWeight: 500, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>Revenue</th>
                <th style={{ textAlign: "right", padding: "10px 16px", color: COLORS.textMuted, fontWeight: 500, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>% of Total</th>
                {current.level === "rep" && <th style={{ textAlign: "right", padding: "10px 16px", color: COLORS.textMuted, fontWeight: 500, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>Clients</th>}
                {current.level === "customer" && <th style={{ textAlign: "right", padding: "10px 16px", color: COLORS.textMuted, fontWeight: 500, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>Projects</th>}
              </tr>
            </thead>
            <tbody>
              {data.map((item, i) => (
                <tr key={i} onClick={() => item.children && drillIn(item)} style={{
                  borderBottom: `1px solid ${COLORS.border}22`, cursor: item.children ? "pointer" : "default",
                  transition: "background 0.1s",
                }} onMouseEnter={(e) => { if (item.children) (e.currentTarget as HTMLElement).style.background = COLORS.surfaceHover; }}
                  onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "transparent"; }}>
                  <td style={{ padding: "10px 16px", color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>
                    {item.children && <span style={{ color: COLORS.accent, marginRight: 8 }}>{"\u25B8"}</span>}
                    {item.name}
                  </td>
                  <td style={{ textAlign: "right", padding: "10px 16px", color: COLORS.text }}>{fmtFull(item.revenue)}</td>
                  <td style={{ textAlign: "right", padding: "10px 16px", color: COLORS.textMuted }}>{total > 0 ? (item.revenue / total * 100).toFixed(1) : "0.0"}%</td>
                  {current.level === "rep" && <td style={{ textAlign: "right", padding: "10px 16px", color: COLORS.textMuted }}>{item.customers}</td>}
                  {current.level === "customer" && <td style={{ textAlign: "right", padding: "10px 16px", color: COLORS.textMuted }}>{item.projects}</td>}
                </tr>
              ))}
              <tr style={{ borderTop: `2px solid ${COLORS.accent}`, background: COLORS.totalBg }}>
                <td style={{ padding: "10px 16px", fontWeight: 600, color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>Total</td>
                <td style={{ textAlign: "right", padding: "10px 16px", fontWeight: 600, color: COLORS.text }}>{fmtFull(total)}</td>
                <td style={{ textAlign: "right", padding: "10px 16px", color: COLORS.textMuted }}>100.0%</td>
                {(current.level === "rep" || current.level === "customer") && <td></td>}
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ============================================================
// LINE ITEM DETAIL (non-revenue drill-through)
// ============================================================
function LineDetail({ lineKey, lineName, fsData, onClose }: { lineKey: string; lineName: string; fsData: FinancialStatementData; onClose: () => void }) {
  const lineItem = fsData.line_items.find((li) => li.key === lineKey);
  if (!lineItem) return null;

  // Find child lines: lines between this line and the next line at same or lower indent,
  // that are at higher indent (children). For subtotals, find the preceding detail lines.
  const idx = fsData.line_items.indexOf(lineItem);
  const children: FinancialStatementLineItem[] = [];

  if (lineItem.is_subtotal) {
    // Walk backward from this subtotal to find its children (indent > 0 lines above it until we hit a header or another subtotal at same level)
    for (let i = idx - 1; i >= 0; i--) {
      const li = fsData.line_items[i];
      if (li.is_subtotal || (li.indent === 0 && !li.key)) break;
      if (li.format !== 'percent') children.unshift(li);
    }
  } else {
    // Walk forward from this line to find children at deeper indent
    for (let i = idx + 1; i < fsData.line_items.length; i++) {
      const li = fsData.line_items[i];
      if (li.indent <= lineItem.indent) break;
      if (li.format !== 'percent') children.push(li);
    }
  }

  // Filter to non-variance periods (CY and PY, not "Variance")
  const periods = fsData.periods.filter((p) => !p.toLowerCase().includes('variance'));

  return (
    <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, overflow: "hidden" }}>
      <div style={{ padding: "16px 20px", borderBottom: `1px solid ${COLORS.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: COLORS.text }}>{lineName} — Detail</span>
        <button onClick={onClose} style={{ background: "transparent", border: "none", color: COLORS.textMuted, cursor: "pointer", fontSize: 16 }}>{"\u2715"}</button>
      </div>

      {/* Period values for this line */}
      <div style={{ padding: "12px 20px", borderBottom: children.length > 0 ? `1px solid ${COLORS.border}` : "none" }}>
        <div style={{ fontSize: 11, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>Across Periods</div>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          {periods.map((p) => {
            const val = lineItem.values[p];
            return (
              <div key={p} style={{ background: COLORS.bg, borderRadius: 6, padding: "8px 14px", minWidth: 100 }}>
                <div style={{ fontSize: 10, color: COLORS.textMuted, marginBottom: 2 }}>{p}</div>
                <div style={{ fontSize: 14, fontWeight: 600, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>
                  {val !== null && val !== undefined ? fmt(val, lineItem.format === 'percent') : "\u2014"}
                </div>
              </div>
            );
          })}
        </div>
        {periods.length >= 2 && (() => {
          const vals = periods.map((p) => lineItem.values[p]).filter((v): v is number => v !== null && v !== undefined);
          if (vals.length >= 2) {
            const first = vals[0];
            const last = vals[vals.length - 1];
            const change = first !== 0 ? ((last - first) / Math.abs(first)) * 100 : 0;
            return (
              <div style={{ marginTop: 8, fontSize: 12, color: change >= 0 ? COLORS.green : COLORS.red }}>
                {change >= 0 ? "\u25B2" : "\u25BC"} {Math.abs(change).toFixed(1)}% from {periods[0]} to {periods[periods.length - 1]}
              </div>
            );
          }
          return null;
        })()}
      </div>

      {/* Component breakdown for aggregate lines */}
      {children.length > 0 && (
        <div style={{ padding: "12px 20px" }}>
          <div style={{ fontSize: 11, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 8 }}>Component Breakdown</div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "'IBM Plex Mono',monospace", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                <th style={{ textAlign: "left", padding: "8px 12px", color: COLORS.textMuted, fontWeight: 500, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>Item</th>
                {periods.map((p) => (
                  <th key={p} style={{ textAlign: "right", padding: "8px 12px", color: COLORS.textMuted, fontWeight: 500, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>{p}</th>
                ))}
                <th style={{ textAlign: "right", padding: "8px 12px", color: COLORS.textMuted, fontWeight: 500, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>% of Total</th>
              </tr>
            </thead>
            <tbody>
              {children.map((child) => {
                const parentVal = lineItem.values[periods[0]];
                const childVal = child.values[periods[0]];
                const pctOfTotal = parentVal && childVal ? (childVal / Math.abs(parentVal)) * 100 : null;
                return (
                  <tr key={child.key} style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                    <td style={{ padding: "8px 12px", color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>{child.label}</td>
                    {periods.map((p) => (
                      <td key={p} style={{ textAlign: "right", padding: "8px 12px", color: COLORS.text }}>{fmt(child.values[p])}</td>
                    ))}
                    <td style={{ textAlign: "right", padding: "8px 12px", color: COLORS.textMuted }}>{pctOfTotal !== null ? pctOfTotal.toFixed(1) + "%" : "\u2014"}</td>
                  </tr>
                );
              })}
              <tr style={{ borderTop: `2px solid ${COLORS.accent}`, background: COLORS.totalBg }}>
                <td style={{ padding: "8px 12px", fontWeight: 600, color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>{lineName}</td>
                {periods.map((p) => (
                  <td key={p} style={{ textAlign: "right", padding: "8px 12px", fontWeight: 600, color: COLORS.text }}>{fmt(lineItem.values[p])}</td>
                ))}
                <td style={{ textAlign: "right", padding: "8px 12px", fontWeight: 600, color: COLORS.textMuted }}>100.0%</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function CheckDetail({ check }: { check: ReconCheck }) {
  if (!check.mismatches || check.mismatches.length === 0) {
    return (
      <div style={{ padding: "16px 20px", display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ fontSize: 16, color: COLORS.green }}>&#10003;</span>
        <span style={{ fontSize: 13, color: COLORS.green, fontFamily: "'IBM Plex Sans',sans-serif", fontWeight: 500 }}>
          All {check.total} metrics reconciled — no variances
        </span>
      </div>
    );
  }

  return (
    <div style={{ padding: "0 8px 12px", maxHeight: 300, overflowY: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "'IBM Plex Mono',monospace", fontSize: 12 }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
            <th style={{ textAlign: "left", padding: "6px 12px", color: COLORS.textDim, fontSize: 10, letterSpacing: "0.06em", textTransform: "uppercase" }}>Metric</th>
            <th style={{ textAlign: "left", padding: "6px 12px", color: COLORS.textDim, fontSize: 10, letterSpacing: "0.06em", textTransform: "uppercase" }}>Status</th>
            <th style={{ textAlign: "right", padding: "6px 12px", color: COLORS.textDim, fontSize: 10, letterSpacing: "0.06em", textTransform: "uppercase" }}>Expected</th>
            <th style={{ textAlign: "right", padding: "6px 12px", color: COLORS.textDim, fontSize: 10, letterSpacing: "0.06em", textTransform: "uppercase" }}>Actual</th>
            <th style={{ textAlign: "right", padding: "6px 12px", color: COLORS.textDim, fontSize: 10, letterSpacing: "0.06em", textTransform: "uppercase" }}>Delta</th>
            <th style={{ textAlign: "right", padding: "6px 12px", color: COLORS.textDim, fontSize: 10, letterSpacing: "0.06em", textTransform: "uppercase" }}>% Off</th>
          </tr>
        </thead>
        <tbody>
          {check.mismatches.map((m, i) => (
            <tr key={i} style={{ borderBottom: `1px solid ${COLORS.border}15` }}>
              <td style={{ padding: "6px 12px", color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif", fontSize: 12 }}>
                {m.metric.replace(/_/g, " ")}
              </td>
              <td style={{ padding: "6px 12px" }}>
                <span style={{
                  fontSize: 10, padding: "2px 6px", borderRadius: 3, fontWeight: 600,
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

  useEffect(() => {
    fetchReconciliation()
      .then(setRecon)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, []);

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
        <span style={{ fontSize: 13, color: COLORS.textMuted, fontFamily: "'IBM Plex Sans',sans-serif" }}>Loading reconciliation data...</span>
      </div>
    );
  }

  if (error || !recon) {
    return (
      <div style={{ padding: "20px", background: COLORS.redBg, borderRadius: 8, border: `1px solid ${COLORS.red}33` }}>
        <p style={{ fontSize: 13, color: COLORS.red, fontFamily: "'IBM Plex Sans',sans-serif", margin: 0 }}>Error loading reconciliation: {error || "No data returned"}</p>
        <button onClick={() => { setLoading(true); setError(null); fetchReconciliation().then(setRecon).catch((e) => setError(String(e))).finally(() => setLoading(false)); }}
          style={{ marginTop: 8, fontSize: 12, color: COLORS.red, background: "transparent", border: "none", cursor: "pointer", textDecoration: "underline" }}>Retry</button>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 24, marginBottom: 24 }}>
        <div style={{ background: recon.totalRed === 0 ? COLORS.greenBg : COLORS.redBg, border: `1px solid ${recon.totalRed === 0 ? COLORS.green : COLORS.red}33`, borderRadius: 8, padding: "16px 24px", flex: 1 }}>
          <div style={{ fontSize: 32, fontWeight: 700, color: recon.totalRed === 0 ? COLORS.green : COLORS.red, fontFamily: "'IBM Plex Mono',monospace" }}>{recon.totalRed === 0 ? "PASS" : "FAIL"}</div>
          <div style={{ fontSize: 13, color: COLORS.textMuted, marginTop: 4 }}>{recon.totalChecks.toLocaleString()} checks</div>
        </div>
        <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "16px 24px", flex: 1 }}>
          <div style={{ fontSize: 32, fontWeight: 700, color: COLORS.green, fontFamily: "'IBM Plex Mono',monospace" }}>{recon.totalGreen.toLocaleString()}</div>
          <div style={{ fontSize: 13, color: COLORS.textMuted, marginTop: 4 }}>GREEN (matched)</div>
        </div>
        <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "16px 24px", flex: 1 }}>
          <div style={{ fontSize: 32, fontWeight: 700, color: recon.totalRed > 0 ? COLORS.red : COLORS.textDim, fontFamily: "'IBM Plex Mono',monospace" }}>{recon.totalRed}</div>
          <div style={{ fontSize: 13, color: COLORS.textMuted, marginTop: 4 }}>RED (variance)</div>
        </div>
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "'IBM Plex Mono',monospace", fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: `2px solid ${COLORS.accent}` }}>
            <th style={{ textAlign: "left", padding: "8px 16px", color: COLORS.textMuted, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase", width: 24 }}></th>
            <th style={{ textAlign: "left", padding: "8px 16px", color: COLORS.textMuted, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>Statement</th>
            <th style={{ textAlign: "left", padding: "8px 16px", color: COLORS.textMuted, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>Period</th>
            <th style={{ textAlign: "right", padding: "8px 16px", color: COLORS.textMuted, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>Checks</th>
            <th style={{ textAlign: "right", padding: "8px 16px", color: COLORS.textMuted, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>Green</th>
            <th style={{ textAlign: "right", padding: "8px 16px", color: COLORS.textMuted, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>Red</th>
            <th style={{ textAlign: "center", padding: "8px 16px", color: COLORS.textMuted, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>Status</th>
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
                  <td style={{ padding: "8px 8px 8px 16px", color: COLORS.accent, fontSize: 11, width: 24 }}>
                    {isExpanded ? "\u25BE" : "\u25B8"}
                  </td>
                  <td style={{ padding: "8px 16px", color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>{c.statement}</td>
                  <td style={{ padding: "8px 16px", color: COLORS.textMuted }}>{c.period}</td>
                  <td style={{ textAlign: "right", padding: "8px 16px", color: COLORS.textMuted }}>{c.total}</td>
                  <td style={{ textAlign: "right", padding: "8px 16px", color: COLORS.green }}>{c.green}</td>
                  <td style={{ textAlign: "right", padding: "8px 16px", color: c.red > 0 ? COLORS.red : COLORS.textDim }}>{c.red}</td>
                  <td style={{ textAlign: "center", padding: "8px 16px" }}>
                    <span style={{
                      fontSize: 11, padding: "3px 10px", borderRadius: 4, fontWeight: 600,
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
    </div>
  );
}

// ============================================================
// ENTITY SELECTOR
// ============================================================

function EntitySelector({ selected, onChange }: { selected: EntitySelection; onChange: (e: EntitySelection) => void }) {
  const entities: { id: EntitySelection; label: string }[] = [
    { id: "meridian", label: "Meridian" },
    { id: "cascadia", label: "Cascadia" },
    { id: "combined", label: "Combined" },
  ];
  return (
    <div style={{ display: "flex", gap: 4, padding: "12px 32px 0", background: COLORS.headerBg }}>
      {entities.map((e) => (
        <button key={e.id} onClick={() => onChange(e.id)} style={{
          padding: "7px 18px", fontSize: 12, fontWeight: selected === e.id ? 600 : 400,
          fontFamily: "'IBM Plex Sans',sans-serif", letterSpacing: "0.03em", cursor: "pointer",
          transition: "all 0.15s", borderRadius: "6px 6px 0 0",
          background: selected === e.id ? COLORS.surface : "transparent",
          color: selected === e.id ? COLORS.text : COLORS.textMuted,
          border: selected === e.id
            ? `1px solid ${COLORS.borderLight}`
            : `1px solid transparent`,
          borderBottom: selected === e.id
            ? `1px solid ${COLORS.surface}`
            : `1px solid transparent`,
        }}>
          {e.label}
        </button>
      ))}
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
    fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase",
    fontFamily: "'JetBrains Mono',monospace",
  };

  return (
    <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, overflow: "hidden" }}>
      <div style={{ padding: "12px 20px", borderBottom: `1px solid ${COLORS.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: COLORS.text }}>Combining Income Statement</span>
        <span style={{ fontSize: 12, color: COLORS.textMuted }}>{data.period}</span>
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "'IBM Plex Mono','JetBrains Mono',monospace", fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: `2px solid ${COLORS.accent}` }}>
              <th style={{ ...thStyle, textAlign: "left", width: "30%" }}>
                Line Item
                {" "}
                <span style={{ fontWeight: 400, fontSize: 10, fontStyle: "italic", letterSpacing: "0.04em", color: COLORS.textDim }}>($MM)</span>
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

  const thS: React.CSSProperties = { textAlign: "left", padding: "6px 10px", color: COLORS.textMuted, fontSize: 10, letterSpacing: "0.06em", textTransform: "uppercase", fontFamily: "'JetBrains Mono',monospace" };
  const thR: React.CSSProperties = { ...thS, textAlign: "right" };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* Customer Overlap */}
      <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, overflow: "hidden" }}>
        <div style={{ padding: "12px 20px", borderBottom: `1px solid ${COLORS.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: COLORS.text }}>Customer Overlap</span>
          <button onClick={() => setCustExpanded(!custExpanded)} style={{ background: "rgba(199,120,64,0.08)", border: `1px solid ${COLORS.accent}33`, borderRadius: 4, color: COLORS.accent, fontSize: 11, padding: "4px 12px", cursor: "pointer", fontWeight: 600 }}>
            {custExpanded ? "Collapse" : `View All ${co.total_overlapping} Matches`}
          </button>
        </div>
        {/* Summary cards — all clickable */}
        <div style={{ padding: "16px 20px", display: "flex", gap: 16, cursor: "pointer" }} onClick={() => setCustExpanded(!custExpanded)}>
          <div style={{ background: COLORS.bg, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 20px", flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.accent, fontFamily: "'IBM Plex Mono',monospace" }}>{co.total_overlapping}</div>
            <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 4 }}>Overlapping Customers</div>
          </div>
          <div style={{ background: COLORS.bg, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 20px", flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.textDim, fontFamily: "'IBM Plex Mono',monospace" }}>{co.overlap_pct_of_combined.toFixed(1)}%</div>
            <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 4 }}>of Combined Revenue</div>
          </div>
          <div style={{ background: COLORS.bg, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 20px", flex: 2 }}>
            <div style={{ fontSize: 11, color: COLORS.textMuted, marginBottom: 6 }}>Match Type Breakdown</div>
            <div style={{ display: "flex", gap: 16, fontSize: 13, fontFamily: "'IBM Plex Mono',monospace" }}>
              <span style={{ color: COLORS.green }}>Exact: {matchCounts.exact}</span>
              <span style={{ color: COLORS.accent }}>Fuzzy: {matchCounts.fuzzy}</span>
              <span style={{ color: COLORS.red }}>Manual: {matchCounts.manual}</span>
            </div>
          </div>
        </div>

        {/* Expanded match table */}
        {custExpanded && (
          <div style={{ borderTop: `1px solid ${COLORS.border}` }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
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
                          <span style={{ color: COLORS.accent, marginRight: 6, fontSize: 9 }}>{isExp ? "\u25BE" : "\u25B8"}</span>
                          {m.canonical_name}
                        </td>
                        <td style={{ padding: "6px 10px" }}>
                          <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 3, fontWeight: 600, color: m.match_type === "exact" ? COLORS.green : m.match_type === "fuzzy" ? COLORS.accent : COLORS.red, background: m.match_type === "exact" ? COLORS.greenBg : m.match_type === "fuzzy" ? "rgba(199,120,64,0.08)" : COLORS.redBg }}>
                            {m.match_type.toUpperCase()}
                          </span>
                        </td>
                        <td style={{ textAlign: "right", padding: "6px 10px", color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{m.meridian_revenue_M.toFixed(1)}</td>
                        <td style={{ textAlign: "right", padding: "6px 10px", color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{m.cascadia_revenue_M.toFixed(1)}</td>
                        <td style={{ textAlign: "right", padding: "6px 10px", color: COLORS.text, fontWeight: 600, fontFamily: "'IBM Plex Mono',monospace" }}>{m.combined_revenue_M.toFixed(1)}</td>
                        <td style={{ textAlign: "right", padding: "6px 10px", color: COLORS.textMuted, fontFamily: "'IBM Plex Mono',monospace" }}>{m.combined_pct_of_total.toFixed(2)}%</td>
                        <td style={{ padding: "6px 10px", color: COLORS.textMuted, fontFamily: "'IBM Plex Sans',sans-serif", fontSize: 11 }}>{m.industry}</td>
                        <td style={{ padding: "6px 10px" }}>
                          {m.concentration_flag && <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 3, fontWeight: 600, color: COLORS.red, background: COLORS.redBg }}>CONC</span>}
                        </td>
                      </tr>
                      {isExp && (
                        <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                          <td colSpan={8} style={{ padding: "10px 20px 14px 32px", background: COLORS.surface }}>
                            <div style={{ fontSize: 12, color: COLORS.textMuted, lineHeight: 1.6, fontFamily: "'IBM Plex Sans',sans-serif" }}>
                              <div><span style={{ color: COLORS.textDim }}>Meridian Name:</span> {m.meridian_name}</div>
                              <div><span style={{ color: COLORS.textDim }}>Cascadia Name:</span> {m.cascadia_name}</div>
                              <div><span style={{ color: COLORS.textDim }}>Confidence:</span> {(m.confidence * 100).toFixed(0)}%</div>
                              <div><span style={{ color: COLORS.textDim }}>Notes:</span> {m.notes}</div>
                              {m.engagement_detail && m.engagement_detail.length > 0 && (
                                <div style={{ marginTop: 8 }}>
                                  <div style={{ fontWeight: 600, color: COLORS.text, marginBottom: 4 }}>Engagement Detail:</div>
                                  {m.engagement_detail.map((ed, i) => (
                                    <div key={i} style={{ marginLeft: 12, marginBottom: 4, fontSize: 11 }}>
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
          <span style={{ fontSize: 14, fontWeight: 600, color: COLORS.text }}>Vendor Overlap</span>
          <button onClick={() => setVendExpanded(!vendExpanded)} style={{ background: "rgba(199,120,64,0.08)", border: `1px solid ${COLORS.accent}33`, borderRadius: 4, color: COLORS.accent, fontSize: 11, padding: "4px 12px", cursor: "pointer", fontWeight: 600 }}>
            {vendExpanded ? "Collapse" : `View All ${vo.total_overlapping} Matches`}
          </button>
        </div>
        <div style={{ padding: "16px 20px", display: "flex", gap: 16, cursor: "pointer" }} onClick={() => setVendExpanded(!vendExpanded)}>
          <div style={{ background: COLORS.bg, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 20px", flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.accent, fontFamily: "'IBM Plex Mono',monospace" }}>{vo.total_overlapping}</div>
            <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 4 }}>Overlapping Vendors</div>
          </div>
          <div style={{ background: COLORS.bg, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 20px", flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.textDim, fontFamily: "'IBM Plex Mono',monospace" }}>{vo.overlap_pct_of_combined.toFixed(1)}%</div>
            <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 4 }}>of Combined Spend</div>
          </div>
        </div>

        {vendExpanded && (
          <div style={{ borderTop: `1px solid ${COLORS.border}` }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
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
                          <span style={{ color: COLORS.accent, marginRight: 6, fontSize: 9 }}>{isExp ? "\u25BE" : "\u25B8"}</span>
                          {v.canonical_name}
                        </td>
                        <td style={{ padding: "6px 10px", color: COLORS.textMuted, fontSize: 11 }}>{v.category?.replace(/_/g, " ")}</td>
                        <td style={{ padding: "6px 10px" }}>
                          <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 3, fontWeight: 600, color: v.match_type === "exact" ? COLORS.green : COLORS.accent, background: v.match_type === "exact" ? COLORS.greenBg : "rgba(199,120,64,0.08)" }}>
                            {v.match_type.toUpperCase()}
                          </span>
                        </td>
                        <td style={{ textAlign: "right", padding: "6px 10px", color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{v.meridian_spend_M.toFixed(1)}</td>
                        <td style={{ textAlign: "right", padding: "6px 10px", color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{v.cascadia_spend_M.toFixed(1)}</td>
                        <td style={{ textAlign: "right", padding: "6px 10px", color: COLORS.text, fontWeight: 600, fontFamily: "'IBM Plex Mono',monospace" }}>{v.combined_spend_M.toFixed(1)}</td>
                        <td style={{ padding: "6px 10px" }}>
                          {v.consolidation_opportunity && <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 3, fontWeight: 600, color: COLORS.green, background: COLORS.greenBg }}>YES</span>}
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
                                  <div style={{ fontSize: 10, color: COLORS.textDim, marginBottom: 2 }}>Meridian Contract</div>
                                  <div style={{ fontSize: 12, color: COLORS.text }}>{String(d.meridian_contract_type || "—")} · ends {String(d.meridian_contract_end || "—")}</div>
                                </div>
                                <div>
                                  <div style={{ fontSize: 10, color: COLORS.textDim, marginBottom: 2 }}>Cascadia Contract</div>
                                  <div style={{ fontSize: 12, color: COLORS.text }}>{String(d.cascadia_contract_type || "—")} · ends {String(d.cascadia_contract_end || "—")}</div>
                                </div>
                                {savM !== null && (
                                  <div>
                                    <div style={{ fontSize: 10, color: COLORS.textDim, marginBottom: 2 }}>Est. Savings</div>
                                    <div style={{ fontSize: 13, color: COLORS.green, fontWeight: 700, fontFamily: "'IBM Plex Mono',monospace" }}>
                                      ${savM.toFixed(1)}M{savPct !== null && <span style={{ fontWeight: 400, fontSize: 11, marginLeft: 4 }}>({savPct.toFixed(1)}%)</span>}
                                    </div>
                                  </div>
                                )}
                              </div>
                              {!!d.savings_rationale && (
                                <div style={{ fontSize: 11, color: COLORS.textMuted, marginBottom: 8, fontStyle: "italic" }}>{String(d.savings_rationale)}</div>
                              )}
                              {subcats.length > 0 && (
                                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                                  {subcats.map((s) => (
                                    <span key={s} style={{ fontSize: 10, padding: "2px 8px", borderRadius: 3, background: `${COLORS.accent}15`, color: COLORS.accent, border: `1px solid ${COLORS.accent}30` }}>{s}</span>
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
          <span style={{ fontSize: 14, fontWeight: 600, color: COLORS.text }}>People Overlap</span>
          <button onClick={() => setPeopleExpanded(!peopleExpanded)} style={{ background: "rgba(199,120,64,0.08)", border: `1px solid ${COLORS.accent}33`, borderRadius: 4, color: COLORS.accent, fontSize: 11, padding: "4px 12px", cursor: "pointer", fontWeight: 600 }}>
            {peopleExpanded ? "Collapse" : `View All ${po.functions.length} Functions`}
          </button>
        </div>
        {/* Summary cards */}
        <div style={{ padding: "16px 20px", display: "flex", gap: 16, cursor: "pointer" }} onClick={() => setPeopleExpanded(!peopleExpanded)}>
          <div style={{ background: COLORS.bg, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 20px", flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.accent, fontFamily: "'IBM Plex Mono',monospace" }}>{po.total_meridian_corporate.toLocaleString()}</div>
            <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 4 }}>Meridian Headcount</div>
          </div>
          <div style={{ background: COLORS.bg, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 20px", flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.accent, fontFamily: "'IBM Plex Mono',monospace" }}>{po.total_cascadia_corporate.toLocaleString()}</div>
            <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 4 }}>Cascadia Headcount</div>
          </div>
          <div style={{ background: COLORS.bg, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 20px", flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{po.total_combined_corporate.toLocaleString()}</div>
            <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 4 }}>Combined Corporate</div>
          </div>
          <div style={{ background: COLORS.bg, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 20px", flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.green, fontFamily: "'IBM Plex Mono',monospace" }}>{po.functions.length}</div>
            <div style={{ fontSize: 11, color: COLORS.textMuted, marginTop: 4 }}>Functions Analyzed</div>
          </div>
        </div>

        {/* Expanded function table */}
        {peopleExpanded && (
          <div style={{ borderTop: `1px solid ${COLORS.border}` }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
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
                          <span style={{ color: COLORS.accent, marginRight: 6, fontSize: 9 }}>{isFuncExp ? "\u25BE" : "\u25B8"}</span>
                          {fn.function}
                        </td>
                        <td style={{ textAlign: "right", padding: "6px 10px", color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{fn.meridian_headcount.toLocaleString()}</td>
                        <td style={{ textAlign: "right", padding: "6px 10px", color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{fn.cascadia_headcount.toLocaleString()}</td>
                        <td style={{ textAlign: "right", padding: "6px 10px", color: COLORS.text, fontWeight: 600, fontFamily: "'IBM Plex Mono',monospace" }}>{fn.combined_headcount.toLocaleString()}</td>
                        <td style={{ padding: "6px 10px", color: COLORS.textMuted, fontSize: 11 }}>{fn.role_overlap_examples.slice(0, 3).join(", ")}{fn.role_overlap_examples.length > 3 ? "..." : ""}</td>
                      </tr>
                      {isFuncExp && (
                        <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                          <td colSpan={5} style={{ padding: "10px 20px 14px 32px", background: COLORS.surface }}>
                            <div style={{ fontSize: 11, color: COLORS.textDim, fontStyle: "italic", marginBottom: 8 }}>{fn.definitional_note}</div>
                            {fn.role_detail && fn.role_detail.length > 0 && (
                              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
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
                                        <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 3, fontWeight: 600,
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
      <div style={{ fontSize: 14, color: COLORS.textMuted, fontFamily: "'IBM Plex Sans',sans-serif" }}>{message}</div>
      <div style={{ marginTop: 12, fontSize: 12, color: COLORS.textDim }}>Querying NLQ pipeline...</div>
    </div>
  );
}

function ErrorState({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <div style={{ margin: "20px 0", padding: "20px", background: COLORS.redBg, borderRadius: 8, border: `1px solid ${COLORS.red}33` }}>
      <p style={{ fontSize: 13, fontWeight: 600, color: COLORS.red, fontFamily: "'IBM Plex Sans',sans-serif", margin: 0 }}>Error loading report data</p>
      <p style={{ fontSize: 12, color: COLORS.red, fontFamily: "'IBM Plex Mono',monospace", margin: "8px 0 0", whiteSpace: "pre-wrap", opacity: 0.85 }}>{error}</p>
      <button onClick={onRetry} style={{ marginTop: 12, fontSize: 12, color: COLORS.red, background: "transparent", border: `1px solid ${COLORS.red}44`, padding: "4px 12px", borderRadius: 4, cursor: "pointer" }}>Retry</button>
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
  const thS: React.CSSProperties = { textAlign: "left", padding: "8px 12px", color: COLORS.textMuted, fontWeight: 500, fontSize: 10, letterSpacing: "0.06em", textTransform: "uppercase", fontFamily: "'JetBrains Mono',monospace" };
  const thR: React.CSSProperties = { ...thS, textAlign: "right" };

  return (
    <div>
      {/* Summary cards */}
      <div style={{ display: "flex", gap: 16, marginBottom: 24, flexWrap: "wrap" }}>
        {[
          { label: "Total Pipeline", value: fmtM(s.total_pipeline_acv), sub: `${s.total_candidates} candidates` },
          { label: "High Confidence", value: fmtM(s.total_high_conf_acv), sub: "Score > 80" },
          { label: "M \u2192 C Candidates", value: String(s.m_to_c_candidates), sub: fmtM(s.m_to_c_total_acv) },
          { label: "C \u2192 M Candidates", value: String(s.c_to_m_candidates), sub: fmtM(s.c_to_m_total_acv) },
        ].map((card) => (
          <div key={card.label} style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "16px 20px", flex: "1 1 180px", minWidth: 180 }}>
            <div style={{ fontSize: 11, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono',monospace" }}>{card.label}</div>
            <div style={{ fontSize: 24, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace", marginTop: 4 }}>{card.value}</div>
            <div style={{ fontSize: 12, color: COLORS.textDim, marginTop: 2 }}>{card.sub}</div>
          </div>
        ))}
      </div>

      {/* Direction toggle */}
      <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
        {(["m_to_c", "c_to_m"] as const).map((d) => (
          <button key={d} onClick={() => setDirection(d)} style={{
            padding: "6px 16px", fontSize: 12, fontWeight: direction === d ? 600 : 400,
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
        <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "'IBM Plex Mono','JetBrains Mono',monospace", fontSize: 12 }}>
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
                      <span style={{ color: COLORS.accent, marginRight: 6, fontSize: 10 }}>{isExp ? "\u25BE" : "\u25B8"}</span>
                      {c.customer_name}
                    </td>
                    <td style={{ padding: "8px 12px", color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>{c.recommended_service}</td>
                    <td style={{ textAlign: "right", padding: "8px 12px", fontWeight: 600, color: c.propensity_score >= 80 ? COLORS.green : c.propensity_score >= 60 ? COLORS.accent : COLORS.textMuted }}>
                      {c.propensity_score}
                    </td>
                    <td style={{ textAlign: "right", padding: "8px 12px", color: COLORS.text }}>{fmtM(c.estimated_acv)}</td>
                    <td style={{ padding: "8px 12px", color: COLORS.textMuted, fontFamily: "'IBM Plex Sans',sans-serif", fontSize: 11 }}>{c.industry}</td>
                    <td style={{ padding: "8px 12px" }}>
                      <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 3, fontWeight: 600,
                        background: c.propensity_score >= 80 ? COLORS.greenBg : c.propensity_score >= 60 ? "rgba(199,120,64,0.08)" : COLORS.redBg,
                        color: c.propensity_score >= 80 ? COLORS.green : c.propensity_score >= 60 ? COLORS.accent : COLORS.red,
                      }}>{fmtScore(c.propensity_score)}</span>
                    </td>
                  </tr>
                  {isExp && (
                    <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                      <td colSpan={6} style={{ padding: "12px 20px 16px", background: COLORS.surface }}>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, fontSize: 12, fontFamily: "'IBM Plex Sans',sans-serif" }}>
                          <div><span style={{ color: COLORS.textDim }}>Buyer Persona:</span> <span style={{ color: COLORS.text }}>{c.buyer_persona}</span></div>
                          <div><span style={{ color: COLORS.textDim }}>Years as Client:</span> <span style={{ color: COLORS.text }}>{c.years_as_client}</span></div>
                          <div><span style={{ color: COLORS.textDim }}>Industry Match:</span> <span style={{ color: COLORS.text }}>{c.industry_match}/25</span></div>
                          <div><span style={{ color: COLORS.textDim }}>Size Match:</span> <span style={{ color: COLORS.text }}>{c.size_match}/20</span></div>
                          <div><span style={{ color: COLORS.textDim }}>Behavioral:</span> <span style={{ color: COLORS.text }}>{c.behavioral_score}/30</span></div>
                          <div><span style={{ color: COLORS.textDim }}>Engagement Fit:</span> <span style={{ color: COLORS.text }}>{c.engagement_fit}/15</span></div>
                          <div><span style={{ color: COLORS.textDim }}>Relationship:</span> <span style={{ color: COLORS.text }}>{c.relationship_strength}/10</span></div>
                          <div><span style={{ color: COLORS.textDim }}>Current Engagement:</span> <span style={{ color: COLORS.text }}>{fmtM(c.customer_engagement_M * 1_000_000)}</span></div>
                        </div>
                        <div style={{ marginTop: 12, padding: "10px 14px", background: COLORS.bg, borderRadius: 6, fontSize: 12, color: COLORS.textMuted, lineHeight: 1.5 }}>
                          <span style={{ fontWeight: 600, color: COLORS.text }}>Rationale:</span> {c.rationale}
                        </div>
                        {c.comparable_customers.length > 0 && (
                          <div style={{ marginTop: 8, fontSize: 11, color: COLORS.textDim }}>
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
          <td style={{ padding: "8px 16px 8px 32px", color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif", fontSize: 13 }}>
            <span style={{ color: COLORS.accent, marginRight: 6, fontSize: 10 }}>{isExp ? "\u25BE" : "\u25B8"}</span>
            {isSubtract ? "\u2212 " : "+ "}{adj.name}
          </td>
          <td style={{ textAlign: "right", padding: "8px 16px", color: isSubtract ? COLORS.red : COLORS.green, fontSize: 13, fontFamily: "'IBM Plex Mono',monospace" }}>
            {isSubtract ? `(${fmtM(Math.abs(adj.amount))})` : fmtM(adj.amount)}
          </td>
          <td style={{ textAlign: "center", padding: "8px 12px" }}>
            <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 3, fontWeight: 600, color: confidenceColor(adj.confidence), background: adj.confidence === "high" ? COLORS.greenBg : adj.confidence === "medium" ? "rgba(199,120,64,0.08)" : COLORS.redBg }}>
              {adj.confidence.toUpperCase()}
            </span>
          </td>
        </tr>
        {isExp && (
          <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
            <td colSpan={3} style={{ padding: "8px 20px 12px 48px", background: COLORS.surface }}>
              <div style={{ fontSize: 12, color: COLORS.textMuted, lineHeight: 1.5, fontFamily: "'IBM Plex Sans',sans-serif" }}>
                <div><span style={{ color: COLORS.textDim }}>Range:</span> {fmtM(adj.amount_low)} — {fmtM(adj.amount_high)}</div>
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

  const bridgeThS: React.CSSProperties = { textAlign: "left", padding: "8px 16px", color: COLORS.textMuted, fontWeight: 500, fontSize: 10, letterSpacing: "0.06em", textTransform: "uppercase", fontFamily: "'JetBrains Mono',monospace" };

  return (
    <div>
      {/* Summary KPIs — drillable */}
      <div style={{ display: "flex", flexDirection: "column", gap: 0, marginBottom: 24 }}>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
          {([
            { id: "reported", label: "Reported EBITDA", value: fmtM(rep.combined_reported) },
            { id: "adjusted", label: "Entity Adjusted", value: fmtM(ea.combined) },
            { id: "pf_yr1", label: "Pro Forma Yr 1", value: fmtM(pf.year_1.current) },
            { id: "pf_ss", label: "Pro Forma Steady State", value: fmtM(pf.steady_state.current) },
            { id: "ev", label: `EV @ ${ev.multiple}x`, value: fmtM(ev.steady_state_ev.current) },
          ] as const).map((kpi) => {
            const isExp = expandedKpi === kpi.id;
            return (
              <div key={kpi.id} onClick={() => setExpandedKpi(isExp ? null : kpi.id)} style={{ background: isExp ? COLORS.surfaceHover : COLORS.surface, border: `1px solid ${isExp ? COLORS.accent : COLORS.border}`, borderRadius: 8, padding: "14px 18px", flex: "1 1 160px", cursor: "pointer", transition: "border-color 0.15s" }}>
                <div style={{ fontSize: 10, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono',monospace" }}>
                  <span style={{ color: COLORS.accent, marginRight: 4, fontSize: 8 }}>{isExp ? "\u25BE" : "\u25B8"}</span>
                  {kpi.label}
                </div>
                <div style={{ fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace", marginTop: 4 }}>{kpi.value}</div>
              </div>
            );
          })}
        </div>

        {/* KPI drill-through panel */}
        {expandedKpi && (
          <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.accent}`, borderTop: "none", borderRadius: "0 0 8px 8px", padding: "16px 20px", marginTop: -1 }}>
            {expandedKpi === "reported" && (
              <div>
                <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.accent, marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Reported EBITDA by Entity</div>
                <table style={{ width: "100%", maxWidth: 400, borderCollapse: "collapse", fontSize: 12 }}>
                  <tbody>
                    <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                      <td style={{ padding: "6px 0", color: COLORS.textMuted }}>Meridian</td>
                      <td style={{ textAlign: "right", padding: "6px 0", color: COLORS.text, fontWeight: 600, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(rep.meridian)}</td>
                    </tr>
                    <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                      <td style={{ padding: "6px 0", color: COLORS.textMuted }}>Cascadia</td>
                      <td style={{ textAlign: "right", padding: "6px 0", color: COLORS.text, fontWeight: 600, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(rep.cascadia)}</td>
                    </tr>
                    <tr style={{ borderTop: `1px solid ${COLORS.borderLight}` }}>
                      <td style={{ padding: "6px 0", color: COLORS.text, fontWeight: 700 }}>Combined</td>
                      <td style={{ textAlign: "right", padding: "6px 0", color: COLORS.text, fontWeight: 700, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(rep.combined_reported)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
            {expandedKpi === "adjusted" && (
              <div>
                <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.accent, marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Entity-Adjusted EBITDA</div>
                <table style={{ width: "100%", maxWidth: 500, borderCollapse: "collapse", fontSize: 12 }}>
                  <thead>
                    <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                      <th style={{ textAlign: "left", padding: "4px 0", color: COLORS.textDim, fontSize: 10 }}></th>
                      <th style={{ textAlign: "right", padding: "4px 8px", color: COLORS.textDim, fontSize: 10 }}>MERIDIAN</th>
                      <th style={{ textAlign: "right", padding: "4px 8px", color: COLORS.textDim, fontSize: 10 }}>CASCADIA</th>
                      <th style={{ textAlign: "right", padding: "4px 0", color: COLORS.textDim, fontSize: 10 }}>COMBINED</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                      <td style={{ padding: "6px 0", color: COLORS.textMuted }}>Reported</td>
                      <td style={{ textAlign: "right", padding: "6px 8px", color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(rep.meridian)}</td>
                      <td style={{ textAlign: "right", padding: "6px 8px", color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(rep.cascadia)}</td>
                      <td style={{ textAlign: "right", padding: "6px 0", color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(rep.combined_reported)}</td>
                    </tr>
                    {data.entity_adjustments.map((adj) => (
                      <tr key={adj.name} style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                        <td style={{ padding: "6px 0", color: COLORS.textMuted, fontSize: 11 }}>{adj.name}</td>
                        <td colSpan={2} style={{ textAlign: "center", padding: "6px 8px", color: COLORS.textDim, fontSize: 10 }}>{adj.entity}</td>
                        <td style={{ textAlign: "right", padding: "6px 0", color: adj.amount >= 0 ? COLORS.green : COLORS.red, fontFamily: "'IBM Plex Mono',monospace" }}>{adj.amount >= 0 ? "+" : ""}{fmtM(adj.amount)}</td>
                      </tr>
                    ))}
                    <tr style={{ borderTop: `1px solid ${COLORS.borderLight}` }}>
                      <td style={{ padding: "6px 0", color: COLORS.text, fontWeight: 700 }}>Adjusted</td>
                      <td style={{ textAlign: "right", padding: "6px 8px", color: COLORS.text, fontWeight: 700, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(ea.meridian)}</td>
                      <td style={{ textAlign: "right", padding: "6px 8px", color: COLORS.text, fontWeight: 700, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(ea.cascadia)}</td>
                      <td style={{ textAlign: "right", padding: "6px 0", color: COLORS.text, fontWeight: 700, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(ea.combined)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
            {expandedKpi === "pf_yr1" && (
              <div>
                <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.accent, marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Pro Forma Year 1 — Range</div>
                <div style={{ display: "flex", gap: 32, alignItems: "center" }}>
                  <div>
                    <div style={{ fontSize: 10, color: COLORS.textDim }}>LOW</div>
                    <div style={{ fontSize: 16, fontWeight: 600, color: COLORS.red, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(pf.year_1.low)}</div>
                  </div>
                  <div style={{ flex: 1, height: 6, background: COLORS.bg, borderRadius: 3, position: "relative", maxWidth: 200 }}>
                    <div style={{ position: "absolute", left: 0, top: 0, height: 6, borderRadius: 3, background: `linear-gradient(90deg, ${COLORS.red}, ${COLORS.green})`, width: "100%" }} />
                    <div style={{ position: "absolute", top: -4, height: 14, width: 3, background: COLORS.accent, borderRadius: 1, left: `${pf.year_1.high === pf.year_1.low ? 50 : ((pf.year_1.current - pf.year_1.low) / (pf.year_1.high - pf.year_1.low)) * 100}%` }} />
                  </div>
                  <div>
                    <div style={{ fontSize: 10, color: COLORS.textDim }}>HIGH</div>
                    <div style={{ fontSize: 16, fontWeight: 600, color: COLORS.green, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(pf.year_1.high)}</div>
                  </div>
                  <div style={{ borderLeft: `1px solid ${COLORS.border}`, paddingLeft: 24 }}>
                    <div style={{ fontSize: 10, color: COLORS.textDim }}>CURRENT</div>
                    <div style={{ fontSize: 18, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(pf.year_1.current)}</div>
                  </div>
                </div>
                <div style={{ marginTop: 12, fontSize: 11, color: COLORS.textMuted }}>
                  Synergies applied: {data.combination_synergies.length} items totaling {fmtM(data.combination_synergies.reduce((s, a) => s + a.amount, 0))}
                </div>
              </div>
            )}
            {expandedKpi === "pf_ss" && (
              <div>
                <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.accent, marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Pro Forma Steady State — Range</div>
                <div style={{ display: "flex", gap: 32, alignItems: "center" }}>
                  <div>
                    <div style={{ fontSize: 10, color: COLORS.textDim }}>LOW</div>
                    <div style={{ fontSize: 16, fontWeight: 600, color: COLORS.red, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(pf.steady_state.low)}</div>
                  </div>
                  <div style={{ flex: 1, height: 6, background: COLORS.bg, borderRadius: 3, position: "relative", maxWidth: 200 }}>
                    <div style={{ position: "absolute", left: 0, top: 0, height: 6, borderRadius: 3, background: `linear-gradient(90deg, ${COLORS.red}, ${COLORS.green})`, width: "100%" }} />
                    <div style={{ position: "absolute", top: -4, height: 14, width: 3, background: COLORS.accent, borderRadius: 1, left: `${pf.steady_state.high === pf.steady_state.low ? 50 : ((pf.steady_state.current - pf.steady_state.low) / (pf.steady_state.high - pf.steady_state.low)) * 100}%` }} />
                  </div>
                  <div>
                    <div style={{ fontSize: 10, color: COLORS.textDim }}>HIGH</div>
                    <div style={{ fontSize: 16, fontWeight: 600, color: COLORS.green, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(pf.steady_state.high)}</div>
                  </div>
                  <div style={{ borderLeft: `1px solid ${COLORS.border}`, paddingLeft: 24 }}>
                    <div style={{ fontSize: 10, color: COLORS.textDim }}>CURRENT</div>
                    <div style={{ fontSize: 18, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(pf.steady_state.current)}</div>
                  </div>
                </div>
                <div style={{ marginTop: 12, fontSize: 11, color: COLORS.textMuted }}>
                  Full synergy realization assumed at steady state
                </div>
              </div>
            )}
            {expandedKpi === "ev" && (
              <div>
                <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.accent, marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Enterprise Value Impact @ {ev.multiple}x Multiple</div>
                <table style={{ width: "100%", maxWidth: 500, borderCollapse: "collapse", fontSize: 12 }}>
                  <thead>
                    <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                      <th style={{ textAlign: "left", padding: "4px 0", color: COLORS.textDim, fontSize: 10 }}></th>
                      <th style={{ textAlign: "right", padding: "4px 8px", color: COLORS.textDim, fontSize: 10 }}>LOW</th>
                      <th style={{ textAlign: "right", padding: "4px 8px", color: COLORS.textDim, fontSize: 10 }}>CURRENT</th>
                      <th style={{ textAlign: "right", padding: "4px 0", color: COLORS.textDim, fontSize: 10 }}>HIGH</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                      <td style={{ padding: "6px 0", color: COLORS.textMuted }}>Year 1 EV</td>
                      <td style={{ textAlign: "right", padding: "6px 8px", color: COLORS.red, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(ev.year_1_ev.low)}</td>
                      <td style={{ textAlign: "right", padding: "6px 8px", color: COLORS.text, fontWeight: 600, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(ev.year_1_ev.current)}</td>
                      <td style={{ textAlign: "right", padding: "6px 0", color: COLORS.green, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(ev.year_1_ev.high)}</td>
                    </tr>
                    <tr>
                      <td style={{ padding: "6px 0", color: COLORS.text, fontWeight: 600 }}>Steady State EV</td>
                      <td style={{ textAlign: "right", padding: "6px 8px", color: COLORS.red, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(ev.steady_state_ev.low)}</td>
                      <td style={{ textAlign: "right", padding: "6px 8px", color: COLORS.text, fontWeight: 700, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(ev.steady_state_ev.current)}</td>
                      <td style={{ textAlign: "right", padding: "6px 0", color: COLORS.green, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(ev.steady_state_ev.high)}</td>
                    </tr>
                  </tbody>
                </table>
                <div style={{ marginTop: 10, fontSize: 11, color: COLORS.textMuted }}>
                  EV delta from reported: {fmtM(ev.steady_state_ev.current - rep.combined_reported * ev.multiple)} incremental value created
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Bridge waterfall table */}
      <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
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
              <td style={{ textAlign: "right", padding: "10px 16px", fontWeight: 600, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(rep.combined_reported)}</td>
              <td></td>
            </tr>

            {/* Entity adjustments header */}
            <tr><td colSpan={3} style={{ padding: "12px 16px 4px", fontSize: 11, fontWeight: 600, color: COLORS.accent, letterSpacing: "0.06em", textTransform: "uppercase", fontFamily: "'JetBrains Mono',monospace" }}>Entity-Level Adjustments</td></tr>
            {data.entity_adjustments.map((adj) => <BridgeLine key={adj.name} adj={adj} />)}

            {/* Entity adjusted subtotal */}
            <tr style={{ background: COLORS.totalBg, borderTop: `1px solid ${COLORS.borderLight}`, borderBottom: `1px solid ${COLORS.borderLight}` }}>
              <td style={{ padding: "10px 16px", fontWeight: 600, color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>Entity-Level Adjusted EBITDA</td>
              <td style={{ textAlign: "right", padding: "10px 16px", fontWeight: 600, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(ea.combined)}</td>
              <td></td>
            </tr>

            {/* Combination synergies header */}
            <tr><td colSpan={3} style={{ padding: "12px 16px 4px", fontSize: 11, fontWeight: 600, color: COLORS.accent, letterSpacing: "0.06em", textTransform: "uppercase", fontFamily: "'JetBrains Mono',monospace" }}>Combination Synergies</td></tr>
            {data.combination_synergies.map((syn) => (
              <BridgeLine key={syn.name} adj={syn} isSubtract={syn.category === "dis_synergy"} />
            ))}

            {/* Pro forma */}
            <tr style={{ background: COLORS.totalBg, borderTop: `2px solid ${COLORS.accent}` }}>
              <td style={{ padding: "10px 16px", fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>Pro Forma Adjusted EBITDA (Yr 1)</td>
              <td style={{ textAlign: "right", padding: "10px 16px", fontWeight: 700, color: COLORS.green, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(pf.year_1.current)}</td>
              <td></td>
            </tr>
            <tr style={{ background: COLORS.totalBg }}>
              <td style={{ padding: "10px 16px", fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>Pro Forma Adjusted EBITDA (Steady State)</td>
              <td style={{ textAlign: "right", padding: "10px 16px", fontWeight: 700, color: COLORS.green, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(pf.steady_state.current)}</td>
              <td></td>
            </tr>
          </tbody>
        </table>
      </div>
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
        <div style={{ fontSize: 12, fontWeight: 600, color: COLORS.accent, marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono',monospace" }}>Sensitivity Levers</div>

        {/* Presets */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 16 }}>
          {presetNames.map((p) => (
            <button key={p} onClick={() => applyPreset(p)} style={{
              padding: "4px 10px", fontSize: 10, fontWeight: 600, cursor: "pointer",
              background: "rgba(199,120,64,0.08)", color: COLORS.accent,
              border: `1px solid ${COLORS.accent}33`, borderRadius: 3,
              fontFamily: "'JetBrains Mono',monospace", textTransform: "uppercase",
            }}>{p.replace(/_/g, " ")}</button>
          ))}
        </div>

        {defs.map((d) => (
          <div key={d.name} style={{ marginBottom: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
              <span style={{ fontSize: 11, color: COLORS.textMuted, fontFamily: "'IBM Plex Sans',sans-serif" }}>{d.label}</span>
              <span style={{ fontSize: 12, fontWeight: 600, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>
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
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: COLORS.textDim }}>
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
              { id: "wi_reported", label: "Reported EBITDA", value: fmtM(result.reported_ebitda) },
              { id: "wi_adjusted", label: "Entity Adjusted", value: fmtM(result.entity_adjusted_ebitda) },
              { id: "wi_pf1", label: "Pro Forma Yr 1", value: fmtM(result.pro_forma_ebitda.year_1) },
              { id: "wi_pfss", label: "Pro Forma SS", value: fmtM(result.pro_forma_ebitda.steady_state) },
              { id: "wi_ev1", label: "EV (Yr 1)", value: fmtM(result.ev_impact.year_1) },
              { id: "wi_evss", label: "EV (SS)", value: fmtM(result.ev_impact.steady_state) },
            ] as const).map((kpi) => {
              const isExp = wiKpi === kpi.id;
              return (
                <div key={kpi.id} onClick={() => setWiKpi(isExp ? null : kpi.id)} style={{ background: isExp ? COLORS.surfaceHover : COLORS.surface, border: `1px solid ${isExp ? COLORS.accent : COLORS.border}`, borderRadius: 8, padding: "12px 16px", flex: "1 1 140px", cursor: "pointer", transition: "border-color 0.15s" }}>
                  <div style={{ fontSize: 10, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono',monospace" }}>
                    <span style={{ color: COLORS.accent, marginRight: 4, fontSize: 8 }}>{isExp ? "\u25BE" : "\u25B8"}</span>
                    {kpi.label}
                  </div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace", marginTop: 2 }}>{kpi.value}</div>
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
            const thD: React.CSSProperties = { textAlign: "left", padding: "4px 12px", color: COLORS.textDim, fontSize: 10, fontWeight: 500 };
            const thDR: React.CSSProperties = { ...thD, textAlign: "right" };

            const adjTable = (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
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
                      <td style={{ textAlign: "right", padding: "5px 12px", color: a.amount >= 0 ? COLORS.green : COLORS.red, fontFamily: "'IBM Plex Mono',monospace" }}>{a.amount >= 0 ? "+" : ""}{fmtM(a.amount)}</td>
                      <td style={{ textAlign: "center", padding: "5px 8px" }}>
                        <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 3, fontWeight: 600, color: confidenceColor(a.confidence), background: a.confidence === "high" ? COLORS.greenBg : a.confidence === "medium" ? "rgba(199,120,64,0.08)" : COLORS.redBg }}>{a.confidence.toUpperCase()}</span>
                      </td>
                      <td style={{ padding: "5px 12px", color: COLORS.textMuted, fontSize: 11 }}>{a.lever || "—"}</td>
                    </tr>
                  ))}
                  <tr style={{ borderTop: `1px solid ${COLORS.borderLight}` }}>
                    <td style={{ padding: "5px 12px", color: COLORS.text, fontWeight: 700 }}>Total Adjustments</td>
                    <td style={{ textAlign: "right", padding: "5px 12px", color: COLORS.text, fontWeight: 700, fontFamily: "'IBM Plex Mono',monospace" }}>{adjTotal >= 0 ? "+" : ""}{fmtM(adjTotal)}</td>
                    <td colSpan={2}></td>
                  </tr>
                </tbody>
              </table>
            );

            const synTable = (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
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
                        {s.category === "dis_synergy" ? `(${fmtM(Math.abs(s.amount))})` : `+${fmtM(s.amount)}`}
                      </td>
                      <td style={{ textAlign: "center", padding: "5px 8px" }}>
                        <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 3, fontWeight: 600, color: confidenceColor(s.confidence), background: s.confidence === "high" ? COLORS.greenBg : s.confidence === "medium" ? "rgba(199,120,64,0.08)" : COLORS.redBg }}>{s.confidence.toUpperCase()}</span>
                      </td>
                      <td style={{ padding: "5px 12px", color: COLORS.textMuted, fontSize: 11 }}>{s.category.replace(/_/g, " ")}</td>
                    </tr>
                  ))}
                  <tr style={{ borderTop: `1px solid ${COLORS.borderLight}` }}>
                    <td style={{ padding: "5px 12px", color: COLORS.text, fontWeight: 700 }}>Net Synergies</td>
                    <td style={{ textAlign: "right", padding: "5px 12px", color: COLORS.text, fontWeight: 700, fontFamily: "'IBM Plex Mono',monospace" }}>{synTotal >= 0 ? "+" : ""}{fmtM(synTotal)}</td>
                    <td colSpan={2}></td>
                  </tr>
                </tbody>
              </table>
            );

            return (
              <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.accent}`, borderTop: "none", borderRadius: "0 0 8px 8px", padding: "16px 20px", marginTop: -1 }}>
                {wiKpi === "wi_reported" && (
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.accent, marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.06em" }}>Reported EBITDA — Baseline</div>
                    <div style={{ fontSize: 12, color: COLORS.textMuted, lineHeight: 1.6 }}>
                      <div>This is the unadjusted, as-reported combined EBITDA before any normalization adjustments or synergy assumptions.</div>
                      <div style={{ marginTop: 8, display: "flex", gap: 24 }}>
                        <div><span style={{ color: COLORS.textDim }}>Value:</span> <span style={{ fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(result.reported_ebitda)}</span></div>
                        <div><span style={{ color: COLORS.textDim }}>Adjustments pending:</span> <span style={{ fontWeight: 600, color: COLORS.accent }}>{adjRows.length} items ({adjTotal >= 0 ? "+" : ""}{fmtM(adjTotal)})</span></div>
                      </div>
                    </div>
                  </div>
                )}
                {wiKpi === "wi_adjusted" && (
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.accent, marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Entity-Adjusted EBITDA Build-Up</div>
                    <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 10 }}>
                      Reported {fmtM(result.reported_ebitda)} + adjustments {adjTotal >= 0 ? "+" : ""}{fmtM(adjTotal)} = <span style={{ fontWeight: 700, color: COLORS.text }}>{fmtM(result.entity_adjusted_ebitda)}</span>
                    </div>
                    {adjTable}
                  </div>
                )}
                {wiKpi === "wi_pf1" && (
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.accent, marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Pro Forma Year 1 Build-Up</div>
                    <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 10 }}>
                      Adjusted {fmtM(result.entity_adjusted_ebitda)} + net synergies {synTotal >= 0 ? "+" : ""}{fmtM(synTotal)} = <span style={{ fontWeight: 700, color: COLORS.green }}>{fmtM(result.pro_forma_ebitda.year_1)}</span>
                    </div>
                    {synTable}
                  </div>
                )}
                {wiKpi === "wi_pfss" && (
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.accent, marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Pro Forma Steady State Build-Up</div>
                    <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 10 }}>
                      Adjusted {fmtM(result.entity_adjusted_ebitda)} + full synergy realization {synTotal >= 0 ? "+" : ""}{fmtM(synTotal)} = <span style={{ fontWeight: 700, color: COLORS.green }}>{fmtM(result.pro_forma_ebitda.steady_state)}</span>
                    </div>
                    <div style={{ marginBottom: 12 }}>{synTable}</div>
                    <div style={{ fontSize: 11, color: COLORS.textMuted, fontStyle: "italic" }}>Steady state assumes 100% synergy realization (typically 24–36 months post-close)</div>
                  </div>
                )}
                {wiKpi === "wi_ev1" && (
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.accent, marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Enterprise Value — Year 1</div>
                    <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 12 }}>
                      Pro Forma Yr 1 EBITDA {fmtM(result.pro_forma_ebitda.year_1)} applied at current lever multiple
                    </div>
                    <table style={{ borderCollapse: "collapse", fontSize: 12 }}>
                      <tbody>
                        <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                          <td style={{ padding: "5px 16px 5px 0", color: COLORS.textMuted }}>Pro Forma EBITDA (Yr 1)</td>
                          <td style={{ textAlign: "right", padding: "5px 0", color: COLORS.text, fontWeight: 600, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(result.pro_forma_ebitda.year_1)}</td>
                        </tr>
                        <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                          <td style={{ padding: "5px 16px 5px 0", color: COLORS.textMuted }}>Multiple (from lever)</td>
                          <td style={{ textAlign: "right", padding: "5px 0", color: COLORS.accent, fontWeight: 600, fontFamily: "'IBM Plex Mono',monospace" }}>{levers["ev_multiple"] ?? "—"}x</td>
                        </tr>
                        <tr style={{ borderTop: `1px solid ${COLORS.borderLight}` }}>
                          <td style={{ padding: "5px 16px 5px 0", color: COLORS.text, fontWeight: 700 }}>EV (Year 1)</td>
                          <td style={{ textAlign: "right", padding: "5px 0", color: COLORS.green, fontWeight: 700, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(result.ev_impact.year_1)}</td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                )}
                {wiKpi === "wi_evss" && (
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.accent, marginBottom: 10, textTransform: "uppercase", letterSpacing: "0.06em" }}>Enterprise Value — Steady State</div>
                    <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 12 }}>
                      Pro Forma SS EBITDA {fmtM(result.pro_forma_ebitda.steady_state)} applied at current lever multiple
                    </div>
                    <table style={{ borderCollapse: "collapse", fontSize: 12 }}>
                      <tbody>
                        <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                          <td style={{ padding: "5px 16px 5px 0", color: COLORS.textMuted }}>Pro Forma EBITDA (SS)</td>
                          <td style={{ textAlign: "right", padding: "5px 0", color: COLORS.text, fontWeight: 600, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(result.pro_forma_ebitda.steady_state)}</td>
                        </tr>
                        <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                          <td style={{ padding: "5px 16px 5px 0", color: COLORS.textMuted }}>Multiple (from lever)</td>
                          <td style={{ textAlign: "right", padding: "5px 0", color: COLORS.accent, fontWeight: 600, fontFamily: "'IBM Plex Mono',monospace" }}>{levers["ev_multiple"] ?? "—"}x</td>
                        </tr>
                        <tr style={{ borderTop: `1px solid ${COLORS.borderLight}` }}>
                          <td style={{ padding: "5px 16px 5px 0", color: COLORS.text, fontWeight: 700 }}>EV (Steady State)</td>
                          <td style={{ textAlign: "right", padding: "5px 0", color: COLORS.green, fontWeight: 700, fontFamily: "'IBM Plex Mono',monospace" }}>{fmtM(result.ev_impact.steady_state)}</td>
                        </tr>
                        <tr style={{ borderTop: `1px solid ${COLORS.border}22` }}>
                          <td style={{ padding: "5px 16px 5px 0", color: COLORS.textMuted, fontSize: 11 }}>Incremental vs Reported</td>
                          <td style={{ textAlign: "right", padding: "5px 0", color: COLORS.accent, fontWeight: 600, fontFamily: "'IBM Plex Mono',monospace", fontSize: 11 }}>+{fmtM(result.ev_impact.steady_state - result.ev_impact.year_1)}</td>
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
          <div style={{ fontSize: 10, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono',monospace" }}>Sustainability Score</div>
          <div style={{ fontSize: 28, fontWeight: 700, color: sus.overall >= 65 ? COLORS.green : sus.overall >= 50 ? COLORS.accent : COLORS.red, fontFamily: "'IBM Plex Mono',monospace", marginTop: 4 }}>{sus.overall.toFixed(0)}<span style={{ fontSize: 14, fontWeight: 400, color: COLORS.textMuted }}>/100</span></div>
          <div style={{ fontSize: 12, fontWeight: 600, color: COLORS.textDim, marginTop: 2 }}>Grade: {sus.grade}</div>
        </div>
        <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 18px", flex: "1 1 160px" }}>
          <div style={{ fontSize: 10, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono',monospace" }}>Adjusted EBITDA</div>
          <div style={{ fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace", marginTop: 4 }}>{fmtM(summary.entity_adjusted_ebitda)}</div>
        </div>
        <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 18px", flex: "1 1 160px" }}>
          <div style={{ fontSize: 10, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono',monospace" }}>Adjustments</div>
          <div style={{ display: "flex", gap: 8, marginTop: 4, fontSize: 12, fontFamily: "'IBM Plex Mono',monospace" }}>
            <span style={{ color: COLORS.green }}>{summary.active_adjustments} active</span>
            <span style={{ color: COLORS.textDim }}>{summary.resolved_adjustments} resolved</span>
            <span style={{ color: COLORS.accent }}>{summary.new_adjustments} new</span>
            <span style={{ color: COLORS.red }}>{summary.changed_adjustments} changed</span>
          </div>
        </div>
        <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 18px", flex: "1 1 160px" }}>
          <div style={{ fontSize: 10, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono',monospace" }}>Period</div>
          <div style={{ fontSize: 16, fontWeight: 600, color: COLORS.text, marginTop: 4 }}>{data.period}</div>
          <div style={{ fontSize: 10, color: COLORS.textDim, marginTop: 2 }}>{data.is_initial_diligence ? "Initial Diligence" : "Ongoing QofE"}</div>
        </div>
      </div>

      {/* Sub-view tabs */}
      <div style={{ display: "flex", gap: 4, marginBottom: 20 }}>
        {subTabs.map((st) => (
          <button key={st.id} onClick={() => setSubView(st.id)} style={{
            padding: "6px 16px", fontSize: 11, fontWeight: subView === st.id ? 700 : 400,
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
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                <th style={{ textAlign: "left", padding: "6px 12px", color: COLORS.textDim, fontSize: 10, textTransform: "uppercase" }}>Adjustment</th>
                <th style={{ textAlign: "right", padding: "6px 12px", color: COLORS.textDim, fontSize: 10 }}>Current</th>
                <th style={{ textAlign: "right", padding: "6px 12px", color: COLORS.textDim, fontSize: 10 }}>Diligence</th>
                <th style={{ textAlign: "right", padding: "6px 12px", color: COLORS.textDim, fontSize: 10 }}>Prior</th>
                <th style={{ textAlign: "center", padding: "6px 8px", color: COLORS.textDim, fontSize: 10 }}>Status</th>
                <th style={{ textAlign: "center", padding: "6px 8px", color: COLORS.textDim, fontSize: 10 }}>Trend</th>
                <th style={{ textAlign: "center", padding: "6px 8px", color: COLORS.textDim, fontSize: 10 }}>Conf.</th>
              </tr>
            </thead>
            <tbody>
              {data.ebitda_bridge.map((row) => {
                const isExp = expandedAdj === row.name;
                return (
                  <React.Fragment key={row.name}>
                    <tr onClick={() => setExpandedAdj(isExp ? null : row.name)} style={{ cursor: "pointer", borderBottom: `1px solid ${COLORS.border}15`, background: isExp ? COLORS.surfaceHover : "transparent" }}>
                      <td style={{ padding: "6px 12px", color: COLORS.text }}>
                        <span style={{ color: COLORS.accent, marginRight: 6, fontSize: 9 }}>{isExp ? "\u25BE" : "\u25B8"}</span>
                        {row.name}
                      </td>
                      <td style={{ textAlign: "right", padding: "6px 12px", fontFamily: "'IBM Plex Mono',monospace", color: COLORS.text }}>{fmtM(row.current_amount)}</td>
                      <td style={{ textAlign: "right", padding: "6px 12px", fontFamily: "'IBM Plex Mono',monospace", color: COLORS.textMuted }}>{row.diligence_amount !== null ? fmtM(row.diligence_amount) : "—"}</td>
                      <td style={{ textAlign: "right", padding: "6px 12px", fontFamily: "'IBM Plex Mono',monospace", color: COLORS.textMuted }}>{row.prior_amount !== null ? fmtM(row.prior_amount) : "—"}</td>
                      <td style={{ textAlign: "center", padding: "6px 8px" }}>
                        <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 3, fontWeight: 600, color: statusColor(row.status), background: statusBg(row.status) }}>{row.status.toUpperCase()}</span>
                      </td>
                      <td style={{ textAlign: "center", padding: "6px 8px", color: trendColor(row.trend), fontWeight: 600, fontSize: 14 }}>{trendIcon(row.trend)}</td>
                      <td style={{ textAlign: "center", padding: "6px 8px" }}>
                        <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 3, fontWeight: 600, color: confidenceColor(row.confidence), background: row.confidence === "high" ? COLORS.greenBg : row.confidence === "medium" ? "rgba(199,120,64,0.08)" : COLORS.redBg }}>{row.confidence.toUpperCase()}</span>
                      </td>
                    </tr>
                    {isExp && (
                      <tr style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                        <td colSpan={7} style={{ padding: "8px 20px 12px 36px", background: COLORS.surface }}>
                          <div style={{ fontSize: 11, color: COLORS.textMuted, lineHeight: 1.6 }}>
                            <div><span style={{ color: COLORS.textDim }}>Range:</span> {fmtM(row.amount_low)} — {fmtM(row.amount_high)}</div>
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
              <div style={{ fontSize: 48, fontWeight: 700, color: sus.overall >= 65 ? COLORS.green : sus.overall >= 50 ? COLORS.accent : COLORS.red, fontFamily: "'IBM Plex Mono',monospace" }}>{sus.overall.toFixed(0)}</div>
              <div style={{ fontSize: 13, color: COLORS.textMuted }}>Earnings Sustainability Score</div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {sus.components.map((c) => (
                <div key={c.name} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={{ width: 160, fontSize: 11, color: COLORS.textMuted }}>{c.name}</div>
                  <div style={{ flex: 1, height: 8, background: COLORS.bg, borderRadius: 4, overflow: "hidden" }}>
                    <div style={{ width: `${c.score}%`, height: "100%", borderRadius: 4, background: c.score >= 70 ? COLORS.green : c.score >= 50 ? COLORS.accent : COLORS.red, transition: "width 0.3s" }} />
                  </div>
                  <div style={{ width: 50, textAlign: "right", fontSize: 12, fontWeight: 600, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{c.score.toFixed(0)}</div>
                  <div style={{ width: 30, textAlign: "right", fontSize: 10, color: COLORS.textDim }}>/{c.max_points}</div>
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
            <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.accent, marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.06em" }}>Customer Concentration</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 12 }}>
              <div><div style={{ fontSize: 10, color: COLORS.textDim }}>HHI Index</div><div style={{ fontSize: 18, fontWeight: 700, color: rq.customer_concentration.hhi < 1500 ? COLORS.green : COLORS.red, fontFamily: "'IBM Plex Mono',monospace" }}>{rq.customer_concentration.hhi.toFixed(0)}</div></div>
              <div><div style={{ fontSize: 10, color: COLORS.textDim }}>Top 10 %</div><div style={{ fontSize: 18, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{rq.customer_concentration.top_10_pct.toFixed(1)}%</div></div>
              <div><div style={{ fontSize: 10, color: COLORS.textDim }}>Top 20 %</div><div style={{ fontSize: 18, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{rq.customer_concentration.top_20_pct.toFixed(1)}%</div></div>
              <div><div style={{ fontSize: 10, color: COLORS.textDim }}>Customers</div><div style={{ fontSize: 18, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{rq.customer_concentration.total_customers.toLocaleString()}</div></div>
            </div>
            {rq.customer_concentration.threshold_alerts.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <div style={{ fontSize: 10, fontWeight: 600, color: COLORS.red, marginBottom: 4 }}>THRESHOLD ALERTS</div>
                {rq.customer_concentration.threshold_alerts.map((a) => (
                  <div key={a.customer} style={{ fontSize: 11, color: COLORS.textMuted }}>{a.customer}: {a.pct}% (crossed {a.threshold})</div>
                ))}
              </div>
            )}
          </div>

          {/* Contract quality */}
          <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, padding: "16px 20px" }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.accent, marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.06em" }}>Contract Quality</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
              <div><div style={{ fontSize: 10, color: COLORS.textDim }}>MSA %</div><div style={{ fontSize: 18, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{rq.contract_quality.msa_pct}%</div></div>
              <div><div style={{ fontSize: 10, color: COLORS.textDim }}>SOW %</div><div style={{ fontSize: 18, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{rq.contract_quality.sow_pct}%</div></div>
              <div><div style={{ fontSize: 10, color: COLORS.textDim }}>T&M %</div><div style={{ fontSize: 18, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{rq.contract_quality.t_and_m_pct}%</div></div>
              <div><div style={{ fontSize: 10, color: COLORS.textDim }}>Avg Tenure</div><div style={{ fontSize: 18, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{rq.contract_quality.avg_tenure_years} yrs</div></div>
            </div>
          </div>

          {/* Revenue mix */}
          <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, padding: "16px 20px" }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.accent, marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.06em" }}>Revenue Mix (Quarterly)</div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <div>
                <div style={{ fontSize: 10, color: COLORS.textDim }}>Recurring</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: COLORS.green, fontFamily: "'IBM Plex Mono',monospace" }}>{rq.revenue_mix.recurring_pct}%</div>
                <div style={{ fontSize: 10, color: COLORS.textMuted }}>Managed ${rq.revenue_mix.managed_services_M}M · Per-FTE ${rq.revenue_mix.per_fte_M}M · Per-Txn ${rq.revenue_mix.per_transaction_M}M</div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: COLORS.textDim }}>Non-Recurring</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: COLORS.accent, fontFamily: "'IBM Plex Mono',monospace" }}>{rq.revenue_mix.non_recurring_pct}%</div>
                <div style={{ fontSize: 10, color: COLORS.textMuted }}>Advisory & Consulting ${rq.revenue_mix.advisory_consulting_M}M</div>
              </div>
            </div>
          </div>

          {/* Cross-sell penetration */}
          <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, padding: "16px 20px" }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.accent, marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.06em" }}>Cross-Sell Penetration</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
              <div><div style={{ fontSize: 10, color: COLORS.textDim }}>Candidates</div><div style={{ fontSize: 18, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{rq.cross_sell_penetration.total_candidates}</div></div>
              <div><div style={{ fontSize: 10, color: COLORS.textDim }}>Pipeline ACV</div><div style={{ fontSize: 18, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>${rq.cross_sell_penetration.total_pipeline_acv_M}M</div></div>
              <div><div style={{ fontSize: 10, color: COLORS.textDim }}>Converted</div><div style={{ fontSize: 18, fontWeight: 700, color: rq.cross_sell_penetration.converted_count > 0 ? COLORS.green : COLORS.textDim, fontFamily: "'IBM Plex Mono',monospace" }}>{rq.cross_sell_penetration.converted_count}</div></div>
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
              <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.accent, marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.06em" }}>{metric.label}</div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                {metric.data.map((d, i) => (
                  <div key={d.period} style={{ textAlign: "center", minWidth: 60 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: i === metric.data.length - 1 ? COLORS.accent : COLORS.text, fontFamily: "'IBM Plex Mono',monospace" }}>{d.value.toFixed(1)}{metric.unit}</div>
                    <div style={{ fontSize: 9, color: COLORS.textDim }}>{d.period}</div>
                  </div>
                ))}
              </div>
            </div>
          ))}

          {/* Margin trend */}
          <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, padding: "16px 20px" }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.accent, marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.06em" }}>Margin Trend</div>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                  <th style={{ textAlign: "left", padding: "4px 8px", color: COLORS.textDim, fontSize: 10 }}>Period</th>
                  <th style={{ textAlign: "right", padding: "4px 8px", color: COLORS.textDim, fontSize: 10 }}>Gross Margin</th>
                  <th style={{ textAlign: "right", padding: "4px 8px", color: COLORS.textDim, fontSize: 10 }}>EBITDA Margin</th>
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
            <div style={{ padding: 20, textAlign: "center", color: COLORS.textMuted, fontSize: 13 }}>No new items detected this period.</div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                  <th style={{ textAlign: "left", padding: "6px 12px", color: COLORS.textDim, fontSize: 10, textTransform: "uppercase" }}>Description</th>
                  <th style={{ textAlign: "right", padding: "6px 12px", color: COLORS.textDim, fontSize: 10 }}>Amount</th>
                  <th style={{ textAlign: "center", padding: "6px 8px", color: COLORS.textDim, fontSize: 10 }}>Classification</th>
                  <th style={{ textAlign: "center", padding: "6px 8px", color: COLORS.textDim, fontSize: 10 }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {data.new_items.map((item, i) => (
                  <tr key={i} style={{ borderBottom: `1px solid ${COLORS.border}15` }}>
                    <td style={{ padding: "6px 12px", color: COLORS.text }}>{item.description}</td>
                    <td style={{ textAlign: "right", padding: "6px 12px", fontFamily: "'IBM Plex Mono',monospace", color: item.amount >= 0 ? COLORS.green : COLORS.red }}>{fmtM(item.amount)}</td>
                    <td style={{ textAlign: "center", padding: "6px 8px" }}>
                      <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 3, fontWeight: 600, color: COLORS.accent, background: "rgba(199,120,64,0.08)" }}>{item.classification_suggestion.toUpperCase()}</span>
                    </td>
                    <td style={{ textAlign: "center", padding: "6px 8px" }}>
                      <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 3, fontWeight: 600, color: item.recommended_action === "add_to_bridge" ? COLORS.green : COLORS.textMuted, background: item.recommended_action === "add_to_bridge" ? COLORS.greenBg : `${COLORS.textDim}15` }}>{item.recommended_action.replace(/_/g, " ").toUpperCase()}</span>
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
  if (typeof v === "number") return Math.abs(v) > 100_000 ? fmtM(v) : v.toLocaleString();
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
                <th key={h} style={{ textAlign: typeof first[h] === "number" ? "right" : "left", padding: "4px 8px", fontSize: 10, color: COLORS.textDim, textTransform: "uppercase", letterSpacing: "0.04em" }}>
                  {h.replace(/_/g, " ")}
                </th>
              ))}
              {nestedKeys.length > 0 && <th style={{ padding: "4px 8px", fontSize: 10, color: COLORS.textDim }}></th>}
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
                          <div key={nk} style={{ fontSize: 11, color: COLORS.textMuted }}>
                            <span style={{ color: COLORS.textDim, fontSize: 10 }}>{nk.replace(/_/g, " ")}: </span>
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
              <span style={{ color: COLORS.textDim, fontSize: 11 }}>{k.replace(/_/g, " ")}:</span>{" "}
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
                <span style={{ color: COLORS.textDim, fontSize: 11 }}>{k.replace(/_/g, " ")}:</span>{" "}
                <span style={{ color: COLORS.text, fontFamily: typeof v === "number" ? "'IBM Plex Mono',monospace" : "'IBM Plex Sans',sans-serif" }}>{formatDashVal(v)}</span>
              </div>
            );
          }
          return (
            <div key={k} style={{ background: depth < 1 ? COLORS.bg : "transparent", borderRadius: 6, padding: depth < 1 ? "10px 14px" : "0 0 0 12px", borderLeft: depth < 1 ? "none" : `2px solid ${COLORS.border}` }}>
              <div style={{ fontSize: 10, fontWeight: 600, color: COLORS.accent, marginBottom: 6, textTransform: "uppercase", letterSpacing: "0.04em" }}>{k.replace(/_/g, " ")}</div>
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
            padding: "8px 20px", fontSize: 12, fontWeight: persona === p.id ? 700 : 400,
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
          <div style={{ fontSize: 16, fontWeight: 600, color: COLORS.text, marginBottom: 20, fontFamily: "'IBM Plex Sans',sans-serif" }}>{data.title}</div>

          {/* KPI cards */}
          <div style={{ display: "flex", gap: 16, marginBottom: 24, flexWrap: "wrap" }}>
            {Object.entries(data.kpis).map(([key, val]) => (
              <div key={key} style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "14px 18px", flex: "1 1 180px", minWidth: 180 }}>
                <div style={{ fontSize: 10, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", fontFamily: "'JetBrains Mono',monospace" }}>
                  {key.replace(/_/g, " ")}
                </div>
                <div style={{ fontSize: 20, fontWeight: 700, color: COLORS.text, fontFamily: "'IBM Plex Mono',monospace", marginTop: 4 }}>
                  {typeof val === "number" && Math.abs(val) > 100_000 ? fmtM(val) : typeof val === "number" ? val.toLocaleString() : String(val)}
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
                <div style={{ padding: "10px 16px", borderBottom: `1px solid ${COLORS.border}`, fontSize: 11, fontWeight: 600, color: COLORS.accent, letterSpacing: "0.06em", textTransform: "uppercase", fontFamily: "'JetBrains Mono',monospace" }}>
                  {key.replace(/_/g, " ")}
                </div>
                <div style={{ padding: "12px 16px", fontSize: 12, color: COLORS.textMuted, maxHeight: 400, overflowY: "auto" }}>
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
      {title && <div style={{ padding: "6px 10px", fontSize: 11, fontWeight: 600, color: COLORS.accent, background: COLORS.headerBg, borderBottom: `1px solid ${COLORS.border}`, fontFamily: "'JetBrains Mono',monospace" }}>{title}</div>}
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
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
        style={{ display: "flex", alignItems: "center", gap: 4, padding: "3px 0", cursor: hasChildren ? "pointer" : "default", fontSize: 12, color: COLORS.text }}
      >
        <span style={{ width: 14, textAlign: "center", color: COLORS.textDim, fontSize: 10 }}>{hasChildren ? (expanded ? "\u25BC" : "\u25B6") : "\u2022"}</span>
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
      {title && <div style={{ fontSize: 11, fontWeight: 600, color: COLORS.accent, marginBottom: 6, fontFamily: "'JetBrains Mono',monospace" }}>{title}</div>}
      <HierarchyNodeView node={root} />
    </div>
  );
}

function InlineComparison({ dimension, systems }: { dimension?: string; systems?: { system: string; value: string; is_match?: boolean }[] }) {
  if (!systems) return null;
  return (
    <div style={{ margin: "8px 0", borderRadius: 6, overflow: "hidden", border: `1px solid ${COLORS.border}` }}>
      {dimension && <div style={{ padding: "6px 10px", fontSize: 11, fontWeight: 600, color: COLORS.accent, background: COLORS.headerBg, borderBottom: `1px solid ${COLORS.border}`, fontFamily: "'JetBrains Mono',monospace" }}>Comparison: {dimension}</div>}
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${systems.length}, 1fr)`, gap: 0 }}>
        {systems.map((s, i) => (
          <div key={i} style={{
            padding: "8px 12px", textAlign: "center",
            borderRight: i < systems.length - 1 ? `1px solid ${COLORS.border}` : "none",
            background: s.is_match === false ? COLORS.redBg : s.is_match === true ? COLORS.greenBg : "transparent",
          }}>
            <div style={{ fontSize: 10, fontWeight: 600, color: COLORS.textMuted, marginBottom: 4 }}>{s.system}</div>
            <div style={{ fontSize: 13, color: COLORS.text, fontWeight: 600 }}>{s.value}</div>
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
        <span style={{ fontSize: 11, fontWeight: 600, color: COLORS.accent, fontFamily: "'JetBrains Mono',monospace", letterSpacing: "0.06em" }}>DD DELIVERABLES</span>
      </div>
      <div style={{ padding: "8px 12px" }}>
        {deliverables.map((d) => (
          <div key={d.id} style={{ padding: "4px 0", display: "flex", alignItems: "flex-start", gap: 8 }}>
            <span style={{ fontSize: 14, lineHeight: "18px", color: d.selected ? COLORS.green : COLORS.textDim, flexShrink: 0 }}>{d.selected ? "\u2611" : "\u2610"}</span>
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, color: COLORS.text }}>{d.name}</div>
              <div style={{ fontSize: 11, color: COLORS.textMuted }}>{d.description}</div>
            </div>
          </div>
        ))}
      </div>
      {reconciliation_objects && (
        <>
          <div style={{ padding: "8px 12px", background: COLORS.headerBg, borderTop: `1px solid ${COLORS.border}`, borderBottom: `1px solid ${COLORS.border}` }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: COLORS.accent, fontFamily: "'JetBrains Mono',monospace", letterSpacing: "0.06em" }}>RECONCILIATION OBJECTS (always included)</span>
          </div>
          <div style={{ padding: "8px 12px" }}>
            {reconciliation_objects.map((obj, i) => (
              <div key={i} style={{ padding: "2px 0", fontSize: 12, color: COLORS.text, display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ color: COLORS.green, fontSize: 12 }}>{"\u2713"}</span> {obj}
              </div>
            ))}
          </div>
        </>
      )}
      {synergy_targets && (
        <>
          <div style={{ padding: "8px 12px", background: COLORS.headerBg, borderTop: `1px solid ${COLORS.border}`, borderBottom: `1px solid ${COLORS.border}` }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: COLORS.accent, fontFamily: "'JetBrains Mono',monospace", letterSpacing: "0.06em" }}>DEAL MODEL TARGETS</span>
          </div>
          <div style={{ padding: "8px 12px", fontSize: 12, color: COLORS.text }}>
            {synergy_targets.revenue_synergy != null && <div>Revenue synergy: ${(synergy_targets.revenue_synergy / 1e6).toFixed(0)}M</div>}
            {synergy_targets.cost_synergy != null && <div>Cost synergy: ${(synergy_targets.cost_synergy / 1e6).toFixed(0)}M</div>}
            {synergy_targets.integration_budget != null && <div>Integration budget: ${(synergy_targets.integration_budget / 1e6).toFixed(0)}M</div>}
          </div>
        </>
      )}
    </div>
  );
}

function RichContentRenderer({ content }: { content: any }) {
  if (!content || !content.type) return null;
  switch (content.type) {
    case "table": return <InlineTable title={content.title} headers={content.headers} rows={content.rows} />;
    case "hierarchy": return <InlineHierarchy title={content.title} root={content.root} />;
    case "comparison": return <InlineComparison dimension={content.dimension} systems={content.systems} />;
    case "scope_checklist": return <InlineScopeChecklist deliverables={content.deliverables} reconciliation_objects={content.reconciliation_objects} synergy_targets={content.synergy_targets} />;
    default: return null;
  }
}

// ── Maestra Floating Chat ──────────────────────────────────────────────────
type ChatMsg = { role: "user" | "maestra"; text: string; richContent?: any[]; nav?: string; completeness?: number };

function MaestraFloatingChat({ onNavigate, onEntityChange }: { onNavigate?: (tab: string) => void; onEntityChange?: (entity: EntitySelection) => void }) {
  const [expanded, setExpanded] = useState(false);
  const [engagementId, setEngagementId] = useState<string | null>(null);
  const [status, setStatus] = useState<MaestraStatus | null>(null);
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [completeness, setCompleteness] = useState(0);
  const [unreadCount, setUnreadCount] = useState(0);
  const [section, setSection] = useState<string>("");
  const chatEndRef = React.useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => { scrollToBottom(); }, [messages, loading]);

  // Clear unread when expanded
  useEffect(() => { if (expanded) setUnreadCount(0); }, [expanded]);

  const startEngagement = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const eng = await createMaestraEngagement();
      setEngagementId(eng.engagement_id);
      setMessages([{
        role: "maestra",
        text: `I've completed my background research on both Meridian Partners and Cascadia Advisory. I have their business profiles, systems landscape, and deal context loaded.\n\nLet's get started — I'll walk you through what I found and confirm the details with you.`,
      }]);
      setSuggestions(["Let's go", "What do you know so far?", "Tell me about both companies"]);
      setSection("PDC");
      const st = await fetchMaestraStatus(eng.engagement_id);
      setStatus(st);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  const handleNavigate = useCallback((tab: string) => {
    if (onNavigate) onNavigate(tab);
    // Auto-switch to combined entity for M&A tabs
    const combinedTabs = ["combining", "overlap", "crosssell", "cross_sell", "bridge", "ebitda", "whatif", "what_if", "qoe", "dashboards"];
    if (onEntityChange && combinedTabs.includes(tab)) {
      onEntityChange("combined");
    }
  }, [onNavigate, onEntityChange]);

  const sendMessage = useCallback(async (overrideMsg?: string) => {
    const msg = (overrideMsg || input).trim();
    if (!engagementId || !msg) return;
    setInput("");
    setSuggestions([]);
    setMessages((prev) => [...prev, { role: "user", text: msg }]);
    setLoading(true);
    try {
      const resp = await sendMaestraMessage(engagementId, msg);
      const newMsg: ChatMsg = {
        role: "maestra",
        text: resp.response,
        richContent: resp.rich_content,
        completeness: resp.completeness,
      };
      setMessages((prev) => [...prev, newMsg]);
      if (!expanded) setUnreadCount((c) => c + 1);

      if (resp.completeness !== undefined) setCompleteness(resp.completeness);
      if (resp.suggestions) setSuggestions(resp.suggestions);
      if (resp.section) setSection(resp.section);

      if (resp.navigation && handleNavigate) {
        // Map navigate_portal tab names to portal tab IDs
        const tabMap: Record<string, string> = {
          cross_sell: "crosssell", ebitda: "bridge", what_if: "whatif",
          pl: "pl", bs: "bs", socf: "cf", drill: "pl", recon: "recon",
          combining: "combining", overlap: "overlap", qoe: "qoe", dashboard: "dashboards",
        };
        const portalTab = tabMap[resp.navigation.tab] || resp.navigation.tab;
        handleNavigate(portalTab);
        setMessages((prev) => [...prev, {
          role: "maestra",
          text: `I've opened the ${resp.navigation!.tab.replace(/_/g, " ")} view in the portal.`,
          nav: portalTab,
        }]);
      }
      const st = await fetchMaestraStatus(engagementId);
      setStatus(st);
    } catch (err) {
      setMessages((prev) => [...prev, { role: "maestra", text: `Error: ${err instanceof Error ? err.message : String(err)}` }]);
    } finally {
      setLoading(false);
    }
  }, [engagementId, input, handleNavigate, expanded]);

  const sectionLabel = (s: string) => {
    const labels: Record<string, string> = {
      PDC: "Deal Context", PDA: "Acquirer Profile", PDT: "Target Profile",
      PDS: "DD Scope", PDR: "Analysis", PDF: "Findings",
    };
    return labels[s] || s;
  };

  // Collapsed state — floating icon
  // Use createPortal to render at document.body, bypassing any parent overflow/transform constraints
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
        {/* M icon */}
        <span style={{ fontSize: 22, fontWeight: 700, color: "#fff", fontFamily: "'IBM Plex Sans',sans-serif", lineHeight: 1 }}>M</span>
        {/* Notification badge */}
        {unreadCount > 0 && (
          <span style={{
            position: "absolute", top: -2, right: -2, minWidth: 18, height: 18,
            borderRadius: 9, background: COLORS.red, color: "#fff",
            fontSize: 10, fontWeight: 700, display: "flex", alignItems: "center",
            justifyContent: "center", padding: "0 4px",
          }}>{unreadCount}</span>
        )}
      </div>,
      document.body,
    );
  }

  // Expanded state — full chat panel
  // Use createPortal to render at document.body, bypassing any parent overflow/transform constraints
  return createPortal(
    <div style={{
      position: "fixed", bottom: 24, right: 24, width: 420, height: 580,
      borderRadius: 12, background: COLORS.surface, border: `1px solid ${COLORS.border}`,
      display: "flex", flexDirection: "column", overflow: "hidden",
      boxShadow: "0 8px 40px rgba(0,0,0,0.5)", zIndex: 10000,
      fontFamily: "'IBM Plex Sans',sans-serif",
    }}>
      {/* Header */}
      <div style={{
        padding: "12px 16px", background: COLORS.headerBg,
        borderBottom: `1px solid ${COLORS.border}`,
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ width: 28, height: 28, borderRadius: "50%", background: COLORS.accent, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <span style={{ fontSize: 14, fontWeight: 700, color: "#fff" }}>M</span>
          </span>
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: COLORS.text }}>Maestra</div>
            <div style={{ fontSize: 10, color: COLORS.textMuted }}>
              {!engagementId ? "Integration Manager" : section ? sectionLabel(section) : status?.phase || "Ready"}
              {completeness > 0 && <span style={{ marginLeft: 6, color: completeness >= 70 ? COLORS.green : COLORS.accent }}>{completeness}%</span>}
            </div>
          </div>
        </div>
        <button
          onClick={() => setExpanded(false)}
          style={{ background: "transparent", border: "none", color: COLORS.textMuted, cursor: "pointer", fontSize: 18, padding: "0 4px", lineHeight: 1 }}
          title="Minimize"
        >{"\u2013"}</button>
      </div>

      {/* Body */}
      {!engagementId ? (
        /* First visit — Start New Engagement */
        <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "40px 24px", textAlign: "center" }}>
          <div style={{
            width: 64, height: 64, borderRadius: "50%", background: `${COLORS.accent}22`,
            display: "flex", alignItems: "center", justifyContent: "center", marginBottom: 20,
          }}>
            <span style={{ fontSize: 28, fontWeight: 700, color: COLORS.accent }}>M</span>
          </div>
          <div style={{ fontSize: 15, fontWeight: 600, color: COLORS.text, marginBottom: 8 }}>Maestra Integration Manager</div>
          <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 24, lineHeight: 1.5 }}>
            I'll guide you through the Meridian-Cascadia integration — from initial scoping through findings presentation.
          </div>
          {error && <div style={{ color: COLORS.red, fontSize: 11, marginBottom: 12 }}>{error}</div>}
          <button onClick={startEngagement} disabled={loading} style={{
            padding: "12px 32px", fontSize: 14, fontWeight: 600, cursor: "pointer",
            background: COLORS.accent, color: "#fff", border: "none", borderRadius: 8,
            opacity: loading ? 0.6 : 1, transition: "opacity 0.15s",
          }}>{loading ? "Preparing..." : "Start New Engagement"}</button>
        </div>
      ) : (
        /* Chat interface */
        <>
          <div style={{ flex: 1, overflowY: "auto", padding: "12px 16px" }}>
            {messages.map((m, i) => (
              <div key={i} style={{ marginBottom: 12, textAlign: m.role === "user" ? "right" : "left" }}>
                {m.nav && handleNavigate ? (
                  <button onClick={() => handleNavigate(m.nav!)} style={{
                    display: "inline-block", padding: "6px 14px", borderRadius: 8,
                    background: "rgba(199,120,64,0.12)", border: `1px solid ${COLORS.accent}44`,
                    color: COLORS.accent, fontSize: 12, fontWeight: 600, cursor: "pointer",
                  }}>
                    {"\u2197"} {m.text}
                  </button>
                ) : (
                  <>
                    <div style={{
                      display: "inline-block", maxWidth: "88%", padding: "8px 14px", borderRadius: 8,
                      background: m.role === "user" ? "rgba(199,120,64,0.12)" : COLORS.bg,
                      color: COLORS.text, fontSize: 13, lineHeight: 1.5,
                      textAlign: "left", whiteSpace: "pre-wrap",
                    }}>{m.text}</div>
                    {m.richContent && m.richContent.length > 0 && (
                      <div style={{ maxWidth: "88%", display: "inline-block", width: "100%" }}>
                        {m.richContent.map((rc: any, j: number) => <RichContentRenderer key={j} content={rc} />)}
                      </div>
                    )}
                  </>
                )}
              </div>
            ))}
            {loading && (
              <div style={{ fontSize: 12, color: COLORS.textDim, fontStyle: "italic", display: "flex", alignItems: "center", gap: 6, padding: "4px 0" }}>
                <span style={{ display: "inline-flex", gap: 3 }}>
                  {[0, 1, 2].map(d => <span key={d} style={{ width: 4, height: 4, borderRadius: "50%", background: COLORS.accent, animation: `bounce 1.4s ${d * 0.16}s infinite ease-in-out both` }} />)}
                </span>
                Maestra is thinking...
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Suggestions */}
          {suggestions.length > 0 && !loading && (
            <div style={{ padding: "6px 12px", borderTop: `1px solid ${COLORS.border}22`, display: "flex", gap: 6, flexWrap: "wrap" }}>
              {suggestions.map((s, i) => (
                <button key={i} onClick={() => sendMessage(s)} style={{
                  padding: "4px 10px", fontSize: 11, borderRadius: 12, cursor: "pointer",
                  background: COLORS.bg, color: COLORS.textMuted, border: `1px solid ${COLORS.border}`,
                }}>{s}</button>
              ))}
            </div>
          )}

          {/* Input */}
          <div style={{ padding: "10px 12px", borderTop: `1px solid ${COLORS.border}`, display: "flex", gap: 8 }}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
              placeholder="Ask Maestra..."
              style={{
                flex: 1, padding: "8px 12px", fontSize: 13, background: COLORS.bg, color: COLORS.text,
                border: `1px solid ${COLORS.border}`, borderRadius: 6, outline: "none",
              }}
            />
            <button onClick={() => sendMessage()} disabled={loading || !input.trim()} style={{
              padding: "8px 16px", fontSize: 12, fontWeight: 600, cursor: "pointer",
              background: COLORS.accent, color: "#fff", border: "none", borderRadius: 6,
              opacity: loading || !input.trim() ? 0.5 : 1,
            }}>Send</button>
          </div>
        </>
      )}
    </div>,
    document.body,
  );
}

// ============================================================
// MAIN COMPONENT
// ============================================================
export function ReportPortal({ onClose }: { onClose: () => void }) {
  const [entity, setEntity] = useState<EntitySelection>("meridian");
  const [tab, setTab] = useState("pl");
  const [variant, setVariant] = useState("act_vs_py");
  const [quarter, setQuarter] = useState("2025-Q3");
  const [segment, setSegment] = useState("all");

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

  // Overlap report data states
  const [overlapData, setOverlapData] = useState<OverlapData | null>(null);
  const [overlapLoading, setOverlapLoading] = useState(false);
  const [overlapError, setOverlapError] = useState<string | null>(null);

  const actQuarters = useMemo(() => QUARTERS.filter(isActual), []);
  const cfQuarters = useMemo(() => QUARTERS.filter((q) => !isActual(q) && q.startsWith(String(wallClockDate().getFullYear()))), []);
  const lastFullYear = wallClockDate().getFullYear() - 1;
  const pyYear = lastFullYear - 1;

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
      { id: "pl", label: "Income Statement" },
      { id: "bs", label: "Balance Sheet" },
      { id: "cf", label: "Cash Flow" },
      { id: "recon", label: "Reconciliation" },
    ];
    if (entity === "combined") {
      return [
        ...base,
        { id: "combining", label: "Combining" },
        { id: "overlap", label: "Overlap" },
        { id: "crosssell", label: "Cross-Sell" },
        { id: "bridge", label: "EBITDA Bridge" },
        { id: "whatif", label: "What-If" },
        { id: "qoe", label: "QofE" },
        { id: "dashboards", label: "Dashboards" },
      ];
    }
    return base;
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
    if (variant === "cf_vs_py") return `${wallClockDate().getFullYear()}-Q2`;
    if (variant === "q_cf_vs_py") return quarter || cfQuarters[0];
    if (variant === "quarterly") return quarter;
    return `${lastFullYear}-Q4`;
  }, [variant, quarter, lastFullYear, cfQuarters]);

  // Fetch report data when tab/variant/quarter/segment changes
  const loadReport = useCallback(async () => {
    if (!isStatementTab) return;

    setLoading(true);
    setError(null);

    const statement = tabToStatement(tab);
    const apiVariant = mapVariant(variant);

    try {
      const result = await fetchReport(statement, apiVariant, effectiveQuarter, seg, entity);
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
      setError(err instanceof Error ? err.message : String(err));
      setCurrentData(null);
      setPyData(null);
      setRawFSData(null);
    } finally {
      setLoading(false);
    }
  }, [tab, variant, effectiveQuarter, seg, isStatementTab, pyYear, lastFullYear, quarter, cfQuarters, entity]);

  useEffect(() => {
    if (isStatementTab) {
      loadReport();
    }
  }, [loadReport, isStatementTab]);

  // Load combining statement data when the combining tab is active
  const loadCombining = useCallback(async () => {
    if (tab !== "combining" || entity !== "combined") return;
    setCombiningLoading(true);
    setCombiningError(null);
    try {
      const result = await fetchCombiningStatement(effectiveQuarter);
      setCombiningData(result);
    } catch (err) {
      setCombiningError(err instanceof Error ? err.message : String(err));
      setCombiningData(null);
    } finally {
      setCombiningLoading(false);
    }
  }, [tab, entity, effectiveQuarter]);

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

      {/* Header */}
      <div style={{ padding: "20px 32px", borderBottom: `1px solid ${COLORS.border}`, display: "flex", justifyContent: "space-between", alignItems: "center", background: COLORS.headerBg }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <span style={{ fontSize: 18, fontWeight: 700, color: COLORS.accent, letterSpacing: "-0.02em" }}>AOS</span>
          <span style={{ color: COLORS.textDim }}>|</span>
          <span style={{ fontSize: 14, fontWeight: 500, color: COLORS.text }}>Financial Report Portal</span>
          <span style={{ fontSize: 11, padding: "3px 10px", background: "rgba(199,120,64,0.12)", color: COLORS.accent, borderRadius: 4, fontWeight: 600 }}>PHASE 1</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <span style={{ fontSize: 12, color: COLORS.textMuted }}>
            {entity === "meridian" ? "Meridian Partners" : entity === "cascadia" ? "Cascadia Group" : "Combined View"} {"\u2022"} {entity === "combined" ? "Multi-Entity" : "Single Entity"} {"\u2022"} {wallClockDate().toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}
          </span>
          <button onClick={onClose} style={{ background: "transparent", border: `1px solid ${COLORS.border}`, color: COLORS.textMuted, cursor: "pointer", padding: "4px 12px", borderRadius: 4, fontSize: 12 }}>
            Close
          </button>
        </div>
      </div>

      {/* Entity Selector — above tab bar */}
      <EntitySelector selected={entity} onChange={handleEntityChange} />

      <div style={{ flex: 1, overflow: "auto", padding: "24px 32px" }}>
        <TabBar tabs={statementTabs} active={tab} onChange={handleTabChange} />

        {isStatementTab && (
          <div style={{ display: "flex", gap: 16, marginBottom: 24, flexWrap: "wrap" }}>
            <Select label="Report Variant" value={variant} onChange={setVariant} options={variantOptions} width={220} />
            {showQuarterSelect && <Select label="Quarter" value={quarter} onChange={setQuarter} options={quarterOptions} width={140} />}
            <Select label="Segment" value={segment} onChange={setSegment} width={180} options={[
              { value: "all", label: "All Segments" },
              ...SEGMENTS.map((s) => ({ value: s, label: s })),
            ]} />
          </div>
        )}

        {isStatementTab && loading && <LoadingState message={`Loading ${tab === "pl" ? "Income Statement" : tab === "bs" ? "Balance Sheet" : "Cash Flow"}...`} />}

        {isStatementTab && error && !loading && <ErrorState error={error} onRetry={loadReport} />}

        {isStatementTab && !loading && !error && currentData && (
          <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, overflow: "hidden" }}>
            <div style={{ padding: "12px 20px", borderBottom: `1px solid ${COLORS.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 14, fontWeight: 600, color: COLORS.text }}>
                {tab === "pl" ? "Income Statement" : tab === "bs" ? "Balance Sheet" : "Statement of Cash Flows"}
              </span>
              <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
                {currentData.metadata.periodType === "forecast" && (
                  <span style={{ fontSize: 11, padding: "3px 8px", background: "rgba(91,141,239,0.12)", color: COLORS.blue, borderRadius: 4, fontWeight: 600 }}>CONTAINS FORECAST</span>
                )}
                {segment !== "all" && (
                  <span style={{ fontSize: 11, padding: "3px 8px", background: "rgba(199,120,64,0.12)", color: COLORS.accent, borderRadius: 4, fontWeight: 600 }}>FILTERED: {segment}</span>
                )}
              </div>
            </div>
            <StatementTable data={currentData} pyData={pyData} showVariance={variant !== "quarterly"} onDrillLine={(id, name) => setDrillLine(drillLine?.id === id ? null : { id, name })} />
          </div>
        )}

        {/* Inline drill-through below FS table */}
        {isStatementTab && !loading && drillLine && (
          <div style={{ marginTop: 12 }}>
            {(drillLine.id === "revenue" || drillLine.id === "total_revenue") ? (
              <DrillThrough onClose={() => setDrillLine(null)} />
            ) : rawFSData ? (
              <LineDetail lineKey={drillLine.id} lineName={drillLine.name} fsData={rawFSData} onClose={() => setDrillLine(null)} />
            ) : null}
          </div>
        )}

        {tab === "recon" && <ReconView />}
        {tab === "combining" && entity === "combined" && (
          <CombiningStatement data={combiningData} loading={combiningLoading} error={combiningError} onRetry={loadCombining} />
        )}
        {tab === "overlap" && entity === "combined" && (
          <OverlapReport data={overlapData} loading={overlapLoading} error={overlapError} onRetry={loadOverlap} />
        )}
        {tab === "crosssell" && entity === "combined" && <CrossSellTab />}
        {tab === "bridge" && entity === "combined" && <EBITDABridgeTab />}
        {tab === "whatif" && entity === "combined" && <WhatIfTab />}
        {tab === "qoe" && entity === "combined" && <QofETab />}
        {tab === "dashboards" && entity === "combined" && <DashboardsTab />}
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
