// TypeScript types mirroring the backend Pydantic models exactly.
// Keep in sync with backend/app/models/

export type Sentiment = "bullish" | "bearish" | "neutral" | "mixed";
export type RiskLevel = "low" | "medium" | "high" | "critical";
export type WSMessageType =
  | "connection_ack"
  | "analysis_result"
  | "heartbeat"
  | "error"
  | "disconnect";

export interface AnalysisResult {
  event_id: string;
  sentiment: Sentiment;
  market_narrative: string;
  potential_impact_sectors: string[];
  risk_level: RiskLevel;
  confidence_score: number;
  key_levels: Record<string, number> | null;
  model_used: string;
  cached: boolean;
  analyzed_at: string;
}

export interface WSMessage {
  type: WSMessageType;
  timestamp: string;
  data: AnalysisResult | null;
  client_id: string | null;
  message: string | null;
}

export type ConnectionStatus =
  | "connecting"
  | "connected"
  | "disconnected"
  | "error";

/** Superset of AnalysisResult — includes the underlying economic event fields. */
export interface HistoryEntry extends AnalysisResult {
  event_name: string;
  country: string;
  currency: string;
  event_timestamp: string;
  impact_level: string;
  actual: number | null;
  forecast: number | null;
  previous: number | null;
  unit: string | null;
  surprise_pct: number | null;
}

export interface HistoryResponse {
  items: HistoryEntry[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export type SpikeType = "BULLISH_SURGE" | "BEARISH_DROP";

export interface VolatilityAlert {
  id: number;
  asset: string;
  ticker: string;
  spike_type: SpikeType;
  current_price: number;
  z_score: number;
  cause_found: boolean;
  explanation: string;
  detected_at: string;
}

export interface VolatilityAlertsResponse {
  items: VolatilityAlert[];
  total: number;
}
