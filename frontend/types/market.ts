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
