import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useState } from "react";
import { Search, ArrowRight } from "lucide-react";
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Tooltip,
} from "recharts";
import { useRoute, useLocation, Link } from "wouter";

function ScoreGauge({ score, band }: { score: number; band: string }) {
  const color = band === "STRONG" ? "#34d399" : band === "REVIEW" ? "#fbbf24" : "#f87171";
  const circumference = 2 * Math.PI * 70;
  const dashOffset = circumference - (score / 100) * circumference;

  return (
    <div className="relative w-48 h-48 mx-auto">
      <svg viewBox="0 0 160 160" className="w-full h-full -rotate-90">
        <circle cx="80" cy="80" r="70" fill="none" stroke="hsl(var(--border))" strokeWidth="8" />
        <circle
          cx="80" cy="80" r="70"
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          className="transition-all duration-1000"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-3xl font-bold font-mono tabular-nums" style={{ color }}>
          {score.toFixed(1)}
        </span>
        <span className="text-[11px] uppercase tracking-wider font-medium mt-0.5" style={{ color }}>
          {band}
        </span>
      </div>
    </div>
  );
}

export default function FundLookup() {
  const [, params] = useRoute("/lookup/:symbol");
  const [, setLocation] = useLocation();
  const [ticker, setTicker] = useState(params?.symbol?.toUpperCase() || "");
  const activeSymbol = params?.symbol?.toUpperCase() || "";

  const { data, isLoading, error } = useQuery<any>({
    queryKey: ["/api/funds/lookup", activeSymbol],
    enabled: !!activeSymbol,
    queryFn: async () => {
      const res = await fetch(`${("__PORT_5000__".startsWith("__") ? "" : "__PORT_5000__")}/api/funds/lookup/${activeSymbol}`);
      if (!res.ok) throw new Error("Fund not found");
      return res.json();
    },
  });

  const handleSearch = () => {
    if (ticker.trim()) {
      setLocation(`/lookup/${ticker.trim().toUpperCase()}`);
    }
  };

  const fund = data?.fund;
  const breakdown = data?.breakdown;
  const peers = data?.peers;

  // Prepare radar data
  const radarData = breakdown?.filter((b: any) => b.percentile !== null).map((b: any) => ({
    metric: b.label,
    percentile: b.percentile,
    fullMark: 100,
  })) || [];

  return (
    <div className="p-4 lg:p-6 space-y-4 max-w-[1600px]">
      <div>
        <h2 className="text-lg font-bold">Fund Lookup</h2>
        <p className="text-xs text-muted-foreground">Detailed scoring breakdown for any fund</p>
      </div>

      {/* Search Bar */}
      <Card className="bg-card border-card-border">
        <CardContent className="p-3">
          <div className="flex gap-2">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
              <Input
                placeholder="Enter ticker symbol (e.g., VFIAX, SPY)"
                value={ticker}
                onChange={e => setTicker(e.target.value.toUpperCase())}
                onKeyDown={e => e.key === "Enter" && handleSearch()}
                className="pl-8 h-9 text-sm font-mono bg-background"
                data-testid="input-ticker"
              />
            </div>
            <Button onClick={handleSearch} size="sm" className="gap-1.5" data-testid="button-lookup">
              <ArrowRight className="w-3.5 h-3.5" />
              Lookup
            </Button>
          </div>
        </CardContent>
      </Card>

      {isLoading && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <Skeleton className="h-64" />
          <Skeleton className="h-64 lg:col-span-2" />
        </div>
      )}

      {error && (
        <Card className="bg-card border-destructive/30">
          <CardContent className="p-4 text-center text-sm text-destructive">
            Fund "{activeSymbol}" not found. Check the ticker symbol.
          </CardContent>
        </Card>
      )}

      {fund && (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Score Display */}
            <Card className="bg-card border-card-border">
              <CardHeader className="pb-0 px-4 pt-4">
                <CardTitle className="text-sm font-medium text-center">
                  {fund.symbol} — {fund.isIndexFund ? "Passive" : "Active"}
                </CardTitle>
                <p className="text-xs text-muted-foreground text-center truncate">{fund.name}</p>
                <p className="text-[11px] text-muted-foreground text-center">{fund.categoryName}</p>
              </CardHeader>
              <CardContent className="p-4">
                <ScoreGauge score={fund.score || 0} band={fund.scoreBand || "WEAK"} />
                <div className="mt-3 text-center">
                  <p className="text-xs text-muted-foreground">
                    Category Percentile: <span className="font-mono font-medium text-foreground">{fund.categoryPercentile?.toFixed(0)}%</span>
                  </p>
                </div>
              </CardContent>
            </Card>

            {/* Radar Chart */}
            <Card className="bg-card border-card-border lg:col-span-2">
              <CardHeader className="pb-0 px-4 pt-4">
                <CardTitle className="text-sm font-medium">Scoring Breakdown</CardTitle>
              </CardHeader>
              <CardContent className="p-2">
                {radarData.length > 0 ? (
                  <ResponsiveContainer width="100%" height={280}>
                    <RadarChart data={radarData} outerRadius="70%">
                      <PolarGrid stroke="hsl(var(--border))" />
                      <PolarAngleAxis
                        dataKey="metric"
                        tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))" }}
                      />
                      <PolarRadiusAxis
                        angle={90}
                        domain={[0, 100]}
                        tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))" }}
                      />
                      <Radar
                        name="Percentile"
                        dataKey="percentile"
                        stroke="hsl(var(--primary))"
                        fill="hsl(var(--primary))"
                        fillOpacity={0.2}
                        strokeWidth={2}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "hsl(var(--popover))",
                          border: "1px solid hsl(var(--border))",
                          borderRadius: "6px",
                          fontSize: 12,
                        }}
                        labelStyle={{ color: "hsl(var(--foreground))" }}
                      />
                    </RadarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="h-[280px] flex items-center justify-center text-sm text-muted-foreground">
                    Insufficient data for radar chart
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Key Metrics Table */}
          <Card className="bg-card border-card-border">
            <CardHeader className="pb-2 px-4 pt-4">
              <CardTitle className="text-sm font-medium">Component Scores</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-muted/30">
                    <tr>
                      <th className="px-3 py-2 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Metric</th>
                      <th className="px-3 py-2 text-right text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Weight</th>
                      <th className="px-3 py-2 text-right text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Value</th>
                      <th className="px-3 py-2 text-right text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Percentile</th>
                      <th className="px-3 py-2 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground w-[120px]">Bar</th>
                    </tr>
                  </thead>
                  <tbody>
                    {breakdown?.map((b: any) => (
                      <tr key={b.metric} className="border-t border-border/30">
                        <td className="px-3 py-1.5 text-sm">{b.label}</td>
                        <td className="px-3 py-1.5 text-sm font-mono tabular-nums text-right text-muted-foreground">{b.weight}</td>
                        <td className="px-3 py-1.5 text-sm font-mono tabular-nums text-right">
                          {b.value !== null ? (typeof b.value === "number" ? b.value.toFixed(4) : b.value) : "—"}
                        </td>
                        <td className="px-3 py-1.5 text-sm font-mono tabular-nums text-right">
                          {b.percentile !== null ? (
                            <span className={b.percentile >= 75 ? "text-emerald-400" : b.percentile >= 50 ? "text-amber-400" : "text-red-400"}>
                              {b.percentile}%
                            </span>
                          ) : "—"}
                        </td>
                        <td className="px-3 py-1.5">
                          {b.percentile !== null && (
                            <div className="h-2 bg-muted rounded-full overflow-hidden">
                              <div
                                className="h-full rounded-full transition-all"
                                style={{
                                  width: `${b.percentile}%`,
                                  backgroundColor: b.percentile >= 75 ? "#34d399" : b.percentile >= 50 ? "#fbbf24" : "#f87171",
                                }}
                              />
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardContent>
          </Card>

          {/* Category Peers */}
          {peers && peers.length > 0 && (
            <Card className="bg-card border-card-border">
              <CardHeader className="pb-2 px-4 pt-4">
                <CardTitle className="text-sm font-medium">Category Peers — {fund.categoryName}</CardTitle>
              </CardHeader>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="bg-muted/30">
                      <tr>
                        <th className="px-3 py-2 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">#</th>
                        <th className="px-3 py-2 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Symbol</th>
                        <th className="px-3 py-2 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Name</th>
                        <th className="px-3 py-2 text-right text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Expense</th>
                        <th className="px-3 py-2 text-right text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Score</th>
                      </tr>
                    </thead>
                    <tbody>
                      {peers.map((p: any, i: number) => (
                        <tr
                          key={p.symbol}
                          className={`border-t border-border/30 ${p.symbol === fund.symbol ? "bg-primary/5" : "hover:bg-accent/30"} transition-colors`}
                        >
                          <td className="px-3 py-1.5 text-xs text-muted-foreground font-mono">{i + 1}</td>
                          <td className="px-3 py-1.5">
                            <Link href={`/lookup/${p.symbol}`} className="text-sm font-mono font-medium text-primary hover:underline">
                              {p.symbol}
                            </Link>
                          </td>
                          <td className="px-3 py-1.5 text-sm truncate max-w-[250px]">{p.name}</td>
                          <td className="px-3 py-1.5 text-sm font-mono tabular-nums text-right text-muted-foreground">
                            {p.netExpenseRatio !== null ? `${(p.netExpenseRatio * 100).toFixed(2)}%` : "—"}
                          </td>
                          <td className="px-3 py-1.5 text-sm font-mono font-bold tabular-nums text-right">
                            <span className={p.score >= 80 ? "text-emerald-400" : p.score >= 60 ? "text-amber-400" : "text-red-400"}>
                              {p.score?.toFixed(1)}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {!activeSymbol && !isLoading && (
        <div className="flex items-center justify-center h-64 text-muted-foreground text-sm">
          Enter a ticker symbol above to view detailed scoring
        </div>
      )}
    </div>
  );
}
