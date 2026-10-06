import type { Fund } from "@shared/schema";
import { storage } from "./storage";
import { PASSIVE_METRICS, ACTIVE_METRICS, type DualScoreRow } from "./scoring";

export interface ReplacementCandidate {
  rank: number;
  symbol: string;
  name: string;
  category: string;
  fundType: "Passive" | "Active";
  score2023: number | null;
  score2025: number | null;
  scoreGap: number | null;
  consensusRank: number | null;
  rank2023: number | null;
  rank2025: number | null;
  scoreBand2023: string | null;
  scoreBand2025: string | null;
  quadrant: string | null;
  actionFlag: string | null;
  primaryDriver: string | null;
  netExpenseRatio: number | null;
  score2025Delta: number | null;
  score2023Delta: number | null;
  expenseDelta: number | null;
}

export interface ReplacementWorkbenchResult {
  currentHolding: {
    symbol: string;
    name: string;
    category: string;
    fundType: "Passive" | "Active";
    score2023: number | null;
    score2025: number | null;
    scoreGap: number | null;
    consensusRank: number | null;
    rank2023: number | null;
    rank2025: number | null;
    scoreBand2023: string | null;
    scoreBand2025: string | null;
    quadrant: string | null;
    actionFlag: string | null;
    primaryDriver: string | null;
    netExpenseRatio: number | null;
  };
  categoryPeerCount: number;
  candidates: ReplacementCandidate[];
}

export function buildReplacementWorkbench(
  ticker: string,
  topN: number = 10
): ReplacementWorkbenchResult | null {
  const symbol = ticker.trim().toUpperCase();
  const current = storage.getFundBySymbol(symbol);
  if (!current) return null;

  const category = current.categoryName || "Uncategorized";
  const peers = storage.getFundsByCategory(category);

  const currentHolding = {
    symbol: current.symbol,
    name: current.name,
    category,
    fundType: (current.isIndexFund ? "Passive" : "Active") as "Passive" | "Active",
    score2023: current.score2023 ?? null,
    score2025: current.score2025 ?? current.score ?? null,
    scoreGap: current.scoreGap ?? null,
    consensusRank: current.consensusRank ?? null,
    rank2023: current.rank2023 ?? null,
    rank2025: current.rank2025 ?? null,
    scoreBand2023: current.scoreBand2023 ?? null,
    scoreBand2025: current.scoreBand2025 ?? current.scoreBand ?? null,
    quadrant: current.quadrant ?? null,
    actionFlag: current.actionFlag ?? null,
    primaryDriver: current.primaryDriver ?? null,
    netExpenseRatio: current.netExpenseRatio ?? null,
  };

  // Exclude current holding and filter to candidates with a score
  const candidateFunds = peers
    .filter(f => f.symbol.toUpperCase() !== symbol && (f.score2025 !== null || f.score !== null))
    .sort((a, b) => {
      const crA = a.consensusRank ?? Number.MAX_SAFE_INTEGER;
      const crB = b.consensusRank ?? Number.MAX_SAFE_INTEGER;
      if (crA !== crB) return crA - crB;
      const sA = a.score2025 ?? a.score ?? -1;
      const sB = b.score2025 ?? b.score ?? -1;
      return sB - sA;
    });

  const candidates: ReplacementCandidate[] = candidateFunds.slice(0, topN).map((c, idx) => {
    const s23 = c.score2023 ?? null;
    const s25 = c.score2025 ?? c.score ?? null;
    const cur23 = currentHolding.score2023;
    const cur25 = currentHolding.score2025;
    const curExp = currentHolding.netExpenseRatio;
    const cExp = c.netExpenseRatio ?? null;

    return {
      rank: idx + 1,
      symbol: c.symbol,
      name: c.name,
      category,
      fundType: c.isIndexFund ? "Passive" : "Active",
      score2023: s23,
      score2025: s25,
      scoreGap: c.scoreGap ?? (s23 !== null && s25 !== null ? s25 - s23 : null),
      consensusRank: c.consensusRank ?? null,
      rank2023: c.rank2023 ?? null,
      rank2025: c.rank2025 ?? null,
      scoreBand2023: c.scoreBand2023 ?? null,
      scoreBand2025: c.scoreBand2025 ?? c.scoreBand ?? null,
      quadrant: c.quadrant ?? null,
      actionFlag: c.actionFlag ?? null,
      primaryDriver: c.primaryDriver ?? null,
      netExpenseRatio: cExp,
      score2025Delta: s25 !== null && cur25 !== null ? Math.round((s25 - cur25) * 10) / 10 : null,
      score2023Delta: s23 !== null && cur23 !== null ? Math.round((s23 - cur23) * 10) / 10 : null,
      expenseDelta: cExp !== null && curExp !== null ? Math.round((cExp - curExp) * 10000) / 10000 : null,
    };
  });

  return {
    currentHolding,
    categoryPeerCount: peers.length,
    candidates,
  };
}

export function renderReplacementBriefHtml(
  result: ReplacementWorkbenchResult,
  runDate: string = new Date().toISOString().split("T")[0]
): string {
  const { currentHolding, categoryPeerCount, candidates } = result;

  const esc = (val: any) => {
    if (val === null || val === undefined) return "—";
    const s = String(val);
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  };

  const fmtScore = (s: number | null) => (s !== null ? s.toFixed(1) : "—");
  const fmtExp = (e: number | null) => (e !== null ? `${(e * 100).toFixed(2)}%` : "—");
  const fmtDelta = (d: number | null, isExpense = false) => {
    if (d === null) return "—";
    if (isExpense) {
      const pct = (d * 100).toFixed(2);
      const color = d < 0 ? "#15803d" : d > 0 ? "#b91c1c" : "#475569";
      const sign = d > 0 ? "+" : "";
      return `<span style="color: ${color}; font-weight: 600;">${sign}${pct}%</span>`;
    }
    const color = d > 0 ? "#15803d" : d < 0 ? "#b91c1c" : "#475569";
    const sign = d > 0 ? "+" : "";
    return `<span style="color: ${color}; font-weight: 600;">${sign}${d.toFixed(1)}</span>`;
  };

  const getBadge = (flag: string | null) => {
    if (!flag) return "—";
    let bg = "#f1f5f9";
    let color = "#475569";
    if (flag === "LEAD" || flag === "Q1_Both_Strong") {
      bg = "#dcfce7";
      color = "#15803d";
    } else if (flag === "REVIEW" || flag === "Q2_Only_2025" || flag === "Q3_Only_2023") {
      bg = "#fef3c7";
      color = "#b45309";
    } else if (flag === "WATCH" || flag === "DROP" || flag === "Q4_Both_Weak") {
      bg = "#fee2e2";
      color = "#b91c1c";
    }
    return `<span style="display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 11px; font-weight: 600; background: ${bg}; color: ${color};">${esc(flag)}</span>`;
  };

  const candidateRows = candidates.map(c => `
    <tr>
      <td style="text-align: center; font-weight: 600;">${c.rank}</td>
      <td style="font-weight: 700; color: #1e3a8a;">${esc(c.symbol)}</td>
      <td>${esc(c.name)}</td>
      <td>${esc(c.fundType)}</td>
      <td style="text-align: right; font-weight: 600;">${fmtScore(c.score2025)}</td>
      <td style="text-align: right;">${fmtDelta(c.score2025Delta)}</td>
      <td style="text-align: right; font-weight: 600;">${fmtScore(c.score2023)}</td>
      <td style="text-align: right;">${fmtExp(c.netExpenseRatio)}</td>
      <td style="text-align: right;">${fmtDelta(c.expenseDelta, true)}</td>
      <td style="text-align: center;">${c.consensusRank ?? "—"}</td>
      <td style="text-align: center;">${getBadge(c.quadrant)}</td>
      <td style="text-align: center;">${getBadge(c.actionFlag)}</td>
    </tr>
  `).join("\n");

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>FundScore Replacement Brief — ${esc(currentHolding.symbol)}</title>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      margin: 24px;
      color: #1e293b;
      background: #ffffff;
      line-height: 1.4;
    }
    .header {
      border-bottom: 2px solid #0f172a;
      padding-bottom: 12px;
      margin-bottom: 20px;
    }
    .header h1 {
      margin: 0 0 6px 0;
      font-size: 22px;
      color: #0f172a;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .header .meta {
      font-size: 12px;
      color: #64748b;
      margin: 0;
    }
    .card {
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 16px;
      margin-bottom: 20px;
    }
    .card h2 {
      margin: 0 0 12px 0;
      font-size: 15px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #334155;
    }
    .profile-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
    }
    .profile-item {
      font-size: 12px;
    }
    .profile-item .label {
      color: #64748b;
      margin-bottom: 2px;
      font-size: 11px;
      text-transform: uppercase;
    }
    .profile-item .val {
      font-weight: 600;
      font-size: 14px;
      color: #0f172a;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
      margin-top: 12px;
    }
    th {
      background: #0f172a;
      color: #ffffff;
      text-align: left;
      padding: 8px;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    td {
      padding: 8px;
      border-bottom: 1px solid #e2e8f0;
    }
    tr:nth-child(even) {
      background: #f8fafc;
    }
    .footer {
      margin-top: 24px;
      padding-top: 12px;
      border-top: 1px solid #e2e8f0;
      font-size: 11px;
      color: #64748b;
      display: flex;
      justify-content: space-between;
    }
    @media print {
      body { margin: 10mm; }
      .no-print { display: none; }
      @page { size: landscape; margin: 10mm; }
    }
  </style>
</head>
<body>
  <div class="header">
    <div style="float: right;" class="no-print">
      <button onclick="window.print()" style="padding: 6px 14px; background: #0f172a; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; font-weight: 600;">
        Print / Save to PDF
      </button>
    </div>
    <h1>FundScore Committee Brief — Candidate Replacement Analysis</h1>
    <p class="meta">Target Holding: <strong>${esc(currentHolding.symbol)}</strong> (${esc(currentHolding.name)}) · Category: <strong>${esc(currentHolding.category)}</strong> (${categoryPeerCount} peers) · Run Date: ${esc(runDate)}</p>
  </div>

  <div class="card">
    <h2>Current Holding Profile</h2>
    <div class="profile-grid">
      <div class="profile-item"><div class="label">Symbol</div><div class="val">${esc(currentHolding.symbol)}</div></div>
      <div class="profile-item"><div class="label">Fund Type</div><div class="val">${esc(currentHolding.fundType)}</div></div>
      <div class="profile-item"><div class="label">2025 Score</div><div class="val">${fmtScore(currentHolding.score2025)}</div></div>
      <div class="profile-item"><div class="label">2023 Score</div><div class="val">${fmtScore(currentHolding.score2023)}</div></div>
      <div class="profile-item"><div class="label">Expense Ratio</div><div class="val">${fmtExp(currentHolding.netExpenseRatio)}</div></div>
      <div class="profile-item"><div class="label">Consensus Rank</div><div class="val">${currentHolding.consensusRank ?? "—"}</div></div>
      <div class="profile-item"><div class="label">Quadrant</div><div class="val">${getBadge(currentHolding.quadrant)}</div></div>
      <div class="profile-item"><div class="label">Action Flag</div><div class="val">${getBadge(currentHolding.actionFlag)}</div></div>
    </div>
  </div>

  <div class="card">
    <h2>Top Same-Category Replacement Candidates</h2>
    <p style="margin: 0 0 10px 0; font-size: 12px; color: #64748b;">
      Ranked by consensus dual-lens score within the <strong>${esc(currentHolding.category)}</strong> peer universe.
    </p>
    <table>
      <thead>
        <tr>
          <th style="text-align: center;">#</th>
          <th>Symbol</th>
          <th>Name</th>
          <th>Type</th>
          <th style="text-align: right;">2025 Score</th>
          <th style="text-align: right;">2025 &Delta;</th>
          <th style="text-align: right;">2023 Score</th>
          <th style="text-align: right;">Expense</th>
          <th style="text-align: right;">Exp &Delta;</th>
          <th style="text-align: center;">Cons. Rank</th>
          <th style="text-align: center;">Quadrant</th>
          <th style="text-align: center;">Action</th>
        </tr>
      </thead>
      <tbody>
        ${candidateRows}
      </tbody>
    </table>
  </div>

  <div class="footer">
    <div>FundScore Investment Research & Committee Modernization Suite</div>
    <div>Dual-Scoring Methodology Parity Baseline · Confidential / Internal Use Only</div>
  </div>
</body>
</html>`;
}
