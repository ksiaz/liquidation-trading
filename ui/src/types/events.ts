/**
 * Event Types - Observability UI
 * 
 * TypeScript types for audit events, ghost execution, and snapshots.
 * These are read-only data structures from the system.
 */

export type DecisionCode = "AUTHORIZED_ACTION" | "NO_ACTION" | "REJECTED_ACTION";
export type ExecutionResult = "SUCCESS" | "NOOP" | "FAILED_SAFE" | "REJECTED";
export type ExecutionMode = "GHOST_LIVE" | "SNAPSHOT";
export type FillEstimate = "FULL" | "PARTIAL" | "NONE";

/**
 * Audit Event from EP-3/EP-4 pipeline
 */
export interface AuditEvent {
    trace_id: string;
    timestamp: number;
    strategy_id: string;
    decision_code: DecisionCode;
    action_type?: string;
    execution_result?: ExecutionResult;
    reason_code: string;
    symbol: string;
}

/**
 * Ghost Execution Record from EP-4
 */
export interface GhostExecutionRecord {
    trace_id: string;
    execution_mode: ExecutionMode;
    orderbook_snapshot_id: string;
    best_bid: number;
    best_ask: number;
    spread: number;
    would_execute: boolean;
    fill_estimate: FillEstimate;
    reject_reason?: string;
    order_type?: string;
    quantity?: number;
    price?: number;
}

/**
 * Snapshot Metadata
 */
export interface SnapshotMetadata {
    snapshot_id: string;
    symbol: string;
    timestamp: number;
    best_bid: number;
    best_ask: number;
    spread: number;
    bids: [number, number][];
    asks: [number, number][];
}

/**
 * System Status
 */
export interface SystemStatus {
    mode: ExecutionMode;
    symbols: string[];
    last_activity: number;
    event_count: number;
    event_rate: number;
}

/**
 * Strategy Activity Metrics
 */
export interface StrategyActivity {
    strategy_id: string;
    proposals_attempted: number;
    proposals_emitted: number;
    last_proposal_timestamp: number;
    abstention_count: number;
    silence_percentage: number;
}

/**
 * Aggregated Metrics
 */
export interface AggregatedMetrics {
    total_events: number;
    symbols: string[];
    proposal_frequency: Record<string, number>;
    authorization_rate: number;
    execution_feasibility_rate: number;
    partial_fill_frequency: number;
    rest_in_book_frequency: number;
    risk_gate_failures: Record<string, number>;
    cooldown_violations: number;
}
