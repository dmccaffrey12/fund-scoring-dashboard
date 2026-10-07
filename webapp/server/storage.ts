import {
  type Fund, type InsertFund, funds,
  type MonitoringHolding, type InsertMonitoringHolding, monitoringHoldings,
  type UploadBatch, type InsertUploadBatch, uploadBatches,
  type ScoreSnapshot, type InsertScoreSnapshot, scoreSnapshots,
  type ScoringRun, type InsertScoringRun, scoringRuns,
} from "@shared/schema";
import { drizzle } from "drizzle-orm/better-sqlite3";
import Database from "better-sqlite3";
import { eq, desc, asc, sql, and } from "drizzle-orm";
import fs from "fs";
import path from "path";
import type { DualScoreRow } from "./scoring";

const dbPath = process.env.DATABASE_PATH || "data.db";
const absoluteDbDir = path.dirname(path.resolve(dbPath));
fs.mkdirSync(absoluteDbDir, { recursive: true });

const sqlite = new Database(dbPath);
sqlite.pragma("journal_mode = WAL");

// Initialize tables
sqlite.exec(`
  CREATE TABLE IF NOT EXISTS upload_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    uploaded_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS scoring_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL UNIQUE,
    label TEXT,
    created_at TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    joined_count INTEGER NOT NULL,
    hash_2025 TEXT,
    hash_2023 TEXT,
    validation_json TEXT
  );

  CREATE TABLE IF NOT EXISTS score_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date TEXT NOT NULL,
    snapshot_label TEXT,
    symbol TEXT NOT NULL,
    score REAL,
    score_band TEXT,
    category_name TEXT,
    is_index_fund INTEGER DEFAULT 0,
    upload_batch_id INTEGER
  );

  CREATE TABLE IF NOT EXISTS monitoring_holdings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    model_name TEXT,
    target_weight REAL,
    sleeve TEXT,
    baseline_score REAL,
    baseline_expense_ratio REAL,
    added_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS funds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    is_index_fund INTEGER NOT NULL DEFAULT 0,
    category_name TEXT,
    net_expense_ratio REAL,
    tracking_error_3y REAL,
    tracking_error_5y REAL,
    tracking_error_10y REAL,
    r_squared_5y REAL,
    share_class_aum REAL,
    downside_5y REAL,
    downside_10y REAL,
    max_drawdown_5y REAL,
    max_drawdown_10y REAL,
    info_ratio_3y REAL,
    info_ratio_5y REAL,
    info_ratio_10y REAL,
    sortino_3y REAL,
    sortino_5y REAL,
    sortino_10y REAL,
    upside_3y REAL,
    upside_5y REAL,
    upside_10y REAL,
    returns_3y REAL,
    returns_5y REAL,
    returns_10y REAL,
    oldest_share_symbol TEXT,
    share_class TEXT,
    score REAL,
    score_band TEXT,
    category_percentile REAL,
    score_2023 REAL,
    score_2025 REAL,
    score_gap REAL,
    rank_2023 INTEGER,
    rank_2025 INTEGER,
    consensus_rank INTEGER,
    score_band_2023 TEXT,
    score_band_2025 TEXT,
    quadrant TEXT,
    action_flag TEXT,
    primary_driver TEXT,
    data_coverage_2023 REAL,
    data_coverage_2025 REAL,
    upload_batch_id INTEGER
  );
`);

// Safe column migrations for existing SQLite databases
const columnsToAdd = [
  "ALTER TABLE funds ADD COLUMN score_2023 REAL",
  "ALTER TABLE funds ADD COLUMN score_2025 REAL",
  "ALTER TABLE funds ADD COLUMN score_gap REAL",
  "ALTER TABLE funds ADD COLUMN rank_2023 INTEGER",
  "ALTER TABLE funds ADD COLUMN rank_2025 INTEGER",
  "ALTER TABLE funds ADD COLUMN consensus_rank INTEGER",
  "ALTER TABLE funds ADD COLUMN score_band_2023 TEXT",
  "ALTER TABLE funds ADD COLUMN score_band_2025 TEXT",
  "ALTER TABLE funds ADD COLUMN quadrant TEXT",
  "ALTER TABLE funds ADD COLUMN action_flag TEXT",
  "ALTER TABLE funds ADD COLUMN primary_driver TEXT",
  "ALTER TABLE funds ADD COLUMN data_coverage_2023 REAL",
  "ALTER TABLE funds ADD COLUMN data_coverage_2025 REAL",
  "ALTER TABLE monitoring_holdings ADD COLUMN model_name TEXT",
  "ALTER TABLE monitoring_holdings ADD COLUMN target_weight REAL",
  "ALTER TABLE monitoring_holdings ADD COLUMN sleeve TEXT",
];

for (const alterSql of columnsToAdd) {
  try {
    sqlite.exec(alterSql);
  } catch {
    // Column already exists, ignore
  }
}

export const db = drizzle(sqlite);

export interface IStorage {
  // Funds
  getAllFunds(): Fund[];
  getFundBySymbol(symbol: string): Fund | undefined;
  getFundsByCategory(category: string): Fund[];
  getCategories(): string[];
  insertFunds(data: InsertFund[]): void;
  clearFunds(): void;
  updateFundScores(updates: { id: number; score: number; scoreBand: string; categoryPercentile: number }[]): void;
  updateFundDualScores(dualRows: DualScoreRow[]): void;
  getTopFunds(limit: number): Fund[];
  getBottomFunds(limit: number): Fund[];
  getFundStats(): { total: number; avgScore: number; strongCount: number; weakCount: number };

  // Scoring Runs
  createScoringRun(run: InsertScoringRun): ScoringRun;
  getScoringRuns(): ScoringRun[];
  getLatestScoringRun(): ScoringRun | undefined;

  // Monitoring
  getMonitoringHoldings(): MonitoringHolding[];
  addMonitoringHolding(holding: InsertMonitoringHolding): MonitoringHolding;
  removeMonitoringHolding(id: number): void;
  updateBaseline(id: number, score: number, expense: number): void;

  // Upload batches
  createUploadBatch(batch: InsertUploadBatch): UploadBatch;
  getUploadBatches(): UploadBatch[];

  // Snapshots
  createSnapshot(date: string, label: string): { date: string; label: string; count: number };
  getSnapshots(): { snapshotDate: string; snapshotLabel: string | null; fundCount: number }[];
  getSnapshotScores(snapshotDate: string): ScoreSnapshot[];
  getFundHistory(symbol: string): ScoreSnapshot[];
  getSnapshotComparison(fromDate: string, toDate: string): {
    symbol: string;
    categoryName: string | null;
    fromScore: number | null;
    toScore: number | null;
    delta: number;
    fromBand: string | null;
    toBand: string | null;
  }[];
}

export class DatabaseStorage implements IStorage {
  getAllFunds(): Fund[] {
    return db.select().from(funds).all();
  }

  getFundBySymbol(symbol: string): Fund | undefined {
    return db.select().from(funds).where(eq(funds.symbol, symbol.toUpperCase())).get();
  }

  getFundsByCategory(category: string): Fund[] {
    return db.select().from(funds).where(eq(funds.categoryName, category)).all();
  }

  getCategories(): string[] {
    const rows = db.selectDistinct({ categoryName: funds.categoryName }).from(funds).all();
    return rows.map(r => r.categoryName).filter((c): c is string => c !== null).sort();
  }

  insertFunds(data: InsertFund[]): void {
    // Batch insert in chunks of 100
    for (let i = 0; i < data.length; i += 100) {
      const chunk = data.slice(i, i + 100);
      db.insert(funds).values(chunk).run();
    }
  }

  clearFunds(): void {
    db.delete(funds).run();
  }

  updateFundScores(updates: { id: number; score: number; scoreBand: string; categoryPercentile: number }[]): void {
    const stmt = sqlite.prepare(
      "UPDATE funds SET score = ?, score_band = ?, category_percentile = ? WHERE id = ?"
    );
    const txn = sqlite.transaction(() => {
      for (const u of updates) {
        stmt.run(u.score, u.scoreBand, u.categoryPercentile, u.id);
      }
    });
    txn();
  }

  updateFundDualScores(dualRows: DualScoreRow[]): void {
    const stmt = sqlite.prepare(`
      UPDATE funds SET
        score_2023 = ?,
        score_2025 = ?,
        score_gap = ?,
        rank_2023 = ?,
        rank_2025 = ?,
        consensus_rank = ?,
        score_band_2023 = ?,
        score_band_2025 = ?,
        quadrant = ?,
        action_flag = ?,
        primary_driver = ?,
        data_coverage_2023 = ?,
        data_coverage_2025 = ?
      WHERE UPPER(symbol) = UPPER(?)
    `);

    const txn = sqlite.transaction(() => {
      for (const r of dualRows) {
        stmt.run(
          r.Score_2023_Final,
          r.Score_2025_Final,
          r.Score_Gap,
          r.Rank_2023,
          r.Rank_2025,
          r.Consensus_Rank,
          r.Score_Band_2023,
          r.Score_Band_2025,
          r.Quadrant,
          r.Action_Flag,
          r.Primary_Driver,
          r.Data_Coverage_2023,
          r.Data_Coverage_2025,
          r.Symbol
        );
      }
    });
    txn();
  }

  getTopFunds(limit: number): Fund[] {
    return db.select().from(funds).where(sql`${funds.score} IS NOT NULL`).orderBy(desc(funds.score)).limit(limit).all();
  }

  getBottomFunds(limit: number): Fund[] {
    return db.select().from(funds).where(sql`${funds.score} IS NOT NULL`).orderBy(asc(funds.score)).limit(limit).all();
  }

  getFundStats(): { total: number; avgScore: number; strongCount: number; weakCount: number } {
    const result = sqlite.prepare(`
      SELECT 
        COUNT(*) as total,
        AVG(score) as avgScore,
        SUM(CASE WHEN score >= 80 THEN 1 ELSE 0 END) as strongCount,
        SUM(CASE WHEN score < 60 THEN 1 ELSE 0 END) as weakCount
      FROM funds WHERE score IS NOT NULL
    `).get() as any;
    return {
      total: result.total || 0,
      avgScore: result.avgScore || 0,
      strongCount: result.strongCount || 0,
      weakCount: result.weakCount || 0,
    };
  }

  // Scoring Runs
  createScoringRun(run: InsertScoringRun): ScoringRun {
    return db.insert(scoringRuns).values(run).returning().get();
  }

  getScoringRuns(): ScoringRun[] {
    return db.select().from(scoringRuns).orderBy(desc(scoringRuns.runDate)).all();
  }

  getLatestScoringRun(): ScoringRun | undefined {
    return db.select().from(scoringRuns).orderBy(desc(scoringRuns.runDate)).limit(1).get();
  }

  // Monitoring
  getMonitoringHoldings(): MonitoringHolding[] {
    return db.select().from(monitoringHoldings).all();
  }

  addMonitoringHolding(holding: InsertMonitoringHolding): MonitoringHolding {
    return db.insert(monitoringHoldings).values(holding).returning().get();
  }

  removeMonitoringHolding(id: number): void {
    db.delete(monitoringHoldings).where(eq(monitoringHoldings.id, id)).run();
  }

  updateBaseline(id: number, score: number, expense: number): void {
    db.update(monitoringHoldings)
      .set({ baselineScore: score, baselineExpenseRatio: expense })
      .where(eq(monitoringHoldings.id, id))
      .run();
  }

  // Upload batches
  createUploadBatch(batch: InsertUploadBatch): UploadBatch {
    return db.insert(uploadBatches).values(batch).returning().get();
  }

  getUploadBatches(): UploadBatch[] {
    return db.select().from(uploadBatches).orderBy(desc(uploadBatches.id)).all();
  }

  // Snapshots
  createSnapshot(date: string, label: string): { date: string; label: string; count: number } {
    const allFunds = this.getAllFunds().filter(f => f.score !== null);
    const rows: InsertScoreSnapshot[] = allFunds.map(f => ({
      snapshotDate: date,
      snapshotLabel: label,
      symbol: f.symbol,
      score: f.score,
      scoreBand: f.scoreBand,
      categoryName: f.categoryName,
      isIndexFund: f.isIndexFund,
      uploadBatchId: f.uploadBatchId,
    }));

    for (let i = 0; i < rows.length; i += 100) {
      const chunk = rows.slice(i, i + 100);
      db.insert(scoreSnapshots).values(chunk).run();
    }

    return { date, label, count: rows.length };
  }

  getSnapshots(): { snapshotDate: string; snapshotLabel: string | null; fundCount: number }[] {
    const rows = sqlite.prepare(`
      SELECT snapshot_date, snapshot_label, COUNT(*) as fund_count
      FROM score_snapshots
      GROUP BY snapshot_date
      ORDER BY snapshot_date DESC
    `).all() as any[];
    return rows.map(r => ({
      snapshotDate: r.snapshot_date,
      snapshotLabel: r.snapshot_label,
      fundCount: r.fund_count,
    }));
  }

  getSnapshotScores(snapshotDate: string): ScoreSnapshot[] {
    return db.select().from(scoreSnapshots)
      .where(eq(scoreSnapshots.snapshotDate, snapshotDate))
      .all();
  }

  getFundHistory(symbol: string): ScoreSnapshot[] {
    return db.select().from(scoreSnapshots)
      .where(eq(scoreSnapshots.symbol, symbol.toUpperCase()))
      .orderBy(asc(scoreSnapshots.snapshotDate))
      .all();
  }

  getSnapshotComparison(fromDate: string, toDate: string) {
    const rows = sqlite.prepare(`
      SELECT
        COALESCE(f.symbol, t.symbol) as symbol,
        COALESCE(t.category_name, f.category_name) as category_name,
        f.score as from_score,
        t.score as to_score,
        COALESCE(t.score, 0) - COALESCE(f.score, 0) as delta,
        f.score_band as from_band,
        t.score_band as to_band
      FROM score_snapshots f
      FULL OUTER JOIN score_snapshots t
        ON f.symbol = t.symbol AND t.snapshot_date = ?
      WHERE f.snapshot_date = ?
      ORDER BY ABS(COALESCE(t.score, 0) - COALESCE(f.score, 0)) DESC
    `).all(toDate, fromDate) as any[];
    return rows.map(r => ({
      symbol: r.symbol,
      categoryName: r.category_name,
      fromScore: r.from_score,
      toScore: r.to_score,
      delta: r.delta,
      fromBand: r.from_band,
      toBand: r.to_band,
    }));
  }
}

export const storage = new DatabaseStorage();
