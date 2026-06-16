"use client";

import { Activity } from "lucide-react";
import { ConnectionStatusBadge } from "@/components/ConnectionStatus";
import { LiveFeed } from "@/components/LiveFeed";
import { StatsBar } from "@/components/StatsBar";
import { HistoricalView } from "@/components/HistoricalView";
import { useMarketPulse } from "@/hooks/useMarketPulse";

export function Dashboard() {
  const { events, status, clearEvents } = useMarketPulse();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* ── Top bar ─────────────────────────────────────────────── */}
      <header className="sticky top-0 z-10 border-b border-slate-800 bg-slate-950/90 backdrop-blur-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2">
            <Activity className="h-5 w-5 text-indigo-400" />
            <span className="font-semibold tracking-tight text-white">
              Market Pulse{" "}
              <span className="font-light text-slate-400">Intelligence</span>
            </span>
          </div>

          <ConnectionStatusBadge status={status} />
        </div>
      </header>

      {/* ── Main content ────────────────────────────────────────── */}
      <main className="mx-auto max-w-7xl px-4 py-6">
        <StatsBar events={events} />

        <div className="mt-4 grid grid-cols-1 gap-6 xl:grid-cols-2">
          <LiveFeed events={events} onClear={clearEvents} />
          <HistoricalView />
        </div>
      </main>

      {/* ── Footer ──────────────────────────────────────────────── */}
      <footer className="mx-auto max-w-7xl border-t border-slate-800/50 px-4 py-4 text-center text-xs text-slate-700">
        Market Pulse Intelligence — real-time AI-powered economic event analysis
      </footer>
    </div>
  );
}
