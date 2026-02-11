export interface Mandate {
  id: number;
  cycle_id: number;
  symbol: string;
  mandate_type: 'ENTRY' | 'EXIT' | 'BLOCK';
  direction: 'LONG' | 'SHORT' | null;
  source: string | null;
  confidence: number | null;
  timestamp: number;
}

export interface ArbitrationRound {
  id: number;
  cycle_id: number;
  symbol: string;
  mandate_count: number | null;
  winning_mandate_id: number | null;
  action_taken: string | null;
  theorem_applied: string | null;
  timestamp: number | null;
}

export interface Zone {
  id: number;
  node_id: string;
  symbol: string;
  zone_type: 'demand' | 'supply';
  price_low: number | null;
  price_high: number | null;
  strength: number | null;
  created_at: number | null;
}

export interface Liquidation {
  id: number;
  timestamp: number;
  symbol: string;
  side: string | null;
  size: number | null;
  price: number | null;
}

export type StabilityStatus = 'STABLE' | 'WARNING' | 'CRITICAL' | 'UNKNOWN';

export interface Stability {
  status: StabilityStatus;
  total_mandates: number;
  total_actions: number;
  issues_total: number;
  recent_issues: Array<{ issue: string; symbol: string; severity: string }>;
}

export interface Health {
  status: string;
  memory_mb: number;
  memory_percent: number;
  uptime_seconds: number;
  cycles_completed: number;
  last_cycle_at: number | null;
}

export interface ObservatorySnapshot {
  timestamp: string;
  stability: Stability;
  health: Health;
  mandate_counts: { entry: number; exit: number; block: number; total: number };
  table_counts: { execution_cycles: number; mandates: number; m2_nodes: number; liquidation_events: number };
  active_zones_count: number;
  recent_liquidations_count: number;
}
