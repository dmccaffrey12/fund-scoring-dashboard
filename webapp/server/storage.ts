import {
  type Fund, type InsertFund, funds,
  type MonitoringHolding, type InsertMonitoringHolding, monitoringHoldings,
  type UploadBatch, type InsertUploadBatch, uploadBatches,
  type ScoreSnapshot, type InsertScoreSnapshot, scoreSnapshots,
} from "@shared/schema";
import { drizzle } from "drizzle-orm/better-sqlite3";
import Database from "better-sqlite3";
import { eq, desc, asc, sql, and, inArray } from "drizzle-orm";

const sqlite = new Database("data.db");
sqlite.pragma("journal_mode = WAL");

// Create score_snapshots table if it doesn't exist
sqlite.exec(`
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
  )
`);

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
  getTopFunds(limit: number): Fund[];
  getBottomFunds(limit: number): Fund[];
  getFundStats(): { total: number; avgScore: number; strongCount: number; weakCount: number };

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
    return db.select().from(funds).where(eq(funds.symbol, symbol)).get();
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
