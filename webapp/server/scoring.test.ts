import { describe, it, expect } from "vitest";
import goldenData from "./golden_scoring_fixtures.json";
import {
  scoreAllFunds,
  score2023Funds,
  buildDualScoreTable,
  PASSIVE_RESCALE,
} from "./scoring";
import type { Fund } from "@shared/schema";
import fs from "fs";
import path from "path";
import Papa from "papaparse";

const TOLERANCE = 1e-4;

function expectClose(
  actual: number | null | undefined,
  expected: number | null | undefined,
  label: string
) {
  if (expected === null || expected === undefined) {
    expect(actual, `${label} should be null/undefined`).toBeNull();
    return;
  }
  expect(actual, `${label} should be defined`).toBeDefined();
  expect(
    Math.abs((actual ?? 0) - expected),
    `${label} diff ${Math.abs((actual ?? 0) - expected)} exceeds tolerance ${TOLERANCE} (actual=${actual}, expected=${expected})`
  ).toBeLessThanOrEqual(TOLERANCE);
}

describe("Golden Parity Test Suite (Milestones 1 & 2)", () => {
  it("verifies PASSIVE_RESCALE is strictly 1.0 (no inflation factor)", () => {
    expect(PASSIVE_RESCALE).toBe(1.0);
  });

  describe("Synthetic Parity Scenarios", () => {
    it("verifies passive_dominator without 100/90 inflation factor", () => {
      const inputs = goldenData.synthetic.passive_dominator.inputs as any[];
      const expectedOutputs = goldenData.synthetic.passive_dominator.outputs as any[];

      const funds: Fund[] = inputs.map((inp, idx) => ({
        id: idx + 1,
        symbol: inp["Symbol"],
        name: inp["Name"],
        isIndexFund: inp["Index Fund"],
        categoryName: inp["Category Name"],
        netExpenseRatio: inp["Net Expense Ratio"] ?? null,
        trackingError3Y: inp["Tracking Error (vs Category) (3Y)"] ?? null,
        trackingError5Y: inp["Tracking Error (vs Category) (5Y)"] ?? null,
        trackingError10Y: inp["Tracking Error (vs Category) (10Y)"] ?? null,
        rSquared5Y: inp["R-Squared (vs Category) (5Y)"] ?? null,
        shareClassAum: inp["Share Class Assets Under Management"] ?? null,
        downside5Y: inp["Downside (vs Category) (5Y)"] ?? null,
        downside10Y: inp["Downside (vs Category) (10Y)"] ?? null,
        maxDrawdown5Y: inp["Max Drawdown (5Y)"] ?? null,
        maxDrawdown10Y: inp["Max Drawdown (10Y)"] ?? null,
        infoRatio3Y: null,
        infoRatio5Y: null,
        infoRatio10Y: null,
        sortino3Y: null,
        sortino5Y: null,
        sortino10Y: null,
        upside3Y: null,
        upside5Y: null,
        upside10Y: null,
        returns3Y: null,
        returns5Y: null,
        returns10Y: null,
        oldestShareSymbol: null,
        shareClass: null,
        score: null,
        scoreBand: null,
        categoryPercentile: null,
        uploadBatchId: null,
      }));

      const results = scoreAllFunds(funds);

      for (const exp of expectedOutputs) {
        const actual = results.find(r => r.symbol === exp.Symbol);
        expect(actual, `Fund ${exp.Symbol} must be found`).toBeDefined();
        expectClose(actual?.score, exp.Score_Final, `${exp.Symbol} Score_Final`);
        expect(actual?.scoreBand, `${exp.Symbol} Score_Band`).toBe(exp.Score_Band);
      }
    });

    it("verifies singleton_category evaluates to percentile 1.0 (matching Python baseline)", () => {
      const inputs = goldenData.synthetic.singleton_category.inputs as any[];
      const expectedOutputs = goldenData.synthetic.singleton_category.outputs as any[];

      const funds: Fund[] = inputs.map((inp, idx) => ({
        id: idx + 1,
        symbol: inp["Symbol"],
        name: inp["Name"],
        isIndexFund: inp["Index Fund"],
        categoryName: inp["Category Name"],
        netExpenseRatio: inp["Net Expense Ratio"] ?? null,
        trackingError3Y: null,
        trackingError5Y: null,
        trackingError10Y: null,
        rSquared5Y: null,
        shareClassAum: null,
        downside5Y: inp["Downside (vs Category) (5Y)"] ?? null,
        downside10Y: inp["Downside (vs Category) (10Y)"] ?? null,
        maxDrawdown5Y: inp["Max Drawdown (5Y)"] ?? null,
        maxDrawdown10Y: inp["Max Drawdown (10Y)"] ?? null,
        infoRatio3Y: inp["Information Ratio (vs Category) (3Y)"] ?? null,
        infoRatio5Y: inp["Information Ratio (vs Category) (5Y)"] ?? null,
        infoRatio10Y: inp["Information Ratio (vs Category) (10Y)"] ?? null,
        sortino3Y: inp["Historical Sortino (3Y)"] ?? null,
        sortino5Y: inp["Historical Sortino (5Y)"] ?? null,
        sortino10Y: inp["Historical Sortino (10Y)"] ?? null,
        upside3Y: null,
        upside5Y: inp["Upside (vs Category) (5Y)"] ?? null,
        upside10Y: inp["Upside (vs Category) (10Y)"] ?? null,
        returns3Y: inp["3 Year Total Returns (Daily)"] ?? null,
        returns5Y: inp["5 Year Total Returns (Daily)"] ?? null,
        returns10Y: inp["10 Year Total Returns (Daily)"] ?? null,
        oldestShareSymbol: null,
        shareClass: null,
        score: null,
        scoreBand: null,
        categoryPercentile: null,
        uploadBatchId: null,
      }));

      const results = scoreAllFunds(funds);

      for (const exp of expectedOutputs) {
        const actual = results.find(r => r.symbol === exp.Symbol);
        expect(actual, `Fund ${exp.Symbol} must be found`).toBeDefined();
        expectClose(actual?.score, exp.Score_Final, `${exp.Symbol} Score_Final`);
        expect(actual?.scoreBand, `${exp.Symbol} Score_Band`).toBe(exp.Score_Band);
      }
    });
  });

  describe("Fixture Parity Verification", () => {
    const fixture2025Path = path.resolve(__dirname, "../../streamlit/tests/fixtures/ycharts_2025_good.csv");
    const fixture2023Path = path.resolve(__dirname, "../../streamlit/tests/fixtures/ycharts_2023_good.csv");

    it("verifies 2025 scoring parity against Python golden fixture", () => {
      const csvText = fs.readFileSync(fixture2025Path, "utf-8");
      const parsed = Papa.parse(csvText, { header: true, skipEmptyLines: true });

      const funds: Fund[] = parsed.data.map((row: any, idx: number) => {
        const num = (v: any) => (v !== null && v !== undefined && v !== "" ? Number(v) : null);
        const isIdx = String(row["Index Fund"]).toLowerCase() === "true" || row["Index Fund"] === "1" || row["Index Fund"] === 1;
        return {
          id: idx + 1,
          symbol: String(row["Symbol"]).trim().toUpperCase(),
          name: String(row["Name"]).trim(),
          isIndexFund: isIdx,
          categoryName: row["Category Name"] ? String(row["Category Name"]).trim() : null,
          netExpenseRatio: num(row["Net Expense Ratio"]),
          trackingError3Y: num(row["Tracking Error (vs Category) (3Y)"]),
          trackingError5Y: num(row["Tracking Error (vs Category) (5Y)"]),
          trackingError10Y: num(row["Tracking Error (vs Category) (10Y)"]),
          rSquared5Y: num(row["R-Squared (vs Category) (5Y)"]),
          shareClassAum: num(row["Share Class Assets Under Management"]),
          downside5Y: num(row["Downside (vs Category) (5Y)"]),
          downside10Y: num(row["Downside (vs Category) (10Y)"]),
          maxDrawdown5Y: num(row["Max Drawdown (5Y)"]),
          maxDrawdown10Y: num(row["Max Drawdown (10Y)"]),
          infoRatio3Y: num(row["Information Ratio (vs Category) (3Y)"]),
          infoRatio5Y: num(row["Information Ratio (vs Category) (5Y)"]),
          infoRatio10Y: num(row["Information Ratio (vs Category) (10Y)"]),
          sortino3Y: num(row["Historical Sortino (3Y)"]),
          sortino5Y: num(row["Historical Sortino (5Y)"]),
          sortino10Y: num(row["Historical Sortino (10Y)"]),
          upside3Y: num(row["Upside (vs Category) (3Y)"]),
          upside5Y: num(row["Upside (vs Category) (5Y)"]),
          upside10Y: num(row["Upside (vs Category) (10Y)"]),
          returns3Y: num(row["3 Year Total Returns (Daily)"]),
          returns5Y: num(row["5 Year Total Returns (Daily)"]),
          returns10Y: num(row["10 Year Total Returns (Daily)"]),
          oldestShareSymbol: null,
          shareClass: null,
          score: null,
          scoreBand: null,
          categoryPercentile: null,
          uploadBatchId: null,
        };
      });

      const results = scoreAllFunds(funds);
      const expectedOutputs = goldenData.fixture_2025_scored as any[];

      for (const exp of expectedOutputs) {
        const actual = results.find(r => r.symbol === exp.Symbol);
        expect(actual, `Fund ${exp.Symbol} must be scored`).toBeDefined();
        expectClose(actual?.score, exp.Score_Final, `${exp.Symbol} Final Score`);
        expect(actual?.scoreBand, `${exp.Symbol} Score Band`).toBe(exp.Score_Band);
      }
    });

    it("verifies 2023 scoring parity against Python golden fixture", () => {
      const csvText = fs.readFileSync(fixture2023Path, "utf-8");
      const parsed = Papa.parse(csvText, { header: true, skipEmptyLines: true });

      const results = score2023Funds(parsed.data as Record<string, any>[]);
      const expectedOutputs = goldenData.fixture_2023_scored as any[];

      for (const exp of expectedOutputs) {
        const actual = results.find(r => r.symbol === exp.Symbol);
        expect(actual, `Fund ${exp.Symbol} must be scored in 2023`).toBeDefined();
        expectClose(actual?.score2023, exp.Score_2023, `${exp.Symbol} Score_2023`);
        expectClose(actual?.availWeight, exp.Avail_Weight, `${exp.Symbol} Avail_Weight`);
      }
    });

    it("verifies Dual-Score Table parity (dense ranks, consensus rank, quadrants, action flags)", () => {
      const csv2025 = fs.readFileSync(fixture2025Path, "utf-8");
      const parsed2025 = Papa.parse(csv2025, { header: true, skipEmptyLines: true });

      const funds: Fund[] = parsed2025.data.map((row: any, idx: number) => {
        const num = (v: any) => (v !== null && v !== undefined && v !== "" ? Number(v) : null);
        const isIdx = String(row["Index Fund"]).toLowerCase() === "true" || row["Index Fund"] === "1" || row["Index Fund"] === 1;
        return {
          id: idx + 1,
          symbol: String(row["Symbol"]).trim().toUpperCase(),
          name: String(row["Name"]).trim(),
          isIndexFund: isIdx,
          categoryName: row["Category Name"] ? String(row["Category Name"]).trim() : null,
          netExpenseRatio: num(row["Net Expense Ratio"]),
          trackingError3Y: num(row["Tracking Error (vs Category) (3Y)"]),
          trackingError5Y: num(row["Tracking Error (vs Category) (5Y)"]),
          trackingError10Y: num(row["Tracking Error (vs Category) (10Y)"]),
          rSquared5Y: num(row["R-Squared (vs Category) (5Y)"]),
          shareClassAum: num(row["Share Class Assets Under Management"]),
          downside5Y: num(row["Downside (vs Category) (5Y)"]),
          downside10Y: num(row["Downside (vs Category) (10Y)"]),
          maxDrawdown5Y: num(row["Max Drawdown (5Y)"]),
          maxDrawdown10Y: num(row["Max Drawdown (10Y)"]),
          infoRatio3Y: num(row["Information Ratio (vs Category) (3Y)"]),
          infoRatio5Y: num(row["Information Ratio (vs Category) (5Y)"]),
          infoRatio10Y: num(row["Information Ratio (vs Category) (10Y)"]),
          sortino3Y: num(row["Historical Sortino (3Y)"]),
          sortino5Y: num(row["Historical Sortino (5Y)"]),
          sortino10Y: num(row["Historical Sortino (10Y)"]),
          upside3Y: num(row["Upside (vs Category) (3Y)"]),
          upside5Y: num(row["Upside (vs Category) (5Y)"]),
          upside10Y: num(row["Upside (vs Category) (10Y)"]),
          returns3Y: num(row["3 Year Total Returns (Daily)"]),
          returns5Y: num(row["5 Year Total Returns (Daily)"]),
          returns10Y: num(row["10 Year Total Returns (Daily)"]),
          oldestShareSymbol: null,
          shareClass: null,
          score: null,
          scoreBand: null,
          categoryPercentile: null,
          uploadBatchId: null,
        };
      });

      const scored2025 = scoreAllFunds(funds);

      const csv2023 = fs.readFileSync(fixture2023Path, "utf-8");
      const parsed2023 = Papa.parse(csv2023, { header: true, skipEmptyLines: true });
      const scored2023 = score2023Funds(parsed2023.data as Record<string, any>[]);

      const dualTable = buildDualScoreTable(scored2025, scored2023, "inner");
      const expectedOutputs = goldenData.dual_score_table as any[];

      expect(dualTable.length).toBe(expectedOutputs.length);

      for (let i = 0; i < expectedOutputs.length; i++) {
        const exp = expectedOutputs[i];
        const actual = dualTable[i];

        expect(actual.Symbol).toBe(exp.Symbol);
        expect(actual.Name).toBe(exp.Name);
        expect(actual.Category).toBe(exp.Category);
        expect(actual.Fund_Type).toBe(exp.Fund_Type);

        expectClose(actual.Score_2023_Final, exp.Score_2023_Final, `${exp.Symbol} Score_2023_Final`);
        expectClose(actual.Score_2025_Final, exp.Score_2025_Final, `${exp.Symbol} Score_2025_Final`);
        expectClose(actual.Score_Gap, exp.Score_Gap, `${exp.Symbol} Score_Gap`);

        expect(actual.Rank_2023).toBe(exp.Rank_2023);
        expect(actual.Rank_2025).toBe(exp.Rank_2025);
        expect(actual.Consensus_Rank).toBe(exp.Consensus_Rank);

        expect(actual.Score_Band_2023).toBe(exp.Score_Band_2023);
        expect(actual.Score_Band_2025).toBe(exp.Score_Band_2025);
        expect(actual.Quadrant).toBe(exp.Quadrant);
        expect(actual.Action_Flag).toBe(exp.Action_Flag);
        expect(actual.Primary_Driver).toBe(exp.Primary_Driver);
        expect(actual.Data_Coverage_2023).toBe(exp.Data_Coverage_2023);
        expect(actual.Data_Coverage_2025).toBe(exp.Data_Coverage_2025);
      }
    });
  });
});
