import type { RiskLevel, Sentiment } from "@/types/market";

// ── Risk level ──────────────────────────────────────────────────────────────

export const RISK_HEADER_CLASSES: Record<RiskLevel, string> = {
  critical:
    "bg-gradient-to-r from-red-950 to-red-900 border-b border-red-700",
  high: "bg-gradient-to-r from-orange-950 to-orange-900 border-b border-orange-700",
  medium:
    "bg-gradient-to-r from-yellow-950 to-yellow-900 border-b border-yellow-700",
  low: "bg-gradient-to-r from-green-950 to-green-900 border-b border-green-700",
};

export const RISK_ACCENT_CLASSES: Record<RiskLevel, string> = {
  critical: "text-red-400",
  high: "text-orange-400",
  medium: "text-yellow-400",
  low: "text-green-400",
};

export const RISK_BADGE_CLASSES: Record<RiskLevel, string> = {
  critical:
    "bg-red-500/20 text-red-300 border border-red-500/40 uppercase tracking-widest",
  high: "bg-orange-500/20 text-orange-300 border border-orange-500/40 uppercase tracking-widest",
  medium:
    "bg-yellow-500/20 text-yellow-300 border border-yellow-500/40 uppercase tracking-widest",
  low: "bg-green-500/20 text-green-300 border border-green-500/40 uppercase tracking-widest",
};

export const RISK_BORDER_CLASSES: Record<RiskLevel, string> = {
  critical: "border-red-800/60",
  high: "border-orange-800/60",
  medium: "border-yellow-800/60",
  low: "border-green-800/60",
};

// ── Sentiment ────────────────────────────────────────────────────────────────

export const SENTIMENT_BADGE_CLASSES: Record<Sentiment, string> = {
  bullish:
    "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40",
  bearish: "bg-rose-500/20 text-rose-300 border border-rose-500/40",
  neutral: "bg-slate-500/20 text-slate-300 border border-slate-500/40",
  mixed: "bg-violet-500/20 text-violet-300 border border-violet-500/40",
};

export const SENTIMENT_LABEL: Record<Sentiment, string> = {
  bullish: "▲ Bullish",
  bearish: "▼ Bearish",
  neutral: "→ Neutral",
  mixed: "⇅ Mixed",
};

// ── Formatting helpers ───────────────────────────────────────────────────────

export function formatConfidence(score: number): string {
  return `${Math.round(score * 100)}%`;
}

export function formatTimestamp(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("en-GB", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      timeZone: "UTC",
    }) + " UTC";
  } catch {
    return iso;
  }
}

export function formatSurprisePct(pct: number | null | undefined): string | null {
  if (pct == null) return null;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}%`;
}

export function formatSector(sector: string): string {
  return sector.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function formatEventDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString("en-GB", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "UTC",
      timeZoneName: "short",
    });
  } catch {
    return iso;
  }
}

// ── URL resolution (works in both SSR and browser) ───────────────────────────

/** Resolve the backend HTTP base URL (no trailing slash) at runtime. */
export function resolveApiBase(): string {
  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
  if (typeof window === "undefined") return "http://localhost:8000";
  const { hostname, protocol } = window.location;
  if (hostname === "localhost" || hostname === "127.0.0.1")
    return "http://localhost:8000";
  const httpScheme = protocol === "https:" ? "https:" : "http:";
  return `${httpScheme}//${hostname.replace(/-\d+\./, "-8000.")}`;
}
