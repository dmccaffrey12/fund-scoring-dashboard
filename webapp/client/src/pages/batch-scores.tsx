import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/lib/queryClient";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useState, useMemo } from "react";
import { Download, Search, ArrowUpDown, Filter, FileText } from "lucide-react";
import type { Fund } from "@shared/schema";
import { Link } from "wouter";

function ScoreBadge({ score, band }: { score: number; band: string }) {
  const colorClass = band === "STRONG" ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/20"
    : band === "REVIEW" ? "bg-amber-500/15 text-amber-400 border-amber-500/20"
    : "bg-red-500/15 text-red-400 border-red-500/20";
  const dotClass = band === "STRONG" ? "bg-emerald-400" : band === "REVIEW" ? "bg-amber-400" : "bg-red-400";

  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-mono font-medium border ${colorClass}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dotClass}`} />
      {band}
    </span>
  );
}

export default function BatchScores() {
  const { data: funds, isLoading } = useQuery<Fund[]>({ queryKey: ["/api/funds"] });
  const { data: categories } = useQuery<string[]>({ queryKey: ["/api/categories"] });

  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [sortField, setSortField] = useState<"score" | "symbol" | "netExpenseRatio" | "categoryPercentile">("score");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [scoreMin, setScoreMin] = useState("");
  const [scoreMax, setScoreMax] = useState("");

  const filtered = useMemo(() => {
    if (!funds) return [];
    let result = funds.filter(f => f.score !== null);

    if (search) {
      const q = search.toLowerCase();
      result = result.filter(f =>
        f.symbol.toLowerCase().includes(q) ||
        f.name.toLowerCase().includes(q)
      );
    }

    if (categoryFilter !== "all") {
      result = result.filter(f => f.categoryName === categoryFilter);
    }

    if (typeFilter !== "all") {
      result = result.filter(f => typeFilter === "passive" ? f.isIndexFund : !f.isIndexFund);
    }

    if (scoreMin) {
      result = result.filter(f => (f.score || 0) >= parseFloat(scoreMin));
    }
    if (scoreMax) {
      result = result.filter(f => (f.score || 0) <= parseFloat(scoreMax));
    }

    result.sort((a, b) => {
      const aVal = a[sortField] ?? 0;
      const bVal = b[sortField] ?? 0;
      const cmp = typeof aVal === "string" ? aVal.localeCompare(bVal as string) : (aVal as number) - (bVal as number);
      return sortDir === "asc" ? cmp : -cmp;
    });

    return result;
  }, [funds, search, categoryFilter, typeFilter, sortField, sortDir, scoreMin, scoreMax]);

  const handleSort = (field: typeof sortField) => {
    if (sortField === field) {
      setSortDir(d => d === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDir("desc");
    }
  };

  const exportCSV = async () => {
    const res = await apiRequest("GET", "/api/export/csv");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "fund_scores.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadPdf = async () => {
    const API_BASE = "__PORT_5000__".startsWith("__") ? "" : "__PORT_5000__";
    const res = await fetch(`${API_BASE}/api/export/pdf`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "fund_scoring_report.pdf";
    a.click();
    URL.revokeObjectURL(url);
  };

  const SortHeader = ({ field, label, className }: { field: typeof sortField; label: string; className?: string }) => (
    <th
      className={`px-3 py-2 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground cursor-pointer hover:text-foreground select-none ${className || ""}`}
      onClick={() => handleSort(field)}
    >
      <span className="flex items-center gap-1">
        {label}
        {sortField === field && (
          <ArrowUpDown className="w-3 h-3" />
        )}
      </span>
    </th>
  );

  return (
    <div className="p-4 lg:p-6 space-y-4 max-w-[1600px]">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold">Batch Scores</h2>
          <p className="text-xs text-muted-foreground">{filtered.length.toLocaleString()} funds displayed</p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={downloadPdf}
            className="text-xs gap-1.5"
          >
            <FileText className="w-3.5 h-3.5" />
            Generate Report
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={exportCSV}
            className="text-xs gap-1.5"
            data-testid="button-export-csv"
          >
            <Download className="w-3.5 h-3.5" />
            Export CSV
          </Button>
        </div>
      </div>

      {/* Filters */}
      <Card className="bg-card border-card-border">
        <CardContent className="p-3">
          <div className="flex flex-wrap gap-2 items-center">
            <div className="relative flex-1 min-w-[200px] max-w-sm">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
              <Input
                placeholder="Search symbol or name..."
                value={search}
                onChange={e => setSearch(e.target.value)}
                className="pl-8 h-8 text-sm bg-background"
                data-testid="input-search"
              />
            </div>
            <Select value={categoryFilter} onValueChange={setCategoryFilter}>
              <SelectTrigger className="w-[180px] h-8 text-xs" data-testid="select-category">
                <Filter className="w-3 h-3 mr-1" />
                <SelectValue placeholder="Category" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Categories</SelectItem>
                {categories?.map(c => (
                  <SelectItem key={c} value={c}>{c}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={typeFilter} onValueChange={setTypeFilter}>
              <SelectTrigger className="w-[130px] h-8 text-xs" data-testid="select-type">
                <SelectValue placeholder="Fund Type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Types</SelectItem>
                <SelectItem value="active">Active</SelectItem>
                <SelectItem value="passive">Passive</SelectItem>
              </SelectContent>
            </Select>
            <div className="flex items-center gap-1">
              <Input
                type="number"
                placeholder="Min"
                value={scoreMin}
                onChange={e => setScoreMin(e.target.value)}
                className="w-16 h-8 text-xs bg-background"
                data-testid="input-score-min"
              />
              <span className="text-xs text-muted-foreground">–</span>
              <Input
                type="number"
                placeholder="Max"
                value={scoreMax}
                onChange={e => setScoreMax(e.target.value)}
                className="w-16 h-8 text-xs bg-background"
                data-testid="input-score-max"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Data Table */}
      <Card className="bg-card border-card-border overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-muted/30 sticky top-0 z-[1]">
              <tr>
                <SortHeader field="symbol" label="Symbol" className="w-[90px]" />
                <th className="px-3 py-2 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Name</th>
                <th className="px-3 py-2 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Category</th>
                <th className="px-3 py-2 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground w-[70px]">Type</th>
                <SortHeader field="netExpenseRatio" label="Expense" className="w-[80px]" />
                <SortHeader field="score" label="Score" className="w-[100px]" />
                <th className="px-3 py-2 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground w-[90px]">Band</th>
                <SortHeader field="categoryPercentile" label="Cat %ile" className="w-[80px]" />
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                Array.from({ length: 20 }).map((_, i) => (
                  <tr key={i} className="border-t border-border/50">
                    <td colSpan={8} className="px-3 py-2"><Skeleton className="h-5" /></td>
                  </tr>
                ))
              ) : (
                filtered.slice(0, 200).map(fund => (
                  <tr
                    key={fund.id}
                    className="border-t border-border/30 hover:bg-accent/30 transition-colors cursor-pointer"
                    data-testid={`row-fund-${fund.symbol}`}
                  >
                    <td className="px-3 py-1.5">
                      <Link href={`/lookup/${fund.symbol}`} className="text-sm font-mono font-medium text-primary hover:underline">
                        {fund.symbol}
                      </Link>
                    </td>
                    <td className="px-3 py-1.5 text-sm truncate max-w-[250px]">{fund.name}</td>
                    <td className="px-3 py-1.5 text-xs text-muted-foreground truncate max-w-[160px]">{fund.categoryName}</td>
                    <td className="px-3 py-1.5">
                      <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${fund.isIndexFund ? "bg-blue-500/10 text-blue-400" : "bg-purple-500/10 text-purple-400"}`}>
                        {fund.isIndexFund ? "IDX" : "ACT"}
                      </span>
                    </td>
                    <td className="px-3 py-1.5 text-sm font-mono tabular-nums">
                      {fund.netExpenseRatio !== null ? `${(fund.netExpenseRatio * 100).toFixed(2)}%` : "—"}
                    </td>
                    <td className="px-3 py-1.5 text-sm font-mono font-bold tabular-nums">
                      <span className={fund.score! >= 80 ? "text-emerald-400" : fund.score! >= 60 ? "text-amber-400" : "text-red-400"}>
                        {fund.score?.toFixed(1)}
                      </span>
                    </td>
                    <td className="px-3 py-1.5">
                      <ScoreBadge score={fund.score || 0} band={fund.scoreBand || "WEAK"} />
                    </td>
                    <td className="px-3 py-1.5 text-sm font-mono tabular-nums text-muted-foreground">
                      {fund.categoryPercentile?.toFixed(0)}%
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {filtered.length > 200 && (
          <div className="p-3 text-center text-xs text-muted-foreground border-t border-border/30">
            Showing 200 of {filtered.length.toLocaleString()} results. Use filters to narrow down.
          </div>
        )}
      </Card>
    </div>
  );
}
