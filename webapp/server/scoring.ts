import type { Fund } from "@shared/schema";

// Passive Fund Scoring — 10 metrics, 90 points rescaled to 100
const PASSIVE_METRICS: { key: keyof Fund; weight: number; higherBetter: boolean }[] = [
  { key: "netExpenseRatio", weight: 40, higherBetter: false },
  { key: "trackingError3Y", weight: 10, higherBetter: false },
  { key: "trackingError5Y", weight: 10, higherBetter: false },
  { key: "trackingError10Y", weight: 10, higherBetter: false },
  { key: "rSquared5Y", weight: 5, higherBetter: true },
  { key: "shareClassAum", weight: 6, higherBetter: true },
  { key: "downside5Y", weight: 3, higherBetter: false },
  { key: "downside10Y", weight: 2, higherBetter: false },
  { key: "maxDrawdown5Y", weight: 2, higherBetter: false },
  { key: "maxDrawdown10Y", weight: 2, higherBetter: false },
];

// Active Fund Scoring — 16 metrics, 100 points
const ACTIVE_METRICS: { key: keyof Fund; weight: number; higherBetter: boolean }[] = [
  { key: "netExpenseRatio", weight: 25, higherBetter: false },
  { key: "infoRatio3Y", weight: 10, higherBetter: true },
  { key: "infoRatio5Y", weight: 6, higherBetter: true },
  { key: "infoRatio10Y", weight: 4, higherBetter: true },
  { key: "sortino3Y", weight: 10, higherBetter: true },
  { key: "sortino5Y", weight: 6, higherBetter: true },
  { key: "sortino10Y", weight: 4, higherBetter: true },
  { key: "maxDrawdown5Y", weight: 7, higherBetter: false },
  { key: "maxDrawdown10Y", weight: 3, higherBetter: false },
  { key: "downside5Y", weight: 7, higherBetter: false },
  { key: "downside10Y", weight: 3, higherBetter: false },
  { key: "returns3Y", weight: 1, higherBetter: true },
  { key: "returns5Y", weight: 1, higherBetter: true },
  { key: "returns10Y", weight: 2, higherBetter: true },
  { key: "upside5Y", weight: 6, higherBetter: true },
  { key: "upside10Y", weight: 5, higherBetter: true },
];

interface ScoredFund {
  id: number;
  score: number;
  scoreBand: string;
  categoryPercentile: number;
}

/**
 * Calculate percentile rank for a fund within its category peers.
 * higherBetter: count peers with value <= this fund / total with data
 * lowerBetter: count peers with value >= this fund / total with data
 */
function percentileRank(
  value: number,
  categoryValues: number[],
  higherBetter: boolean
): number {
  const total = categoryValues.length;
  if (total === 0) return 0.5;
  
  let count: number;
  if (higherBetter) {
    count = categoryValues.filter(v => v <= value).length;
  } else {
    count = categoryValues.filter(v => v >= value).length;
  }
  return count / total;
}

export function scoreAllFunds(allFunds: Fund[]): ScoredFund[] {
  // Group funds by category
  const categories = new Map<string, Fund[]>();
  for (const fund of allFunds) {
    const cat = fund.categoryName || "Uncategorized";
    if (!categories.has(cat)) categories.set(cat, []);
    categories.get(cat)!.push(fund);
  }

  // Pre-compute category metric arrays for percentile calculation
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

  const results: ScoredFund[] = [];

  for (const fund of allFunds) {
    const cat = fund.categoryName || "Uncategorized";
    const metricMap = categoryMetricValues.get(cat)!;
    const metrics = fund.isIndexFund ? PASSIVE_METRICS : ACTIVE_METRICS;
    const rescaleFactor = fund.isIndexFund ? (100 / 90) : 1;

    let weightedSum = 0;
    let availableWeight = 0;

    for (const metric of metrics) {
      const value = fund[metric.key as keyof Fund] as number | null;
      if (value === null || value === undefined || isNaN(value)) continue;

      const categoryValues = metricMap.get(metric.key) || [];
      if (categoryValues.length < 2) continue;

      const pctile = percentileRank(value, categoryValues, metric.higherBetter);
      weightedSum += pctile * metric.weight;
      availableWeight += metric.weight;
    }

    let score: number;
    if (availableWeight > 0) {
      score = (weightedSum / availableWeight) * 100 * rescaleFactor;
      // Cap at 100
      score = Math.min(100, Math.round(score * 100) / 100);
    } else {
      score = 0;
    }

    const scoreBand = score >= 80 ? "STRONG" : score >= 60 ? "REVIEW" : "WEAK";

    results.push({
      id: fund.id,
      score,
      scoreBand,
      categoryPercentile: 0, // Will be computed after all scores
    });
  }

  // Compute category percentiles based on scores
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

/**
 * Get component percentiles for a single fund (for the breakdown spider chart).
 */
export function getFundBreakdown(fund: Fund, categoryFunds: Fund[]): {
  metric: string;
  label: string;
  weight: number;
  value: number | null;
  percentile: number | null;
  higherBetter: boolean;
}[] {
  const metrics = fund.isIndexFund ? PASSIVE_METRICS : ACTIVE_METRICS;

  const LABEL_MAP: Record<string, string> = {
    netExpenseRatio: "Expense Ratio",
    trackingError3Y: "Tracking Error 3Y",
    trackingError5Y: "Tracking Error 5Y",
    trackingError10Y: "Tracking Error 10Y",
    rSquared5Y: "R-Squared 5Y",
    shareClassAum: "AUM",
    downside5Y: "Downside 5Y",
    downside10Y: "Downside 10Y",
    maxDrawdown5Y: "Max Drawdown 5Y",
    maxDrawdown10Y: "Max Drawdown 10Y",
    infoRatio3Y: "Info Ratio 3Y",
    infoRatio5Y: "Info Ratio 5Y",
    infoRatio10Y: "Info Ratio 10Y",
    sortino3Y: "Sortino 3Y",
    sortino5Y: "Sortino 5Y",
    sortino10Y: "Sortino 10Y",
    upside3Y: "Upside 3Y",
    upside5Y: "Upside 5Y",
    upside10Y: "Upside 10Y",
    returns3Y: "Returns 3Y",
    returns5Y: "Returns 5Y",
    returns10Y: "Returns 10Y",
  };

  return metrics.map(m => {
    const value = fund[m.key as keyof Fund] as number | null;
    const catValues = categoryFunds
      .map(f => f[m.key as keyof Fund] as number | null)
      .filter((v): v is number => v !== null && v !== undefined && !isNaN(v));

    let pctile: number | null = null;
    if (value !== null && value !== undefined && !isNaN(value) && catValues.length >= 2) {
      pctile = Math.round(percentileRank(value, catValues, m.higherBetter) * 100);
    }

    return {
      metric: m.key,
      label: LABEL_MAP[m.key] || m.key,
      weight: m.weight,
      value,
      percentile: pctile,
      higherBetter: m.higherBetter,
    };
  });
}
