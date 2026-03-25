import { useQuery, useMutation } from "@tanstack/react-query";
import { apiRequest, queryClient } from "@/lib/queryClient";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import { Camera, TrendingUp, TrendingDown, Search, Calendar } from "lucide-react";
import type { ScoreSnapshot } from "@shared/schema";

type SnapshotSummary = {
  snapshotDate: string;
  snapshotLabel: string | null;
  fundCount: number;
};

type ComparisonRow = {
  symbol: string;
  categoryName: string | null;
  fromScore: number | null;
  toScore: number | null;
  delta: number;
  fromBand: string | null;
  toBand: string | null;
};

export default function History() {
  const { toast } = useToast();
  const [compareFrom, setCompareFrom] = useState("");
  const [compareTo, setCompareTo] = useState("");
  const [lookupSymbol, setLookupSymbol] = useState("");
  const [searchedSymbol, setSearchedSymbol] = useState("");

  const { data: snapshots, isLoading: snapshotsLoading } = useQuery<SnapshotSummary[]>({
    queryKey: ["/api/snapshots"],
  });

  const createSnapshotMutation = useMutation({
    mutationFn: async () => {
      const res = await apiRequest("POST", "/api/snapshots", {});
      return res.json();
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["/api/snapshots"] });
      toast({ title: "Snapshot created", description: `Captured ${data.count} fund scores` });
    },
    onError: (err: Error) => {
      toast({ title: "Error", description: err.message, variant: "destructive" });
    },
  });

  const { data: comparison } = useQuery<ComparisonRow[]>({
    queryKey: ["/api/snapshots/compare", compareFrom, compareTo],
    enabled: !!compareFrom && !!compareTo && compareFrom !== compareTo,
    queryFn: async () => {
      const res = await fetch(
        `${("__PORT_5000__".startsWith("__") ? "" : "__PORT_5000__")}/api/snapshots/compare?from=${encodeURIComponent(compareFrom)}&to=${encodeURIComponent(compareTo)}`
      );
      if (!res.ok) throw new Error("Failed to compare snapshots");
      return res.json();
    },
  });

  const { data: fundHistory } = useQuery<ScoreSnapshot[]>({
    queryKey: ["/api/history", searchedSymbol],
    enabled: !!searchedSymbol,
    queryFn: async () => {
      const res = await fetch(
        `${("__PORT_5000__".startsWith("__") ? "" : "__PORT_5000__")}/api/history/${encodeURIComponent(searchedSymbol)}`
      );
      if (!res.ok) throw new Error("Failed to fetch fund history");
      return res.json();
    },
  });

  // Build trend chart data from snapshots
  const { data: trendData } = useQuery<any[]>({
    queryKey: ["/api/snapshots/trend"],
    enabled: !!snapshots && snapshots.length > 0,
    queryFn: async () => {
      if (!snapshots || snapshots.length === 0) return [];
      const results: any[] = [];
      for (const snap of [...snapshots].reverse()) {
        const res = await fetch(
          `${("__PORT_5000__".startsWith("__") ? "" : "__PORT_5000__")}/api/snapshots/${encodeURIComponent(snap.snapshotDate)}`
        );
        if (!res.ok) continue;
        const scores: ScoreSnapshot[] = await res.json();
        const scored = scores.filter(s => s.score !== null);
        const overall = scored.length > 0 ? scored.reduce((a, s) => a + s.score!, 0) / scored.length : 0;
        const passive = scored.filter(s => s.isIndexFund);
        const active = scored.filter(s => !s.isIndexFund);
        const passiveAvg = passive.length > 0 ? passive.reduce((a, s) => a + s.score!, 0) / passive.length : 0;
        const activeAvg = active.length > 0 ? active.reduce((a, s) => a + s.score!, 0) / active.length : 0;
        results.push({
          date: snap.snapshotDate,
          label: snap.snapshotLabel || snap.snapshotDate,
          overall: Math.round(overall * 10) / 10,
          passive: Math.round(passiveAvg * 10) / 10,
          active: Math.round(activeAvg * 10) / 10,
        });
      }
      return results;
    },
  });

  const handleLookup = () => {
    if (lookupSymbol.trim()) {
      setSearchedSymbol(lookupSymbol.trim().toUpperCase());
    }
  };

  const improvers = comparison?.filter(c => c.delta > 0).slice(0, 15) || [];
  const decliners = comparison?.filter(c => c.delta < 0).slice(0, 15) || [];

  return (
    <div className="p-4 lg:p-6 space-y-6 max-w-[1600px]">
      <div>
        <h2 className="text-lg font-bold">Historical Score Tracking</h2>
        <p className="text-xs text-muted-foreground">Track score changes across snapshots over time</p>
      </div>

      {/* Snapshot Management */}
      <Card className="bg-card border-card-border">
        <CardHeader className="pb-2 px-4 pt-4">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Camera className="w-4 h-4 text-primary" />
              Snapshots
            </CardTitle>
            <Button
              size="sm"
              onClick={() => createSnapshotMutation.mutate()}
              disabled={createSnapshotMutation.isPending}
              className="text-xs gap-1.5"
            >
              <Camera className="w-3.5 h-3.5" />
              {createSnapshotMutation.isPending ? "Creating..." : "Take Snapshot"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="px-4 pb-3">
          {snapshotsLoading ? (
            <Skeleton className="h-16" />
          ) : snapshots && snapshots.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-muted/30">
                  <tr>
                    <th className="px-3 py-2 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Date</th>
                    <th className="px-3 py-2 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Label</th>
                    <th className="px-3 py-2 text-right text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Funds</th>
                  </tr>
                </thead>
                <tbody>
                  {snapshots.map((s) => (
                    <tr key={s.snapshotDate} className="border-t border-border/30 hover:bg-accent/30 transition-colors">
                      <td className="px-3 py-1.5 text-sm font-mono">{s.snapshotDate}</td>
                      <td className="px-3 py-1.5 text-sm text-muted-foreground">{s.snapshotLabel || "—"}</td>
                      <td className="px-3 py-1.5 text-sm font-mono text-right tabular-nums">{s.fundCount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground text-center py-4">
              No snapshots yet. Upload data or take a manual snapshot.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Score Trend Chart */}
      {trendData && trendData.length > 1 && (
        <Card className="bg-card border-card-border">
          <CardHeader className="pb-2 px-4 pt-4">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Calendar className="w-4 h-4 text-primary" />
              Score Trends Over Time
            </CardTitle>
          </CardHeader>
          <CardContent className="px-2 pb-3">
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={trendData} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis
                  dataKey="label"
                  tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                />
                <YAxis
                  domain={[0, 100]}
                  tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "hsl(var(--popover))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "6px",
                    fontSize: 12,
                  }}
                  labelStyle={{ color: "hsl(var(--foreground))" }}
                  itemStyle={{ color: "hsl(var(--foreground))" }}
                />
                <Legend
                  wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
                />
                <Line type="monotone" dataKey="overall" name="Overall Avg" stroke="hsl(var(--primary))" strokeWidth={2} dot={{ r: 4 }} />
                <Line type="monotone" dataKey="passive" name="Passive Avg" stroke="#3b82f6" strokeWidth={2} dot={{ r: 3 }} />
                <Line type="monotone" dataKey="active" name="Active Avg" stroke="#a855f7" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Version Comparison */}
      {snapshots && snapshots.length >= 2 && (
        <Card className="bg-card border-card-border">
          <CardHeader className="pb-2 px-4 pt-4">
            <CardTitle className="text-sm font-medium">Snapshot Comparison</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <Select value={compareFrom} onValueChange={setCompareFrom}>
                <SelectTrigger className="w-[200px] h-8 text-xs">
                  <SelectValue placeholder="From snapshot..." />
                </SelectTrigger>
                <SelectContent>
                  {snapshots.map(s => (
                    <SelectItem key={s.snapshotDate} value={s.snapshotDate}>
                      {s.snapshotLabel || s.snapshotDate}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <span className="text-xs text-muted-foreground">→</span>
              <Select value={compareTo} onValueChange={setCompareTo}>
                <SelectTrigger className="w-[200px] h-8 text-xs">
                  <SelectValue placeholder="To snapshot..." />
                </SelectTrigger>
                <SelectContent>
                  {snapshots.map(s => (
                    <SelectItem key={s.snapshotDate} value={s.snapshotDate}>
                      {s.snapshotLabel || s.snapshotDate}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {comparison && (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Improvers */}
                <div>
                  <h4 className="text-xs font-semibold text-emerald-400 mb-2 flex items-center gap-1.5">
                    <TrendingUp className="w-3.5 h-3.5" /> Top Improvers
                  </h4>
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead className="bg-muted/30">
                        <tr>
                          <th className="px-2 py-1.5 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Symbol</th>
                          <th className="px-2 py-1.5 text-right text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">From</th>
                          <th className="px-2 py-1.5 text-right text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">To</th>
                          <th className="px-2 py-1.5 text-right text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Delta</th>
                        </tr>
                      </thead>
                      <tbody>
                        {improvers.map(c => (
                          <tr key={c.symbol} className="border-t border-border/30">
                            <td className="px-2 py-1 text-sm font-mono font-medium text-primary">{c.symbol}</td>
                            <td className="px-2 py-1 text-sm font-mono tabular-nums text-right text-muted-foreground">{c.fromScore?.toFixed(1) ?? "—"}</td>
                            <td className="px-2 py-1 text-sm font-mono tabular-nums text-right">{c.toScore?.toFixed(1) ?? "—"}</td>
                            <td className="px-2 py-1 text-sm font-mono font-bold tabular-nums text-right text-emerald-400">+{c.delta.toFixed(1)}</td>
                          </tr>
                        ))}
                        {improvers.length === 0 && (
                          <tr><td colSpan={4} className="px-2 py-3 text-center text-xs text-muted-foreground">No improvers</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Decliners */}
                <div>
                  <h4 className="text-xs font-semibold text-red-400 mb-2 flex items-center gap-1.5">
                    <TrendingDown className="w-3.5 h-3.5" /> Top Decliners
                  </h4>
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead className="bg-muted/30">
                        <tr>
                          <th className="px-2 py-1.5 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Symbol</th>
                          <th className="px-2 py-1.5 text-right text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">From</th>
                          <th className="px-2 py-1.5 text-right text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">To</th>
                          <th className="px-2 py-1.5 text-right text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Delta</th>
                        </tr>
                      </thead>
                      <tbody>
                        {decliners.map(c => (
                          <tr key={c.symbol} className="border-t border-border/30">
                            <td className="px-2 py-1 text-sm font-mono font-medium text-primary">{c.symbol}</td>
                            <td className="px-2 py-1 text-sm font-mono tabular-nums text-right text-muted-foreground">{c.fromScore?.toFixed(1) ?? "—"}</td>
                            <td className="px-2 py-1 text-sm font-mono tabular-nums text-right">{c.toScore?.toFixed(1) ?? "—"}</td>
                            <td className="px-2 py-1 text-sm font-mono font-bold tabular-nums text-right text-red-400">{c.delta.toFixed(1)}</td>
                          </tr>
                        ))}
                        {decliners.length === 0 && (
                          <tr><td colSpan={4} className="px-2 py-3 text-center text-xs text-muted-foreground">No decliners</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Fund History Lookup */}
      <Card className="bg-card border-card-border">
        <CardHeader className="pb-2 px-4 pt-4">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <Search className="w-4 h-4 text-primary" />
            Fund History Lookup
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-4 space-y-3">
          <div className="flex items-center gap-2">
            <Input
              placeholder="Enter ticker symbol..."
              value={lookupSymbol}
              onChange={e => setLookupSymbol(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleLookup()}
              className="max-w-xs h-8 text-sm bg-background font-mono"
            />
            <Button size="sm" onClick={handleLookup} className="text-xs gap-1.5">
              <Search className="w-3.5 h-3.5" />
              Lookup
            </Button>
          </div>

          {searchedSymbol && fundHistory && fundHistory.length > 0 && (
            <>
              <p className="text-xs text-muted-foreground">
                {searchedSymbol} — {fundHistory.length} snapshot{fundHistory.length !== 1 ? "s" : ""}
              </p>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart
                  data={fundHistory.map(h => ({
                    date: h.snapshotDate,
                    label: h.snapshotLabel || h.snapshotDate,
                    score: h.score,
                  }))}
                  margin={{ top: 5, right: 20, left: -10, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="label" tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "hsl(var(--popover))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "6px",
                      fontSize: 12,
                    }}
                    labelStyle={{ color: "hsl(var(--foreground))" }}
                    itemStyle={{ color: "hsl(var(--foreground))" }}
                  />
                  <Line type="monotone" dataKey="score" name="Score" stroke="hsl(var(--primary))" strokeWidth={2} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </>
          )}

          {searchedSymbol && fundHistory && fundHistory.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-4">
              No historical data found for {searchedSymbol}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
