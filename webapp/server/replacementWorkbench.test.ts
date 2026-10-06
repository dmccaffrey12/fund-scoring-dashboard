import { describe, it, expect, beforeEach } from "vitest";
import { buildReplacementWorkbench, renderReplacementBriefHtml } from "./replacementWorkbench";
import { storage } from "./storage";
import type { InsertFund } from "@shared/schema";

describe("Replacement Workbench", () => {
  beforeEach(() => {
    storage.clearFunds();
    const testFunds: InsertFund[] = [
      {
        symbol: "HOLDING_A",
        name: "Test Holding A",
        isIndexFund: false,
        categoryName: "Large Growth",
        netExpenseRatio: 0.0095,
        score: 65.0,
        scoreBand: "REVIEW",
        categoryPercentile: 0.5,
        score2023: 62.0,
        score2025: 65.0,
        scoreGap: 3.0,
        rank2023: 50,
        rank2025: 45,
        consensusRank: 48,
        scoreBand2023: "REVIEW",
        scoreBand2025: "REVIEW",
        quadrant: "Q4_Both_Weak",
        actionFlag: "WATCH",
        primaryDriver: "Stable",
      },
      {
        symbol: "REPLACE_1",
        name: "Superior Replacement Candidate 1",
        isIndexFund: false,
        categoryName: "Large Growth",
        netExpenseRatio: 0.0065,
        score: 88.5,
        scoreBand: "STRONG",
        categoryPercentile: 0.95,
        score2023: 86.0,
        score2025: 88.5,
        scoreGap: 2.5,
        rank2023: 3,
        rank2025: 2,
        consensusRank: 2,
        scoreBand2023: "STRONG",
        scoreBand2025: "STRONG",
        quadrant: "Q1_Both_Strong",
        actionFlag: "LEAD",
        primaryDriver: "Stable",
      },
      {
        symbol: "OTHER_CAT",
        name: "Other Category Fund",
        isIndexFund: false,
        categoryName: "Small Blend",
        netExpenseRatio: 0.0050,
        score: 92.0,
        scoreBand: "STRONG",
        categoryPercentile: 0.99,
        score2023: 90.0,
        score2025: 92.0,
        consensusRank: 1,
        quadrant: "Q1_Both_Strong",
        actionFlag: "LEAD",
      },
    ];
    storage.insertFunds(testFunds);
  });

  it("filters to same category, excludes target holding, and calculates deltas", () => {
    const result = buildReplacementWorkbench("HOLDING_A", 10);
    expect(result).not.toBeNull();
    expect(result!.currentHolding.symbol).toBe("HOLDING_A");
    expect(result!.candidates.length).toBe(1);

    const cand = result!.candidates[0];
    expect(cand.symbol).toBe("REPLACE_1");
    expect(cand.score2025Delta).toBe(23.5); // 88.5 - 65.0
    expect(cand.score2023Delta).toBe(24.0); // 86.0 - 62.0
    expect(cand.expenseDelta).toBe(-0.003); // 0.0065 - 0.0095 = -0.003
    expect(cand.actionFlag).toBe("LEAD");
    expect(cand.quadrant).toBe("Q1_Both_Strong");
  });

  it("renders a standalone printable HTML brief", () => {
    const result = buildReplacementWorkbench("HOLDING_A", 10);
    expect(result).not.toBeNull();
    const html = renderReplacementBriefHtml(result!, "2026-04-30");
    expect(html).toContain("HOLDING_A");
    expect(html).toContain("REPLACE_1");
    expect(html).toContain("Superior Replacement Candidate 1");
    expect(html).toContain("@media print");
    expect(html).toContain("2026-04-30");
  });
});
