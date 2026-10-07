import { describe, it, expect } from "vitest";
import fs from "fs";
import path from "path";
import {
  validateYChartsCSV,
  resolveSymbol,
  loadDefaultAliases,
  DEFAULT_ALIASES,
} from "./intake";
import {
  computeSHA256,
  buildValidationSummary,
  saveRunArchive,
  listRunArchives,
  loadRunDualTable,
} from "./runArchive";
import type { DualScoreRow } from "./scoring";

describe("YCharts Intake & Run Archive Test Suite (Milestone 3)", () => {
  const fixture2025Path = path.resolve(__dirname, "../../streamlit/tests/fixtures/ycharts_2025_good.csv");
  const fixture2023Path = path.resolve(__dirname, "../../streamlit/tests/fixtures/ycharts_2023_good.csv");

  describe("YCharts Validation Engine", () => {
    it("validates good 2025 CSV without errors", () => {
      const csv = fs.readFileSync(fixture2025Path, "utf-8");
      const report = validateYChartsCSV(csv, "2025");

      expect(report.failed).toBe(false);
      expect(report.errors.length).toBe(0);
      expect(report.rowCount).toBeGreaterThan(0);
      expect(report.columns).toContain("Net Expense Ratio");
    });

    it("validates good 2023 CSV without errors", () => {
      const csv = fs.readFileSync(fixture2023Path, "utf-8");
      const report = validateYChartsCSV(csv, "2023");

      expect(report.failed).toBe(false);
      expect(report.errors.length).toBe(0);
      expect(report.rowCount).toBeGreaterThan(0);
      expect(report.columns).toContain("Annual Report Expense Ratio");
    });

    it("flags missing required columns", () => {
      const badCsv = "Symbol,Name\nAAA,Fund A";
      const report = validateYChartsCSV(badCsv, "2025");

      expect(report.failed).toBe(true);
      expect(report.errors.some(e => e.code === "missing_required_column")).toBe(true);
    });

    it("flags duplicate symbols as warnings", () => {
      const dupeCsv = `Symbol,Name,Index Fund,Category Name,Net Expense Ratio,R-Squared (vs Category) (5Y),Share Class Assets Under Management,Max Drawdown (5Y),Max Drawdown (10Y),Information Ratio (vs Category) (3Y),Historical Sortino (3Y),Upside (vs Category) (5Y),Downside (vs Category) (5Y),3 Year Total Returns (Daily),5 Year Total Returns (Daily),10 Year Total Returns (Daily)
AAA,Fund 1,true,Large,0.1,0.9,100,10,12,0.5,1.2,100,100,0.1,0.1,0.1
AAA,Fund 2,true,Large,0.2,0.8,200,11,13,0.4,1.1,100,100,0.1,0.1,0.1`;
      const report = validateYChartsCSV(dupeCsv, "2025");

      expect(report.warnings.some(w => w.code === "duplicate_symbols")).toBe(true);
    });
  });

  describe("Symbol Alias Reconciliation", () => {
    it("resolves default aliases correctly", () => {
      const res1 = resolveSymbol("PRBLX", new Set());
      expect(res1.scoringSymbol).toBe("PRILX");
      expect(res1.aliasApplied).toBe(true);

      const res2 = resolveSymbol("GSTKX", new Set());
      expect(res2.scoringSymbol).toBe("GSIKX");
      expect(res2.aliasApplied).toBe(true);
    });

    it("preserves symbol if already present in scored universe", () => {
      const res = resolveSymbol("PRBLX", new Set(["PRBLX"]));
      expect(res.scoringSymbol).toBe("PRBLX");
      expect(res.aliasApplied).toBe(false);
    });

    it("passes through unknown symbols untouched", () => {
      const res = resolveSymbol("XYZ123", new Set());
      expect(res.scoringSymbol).toBe("XYZ123");
      expect(res.aliasApplied).toBe(false);
    });

    it("loads default aliases from config file or fallback", () => {
      const aliases = loadDefaultAliases();
      expect(aliases["PRBLX"]).toBe("PRILX");
      expect(aliases["PONPX"]).toBe("PIMIX");
    });
  });

  describe("Run Hashing & Archiving", () => {
    it("computes deterministic SHA256 hashes", () => {
      const h1 = computeSHA256("test content");
      const h2 = computeSHA256("test content");
      expect(h1).toBe(h2);
      expect(h1).toHaveLength(64);
    });

    it("creates, archives, and reads back a dated run", () => {
      const mockTable: DualScoreRow[] = [
        {
          Symbol: "AAA",
          Name: "Fund Alpha",
          Category: "Large Blend",
          Fund_Type: "Passive",
          Score_2023_Final: 95.0,
          Score_2025_Final: 92.0,
          Score_Gap: -3.0,
          Rank_2023: 1,
          Rank_2025: 1,
          Consensus_Rank: 1,
          Score_Band_2023: "STRONG",
          Score_Band_2025: "STRONG",
          Quadrant: "Q1_Both_Strong",
          Action_Flag: "LEAD",
          Primary_Driver: "Stable",
          Data_Coverage_2023: 1.0,
          Data_Coverage_2025: 1.0,
        },
      ];

      const testRunDate = "2026-10-01";
      const { metadata, validation } = saveRunArchive(testRunDate, mockTable, {
        hash2025: computeSHA256("input2025"),
      });

      expect(metadata.rowCount).toBe(1);
      expect(validation.joinedCount).toBe(1);

      const runs = listRunArchives();
      expect(runs).toContain(testRunDate);

      const loaded = loadRunDualTable(testRunDate);
      expect(loaded).toBeDefined();
      expect(loaded?.length).toBe(1);
      expect(loaded?.[0].Symbol).toBe("AAA");
      expect(loaded?.[0].Score_Band_2025).toBe("STRONG");
    });
  });
});
