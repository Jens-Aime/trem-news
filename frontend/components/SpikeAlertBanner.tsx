"use client";

import { useEffect, useRef, useState } from "react";
import { X, TrendingUp, TrendingDown, Zap } from "lucide-react";
import type { VolatilityAlert } from "@/types/market";
import { useVolatilityAlerts } from "@/hooks/useVolatilityAlerts";

const AUTO_DISMISS_MS = 45_000;

function formatPrice(ticker: string, price: number): string {
  if (ticker === "^GSPC") return price.toFixed(2);
  return price.toFixed(4);
}

interface BannerProps {
  alert: VolatilityAlert;
  onDismiss: () => void;
}

function AlertBanner({ alert, onDismiss }: BannerProps) {
  const isBullish = alert.spike_type === "BULLISH_SURGE";
  const isSimulated = alert.explanation.startsWith("[SIM]");

  const outerCls = isBullish
    ? "border-emerald-500/60 bg-gradient-to-r from-emerald-950 via-emerald-900/80 to-slate-950"
    : "border-rose-500/60 bg-gradient-to-r from-rose-950 via-rose-900/80 to-slate-950";

  const pulseCls = isBullish
    ? "bg-emerald-400 shadow-[0_0_10px_3px_rgba(52,211,153,0.6)]"
    : "bg-rose-400 shadow-[0_0_10px_3px_rgba(244,63,94,0.6)]";

  const accentCls = isBullish ? "text-emerald-300" : "text-rose-300";
  const badgeCls = isBullish
    ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
    : "bg-rose-500/20 text-rose-300 border border-rose-500/40";

  const Icon = isBullish ? TrendingUp : TrendingDown;

  return (
    <div
      className={`relative flex items-start gap-4 rounded-lg border px-4 py-3 ${outerCls}`}
      role="alert"
    >
      {/* Pulse dot */}
      <div className="mt-0.5 flex-shrink-0">
        <span className={`inline-block h-3 w-3 rounded-full animate-pulse ${pulseCls}`} />
      </div>

      {/* Content */}
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <Zap className={`h-4 w-4 flex-shrink-0 ${accentCls}`} />
          <span className="font-semibold text-white text-sm">
            Volatility Spike Detected
          </span>
          <span className={`rounded px-2 py-0.5 text-[11px] font-bold tracking-widest uppercase ${badgeCls}`}>
            {alert.spike_type.replace("_", " ")}
          </span>
          {isSimulated && (
            <span className="rounded bg-amber-500/20 border border-amber-500/30 px-1.5 py-0.5 text-[10px] text-amber-400 uppercase tracking-wider">
              simulated
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
          <span className={`flex items-center gap-1 font-semibold ${accentCls}`}>
            <Icon className="h-3 w-3" />
            {alert.asset}
          </span>
          <span className="font-mono text-slate-300">
            {formatPrice(alert.ticker, alert.current_price)}
          </span>
          <span className="text-slate-500">
            z&#8202;=&#8202;{alert.z_score > 0 ? "+" : ""}{alert.z_score.toFixed(2)}σ
          </span>
        </div>

        <p className="text-xs text-slate-300 leading-snug">
          {isSimulated
            ? alert.explanation.replace(/^\[SIM\]\s*/, "")
            : alert.explanation}
        </p>
      </div>

      {/* Dismiss */}
      <button
        onClick={onDismiss}
        aria-label="Dismiss alert"
        className="flex-shrink-0 rounded p-1 text-slate-500 hover:text-slate-300 transition-colors"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

export function SpikeAlertBanner() {
  const { latestAlert } = useVolatilityAlerts();
  const [dismissedId, setDismissedId] = useState<number | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const visible = latestAlert !== null && latestAlert.id !== dismissedId;

  useEffect(() => {
    if (!visible || !latestAlert) return;
    timerRef.current = setTimeout(() => setDismissedId(latestAlert.id), AUTO_DISMISS_MS);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [visible, latestAlert]);

  if (!visible || !latestAlert) return null;

  const dismiss = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setDismissedId(latestAlert.id);
  };

  return (
    <div className="mb-4">
      <AlertBanner alert={latestAlert} onDismiss={dismiss} />
    </div>
  );
}
