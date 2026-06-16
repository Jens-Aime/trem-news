"use client";

import type { ConnectionStatus } from "@/types/market";

interface ConnectionStatusProps {
  status: ConnectionStatus;
}

const STATUS_CONFIG: Record<
  ConnectionStatus,
  { dot: string; label: string; text: string }
> = {
  connected: {
    dot: "bg-emerald-400 shadow-[0_0_6px_2px_rgba(52,211,153,0.5)] animate-pulse",
    label: "Connected (Live Sync)",
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
    label: "Sync Error — retrying",
    text: "text-red-400",
  },
};

export function ConnectionStatusBadge({ status }: ConnectionStatusProps) {
  const cfg = STATUS_CONFIG[status];

  return (
    <div className="flex items-center gap-2 text-sm">
      <span
        className={`inline-block h-2 w-2 rounded-full ${cfg.dot}`}
        aria-label={cfg.label}
      />
      <span className={`font-medium ${cfg.text}`}>{cfg.label}</span>
    </div>
  );
}
