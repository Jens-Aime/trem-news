"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Cell,
} from "recharts";
import type { HistoryEntry } from "@/types/market";
import { formatSurprisePct } from "@/lib/utils";

interface SurpriseChartProps {
  items: HistoryEntry[];
}

interface ChartDatum {
  name: string;
  surprise: number | null;
  beat: boolean;
}

interface TooltipPayload {
  payload: ChartDatum;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayload[];
}

function CustomTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="rounded border border-slate-700 bg-slate-900 px-3 py-2 text-xs shadow-lg">
      <p className="font-medium text-slate-200">{d.name}</p>
      <p className={d.beat ? "text-emerald-400" : "text-rose-400"}>
        Surprise: {formatSurprisePct(d.surprise) ?? "n/a"}
      </p>
    </div>
  );
}

export function SurpriseChart({ items }: SurpriseChartProps) {
  const data: ChartDatum[] = items
    .filter((e) => e.surprise_pct != null)
    .slice(0, 20)
    .reverse()
    .map((e) => ({
      name: e.event_name.length > 18 ? e.event_name.slice(0, 16) + "…" : e.event_name,
      surprise: e.surprise_pct,
      beat: (e.surprise_pct ?? 0) >= 0,
    }));

  if (data.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-sm text-slate-600">
        No surprise data yet
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={180}>
      <BarChart data={data} margin={{ top: 4, right: 8, left: -24, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
        <XAxis
          dataKey="name"
          tick={{ fill: "#64748b", fontSize: 10 }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tick={{ fill: "#64748b", fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: number) => `${v > 0 ? "+" : ""}${v.toFixed(0)}%`}
        />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
        <ReferenceLine y={0} stroke="#334155" />
        <Bar dataKey="surprise" radius={[3, 3, 0, 0]}>
          {data.map((entry, idx) => (
            <Cell
              key={idx}
              fill={entry.beat ? "#10b981" : "#f43f5e"}
              fillOpacity={0.8}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
