import { useQuery, useMutation } from "@tanstack/react-query";
import { apiRequest, queryClient } from "@/lib/queryClient";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";
import { useState } from "react";
import { Plus, Trash2, RefreshCw, Shield, AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { Link } from "wouter";

interface EnrichedHolding {
  id: number;
  symbol: string;
  baselineScore: number | null;
  baselineExpenseRatio: number | null;
  addedAt: string;
  currentScore: number | null;
  currentExpenseRatio: number | null;
  fundName: string;
  categoryName: string | null;
  scoreBand: string | null;
  categoryPercentile: number | null;
}

function getStatus(h: EnrichedHolding): { label: string; color: string; icon: any; reason: string } {
  if (!h.currentScore) {
    return { label: "UNKNOWN", color: "text-muted-foreground", icon: AlertTriangle, reason: "No score data" };
  }

  // RED: score < 60 or expense increased
  if (h.currentScore < 60) {
    return { label: "RED", color: "text-red-400", icon: XCircle, reason: "Score below 60" };
  }
  if (h.baselineExpenseRatio !== null && h.currentExpenseRatio !== null && h.currentExpenseRatio > h.baselineExpenseRatio) {
    return { label: "RED", color: "text-red-400", icon: XCircle, reason: "Expense ratio increased" };
  }

  // YELLOW: score dropped >10 or category percentile < 75
  if (h.baselineScore !== null && h.currentScore < h.baselineScore - 10) {
    return { label: "YELLOW", color: "text-amber-400", icon: AlertTriangle, reason: `Score dropped ${(h.baselineScore - h.currentScore).toFixed(1)} pts` };
  }
  if (h.categoryPercentile !== null && h.categoryPercentile < 75) {
    return { label: "YELLOW", color: "text-amber-400", icon: AlertTriangle, reason: `Category percentile: ${h.categoryPercentile.toFixed(0)}%` };
  }

  // GREEN
  return { label: "GREEN", color: "text-emerald-400", icon: CheckCircle2, reason: "All clear" };
}

export default function Monitoring() {
  const [ticker, setTicker] = useState("");
  const { toast } = useToast();

  const { data: holdings, isLoading } = useQuery<EnrichedHolding[]>({
    queryKey: ["/api/monitoring"],
  });

  const addMutation = useMutation({
    mutationFn: async (symbol: string) => {
      const res = await apiRequest("POST", "/api/monitoring", { symbol });
      return res.json();
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/monitoring"] });
      setTicker("");
      toast({ title: "Holding added", description: `Added ${ticker} to monitoring` });
    },
    onError: (err: Error) => {
      toast({ title: "Error", description: err.message, variant: "destructive" });
    },
  });

  const removeMutation = useMutation({
    mutationFn: async (id: number) => {
      await apiRequest("DELETE", `/api/monitoring/${id}`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/monitoring"] });
    },
  });

  const baselineMutation = useMutation({
    mutationFn: async (id: number) => {
      await apiRequest("POST", `/api/monitoring/${id}/baseline`);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["/api/monitoring"] });
      toast({ title: "Baseline updated" });
    },
  });

  const handleAdd = () => {
    if (ticker.trim()) {
      addMutation.mutate(ticker.trim().toUpperCase());
    }
  };

  const statusCounts = { GREEN: 0, YELLOW: 0, RED: 0 };
  holdings?.forEach(h => {
    const s = getStatus(h);
    if (s.label in statusCounts) statusCounts[s.label as keyof typeof statusCounts]++;
  });

  return (
    <div className="p-4 lg:p-6 space-y-4 max-w-[1600px]">
      <div>
        <h2 className="text-lg font-bold flex items-center gap-2">
          <Shield className="w-5 h-5 text-primary" />
          Model Portfolio Monitoring
        </h2>
        <p className="text-xs text-muted-foreground">Track holdings against baseline scores</p>
      </div>

      {/* Add ticker */}
      <Card className="bg-card border-card-border">
        <CardContent className="p-3">
          <div className="flex gap-2">
            <Input
              placeholder="Add ticker to monitor (e.g., VFIAX)"
              value={ticker}
              onChange={e => setTicker(e.target.value.toUpperCase())}
              onKeyDown={e => e.key === "Enter" && handleAdd()}
              className="max-w-md h-9 text-sm font-mono bg-background"
              data-testid="input-monitoring-ticker"
            />
            <Button onClick={handleAdd} size="sm" className="gap-1.5" disabled={addMutation.isPending} data-testid="button-add-holding">
              <Plus className="w-3.5 h-3.5" />
              Add
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Status Summary */}
      {holdings && holdings.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          <Card className="bg-card border-card-border">
            <CardContent className="p-3 flex items-center gap-3">
              <CheckCircle2 className="w-5 h-5 text-emerald-400" />
              <div>
                <p className="text-xl font-bold font-mono text-emerald-400">{statusCounts.GREEN}</p>
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Green</p>
              </div>
            </CardContent>
          </Card>
          <Card className="bg-card border-card-border">
            <CardContent className="p-3 flex items-center gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-400" />
              <div>
                <p className="text-xl font-bold font-mono text-amber-400">{statusCounts.YELLOW}</p>
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Yellow</p>
              </div>
            </CardContent>
          </Card>
          <Card className="bg-card border-card-border">
            <CardContent className="p-3 flex items-center gap-3">
              <XCircle className="w-5 h-5 text-red-400" />
              <div>
                <p className="text-xl font-bold font-mono text-red-400">{statusCounts.RED}</p>
                <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Red</p>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Holdings Table */}
      <Card className="bg-card border-card-border">
        <CardContent className="p-0">
          {holdings && holdings.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-muted/30">
                  <tr>
                    <th className="px-3 py-2 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Status</th>
                    <th className="px-3 py-2 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Symbol</th>
                    <th className="px-3 py-2 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Name</th>
                    <th className="px-3 py-2 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Category</th>
                    <th className="px-3 py-2 text-right text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Baseline</th>
                    <th className="px-3 py-2 text-right text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Current</th>
                    <th className="px-3 py-2 text-right text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Change</th>
                    <th className="px-3 py-2 text-left text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Reason</th>
                    <th className="px-3 py-2 text-right text-[10px] uppercase tracking-wider font-semibold text-muted-foreground">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {holdings.map(h => {
                    const status = getStatus(h);
                    const StatusIcon = status.icon;
                    const change = h.baselineScore !== null && h.currentScore !== null
                      ? h.currentScore - h.baselineScore
                      : null;

                    return (
                      <tr key={h.id} className="border-t border-border/30 hover:bg-accent/30 transition-colors" data-testid={`monitoring-row-${h.symbol}`}>
                        <td className="px-3 py-2">
                          <span className={`flex items-center gap-1.5 text-xs font-medium ${status.color}`}>
                            <StatusIcon className="w-4 h-4" />
                            {status.label}
                          </span>
                        </td>
                        <td className="px-3 py-2">
                          <Link href={`/lookup/${h.symbol}`} className="text-sm font-mono font-medium text-primary hover:underline">
                            {h.symbol}
                          </Link>
                        </td>
                        <td className="px-3 py-2 text-sm truncate max-w-[200px]">{h.fundName}</td>
                        <td className="px-3 py-2 text-xs text-muted-foreground truncate max-w-[150px]">{h.categoryName}</td>
                        <td className="px-3 py-2 text-sm font-mono tabular-nums text-right text-muted-foreground">
                          {h.baselineScore?.toFixed(1) || "—"}
                        </td>
                        <td className="px-3 py-2 text-sm font-mono font-bold tabular-nums text-right">
                          <span className={h.currentScore && h.currentScore >= 80 ? "text-emerald-400" : h.currentScore && h.currentScore >= 60 ? "text-amber-400" : "text-red-400"}>
                            {h.currentScore?.toFixed(1) || "—"}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-sm font-mono tabular-nums text-right">
                          {change !== null ? (
                            <span className={change >= 0 ? "text-emerald-400" : "text-red-400"}>
                              {change >= 0 ? "+" : ""}{change.toFixed(1)}
                            </span>
                          ) : "—"}
                        </td>
                        <td className="px-3 py-2 text-xs text-muted-foreground">{status.reason}</td>
                        <td className="px-3 py-2 text-right">
                          <div className="flex items-center gap-1 justify-end">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => baselineMutation.mutate(h.id)}
                              className="h-7 px-2 text-xs"
                              title="Reset baseline"
                              data-testid={`button-baseline-${h.symbol}`}
                            >
                              <RefreshCw className="w-3 h-3" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => removeMutation.mutate(h.id)}
                              className="h-7 px-2 text-xs text-destructive hover:text-destructive"
                              title="Remove"
                              data-testid={`button-remove-${h.symbol}`}
                            >
                              <Trash2 className="w-3 h-3" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-8 text-center text-sm text-muted-foreground">
              {isLoading ? "Loading..." : "No holdings monitored yet. Add a ticker above."}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
