import { sqliteTable, text, integer, real } from "drizzle-orm/sqlite-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod";

// Scored funds table — stores all fund data + computed scores
export const funds = sqliteTable("funds", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  symbol: text("symbol").notNull(),
  name: text("name").notNull(),
  isIndexFund: integer("is_index_fund", { mode: "boolean" }).notNull().default(false),
  categoryName: text("category_name"),
  // Raw metrics
  netExpenseRatio: real("net_expense_ratio"),
  trackingError3Y: real("tracking_error_3y"),
  trackingError5Y: real("tracking_error_5y"),
  trackingError10Y: real("tracking_error_10y"),
  rSquared5Y: real("r_squared_5y"),
  shareClassAum: real("share_class_aum"),
  downside5Y: real("downside_5y"),
  downside10Y: real("downside_10y"),
  maxDrawdown5Y: real("max_drawdown_5y"),
  maxDrawdown10Y: real("max_drawdown_10y"),
  infoRatio3Y: real("info_ratio_3y"),
  infoRatio5Y: real("info_ratio_5y"),
  infoRatio10Y: real("info_ratio_10y"),
  sortino3Y: real("sortino_3y"),
  sortino5Y: real("sortino_5y"),
  sortino10Y: real("sortino_10y"),
  upside3Y: real("upside_3y"),
  upside5Y: real("upside_5y"),
  upside10Y: real("upside_10y"),
  returns3Y: real("returns_3y"),
  returns5Y: real("returns_5y"),
  returns10Y: real("returns_10y"),
  oldestShareSymbol: text("oldest_share_symbol"),
  shareClass: text("share_class"),
  // Computed scores
  score: real("score"),
  scoreBand: text("score_band"), // STRONG, REVIEW, WEAK
  categoryPercentile: real("category_percentile"),
  // Upload batch tracking
  uploadBatchId: integer("upload_batch_id"),
});

// Monitoring / model portfolio holdings
export const monitoringHoldings = sqliteTable("monitoring_holdings", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  symbol: text("symbol").notNull(),
  baselineScore: real("baseline_score"),
  baselineExpenseRatio: real("baseline_expense_ratio"),
  addedAt: text("added_at").notNull(),
});

// Upload batches
export const uploadBatches = sqliteTable("upload_batches", {
  id: integer("id").primaryKey({ autoIncrement: true }),
  filename: text("filename").notNull(),
  rowCount: integer("row_count").notNull(),
  uploadedAt: text("uploaded_at").notNull(),
});

// Insert schemas
export const insertFundSchema = createInsertSchema(funds).omit({ id: true });
export const insertMonitoringSchema = createInsertSchema(monitoringHoldings).omit({ id: true });
export const insertUploadBatchSchema = createInsertSchema(uploadBatches).omit({ id: true });

// Types
export type Fund = typeof funds.$inferSelect;
export type InsertFund = z.infer<typeof insertFundSchema>;
export type MonitoringHolding = typeof monitoringHoldings.$inferSelect;
export type InsertMonitoringHolding = z.infer<typeof insertMonitoringSchema>;
export type UploadBatch = typeof uploadBatches.$inferSelect;
export type InsertUploadBatch = z.infer<typeof insertUploadBatchSchema>;
