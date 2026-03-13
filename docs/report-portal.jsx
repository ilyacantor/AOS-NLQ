import { useState, useEffect, useCallback, useMemo } from "react";

// ============================================================
// MOCK DATA ENGINE — simulates what DCL/NLQ endpoints return
// Replace with real API calls when connecting to backend
// ============================================================

const QUARTERS = ["2024-Q1","2024-Q2","2024-Q3","2024-Q4","2025-Q1","2025-Q2","2025-Q3","2025-Q4","2026-Q1","2026-Q2","2026-Q3","2026-Q4"];
const REGIONS = ["NA","EMEA","APAC"];
const SEGMENTS = ["Strategy","Operations","Technology","Risk","Digital/AI","Commercial"];

function wallClockDate() { return new Date(); }
function isActual(q) {
  const [y,qn] = q.split("-");
  const qEnd = new Date(parseInt(y), parseInt(qn.replace("Q",""))*3, 0);
  return qEnd < wallClockDate();
}

function seed(s) { let h=0; for(let i=0;i<s.length;i++){h=((h<<5)-h)+s.charCodeAt(i);h|=0;} return()=>{h^=h<<13;h^=h>>17;h^=h<<5;return((h>>>0)/4294967296);}; }

function generatePL(entity="meridian", quarter="2025-Q1", segment=null) {
  const rng = seed(entity+quarter+(segment||"total"));
  const base = entity === "meridian" ? 14500000 : 10000000;
  const scale = segment ? 0.2 + rng()*0.15 : 1;
  const qIdx = QUARTERS.indexOf(quarter);
  const growth = 1 + (qIdx * 0.008) + (rng()-0.5)*0.02;
  const isForecast = !isActual(quarter);
  const variance = isForecast ? 0.98 + rng()*0.04 : 0.92 + rng()*0.16;
  
  const rev = Math.round(base * scale * growth * variance);
  const cogs_labor = Math.round(rev * (0.38 + rng()*0.06));
  const cogs_bench = Math.round(rev * (0.12 + rng()*0.03));
  const cogs_sub = Math.round(rev * (0.05 + rng()*0.02));
  const cogs_travel = Math.round(rev * (0.02 + rng()*0.01));
  const cogs_other = Math.round(rev * (0.01 + rng()*0.005));
  const totalCogs = cogs_labor + cogs_bench + cogs_sub + cogs_travel + cogs_other;
  const gp = rev - totalCogs;
  const opex_sales = Math.round(rev * (0.06 + rng()*0.02));
  const opex_mktg = Math.round(rev * (0.02 + rng()*0.01));
  const opex_ga = Math.round(rev * (0.05 + rng()*0.015));
  const opex_tech = Math.round(rev * (0.025 + rng()*0.01));
  const opex_fac = Math.round(rev * (0.015 + rng()*0.005));
  const totalOpex = opex_sales + opex_mktg + opex_ga + opex_tech + opex_fac;
  const ebit = gp - totalOpex;
  const da = Math.round(rev * (0.02 + rng()*0.005));
  const ebitda = ebit + da;
  
  return {
    lines: [
      { id: "rev", name: "Total Revenue", amount: rev, level: 0, isTotal: true, drillable: true },
      { id: "cogs_hdr", name: "Cost of Revenue", amount: null, level: 0, isHeader: true },
      { id: "cogs_labor", name: "Direct Labor — Onshore", amount: -cogs_labor, level: 1 },
      { id: "cogs_bench", name: "Bench Cost", amount: -cogs_bench, level: 1, highlight: true },
      { id: "cogs_sub", name: "Subcontractor / Third Party", amount: -cogs_sub, level: 1 },
      { id: "cogs_travel", name: "Travel & Project Costs", amount: -cogs_travel, level: 1 },
      { id: "cogs_other", name: "Delivery Center Ops", amount: -cogs_other, level: 1 },
      { id: "cogs_total", name: "Total COGS", amount: -totalCogs, level: 0, isTotal: true, isSub: true },
      { id: "gp", name: "Gross Profit", amount: gp, level: 0, isTotal: true, bold: true },
      { id: "gp_pct", name: "Gross Margin %", amount: gp/rev, level: 0, isPercent: true },
      { id: "opex_hdr", name: "Operating Expenses", amount: null, level: 0, isHeader: true },
      { id: "opex_sales", name: "Sales & Business Development", amount: -opex_sales, level: 1 },
      { id: "opex_mktg", name: "Marketing", amount: -opex_mktg, level: 1 },
      { id: "opex_ga", name: "G&A", amount: -opex_ga, level: 1 },
      { id: "opex_tech", name: "Technology & Platforms", amount: -opex_tech, level: 1 },
      { id: "opex_fac", name: "Facilities", amount: -opex_fac, level: 1 },
      { id: "opex_total", name: "Total OpEx", amount: -totalOpex, level: 0, isTotal: true, isSub: true },
      { id: "ebit", name: "Operating Income (EBIT)", amount: ebit, level: 0, isTotal: true, bold: true },
      { id: "da", name: "Depreciation & Amortization", amount: da, level: 0 },
      { id: "ebitda", name: "EBITDA", amount: ebitda, level: 0, isTotal: true, bold: true, isFinal: true },
      { id: "ebitda_pct", name: "EBITDA Margin %", amount: ebitda/rev, level: 0, isPercent: true },
    ],
    metadata: { entity, quarter, segment, periodType: isActual(quarter) ? "actual" : "forecast" }
  };
}

function generateBS(entity="meridian", quarter="2025-Q4", segment=null) {
  const rng = seed("bs"+entity+quarter+(segment||"total"));
  const base = entity === "meridian" ? 14500000 : 10000000;
  const scale = segment ? 0.2 + rng()*0.15 : 1;
  const qIdx = QUARTERS.indexOf(quarter);
  const growth = 1 + (qIdx * 0.012);
  const rev = base * scale * growth;

  const cash = Math.round(rev * (0.55 + rng()*0.15));
  const ar = Math.round(rev * (0.28 + rng()*0.06));
  const prepaid = Math.round(rev * (0.04 + rng()*0.02));
  const currentAssets = cash + ar + prepaid;
  const ppe = Math.round(rev * (0.15 + rng()*0.05));
  const intangibles = Math.round(rev * (0.08 + rng()*0.04));
  const otherLT = Math.round(rev * (0.03 + rng()*0.02));
  const totalAssets = currentAssets + ppe + intangibles + otherLT;

  const ap = Math.round(rev * (0.12 + rng()*0.04));
  const accrued = Math.round(rev * (0.18 + rng()*0.05));
  const deferredRev = Math.round(rev * (0.10 + rng()*0.04));
  const currentLiab = ap + accrued + deferredRev;
  const ltDebt = Math.round(rev * (0.20 + rng()*0.10));
  const otherLTLiab = Math.round(rev * (0.05 + rng()*0.03));
  const totalLiab = currentLiab + ltDebt + otherLTLiab;
  const equity = totalAssets - totalLiab;

  return {
    lines: [
      { id: "assets_hdr", name: "Assets", amount: null, level: 0, isHeader: true },
      { id: "ca_hdr", name: "Current Assets", amount: null, level: 0, isHeader: true },
      { id: "cash", name: "Cash & Equivalents", amount: cash, level: 1 },
      { id: "ar", name: "Accounts Receivable", amount: ar, level: 1 },
      { id: "prepaid", name: "Prepaid Expenses", amount: prepaid, level: 1 },
      { id: "ca_total", name: "Total Current Assets", amount: currentAssets, level: 0, isTotal: true, isSub: true },
      { id: "nca_hdr", name: "Non-Current Assets", amount: null, level: 0, isHeader: true },
      { id: "ppe", name: "Property, Plant & Equipment (net)", amount: ppe, level: 1 },
      { id: "intangibles", name: "Intangible Assets & Goodwill", amount: intangibles, level: 1 },
      { id: "other_lt_a", name: "Other Long-Term Assets", amount: otherLT, level: 1 },
      { id: "total_assets", name: "Total Assets", amount: totalAssets, level: 0, isTotal: true, bold: true, isSub: true },
      { id: "liab_hdr", name: "Liabilities", amount: null, level: 0, isHeader: true },
      { id: "cl_hdr", name: "Current Liabilities", amount: null, level: 0, isHeader: true },
      { id: "ap", name: "Accounts Payable", amount: ap, level: 1 },
      { id: "accrued", name: "Accrued Expenses", amount: accrued, level: 1 },
      { id: "deferred_rev", name: "Deferred Revenue", amount: deferredRev, level: 1 },
      { id: "cl_total", name: "Total Current Liabilities", amount: currentLiab, level: 0, isTotal: true, isSub: true },
      { id: "ncl_hdr", name: "Non-Current Liabilities", amount: null, level: 0, isHeader: true },
      { id: "lt_debt", name: "Long-Term Debt", amount: ltDebt, level: 1 },
      { id: "other_lt_l", name: "Other Long-Term Liabilities", amount: otherLTLiab, level: 1 },
      { id: "total_liab", name: "Total Liabilities", amount: totalLiab, level: 0, isTotal: true, bold: true, isSub: true },
      { id: "equity_hdr", name: "Shareholders\u2019 Equity", amount: null, level: 0, isHeader: true },
      { id: "equity", name: "Total Equity", amount: equity, level: 0, isTotal: true, bold: true },
      { id: "total_le", name: "Total Liabilities & Equity", amount: totalAssets, level: 0, isTotal: true, bold: true, isFinal: true },
    ],
    metadata: { entity, quarter, segment, periodType: isActual(quarter) ? "actual" : "forecast", statement: "balance_sheet" }
  };
}

function generateSOCF(entity="meridian", quarter="2025-Q4", segment=null) {
  const rng = seed("socf"+entity+quarter+(segment||"total"));
  const base = entity === "meridian" ? 14500000 : 10000000;
  const scale = segment ? 0.2 + rng()*0.15 : 1;
  const qIdx = QUARTERS.indexOf(quarter);
  const growth = 1 + (qIdx * 0.008);
  const rev = base * scale * growth;

  const netIncome = Math.round(rev * (0.04 + rng()*0.03));
  const da = Math.round(rev * (0.02 + rng()*0.005));
  const wcChange = Math.round(rev * (-0.02 + rng()*0.04));
  const deferredRevChange = Math.round(rev * (-0.005 + rng()*0.015));
  const otherOps = Math.round(rev * (-0.005 + rng()*0.01));
  const opsCF = netIncome + da + wcChange + deferredRevChange + otherOps;

  const capex = -Math.round(rev * (0.02 + rng()*0.015));
  const acquisitions = qIdx > 6 ? -Math.round(rev * rng()*0.05) : 0;
  const otherInv = -Math.round(rev * rng()*0.005);
  const invCF = capex + acquisitions + otherInv;

  const debtChange = Math.round(rev * (-0.01 + rng()*0.03));
  const dividends = -Math.round(rev * (0.005 + rng()*0.005));
  const otherFin = Math.round(rev * (-0.002 + rng()*0.004));
  const finCF = debtChange + dividends + otherFin;

  const netChange = opsCF + invCF + finCF;

  return {
    lines: [
      { id: "ops_hdr", name: "Operating Activities", amount: null, level: 0, isHeader: true },
      { id: "net_income", name: "Net Income", amount: netIncome, level: 1 },
      { id: "da_add", name: "Depreciation & Amortization", amount: da, level: 1 },
      { id: "wc_change", name: "Changes in Working Capital", amount: wcChange, level: 1 },
      { id: "def_rev_chg", name: "Change in Deferred Revenue", amount: deferredRevChange, level: 1 },
      { id: "other_ops", name: "Other Operating Adjustments", amount: otherOps, level: 1 },
      { id: "ops_total", name: "Net Cash from Operations", amount: opsCF, level: 0, isTotal: true, bold: true, isSub: true },
      { id: "inv_hdr", name: "Investing Activities", amount: null, level: 0, isHeader: true },
      { id: "capex", name: "Capital Expenditures", amount: capex, level: 1 },
      { id: "acquisitions", name: "Acquisitions", amount: acquisitions, level: 1 },
      { id: "other_inv", name: "Other Investing", amount: otherInv, level: 1 },
      { id: "inv_total", name: "Net Cash from Investing", amount: invCF, level: 0, isTotal: true, bold: true, isSub: true },
      { id: "fin_hdr", name: "Financing Activities", amount: null, level: 0, isHeader: true },
      { id: "debt_change", name: "Net Borrowings / (Repayments)", amount: debtChange, level: 1 },
      { id: "dividends", name: "Dividends Paid", amount: dividends, level: 1 },
      { id: "other_fin", name: "Other Financing", amount: otherFin, level: 1 },
      { id: "fin_total", name: "Net Cash from Financing", amount: finCF, level: 0, isTotal: true, bold: true, isSub: true },
      { id: "net_change", name: "Net Change in Cash", amount: netChange, level: 0, isTotal: true, bold: true, isFinal: true },
    ],
    metadata: { entity, quarter, segment, periodType: isActual(quarter) ? "actual" : "forecast", statement: "cash_flow" }
  };
}

const REPS = {
  "NA": ["James Wilson","Maria Garcia","David Kim","Lisa Chen","Robert Taylor","Jennifer Lee","Michael Brown","Sarah Johnson","Alex Rivera","Tom Mitchell"],
  "EMEA": ["Sarah Chen","Hans Mueller","Emma Thompson","Pierre Dubois","Anna Kowalski","Marco Rossi","Olga Petrova","Lars Andersen","Fatima Hassan","Isabel Santos"],
  "APAC": ["Raj Patel","Yuki Tanaka","Wei Zhang","Priya Sharma","Kenji Watanabe","Min-Ji Park","Arjun Nair","Mei Lin","Sato Hiroshi","Deepa Krishnan"]
};

function generateDrillThrough(level, parent, quarter="2025-Q1") {
  const rng = seed(level+String(parent)+quarter);
  if (level === "region") {
    const total = generatePL("meridian", quarter).lines.find(l=>l.id==="rev").amount;
    const splits = [0.45, 0.32, 0.23];
    return REGIONS.map((r,i) => ({ name: r, revenue: Math.round(total * splits[i] * (0.95+rng()*0.1)), children: true }));
  }
  if (level === "rep") {
    const reps = REPS[parent] || REPS["NA"];
    const regionRev = Math.round(14500000 * (parent==="NA"?0.45:parent==="EMEA"?0.32:0.23));
    return reps.slice(0,4+Math.floor(rng()*4)).map((name,i) => {
      const share = (0.15 + rng()*0.2) / (i+1);
      return { name, revenue: Math.round(regionRev * share * (0.9+rng()*0.2)), customers: 8+Math.floor(rng()*15), children: true };
    }).sort((a,b) => b.revenue - a.revenue);
  }
  if (level === "customer") {
    const customers = ["GlobalBank Corp","DataFlow Systems","Apex Financial","Vantage Health","Atlas Energy","NovaPay Inc","TrueNorth Analytics","PrimeRetail Group","CloudScale Labs","Meridian Healthcare","Redline Logistics","FinEdge Capital","TechVault Inc","GreenField Ops","Summit Partners"];
    const repRev = 2000000 + Math.floor(rng() * 3000000);
    return customers.slice(0,5+Math.floor(rng()*6)).map((name,i) => {
      const share = (0.12 + rng()*0.18) / (i*0.5+1);
      return { name, revenue: Math.round(repRev * share * (0.8+rng()*0.4)), projects: 1+Math.floor(rng()*4), children: true };
    }).sort((a,b) => b.revenue - a.revenue);
  }
  if (level === "project") {
    const types = ["Digital Transformation","Risk Assessment","Cloud Migration","Process Optimization","Data Strategy","Compliance Review","Cost Reduction","Tech Architecture","M&A Integration","Ops Excellence"];
    const custRev = 500000 + Math.floor(rng() * 1500000);
    const count = 1 + Math.floor(rng()*4);
    return types.slice(0,count).map((type,i) => {
      const pId = `PRJ-${100+Math.floor(rng()*900)}`;
      const share = 1/count * (0.7 + rng()*0.6);
      return { name: `${pId} ${type}`, revenue: Math.round(custRev * share), children: false };
    }).sort((a,b) => b.revenue - a.revenue);
  }
  return [];
}

function generateReconReport() {
  const statements = ["Income Statement","Balance Sheet","Cash Flow"];
  const checks = [];
  let totalGreen = 0, totalRed = 0;
  statements.forEach(stmt => {
    const lineCount = stmt === "Income Statement" ? 20 : stmt === "Balance Sheet" ? 15 : 8;
    const dimChecks = lineCount * 4;
    QUARTERS.slice(0,8).forEach(q => {
      const green = lineCount + dimChecks;
      totalGreen += green;
      checks.push({ statement: stmt, period: q, total: green, green, red: 0 });
    });
  });
  return { checks, totalChecks: totalGreen + totalRed, totalGreen, totalRed, timestamp: new Date().toISOString() };
}

// ============================================================
// FORMATTING
// ============================================================
function fmt(n, isPercent=false) {
  if (n === null || n === undefined) return "";
  if (isPercent) return (n*100).toFixed(1) + "%";
  const abs = Math.abs(n);
  const formatted = abs >= 1000000 
    ? (abs/1000000).toFixed(1) + "M"
    : abs >= 1000 
    ? (abs/1000).toFixed(0) + "K"
    : abs.toFixed(0);
  return n < 0 ? `(${formatted})` : `$${formatted}`;
}

function fmtFull(n) {
  if (n === null || n === undefined) return "";
  const abs = Math.abs(n);
  const s = abs.toLocaleString("en-US", {minimumFractionDigits:0, maximumFractionDigits:0});
  return n < 0 ? `($${s})` : `$${s}`;
}

function variancePct(act, py) {
  if (!py || py === 0) return "—";
  const pct = ((act - py) / Math.abs(py)) * 100;
  return (pct >= 0 ? "+" : "") + pct.toFixed(1) + "%";
}

// ============================================================
// COMPONENTS
// ============================================================

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

function Select({ value, onChange, options, label, width=180 }) {
  return (
    <div style={{display:"flex",flexDirection:"column",gap:4}}>
      {label && <span style={{fontSize:11,color:COLORS.textMuted,letterSpacing:"0.05em",textTransform:"uppercase",fontFamily:"'JetBrains Mono',monospace"}}>{label}</span>}
      <select value={value} onChange={e=>onChange(e.target.value)} style={{
        width, padding:"8px 12px", background:COLORS.surface, color:COLORS.text, border:`1px solid ${COLORS.border}`,
        borderRadius:6, fontSize:13, fontFamily:"'IBM Plex Sans',sans-serif", cursor:"pointer", outline:"none",
        appearance:"none", backgroundImage:`url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%238B8F9E' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E")`,
        backgroundRepeat:"no-repeat", backgroundPosition:"right 10px center", paddingRight:30
      }}>
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </div>
  );
}

function TabBar({ tabs, active, onChange }) {
  return (
    <div style={{display:"flex",gap:2,borderBottom:`1px solid ${COLORS.border}`,marginBottom:20}}>
      {tabs.map(t => (
        <button key={t.id} onClick={()=>onChange(t.id)} style={{
          padding:"10px 20px", background: active===t.id ? COLORS.surface : "transparent",
          color: active===t.id ? COLORS.accent : COLORS.textMuted, border:"none", borderBottom: active===t.id ? `2px solid ${COLORS.accent}` : "2px solid transparent",
          cursor:"pointer", fontSize:13, fontFamily:"'IBM Plex Sans',sans-serif", fontWeight: active===t.id ? 600 : 400,
          transition:"all 0.15s", letterSpacing:"0.02em"
        }}>{t.label}</button>
      ))}
    </div>
  );
}

function StatementTable({ data, pyData, showVariance=true }) {
  if (!data) return null;
  return (
    <div style={{overflowX:"auto"}}>
      <table style={{width:"100%",borderCollapse:"collapse",fontFamily:"'IBM Plex Mono','JetBrains Mono',monospace",fontSize:13}}>
        <thead>
          <tr style={{borderBottom:`2px solid ${COLORS.accent}`}}>
            <th style={{textAlign:"left",padding:"10px 16px",color:COLORS.textMuted,fontWeight:500,width:"40%",fontSize:11,letterSpacing:"0.06em",textTransform:"uppercase"}}>Line Item</th>
            <th style={{textAlign:"right",padding:"10px 16px",color:COLORS.textMuted,fontWeight:500,fontSize:11,letterSpacing:"0.06em",textTransform:"uppercase"}}>
              {data.metadata.periodType === "forecast" ? "CF " : ""}{data.metadata.quarter}
            </th>
            {showVariance && pyData && <>
              <th style={{textAlign:"right",padding:"10px 16px",color:COLORS.textMuted,fontWeight:500,fontSize:11,letterSpacing:"0.06em",textTransform:"uppercase"}}>PY</th>
              <th style={{textAlign:"right",padding:"10px 16px",color:COLORS.textMuted,fontWeight:500,fontSize:11,letterSpacing:"0.06em",textTransform:"uppercase"}}>Var $</th>
              <th style={{textAlign:"right",padding:"10px 16px",color:COLORS.textMuted,fontWeight:500,fontSize:11,letterSpacing:"0.06em",textTransform:"uppercase"}}>Var %</th>
            </>}
          </tr>
        </thead>
        <tbody>
          {data.lines.map((line, i) => {
            const pyLine = pyData?.lines?.[i];
            const varAmt = line.amount !== null && pyLine?.amount !== null ? line.amount - pyLine.amount : null;
            const isNeg = varAmt !== null && varAmt < 0;
            const rowBg = line.isTotal ? COLORS.totalBg : line.highlight ? COLORS.highlight : "transparent";
            return (
              <tr key={line.id} style={{
                borderBottom: line.isFinal ? `2px double ${COLORS.accent}` : line.isTotal ? `1px solid ${COLORS.borderLight}` : `1px solid ${COLORS.border}22`,
                background: rowBg
              }}>
                <td style={{
                  padding: line.isHeader ? "14px 16px 6px" : "8px 16px",
                  paddingLeft: line.level === 1 ? 40 : 16,
                  color: line.isHeader ? COLORS.accent : line.bold ? COLORS.text : line.isPercent ? COLORS.textMuted : COLORS.text,
                  fontWeight: line.bold || line.isHeader ? 600 : 400,
                  fontSize: line.isHeader ? 12 : 13,
                  letterSpacing: line.isHeader ? "0.06em" : "0",
                  textTransform: line.isHeader ? "uppercase" : "none",
                  fontFamily: "'IBM Plex Sans',sans-serif",
                  cursor: line.drillable ? "pointer" : "default"
                }}>
                  {line.drillable && <span style={{color:COLORS.accent,marginRight:6}}>▸</span>}
                  {line.name}
                  {line.highlight && <span style={{marginLeft:8,fontSize:10,color:COLORS.accent,background:"rgba(199,120,64,0.12)",padding:"2px 6px",borderRadius:3}}>SYNERGY</span>}
                </td>
                <td style={{textAlign:"right",padding:"8px 16px",color: line.isPercent ? COLORS.textMuted : COLORS.text, fontWeight: line.bold ? 600 : 400}}>
                  {line.isHeader ? "" : fmt(line.amount, line.isPercent)}
                  {data.metadata.periodType === "forecast" && !line.isHeader && !line.isPercent && 
                    <span style={{marginLeft:4,fontSize:9,color:COLORS.textDim}}>CF</span>}
                </td>
                {showVariance && pyData && <>
                  <td style={{textAlign:"right",padding:"8px 16px",color:COLORS.textMuted}}>
                    {line.isHeader ? "" : fmt(pyLine?.amount, line.isPercent)}
                  </td>
                  <td style={{textAlign:"right",padding:"8px 16px",color: varAmt === null ? COLORS.textDim : isNeg ? COLORS.red : COLORS.green}}>
                    {line.isHeader || line.isPercent || varAmt === null ? "" : fmt(varAmt)}
                  </td>
                  <td style={{textAlign:"right",padding:"8px 16px",color: varAmt === null ? COLORS.textDim : isNeg ? COLORS.red : COLORS.green}}>
                    {line.isHeader || line.isPercent || !pyLine?.amount ? "" : variancePct(line.amount, pyLine.amount)}
                  </td>
                </>}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function DrillThrough({ onClose }) {
  const [path, setPath] = useState([{ level: "region", parent: null, label: "Revenue" }]);
  const current = path[path.length - 1];
  const data = useMemo(() => generateDrillThrough(current.level, current.parent), [current.level, current.parent]);
  const total = data.reduce((s, d) => s + d.revenue, 0);

  function drillIn(item, nextLevel) {
    if (!item.children) return;
    const levels = { region: "rep", rep: "customer", customer: "project" };
    setPath([...path, { level: levels[current.level], parent: item.name, label: item.name }]);
  }

  return (
    <div style={{background:COLORS.surface,borderRadius:8,border:`1px solid ${COLORS.border}`,overflow:"hidden"}}>
      <div style={{padding:"16px 20px",borderBottom:`1px solid ${COLORS.border}`,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
        <div style={{display:"flex",alignItems:"center",gap:8}}>
          <span style={{fontSize:14,fontWeight:600,color:COLORS.text,fontFamily:"'IBM Plex Sans',sans-serif"}}>Revenue Drill-Through</span>
          <div style={{display:"flex",gap:4,marginLeft:12}}>
            {path.map((p,i) => (
              <span key={i} style={{display:"flex",alignItems:"center",gap:4}}>
                {i > 0 && <span style={{color:COLORS.textDim}}>›</span>}
                <button onClick={()=>setPath(path.slice(0,i+1))} style={{
                  background: i === path.length-1 ? "rgba(199,120,64,0.12)" : "transparent",
                  color: i === path.length-1 ? COLORS.accent : COLORS.textMuted,
                  border:"none",cursor:"pointer",padding:"3px 8px",borderRadius:4,fontSize:12,
                  fontFamily:"'IBM Plex Sans',sans-serif"
                }}>{p.label}</button>
              </span>
            ))}
          </div>
        </div>
        <button onClick={onClose} style={{background:"transparent",border:"none",color:COLORS.textMuted,cursor:"pointer",fontSize:16}}>✕</button>
      </div>
      <div style={{padding:"0 4px"}}>
        <table style={{width:"100%",borderCollapse:"collapse",fontFamily:"'IBM Plex Mono',monospace",fontSize:13}}>
          <thead>
            <tr style={{borderBottom:`1px solid ${COLORS.border}`}}>
              <th style={{textAlign:"left",padding:"10px 16px",color:COLORS.textMuted,fontWeight:500,fontSize:11,letterSpacing:"0.06em",textTransform:"uppercase"}}>
                {current.level === "region" ? "Region" : current.level === "rep" ? "Rep" : current.level === "customer" ? "Customer" : "Project"}
              </th>
              <th style={{textAlign:"right",padding:"10px 16px",color:COLORS.textMuted,fontWeight:500,fontSize:11,letterSpacing:"0.06em",textTransform:"uppercase"}}>Revenue</th>
              <th style={{textAlign:"right",padding:"10px 16px",color:COLORS.textMuted,fontWeight:500,fontSize:11,letterSpacing:"0.06em",textTransform:"uppercase"}}>% of Total</th>
              {current.level === "rep" && <th style={{textAlign:"right",padding:"10px 16px",color:COLORS.textMuted,fontWeight:500,fontSize:11,letterSpacing:"0.06em",textTransform:"uppercase"}}>Clients</th>}
              {current.level === "customer" && <th style={{textAlign:"right",padding:"10px 16px",color:COLORS.textMuted,fontWeight:500,fontSize:11,letterSpacing:"0.06em",textTransform:"uppercase"}}>Projects</th>}
            </tr>
          </thead>
          <tbody>
            {data.map((item, i) => (
              <tr key={i} onClick={()=>item.children && drillIn(item)} style={{
                borderBottom:`1px solid ${COLORS.border}22`,cursor:item.children?"pointer":"default",
                transition:"background 0.1s"
              }} onMouseEnter={e=>{if(item.children)e.currentTarget.style.background=COLORS.surfaceHover}}
                 onMouseLeave={e=>{e.currentTarget.style.background="transparent"}}>
                <td style={{padding:"10px 16px",color:COLORS.text,fontFamily:"'IBM Plex Sans',sans-serif"}}>
                  {item.children && <span style={{color:COLORS.accent,marginRight:8}}>▸</span>}
                  {item.name}
                </td>
                <td style={{textAlign:"right",padding:"10px 16px",color:COLORS.text}}>{fmtFull(item.revenue)}</td>
                <td style={{textAlign:"right",padding:"10px 16px",color:COLORS.textMuted}}>{(item.revenue/total*100).toFixed(1)}%</td>
                {current.level === "rep" && <td style={{textAlign:"right",padding:"10px 16px",color:COLORS.textMuted}}>{item.customers}</td>}
                {current.level === "customer" && <td style={{textAlign:"right",padding:"10px 16px",color:COLORS.textMuted}}>{item.projects}</td>}
              </tr>
            ))}
            <tr style={{borderTop:`2px solid ${COLORS.accent}`,background:COLORS.totalBg}}>
              <td style={{padding:"10px 16px",fontWeight:600,color:COLORS.text,fontFamily:"'IBM Plex Sans',sans-serif"}}>Total</td>
              <td style={{textAlign:"right",padding:"10px 16px",fontWeight:600,color:COLORS.text}}>{fmtFull(total)}</td>
              <td style={{textAlign:"right",padding:"10px 16px",color:COLORS.textMuted}}>100.0%</td>
              {(current.level === "rep" || current.level === "customer") && <td></td>}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ReconView() {
  const recon = useMemo(() => generateReconReport(), []);
  return (
    <div>
      <div style={{display:"flex",gap:24,marginBottom:24}}>
        <div style={{background:recon.totalRed===0?COLORS.greenBg:COLORS.redBg,border:`1px solid ${recon.totalRed===0?COLORS.green:COLORS.red}33`,borderRadius:8,padding:"16px 24px",flex:1}}>
          <div style={{fontSize:32,fontWeight:700,color:recon.totalRed===0?COLORS.green:COLORS.red,fontFamily:"'IBM Plex Mono',monospace"}}>{recon.totalRed === 0 ? "PASS" : "FAIL"}</div>
          <div style={{fontSize:13,color:COLORS.textMuted,marginTop:4}}>{recon.totalChecks.toLocaleString()} checks</div>
        </div>
        <div style={{background:COLORS.surface,border:`1px solid ${COLORS.border}`,borderRadius:8,padding:"16px 24px",flex:1}}>
          <div style={{fontSize:32,fontWeight:700,color:COLORS.green,fontFamily:"'IBM Plex Mono',monospace"}}>{recon.totalGreen.toLocaleString()}</div>
          <div style={{fontSize:13,color:COLORS.textMuted,marginTop:4}}>GREEN (matched)</div>
        </div>
        <div style={{background:COLORS.surface,border:`1px solid ${COLORS.border}`,borderRadius:8,padding:"16px 24px",flex:1}}>
          <div style={{fontSize:32,fontWeight:700,color:recon.totalRed>0?COLORS.red:COLORS.textDim,fontFamily:"'IBM Plex Mono',monospace"}}>{recon.totalRed}</div>
          <div style={{fontSize:13,color:COLORS.textMuted,marginTop:4}}>RED (variance)</div>
        </div>
      </div>
      <table style={{width:"100%",borderCollapse:"collapse",fontFamily:"'IBM Plex Mono',monospace",fontSize:13}}>
        <thead>
          <tr style={{borderBottom:`2px solid ${COLORS.accent}`}}>
            <th style={{textAlign:"left",padding:"8px 16px",color:COLORS.textMuted,fontSize:11,letterSpacing:"0.06em",textTransform:"uppercase"}}>Statement</th>
            <th style={{textAlign:"left",padding:"8px 16px",color:COLORS.textMuted,fontSize:11,letterSpacing:"0.06em",textTransform:"uppercase"}}>Period</th>
            <th style={{textAlign:"right",padding:"8px 16px",color:COLORS.textMuted,fontSize:11,letterSpacing:"0.06em",textTransform:"uppercase"}}>Checks</th>
            <th style={{textAlign:"right",padding:"8px 16px",color:COLORS.textMuted,fontSize:11,letterSpacing:"0.06em",textTransform:"uppercase"}}>Green</th>
            <th style={{textAlign:"right",padding:"8px 16px",color:COLORS.textMuted,fontSize:11,letterSpacing:"0.06em",textTransform:"uppercase"}}>Red</th>
            <th style={{textAlign:"center",padding:"8px 16px",color:COLORS.textMuted,fontSize:11,letterSpacing:"0.06em",textTransform:"uppercase"}}>Status</th>
          </tr>
        </thead>
        <tbody>
          {recon.checks.map((c, i) => (
            <tr key={i} style={{borderBottom:`1px solid ${COLORS.border}22`}}>
              <td style={{padding:"8px 16px",color:COLORS.text,fontFamily:"'IBM Plex Sans',sans-serif"}}>{c.statement}</td>
              <td style={{padding:"8px 16px",color:COLORS.textMuted}}>{c.period}</td>
              <td style={{textAlign:"right",padding:"8px 16px",color:COLORS.textMuted}}>{c.total}</td>
              <td style={{textAlign:"right",padding:"8px 16px",color:COLORS.green}}>{c.green}</td>
              <td style={{textAlign:"right",padding:"8px 16px",color:c.red>0?COLORS.red:COLORS.textDim}}>{c.red}</td>
              <td style={{textAlign:"center",padding:"8px 16px"}}>
                <span style={{fontSize:11,padding:"3px 10px",borderRadius:4,fontWeight:600,
                  background:c.red===0?COLORS.greenBg:COLORS.redBg,color:c.red===0?COLORS.green:COLORS.red
                }}>{c.red===0?"PASS":"FAIL"}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ============================================================
// MAIN APP
// ============================================================
export default function ReportPortal() {
  const [tab, setTab] = useState("pl");
  const [variant, setVariant] = useState("act_vs_py");
  const [quarter, setQuarter] = useState("2025-Q3");
  const [segment, setSegment] = useState("all");
  const [showDrill, setShowDrill] = useState(false);

  const actQuarters = QUARTERS.filter(isActual);
  const cfQuarters = QUARTERS.filter(q => !isActual(q) && q.startsWith(String(wallClockDate().getFullYear())));
  const lastFullYear = wallClockDate().getFullYear() - 1;
  const pyYear = lastFullYear - 1;

  // Reset variant when switching tabs (BS has fewer options)
  const handleTabChange = useCallback((t) => {
    setTab(t);
    if (t === "bs" && variant !== "act_vs_py" && variant !== "quarterly") {
      setVariant("act_vs_py");
    }
    if (t === "drill") setShowDrill(true);
  }, [variant]);

  const statementTabs = [
    { id: "pl", label: "Income Statement" },
    { id: "bs", label: "Balance Sheet" },
    { id: "cf", label: "Cash Flow" },
    { id: "drill", label: "Revenue Drill-Through" },
    { id: "recon", label: "Reconciliation" },
  ];

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
    ? cfQuarters.map(q => ({ value: q, label: q }))
    : actQuarters.map(q => ({ value: q, label: q }));

  const seg = segment === "all" ? null : segment;

  // Pick the right generator based on active tab
  const genFn = tab === "bs" ? generateBS : tab === "cf" ? generateSOCF : generatePL;
  
  const currentData = useMemo(() => {
    if (variant === "act_vs_py") return genFn("meridian", `${lastFullYear}-Q4`, seg);
    if (variant === "q_act_vs_py") return genFn("meridian", quarter, seg);
    if (variant === "cf_vs_py") return genFn("meridian", `${wallClockDate().getFullYear()}-Q2`, seg);
    if (variant === "q_cf_vs_py") return genFn("meridian", quarter || cfQuarters[0], seg);
    if (variant === "quarterly") return genFn("meridian", quarter, seg);
    return genFn("meridian", `${lastFullYear}-Q4`, seg);
  }, [variant, quarter, seg, lastFullYear, genFn]);

  const pyData = useMemo(() => {
    if (variant === "quarterly") return null;
    if (variant === "act_vs_py") return genFn("meridian", `${pyYear}-Q4`, seg);
    if (variant === "q_act_vs_py") { const [y,q] = quarter.split("-"); return genFn("meridian", `${parseInt(y)-1}-${q}`, seg); }
    if (variant === "cf_vs_py") return genFn("meridian", `${lastFullYear}-Q4`, seg);
    if (variant === "q_cf_vs_py") { const [y,q] = (quarter||cfQuarters[0]).split("-"); return genFn("meridian", `${parseInt(y)-1}-${q}`, seg); }
    return null;
  }, [variant, quarter, seg, pyYear, lastFullYear, genFn]);

  return (
    <div style={{minHeight:"100vh",background:COLORS.bg,color:COLORS.text,fontFamily:"'IBM Plex Sans',sans-serif",padding:0}}>
      <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet"/>
      
      {/* Header */}
      <div style={{padding:"20px 32px",borderBottom:`1px solid ${COLORS.border}`,display:"flex",justifyContent:"space-between",alignItems:"center",background:COLORS.headerBg}}>
        <div style={{display:"flex",alignItems:"center",gap:16}}>
          <span style={{fontSize:18,fontWeight:700,color:COLORS.accent,letterSpacing:"-0.02em"}}>AOS</span>
          <span style={{color:COLORS.textDim}}>|</span>
          <span style={{fontSize:14,fontWeight:500,color:COLORS.text}}>Financial Report Portal</span>
          <span style={{fontSize:11,padding:"3px 10px",background:"rgba(199,120,64,0.12)",color:COLORS.accent,borderRadius:4,fontWeight:600}}>PHASE 0</span>
        </div>
        <div style={{fontSize:12,color:COLORS.textMuted}}>
          Meridian Partners • Single Entity • {wallClockDate().toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric"})}
        </div>
      </div>

      <div style={{padding:"24px 32px"}}>
        <TabBar tabs={statementTabs} active={tab} onChange={handleTabChange} />

        {tab !== "drill" && tab !== "recon" && (
          <div style={{display:"flex",gap:16,marginBottom:24,flexWrap:"wrap"}}>
            <Select label="Report Variant" value={variant} onChange={setVariant} options={variantOptions} width={220} />
            {showQuarterSelect && <Select label="Quarter" value={quarter} onChange={setQuarter} options={quarterOptions} width={140} />}
            <Select label="Segment" value={segment} onChange={setSegment} width={180} options={[
              {value:"all",label:"All Segments"},
              ...SEGMENTS.map(s=>({value:s,label:s}))
            ]} />
          </div>
        )}

        {tab !== "drill" && tab !== "recon" && (
          <div style={{background:COLORS.surface,borderRadius:8,border:`1px solid ${COLORS.border}`,overflow:"hidden"}}>
            <div style={{padding:"12px 20px",borderBottom:`1px solid ${COLORS.border}`,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
              <span style={{fontSize:14,fontWeight:600,color:COLORS.text}}>
                {tab==="pl"?"Income Statement":tab==="bs"?"Balance Sheet":"Statement of Cash Flows"}
              </span>
              <div style={{display:"flex",gap:12,alignItems:"center"}}>
                {currentData?.metadata?.periodType === "forecast" && 
                  <span style={{fontSize:11,padding:"3px 8px",background:"rgba(91,141,239,0.12)",color:COLORS.blue,borderRadius:4,fontWeight:600}}>CONTAINS FORECAST</span>
                }
                {segment !== "all" &&
                  <span style={{fontSize:11,padding:"3px 8px",background:"rgba(199,120,64,0.12)",color:COLORS.accent,borderRadius:4,fontWeight:600}}>FILTERED: {segment}</span>
                }
              </div>
            </div>
            <StatementTable data={currentData} pyData={pyData} showVariance={variant !== "quarterly"} />
          </div>
        )}

        {tab === "drill" && <DrillThrough onClose={()=>setTab("pl")} />}
        {tab === "recon" && <ReconView />}
      </div>
    </div>
  );
}
