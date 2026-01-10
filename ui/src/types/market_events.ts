/**
 * Market Event Types
 * 
 * Raw market observations for hypothesis testing.
 * No interpretation. No aggregation.
 */

export interface TradeEvent {
    timestamp: number;
    symbol: string;
    price: number;
    quantity: number;
    side: "BUY" | "SELL";
    trade_id: number;
}

export interface LiquidationEvent {
    timestamp: number;
    symbol: string;
    side: string;
    price: number;
    quantity: number;
    order_type: string;
}

export interface BookUpdateEvent {
    timestamp: number;
    symbol: string;
    bids_changed: number;
    asks_changed: number;
    event_type: string;
}

/**
 * Correlation Window
 * 
 * Time-aligned event counts within a window.
 * NO RATIOS. NO THRESHOLDS. Counts only.
 */
export interface CorrelationWindow {
    center_timestamp: number;
    window_seconds: number;

    // Market events
    trade_count: number;
    total_volume: number;
    book_update_count: number;
    liquidation_count: number;

    // System events
    proposal_count: number;
    ghost_execution_count: number;
}
