import { describe, it, expect } from "vitest";
import ExcelJS from "exceljs";
import { generateAuditWorkbook } from "./excelExport";
import type { DualScoreRow } from "./scoring";

describe("Excel Audit Export Service Test Suite", () => {
  const mockTable: DualScoreRow[] = [
    {
      Symbol: "TOP",
      Name: "Top Fund",
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
    {
      Symbol: "MOVER",
      Name: "Mover Fund",
      Category: "Mid Cap Value",
      Fund_Type: "Active",
      Score_2023_Final: 60.0,
      Score_2025_Final: 85.0,
      Score_Gap: 25.0,
      Rank_2023: 10,
      Rank_2025: 2,
      Consensus_Rank: 6,
      Score_Band_2023: "REVIEW",
      Score_Band_2025: "STRONG",
      Quadrant: "Q2_Only_2025",
      Action_Flag: "REVIEW",
      Primary_Driver: "Upgraded by 2025 system",
      Data_Coverage_2023: 0.9,
      Data_Coverage_2025: 0.95,
    },
  ];

  it("generates an Excel 2019-compatible workbook with all 5 core sheets", async () => {
    const buffer = await generateAuditWorkbook(mockTable, {
      runDate: "2026-10-06",
      rowCount: 2,
    });

    expect(buffer).toBeDefined();
    expect(buffer.length).toBeGreaterThan(1000);

    // Read back workbook
    const wb = new ExcelJS.Workbook();
    await wb.xlsx.load(buffer);

    const sheetNames = wb.worksheets.map(ws => ws.name);
    expect(sheetNames).toContain("Summary");
    expect(sheetNames).toContain("Dual_Score_Table");
    expect(sheetNames).toContain("Top_50_Consensus");
    expect(sheetNames).toContain("Disagreements");
    expect(sheetNames).toContain("Quadrants");

    // Verify Summary sheet content
    const wsSummary = wb.getWorksheet("Summary")!;
    expect(wsSummary.getCell("B2").value).toContain("FundScore");
    expect(wsSummary.getCell("C4").value).toBe("2026-10-06");

    // Verify Dual_Score_Table rows
    const wsDual = wb.getWorksheet("Dual_Score_Table")!;
    expect(wsDual.rowCount).toBe(3); // 1 header + 2 data rows
    expect(wsDual.getCell("A2").value).toBe("TOP");
    expect(wsDual.getCell("A3").value).toBe("MOVER");

    // Verify Disagreements sheet has only MOVER (Score_Gap 25 >= 10)
    const wsDisagreements = wb.getWorksheet("Disagreements")!;
    expect(wsDisagreements.rowCount).toBe(2); // 1 header + 1 row
    expect(wsDisagreements.getCell("A2").value).toBe("MOVER");
  });
});
