import ExcelJS from "exceljs";
import type { DualScoreRow } from "./scoring";
import type { RunMetadata, RunArchiveValidation } from "./runArchive";

const HEADER_FILL: ExcelJS.Fill = {
  type: "pattern",
  pattern: "solid",
  fgColor: { argb: "FF1F4E78" },
};

const HEADER_FONT: Partial<ExcelJS.Font> = {
  name: "Calibri",
  size: 11,
  bold: true,
  color: { argb: "FFFFFFFF" },
};

const SECTION_FONT: Partial<ExcelJS.Font> = {
  name: "Calibri",
  size: 13,
  bold: true,
  color: { argb: "FF1F4E78" },
};

const BODY_FONT: Partial<ExcelJS.Font> = {
  name: "Calibri",
  size: 11,
};

const BORDER_BOX: Partial<ExcelJS.Borders> = {
  top: { style: "thin", color: { argb: "FFB7B7B7" } },
  left: { style: "thin", color: { argb: "FFB7B7B7" } },
  bottom: { style: "thin", color: { argb: "FFB7B7B7" } },
  right: { style: "thin", color: { argb: "FFB7B7B7" } },
};

const BAND_FILLS: Record<string, ExcelJS.Fill> = {
  STRONG: { type: "pattern", pattern: "solid", fgColor: { argb: "FFC6EFCE" } },
  REVIEW: { type: "pattern", pattern: "solid", fgColor: { argb: "FFFFEB9C" } },
  WEAK: { type: "pattern", pattern: "solid", fgColor: { argb: "FFFFC7CE" } },
};

function autoFitColumns(worksheet: ExcelJS.Worksheet) {
  worksheet.columns.forEach(column => {
    let maxLen = 10;
    column.eachCell?.({ includeEmpty: false }, cell => {
      const val = cell.value ? String(cell.value) : "";
      if (val.length > maxLen) {
        maxLen = val.length;
      }
    });
    column.width = Math.min(Math.max(maxLen + 3, 12), 45);
  });
}

export async function generateAuditWorkbook(
  dualTable: DualScoreRow[],
  metadata?: Partial<RunMetadata>,
  validation?: Partial<RunArchiveValidation>
): Promise<Buffer> {
  const wb = new ExcelJS.Workbook();
  wb.creator = "FundScore Modernized";
  wb.lastModifiedBy = "FundScore Committee Audit";
  wb.created = new Date();
  wb.modified = new Date();

  // ==========================================
  // SHEET 1: Summary & Methodology
  // ==========================================
  const wsSummary = wb.addWorksheet("Summary");
  wsSummary.views = [{ showGridLines: true }];

  wsSummary.getCell("B2").value = "FundScore — Investment Committee Audit Summary";
  wsSummary.getCell("B2").font = SECTION_FONT;

  wsSummary.getCell("B4").value = "Run Date:";
  wsSummary.getCell("B4").font = { bold: true };
  wsSummary.getCell("C4").value = metadata?.runDate || new Date().toISOString().split("T")[0];

  wsSummary.getCell("B5").value = "Generated At:";
  wsSummary.getCell("B5").font = { bold: true };
  wsSummary.getCell("C5").value = metadata?.createdAt || new Date().toISOString();

  wsSummary.getCell("B6").value = "Scoring Engine:";
  wsSummary.getCell("B6").font = { bold: true };
  wsSummary.getCell("C6").value = metadata?.scoreSystemVersion || "dual-2023-combined+2025-split";

  wsSummary.getCell("B7").value = "Total Scored Funds:";
  wsSummary.getCell("B7").font = { bold: true };
  wsSummary.getCell("C7").value = dualTable.length;

  wsSummary.getCell("B8").value = "Dual Joined Funds:";
  wsSummary.getCell("B8").font = { bold: true };
  wsSummary.getCell("C8").value = dualTable.filter(r => r.Score_2023_Final !== null && r.Score_2025_Final !== null).length;

  // Band counts summary table
  wsSummary.getCell("B11").value = "Score Band Distribution";
  wsSummary.getCell("B11").font = SECTION_FONT;

  wsSummary.getRow(13).values = ["", "Band", "2023 System", "2025 System"];
  ["B13", "C13", "D13"].forEach(addr => {
    wsSummary.getCell(addr).fill = HEADER_FILL;
    wsSummary.getCell(addr).font = HEADER_FONT;
    wsSummary.getCell(addr).border = BORDER_BOX;
  });

  const bands = ["STRONG", "REVIEW", "WEAK"] as const;
  bands.forEach((b, idx) => {
    const rowNum = 14 + idx;
    const c23 = dualTable.filter(r => r.Score_Band_2023 === b).length;
    const c25 = dualTable.filter(r => r.Score_Band_2025 === b).length;
    wsSummary.getRow(rowNum).values = ["", b, c23, c25];
    wsSummary.getCell(`B${rowNum}`).border = BORDER_BOX;
    wsSummary.getCell(`C${rowNum}`).border = BORDER_BOX;
    wsSummary.getCell(`D${rowNum}`).border = BORDER_BOX;
  });

  // Quadrants summary
  wsSummary.getCell("B19").value = "Dual-Lens Quadrants";
  wsSummary.getCell("B19").font = SECTION_FONT;

  wsSummary.getRow(21).values = ["", "Quadrant", "Description", "Fund Count"];
  ["B21", "C21", "D21"].forEach(addr => {
    wsSummary.getCell(addr).fill = HEADER_FILL;
    wsSummary.getCell(addr).font = HEADER_FONT;
    wsSummary.getCell(addr).border = BORDER_BOX;
  });

  const quadDefs = [
    { key: "Q1_Both_Strong", desc: "Both 2023 and 2025 Score >= 80 (High Conviction)" },
    { key: "Q2_Only_2025", desc: "Upgraded: 2025 Score >= 80, 2023 < 80" },
    { key: "Q3_Only_2023", desc: "Downgraded: 2023 Score >= 80, 2025 < 80" },
    { key: "Q4_Both_Weak", desc: "Both Scores < 80 (Watch / Drop Triage)" },
  ];

  quadDefs.forEach((qd, idx) => {
    const rowNum = 22 + idx;
    const count = dualTable.filter(r => r.Quadrant === qd.key).length;
    wsSummary.getRow(rowNum).values = ["", qd.key, qd.desc, count];
    ["B", "C", "D"].forEach(c => {
      wsSummary.getCell(`${c}${rowNum}`).border = BORDER_BOX;
    });
  });

  autoFitColumns(wsSummary);

  // Helper to add data tables
  const addDataTableSheet = (
    sheetName: string,
    rows: DualScoreRow[]
  ) => {
    const ws = wb.addWorksheet(sheetName);
    ws.views = [{ showGridLines: true }];

    const headers = [
      "Symbol",
      "Name",
      "Category",
      "Fund_Type",
      "Score_2023_Final",
      "Score_2025_Final",
      "Score_Gap",
      "Rank_2023",
      "Rank_2025",
      "Consensus_Rank",
      "Score_Band_2023",
      "Score_Band_2025",
      "Quadrant",
      "Action_Flag",
      "Primary_Driver",
      "Data_Coverage_2023",
      "Data_Coverage_2025",
    ];

    ws.getRow(1).values = headers;
    for (let c = 1; c <= headers.length; c++) {
      const cell = ws.getCell(1, c);
      cell.fill = HEADER_FILL;
      cell.font = HEADER_FONT;
      cell.border = BORDER_BOX;
    }

    rows.forEach((r, rIdx) => {
      const rowNum = rIdx + 2;
      const row = ws.getRow(rowNum);
      row.values = [
        r.Symbol,
        r.Name,
        r.Category,
        r.Fund_Type,
        r.Score_2023_Final !== null ? Math.round(r.Score_2023_Final * 100) / 100 : "",
        r.Score_2025_Final !== null ? Math.round(r.Score_2025_Final * 100) / 100 : "",
        r.Score_Gap !== null ? Math.round(r.Score_Gap * 100) / 100 : "",
        r.Rank_2023 ?? "",
        r.Rank_2025 ?? "",
        r.Consensus_Rank ?? "",
        r.Score_Band_2023 ?? "",
        r.Score_Band_2025 ?? "",
        r.Quadrant,
        r.Action_Flag,
        r.Primary_Driver,
        r.Data_Coverage_2023 !== null ? `${Math.round(r.Data_Coverage_2023 * 100)}%` : "",
        r.Data_Coverage_2025 !== null ? `${Math.round(r.Data_Coverage_2025 * 100)}%` : "",
      ];

      for (let c = 1; c <= headers.length; c++) {
        const cell = ws.getCell(rowNum, c);
        cell.font = BODY_FONT;
        cell.border = BORDER_BOX;
      }

      // Highlight bands
      if (r.Score_Band_2025 && BAND_FILLS[r.Score_Band_2025]) {
        ws.getCell(rowNum, 12).fill = BAND_FILLS[r.Score_Band_2025];
      }
    });

    autoFitColumns(ws);
  };

  // ==========================================
  // SHEET 2: Full Dual-Score Table
  // ==========================================
  addDataTableSheet("Dual_Score_Table", dualTable);

  // ==========================================
  // SHEET 3: Top 50 Consensus
  // ==========================================
  const top50Consensus = [...dualTable]
    .filter(r => r.Consensus_Rank !== null)
    .sort((a, b) => (a.Consensus_Rank ?? 9999) - (b.Consensus_Rank ?? 9999))
    .slice(0, 50);
  addDataTableSheet("Top_50_Consensus", top50Consensus);

  // ==========================================
  // SHEET 4: Disagreements (Score Gap >= 10)
  // ==========================================
  const disagreements = [...dualTable]
    .filter(r => r.Score_Gap !== null && Math.abs(r.Score_Gap) >= 10)
    .sort((a, b) => Math.abs(b.Score_Gap ?? 0) - Math.abs(a.Score_Gap ?? 0));
  addDataTableSheet("Disagreements", disagreements);

  // ==========================================
  // SHEET 5: Quadrants
  // ==========================================
  const quadrantsSorted = [...dualTable].sort((a, b) => a.Quadrant.localeCompare(b.Quadrant));
  addDataTableSheet("Quadrants", quadrantsSorted);

  const arrayBuffer = await wb.xlsx.writeBuffer();
  return Buffer.from(arrayBuffer);
}
