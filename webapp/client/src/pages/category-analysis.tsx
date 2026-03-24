import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { useRoute, useLocation, Link } from "wouter";
import { Hash, TrendingUp, TrendingDown, Activity } from "lucide-react";
import type { Fund } from "@shared/schema";

function ScoreBadge({ score, band }: { score: number; band: string }) {
  const colorClass = band === "STRONG" ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/20"
    : band === "REVIEW" ? "bg-amber-500/15 text-amber-400 border-amber-500/20"
    : "bg-red-500/15 text-red-400 border-red-500/20";
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-mono font-medium border ${colorClass}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${band === "STRONG" ? "bg-emerald-400" : band === "REVIEW" ? "bg-amber-400" : "bg-red-400"}`} />
      {score.toFixed(1)}
    </span>
  );
}

export default function CategoryAnalysis() {
  const [, params] = useRoute("/categories/:name");
  const [, setLocation] = useLocation();
  const selectedCategory = params?.name ? decodeURIComponent(params.name) : "";

  const { data: categories } = useQuery<string[]>({ queryKey: ["/api/categories"] });

  const { data: catData, isLoading } = useQuery<any>({
    queryKey: ["/api/categories", selectedCategory],
    enabled: !!selectedCategory,
    queryFn: async () => {
      const res = await fetch(`${("__PORT_5000__".startsWith("__") ? "" : "__PORT_5000__")}/api/categories/${encodeURIComponent(selectedCategory)}`);
      if (!res.ok) throw new Error("Category not found");
      return res.json();
    },
  });

  const getBarColor = (range: string) => {
    const start = parseInt(range.split("-")[0]);
    if (start >= 80) return "hsl(145, 55%, 50%)";
    if (start >= 60) return "hsl(45, 75%, 55%)";
    return "hsl(0, 60%, 55%)";
  };

  return (
    <div className="p-4 lg:p-6 space-y-4 max-w-[1600px]">
      <div>
        <h2 className="text-lg font-bold">Category Analysis</h2>
        <p className="text-xs text-muted-foreground">Score distribution and rankings within categories</p>
      </div>

      {/* Category Selector */}
      <Card className="bg-card border-card-border">
        <CardContent className="p-3">
          <Select
            value={selectedCategory}
            onValueChange={v => setLocation(`/categories/${encodeURIComponent(v)}`)}
          >
            <SelectTrigger className="w-full max-w-md h-9 text-sm" data-testid="select-category">
              <SelectValue placeholder="Select a category..." />
            </SelectTrigger>
            <SelectContent>
              {categories?.map(c => (
                <SelectItem key={c} value={c}>{c}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardContent>
      </Card>

      {!selectedCategory && (
        <div className="flex items-center justify-center h-64 text-muted-foreground text-sm">
          Select a category above to view analysis
        </div>
      )}

      {isLoading && selectedCategory && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20" />)}
        </div>
      )}

      {catData && (
        <>
          {/* KPIs */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <Card className="bg-card border-card-border">
              <CardContent className="p-3">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Total Funds</p>
                <p className="text-xl font-bold font-mono tabular-nums">{catData.totalFunds}</p>
              </CardContent>
            </Card>
            <Card className="bg-card border-card-border">
              <CardContent className="p-3">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Avg Score</p>
                <p className="text-xl font-bold font-mono tabular-nums">{catData.avgScore.toFixed(1)}</p>
              </CardContent>
            </Card>
            <Card className="bg-card border-card-border">
              <CardContent className="p-3">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Strong (≥80)</p>
                <p className="text-xl font-bold font-mono tabular-nums text-emerald-400">{catData.strongCount}</p>
              </CardContent>
            </Card>
            <Card className="bg-card border-card-border">
              <CardContent className="p-3">
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Weak (&lt;60)</p>
                <p className="text-xl font-bold font-mono tabular-nums text-red-400">{catData.weakCount}</p>
              </CardContent>
            </Card>
          </div>

          {/* Distribution */}
          <Card className="bg-card border-card-border">
            <CardHeader className="pb-2 px-4 pt-4">
              <CardTitle className="text-sm font-medium">Score Distribution — {catData.name}</CardTitle>
            </CardHeader>
            <CardContent className="px-2 pb-3">
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={catData.distribution} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="range" tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} />
                  <YAxis tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} />
                  <Tooltip
                    contentStyle={{ backgroundColor: "hsl(var(--popover))", border: "1px solid hsl(var(--border))", borderRadius: "6px", fontSize: 12 }}
                    labelStyle={{ color: "hsl(var(--foreground))" }}
                    itemStyle={{ color: "hsl(var(--foreground))" }}
                  />
                  <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                    {catData.distribution.map((entry: any, i: number) => (
                      <Cell key={i} fill={getBarColor(entry.range)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* All funds ranked */}
          <Card className="bg-card border-card-border">
            <CardHeader className="pb-2 px-4 pt-4">
              <CardTitle className="text-sm font-medium">All Funds Ranked — {catData.name}</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto max-h-[500px] overflow-y-auto">
                <table className="w-full">
                  <thead className="bg-muted/30 sticky top-0 z-[1]">
                    <tr>
                      <th className="px-3 py-2 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground w-10">#</th>
                      <th className="px-3 py-2 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Symbol</th>
                      <th className="px-3 py-2 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Name</th>
                      <th className="px-3 py-2 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground w-16">Type</th>
                      <th className="px-3 py-2 text-right text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Expense</th>
                      <th className="px-3 py-2 text-right text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Score</th>
                      <th className="px-3 py-2 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Band</th>
                    </tr>
                  </thead>
                  <tbody>
                    {catData.allFunds?.map((f: Fund, i: number) => (
                      <tr key={f.id} className="border-t border-border/30 hover:bg-accent/30 transition-colors">
                        <td className="px-3 py-1.5 text-xs text-muted-foreground font-mono">{i + 1}</td>
                        <td className="px-3 py-1.5">
                          <Link href={`/lookup/${f.symbol}`} className="text-sm font-mono font-medium text-primary hover:underline">
                            {f.symbol}
                          </Link>
                        </td>
                        <td className="px-3 py-1.5 text-sm truncate max-w-[250px]">{f.name}</td>
                        <td className="px-3 py-1.5">
                          <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${f.isIndexFund ? "bg-blue-500/10 text-blue-400" : "bg-purple-500/10 text-purple-400"}`}>
                            {f.isIndexFund ? "IDX" : "ACT"}
                          </span>
                        </td>
                        <td className="px-3 py-1.5 text-sm font-mono tabular-nums text-right text-muted-foreground">
                          {f.netExpenseRatio !== null ? `${(f.netExpenseRatio! * 100).toFixed(2)}%` : "—"}
                        </td>
                        <td className="px-3 py-1.5 text-sm font-mono font-bold tabular-nums text-right">
                          <span className={f.score! >= 80 ? "text-emerald-400" : f.score! >= 60 ? "text-amber-400" : "text-red-400"}>
                            {f.score?.toFixed(1)}
                          </span>
                        </td>
                        <td className="px-3 py-1.5">
                          <ScoreBadge score={f.score || 0} band={f.scoreBand || "WEAK"} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
