"use client";

import { Activity } from "lucide-react";
import { ConnectionStatusBadge } from "@/components/ConnectionStatus";
import { LiveFeed } from "@/components/LiveFeed";
import { StatsBar } from "@/components/StatsBar";
import { useMarketPulse } from "@/hooks/useMarketPulse";

export function Dashboard() {
  const { events, status, clientId, reconnectAttempt, clearEvents } =
    useMarketPulse();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* ── Top bar ─────────────────────────────────────────────── */}
      <header className="sticky top-0 z-10 border-b border-slate-800 bg-slate-950/90 backdrop-blur-sm">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-4 py-3">
          {/* Brand */}
          <div className="flex items-center gap-2">
            <Activity className="h-5 w-5 text-indigo-400" />
            <span className="font-semibold tracking-tight text-white">
              Market Pulse{" "}
              <span className="font-light text-slate-400">Intelligence</span>
            </span>
          </div>

          {/* Connection badge */}
          <ConnectionStatusBadge
            status={status}
            clientId={clientId}
            reconnectAttempt={reconnectAttempt}
          />
        </div>
      </header>

      {/* ── Main content ────────────────────────────────────────── */}
      <main className="mx-auto max-w-4xl space-y-4 px-4 py-6">
        {/* Stats bar */}
        <StatsBar events={events} />

        {/* Live feed */}
        <LiveFeed events={events} onClear={clearEvents} />
      </main>

      {/* ── Footer ──────────────────────────────────────────────── */}
      <footer className="mx-auto max-w-4xl border-t border-slate-800/50 px-4 py-4 text-center text-xs text-slate-700">
        Market Pulse Intelligence — real-time AI-powered economic event analysis
      </footer>
    </div>
  );
}
