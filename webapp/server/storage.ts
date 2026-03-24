import {
  type Fund, type InsertFund, funds,
  type MonitoringHolding, type InsertMonitoringHolding, monitoringHoldings,
  type UploadBatch, type InsertUploadBatch, uploadBatches,
} from "@shared/schema";
import { drizzle } from "drizzle-orm/better-sqlite3";
import Database from "better-sqlite3";
import { eq, desc, asc, sql, and, inArray } from "drizzle-orm";

const sqlite = new Database("data.db");
sqlite.pragma("journal_mode = WAL");

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
}

export const storage = new DatabaseStorage();
