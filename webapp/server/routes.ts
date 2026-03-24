import type { Express } from "express";
import { createServer, type Server } from "http";
import { storage } from "./storage";
import { scoreAllFunds, getFundBreakdown } from "./scoring";
import multer from "multer";
import Papa from "papaparse";
import fs from "fs";
import path from "path";
import type { InsertFund } from "@shared/schema";

const upload = multer({ dest: "/tmp/uploads/" });

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
    uploadBatchId: null,
  };
}

function seedIfEmpty() {
  const allFunds = storage.getAllFunds();
  if (allFunds.length > 0) return;

  // Try multiple possible paths for the seed CSV
  const possiblePaths = [
    path.join(process.cwd(), "server", "data", "seed.csv"),
    path.resolve("server", "data", "seed.csv"),
    path.resolve("data", "seed.csv"),
  ];
  const csvPath = possiblePaths.find(p => fs.existsSync(p)) || null;
  
  if (!csvPath) {
    console.log("No seed CSV found, skipping seed.");
    return;
  }

  console.log("Seeding database from CSV...");
  const csvText = fs.readFileSync(csvPath, "utf-8");
  const parsed = Papa.parse(csvText, { header: true, skipEmptyLines: true });
  
  const fundRows: InsertFund[] = parsed.data
    .map((row: any) => parseCSVRow(row))
    .filter((f: InsertFund) => f.symbol && f.name);

  storage.insertFunds(fundRows);

  // Score all funds
  const allFundsAfterInsert = storage.getAllFunds();
  const scores = scoreAllFunds(allFundsAfterInsert);
  storage.updateFundScores(scores);

  console.log(`Seeded and scored ${scores.length} funds.`);
}

export async function registerRoutes(
  httpServer: Server,
  app: Express
): Promise<Server> {
  // Seed on startup
  seedIfEmpty();

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
    // 100 exactly
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

    // Category peers sorted by score
    const peers = categoryFunds
      .filter(f => f.score !== null)
      .sort((a, b) => (b.score || 0) - (a.score || 0))
      .slice(0, 20)
      .map(f => ({
        symbol: f.symbol,
        name: f.name,
        score: f.score,
        scoreBand: f.scoreBand,
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

    // Distribution
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
    // Enrich with current fund data
    const enriched = holdings.map(h => {
      const fund = storage.getFundBySymbol(h.symbol);
      return {
        ...h,
        currentScore: fund?.score || null,
        currentExpenseRatio: fund?.netExpenseRatio || null,
        fundName: fund?.name || "Unknown",
        categoryName: fund?.categoryName || null,
        scoreBand: fund?.scoreBand || null,
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

  // ============ CSV UPLOAD ============
  app.post("/api/upload", upload.single("file"), (req, res) => {
    if (!req.file) return res.status(400).json({ error: "No file uploaded" });

    try {
      const csvText = fs.readFileSync(req.file.path, "utf-8");
      const parsed = Papa.parse(csvText, { header: true, skipEmptyLines: true });

      const fundRows: InsertFund[] = parsed.data
        .map((row: any) => parseCSVRow(row))
        .filter((f: InsertFund) => f.symbol && f.name);

      // Create upload batch
      const batch = storage.createUploadBatch({
        filename: req.file.originalname || "upload.csv",
        rowCount: fundRows.length,
        uploadedAt: new Date().toISOString(),
      });

      // Clear existing and insert new
      storage.clearFunds();
      const fundsWithBatch = fundRows.map(f => ({ ...f, uploadBatchId: batch.id }));
      storage.insertFunds(fundsWithBatch);

      // Score all
      const allFunds = storage.getAllFunds();
      const scores = scoreAllFunds(allFunds);
      storage.updateFundScores(scores);

      // Cleanup temp file
      fs.unlinkSync(req.file.path);

      res.json({
        success: true,
        batchId: batch.id,
        rowCount: fundRows.length,
        scoredCount: scores.length,
      });
    } catch (err: any) {
      res.status(500).json({ error: err.message });
    }
  });

  app.get("/api/upload/preview", upload.single("file"), (req, res) => {
    // Just return upload batch history
    res.json(storage.getUploadBatches());
  });

  // ============ EXPORT ============
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
    })));

    res.setHeader("Content-Type", "text/csv");
    res.setHeader("Content-Disposition", "attachment; filename=fund_scores.csv");
    res.send(csv);
  });

  return httpServer;
}
