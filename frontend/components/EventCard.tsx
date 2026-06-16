"use client";

import {
  AlertTriangle,
  TrendingDown,
  TrendingUp,
  Minus,
  ArrowUpDown,
  Brain,
  Clock,
  Zap,
  Layers,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import type { AnalysisResult, RiskLevel, Sentiment } from "@/types/market";
import {
  RISK_BADGE_CLASSES,
  RISK_BORDER_CLASSES,
  RISK_HEADER_CLASSES,
  SENTIMENT_BADGE_CLASSES,
  SENTIMENT_LABEL,
  formatConfidence,
  formatSector,
  formatSurprisePct,
  formatTimestamp,
} from "@/lib/utils";

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

const SENTIMENT_ICONS: Record<Sentiment, React.ComponentType<{ className?: string }>> = {
  bullish: TrendingUp,
  bearish: TrendingDown,
  neutral: Minus,
  mixed: ArrowUpDown,
};

function RiskStrip({ level }: { level: RiskLevel }) {
  return (
    <div className={`flex items-center justify-between ${RISK_HEADER_CLASSES[level]}`}>
      <div className="flex items-center gap-2 px-4 py-2">
        {level === "critical" && (
          <AlertTriangle className="h-3.5 w-3.5 text-red-400" />
        )}
        <Badge className={`${RISK_BADGE_CLASSES[level]} text-[10px]`}>
          {level}
        </Badge>
      </div>
      {level === "critical" && (
        <span className="pr-4 text-[10px] font-medium tracking-widest text-red-400 uppercase">
          Immediate Action Required
        </span>
      )}
    </div>
  );
}

function SentimentBadge({ sentiment }: { sentiment: Sentiment }) {
  const Icon = SENTIMENT_ICONS[sentiment];
  return (
    <Badge className={`${SENTIMENT_BADGE_CLASSES[sentiment]} flex items-center gap-1`}>
      <Icon className="h-3 w-3" />
      <span className="capitalize">{sentiment}</span>
    </Badge>
  );
}

function ConfidenceBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const barColor =
    pct >= 80
      ? "bg-emerald-500"
      : pct >= 60
      ? "bg-yellow-500"
      : "bg-red-500";

  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-800">
        <div
          className={`h-full rounded-full transition-all duration-700 ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-8 text-right font-mono text-xs text-slate-400">
        {pct}%
      </span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main EventCard
// ─────────────────────────────────────────────────────────────────────────────

interface EventCardProps {
  event: AnalysisResult;
  isNew?: boolean;
}

export function EventCard({ event, isNew = false }: EventCardProps) {
  const surpriseStr = formatSurprisePct(null); // placeholder — extend when EconomicEvent attached
  const borderClass = RISK_BORDER_CLASSES[event.risk_level];

  return (
    <Card
      className={`border ${borderClass} overflow-hidden transition-all duration-300 ${
        isNew ? "ring-1 ring-white/10" : ""
      }`}
    >
      {/* ── Risk strip ─────────────────────────────────────── */}
      <RiskStrip level={event.risk_level} />

      <CardHeader className="rounded-t-none bg-slate-900 pb-2 pt-3">
        {/* ── Title row ───────────────────────────────────── */}
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="font-mono text-xs text-slate-500">
              {event.event_id}
            </p>
          </div>
          <SentimentBadge sentiment={event.sentiment} />
        </div>

        {/* ── Timestamp + model ───────────────────────────── */}
        <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-500">
          <span className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {formatTimestamp(event.analyzed_at)}
          </span>
          <span className="flex items-center gap-1">
            <Brain className="h-3 w-3" />
            {event.model_used}
          </span>
          {event.cached && (
            <span className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-500">
              cached
            </span>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-3 pt-0">
        {/* ── Market narrative ────────────────────────────── */}
        <p className="text-sm leading-relaxed text-slate-200">
          {event.market_narrative}
        </p>

        {/* ── Impact sectors ──────────────────────────────── */}
        {event.potential_impact_sectors.length > 0 && (
          <div>
            <p className="mb-1.5 flex items-center gap-1 text-xs font-medium text-slate-500">
              <Layers className="h-3 w-3" /> Affected Sectors
            </p>
            <div className="flex flex-wrap gap-1.5">
              {event.potential_impact_sectors.map((sector) => (
                <span
                  key={sector}
                  className="rounded border border-slate-700 bg-slate-800 px-2 py-0.5 text-xs text-slate-300"
                >
                  {formatSector(sector)}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* ── Key levels ──────────────────────────────────── */}
        {event.key_levels && Object.keys(event.key_levels).length > 0 && (
          <div>
            <p className="mb-1.5 flex items-center gap-1 text-xs font-medium text-slate-500">
              <Zap className="h-3 w-3" /> Key Levels
            </p>
            <div className="flex flex-wrap gap-2">
              {Object.entries(event.key_levels).map(([instrument, level]) => (
                <span
                  key={instrument}
                  className="rounded border border-slate-700 bg-slate-800 px-2 py-0.5 font-mono text-xs text-slate-200"
                >
                  <span className="text-slate-500">{instrument}</span>{" "}
                  {level.toLocaleString()}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* ── Confidence bar ──────────────────────────────── */}
        <div>
          <p className="mb-1 text-xs text-slate-500">AI Confidence</p>
          <ConfidenceBar score={event.confidence_score} />
        </div>
      </CardContent>
    </Card>
  );
}
