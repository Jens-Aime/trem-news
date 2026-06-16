"use client";

import type { AnalysisResult } from "@/types/market";

interface StatsBarProps {
  events: AnalysisResult[];
}

export function StatsBar({ events }: StatsBarProps) {
  const total = events.length;
  const critical = events.filter((e) => e.risk_level === "critical").length;
  const high = events.filter((e) => e.risk_level === "high").length;
  const bullish = events.filter((e) => e.sentiment === "bullish").length;
  const bearish = events.filter((e) => e.sentiment === "bearish").length;
  const cached = events.filter((e) => e.cached).length;

  if (total === 0) return null;

  return (
    <div className="flex flex-wrap gap-x-6 gap-y-1 rounded-md border border-slate-800 bg-slate-900/60 px-4 py-2 text-xs">
      <Stat label="Events" value={total} />
      {critical > 0 && (
        <Stat label="Critical" value={critical} className="text-red-400" />
      )}
      {high > 0 && (
        <Stat label="High" value={high} className="text-orange-400" />
      )}
      <Stat label="Bullish" value={bullish} className="text-emerald-400" />
      <Stat label="Bearish" value={bearish} className="text-rose-400" />
      {cached > 0 && (
        <Stat label="Cached" value={cached} className="text-slate-500" />
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  className = "text-slate-300",
}: {
  label: string;
  value: number;
  className?: string;
}) {
  return (
    <span className="flex items-baseline gap-1">
      <span className={`font-mono font-semibold tabular-nums ${className}`}>
        {value}
      </span>
      <span className="text-slate-500">{label}</span>
    </span>
  );
}
