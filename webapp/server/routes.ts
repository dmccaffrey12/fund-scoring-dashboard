import type { Express } from "express";
import { createServer, type Server } from "http";
import { storage } from "./storage";
import {
  scoreAllFunds,
  getFundBreakdown,
  score2023Funds,
  buildDualScoreTable,
  type DualScoreRow,
} from "./scoring";
import { generatePdfReport } from "./pdf-report";
import { generateAuditWorkbook } from "./excelExport";
import {
  saveRunArchive,
  listRunArchives,
  loadRunDualTable,
  loadLatestRunDate,
  computeSHA256,
  buildValidationSummary,
} from "./runArchive";
import { validateYChartsCSV } from "./intake";
import {
  buildReplacementWorkbench,
  renderReplacementBriefHtml,
} from "./replacementWorkbench";
import multer from "multer";
import Papa from "papaparse";
import fs from "fs";
import path from "path";
import os from "os";
import type { InsertFund } from "@shared/schema";

const uploadDir = path.join(os.tmpdir(), "fundscore_uploads");
fs.mkdirSync(uploadDir, { recursive: true });
const upload = multer({ dest: uploadDir });

function parseCSVRow(row: any): InsertFund {
  const parseNum = (val: any): number | null => {
    if (val === null || val === undefined || val === "" || val === "N/A") return null;
    const n = parseFloat(String(val));
    return isNaN(n) ? null : n;
  };

  return {
    symbol: String(row["Symbol"] || "").trim(),
    name: String(row["Name"] || "").trim(),
    isIndexFund: String(row["Index Fund"] || "").toLowerCase() === "true",
    categoryName: row["Category Name"] ? String(row["Category Name"]).trim() : null,
    netExpenseRatio: parseNum(row["Net Expense Ratio"]),
    trackingError3Y: parseNum(row["Tracking Error (vs Category) (3Y)"]),
    trackingError5Y: parseNum(row["Tracking Error (vs Category) (5Y)"]),
    trackingError10Y: parseNum(row["Tracking Error (vs Category) (10Y)"]),
    rSquared5Y: parseNum(row["R-Squared (vs Category) (5Y)"]),
    shareClassAum: parseNum(row["Share Class Assets Under Management"]),
    downside5Y: parseNum(row["Downside (vs Category) (5Y)"]),
    downside10Y: parseNum(row["Downside (vs Category) (10Y)"]),
    maxDrawdown5Y: parseNum(row["Max Drawdown (5Y)"]),
    maxDrawdown10Y: parseNum(row["Max Drawdown (10Y)"]),
    infoRatio3Y: parseNum(row["Information Ratio (vs Category) (3Y)"]),
    infoRatio5Y: parseNum(row["Information Ratio (vs Category) (5Y)"]),
    infoRatio10Y: parseNum(row["Information Ratio (vs Category) (10Y)"]),
    sortino3Y: parseNum(row["Historical Sortino (3Y)"]),
    sortino5Y: parseNum(row["Historical Sortino (5Y)"]),
    sortino10Y: parseNum(row["Historical Sortino (10Y)"]),
    upside3Y: parseNum(row["Upside (vs Category) (3Y)"]),
    upside5Y: parseNum(row["Upside (vs Category) (5Y)"]),
    upside10Y: parseNum(row["Upside (vs Category) (10Y)"]),
    returns3Y: parseNum(row["3 Year Total Returns (Daily)"]),
    returns5Y: parseNum(row["5 Year Total Returns (Daily)"]),
    returns10Y: parseNum(row["10 Year Total Returns (Daily)"]),
    oldestShareSymbol: row["Oldest Share Symbol"] ? String(row["Oldest Share Symbol"]).trim() : null,
    shareClass: row["Share Class"] ? String(row["Share Class"]).trim() : null,
    score: null,
    scoreBand: null,
    categoryPercentile: null,
    score2023: null,
    score2025: null,
    scoreGap: null,
    rank2023: null,
    rank2025: null,
    consensusRank: null,
    scoreBand2023: null,
    scoreBand2025: null,
    quadrant: null,
    actionFlag: null,
    primaryDriver: null,
    dataCoverage2023: null,
    dataCoverage2025: null,
    uploadBatchId: null,
  };
}

export function seedIfEmpty() {
  const allFunds = storage.getAllFunds();
  const hasDualScores = allFunds.some(f => f.score2025 !== null && f.score2023 !== null);
  if (allFunds.length > 0 && hasDualScores) {
    console.log(`Database already seeded with ${allFunds.length} funds and dual scores.`);
    return;
  }

  // Find 2025 CSV path
  const seed2025Paths = [
    path.join(process.cwd(), "server", "data", "seed.csv"),
    path.resolve("server", "data", "seed.csv"),
    path.resolve("data", "seed.csv"),
    path.resolve("..", "streamlit", "sample_data.csv"),
  ];
  const csv2025Path = seed2025Paths.find(p => fs.existsSync(p)) || null;

  // Find 2023 CSV path
  const seed2023Paths = [
    path.join(process.cwd(), "server", "data", "scores_2023.csv"),
    path.resolve("server", "data", "scores_2023.csv"),
    path.resolve("data", "scores_2023.csv"),
    path.resolve("..", "streamlit", "scores_2023.csv"),
  ];
  const csv2023Path = seed2023Paths.find(p => fs.existsSync(p)) || null;

  if (!csv2025Path) {
    console.log("No 2025 seed CSV found, skipping seed.");
    return;
  }

  console.log("Seeding database and calculating dual scores...");

  // 1. Insert 2025 funds if not already present
  let currentFunds = storage.getAllFunds();
  if (currentFunds.length === 0) {
    const csv2025Text = fs.readFileSync(csv2025Path, "utf-8");
    const parsed2025 = Papa.parse(csv2025Text, { header: true, skipEmptyLines: true });
    const fundRows: InsertFund[] = parsed2025.data
      .map((row: any) => parseCSVRow(row))
      .filter((f: InsertFund) => f.symbol && f.name);

    storage.insertFunds(fundRows);
    currentFunds = storage.getAllFunds();
    console.log(`Inserted ${currentFunds.length} funds into database.`);
  }

  // 2. Score 2025 funds
  const scored2025 = scoreAllFunds(currentFunds);
  storage.updateFundScores(scored2025);
  console.log(`Computed 2025 scores for ${scored2025.length} funds.`);

  // 3. Score 2023 funds and build Dual-Score Table if 2023 data exists
  if (csv2023Path) {
    const csv2023Text = fs.readFileSync(csv2023Path, "utf-8");
    const parsed2023 = Papa.parse(csv2023Text, { header: true, dynamicTyping: true, skipEmptyLines: true });
    const scored2023 = score2023Funds(parsed2023.data as any[]);
    console.log(`Computed 2023 scores for ${scored2023.length} funds.`);

    const dualTable = buildDualScoreTable(scored2025, scored2023, "inner");
    storage.updateFundDualScores(dualTable);
    console.log(`Updated dual score table for ${dualTable.length} funds.`);

    // Save baseline run archive
    const runDate = "2026-04-30";
    const hash2025 = computeSHA256(fs.readFileSync(csv2025Path));
    const hash2023 = computeSHA256(fs.readFileSync(csv2023Path));
    const archiveResult = saveRunArchive(runDate, dualTable, { hash2025, hash2023 });

    // Record in scoring_runs if not already present
    const existingRuns = storage.getScoringRuns();
    if (!existingRuns.some(r => r.runDate === runDate)) {
      storage.createScoringRun({
        runDate,
        label: "April 2026 Baseline Committee Run",
        createdAt: new Date().toISOString(),
        rowCount: dualTable.length,
        joinedCount: archiveResult.validation.joinedCount,
        hash2025,
        hash2023,
        validationJson: JSON.stringify(archiveResult.validation),
      });
      console.log(`Created baseline scoring run: ${runDate}`);
    }
  }

  console.log("Database seed & dual scoring completed successfully.");
}

export async function registerRoutes(
  httpServer: Server,
  app: Express
): Promise<Server> {
  // Seed on startup
  try {
    seedIfEmpty();
  } catch (err) {
    console.error("Error during seed initialization:", err);
  }

  // ============ SYSTEM HEALTH ============
  app.get("/api/health", (_req, res) => {
    const allFunds = storage.getAllFunds();
    const scoredFunds = allFunds.filter(f => f.score !== null);
    const dualScoredFunds = allFunds.filter(f => f.score2025 !== null && f.score2023 !== null);
    const runs = storage.getScoringRuns();

    res.json({
      status: "ok",
      timestamp: new Date().toISOString(),
      databasePath: process.env.DATABASE_PATH || "data.db",
      totalFunds: allFunds.length,
      scoredFunds: scoredFunds.length,
      dualScoredFunds: dualScoredFunds.length,
      scoringRunsCount: runs.length,
      nodeVersion: process.version,
      environment: process.env.NODE_ENV || "development",
    });
  });

  // ============ COMMITTEE AUDIT SUITE ============
  app.get("/api/audit-table", (req, res) => {
    const allFunds = storage.getAllFunds();
    const scored = allFunds.filter(f => f.score2025 !== null && f.score2023 !== null);

    // Build DualScoreRow array from storage
    const allDualRows: DualScoreRow[] = scored.map(f => ({
      Symbol: f.symbol,
      Name: f.name,
      Category: f.categoryName || "Uncategorized",
      Fund_Type: f.isIndexFund ? "Passive" : "Active",
      Score_2023_Final: f.score2023,
      Score_2025_Final: f.score2025,
      Score_Gap: f.scoreGap,
      Rank_2023: f.rank2023,
      Rank_2025: f.rank2025,
      Consensus_Rank: f.consensusRank,
      Score_Band_2023: f.scoreBand2023 as any,
      Score_Band_2025: f.scoreBand2025 as any,
      Quadrant: (f.quadrant || "Q4_Both_Weak") as any,
      Action_Flag: (f.actionFlag || "WATCH") as any,
      Primary_Driver: f.primaryDriver || "Stable",
      Data_Coverage_2023: f.dataCoverage2023,
      Data_Coverage_2025: f.dataCoverage2025,
    }));

    // Summary statistics over the entire dual universe
    const q1Count = allDualRows.filter(r => r.Quadrant === "Q1_Both_Strong").length;
    const q2Count = allDualRows.filter(r => r.Quadrant === "Q2_Only_2025").length;
    const q3Count = allDualRows.filter(r => r.Quadrant === "Q3_Only_2023").length;
    const q4Count = allDualRows.filter(r => r.Quadrant === "Q4_Both_Weak").length;

    const leadCount = allDualRows.filter(r => r.Action_Flag === "LEAD").length;
    const reviewCount = allDualRows.filter(r => r.Action_Flag === "REVIEW").length;
    const watchCount = allDualRows.filter(r => r.Action_Flag === "WATCH").length;
    const dropCount = allDualRows.filter(r => r.Action_Flag === "DROP").length;

    const upgradesCount = allDualRows.filter(r => (r.Score_Gap ?? 0) >= 10).length;
    const downgradesCount = allDualRows.filter(r => (r.Score_Gap ?? 0) <= -10).length;
    const stableCount = allDualRows.filter(r => Math.abs(r.Score_Gap ?? 0) < 10).length;

    // Optional filtering
    let filtered = [...allDualRows];

    const category = req.query.category as string | undefined;
    if (category && category !== "all") {
      filtered = filtered.filter(r => r.Category === category);
    }

    const quadrant = req.query.quadrant as string | undefined;
    if (quadrant && quadrant !== "all") {
      filtered = filtered.filter(r => r.Quadrant === quadrant);
    }

    const actionFlag = req.query.actionFlag as string | undefined;
    if (actionFlag && actionFlag !== "all") {
      filtered = filtered.filter(r => r.Action_Flag === actionFlag);
    }

    const fundType = req.query.fundType as string | undefined;
    if (fundType && fundType !== "all") {
      filtered = filtered.filter(r => r.Fund_Type.toLowerCase() === fundType.toLowerCase());
    }

    const search = req.query.search as string | undefined;
    if (search) {
      const q = search.toLowerCase();
      filtered = filtered.filter(r =>
        r.Symbol.toLowerCase().includes(q) ||
        r.Name.toLowerCase().includes(q) ||
        r.Category.toLowerCase().includes(q)
      );
    }

    const view = req.query.view as string | undefined;
    if (view === "top50") {
      filtered = filtered.slice(0, 50);
    } else if (view === "disagreements") {
      filtered = filtered.filter(r => Math.abs(r.Score_Gap ?? 0) >= 10);
    } else if (view === "q1") {
      filtered = filtered.filter(r => r.Quadrant === "Q1_Both_Strong");
    } else if (view === "q2") {
      filtered = filtered.filter(r => r.Quadrant === "Q2_Only_2025");
    } else if (view === "q3") {
      filtered = filtered.filter(r => r.Quadrant === "Q3_Only_2023");
    } else if (view === "q4") {
      filtered = filtered.filter(r => r.Quadrant === "Q4_Both_Weak");
    }

    res.json({
      rows: filtered,
      totalCount: allDualRows.length,
      filteredCount: filtered.length,
      summary: {
        totalScored: allDualRows.length,
        q1Count,
        q2Count,
        q3Count,
        q4Count,
        leadCount,
        reviewCount,
        watchCount,
        dropCount,
        upgradesCount,
        downgradesCount,
        stableCount,
      },
    });
  });

  // ============ EXCEL AUDIT EXPORT ============
  app.get("/api/export/audit-excel", async (req, res) => {
    try {
      const allFunds = storage.getAllFunds();
      const scored = allFunds.filter(f => f.score2025 !== null && f.score2023 !== null);

      const dualRows: DualScoreRow[] = scored.map(f => ({
        Symbol: f.symbol,
        Name: f.name,
        Category: f.categoryName || "Uncategorized",
        Fund_Type: f.isIndexFund ? "Passive" : "Active",
        Score_2023_Final: f.score2023,
        Score_2025_Final: f.score2025,
        Score_Gap: f.scoreGap,
        Rank_2023: f.rank2023,
        Rank_2025: f.rank2025,
        Consensus_Rank: f.consensusRank,
        Score_Band_2023: f.scoreBand2023 as any,
        Score_Band_2025: f.scoreBand2025 as any,
        Quadrant: (f.quadrant || "Q4_Both_Weak") as any,
        Action_Flag: (f.actionFlag || "WATCH") as any,
        Primary_Driver: f.primaryDriver || "Stable",
        Data_Coverage_2023: f.dataCoverage2023,
        Data_Coverage_2025: f.dataCoverage2025,
      }));

      const latestRun = storage.getLatestScoringRun();
      const runDate = req.query.runDate as string || latestRun?.runDate || new Date().toISOString().split("T")[0];

      const validation = buildValidationSummary(dualRows);
      const buffer = await generateAuditWorkbook(
        dualRows,
        {
          runDate,
          rowCount: dualRows.length,
          joinedCount: validation.joinedCount,
          scoreSystemVersion: "dual-2023-combined+2025-split",
        },
        validation
      );

      res.setHeader("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
      res.setHeader("Content-Disposition", `attachment; filename=fundscore_audit_workbook_${runDate}.xlsx`);
      res.send(buffer);
    } catch (err: any) {
      console.error("Excel export error:", err);
      res.status(500).json({ error: err.message || "Failed to generate Excel audit workbook" });
    }
  });

  // ============ COMPARISON RADAR "WEB" ============
  app.get("/api/funds/radar/:symbol", (req, res) => {
    const symbol = req.params.symbol.trim().toUpperCase();
    const fund = storage.getFundBySymbol(symbol);
    if (!fund) {
      return res.status(404).json({ error: "Fund not found" });
    }

    const categoryFunds = fund.categoryName
      ? storage.getFundsByCategory(fund.categoryName)
      : [fund];

    const breakdown = getFundBreakdown(fund, categoryFunds);

    res.json({
      fund: {
        symbol: fund.symbol,
        name: fund.name,
        categoryName: fund.categoryName,
        isIndexFund: fund.isIndexFund,
        netExpenseRatio: fund.netExpenseRatio,
        score: fund.score,
        scoreBand: fund.scoreBand,
        score2023: fund.score2023,
        score2025: fund.score2025,
        scoreGap: fund.scoreGap,
        rank2023: fund.rank2023,
        rank2025: fund.rank2025,
        consensusRank: fund.consensusRank,
        quadrant: fund.quadrant,
        actionFlag: fund.actionFlag,
        primaryDriver: fund.primaryDriver,
      },
      categoryPeerCount: categoryFunds.length,
      breakdown,
    });
  });

  // ============ REPLACEMENT WORKBENCH ============
  app.get("/api/replacement-workbench", (req, res) => {
    const symbol = req.query.symbol as string;
    if (!symbol) {
      return res.status(400).json({ error: "Symbol query parameter required" });
    }

    const topN = parseInt(req.query.topN as string) || 10;
    const result = buildReplacementWorkbench(symbol, topN);

    if (!result) {
      return res.status(404).json({ error: `Fund ${symbol} not found` });
    }

    res.json(result);
  });

  // Standalone printable committee brief HTML
  app.get("/api/replacement-workbench/brief/:symbol", (req, res) => {
    const symbol = req.params.symbol;
    const topN = parseInt(req.query.topN as string) || 10;
    const result = buildReplacementWorkbench(symbol, topN);

    if (!result) {
      return res.status(404).send(`Fund ${symbol} not found`);
    }

    const latestRun = storage.getLatestScoringRun();
    const runDate = latestRun?.runDate || new Date().toISOString().split("T")[0];
    const html = renderReplacementBriefHtml(result, runDate);

    res.setHeader("Content-Type", "text/html; charset=utf-8");
    res.send(html);
  });

  // ============ SCORING RUNS & SNAPSHOTS ============
  app.get("/api/runs", (_req, res) => {
    const dbRuns = storage.getScoringRuns();
    const diskRuns = listRunArchives();
    res.json({
      latestRunDate: loadLatestRunDate(),
      dbRuns,
      diskRuns,
    });
  });

  app.get("/api/runs/:runDate/dual-table", (req, res) => {
    const runDate = req.params.runDate;
    const table = loadRunDualTable(runDate);
    if (!table) {
      return res.status(404).json({ error: `Run ${runDate} not found` });
    }
    res.json(table);
  });

  app.get("/api/runs/:runDate/export/excel", async (req, res) => {
    try {
      const runDate = req.params.runDate;
      const table = loadRunDualTable(runDate);
      if (!table) {
        return res.status(404).json({ error: `Run ${runDate} not found` });
      }

      const validation = buildValidationSummary(table);
      const buffer = await generateAuditWorkbook(
        table,
        {
          runDate,
          rowCount: table.length,
          joinedCount: validation.joinedCount,
          scoreSystemVersion: "dual-2023-combined+2025-split",
        },
        validation
      );

      res.setHeader("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
      res.setHeader("Content-Disposition", `attachment; filename=fundscore_audit_workbook_${runDate}.xlsx`);
      res.send(buffer);
    } catch (err: any) {
      console.error("Error exporting run Excel:", err);
      res.status(500).json({ error: err.message || "Failed to generate Excel export" });
    }
  });

  // ============ DASHBOARD STATS ============
  app.get("/api/stats", (_req, res) => {
    const stats = storage.getFundStats();
    const allFunds = storage.getAllFunds().filter(f => f.score !== null);

    // Score distribution for histogram (buckets of 5)
    const histogram: { range: string; count: number }[] = [];
    for (let i = 0; i < 100; i += 5) {
      const count = allFunds.filter(f => f.score! >= i && f.score! < i + 5).length;
      histogram.push({ range: `${i}-${i + 5}`, count });
    }
    const hundredCount = allFunds.filter(f => f.score! >= 100).length;
    if (hundredCount > 0) {
      histogram[histogram.length - 1].count += hundredCount;
    }

    // Category breakdown (avg score per category)
    const catMap = new Map<string, { total: number; count: number }>();
    for (const f of allFunds) {
      const cat = f.categoryName || "Uncategorized";
      if (!catMap.has(cat)) catMap.set(cat, { total: 0, count: 0 });
      const entry = catMap.get(cat)!;
      entry.total += f.score!;
      entry.count++;
    }
    const categoryBreakdown = Array.from(catMap.entries())
      .map(([name, data]) => ({ name, avgScore: Math.round(data.total / data.count * 100) / 100, count: data.count }))
      .sort((a, b) => b.avgScore - a.avgScore);

    res.json({
      ...stats,
      strongPct: stats.total > 0 ? Math.round(stats.strongCount / stats.total * 10000) / 100 : 0,
      weakPct: stats.total > 0 ? Math.round(stats.weakCount / stats.total * 10000) / 100 : 0,
      histogram,
      categoryBreakdown,
    });
  });

  // Top/Bottom funds
  app.get("/api/funds/top/:limit", (req, res) => {
    const limit = parseInt(req.params.limit) || 10;
    res.json(storage.getTopFunds(limit));
  });

  app.get("/api/funds/bottom/:limit", (req, res) => {
    const limit = parseInt(req.params.limit) || 10;
    res.json(storage.getBottomFunds(limit));
  });

  // ============ ALL FUNDS (Batch Scores) ============
  app.get("/api/funds", (_req, res) => {
    res.json(storage.getAllFunds());
  });

  // ============ FUND LOOKUP ============
  app.get("/api/funds/lookup/:symbol", (req, res) => {
    const symbol = req.params.symbol.toUpperCase();
    const fund = storage.getFundBySymbol(symbol);
    if (!fund) {
      return res.status(404).json({ error: "Fund not found" });
    }

    const categoryFunds = fund.categoryName
      ? storage.getFundsByCategory(fund.categoryName)
      : [fund];

    const breakdown = getFundBreakdown(fund, categoryFunds);

    const peers = categoryFunds
      .filter(f => f.score !== null)
      .sort((a, b) => (b.score || 0) - (a.score || 0))
      .slice(0, 20)
      .map(f => ({
        symbol: f.symbol,
        name: f.name,
        score: f.score,
        scoreBand: f.scoreBand,
        score2023: f.score2023,
        score2025: f.score2025,
        consensusRank: f.consensusRank,
        quadrant: f.quadrant,
        actionFlag: f.actionFlag,
        netExpenseRatio: f.netExpenseRatio,
      }));

    res.json({ fund, breakdown, peers });
  });

  // ============ CATEGORIES ============
  app.get("/api/categories", (_req, res) => {
    res.json(storage.getCategories());
  });

  app.get("/api/categories/:name", (req, res) => {
    const name = req.params.name;
    const catFunds = storage.getFundsByCategory(name);
    if (catFunds.length === 0) {
      return res.status(404).json({ error: "Category not found" });
    }

    const scored = catFunds.filter(f => f.score !== null);
    const scores = scored.map(f => f.score!);
    const avg = scores.length > 0 ? scores.reduce((a, b) => a + b, 0) / scores.length : 0;
    const strongCount = scores.filter(s => s >= 80).length;
    const weakCount = scores.filter(s => s < 60).length;

    const distribution: { range: string; count: number }[] = [];
    for (let i = 0; i < 100; i += 10) {
      const count = scores.filter(s => s >= i && s < i + 10).length;
      distribution.push({ range: `${i}-${i + 10}`, count });
    }

    const topFunds = scored.sort((a, b) => (b.score || 0) - (a.score || 0)).slice(0, 10);
    const bottomFunds = scored.sort((a, b) => (a.score || 0) - (b.score || 0)).slice(0, 10);

    res.json({
      name,
      totalFunds: catFunds.length,
      scoredFunds: scored.length,
      avgScore: Math.round(avg * 100) / 100,
      strongCount,
      weakCount,
      distribution,
      topFunds,
      bottomFunds: bottomFunds.reverse(),
      allFunds: scored.sort((a, b) => (b.score || 0) - (a.score || 0)),
    });
  });

  // ============ MONITORING ============
  app.get("/api/monitoring", (_req, res) => {
    const holdings = storage.getMonitoringHoldings();
    const enriched = holdings.map(h => {
      const fund = storage.getFundBySymbol(h.symbol);
      return {
        ...h,
        currentScore: fund?.score || null,
        currentExpenseRatio: fund?.netExpenseRatio || null,
        fundName: fund?.name || "Unknown",
        categoryName: fund?.categoryName || null,
        scoreBand: fund?.scoreBand || null,
        score2023: fund?.score2023 || null,
        score2025: fund?.score2025 || null,
        consensusRank: fund?.consensusRank || null,
        quadrant: fund?.quadrant || null,
        actionFlag: fund?.actionFlag || null,
        categoryPercentile: fund?.categoryPercentile || null,
      };
    });
    res.json(enriched);
  });

  app.post("/api/monitoring", (req, res) => {
    const { symbol } = req.body;
    if (!symbol) return res.status(400).json({ error: "Symbol required" });

    const fund = storage.getFundBySymbol(symbol.toUpperCase());
    if (!fund) return res.status(404).json({ error: "Fund not found" });

    const holding = storage.addMonitoringHolding({
      symbol: fund.symbol,
      baselineScore: fund.score,
      baselineExpenseRatio: fund.netExpenseRatio,
      addedAt: new Date().toISOString(),
    });
    res.json(holding);
  });

  app.delete("/api/monitoring/:id", (req, res) => {
    const id = parseInt(req.params.id);
    storage.removeMonitoringHolding(id);
    res.json({ success: true });
  });

  app.post("/api/monitoring/:id/baseline", (req, res) => {
    const id = parseInt(req.params.id);
    const holding = storage.getMonitoringHoldings().find(h => h.id === id);
    if (!holding) return res.status(404).json({ error: "Holding not found" });

    const fund = storage.getFundBySymbol(holding.symbol);
    if (!fund) return res.status(404).json({ error: "Fund not found" });

    storage.updateBaseline(id, fund.score || 0, fund.netExpenseRatio || 0);
    res.json({ success: true });
  });

  // ============ PREFLIGHT CSV VALIDATION ============
  app.post("/api/upload/validate", upload.single("file"), (req, res) => {
    if (!req.file) return res.status(400).json({ error: "No file uploaded" });

    try {
      const csvText = fs.readFileSync(req.file.path, "utf-8");
      fs.unlinkSync(req.file.path);
      const schema = (req.query.schema as "2025" | "2023") || (req.body?.schema as "2025" | "2023") || "2025";
      const validation = validateYChartsCSV(csvText, schema);
      res.json(validation);
    } catch (err: any) {
      if (req.file && fs.existsSync(req.file.path)) {
        fs.unlinkSync(req.file.path);
      }
      res.status(500).json({ error: err.message || "Failed to validate CSV" });
    }
  });

  // ============ CSV UPLOAD (PAIRED OR INDIVIDUAL) ============
  app.post(
    "/api/upload",
    upload.fields([
      { name: "file2025", maxCount: 1 },
      { name: "file2023", maxCount: 1 },
      { name: "file", maxCount: 1 },
    ]),
    (req, res) => {
      const files = req.files as { [fieldname: string]: Express.Multer.File[] } | undefined;
      const file2025 = files?.["file2025"]?.[0] || files?.["file"]?.[0] || (req.file as Express.Multer.File | undefined);
      const file2023 = files?.["file2023"]?.[0];

      if (!file2025 && !file2023) {
        return res.status(400).json({ error: "No CSV files uploaded. Please upload a 2025 or 2023 YCharts export." });
      }

      const runDate = req.body?.runDate || new Date().toISOString().split("T")[0];
      const runLabel = req.body?.runLabel || `Committee Run ${runDate}`;

      try {
        let csv2025Text: string | null = null;
        let csv2023Text: string | null = null;

        if (file2025) {
          csv2025Text = fs.readFileSync(file2025.path, "utf-8");
          const val2025 = validateYChartsCSV(csv2025Text, "2025");
          if (val2025.failed) {
            fs.unlinkSync(file2025.path);
            if (file2023 && fs.existsSync(file2023.path)) fs.unlinkSync(file2023.path);
            return res.status(400).json({
              error: "2025 CSV validation failed",
              details: val2025.errors,
            });
          }
        }

        if (file2023) {
          csv2023Text = fs.readFileSync(file2023.path, "utf-8");
          const val2023 = validateYChartsCSV(csv2023Text, "2023");
          if (val2023.failed) {
            if (file2025 && fs.existsSync(file2025.path)) fs.unlinkSync(file2025.path);
            fs.unlinkSync(file2023.path);
            return res.status(400).json({
              error: "2023 CSV validation failed",
              details: val2023.errors,
            });
          }
        }

        // Case A: 2025 provided (or both)
        let scored2025: any[] = [];
        if (csv2025Text && file2025) {
          const parsed = Papa.parse(csv2025Text, { header: true, skipEmptyLines: true });
          const fundRows: InsertFund[] = parsed.data
            .map((row: any) => parseCSVRow(row))
            .filter((f: InsertFund) => f.symbol && f.name);

          const batch = storage.createUploadBatch({
            filename: file2025.originalname || "ycharts_2025.csv",
            rowCount: fundRows.length,
            uploadedAt: new Date().toISOString(),
          });

          storage.clearFunds();
          const fundsWithBatch = fundRows.map(f => ({ ...f, uploadBatchId: batch.id }));
          storage.insertFunds(fundsWithBatch);

          const allFunds = storage.getAllFunds();
          scored2025 = scoreAllFunds(allFunds);
          storage.updateFundScores(scored2025);
        } else {
          // If only 2023 uploaded, use existing 2025 funds
          const allFunds = storage.getAllFunds();
          scored2025 = scoreAllFunds(allFunds);
        }

        // Locate or read 2023 data
        const seed2023Paths = [
          path.join(process.cwd(), "server", "data", "scores_2023.csv"),
          path.resolve("server", "data", "scores_2023.csv"),
          path.resolve("data", "scores_2023.csv"),
          path.resolve("..", "streamlit", "scores_2023.csv"),
        ];
        const existing2023Path = seed2023Paths.find(p => fs.existsSync(p)) || null;

        if (!csv2023Text && existing2023Path) {
          csv2023Text = fs.readFileSync(existing2023Path, "utf-8");
        }

        let dualCount = 0;
        let scored2023Count = 0;

        if (csv2023Text) {
          // If a new 2023 file was uploaded, persist it to server/data/scores_2023.csv
          if (file2023) {
            const dest2023 = path.resolve("server", "data", "scores_2023.csv");
            fs.mkdirSync(path.dirname(dest2023), { recursive: true });
            fs.writeFileSync(dest2023, csv2023Text, "utf-8");
          }

          const parsed2023 = Papa.parse(csv2023Text, { header: true, dynamicTyping: true, skipEmptyLines: true });
          const scored2023 = score2023Funds(parsed2023.data as any[]);
          scored2023Count = scored2023.length;

          if (scored2025.length > 0) {
            const dualTable = buildDualScoreTable(scored2025, scored2023, "inner");
            storage.updateFundDualScores(dualTable);
            dualCount = dualTable.length;

            // Archive run
            const hash2025 = csv2025Text ? computeSHA256(csv2025Text) : undefined;
            const hash2023 = computeSHA256(csv2023Text);
            const archiveResult = saveRunArchive(runDate, dualTable, { hash2025, hash2023 });

            storage.createScoringRun({
              runDate,
              label: runLabel,
              createdAt: new Date().toISOString(),
              rowCount: dualTable.length,
              joinedCount: archiveResult.validation.joinedCount,
              hash2025,
              hash2023,
              validationJson: JSON.stringify(archiveResult.validation),
            });
          }
        }

        // Cleanup temp files
        if (file2025 && fs.existsSync(file2025.path)) fs.unlinkSync(file2025.path);
        if (file2023 && fs.existsSync(file2023.path)) fs.unlinkSync(file2023.path);

        // Snapshot
        const now = new Date();
        const snapshotLabel = now.toLocaleDateString("en-US", { month: "long", year: "numeric" });
        storage.createSnapshot(runDate, snapshotLabel);

        res.json({
          success: true,
          runDate,
          runLabel,
          scored2025Count: scored2025.length,
          scored2023Count,
          dualScoredCount: dualCount,
          uploadedFiles: {
            has2025: !!file2025,
            has2023: !!file2023,
          },
        });
      } catch (err: any) {
        if (file2025 && fs.existsSync(file2025.path)) fs.unlinkSync(file2025.path);
        if (file2023 && fs.existsSync(file2023.path)) fs.unlinkSync(file2023.path);
        res.status(500).json({ error: err.message || "Failed to process upload" });
      }
    }
  );

  app.get("/api/upload/preview", (_req, res) => {
    res.json(storage.getUploadBatches());
  });

  // ============ SNAPSHOTS / HISTORY ============
  app.post("/api/snapshots", (req, res) => {
    const label = req.body?.label || new Date().toLocaleDateString("en-US", { month: "long", year: "numeric" });
    const date = new Date().toISOString().split("T")[0];
    const result = storage.createSnapshot(date, label);
    res.json(result);
  });

  app.get("/api/snapshots", (_req, res) => {
    res.json(storage.getSnapshots());
  });

  app.get("/api/snapshots/compare", (req, res) => {
    const from = req.query.from as string;
    const to = req.query.to as string;
    if (!from || !to) return res.status(400).json({ error: "from and to query params required" });
    res.json(storage.getSnapshotComparison(from, to));
  });

  app.get("/api/snapshots/:date", (req, res) => {
    const date = req.params.date;
    const scores = storage.getSnapshotScores(date);
    if (scores.length === 0) return res.status(404).json({ error: "Snapshot not found" });
    res.json(scores);
  });

  app.get("/api/history/:symbol", (req, res) => {
    const symbol = req.params.symbol.toUpperCase();
    res.json(storage.getFundHistory(symbol));
  });

  // ============ CSV EXPORT ============
  app.get("/api/export/csv", (_req, res) => {
    const allFunds = storage.getAllFunds();
    const csv = Papa.unparse(allFunds.map(f => ({
      Symbol: f.symbol,
      Name: f.name,
      Category: f.categoryName,
      "Fund Type": f.isIndexFund ? "Passive" : "Active",
      "Expense Ratio": f.netExpenseRatio,
      Score: f.score,
      "Score Band": f.scoreBand,
      "Category Percentile": f.categoryPercentile,
      "Score 2023": f.score2023,
      "Score 2025": f.score2025,
      "Score Gap": f.scoreGap,
      "Consensus Rank": f.consensusRank,
      Quadrant: f.quadrant,
      "Action Flag": f.actionFlag,
      "Primary Driver": f.primaryDriver,
    })));

    res.setHeader("Content-Type", "text/csv");
    res.setHeader("Content-Disposition", "attachment; filename=fund_scores.csv");
    res.send(csv);
  });

  // PDF report
  app.get("/api/export/pdf", (_req, res) => {
    const categoriesParam = _req.query.categories as string | undefined;
    const categoryFilter = categoriesParam ? categoriesParam.split(",").map(c => c.trim()) : undefined;

    const allFunds = storage.getAllFunds().filter(f => f.score !== null);
    const stats = storage.getFundStats();

    const pdfBuffer = generatePdfReport(allFunds, stats, categoryFilter);

    res.setHeader("Content-Type", "application/pdf");
    res.setHeader("Content-Disposition", "attachment; filename=fund_scoring_report.pdf");
    res.send(pdfBuffer);
  });

  return httpServer;
}
