"use client";

import type { ConnectionStatus } from "@/types/market";

interface ConnectionStatusProps {
  status: ConnectionStatus;
  clientId: string | null;
  reconnectAttempt: number;
  mode?: "ws" | "polling";
}

const STATUS_CONFIG: Record<
  ConnectionStatus,
  { dot: string; label: string; text: string }
> = {
  connected: {
    dot: "bg-emerald-400 shadow-[0_0_6px_2px_rgba(52,211,153,0.5)] animate-pulse",
    label: "Connected",
    text: "text-emerald-400",
  },
  connecting: {
    dot: "bg-yellow-400 animate-pulse",
    label: "Connecting…",
    text: "text-yellow-400",
  },
  disconnected: {
    dot: "bg-slate-500",
    label: "Disconnected",
    text: "text-slate-400",
  },
  error: {
    dot: "bg-red-500 animate-pulse",
    label: "Error",
    text: "text-red-400",
  },
};

export function ConnectionStatusBadge({
  status,
  clientId,
  reconnectAttempt,
  mode,
}: ConnectionStatusProps) {
  const cfg = STATUS_CONFIG[status];

  return (
    <div className="flex items-center gap-3 text-sm">
      <span className="flex items-center gap-1.5">
        <span
          className={`inline-block h-2 w-2 rounded-full ${cfg.dot}`}
          aria-label={cfg.label}
        />
        <span className={`font-medium ${cfg.text}`}>{cfg.label}</span>
      </span>

      {status === "connected" && clientId && (
        <span className="rounded border border-slate-700 bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-400">
          id:{clientId}
        </span>
      )}

      {(status === "disconnected" || status === "error") &&
        reconnectAttempt > 0 && (
          <span className="text-xs text-slate-500">
            reconnect #{reconnectAttempt}
          </span>
        )}

      {mode === "polling" && (
        <span className="rounded border border-amber-800/50 bg-amber-950/40 px-2 py-0.5 text-xs text-amber-500">
          polling
        </span>
      )}
    </div>
  );
}
