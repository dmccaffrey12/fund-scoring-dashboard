import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Search, Printer, ArrowRight, TrendingUp, TrendingDown, Minus } from "lucide-react";
import { Link } from "wouter";

interface ReplacementCandidate {
  rank: number;
  symbol: string;
  name: string;
  category: string;
  fundType: "Passive" | "Active";
  score2023: number | null;
  score2025: number | null;
  scoreGap: number | null;
  consensusRank: number | null;
  rank2023: number | null;
  rank2025: number | null;
  scoreBand2023: string | null;
  scoreBand2025: string | null;
  quadrant: string | null;
  actionFlag: string | null;
  primaryDriver: string | null;
  netExpenseRatio: number | null;
  score2025Delta: number | null;
  score2023Delta: number | null;
  expenseDelta: number | null;
}

interface WorkbenchData {
  currentHolding: {
    symbol: string;
    name: string;
    category: string;
    fundType: "Passive" | "Active";
    score2023: number | null;
    score2025: number | null;
    scoreGap: number | null;
    consensusRank: number | null;
    rank2023: number | null;
    rank2025: number | null;
    scoreBand2023: string | null;
    scoreBand2025: string | null;
    quadrant: string | null;
    actionFlag: string | null;
    primaryDriver: string | null;
    netExpenseRatio: number | null;
  };
  categoryPeerCount: number;
  candidates: ReplacementCandidate[];
}

interface ReplacementWorkbenchViewProps {
  initialSymbol?: string;
  onSelectFundForRadar?: (symbol: string) => void;
}

export function ReplacementWorkbenchView({
  initialSymbol = "PRBLX",
  onSelectFundForRadar,
}: ReplacementWorkbenchViewProps) {
  const [tickerInput, setTickerInput] = useState(initialSymbol);
  const [activeTicker, setActiveTicker] = useState(initialSymbol);

  const { data, isLoading, error } = useQuery<WorkbenchData>({
    queryKey: ["/api/replacement-workbench", activeTicker],
    queryFn: async () => {
      if (!activeTicker) throw new Error("Ticker required");
      const res = await fetch(`/api/replacement-workbench?symbol=${activeTicker}&topN=15`);
      if (!res.ok) throw new Error("Fund not found or no replacement candidates available");
      return res.json();
    },
    enabled: !!activeTicker,
  });

  const handleSearch = () => {
    if (tickerInput.trim()) {
      setActiveTicker(tickerInput.trim().toUpperCase());
    }
  };

  const current = data?.currentHolding;
  const candidates = data?.candidates || [];

  const renderBadge = (flag: string | null) => {
    if (!flag) return "—";
    if (flag === "LEAD" || flag === "Q1_Both_Strong") {
      return (
        <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/20 text-[10px]">
          {flag}
        </Badge>
      );
    }
    if (flag === "REVIEW" || flag === "Q2_Only_2025" || flag === "Q3_Only_2023") {
      return (
        <Badge className="bg-amber-500/15 text-amber-400 border-amber-500/20 text-[10px]">
          {flag}
        </Badge>
      );
    }
    return (
      <Badge className="bg-rose-500/15 text-rose-400 border-rose-500/20 text-[10px]">
        {flag}
      </Badge>
    );
  };

  const renderScoreDelta = (delta: number | null) => {
    if (delta === null) return "—";
    if (delta > 0) {
      return (
        <span className="inline-flex items-center text-emerald-400 font-mono font-bold text-xs gap-0.5">
          <TrendingUp className="w-3 h-3" /> +{delta.toFixed(1)}
        </span>
      );
    }
    if (delta < 0) {
      return (
        <span className="inline-flex items-center text-rose-400 font-mono font-bold text-xs gap-0.5">
          <TrendingDown className="w-3 h-3" /> {delta.toFixed(1)}
        </span>
      );
    }
    return (
      <span className="inline-flex items-center text-muted-foreground font-mono text-xs gap-0.5">
        <Minus className="w-3 h-3" /> 0.0
      </span>
    );
  };

  const renderExpenseDelta = (delta: number | null) => {
    if (delta === null) return "—";
    const pct = (delta * 100).toFixed(2);
    if (delta < 0) {
      return (
        <span className="text-emerald-400 font-mono font-medium text-xs">
          {pct}%
        </span>
      );
    }
    if (delta > 0) {
      return (
        <span className="text-rose-400 font-mono font-medium text-xs">
          +{pct}%
        </span>
      );
    }
    return <span className="text-muted-foreground font-mono text-xs">0.00%</span>;
  };

  return (
    <div className="space-y-4">
      {/* Search Header */}
      <Card className="bg-card border-card-border">
        <CardContent className="p-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 flex-1 max-w-md">
              <div className="relative flex-1">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                <Input
                  placeholder="Target holding ticker to replace (e.g. PRBLX, FMAGX, SPY)..."
                  value={tickerInput}
                  onChange={e => setTickerInput(e.target.value.toUpperCase())}
                  onKeyDown={e => e.key === "Enter" && handleSearch()}
                  className="pl-8 h-9 text-xs font-mono bg-background"
                />
              </div>
              <Button size="sm" onClick={handleSearch} className="gap-1.5 h-9 text-xs">
                <ArrowRight className="w-3.5 h-3.5" /> Analyze Replacement
              </Button>
            </div>

            {current && (
              <div className="flex items-center gap-2">
                <a
                  href={`/api/replacement-workbench/brief/${current.symbol}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  <Button variant="outline" size="sm" className="gap-1.5 h-9 text-xs">
                    <Printer className="w-3.5 h-3.5" /> Printable Committee Brief
                  </Button>
                </a>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {isLoading && (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      )}

      {error && (
        <Card className="border-rose-500/30 bg-rose-500/5">
          <CardContent className="p-4 text-center text-xs text-rose-400">
            Fund not found or no same-category replacement candidates found. Check the ticker.
          </CardContent>
        </Card>
      )}

      {current && (
        <>
          {/* Current Holding Banner */}
          <Card className="bg-card border-card-border overflow-hidden">
            <CardHeader className="p-4 pb-2 bg-muted/20 border-b border-border/40">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs uppercase tracking-wider font-semibold text-muted-foreground">
                      Current Portfolio Holding Under Review
                    </span>
                    <Badge variant="outline" className="text-[10px]">
                      {current.fundType}
                    </Badge>
                  </div>
                  <h3 className="text-base font-bold text-foreground mt-0.5">
                    <span className="font-mono text-primary mr-2">{current.symbol}</span>
                    <span>{current.name}</span>
                  </h3>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">Category:</span>
                  <Badge variant="secondary" className="text-xs font-medium">
                    {current.category} ({data?.categoryPeerCount} peers)
                  </Badge>
                </div>
              </div>
            </CardHeader>
            <CardContent className="p-4">
              <div className="grid grid-cols-2 sm:grid-cols-4 md:grid-cols-7 gap-3 text-center">
                <div className="p-2 bg-muted/30 rounded border border-border/20">
                  <div className="text-[10px] uppercase text-muted-foreground font-semibold">2025 Score</div>
                  <div className="text-base font-bold font-mono mt-0.5">
                    {current.score2025?.toFixed(1) ?? "—"}
                  </div>
                </div>
                <div className="p-2 bg-muted/30 rounded border border-border/20">
                  <div className="text-[10px] uppercase text-muted-foreground font-semibold">2023 Score</div>
                  <div className="text-base font-bold font-mono mt-0.5">
                    {current.score2023?.toFixed(1) ?? "—"}
                  </div>
                </div>
                <div className="p-2 bg-muted/30 rounded border border-border/20">
                  <div className="text-[10px] uppercase text-muted-foreground font-semibold">Expense Ratio</div>
                  <div className="text-base font-mono mt-0.5">
                    {current.netExpenseRatio !== null ? `${(current.netExpenseRatio * 100).toFixed(2)}%` : "—"}
                  </div>
                </div>
                <div className="p-2 bg-muted/30 rounded border border-border/20">
                  <div className="text-[10px] uppercase text-muted-foreground font-semibold">Consensus Rank</div>
                  <div className="text-base font-mono font-bold mt-0.5">
                    #{current.consensusRank ?? "—"}
                  </div>
                </div>
                <div className="p-2 bg-muted/30 rounded border border-border/20">
                  <div className="text-[10px] uppercase text-muted-foreground font-semibold">Quadrant</div>
                  <div className="mt-1">{renderBadge(current.quadrant)}</div>
                </div>
                <div className="p-2 bg-muted/30 rounded border border-border/20">
                  <div className="text-[10px] uppercase text-muted-foreground font-semibold">Action Flag</div>
                  <div className="mt-1">{renderBadge(current.actionFlag)}</div>
                </div>
                <div className="p-2 bg-muted/30 rounded border border-border/20">
                  <div className="text-[10px] uppercase text-muted-foreground font-semibold">Primary Driver</div>
                  <div className="text-xs font-medium text-muted-foreground mt-1 truncate">
                    {current.primaryDriver ?? "Stable"}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Replacement Candidates Leaderboard */}
          <Card className="bg-card border-card-border">
            <CardHeader className="p-4 pb-2">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-sm font-bold">
                    Top Actionable Replacement Candidates ({candidates.length})
                  </CardTitle>
                  <p className="text-xs text-muted-foreground">
                    Ranked by dual-lens consensus rank within {current.category}. Deltas computed against {current.symbol}.
                  </p>
                </div>
              </div>
            </CardHeader>
            <CardContent className="p-0 overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="bg-muted/30 border-b border-border/40 text-[10px] uppercase font-semibold text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 text-center w-10">#</th>
                    <th className="px-3 py-2 text-left">Candidate Symbol</th>
                    <th className="px-3 py-2 text-left">Fund Name</th>
                    <th className="px-3 py-2 text-center">Type</th>
                    <th className="px-3 py-2 text-right">2025 Score</th>
                    <th className="px-3 py-2 text-right">2025 &Delta;</th>
                    <th className="px-3 py-2 text-right">2023 Score</th>
                    <th className="px-3 py-2 text-right">Expense</th>
                    <th className="px-3 py-2 text-right">Expense &Delta;</th>
                    <th className="px-3 py-2 text-center">Cons. Rank</th>
                    <th className="px-3 py-2 text-center">Quadrant</th>
                    <th className="px-3 py-2 text-center">Action</th>
                    <th className="px-3 py-2 text-center">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/20">
                  {candidates.map(cand => (
                    <tr key={cand.symbol} className="hover:bg-muted/20 transition-colors">
                      <td className="px-3 py-2 text-center font-mono font-medium text-muted-foreground">
                        {cand.rank}
                      </td>
                      <td className="px-3 py-2">
                        <Link
                          href={`/lookup/${cand.symbol}`}
                          className="font-mono font-bold text-primary hover:underline"
                        >
                          {cand.symbol}
                        </Link>
                      </td>
                      <td className="px-3 py-2 max-w-[220px] truncate text-foreground font-medium">
                        {cand.name}
                      </td>
                      <td className="px-3 py-2 text-center">
                        <span
                          className={`text-[9px] font-mono px-1 py-0.5 rounded ${
                            cand.fundType === "Passive"
                              ? "bg-blue-500/10 text-blue-400"
                              : "bg-purple-500/10 text-purple-400"
                          }`}
                        >
                          {cand.fundType === "Passive" ? "IDX" : "ACT"}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right font-mono font-bold tabular-nums">
                        <span
                          className={
                            cand.score2025 && cand.score2025 >= 80
                              ? "text-emerald-400"
                              : cand.score2025 && cand.score2025 >= 60
                              ? "text-amber-400"
                              : "text-rose-400"
                          }
                        >
                          {cand.score2025?.toFixed(1) ?? "—"}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {renderScoreDelta(cand.score2025Delta)}
                      </td>
                      <td className="px-3 py-2 text-right font-mono tabular-nums text-muted-foreground">
                        {cand.score2023?.toFixed(1) ?? "—"}
                      </td>
                      <td className="px-3 py-2 text-right font-mono tabular-nums">
                        {cand.netExpenseRatio !== null ? `${(cand.netExpenseRatio * 100).toFixed(2)}%` : "—"}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {renderExpenseDelta(cand.expenseDelta)}
                      </td>
                      <td className="px-3 py-2 text-center font-mono font-semibold">
                        #{cand.consensusRank ?? "—"}
                      </td>
                      <td className="px-3 py-2 text-center">{renderBadge(cand.quadrant)}</td>
                      <td className="px-3 py-2 text-center">{renderBadge(cand.actionFlag)}</td>
                      <td className="px-3 py-2 text-center">
                        {onSelectFundForRadar && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => onSelectFundForRadar(cand.symbol)}
                            className="h-6 text-[10px] px-2 text-muted-foreground hover:text-foreground"
                          >
                            View Radar
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
