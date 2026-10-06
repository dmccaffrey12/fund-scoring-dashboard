import crypto from "crypto";
import fs from "fs";
import path from "path";
import Papa from "papaparse";
import type { DualScoreRow } from "./scoring";

export interface RunMetadata {
  runDate: string;
  createdAt: string;
  scoreSystemVersion: string;
  rowCount: number;
  joinedCount: number;
  inputHashes: {
    hash2025?: string;
    hash2023?: string;
  };
}

export interface RunArchiveValidation {
  rowCount: number;
  joinedCount: number;
  missingScore2023: number;
  missingScore2025: number;
  bandCounts2023: Record<string, number>;
  bandCounts2025: Record<string, number>;
  quadrantCounts: Record<string, number>;
  actionFlagCounts: Record<string, number>;
  fundTypeCounts: Record<string, number>;
}

export function computeSHA256(content: string | Buffer): string {
  return crypto.createHash("sha256").update(content).digest("hex");
}

export function getRunsDirectory(): string {
  if (process.env.RUNS_DIR) {
    return process.env.RUNS_DIR;
  }
  if (process.env.DATABASE_PATH && path.isAbsolute(process.env.DATABASE_PATH)) {
    return path.join(path.dirname(process.env.DATABASE_PATH), "runs");
  }
  return path.resolve(process.cwd(), "runs");
}

export function buildValidationSummary(table: DualScoreRow[]): RunArchiveValidation {
  const band23: Record<string, number> = {};
  const band25: Record<string, number> = {};
  const quad: Record<string, number> = {};
  const action: Record<string, number> = {};
  const fundType: Record<string, number> = {};

  let missing23 = 0;
  let missing25 = 0;
  let joined = 0;

  for (const row of table) {
    if (row.Score_2023_Final === null) missing23++;
    if (row.Score_2025_Final === null) missing25++;
    if (row.Score_2023_Final !== null && row.Score_2025_Final !== null) joined++;

    const b23 = row.Score_Band_2023 || "MISSING";
    band23[b23] = (band23[b23] || 0) + 1;

    const b25 = row.Score_Band_2025 || "MISSING";
    band25[b25] = (band25[b25] || 0) + 1;

    quad[row.Quadrant] = (quad[row.Quadrant] || 0) + 1;
    action[row.Action_Flag] = (action[row.Action_Flag] || 0) + 1;
    fundType[row.Fund_Type] = (fundType[row.Fund_Type] || 0) + 1;
  }

  return {
    rowCount: table.length,
    joinedCount: joined,
    missingScore2023: missing23,
    missingScore2025: missing25,
    bandCounts2023: band23,
    bandCounts2025: band25,
    quadrantCounts: quad,
    actionFlagCounts: action,
    fundTypeCounts: fundType,
  };
}

export function saveRunArchive(
  runDate: string,
  dualTable: DualScoreRow[],
  inputHashes: { hash2025?: string; hash2023?: string } = {}
): { runDir: string; metadata: RunMetadata; validation: RunArchiveValidation } {
  const baseRunsDir = getRunsDirectory();
  const runDir = path.join(baseRunsDir, runDate);
  const dataDir = path.join(runDir, "data");
  const metaDir = path.join(runDir, "metadata");
  const validDir = path.join(runDir, "validation");

  fs.mkdirSync(dataDir, { recursive: true });
  fs.mkdirSync(metaDir, { recursive: true });
  fs.mkdirSync(validDir, { recursive: true });

  // 1. Write dual_score_table.csv
  const csvContent = Papa.unparse(dualTable);
  fs.writeFileSync(path.join(dataDir, "dual_score_table.csv"), csvContent, "utf-8");

  // 2. Write validation_report.json
  const validation = buildValidationSummary(dualTable);
  fs.writeFileSync(path.join(validDir, "validation_report.json"), JSON.stringify(validation, null, 2), "utf-8");

  // 3. Write run_metadata.json
  const metadata: RunMetadata = {
    runDate,
    createdAt: new Date().toISOString(),
    scoreSystemVersion: "dual-2023-combined+2025-split",
    rowCount: dualTable.length,
    joinedCount: validation.joinedCount,
    inputHashes,
  };
  fs.writeFileSync(path.join(metaDir, "run_metadata.json"), JSON.stringify(metadata, null, 2), "utf-8");

  // 4. Update latest.json manifest
  fs.writeFileSync(
    path.join(baseRunsDir, "latest.json"),
    JSON.stringify({ runDate, updatedAt: new Date().toISOString() }, null, 2),
    "utf-8"
  );

  return { runDir, metadata, validation };
}

export function listRunArchives(): string[] {
  const baseRunsDir = getRunsDirectory();
  if (!fs.existsSync(baseRunsDir)) return [];
  return fs
    .readdirSync(baseRunsDir)
    .filter(entry => /^\d{4}-\d{2}-\d{2}$/.test(entry) && fs.statSync(path.join(baseRunsDir, entry)).isDirectory())
    .sort()
    .reverse();
}

export function loadLatestRunDate(): string | null {
  const baseRunsDir = getRunsDirectory();
  const latestPath = path.join(baseRunsDir, "latest.json");
  if (fs.existsSync(latestPath)) {
    try {
      const data = JSON.parse(fs.readFileSync(latestPath, "utf-8"));
      return data.runDate || null;
    } catch {
      // Fall back to listing dirs
    }
  }
  const runs = listRunArchives();
  return runs.length > 0 ? runs[0] : null;
}

export function loadRunDualTable(runDate: string): DualScoreRow[] | null {
  const baseRunsDir = getRunsDirectory();
  const csvPath = path.join(baseRunsDir, runDate, "data", "dual_score_table.csv");
  if (!fs.existsSync(csvPath)) return null;
  const content = fs.readFileSync(csvPath, "utf-8");
  const parsed = Papa.parse(content, { header: true, dynamicTyping: true, skipEmptyLines: true });
  return parsed.data as DualScoreRow[];
}
