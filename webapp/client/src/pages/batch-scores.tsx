import React, { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Download,
  Search,
  ArrowUpDown,
  Filter,
  FileSpreadsheet,
  FileText,
  Radar as RadarIcon,
  RefreshCw,
  TrendingUp,
  TrendingDown,
  Layers,
  Award,
  AlertTriangle,
  Grid,
} from "lucide-react";
import { Link } from "wouter";
import { ComparisonRadar, type MetricBreakdownItem } from "@/components/comparison-radar";
import { ReplacementWorkbenchView } from "@/components/replacement-workbench-view";

interface DualScoreRow {
  Symbol: string;
  Name: string;
  Category: string;
  Fund_Type: "Passive" | "Active";
  Score_2023_Final: number | null;
  Score_2025_Final: number | null;
  Score_Gap: number | null;
  Rank_2023: number | null;
  Rank_2025: number | null;
  Consensus_Rank: number | null;
  Score_Band_2023: "STRONG" | "REVIEW" | "WEAK" | null;
  Score_Band_2025: "STRONG" | "REVIEW" | "WEAK" | null;
  Quadrant: "Q1_Both_Strong" | "Q2_Only_2025" | "Q3_Only_2023" | "Q4_Both_Weak";
  Action_Flag: "LEAD" | "REVIEW" | "WATCH" | "DROP";
  Primary_Driver: string;
  Data_Coverage_2023: number | null;
  Data_Coverage_2025: number | null;
}

interface AuditTableResponse {
  rows: DualScoreRow[];
  totalCount: number;
  filteredCount: number;
  summary: {
    totalScored: number;
    q1Count: number;
    q2Count: number;
    q3Count: number;
    q4Count: number;
    leadCount: number;
    reviewCount: number;
    watchCount: number;
    dropCount: number;
    upgradesCount: number;
    downgradesCount: number;
    stableCount: number;
  };
}

export default function BatchScores() {
  const [activeTab, setActiveTab] = useState("master");
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [quadrantFilter, setQuadrantFilter] = useState("all");
  const [actionFilter, setActionFilter] = useState("all");
  const [selectedRadarSymbol, setSelectedRadarSymbol] = useState<string>("VFIAX");
  const [selectedReplaceSymbol, setSelectedReplaceSymbol] = useState<string>("PRBLX");

  const [sortField, setSortField] = useState<keyof DualScoreRow>("Consensus_Rank");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  // Fetch full dual audit table
  const { data, isLoading } = useQuery<AuditTableResponse>({
    queryKey: ["/api/audit-table"],
    queryFn: async () => {
      const res = await fetch("/api/audit-table");
      if (!res.ok) throw new Error("Failed to load audit table");
      return res.json();
    },
  });

  const { data: categories } = useQuery<string[]>({ queryKey: ["/api/categories"] });

  // Fetch radar breakdown when radar tab or fund is selected
  const { data: radarResponse } = useQuery<{
    fund: any;
    categoryPeerCount: number;
    breakdown: MetricBreakdownItem[];
  }>({
    queryKey: ["/api/funds/radar", selectedRadarSymbol],
    queryFn: async () => {
      const res = await fetch(`/api/funds/radar/${selectedRadarSymbol}`);
      if (!res.ok) throw new Error("Radar data not found");
      return res.json();
    },
    enabled: !!selectedRadarSymbol,
  });

  const rows = data?.rows || [];
  const summary = data?.summary;

  // Filtered rows for Master Table
  const filtered = useMemo(() => {
    let result = [...rows];

    if (search) {
      const q = search.toLowerCase();
      result = result.filter(
        f =>
          f.Symbol.toLowerCase().includes(q) ||
          f.Name.toLowerCase().includes(q) ||
          f.Category.toLowerCase().includes(q)
      );
    }

    if (categoryFilter !== "all") {
      result = result.filter(f => f.Category === categoryFilter);
    }

    if (typeFilter !== "all") {
      result = result.filter(f =>
        typeFilter === "passive" ? f.Fund_Type === "Passive" : f.Fund_Type === "Active"
      );
    }

    if (quadrantFilter !== "all") {
      result = result.filter(f => f.Quadrant === quadrantFilter);
    }

    if (actionFilter !== "all") {
      result = result.filter(f => f.Action_Flag === actionFilter);
    }

    result.sort((a, b) => {
      const aVal = a[sortField];
      const bVal = b[sortField];
      if (aVal === null || aVal === undefined) return 1;
      if (bVal === null || bVal === undefined) return -1;
      const cmp = typeof aVal === "string" ? aVal.localeCompare(bVal as string) : (aVal as number) - (bVal as number);
      return sortDir === "asc" ? cmp : -cmp;
    });

    return result;
  }, [rows, search, categoryFilter, typeFilter, quadrantFilter, actionFilter, sortField, sortDir]);

  // Top 50 Consensus
  const top50Rows = useMemo(() => {
    return [...rows].slice(0, 50);
  }, [rows]);

  // System Disagreements (|Gap| >= 10)
  const disagreementRows = useMemo(() => {
    return rows.filter(r => Math.abs(r.Score_Gap ?? 0) >= 10);
  }, [rows]);

  const upgrades = useMemo(() => {
    return rows.filter(r => (r.Score_Gap ?? 0) >= 10);
  }, [rows]);

  const downgrades = useMemo(() => {
    return rows.filter(r => (r.Score_Gap ?? 0) <= -10);
  }, [rows]);

  const handleSort = (field: keyof DualScoreRow) => {
    if (sortField === field) {
      setSortDir(d => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir(field === "Consensus_Rank" || field === "Symbol" ? "asc" : "desc");
    }
  };

  const downloadExcel = () => {
    window.location.href = "/api/export/audit-excel";
  };

  const exportCSV = () => {
    window.location.href = "/api/export/csv";
  };

  const downloadPdf = () => {
    window.location.href = "/api/export/pdf";
  };

  const openRadarForSymbol = (symbol: string) => {
    setSelectedRadarSymbol(symbol);
    setActiveTab("radar");
  };

  const openReplaceForSymbol = (symbol: string) => {
    setSelectedReplaceSymbol(symbol);
    setActiveTab("workbench");
  };

  const renderBadge = (flag: string | null) => {
    if (!flag) return "—";
    if (flag === "LEAD" || flag === "STRONG" || flag === "Q1_Both_Strong") {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/20">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
          {flag}
        </span>
      );
    }
    if (flag === "REVIEW" || flag === "Q2_Only_2025" || flag === "Q3_Only_2023") {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/20">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
          {flag}
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-rose-500/15 text-rose-400 border border-rose-500/20">
        <span className="w-1.5 h-1.5 rounded-full bg-rose-400" />
        {flag}
      </span>
    );
  };

  const renderGap = (gap: number | null) => {
    if (gap === null) return "—";
    if (gap >= 10) {
      return (
        <span className="inline-flex items-center text-emerald-400 font-mono font-bold text-xs gap-0.5">
          <TrendingUp className="w-3 h-3" /> +{gap.toFixed(1)}
        </span>
      );
    }
    if (gap <= -10) {
      return (
        <span className="inline-flex items-center text-rose-400 font-mono font-bold text-xs gap-0.5">
          <TrendingDown className="w-3 h-3" /> {gap.toFixed(1)}
        </span>
      );
    }
    return (
      <span className="font-mono text-muted-foreground text-xs">
        {gap > 0 ? `+${gap.toFixed(1)}` : gap.toFixed(1)}
      </span>
    );
  };

  const SortHeader = ({ field, label, className }: { field: keyof DualScoreRow; label: string; className?: string }) => (
    <th
      className={`px-3 py-2 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground cursor-pointer hover:text-foreground select-none ${
        className || ""
      }`}
      onClick={() => handleSort(field)}
    >
      <span className="flex items-center gap-1">
        {label}
        {sortField === field && <ArrowUpDown className="w-3 h-3 text-primary" />}
      </span>
    </th>
  );

  return (
    <div className="p-4 lg:p-6 space-y-4 max-w-[1700px]">
      {/* Header and 1-Click Committee Actions */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-2 border-b border-border/40">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold tracking-tight">Committee Audit Suite</h1>
            <Badge variant="outline" className="font-mono text-[10px] text-primary border-primary/30">
              Dual-Lens Parity
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            Cross-methodology validation comparing 2023 Legacy vs. 2025 Modernized systems across{" "}
            <strong>{summary?.totalScored.toLocaleString() || "..."}</strong> funds.
          </p>
        </div>

        {/* 1-Click Committee Download Bar */}
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            onClick={downloadExcel}
            className="text-xs gap-1.5 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold shadow-sm"
          >
            <FileSpreadsheet className="w-3.5 h-3.5" />
            Download Audit Workbook (.xlsx)
          </Button>
          <Button variant="outline" size="sm" onClick={downloadPdf} className="text-xs gap-1.5">
            <FileText className="w-3.5 h-3.5" />
            Committee Report (PDF)
          </Button>
          <Button variant="outline" size="sm" onClick={exportCSV} className="text-xs gap-1.5">
            <Download className="w-3.5 h-3.5" />
            Export CSV
          </Button>
        </div>
      </div>

      {/* KPI Summary Cards */}
      {summary && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <Card
            className="bg-card border-card-border cursor-pointer hover:border-primary/50 transition-colors"
            onClick={() => {
              setQuadrantFilter("all");
              setActiveTab("master");
            }}
          >
            <CardContent className="p-3">
              <div className="text-[10px] uppercase font-semibold text-muted-foreground flex items-center justify-between">
                <span>Total Dual Scored</span>
                <Layers className="w-3.5 h-3.5 text-muted-foreground" />
              </div>
              <div className="text-xl font-bold font-mono mt-1">{summary.totalScored.toLocaleString()}</div>
              <div className="text-[10px] text-muted-foreground mt-0.5">100% matched universe</div>
            </CardContent>
          </Card>

          <Card
            className="bg-card border-card-border cursor-pointer hover:border-emerald-500/50 transition-colors"
            onClick={() => {
              setQuadrantFilter("Q1_Both_Strong");
              setActiveTab("master");
            }}
          >
            <CardContent className="p-3">
              <div className="text-[10px] uppercase font-semibold text-emerald-400 flex items-center justify-between">
                <span>Q1 Both Strong (Lead)</span>
                <Award className="w-3.5 h-3.5 text-emerald-400" />
              </div>
              <div className="text-xl font-bold font-mono text-emerald-400 mt-1">{summary.q1Count}</div>
              <div className="text-[10px] text-muted-foreground mt-0.5">
                {((summary.q1Count / summary.totalScored) * 100).toFixed(1)}% core recommendations
              </div>
            </CardContent>
          </Card>

          <Card
            className="bg-card border-card-border cursor-pointer hover:border-sky-500/50 transition-colors"
            onClick={() => {
              setQuadrantFilter("Q2_Only_2025");
              setActiveTab("master");
            }}
          >
            <CardContent className="p-3">
              <div className="text-[10px] uppercase font-semibold text-sky-400 flex items-center justify-between">
                <span>Q2 2025 Modern</span>
                <TrendingUp className="w-3.5 h-3.5 text-sky-400" />
              </div>
              <div className="text-xl font-bold font-mono text-sky-400 mt-1">{summary.q2Count}</div>
              <div className="text-[10px] text-muted-foreground mt-0.5">2025 modernization picks</div>
            </CardContent>
          </Card>

          <Card
            className="bg-card border-card-border cursor-pointer hover:border-amber-500/50 transition-colors"
            onClick={() => {
              setQuadrantFilter("Q3_Only_2023");
              setActiveTab("master");
            }}
          >
            <CardContent className="p-3">
              <div className="text-[10px] uppercase font-semibold text-amber-400 flex items-center justify-between">
                <span>Q3 2023 Legacy</span>
                <TrendingDown className="w-3.5 h-3.5 text-amber-400" />
              </div>
              <div className="text-xl font-bold font-mono text-amber-400 mt-1">{summary.q3Count}</div>
              <div className="text-[10px] text-muted-foreground mt-0.5">Scrutiny / Legacy holdovers</div>
            </CardContent>
          </Card>

          <Card
            className="bg-card border-card-border cursor-pointer hover:border-rose-500/50 transition-colors"
            onClick={() => {
              setQuadrantFilter("Q4_Both_Weak");
              setActiveTab("master");
            }}
          >
            <CardContent className="p-3">
              <div className="text-[10px] uppercase font-semibold text-rose-400 flex items-center justify-between">
                <span>Q4 Both Weak (Drop)</span>
                <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
              </div>
              <div className="text-xl font-bold font-mono text-rose-400 mt-1">{summary.q4Count}</div>
              <div className="text-[10px] text-muted-foreground mt-0.5">Replacement candidates</div>
            </CardContent>
          </Card>

          <Card
            className="bg-card border-card-border cursor-pointer hover:border-purple-500/50 transition-colors"
            onClick={() => setActiveTab("disagreements")}
          >
            <CardContent className="p-3">
              <div className="text-[10px] uppercase font-semibold text-purple-400 flex items-center justify-between">
                <span>Disagreements (|&Delta;|&ge;10)</span>
                <RefreshCw className="w-3.5 h-3.5 text-purple-400" />
              </div>
              <div className="text-xl font-bold font-mono text-purple-400 mt-1">
                {summary.upgradesCount + summary.downgradesCount}
              </div>
              <div className="text-[10px] text-muted-foreground mt-0.5">
                +{summary.upgradesCount} up / -{summary.downgradesCount} down
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Main Tabs Navigation */}
      <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-4">
        <TabsList className="bg-muted/40 p-1 border border-border/40">
          <TabsTrigger value="master" className="text-xs gap-1.5">
            <Layers className="w-3.5 h-3.5" /> Dual-Score Table ({filtered.length})
          </TabsTrigger>
          <TabsTrigger value="top50" className="text-xs gap-1.5">
            <Award className="w-3.5 h-3.5" /> Top-50 Consensus
          </TabsTrigger>
          <TabsTrigger value="disagreements" className="text-xs gap-1.5">
            <RefreshCw className="w-3.5 h-3.5" /> Disagreements ({disagreementRows.length})
          </TabsTrigger>
          <TabsTrigger value="quadrants" className="text-xs gap-1.5">
            <Grid className="w-3.5 h-3.5" /> Quadrant Matrix
          </TabsTrigger>
          <TabsTrigger value="radar" className="text-xs gap-1.5">
            <RadarIcon className="w-3.5 h-3.5" /> Comparison "Web" ({selectedRadarSymbol})
          </TabsTrigger>
          <TabsTrigger value="workbench" className="text-xs gap-1.5">
            <RefreshCw className="w-3.5 h-3.5" /> Replacement Workbench
          </TabsTrigger>
        </TabsList>

        {/* =======================================================================
            TAB 1: DUAL-SCORE MASTER TABLE
        ======================================================================== */}
        <TabsContent value="master" className="space-y-3">
          {/* Filter Bar */}
          <Card className="bg-card border-card-border">
            <CardContent className="p-3">
              <div className="flex flex-wrap gap-2 items-center">
                <div className="relative flex-1 min-w-[200px] max-w-sm">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                  <Input
                    placeholder="Search symbol, name, or category..."
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    className="pl-8 h-8 text-xs bg-background"
                  />
                </div>
                <Select value={categoryFilter} onValueChange={setCategoryFilter}>
                  <SelectTrigger className="w-[180px] h-8 text-xs">
                    <Filter className="w-3 h-3 mr-1" />
                    <SelectValue placeholder="Category" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Categories</SelectItem>
                    {categories?.map(c => (
                      <SelectItem key={c} value={c}>
                        {c}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={typeFilter} onValueChange={setTypeFilter}>
                  <SelectTrigger className="w-[120px] h-8 text-xs">
                    <SelectValue placeholder="Type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Types</SelectItem>
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="passive">Passive</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={quadrantFilter} onValueChange={setQuadrantFilter}>
                  <SelectTrigger className="w-[160px] h-8 text-xs">
                    <SelectValue placeholder="Quadrant" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Quadrants</SelectItem>
                    <SelectItem value="Q1_Both_Strong">Q1 Both Strong</SelectItem>
                    <SelectItem value="Q2_Only_2025">Q2 2025 Only</SelectItem>
                    <SelectItem value="Q3_Only_2023">Q3 2023 Only</SelectItem>
                    <SelectItem value="Q4_Both_Weak">Q4 Both Weak</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={actionFilter} onValueChange={setActionFilter}>
                  <SelectTrigger className="w-[130px] h-8 text-xs">
                    <SelectValue placeholder="Action Flag" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Flags</SelectItem>
                    <SelectItem value="LEAD">LEAD</SelectItem>
                    <SelectItem value="REVIEW">REVIEW</SelectItem>
                    <SelectItem value="WATCH">WATCH</SelectItem>
                    <SelectItem value="DROP">DROP</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          {/* Master Table */}
          <Card className="bg-card border-card-border overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-muted/40 sticky top-0 z-[1] border-b border-border/40">
                  <tr>
                    <SortHeader field="Consensus_Rank" label="Cons. #" className="w-16" />
                    <SortHeader field="Symbol" label="Symbol" className="w-20" />
                    <SortHeader field="Name" label="Fund Name" className="min-w-[200px]" />
                    <SortHeader field="Category" label="Category" className="min-w-[140px]" />
                    <SortHeader field="Fund_Type" label="Type" className="w-16 text-center" />
                    <SortHeader field="Score_2025_Final" label="2025 Score" className="w-24 text-right" />
                    <SortHeader field="Score_2023_Final" label="2023 Score" className="w-24 text-right" />
                    <SortHeader field="Score_Gap" label="Score Gap" className="w-20 text-right" />
                    <SortHeader field="Quadrant" label="Quadrant" className="w-28 text-center" />
                    <SortHeader field="Action_Flag" label="Action Flag" className="w-24 text-center" />
                    <SortHeader field="Primary_Driver" label="Primary Driver" className="min-w-[150px]" />
                    <th className="px-3 py-2 text-center text-[10px] uppercase tracking-wider font-semibold text-muted-foreground w-28">
                      Quick Action
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/20">
                  {isLoading ? (
                    Array.from({ length: 15 }).map((_, i) => (
                      <tr key={i}>
                        <td colSpan={12} className="px-3 py-2">
                          <Skeleton className="h-5" />
                        </td>
                      </tr>
                    ))
                  ) : (
                    filtered.slice(0, 250).map(row => (
                      <tr key={row.Symbol} className="hover:bg-muted/20 transition-colors">
                        <td className="px-3 py-2 font-mono font-bold text-foreground">
                          #{row.Consensus_Rank ?? "—"}
                        </td>
                        <td className="px-3 py-2">
                          <Link
                            href={`/lookup/${row.Symbol}`}
                            className="font-mono font-bold text-primary hover:underline"
                          >
                            {row.Symbol}
                          </Link>
                        </td>
                        <td className="px-3 py-2 truncate max-w-[240px] font-medium">{row.Name}</td>
                        <td className="px-3 py-2 text-muted-foreground truncate max-w-[160px]">{row.Category}</td>
                        <td className="px-3 py-2 text-center">
                          <span
                            className={`text-[9px] font-mono px-1 py-0.5 rounded ${
                              row.Fund_Type === "Passive"
                                ? "bg-blue-500/10 text-blue-400"
                                : "bg-purple-500/10 text-purple-400"
                            }`}
                          >
                            {row.Fund_Type === "Passive" ? "IDX" : "ACT"}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-right font-mono font-bold">
                          <span
                            className={
                              row.Score_2025_Final && row.Score_2025_Final >= 80
                                ? "text-emerald-400"
                                : row.Score_2025_Final && row.Score_2025_Final >= 60
                                ? "text-amber-400"
                                : "text-rose-400"
                            }
                          >
                            {row.Score_2025_Final?.toFixed(1) ?? "—"}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-muted-foreground">
                          {row.Score_2023_Final?.toFixed(1) ?? "—"}
                        </td>
                        <td className="px-3 py-2 text-right">{renderGap(row.Score_Gap)}</td>
                        <td className="px-3 py-2 text-center">{renderBadge(row.Quadrant)}</td>
                        <td className="px-3 py-2 text-center">{renderBadge(row.Action_Flag)}</td>
                        <td className="px-3 py-2 text-muted-foreground text-[11px] truncate max-w-[180px]">
                          {row.Primary_Driver}
                        </td>
                        <td className="px-3 py-2 text-center">
                          <div className="flex items-center justify-center gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => openRadarForSymbol(row.Symbol)}
                              className="h-6 text-[10px] px-1.5 text-sky-400 hover:text-sky-300"
                              title="Inspect Factor Radar Web"
                            >
                              Web
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => openReplaceForSymbol(row.Symbol)}
                              className="h-6 text-[10px] px-1.5 text-amber-400 hover:text-amber-300"
                              title="Open Candidate Replacement Workbench"
                            >
                              Replace
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            {filtered.length > 250 && (
              <div className="p-3 text-center text-xs text-muted-foreground border-t border-border/30">
                Displaying first 250 of {filtered.length.toLocaleString()} funds. Filter to view specific subsets.
              </div>
            )}
          </Card>
        </TabsContent>

        {/* =======================================================================
            TAB 2: TOP-50 CONSENSUS LEADERBOARD
        ======================================================================== */}
        <TabsContent value="top50" className="space-y-3">
          <Card className="bg-card border-card-border">
            <CardHeader className="p-4 pb-2">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-sm font-bold flex items-center gap-2">
                    <Award className="w-4 h-4 text-emerald-400" />
                    Top-50 Dual-Lens Consensus Leaderboard
                  </CardTitle>
                  <p className="text-xs text-muted-foreground">
                    Highest conviction funds jointly validated by both legacy (2023) and modern (2025) frameworks.
                  </p>
                </div>
              </div>
            </CardHeader>
            <CardContent className="p-0 overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-muted/40 border-b border-border/40 text-[10px] uppercase font-semibold text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 text-center w-12">Rank</th>
                    <th className="px-3 py-2 text-left">Symbol</th>
                    <th className="px-3 py-2 text-left">Fund Name</th>
                    <th className="px-3 py-2 text-left">Category</th>
                    <th className="px-3 py-2 text-center">Type</th>
                    <th className="px-3 py-2 text-right">2025 Score</th>
                    <th className="px-3 py-2 text-right">2023 Score</th>
                    <th className="px-3 py-2 text-right">Score Gap</th>
                    <th className="px-3 py-2 text-center">Quadrant</th>
                    <th className="px-3 py-2 text-center">Action Flag</th>
                    <th className="px-3 py-2 text-center">Radar Web</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/20">
                  {top50Rows.map((r, i) => (
                    <tr key={r.Symbol} className="hover:bg-muted/20 transition-colors">
                      <td className="px-3 py-2 text-center font-mono font-bold text-foreground">#{i + 1}</td>
                      <td className="px-3 py-2">
                        <Link href={`/lookup/${r.Symbol}`} className="font-mono font-bold text-primary hover:underline">
                          {r.Symbol}
                        </Link>
                      </td>
                      <td className="px-3 py-2 max-w-[250px] truncate font-medium">{r.Name}</td>
                      <td className="px-3 py-2 text-muted-foreground">{r.Category}</td>
                      <td className="px-3 py-2 text-center">
                        <span
                          className={`text-[9px] font-mono px-1 py-0.5 rounded ${
                            r.Fund_Type === "Passive" ? "bg-blue-500/10 text-blue-400" : "bg-purple-500/10 text-purple-400"
                          }`}
                        >
                          {r.Fund_Type === "Passive" ? "IDX" : "ACT"}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right font-mono font-bold text-emerald-400">
                        {r.Score_2025_Final?.toFixed(1)}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-muted-foreground">
                        {r.Score_2023_Final?.toFixed(1)}
                      </td>
                      <td className="px-3 py-2 text-right">{renderGap(r.Score_Gap)}</td>
                      <td className="px-3 py-2 text-center">{renderBadge(r.Quadrant)}</td>
                      <td className="px-3 py-2 text-center">{renderBadge(r.Action_Flag)}</td>
                      <td className="px-3 py-2 text-center">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => openRadarForSymbol(r.Symbol)}
                          className="h-6 text-[10px] px-2 text-sky-400 hover:text-sky-300"
                        >
                          Inspect
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* =======================================================================
            TAB 3: SYSTEM DISAGREEMENTS & SCORE MOVERS
        ======================================================================== */}
        <TabsContent value="disagreements" className="space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Upgrades */}
            <Card className="bg-card border-card-border">
              <CardHeader className="p-4 pb-2 border-b border-border/40">
                <CardTitle className="text-sm font-bold text-emerald-400 flex items-center justify-between">
                  <span>Upgraded by 2025 System (&Delta; &ge; +10)</span>
                  <Badge className="bg-emerald-500/15 text-emerald-400">{upgrades.length} Funds</Badge>
                </CardTitle>
                <p className="text-xs text-muted-foreground">
                  Benefited from updated risk-adjusted factor weights, Sortino focus, and removed passive scaling.
                </p>
              </CardHeader>
              <CardContent className="p-0 overflow-x-auto max-h-[500px]">
                <table className="w-full text-xs">
                  <thead className="bg-muted/40 sticky top-0 text-[10px] uppercase font-semibold text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2 text-left">Symbol</th>
                      <th className="px-3 py-2 text-left">Name</th>
                      <th className="px-3 py-2 text-right">2023</th>
                      <th className="px-3 py-2 text-right">2025</th>
                      <th className="px-3 py-2 text-right">Gap</th>
                      <th className="px-3 py-2 text-center">Radar</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/20">
                    {upgrades.map(r => (
                      <tr key={r.Symbol} className="hover:bg-muted/20">
                        <td className="px-3 py-2 font-mono font-bold text-primary">{r.Symbol}</td>
                        <td className="px-3 py-2 truncate max-w-[180px]">{r.Name}</td>
                        <td className="px-3 py-2 text-right font-mono text-muted-foreground">
                          {r.Score_2023_Final?.toFixed(1)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono font-bold text-emerald-400">
                          {r.Score_2025_Final?.toFixed(1)}
                        </td>
                        <td className="px-3 py-2 text-right">{renderGap(r.Score_Gap)}</td>
                        <td className="px-3 py-2 text-center">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => openRadarForSymbol(r.Symbol)}
                            className="h-6 text-[10px] px-1 text-sky-400"
                          >
                            Web
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>

            {/* Downgrades */}
            <Card className="bg-card border-card-border">
              <CardHeader className="p-4 pb-2 border-b border-border/40">
                <CardTitle className="text-sm font-bold text-rose-400 flex items-center justify-between">
                  <span>Downgraded by 2025 System (&Delta; &le; -10)</span>
                  <Badge className="bg-rose-500/15 text-rose-400">{downgrades.length} Funds</Badge>
                </CardTitle>
                <p className="text-xs text-muted-foreground">
                  Penalized by higher downside capture sensitivity, stricter drawdown limits, or fee hurdles.
                </p>
              </CardHeader>
              <CardContent className="p-0 overflow-x-auto max-h-[500px]">
                <table className="w-full text-xs">
                  <thead className="bg-muted/40 sticky top-0 text-[10px] uppercase font-semibold text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2 text-left">Symbol</th>
                      <th className="px-3 py-2 text-left">Name</th>
                      <th className="px-3 py-2 text-right">2023</th>
                      <th className="px-3 py-2 text-right">2025</th>
                      <th className="px-3 py-2 text-right">Gap</th>
                      <th className="px-3 py-2 text-center">Replace</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/20">
                    {downgrades.map(r => (
                      <tr key={r.Symbol} className="hover:bg-muted/20">
                        <td className="px-3 py-2 font-mono font-bold text-primary">{r.Symbol}</td>
                        <td className="px-3 py-2 truncate max-w-[180px]">{r.Name}</td>
                        <td className="px-3 py-2 text-right font-mono text-muted-foreground">
                          {r.Score_2023_Final?.toFixed(1)}
                        </td>
                        <td className="px-3 py-2 text-right font-mono font-bold text-rose-400">
                          {r.Score_2025_Final?.toFixed(1)}
                        </td>
                        <td className="px-3 py-2 text-right">{renderGap(r.Score_Gap)}</td>
                        <td className="px-3 py-2 text-center">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => openReplaceForSymbol(r.Symbol)}
                            className="h-6 text-[10px] px-1 text-amber-400"
                          >
                            Replace
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* =======================================================================
            TAB 4: DUAL-LENS QUADRANT MATRIX (2x2)
        ======================================================================== */}
        <TabsContent value="quadrants" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Q1 */}
            <Card className="border-emerald-500/30 bg-emerald-500/5">
              <CardHeader className="p-4 pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-bold text-emerald-400">
                    Quadrant 1: Both Strong (&ge;80)
                  </CardTitle>
                  <Badge className="bg-emerald-500/20 text-emerald-400">{summary?.q1Count} Funds</Badge>
                </div>
                <p className="text-xs text-muted-foreground">
                  Action: <strong>LEAD</strong>. Highest committee conviction across both systems. Low risk of methodology whiplash.
                </p>
              </CardHeader>
              <CardContent className="p-4 pt-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setQuadrantFilter("Q1_Both_Strong");
                    setActiveTab("master");
                  }}
                  className="text-xs w-full"
                >
                  View All {summary?.q1Count} Q1 Funds in Master Table
                </Button>
              </CardContent>
            </Card>

            {/* Q2 */}
            <Card className="border-sky-500/30 bg-sky-500/5">
              <CardHeader className="p-4 pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-bold text-sky-400">
                    Quadrant 2: 2025 Modernization Strong Only
                  </CardTitle>
                  <Badge className="bg-sky-500/20 text-sky-400">{summary?.q2Count} Funds</Badge>
                </div>
                <p className="text-xs text-muted-foreground">
                  Action: <strong>REVIEW</strong>. Modernization picks benefiting from updated criteria. Staff should review key factor drivers.
                </p>
              </CardHeader>
              <CardContent className="p-4 pt-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setQuadrantFilter("Q2_Only_2025");
                    setActiveTab("master");
                  }}
                  className="text-xs w-full"
                >
                  View All {summary?.q2Count} Q2 Funds in Master Table
                </Button>
              </CardContent>
            </Card>

            {/* Q3 */}
            <Card className="border-amber-500/30 bg-amber-500/5">
              <CardHeader className="p-4 pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-bold text-amber-400">
                    Quadrant 3: 2023 Legacy Strong Only
                  </CardTitle>
                  <Badge className="bg-amber-500/20 text-amber-400">{summary?.q3Count} Funds</Badge>
                </div>
                <p className="text-xs text-muted-foreground">
                  Action: <strong>REVIEW / SCRUTINY</strong>. High-scoring legacy holdovers undergoing modern scrutiny.
                </p>
              </CardHeader>
              <CardContent className="p-4 pt-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setQuadrantFilter("Q3_Only_2023");
                    setActiveTab("master");
                  }}
                  className="text-xs w-full"
                >
                  View All {summary?.q3Count} Q3 Funds in Master Table
                </Button>
              </CardContent>
            </Card>

            {/* Q4 */}
            <Card className="border-rose-500/30 bg-rose-500/5">
              <CardHeader className="p-4 pb-2">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-bold text-rose-400">
                    Quadrant 4: Both Weak (&lt;80)
                  </CardTitle>
                  <Badge className="bg-rose-500/20 text-rose-400">{summary?.q4Count} Funds</Badge>
                </div>
                <p className="text-xs text-muted-foreground">
                  Action: <strong>WATCH / DROP</strong>. Consistent laggards in both systems. Primary candidates for replacement workbench.
                </p>
              </CardHeader>
              <CardContent className="p-4 pt-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setQuadrantFilter("Q4_Both_Weak");
                    setActiveTab("master");
                  }}
                  className="text-xs w-full"
                >
                  View All {summary?.q4Count} Q4 Funds in Master Table
                </Button>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* =======================================================================
            TAB 5: COMPARISON "WEB" (RADAR CHART)
        ======================================================================== */}
        <TabsContent value="radar" className="space-y-4">
          <Card className="bg-card border-card-border">
            <CardContent className="p-3">
              <div className="flex flex-wrap items-center gap-3">
                <span className="text-xs font-semibold text-muted-foreground">Select Fund for Factor Web:</span>
                <div className="relative w-48">
                  <Input
                    placeholder="Ticker (e.g. VFIAX)"
                    value={selectedRadarSymbol}
                    onChange={e => setSelectedRadarSymbol(e.target.value.toUpperCase())}
                    className="h-8 text-xs font-mono bg-background"
                  />
                </div>
                <Select value={selectedRadarSymbol} onValueChange={setSelectedRadarSymbol}>
                  <SelectTrigger className="w-56 h-8 text-xs">
                    <SelectValue placeholder="Quick Pick" />
                  </SelectTrigger>
                  <SelectContent>
                    {rows.slice(0, 30).map(r => (
                      <SelectItem key={r.Symbol} value={r.Symbol}>
                        {r.Symbol} — {r.Name.slice(0, 24)}...
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          {radarResponse && (
            <ComparisonRadar
              symbol={radarResponse.fund.symbol}
              name={radarResponse.fund.name}
              category={radarResponse.fund.categoryName}
              fundType={radarResponse.fund.isIndexFund ? "Passive" : "Active"}
              score={radarResponse.fund.score}
              quadrant={radarResponse.fund.quadrant}
              actionFlag={radarResponse.fund.actionFlag}
              breakdown={radarResponse.breakdown}
            />
          )}
        </TabsContent>

        {/* =======================================================================
            TAB 6: CANDIDATE REPLACEMENT WORKBENCH
        ======================================================================== */}
        <TabsContent value="workbench" className="space-y-4">
          <ReplacementWorkbenchView
            initialSymbol={selectedReplaceSymbol}
            onSelectFundForRadar={openRadarForSymbol}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}
