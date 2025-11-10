export type OpportunityType =
  | "spot_cross"
  | "spot_vs_perp"
  | "funding"
  | "kimchi_premium";

export interface OpportunityLeg {
  exchange: string;
  venue_type: "spot" | "perp" | "fx";
  side: "buy" | "sell";
  symbol: string;
  price: number;
  quantity: number;
}

export interface Opportunity {
  id: string;
  type: OpportunityType;
  symbol: string;
  spread_bps: number;
  expected_pnl_pct: number;
  notional: number;
  timestamp: string;
  description: string;
  legs: OpportunityLeg[];
  metadata?: OpportunityMetadata;
}

export interface OpportunityMetadata {
  premium_pct?: number;
  fx_rate?: number;
  target_allocation_pct?: number;
  recommended_notional?: number;
  recommended_action?: "buy_krw" | "sell_krw";
}
