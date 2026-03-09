import { useState, useEffect, useCallback, useMemo } from "react";
import { fetchReport, fetchDrillThrough, fetchReconciliation, fetchCombiningStatement, fetchOverlapData } from "./api";
import type { ReportData, ReconReport, ReconCheck, DrillThroughItem, ReportVariant, EntitySelection, CombiningStatementData, OverlapData } from "./types";

// ============================================================
// FORMATTING
// ============================================================
function fmt(n: number | null | undefined, isPercent = false): string {
  if (n === null || n === undefined) return "";
  if (isPercent) return (n * 100).toFixed(1) + "%";
  const abs = Math.abs(n);
  const formatted =
    abs >= 1000000
      ? (abs / 1000000).toFixed(1) + "M"
      : abs >= 1000
        ? (abs / 1000).toFixed(0) + "K"
        : abs.toFixed(0);
  return n < 0 ? `(${formatted})` : `$${formatted}`;
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

function StatementTable({ data, pyData, showVariance = true }: { data: ReportData | null; pyData: ReportData | null; showVariance?: boolean }) {
  if (!data) return null;
  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "'IBM Plex Mono','JetBrains Mono',monospace", fontSize: 13 }}>
        <thead>
          <tr style={{ borderBottom: `2px solid ${COLORS.accent}` }}>
            <th style={{ textAlign: "left", padding: "10px 16px", color: COLORS.textMuted, fontWeight: 500, width: "40%", fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>Line Item</th>
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
            return (
              <tr key={line.id} style={{
                borderBottom: line.isFinal ? `2px double ${COLORS.accent}` : line.isTotal ? `1px solid ${COLORS.borderLight}` : `1px solid ${COLORS.border}22`,
                background: rowBg,
              }}>
                <td style={{
                  padding: line.isHeader ? "14px 16px 6px" : "8px 16px",
                  paddingLeft: line.level === 1 ? 40 : 16,
                  color: line.isHeader ? COLORS.accent : line.bold ? COLORS.text : line.isPercent ? COLORS.textMuted : COLORS.text,
                  fontWeight: line.bold || line.isHeader ? 600 : 400,
                  fontSize: line.isHeader ? 12 : 13,
                  letterSpacing: line.isHeader ? "0.06em" : "0",
                  textTransform: line.isHeader ? "uppercase" as const : "none" as const,
                  fontFamily: "'IBM Plex Sans',sans-serif",
                  cursor: line.drillable ? "pointer" : "default",
                }}>
                  {line.drillable && <span style={{ color: COLORS.accent, marginRight: 6 }}>{"\u25B8"}</span>}
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
              <th style={{ ...thStyle, textAlign: "left", width: "30%" }}>Line Item</th>
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
  if (loading) return <LoadingState message="Loading entity overlap data..." />;
  if (error) return <ErrorState error={error} onRetry={onRetry} />;
  if (!data) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
      {/* Customer Overlap */}
      <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, overflow: "hidden" }}>
        <div style={{ padding: "12px 20px", borderBottom: `1px solid ${COLORS.border}` }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: COLORS.text }}>Customer Overlap</span>
        </div>
        <div style={{ padding: "20px", display: "flex", gap: 24 }}>
          <div style={{ background: COLORS.bg, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "16px 24px", flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.accent, fontFamily: "'IBM Plex Mono',monospace" }}>{data.customers.count}</div>
            <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4 }}>Overlapping Customers</div>
          </div>
          <div style={{ background: COLORS.bg, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "16px 24px", flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.textDim, fontFamily: "'IBM Plex Mono',monospace" }}>{data.customers.pct_of_combined.toFixed(1)}%</div>
            <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4 }}>% of Combined</div>
          </div>
          <div style={{ background: COLORS.bg, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "16px 24px", flex: 2 }}>
            <div style={{ fontSize: 12, color: COLORS.textMuted, marginBottom: 8 }}>Match Type Breakdown</div>
            <div style={{ display: "flex", gap: 16, fontSize: 13, color: COLORS.textDim, fontFamily: "'IBM Plex Mono',monospace" }}>
              <span>Exact: {data.customers.match_types.exact}</span>
              <span>Fuzzy: {data.customers.match_types.fuzzy}</span>
              <span>Manual: {data.customers.match_types.manual}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Vendor Overlap */}
      <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, overflow: "hidden" }}>
        <div style={{ padding: "12px 20px", borderBottom: `1px solid ${COLORS.border}` }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: COLORS.text }}>Vendor Overlap</span>
        </div>
        <div style={{ padding: "20px", display: "flex", gap: 24 }}>
          <div style={{ background: COLORS.bg, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "16px 24px", flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.accent, fontFamily: "'IBM Plex Mono',monospace" }}>{data.vendors.count}</div>
            <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4 }}>Overlapping Vendors</div>
          </div>
          <div style={{ background: COLORS.bg, border: `1px solid ${COLORS.border}`, borderRadius: 8, padding: "16px 24px", flex: 1, textAlign: "center" }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: COLORS.textDim, fontFamily: "'IBM Plex Mono',monospace" }}>{data.vendors.pct_of_combined.toFixed(1)}%</div>
            <div style={{ fontSize: 12, color: COLORS.textMuted, marginTop: 4 }}>% of Combined</div>
          </div>
        </div>
      </div>

      {/* People Overlap */}
      <div style={{ background: COLORS.surface, borderRadius: 8, border: `1px solid ${COLORS.border}`, overflow: "hidden" }}>
        <div style={{ padding: "12px 20px", borderBottom: `1px solid ${COLORS.border}` }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: COLORS.text }}>People Overlap by Function</span>
        </div>
        <div style={{ padding: "12px 20px" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: "'IBM Plex Mono','JetBrains Mono',monospace", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: `2px solid ${COLORS.accent}` }}>
                <th style={{ textAlign: "left", padding: "8px 12px", color: COLORS.textMuted, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>Function</th>
                <th style={{ textAlign: "right", padding: "8px 12px", color: COLORS.textMuted, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>Meridian</th>
                <th style={{ textAlign: "right", padding: "8px 12px", color: COLORS.textMuted, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>Cascadia</th>
                <th style={{ textAlign: "right", padding: "8px 12px", color: COLORS.textMuted, fontSize: 11, letterSpacing: "0.06em", textTransform: "uppercase" }}>Combined</th>
              </tr>
            </thead>
            <tbody>
              {data.people.map((p, i) => (
                <tr key={i} style={{ borderBottom: `1px solid ${COLORS.border}22` }}>
                  <td style={{ padding: "8px 12px", color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif" }}>{p.function}</td>
                  <td style={{ textAlign: "right", padding: "8px 12px", color: COLORS.text }}>{p.meridian.toLocaleString()}</td>
                  <td style={{ textAlign: "right", padding: "8px 12px", color: COLORS.text }}>{p.cascadia.toLocaleString()}</td>
                  <td style={{ textAlign: "right", padding: "8px 12px", color: COLORS.text }}>{p.overlap.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
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
    if (e !== "combined" && (tab === "combining" || tab === "overlap")) {
      setTab("pl");
    }
  }, [tab]);

  const handleTabChange = useCallback((t: string) => {
    setTab(t);
    if (t === "bs" && variant !== "act_vs_py" && variant !== "quarterly") {
      setVariant("act_vs_py");
    }
  }, [variant]);

  const statementTabs = useMemo(() => {
    const base = [
      { id: "pl", label: "Income Statement" },
      { id: "bs", label: "Balance Sheet" },
      { id: "cf", label: "Cash Flow" },
      { id: "drill", label: "Revenue Drill-Through" },
      { id: "recon", label: "Reconciliation" },
    ];
    if (entity === "combined") {
      return [
        ...base,
        { id: "combining", label: "Combining" },
        { id: "overlap", label: "Overlap" },
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

      // Also fetch PY data if showing variance (not quarterly-only view)
      if (variant !== "quarterly") {
        // Determine PY quarter
        let pyQuarter: string;
        if (variant === "act_vs_py") {
          pyQuarter = `${pyYear}-Q4`;
        } else if (variant === "q_act_vs_py") {
          const [y, q] = quarter.split("-");
          pyQuarter = `${parseInt(y) - 1}-${q}`;
        } else if (variant === "cf_vs_py") {
          pyQuarter = `${lastFullYear}-Q4`;
        } else if (variant === "q_cf_vs_py") {
          const [y, q] = (quarter || cfQuarters[0]).split("-");
          pyQuarter = `${parseInt(y) - 1}-${q}`;
        } else {
          pyQuarter = `${pyYear}-Q4`;
        }

        try {
          const pyResult = await fetchReport(statement, apiVariant, pyQuarter, seg, entity);
          setPyData(pyResult.reportData);
        } catch {
          // PY data is supplementary — don't block the main view
          setPyData(null);
        }
      } else {
        setPyData(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setCurrentData(null);
      setPyData(null);
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
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", background: COLORS.bg, color: COLORS.text, fontFamily: "'IBM Plex Sans',sans-serif", padding: 0, overflow: "hidden" }}>
      <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet" />

      {/* Header */}
      <div style={{ padding: "20px 32px", borderBottom: `1px solid ${COLORS.border}`, display: "flex", justifyContent: "space-between", alignItems: "center", background: COLORS.headerBg }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <span style={{ fontSize: 18, fontWeight: 700, color: COLORS.accent, letterSpacing: "-0.02em" }}>AOS</span>
          <span style={{ color: COLORS.textDim }}>|</span>
          <span style={{ fontSize: 14, fontWeight: 500, color: COLORS.text }}>Financial Report Portal</span>
          <span style={{ fontSize: 11, padding: "3px 10px", background: "rgba(199,120,64,0.12)", color: COLORS.accent, borderRadius: 4, fontWeight: 600 }}>PHASE 0</span>
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
            <StatementTable data={currentData} pyData={pyData} showVariance={variant !== "quarterly"} />
          </div>
        )}

        {tab === "drill" && <DrillThrough onClose={() => setTab("pl")} />}
        {tab === "recon" && <ReconView />}
        {tab === "combining" && entity === "combined" && (
          <CombiningStatement data={combiningData} loading={combiningLoading} error={combiningError} onRetry={loadCombining} />
        )}
        {tab === "overlap" && entity === "combined" && (
          <OverlapReport data={overlapData} loading={overlapLoading} error={overlapError} onRetry={loadOverlap} />
        )}
      </div>
    </div>
  );
}

export default ReportPortal;
