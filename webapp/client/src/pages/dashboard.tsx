import { useQuery } from "@tanstack/react-query";
import { apiRequest } from "@/lib/queryClient";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { TrendingUp, TrendingDown, Activity, Hash, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { Fund } from "@shared/schema";
import { Link } from "wouter";

function ScoreBadge({ score, band }: { score: number; band: string }) {
  const colorClass = band === "STRONG" ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/20"
    : band === "REVIEW" ? "bg-amber-500/15 text-amber-400 border-amber-500/20"
    : "bg-red-500/15 text-red-400 border-red-500/20";

  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-mono font-medium border ${colorClass}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${band === "STRONG" ? "bg-emerald-400" : band === "REVIEW" ? "bg-amber-400" : "bg-red-400"}`} />
      {score.toFixed(1)}
    </span>
  );
}

function KpiCard({ title, value, subtitle, icon: Icon, loading }: {
  title: string; value: string; subtitle?: string; icon: any; loading: boolean;
}) {
  return (
    <Card className="bg-card border-card-border">
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">{title}</p>
            {loading ? (
              <Skeleton className="h-7 w-20 mt-1" />
            ) : (
              <p className="text-xl font-bold font-mono tabular-nums mt-0.5" data-testid={`kpi-${title.toLowerCase().replace(/\s/g, "-")}`}>{value}</p>
            )}
            {subtitle && <p className="text-[11px] text-muted-foreground mt-0.5">{subtitle}</p>}
          </div>
          <div className="p-2 rounded-lg bg-primary/10">
            <Icon className="w-4 h-4 text-primary" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function FundRow({ fund, rank }: { fund: Fund; rank: number }) {
  return (
    <Link href={`/lookup/${fund.symbol}`}>
      <div className="flex items-center gap-3 px-3 py-2 hover:bg-accent/50 rounded-md cursor-pointer transition-colors" data-testid={`fund-row-${fund.symbol}`}>
        <span className="text-xs text-muted-foreground font-mono w-5 text-right">{rank}</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">{fund.symbol}</p>
          <p className="text-[11px] text-muted-foreground truncate">{fund.name}</p>
        </div>
        <ScoreBadge score={fund.score || 0} band={fund.scoreBand || "WEAK"} />
      </div>
    </Link>
  );
}

export default function Dashboard() {
  const { data: stats, isLoading } = useQuery<any>({
    queryKey: ["/api/stats"],
  });

  const { data: topFunds } = useQuery<Fund[]>({
    queryKey: ["/api/funds/top/10"],
  });

  const { data: bottomFunds } = useQuery<Fund[]>({
    queryKey: ["/api/funds/bottom/10"],
  });

  const getBarColor = (range: string) => {
    const start = parseInt(range.split("-")[0]);
    if (start >= 80) return "hsl(145, 55%, 50%)";
    if (start >= 60) return "hsl(45, 75%, 55%)";
    return "hsl(0, 60%, 55%)";
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

  return (
    <div className="p-4 lg:p-6 space-y-6 max-w-[1600px]">
      {/* Header with PDF button */}
      <div className="flex items-center justify-between">
        <div />
        <Button
          variant="outline"
          size="sm"
          onClick={downloadPdf}
          className="text-xs gap-1.5"
        >
          <FileText className="w-3.5 h-3.5" />
          Generate Report
        </Button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <KpiCard
          title="Funds Scored"
          value={stats?.total?.toLocaleString() || "0"}
          icon={Hash}
          loading={isLoading}
        />
        <KpiCard
          title="Avg Score"
          value={stats?.avgScore?.toFixed(1) || "0"}
          icon={Activity}
          loading={isLoading}
        />
        <KpiCard
          title="Strong (≥80)"
          value={`${stats?.strongPct?.toFixed(1) || "0"}%`}
          subtitle={`${stats?.strongCount || 0} funds`}
          icon={TrendingUp}
          loading={isLoading}
        />
        <KpiCard
          title="Weak (<60)"
          value={`${stats?.weakPct?.toFixed(1) || "0"}%`}
          subtitle={`${stats?.weakCount || 0} funds`}
          icon={TrendingDown}
          loading={isLoading}
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {/* Score Distribution Histogram */}
        <Card className="bg-card border-card-border">
          <CardHeader className="pb-2 px-4 pt-4">
            <CardTitle className="text-sm font-medium">Score Distribution</CardTitle>
          </CardHeader>
          <CardContent className="px-2 pb-3">
            {stats?.histogram ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={stats.histogram} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="range" tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} interval={1} />
                  <YAxis tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} />
                  <Tooltip
                    contentStyle={{ backgroundColor: "hsl(var(--popover))", border: "1px solid hsl(var(--border))", borderRadius: "6px", fontSize: 12 }}
                    labelStyle={{ color: "hsl(var(--foreground))" }}
                    itemStyle={{ color: "hsl(var(--foreground))" }}
                  />
                  <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                    {stats.histogram.map((entry: any, i: number) => (
                      <Cell key={i} fill={getBarColor(entry.range)} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <Skeleton className="h-[220px]" />
            )}
          </CardContent>
        </Card>

        {/* Category Breakdown */}
        <Card className="bg-card border-card-border">
          <CardHeader className="pb-2 px-4 pt-4">
            <CardTitle className="text-sm font-medium">Avg Score by Category (Top 12)</CardTitle>
          </CardHeader>
          <CardContent className="px-2 pb-3">
            {stats?.categoryBreakdown ? (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart
                  data={stats.categoryBreakdown.slice(0, 12)}
                  layout="vertical"
                  margin={{ top: 5, right: 10, left: 0, bottom: 0 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} />
                  <YAxis dataKey="name" type="category" width={130} tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))" }} />
                  <Tooltip
                    contentStyle={{ backgroundColor: "hsl(var(--popover))", border: "1px solid hsl(var(--border))", borderRadius: "6px", fontSize: 12 }}
                    labelStyle={{ color: "hsl(var(--foreground))" }}
                    itemStyle={{ color: "hsl(var(--foreground))" }}
                    formatter={(value: number) => [`${value.toFixed(1)}`, 'Avg Score']}
                  />
                  <Bar dataKey="avgScore" radius={[0, 3, 3, 0]}>
                    {stats.categoryBreakdown.slice(0, 12).map((entry: any, i: number) => {
                      // Use a gradient of colors from green through yellow to red
                      const score = entry.avgScore;
                      let fill;
                      if (score >= 70) fill = "hsl(145, 55%, 50%)";
                      else if (score >= 60) fill = "hsl(80, 55%, 50%)";
                      else if (score >= 55) fill = "hsl(45, 75%, 55%)";
                      else if (score >= 50) fill = "hsl(30, 70%, 50%)";
                      else fill = "hsl(0, 60%, 55%)";
                      return <Cell key={i} fill={fill} />;
                    })}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <Skeleton className="h-[220px]" />
            )}
          </CardContent>
        </Card>
      </div>

      {/* Top / Bottom Tables */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="bg-card border-card-border">
          <CardHeader className="pb-2 px-4 pt-4">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-emerald-400" />
              Top 10 Funds
            </CardTitle>
          </CardHeader>
          <CardContent className="px-2 pb-3">
            {topFunds ? (
              <div className="space-y-0.5">
                {topFunds.map((f, i) => <FundRow key={f.id} fund={f} rank={i + 1} />)}
              </div>
            ) : (
              Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-10 mb-1" />)
            )}
          </CardContent>
        </Card>

        <Card className="bg-card border-card-border">
          <CardHeader className="pb-2 px-4 pt-4">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <TrendingDown className="w-4 h-4 text-red-400" />
              Bottom 10 Funds
            </CardTitle>
          </CardHeader>
          <CardContent className="px-2 pb-3">
            {bottomFunds ? (
              <div className="space-y-0.5">
                {bottomFunds.map((f, i) => <FundRow key={f.id} fund={f} rank={i + 1} />)}
              </div>
            ) : (
              Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-10 mb-1" />)
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
