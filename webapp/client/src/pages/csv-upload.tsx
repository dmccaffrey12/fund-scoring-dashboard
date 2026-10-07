import React, { useState, useRef, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { queryClient } from "@/lib/queryClient";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/hooks/use-toast";
import {
  Upload,
  FileSpreadsheet,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  Layers,
  Calendar,
  Download,
  Info,
} from "lucide-react";
import { Link } from "wouter";

interface ValidationFinding {
  severity: "error" | "warning" | "info";
  code: string;
  message: string;
}

interface ValidationReport {
  schema: "2025" | "2023";
  failed: boolean;
  rowCount: number;
  columnCount: number;
  errors: ValidationFinding[];
  warnings: ValidationFinding[];
}

export default function CsvUpload() {
  const { toast } = useToast();

  // Mode: "paired" | "2025" | "2023"
  const [activeTab, setActiveTab] = useState("paired");

  // Files
  const [file2025, setFile2025] = useState<File | null>(null);
  const [file2023, setFile2023] = useState<File | null>(null);

  // Metadata
  const [runDate, setRunDate] = useState(new Date().toISOString().split("T")[0]);
  const [runLabel, setRunLabel] = useState(`Committee Review ${new Date().toISOString().split("T")[0]}`);

  // Validation states
  const [validating2025, setValidating2025] = useState(false);
  const [validating2023, setValidating2023] = useState(false);
  const [report2025, setReport2025] = useState<ValidationReport | null>(null);
  const [report2023, setReport2023] = useState<ValidationReport | null>(null);

  // Uploading state
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<any>(null);

  // Historical runs
  const { data: runsData } = useQuery<any>({
    queryKey: ["/api/runs"],
  });

  const fileInput2025Ref = useRef<HTMLInputElement>(null);
  const fileInput2023Ref = useRef<HTMLInputElement>(null);

  // Preflight validation runner
  const validateFile = async (file: File, schema: "2025" | "2023") => {
    if (schema === "2025") setValidating2025(true);
    else setValidating2023(true);

    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`/api/upload/validate?schema=${schema}`, {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (schema === "2025") setReport2025(data);
      else setReport2023(data);
    } catch (err: any) {
      toast({
        title: `Validation error (${schema})`,
        description: err.message,
        variant: "destructive",
      });
    } finally {
      if (schema === "2025") setValidating2025(false);
      else setValidating2023(false);
    }
  };

  const handleSelect2025 = (file: File) => {
    setFile2025(file);
    setUploadResult(null);
    validateFile(file, "2025");
  };

  const handleSelect2023 = (file: File) => {
    setFile2023(file);
    setUploadResult(null);
    validateFile(file, "2023");
  };

  const handleExecuteUpload = async () => {
    if (activeTab === "paired" && (!file2025 || !file2023)) {
      toast({
        title: "Paired Upload Required",
        description: "Please select both the 2025 and 2023 YCharts export CSV files.",
        variant: "destructive",
      });
      return;
    }
    if (activeTab === "2025" && !file2025) {
      toast({ title: "File required", description: "Please select a 2025 CSV file.", variant: "destructive" });
      return;
    }
    if (activeTab === "2023" && !file2023) {
      toast({ title: "File required", description: "Please select a 2023 CSV file.", variant: "destructive" });
      return;
    }

    setUploading(true);

    try {
      const formData = new FormData();
      if (file2025 && (activeTab === "paired" || activeTab === "2025")) {
        formData.append("file2025", file2025);
      }
      if (file2023 && (activeTab === "paired" || activeTab === "2023")) {
        formData.append("file2023", file2023);
      }
      formData.append("runDate", runDate);
      formData.append("runLabel", runLabel);

      const res = await fetch("/api/upload", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.error || "Failed to process scoring upload");
      }

      const result = await res.json();
      setUploadResult(result);

      // Invalidate queries
      queryClient.invalidateQueries({ queryKey: ["/api/stats"] });
      queryClient.invalidateQueries({ queryKey: ["/api/funds"] });
      queryClient.invalidateQueries({ queryKey: ["/api/audit-table"] });
      queryClient.invalidateQueries({ queryKey: ["/api/categories"] });
      queryClient.invalidateQueries({ queryKey: ["/api/runs"] });

      toast({
        title: "Scoring Complete!",
        description: `Successfully scored ${result.scored2025Count} (2025) and ${result.scored2023Count} (2023) funds. Built ${result.dualScoredCount} dual-scored funds.`,
      });
    } catch (err: any) {
      toast({
        title: "Upload Failed",
        description: err.message,
        variant: "destructive",
      });
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="p-4 lg:p-6 space-y-6 max-w-[1500px]">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-xl font-bold tracking-tight">YCharts Data Intake & Monthly Workflow</h1>
          <Badge variant="outline" className="font-mono text-[10px] text-primary border-primary/30">
            Dual Methodology
          </Badge>
        </div>
        <p className="text-xs text-muted-foreground mt-0.5">
          Upload paired or individual YCharts screener exports for the <strong>2025 (Production)</strong> and{" "}
          <strong>2023 (Legacy)</strong> scoring systems.
        </p>
      </div>

      {/* Upload Modes Tabs */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList className="bg-muted/40 p-1 border border-border/40">
          <TabsTrigger value="paired" className="text-xs gap-1.5">
            <Layers className="w-3.5 h-3.5" /> Paired Intake (Recommended for Committee Runs)
          </TabsTrigger>
          <TabsTrigger value="2025" className="text-xs gap-1.5">
            2025 System Only (Current)
          </TabsTrigger>
          <TabsTrigger value="2023" className="text-xs gap-1.5">
            2023 System Only (Legacy)
          </TabsTrigger>
        </TabsList>

        {/* Tab 1: Paired Upload */}
        <TabsContent value="paired" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* 2025 Dropzone */}
            <Card className="bg-card border-card-border">
              <CardHeader className="p-4 pb-2 border-b border-border/40">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-semibold text-sky-400">
                    1. 2025 YCharts Export (Current Production)
                  </CardTitle>
                  <Badge variant="outline" className="text-[10px]">
                    Active/Passive Split
                  </Badge>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  Contains: Net Expense Ratio, Info Ratio, Sortino, Downside/Upside, Drawdowns, Total Returns.
                </p>
              </CardHeader>
              <CardContent className="p-4 space-y-3">
                <input
                  type="file"
                  accept=".csv"
                  ref={fileInput2025Ref}
                  className="hidden"
                  onChange={e => e.target.files?.[0] && handleSelect2025(e.target.files[0])}
                />
                <div
                  onClick={() => fileInput2025Ref.current?.click()}
                  className="border-2 border-dashed border-border/70 hover:border-primary/70 rounded-lg p-6 text-center cursor-pointer transition-colors bg-muted/10 hover:bg-muted/20"
                >
                  <Upload className="w-8 h-8 mx-auto text-muted-foreground mb-2" />
                  <div className="text-xs font-semibold text-foreground">
                    {file2025 ? file2025.name : "Click to select 2025 YCharts CSV"}
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-1">
                    {file2025 ? `${(file2025.size / 1024).toFixed(1)} KB` : "Drag and drop or browse"}
                  </p>
                </div>

                {validating2025 && <p className="text-xs text-muted-foreground animate-pulse">Validating 2025 CSV...</p>}

                {report2025 && (
                  <div
                    className={`p-2.5 rounded text-xs border ${
                      report2025.failed ? "bg-rose-500/10 border-rose-500/30 text-rose-400" : "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                    }`}
                  >
                    <div className="font-semibold flex items-center gap-1.5">
                      {report2025.failed ? <AlertTriangle className="w-4 h-4" /> : <CheckCircle2 className="w-4 h-4" />}
                      <span>{report2025.failed ? "Preflight Check Failed" : `Preflight Verified (${report2025.rowCount} rows)`}</span>
                    </div>
                    {report2025.errors.length > 0 && (
                      <ul className="list-disc list-inside mt-1 text-[11px] space-y-0.5">
                        {report2025.errors.map((e, i) => (
                          <li key={i}>{e.message}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* 2023 Dropzone */}
            <Card className="bg-card border-card-border">
              <CardHeader className="p-4 pb-2 border-b border-border/40">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-semibold text-amber-400">
                    2. 2023 YCharts Export (Legacy Combined)
                  </CardTitle>
                  <Badge variant="outline" className="text-[10px]">
                    15-Factor Baseline
                  </Badge>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  Contains: 5Y/10Y Returns, Alpha 5Y/10Y, Max Drawdown, Upside/Downside, Manager Tenure, AUM.
                </p>
              </CardHeader>
              <CardContent className="p-4 space-y-3">
                <input
                  type="file"
                  accept=".csv"
                  ref={fileInput2023Ref}
                  className="hidden"
                  onChange={e => e.target.files?.[0] && handleSelect2023(e.target.files[0])}
                />
                <div
                  onClick={() => fileInput2023Ref.current?.click()}
                  className="border-2 border-dashed border-border/70 hover:border-primary/70 rounded-lg p-6 text-center cursor-pointer transition-colors bg-muted/10 hover:bg-muted/20"
                >
                  <Upload className="w-8 h-8 mx-auto text-muted-foreground mb-2" />
                  <div className="text-xs font-semibold text-foreground">
                    {file2023 ? file2023.name : "Click to select 2023 YCharts CSV"}
                  </div>
                  <p className="text-[11px] text-muted-foreground mt-1">
                    {file2023 ? `${(file2023.size / 1024).toFixed(1)} KB` : "Drag and drop or browse"}
                  </p>
                </div>

                {validating2023 && <p className="text-xs text-muted-foreground animate-pulse">Validating 2023 CSV...</p>}

                {report2023 && (
                  <div
                    className={`p-2.5 rounded text-xs border ${
                      report2023.failed ? "bg-rose-500/10 border-rose-500/30 text-rose-400" : "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                    }`}
                  >
                    <div className="font-semibold flex items-center gap-1.5">
                      {report2023.failed ? <AlertTriangle className="w-4 h-4" /> : <CheckCircle2 className="w-4 h-4" />}
                      <span>{report2023.failed ? "Preflight Check Failed" : `Preflight Verified (${report2023.rowCount} rows)`}</span>
                    </div>
                    {report2023.errors.length > 0 && (
                      <ul className="list-disc list-inside mt-1 text-[11px] space-y-0.5">
                        {report2023.errors.map((e, i) => (
                          <li key={i}>{e.message}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Tab 2: 2025 Only */}
        <TabsContent value="2025">
          <Card className="bg-card border-card-border p-6 text-center">
            <input
              type="file"
              accept=".csv"
              ref={fileInput2025Ref}
              className="hidden"
              onChange={e => e.target.files?.[0] && handleSelect2025(e.target.files[0])}
            />
            <div
              onClick={() => fileInput2025Ref.current?.click()}
              className="border-2 border-dashed border-border/70 hover:border-primary/70 rounded-lg p-8 cursor-pointer transition-colors max-w-md mx-auto"
            >
              <Upload className="w-10 h-10 mx-auto text-primary mb-2" />
              <div className="text-sm font-semibold">
                {file2025 ? file2025.name : "Select 2025 Production Export CSV"}
              </div>
              <p className="text-xs text-muted-foreground mt-1">Updates the 2025 scoring universe</p>
            </div>
          </Card>
        </TabsContent>

        {/* Tab 3: 2023 Only */}
        <TabsContent value="2023">
          <Card className="bg-card border-card-border p-6 text-center">
            <input
              type="file"
              accept=".csv"
              ref={fileInput2023Ref}
              className="hidden"
              onChange={e => e.target.files?.[0] && handleSelect2023(e.target.files[0])}
            />
            <div
              onClick={() => fileInput2023Ref.current?.click()}
              className="border-2 border-dashed border-border/70 hover:border-primary/70 rounded-lg p-8 cursor-pointer transition-colors max-w-md mx-auto"
            >
              <Upload className="w-10 h-10 mx-auto text-amber-400 mb-2" />
              <div className="text-sm font-semibold">
                {file2023 ? file2023.name : "Select 2023 Legacy Export CSV"}
              </div>
              <p className="text-xs text-muted-foreground mt-1">Updates the 2023 legacy scoring universe</p>
            </div>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Run Metadata & Process Action */}
      <Card className="bg-card border-card-border">
        <CardContent className="p-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap items-center gap-3">
              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-muted-foreground uppercase">Run Snapshot Date</label>
                <div className="flex items-center gap-1.5">
                  <Calendar className="w-4 h-4 text-muted-foreground" />
                  <Input
                    type="date"
                    value={runDate}
                    onChange={e => setRunDate(e.target.value)}
                    className="w-40 h-8 text-xs bg-background"
                  />
                </div>
              </div>
              <div className="space-y-1 flex-1 min-w-[240px]">
                <label className="text-[11px] font-semibold text-muted-foreground uppercase">Committee Run Label</label>
                <Input
                  value={runLabel}
                  onChange={e => setRunLabel(e.target.value)}
                  placeholder="e.g. October 2026 Committee Review"
                  className="h-8 text-xs bg-background"
                />
              </div>
            </div>

            <Button
              onClick={handleExecuteUpload}
              disabled={uploading}
              className="gap-2 bg-primary hover:bg-primary/90 text-primary-foreground font-semibold px-6"
            >
              <ArrowRight className="w-4 h-4" />
              {uploading ? "Processing & Scoring..." : "Execute Scoring & Build Dual Table"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Success Box */}
      {uploadResult && (
        <Card className="border-emerald-500/30 bg-emerald-500/5">
          <CardContent className="p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                  <h3 className="text-sm font-bold text-foreground">Scoring Run Completed Successfully</h3>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  Scored <strong>{uploadResult.scored2025Count?.toLocaleString()}</strong> (2025) and{" "}
                  <strong>{uploadResult.scored2023Count?.toLocaleString()}</strong> (2023) funds. Produced{" "}
                  <strong>{uploadResult.dualScoredCount?.toLocaleString()}</strong> dual-scored consensus records.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Link href="/scores">
                  <Button size="sm" className="gap-1.5 text-xs">
                    View in Committee Audit Suite <ArrowRight className="w-3.5 h-3.5" />
                  </Button>
                </Link>
                <a href={`/api/runs/${uploadResult.runDate}/export/excel`} target="_blank" rel="noreferrer">
                  <Button variant="outline" size="sm" className="gap-1.5 text-xs text-emerald-400 border-emerald-500/30">
                    <Download className="w-3.5 h-3.5" /> Download Audit Excel (.xlsx)
                  </Button>
                </a>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Historical Scoring Runs List */}
      <Card className="bg-card border-card-border">
        <CardHeader className="p-4 pb-2">
          <CardTitle className="text-sm font-semibold">Archived Committee Scoring Runs</CardTitle>
          <p className="text-xs text-muted-foreground">
            Previous monthly scoring runs saved to the persistent volume (`/data/runs/` or `runs/`).
          </p>
        </CardHeader>
        <CardContent className="p-0 overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-muted/30 border-b border-border/40 text-[10px] uppercase font-semibold text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left">Run Date</th>
                <th className="px-3 py-2 text-left">Label</th>
                <th className="px-3 py-2 text-right">Universe Count</th>
                <th className="px-3 py-2 text-right">Dual Scored</th>
                <th className="px-3 py-2 text-center">Export</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/20">
              {runsData?.dbRuns?.map((run: any) => (
                <tr key={run.id} className="hover:bg-muted/20 transition-colors">
                  <td className="px-3 py-2 font-mono font-bold text-primary">{run.runDate}</td>
                  <td className="px-3 py-2 font-medium">{run.label || "Monthly Committee Run"}</td>
                  <td className="px-3 py-2 text-right font-mono text-muted-foreground">{run.rowCount?.toLocaleString()}</td>
                  <td className="px-3 py-2 text-right font-mono font-bold text-emerald-400">
                    {run.joinedCount?.toLocaleString()}
                  </td>
                  <td className="px-3 py-2 text-center">
                    <a href={`/api/runs/${run.runDate}/export/excel`} download>
                      <Button variant="ghost" size="sm" className="h-6 text-[11px] gap-1 px-2 text-emerald-400 hover:text-emerald-300">
                        <Download className="w-3 h-3" /> Workbook (.xlsx)
                      </Button>
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
