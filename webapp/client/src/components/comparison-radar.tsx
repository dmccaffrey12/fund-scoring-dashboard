import React from "react";
import {
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export interface MetricBreakdownItem {
  metric: string;
  label: string;
  weight: number;
  value: number | null;
  percentile: number | null;
  categoryMedianPercentile: number;
  higherBetter: boolean;
}

interface ComparisonRadarProps {
  symbol: string;
  name: string;
  category: string;
  fundType: "Passive" | "Active";
  score: number | null;
  quadrant?: string | null;
  actionFlag?: string | null;
  breakdown: MetricBreakdownItem[];
}

export function ComparisonRadar({
  symbol,
  name,
  category,
  fundType,
  score,
  quadrant,
  actionFlag,
  breakdown,
}: ComparisonRadarProps) {
  // Format data for Recharts Radar
  const chartData = breakdown.map(item => ({
    metric: item.label,
    fundPercentile: item.percentile ?? 0,
    categoryMedian: 50,
    fullMark: 100,
    rawVal: item.value,
    weight: item.weight,
    higherBetter: item.higherBetter,
  }));

  const formatRawValue = (val: number | null, metric: string) => {
    if (val === null || val === undefined) return "—";
    const lower = metric.toLowerCase();
    if (lower.includes("expense") || lower.includes("return")) {
      return `${(val * 100).toFixed(2)}%`;
    }
    if (lower.includes("aum")) {
      if (val >= 1e9) return `$${(val / 1e9).toFixed(2)}B`;
      if (val >= 1e6) return `$${(val / 1e6).toFixed(1)}M`;
      return `$${val.toLocaleString()}`;
    }
    return val.toFixed(3);
  };

  return (
    <div className="space-y-4">
      {/* Overview header */}
      <div className="flex flex-wrap items-center justify-between gap-2 p-3 bg-muted/20 border border-border/40 rounded-lg">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-base font-bold font-mono text-primary">{symbol}</span>
            <span className="text-sm font-medium">{name}</span>
            <Badge variant="outline" className="text-[10px]">
              {fundType}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            Category: <strong className="text-foreground">{category}</strong> · 2025 Score:{" "}
            <strong className={score && score >= 80 ? "text-emerald-500" : score && score >= 60 ? "text-amber-500" : "text-rose-500"}>
              {score ? score.toFixed(1) : "—"}
            </strong>
          </p>
        </div>
        <div className="flex items-center gap-2">
          {quadrant && (
            <Badge variant="secondary" className="text-xs font-mono">
              {quadrant}
            </Badge>
          )}
          {actionFlag && (
            <Badge
              className={`text-xs font-semibold ${
                actionFlag === "LEAD"
                  ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30"
                  : actionFlag === "REVIEW"
                  ? "bg-amber-500/20 text-amber-400 border-amber-500/30"
                  : "bg-rose-500/20 text-rose-400 border-rose-500/30"
              }`}
            >
              {actionFlag}
            </Badge>
          )}
        </div>
      </div>

      {/* Main Grid: Radar Chart + Breakdown Table */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Radar Chart Column */}
        <Card className="lg:col-span-6 bg-card border-card-border flex flex-col">
          <CardHeader className="p-4 pb-0">
            <CardTitle className="text-sm font-semibold flex items-center justify-between">
              <span>Factor Comparison "Web"</span>
              <span className="text-xs font-normal text-muted-foreground">0 – 100 Percentile</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="p-2 flex-1 flex flex-col justify-center">
            {chartData.length > 0 ? (
              <div className="h-[340px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart cx="50%" cy="50%" outerRadius="75%" data={chartData}>
                    <PolarGrid stroke="hsl(var(--border))" strokeDasharray="3 3" />
                    <PolarAngleAxis
                      dataKey="metric"
                      tick={{ fill: "hsl(var(--foreground))", fontSize: 10, fontWeight: 500 }}
                    />
                    <PolarRadiusAxis
                      angle={90}
                      domain={[0, 100]}
                      tick={{ fill: "hsl(var(--muted-foreground))", fontSize: 9 }}
                      stroke="hsl(var(--border))"
                    />
                    {/* Category Median 50th percentile baseline ring */}
                    <Radar
                      name="Category Median (50%ile)"
                      dataKey="categoryMedian"
                      stroke="#94a3b8"
                      strokeWidth={1.5}
                      strokeDasharray="4 4"
                      fill="#94a3b8"
                      fillOpacity={0.05}
                    />
                    {/* Fund percentiles */}
                    <Radar
                      name={`${symbol} Percentile`}
                      dataKey="fundPercentile"
                      stroke="#0284c7"
                      strokeWidth={2.5}
                      fill="#0284c7"
                      fillOpacity={0.25}
                    />
                    <Tooltip
                      content={({ active, payload }) => {
                        if (active && payload && payload.length) {
                          const data = payload[0].payload;
                          return (
                            <div className="bg-popover border border-border rounded p-2 text-xs shadow-md">
                              <p className="font-semibold text-foreground">{data.metric}</p>
                              <p className="text-sky-400 font-mono">
                                Fund Percentile: <strong>{data.fundPercentile.toFixed(1)}%</strong>
                              </p>
                              <p className="text-muted-foreground font-mono">
                                Category Median: 50.0%
                              </p>
                              {data.rawVal !== null && (
                                <p className="text-xs text-muted-foreground mt-1">
                                  Raw Value: {formatRawValue(data.rawVal, data.metric)}
                                </p>
                              )}
                              <p className="text-[10px] text-muted-foreground">
                                Weight: {data.weight} pts · {data.higherBetter ? "Higher" : "Lower"} is better
                              </p>
                            </div>
                          );
                        }
                        return null;
                      }}
                    />
                    <Legend
                      verticalAlign="bottom"
                      height={30}
                      wrapperStyle={{ fontSize: "11px", paddingTop: "10px" }}
                    />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <div className="h-[340px] flex items-center justify-center text-sm text-muted-foreground">
                No factor data available for radar visualization.
              </div>
            )}
          </CardContent>
        </Card>

        {/* Breakdown Table Column */}
        <Card className="lg:col-span-6 bg-card border-card-border flex flex-col">
          <CardHeader className="p-4 pb-2">
            <CardTitle className="text-sm font-semibold">
              Category Peer Factor Breakdown ({chartData.length} Metrics)
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0 flex-1 overflow-x-auto">
            <table className="w-full text-xs">
              <thead className="bg-muted/40 text-[10px] uppercase font-semibold text-muted-foreground border-b border-border/50">
                <tr>
                  <th className="px-3 py-2 text-left">Metric</th>
                  <th className="px-3 py-2 text-right">Raw Value</th>
                  <th className="px-3 py-2 text-center">Direction</th>
                  <th className="px-3 py-2 text-right">Weight</th>
                  <th className="px-3 py-2 text-left w-36">Percentile</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/20">
                {breakdown.map((item, idx) => {
                  const pct = item.percentile ?? 0;
                  const barColor =
                    pct >= 80 ? "bg-emerald-500" : pct >= 50 ? "bg-sky-500" : pct >= 30 ? "bg-amber-500" : "bg-rose-500";
                  return (
                    <tr key={idx} className="hover:bg-muted/20 transition-colors">
                      <td className="px-3 py-2 font-medium">{item.label}</td>
                      <td className="px-3 py-2 text-right font-mono tabular-nums text-muted-foreground">
                        {formatRawValue(item.value, item.label)}
                      </td>
                      <td className="px-3 py-2 text-center text-[10px] text-muted-foreground">
                        {item.higherBetter ? "▲ Higher" : "▼ Lower"}
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-muted-foreground">
                        {item.weight} pts
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-2">
                          <div className="flex-1 bg-muted/60 rounded-full h-2 overflow-hidden relative">
                            {/* Median reference line at 50% */}
                            <div className="absolute top-0 bottom-0 left-1/2 w-0.5 bg-border z-10" />
                            <div
                              className={`h-full rounded-full ${barColor}`}
                              style={{ width: `${Math.min(Math.max(pct, 0), 100)}%` }}
                            />
                          </div>
                          <span className="font-mono tabular-nums font-semibold text-[11px] w-9 text-right">
                            {item.percentile !== null ? `${item.percentile}%` : "—"}
                          </span>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
