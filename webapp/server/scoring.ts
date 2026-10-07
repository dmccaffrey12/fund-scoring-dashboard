import type { Fund } from "@shared/schema";

// ============================================================================
// METRIC DEFINITIONS (2025 Split System)
// ============================================================================

// Passive Fund Scoring — 10 metrics, 90 raw points normalized by available weight
export const PASSIVE_METRICS: { key: keyof Fund; colName: string; weight: number; higherBetter: boolean }[] = [
  { key: "netExpenseRatio", colName: "Net Expense Ratio", weight: 40, higherBetter: false },
  { key: "trackingError3Y", colName: "Tracking Error (vs Category) (3Y)", weight: 10, higherBetter: false },
  { key: "trackingError5Y", colName: "Tracking Error (vs Category) (5Y)", weight: 10, higherBetter: false },
  { key: "trackingError10Y", colName: "Tracking Error (vs Category) (10Y)", weight: 10, higherBetter: false },
  { key: "rSquared5Y", colName: "R-Squared (vs Category) (5Y)", weight: 5, higherBetter: true },
  { key: "shareClassAum", colName: "Share Class Assets Under Management", weight: 6, higherBetter: true },
  { key: "downside5Y", colName: "Downside (vs Category) (5Y)", weight: 3, higherBetter: false },
  { key: "downside10Y", colName: "Downside (vs Category) (10Y)", weight: 2, higherBetter: false },
  { key: "maxDrawdown5Y", colName: "Max Drawdown (5Y)", weight: 2, higherBetter: false },
  { key: "maxDrawdown10Y", colName: "Max Drawdown (10Y)", weight: 2, higherBetter: false },
];

// Active Fund Scoring — 16 metrics, 100 raw points normalized by available weight
export const ACTIVE_METRICS: { key: keyof Fund; colName: string; weight: number; higherBetter: boolean }[] = [
  { key: "netExpenseRatio", colName: "Net Expense Ratio", weight: 25, higherBetter: false },
  { key: "infoRatio3Y", colName: "Information Ratio (vs Category) (3Y)", weight: 10, higherBetter: true },
  { key: "infoRatio5Y", colName: "Information Ratio (vs Category) (5Y)", weight: 6, higherBetter: true },
  { key: "infoRatio10Y", colName: "Information Ratio (vs Category) (10Y)", weight: 4, higherBetter: true },
  { key: "sortino3Y", colName: "Historical Sortino (3Y)", weight: 10, higherBetter: true },
  { key: "sortino5Y", colName: "Historical Sortino (5Y)", weight: 6, higherBetter: true },
  { key: "sortino10Y", colName: "Historical Sortino (10Y)", weight: 4, higherBetter: true },
  { key: "maxDrawdown5Y", colName: "Max Drawdown (5Y)", weight: 7, higherBetter: false },
  { key: "maxDrawdown10Y", colName: "Max Drawdown (10Y)", weight: 3, higherBetter: false },
  { key: "downside5Y", colName: "Downside (vs Category) (5Y)", weight: 7, higherBetter: false },
  { key: "downside10Y", colName: "Downside (vs Category) (10Y)", weight: 3, higherBetter: false },
  { key: "returns3Y", colName: "3 Year Total Returns (Daily)", weight: 1, higherBetter: true },
  { key: "returns5Y", colName: "5 Year Total Returns (Daily)", weight: 1, higherBetter: true },
  { key: "returns10Y", colName: "10 Year Total Returns (Daily)", weight: 2, higherBetter: true },
  { key: "upside5Y", colName: "Upside (vs Category) (5Y)", weight: 6, higherBetter: true },
  { key: "upside10Y", colName: "Upside (vs Category) (10Y)", weight: 5, higherBetter: true },
];

// Passive multiplier: strictly 1.0 (no inflation factor)
export const PASSIVE_RESCALE = 1.0;

// ============================================================================
// METRIC DEFINITIONS (2023 Combined System)
// ============================================================================

export interface Metric2023Def {
  key: string;
  colName: string;
  weight: number;
  direction: "higher" | "lower";
}

export const SYSTEM_2023_METRICS: Metric2023Def[] = [
  { key: "ret_5y", colName: "Annualized 5 Year Total Returns (Monthly)", weight: 9, direction: "higher" },
  { key: "ret_10y", colName: "Annualized 10 Year Total Returns (Monthly)", weight: 9, direction: "higher" },
  { key: "alpha_5y", colName: "Alpha (vs Category) (5Y)", weight: 11, direction: "higher" },
  { key: "alpha_10y", colName: "Alpha (vs Category) (10Y)", weight: 11, direction: "higher" },
  { key: "maxdd_5y", colName: "Max Drawdown (5Y)", weight: 10, direction: "lower" },
  { key: "maxdd_10y", colName: "Max Drawdown (10Y)", weight: 10, direction: "lower" },
  { key: "up_5y", colName: "Upside (5Y)", weight: 5, direction: "higher" },
  { key: "up_10y", colName: "Upside (10Y)", weight: 6, direction: "higher" },
  { key: "dn_5y", colName: "Downside (5Y)", weight: 7, direction: "lower" },
  { key: "dn_10y", colName: "Downside (10Y)", weight: 7, direction: "lower" },
  { key: "med_tenure", colName: "Median Manager Tenure", weight: 3, direction: "higher" },
  { key: "avg_tenure", colName: "Average Manager Tenure", weight: 3, direction: "higher" },
  { key: "sc_aum", colName: "Share Class Assets Under Management", weight: 2.5, direction: "higher" },
  { key: "total_aum", colName: "Total Assets Under Management", weight: 1.5, direction: "higher" },
  { key: "expense", colName: "Annual Report Expense Ratio", weight: 5, direction: "lower" },
];

export const SYSTEM_2023_TOTAL_WEIGHT = SYSTEM_2023_METRICS.reduce((acc, m) => acc + m.weight, 0);

// ============================================================================
// CORE PERCENTILE ENGINE
// ============================================================================

/**
 * Calculate empirical percentile rank (0 to 1) for a value within category peers.
 * Matches Python calculate_percentile:
 *   higherBetter: (values <= v).sum() / n
 *   lowerBetter:  (values >= v).sum() / n
 * Handles singleton categories (n = 1 -> 1.0).
 */
export function percentileRank(
  value: number,
  categoryValues: number[],
  higherBetter: boolean
): number {
  const total = categoryValues.length;
  if (total === 0) return 0.5;

  let count = 0;
  if (higherBetter) {
    for (let i = 0; i < total; i++) {
      if (categoryValues[i] <= value) count++;
    }
  } else {
    for (let i = 0; i < total; i++) {
      if (categoryValues[i] >= value) count++;
    }
  }
  return count / total;
}

export function getScoreBand(score: number | null | undefined): "STRONG" | "REVIEW" | "WEAK" {
  if (score === null || score === undefined || isNaN(score)) return "WEAK";
  if (score >= 80) return "STRONG";
  if (score >= 60) return "REVIEW";
  return "WEAK";
}

// ============================================================================
// 2025 SYSTEM SCORING
// ============================================================================

export interface ScoredFundResult {
  id: number;
  symbol: string;
  name: string;
  categoryName: string | null;
  isIndexFund: boolean;
  scorePassive: number | null;
  scoreActive: number | null;
  score: number;
  scoreBand: "STRONG" | "REVIEW" | "WEAK";
  categoryPercentile: number;
  dataCoverage: number;
}

export function scoreAllFunds(allFunds: Fund[]): ScoredFundResult[] {
  // Group funds by category
  const categories = new Map<string, Fund[]>();
  for (const fund of allFunds) {
    const cat = fund.categoryName || "Uncategorized";
    if (!categories.has(cat)) categories.set(cat, []);
    categories.get(cat)!.push(fund);
  }

  // Pre-compute category metric arrays
  const categoryMetricValues = new Map<string, Map<string, number[]>>();

  for (const [cat, catFunds] of categories) {
    const metricMap = new Map<string, number[]>();
    const allMetricKeys = new Set<string>();

    for (const m of PASSIVE_METRICS) allMetricKeys.add(m.key);
    for (const m of ACTIVE_METRICS) allMetricKeys.add(m.key);

    for (const key of allMetricKeys) {
      const values: number[] = [];
      for (const f of catFunds) {
        const val = f[key as keyof Fund] as number | null;
        if (val !== null && val !== undefined && !isNaN(val)) {
          values.push(val);
        }
      }
      metricMap.set(key, values);
    }
    categoryMetricValues.set(cat, metricMap);
  }

  // Helper to compute weighted score for a given metric set
  function computeMetricSetScore(fund: Fund, metricSet: typeof PASSIVE_METRICS, rescale: number) {
    const cat = fund.categoryName || "Uncategorized";
    const metricMap = categoryMetricValues.get(cat)!;

    let weightedSum = 0;
    let availableWeight = 0;

    for (const metric of metricSet) {
      const value = fund[metric.key as keyof Fund] as number | null;
      if (value === null || value === undefined || isNaN(value)) continue;

      const categoryValues = metricMap.get(metric.key) || [];
      if (categoryValues.length === 0) continue;

      const pctile = percentileRank(value, categoryValues, metric.higherBetter);
      weightedSum += pctile * metric.weight;
      availableWeight += metric.weight;
    }

    if (availableWeight > 0) {
      const totalSystemWeight = metricSet.reduce((acc, m) => acc + m.weight, 0);
      const score = (weightedSum / availableWeight) * 100.0 * rescale;
      const coverage = availableWeight / totalSystemWeight;
      return { score, coverage };
    }
    return { score: null, coverage: 0 };
  }

  const results: ScoredFundResult[] = [];

  for (const fund of allFunds) {
    const passiveResult = computeMetricSetScore(fund, PASSIVE_METRICS, PASSIVE_RESCALE);
    const activeResult = computeMetricSetScore(fund, ACTIVE_METRICS, 1.0);

    const isPassive = Boolean(fund.isIndexFund);
    const finalScore = isPassive
      ? (passiveResult.score ?? 0)
      : (activeResult.score ?? 0);
    const coverage = isPassive ? passiveResult.coverage : activeResult.coverage;

    const scoreBand = getScoreBand(finalScore);

    results.push({
      id: fund.id,
      symbol: fund.symbol,
      name: fund.name,
      categoryName: fund.categoryName,
      isIndexFund: isPassive,
      scorePassive: passiveResult.score !== null ? passiveResult.score : null,
      scoreActive: activeResult.score !== null ? activeResult.score : null,
      score: finalScore,
      scoreBand,
      categoryPercentile: 0,
      dataCoverage: Math.round(coverage * 10000) / 10000,
    });
  }

  // Category percentile of final score
  const scoresByCategory = new Map<string, number[]>();
  for (let i = 0; i < allFunds.length; i++) {
    const cat = allFunds[i].categoryName || "Uncategorized";
    if (!scoresByCategory.has(cat)) scoresByCategory.set(cat, []);
    scoresByCategory.get(cat)!.push(results[i].score);
  }

  for (let i = 0; i < allFunds.length; i++) {
    const cat = allFunds[i].categoryName || "Uncategorized";
    const catScores = scoresByCategory.get(cat)!;
    const myScore = results[i].score;
    const belowOrEqual = catScores.filter(s => s <= myScore).length;
    results[i].categoryPercentile = Math.round((belowOrEqual / catScores.length) * 100 * 100) / 100;
  }

  return results;
}

// ============================================================================
// 2023 SYSTEM SCORING
// ============================================================================

export interface Scored2023Result {
  symbol: string;
  name: string;
  categoryName: string;
  score2023: number;
  availWeight: number;
  dataCoverage: number;
  scoreBand: "STRONG" | "REVIEW" | "WEAK";
}

export function score2023Funds(rows: Record<string, any>[]): Scored2023Result[] {
  // Group by category
  const categories = new Map<string, Record<string, any>[]>();
  for (const row of rows) {
    const cat = String(row["Category Name"] || "Uncategorized").trim();
    if (!categories.has(cat)) categories.set(cat, []);
    categories.get(cat)!.push(row);
  }

  // Pre-compute category metric values
  const catMetricValues = new Map<string, Map<string, number[]>>();
  for (const [cat, catRows] of categories) {
    const metricMap = new Map<string, number[]>();
    for (const m of SYSTEM_2023_METRICS) {
      const vals: number[] = [];
      for (const r of catRows) {
        const raw = r[m.colName];
        if (raw !== null && raw !== undefined && raw !== "") {
          const num = Number(raw);
          if (!isNaN(num)) vals.push(num);
        }
      }
      metricMap.set(m.key, vals);
    }
    catMetricValues.set(cat, metricMap);
  }

  const results: Scored2023Result[] = [];

  for (const row of rows) {
    const cat = String(row["Category Name"] || "Uncategorized").trim();
    const metricMap = catMetricValues.get(cat)!;

    let weightedSum = 0;
    let availableWeight = 0;

    for (const m of SYSTEM_2023_METRICS) {
      const raw = row[m.colName];
      if (raw === null || raw === undefined || raw === "") continue;
      const num = Number(raw);
      if (isNaN(num)) continue;

      const catVals = metricMap.get(m.key) || [];
      if (catVals.length === 0) continue;

      const higherBetter = m.direction === "higher";
      const pctile = percentileRank(num, catVals, higherBetter);
      weightedSum += pctile * m.weight;
      availableWeight += m.weight;
    }

    let score = 0;
    if (availableWeight > 0) {
      score = (weightedSum / availableWeight) * 100.0;
    }

    const availWeightPct = Math.round((availableWeight / SYSTEM_2023_TOTAL_WEIGHT * 100.0) * 100) / 100;

    results.push({
      symbol: String(row["Symbol"] || "").trim().toUpperCase(),
      name: String(row["Name"] || "").trim(),
      categoryName: cat,
      score2023: score,
      availWeight: availWeightPct,
      dataCoverage: Math.round((availableWeight / SYSTEM_2023_TOTAL_WEIGHT) * 10000) / 10000,
      scoreBand: getScoreBand(score),
    });
  }

  return results;
}

// ============================================================================
// DUAL-SCORE TABLE & MATRIX (2023 vs 2025)
// ============================================================================

export interface DualScoreRow {
  Symbol: string;
  Name: string;
  Category: string;
  Fund_Type: "Passive" | "Active";
  Score_2023_Final: number | null;
  Score_2025_Final: number | null;
  Score_Gap: number | null;
  Rank_2023: number | null;
  Rank_2025: number | null;
  Consensus_Rank: number | null;
  Score_Band_2023: "STRONG" | "REVIEW" | "WEAK" | null;
  Score_Band_2025: "STRONG" | "REVIEW" | "WEAK" | null;
  Quadrant: "Q1_Both_Strong" | "Q2_Only_2025" | "Q3_Only_2023" | "Q4_Both_Weak";
  Action_Flag: "LEAD" | "REVIEW" | "WATCH" | "DROP";
  Primary_Driver: string;
  Data_Coverage_2023: number | null;
  Data_Coverage_2025: number | null;
}

function denseRank(values: (number | null)[], descending = true): (number | null)[] {
  // Extract unique valid numbers
  const validVals = Array.from(new Set(values.filter((v): v is number => v !== null && !isNaN(v))));
  validVals.sort((a, b) => (descending ? b - a : a - b));

  const rankMap = new Map<number, number>();
  validVals.forEach((val, idx) => {
    rankMap.set(val, idx + 1);
  });

  return values.map(v => (v !== null && !isNaN(v) ? (rankMap.get(v) ?? null) : null));
}

export function classifyQuadrant(score2023: number | null, score2025: number | null): DualScoreRow["Quadrant"] {
  if (score2023 === null || score2025 === null) return "Q4_Both_Weak";
  const strong23 = score2023 >= 80;
  const strong25 = score2025 >= 80;
  if (strong23 && strong25) return "Q1_Both_Strong";
  if (strong25 && !strong23) return "Q2_Only_2025";
  if (strong23 && !strong25) return "Q3_Only_2023";
  return "Q4_Both_Weak";
}

export function classifyActionFlag(
  band2023: string | null,
  band2025: string | null
): DualScoreRow["Action_Flag"] {
  const b23 = band2023 || "WEAK";
  const b25 = band2025 || "WEAK";
  if (b23 === "STRONG" && b25 === "STRONG") return "LEAD";
  if (b23 === "STRONG" || b25 === "STRONG") return "REVIEW";
  if (b23 === "WEAK" && b25 === "WEAK") return "DROP";
  return "WATCH";
}

export function computePrimaryDriver(gap: number | null): string {
  if (gap === null || isNaN(gap)) return "UNKNOWN";
  if (gap >= 10) return "Upgraded by 2025 system";
  if (gap <= -10) return "Downgraded by 2025 system";
  return "Stable";
}

/**
 * Build the canonical Dual-Score Table matching Python dual_score_table.py
 */
export function buildDualScoreTable(
  scored2025: ScoredFundResult[],
  scored2023: Scored2023Result[],
  mode: "inner" | "outer" = "inner"
): DualScoreRow[] {
  // Deterministic deduplication by symbol for 2025 (highest score, then category, then original order)
  const deduped2025Map = new Map<string, ScoredFundResult>();
  const sorted2025 = [...scored2025].sort((a, b) => {
    if (a.symbol !== b.symbol) return a.symbol.localeCompare(b.symbol);
    if ((b.score ?? -1) !== (a.score ?? -1)) return (b.score ?? -1) - (a.score ?? -1);
    return (a.categoryName || "").localeCompare(b.categoryName || "");
  });
  for (const item of sorted2025) {
    const sym = item.symbol.toUpperCase();
    if (!deduped2025Map.has(sym)) {
      deduped2025Map.set(sym, item);
    }
  }

  // Deduplication for 2023
  const deduped2023Map = new Map<string, Scored2023Result>();
  const sorted2023 = [...scored2023].sort((a, b) => {
    if (a.symbol !== b.symbol) return a.symbol.localeCompare(b.symbol);
    if ((b.score2023 ?? -1) !== (a.score2023 ?? -1)) return (b.score2023 ?? -1) - (a.score2023 ?? -1);
    return (a.categoryName || "").localeCompare(b.categoryName || "");
  });
  for (const item of sorted2023) {
    const sym = item.symbol.toUpperCase();
    if (!deduped2023Map.has(sym)) {
      deduped2023Map.set(sym, item);
    }
  }

  // Determine symbols preserving 2023 input order (matching pandas inner merge)
  const orderedSymbols: string[] = [];
  const seenSymbols = new Set<string>();

  for (const item of scored2023) {
    const sym = item.symbol.toUpperCase();
    if (seenSymbols.has(sym)) continue;
    if (mode === "inner") {
      if (deduped2025Map.has(sym) && deduped2023Map.has(sym)) {
        orderedSymbols.push(sym);
        seenSymbols.add(sym);
      }
    } else {
      orderedSymbols.push(sym);
      seenSymbols.add(sym);
    }
  }

  if (mode === "outer") {
    for (const item of scored2025) {
      const sym = item.symbol.toUpperCase();
      if (!seenSymbols.has(sym)) {
        orderedSymbols.push(sym);
        seenSymbols.add(sym);
      }
    }
  }

  const joinedRows: Omit<DualScoreRow, "Rank_2023" | "Rank_2025" | "Consensus_Rank">[] = [];

  for (const sym of orderedSymbols) {
    const item25 = deduped2025Map.get(sym);
    const item23 = deduped2023Map.get(sym);

    const name = item25?.name || item23?.name || "Unknown";
    const category = item25?.categoryName || item23?.categoryName || "Uncategorized";
    const fundType: "Passive" | "Active" = item25?.isIndexFund ? "Passive" : "Active";

    const s23 = item23?.score2023 ?? null;
    const s25 = item25?.score ?? null;
    const gap = s23 !== null && s25 !== null ? s25 - s23 : null;

    const b23 = item23?.scoreBand ?? null;
    const b25 = item25?.scoreBand ?? null;

    const quadrant = classifyQuadrant(s23, s25);
    const actionFlag = classifyActionFlag(b23, b25);
    const primaryDriver = computePrimaryDriver(gap);

    joinedRows.push({
      Symbol: sym,
      Name: name,
      Category: category,
      Fund_Type: fundType,
      Score_2023_Final: s23,
      Score_2025_Final: s25,
      Score_Gap: gap,
      Score_Band_2023: b23,
      Score_Band_2025: b25,
      Quadrant: quadrant,
      Action_Flag: actionFlag,
      Primary_Driver: primaryDriver,
      Data_Coverage_2023: item23?.dataCoverage ?? null,
      Data_Coverage_2025: item25?.dataCoverage ?? null,
    });
  }

  // Dense Ranks
  const ranks2023 = denseRank(joinedRows.map(r => r.Score_2023_Final), true);
  const ranks2025 = denseRank(joinedRows.map(r => r.Score_2025_Final), true);

  const avgRanks = joinedRows.map((_, idx) => {
    const r23 = ranks2023[idx];
    const r25 = ranks2025[idx];
    if (r23 !== null && r25 !== null) return (r23 + r25) / 2.0;
    return null;
  });

  const consensusRanks = denseRank(avgRanks, false); // ascending: 1 = best average rank

  const mapped = joinedRows.map((row, idx) => ({
    ...row,
    Rank_2023: ranks2023[idx],
    Rank_2025: ranks2025[idx],
    Consensus_Rank: consensusRanks[idx],
  }));

  // Python dual_score_table.py: sort_values(["Consensus_Rank", "Symbol"], ascending=[True, True])
  return mapped.sort((a, b) => {
    const crA = a.Consensus_Rank ?? Number.MAX_SAFE_INTEGER;
    const crB = b.Consensus_Rank ?? Number.MAX_SAFE_INTEGER;
    if (crA !== crB) return crA - crB;
    return a.Symbol.localeCompare(b.Symbol);
  });
}

// ============================================================================
// FUND BREAKDOWN FOR RADAR CHART
// ============================================================================

export interface MetricBreakdownItem {
  metric: string;
  label: string;
  weight: number;
  value: number | null;
  percentile: number | null;
  categoryMedianPercentile: number;
  higherBetter: boolean;
}

export function getFundBreakdown(fund: Fund, categoryFunds: Fund[]): MetricBreakdownItem[] {
  const metrics = fund.isIndexFund ? PASSIVE_METRICS : ACTIVE_METRICS;

  const LABEL_MAP: Record<string, string> = {
    netExpenseRatio: "Expense Ratio",
    trackingError3Y: "Tracking Error (3Y)",
    trackingError5Y: "Tracking Error (5Y)",
    trackingError10Y: "Tracking Error (10Y)",
    rSquared5Y: "R-Squared (5Y)",
    shareClassAum: "AUM",
    downside5Y: "Downside (5Y)",
    downside10Y: "Downside (10Y)",
    maxDrawdown5Y: "Max Drawdown (5Y)",
    maxDrawdown10Y: "Max Drawdown (10Y)",
    infoRatio3Y: "Info Ratio (3Y)",
    infoRatio5Y: "Info Ratio (5Y)",
    infoRatio10Y: "Info Ratio (10Y)",
    sortino3Y: "Sortino (3Y)",
    sortino5Y: "Sortino (5Y)",
    sortino10Y: "Sortino (10Y)",
    upside3Y: "Upside (3Y)",
    upside5Y: "Upside (5Y)",
    upside10Y: "Upside (10Y)",
    returns3Y: "Total Return (3Y)",
    returns5Y: "Total Return (5Y)",
    returns10Y: "Total Return (10Y)",
  };

  return metrics.map(m => {
    const value = fund[m.key as keyof Fund] as number | null;
    const catValues = categoryFunds
      .map(f => f[m.key as keyof Fund] as number | null)
      .filter((v): v is number => v !== null && v !== undefined && !isNaN(v));

    let pctile: number | null = null;
    if (value !== null && value !== undefined && !isNaN(value) && catValues.length > 0) {
      pctile = Math.round(percentileRank(value, catValues, m.higherBetter) * 100);
    }

    return {
      metric: String(m.key),
      label: LABEL_MAP[String(m.key)] || String(m.key),
      weight: m.weight,
      value,
      percentile: pctile,
      categoryMedianPercentile: 50,
      higherBetter: m.higherBetter,
    };
  });
}
