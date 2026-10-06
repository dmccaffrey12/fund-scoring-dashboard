import Papa from "papaparse";
import fs from "fs";
import path from "path";

export interface Finding {
  severity: "error" | "warning" | "info";
  code: string;
  message: string;
  details?: Record<string, any>;
}

export interface ValidationReport {
  schema: "2025" | "2023";
  failed: boolean;
  rowCount: number;
  columnCount: number;
  columns: string[];
  errors: Finding[];
  warnings: Finding[];
  infos: Finding[];
}

export const REQUIRED_2025: string[] = [
  "Symbol",
  "Name",
  "Index Fund",
  "Category Name",
  "Net Expense Ratio",
  "R-Squared (vs Category) (5Y)",
  "Share Class Assets Under Management",
  "Max Drawdown (5Y)",
  "Max Drawdown (10Y)",
  "Information Ratio (vs Category) (3Y)",
  "Historical Sortino (3Y)",
  "Upside (vs Category) (5Y)",
  "Downside (vs Category) (5Y)",
  "3 Year Total Returns (Daily)",
  "5 Year Total Returns (Daily)",
  "10 Year Total Returns (Daily)",
];

export const CRITICAL_NUMERIC_2025: string[] = [
  "Net Expense Ratio",
  "Share Class Assets Under Management",
];

export const NUMERIC_2025: string[] = [
  "Tracking Error (vs Category) (3Y)",
  "Tracking Error (vs Category) (5Y)",
  "Tracking Error (vs Category) (10Y)",
  "R-Squared (vs Category) (5Y)",
  "Downside (vs Category) (5Y)",
  "Downside (vs Category) (10Y)",
  "Max Drawdown (5Y)",
  "Max Drawdown (10Y)",
  "Information Ratio (vs Category) (3Y)",
  "Information Ratio (vs Category) (5Y)",
  "Information Ratio (vs Category) (10Y)",
  "Historical Sortino (3Y)",
  "Historical Sortino (5Y)",
  "Historical Sortino (10Y)",
  "Upside (vs Category) (3Y)",
  "Upside (vs Category) (5Y)",
  "Upside (vs Category) (10Y)",
  "3 Year Total Returns (Daily)",
  "5 Year Total Returns (Daily)",
  "10 Year Total Returns (Daily)",
];

export const REQUIRED_2023: string[] = [
  "Symbol",
  "Name",
  "Category Name",
  "R-Squared (vs Category) (5Y)",
  "Max Drawdown (5Y)",
  "Max Drawdown (10Y)",
  "Share Class Assets Under Management",
  "Annual Report Expense Ratio",
];

export const CRITICAL_NUMERIC_2023: string[] = [
  "Annual Report Expense Ratio",
  "Share Class Assets Under Management",
];

export const NUMERIC_2023: string[] = [
  "3 Year Total NAV Returns Category Rank",
  "5 Year Total NAV Returns Category Rank",
  "10 Year Total NAV Returns Category Rank",
  "Annualized 5 Year Total Returns (Monthly)",
  "Alpha (vs Category) (5Y)",
  "Beta (vs Category) (5Y)",
  "R-Squared (vs Category) (5Y)",
  "Max Drawdown (5Y)",
  "Upside (5Y)",
  "Downside (5Y)",
  "Upside/Downside Ratio (5Y)",
  "Annualized 10 Year Total Returns (Monthly)",
  "Alpha (vs Category) (10Y)",
  "Beta (vs Category) (10Y)",
  "R-Squared (vs Category) (10Y)",
  "Max Drawdown (10Y)",
  "Upside (10Y)",
  "Downside (10Y)",
  "Upside/Downside Ratio (10Y)",
  "Median Manager Tenure",
  "Average Manager Tenure",
  "Total Assets Under Management",
];

const INDEX_FUND_TRUE = new Set(["true", "t", "yes", "y", "1", "1.0"]);
const INDEX_FUND_FALSE = new Set(["false", "f", "no", "n", "0", "0.0"]);

export function parseNumber(val: any): number | null {
  if (val === null || val === undefined || val === "" || val === "N/A" || val === "nan" || val === "--") {
    return null;
  }
  const cleanStr = String(val).replace(/[%$,]/g, "").trim();
  const n = parseFloat(cleanStr);
  return isNaN(n) ? null : n;
}

export function parseIndexFund(val: any): boolean {
  if (typeof val === "boolean") return val;
  const str = String(val || "").trim().toLowerCase();
  return INDEX_FUND_TRUE.has(str);
}

export function validateYChartsCSV(csvText: string, schemaType: "2025" | "2023"): ValidationReport {
  const parsed = Papa.parse(csvText, {
    header: true,
    skipEmptyLines: true,
  });

  const columns = parsed.meta.fields || [];
  const rows = parsed.data as Record<string, any>[];
  const rowCount = rows.length;
  const columnCount = columns.length;

  const errors: Finding[] = [];
  const warnings: Finding[] = [];
  const infos: Finding[] = [];

  const required = schemaType === "2025" ? REQUIRED_2025 : REQUIRED_2023;
  const criticalNumerics = schemaType === "2025" ? CRITICAL_NUMERIC_2025 : CRITICAL_NUMERIC_2023;
  const numerics = schemaType === "2025" ? NUMERIC_2025 : NUMERIC_2023;

  // 1. Check required columns
  for (const col of required) {
    if (!columns.includes(col)) {
      errors.push({
        severity: "error",
        code: "missing_required_column",
        message: `Missing required column: "${col}"`,
        details: { column: col },
      });
    }
  }

  // 2. Check row count
  if (rowCount === 0) {
    errors.push({
      severity: "error",
      code: "empty_file",
      message: "Uploaded CSV contains 0 data rows.",
    });
  } else {
    infos.push({
      severity: "info",
      code: "row_count",
      message: `Parsed ${rowCount} funds across ${columnCount} columns.`,
      details: { rowCount, columnCount },
    });
  }

  // 3. Check duplicate symbols
  const symbolCounts = new Map<string, number>();
  for (const row of rows) {
    const sym = String(row["Symbol"] || "").trim().toUpperCase();
    if (sym) {
      symbolCounts.set(sym, (symbolCounts.get(sym) || 0) + 1);
    }
  }
  const duplicates = Array.from(symbolCounts.entries()).filter(([_, count]) => count > 1);
  if (duplicates.length > 0) {
    warnings.push({
      severity: "warning",
      code: "duplicate_symbols",
      message: `Found ${duplicates.length} duplicate ticker symbols. Downstream scoring will deduplicate deterministically.`,
      details: { count: duplicates.length, symbols: duplicates.slice(0, 10).map(d => d[0]) },
    });
  }

  // 4. Check critical numeric parsing and null rates
  for (const col of criticalNumerics) {
    if (!columns.includes(col)) continue;
    let nullCount = 0;
    let unparseableCount = 0;

    for (const row of rows) {
      const raw = row[col];
      if (raw === null || raw === undefined || String(raw).trim() === "" || String(raw).trim() === "N/A") {
        nullCount++;
      } else {
        const val = parseNumber(raw);
        if (val === null) unparseableCount++;
      }
    }

    if (unparseableCount > 0) {
      errors.push({
        severity: "error",
        code: "unparseable_critical_numeric",
        message: `Column "${col}" contains ${unparseableCount} unparseable values.`,
        details: { column: col, unparseableCount },
      });
    }

    const nullRate = rowCount > 0 ? nullCount / rowCount : 0;
    if (nullRate > 0.5) {
      warnings.push({
        severity: "warning",
        code: "high_null_rate",
        message: `Critical column "${col}" has ${(nullRate * 100).toFixed(1)}% missing values.`,
        details: { column: col, nullRate, nullCount },
      });
    }
  }

  // 5. Check index fund boolean column if 2025
  if (schemaType === "2025" && columns.includes("Index Fund")) {
    let unparseableIdx = 0;
    for (const row of rows) {
      const raw = String(row["Index Fund"] || "").trim().toLowerCase();
      if (raw && !INDEX_FUND_TRUE.has(raw) && !INDEX_FUND_FALSE.has(raw)) {
        unparseableIdx++;
      }
    }
    if (unparseableIdx > 0) {
      warnings.push({
        severity: "warning",
        code: "unparseable_index_fund_values",
        message: `Column "Index Fund" has ${unparseableIdx} values that could not be parsed as boolean. Defaults to false (Active).`,
        details: { count: unparseableIdx },
      });
    }
  }

  return {
    schema: schemaType,
    failed: errors.length > 0,
    rowCount,
    columnCount,
    columns,
    errors,
    warnings,
    infos,
  };
}

// ============================================================================
// SYMBOL ALIAS ENGINE
// ============================================================================

export const DEFAULT_ALIASES: Record<string, string> = {
  PRBLX: "PRILX", // Parnassus Core Equity -> institutional share class
  GSTKX: "GSIKX", // GS Small Cap Growth Insights -> institutional share class
  PONPX: "PIMIX", // PIMCO Income -> institutional share class
  FECMX: "FEMKX", // Fidelity Emerging Markets -> oldest share class
};

export function loadDefaultAliases(): Record<string, string> {
  const merged: Record<string, string> = { ...DEFAULT_ALIASES };

  // Try loading from config/symbol_aliases.csv if available
  const possiblePaths = [
    path.resolve(process.cwd(), "streamlit", "config", "symbol_aliases.csv"),
    path.resolve(process.cwd(), "..", "streamlit", "config", "symbol_aliases.csv"),
    path.resolve(__dirname, "../../streamlit/config/symbol_aliases.csv"),
  ];

  const aliasPath = possiblePaths.find(p => fs.existsSync(p));
  if (aliasPath) {
    try {
      const content = fs.readFileSync(aliasPath, "utf-8");
      const parsed = Papa.parse(content, { header: true, skipEmptyLines: true });
      for (const row of parsed.data as any[]) {
        const orig = String(row["Original_Symbol"] || "").trim().toUpperCase();
        const scoring = String(row["Scoring_Symbol"] || "").trim().toUpperCase();
        if (orig && scoring && orig !== scoring) {
          merged[orig] = scoring;
        }
      }
    } catch {
      // Gracefully fall back to DEFAULT_ALIASES
    }
  }

  return merged;
}

export function resolveSymbol(
  symbol: string,
  scoredUniverseSymbols?: Set<string>,
  aliasMap: Record<string, string> = DEFAULT_ALIASES
): {
  originalSymbol: string;
  scoringSymbol: string;
  aliasApplied: boolean;
} {
  const upper = symbol.trim().toUpperCase();
  // 1. If symbol already exists in universe, keep as-is
  if (scoredUniverseSymbols && scoredUniverseSymbols.has(upper)) {
    return { originalSymbol: upper, scoringSymbol: upper, aliasApplied: false };
  }
  // 2. If present in alias map, remap
  if (aliasMap[upper]) {
    return {
      originalSymbol: upper,
      scoringSymbol: aliasMap[upper],
      aliasApplied: true,
    };
  }
  // 3. Pass through
  return { originalSymbol: upper, scoringSymbol: upper, aliasApplied: false };
}
