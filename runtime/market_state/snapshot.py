"""
Market State Snapshot

Per-symbol market state at a point in time. Two layers:
- Derived values: calculator outputs (VWAP, ATR, orderflow, regime, etc.)
- Raw input counters: pipeline health indicators for fault detection

Triggers: PERIODIC (10s), ENTRY, EXIT, REGIME_CHANGE, CASCADE_TRANSITION, LIQ_SPIKE
"""

from dataclasses import dataclass, fields, asdict
from enum import Enum
from typing import Optional


class SnapshotTrigger(Enum):
    PERIODIC = "PERIODIC"
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    REGIME_CHANGE = "REGIME_CHANGE"
    CASCADE_TRANSITION = "CASCADE_TRANSITION"
    LIQ_SPIKE = "LIQ_SPIKE"


@dataclass(slots=True)
class MarketSnapshot:
    # ── Identity ──
    timestamp: float
    symbol: str
    trigger: str  # SnapshotTrigger value

    # ── DERIVED VALUES (calculator outputs) ──

    # Price & VWAP
    price: float
    vwap: Optional[float] = None
    vwap_distance: Optional[float] = None
    vwap_z: Optional[float] = None

    # Volatility
    atr_5m: Optional[float] = None
    atr_30m: Optional[float] = None
    atr_ratio: Optional[float] = None
    atr_5m_pct: Optional[float] = None

    # Orderflow
    orderflow_ratio: Optional[float] = None
    orderflow_fill_count: Optional[int] = None
    orderflow_neutralized: bool = False

    # Liquidation Pressure
    liq_z: Optional[float] = None
    rolling_liq_volume: Optional[float] = None
    rolling_liq_z: Optional[float] = None

    # Regime & Cascade
    regime: Optional[str] = None
    cascade_state: Optional[str] = None

    # Proximity
    proximity_count: Optional[int] = None
    proximity_usd_at_risk: Optional[float] = None
    closest_liq_pct: Optional[float] = None

    # Orderbook Depth
    bid_depth_2pct: Optional[float] = None
    ask_depth_2pct: Optional[float] = None
    absorption_ratio_longs: Optional[float] = None
    absorption_ratio_shorts: Optional[float] = None

    # Capitulation & Position
    cap_confidence: Optional[float] = None
    has_position: bool = False
    position_side: Optional[str] = None

    # ── RAW INPUT COUNTERS (pipeline health) ──

    feed_age_ms: Optional[int] = None
    raw_of_fills_60s: Optional[int] = None
    raw_liq_events_baseline: Optional[int] = None
    raw_liq_rate_1m: Optional[float] = None
    raw_burst_count: Optional[int] = None
    raw_burst_volume: Optional[float] = None
    raw_rolling_history_count: Optional[int] = None
    raw_rolling_warmed_up: bool = False
    raw_l2_age_ms: Optional[int] = None
    raw_cap_fills: Optional[int] = None

    def to_dict(self) -> dict:
        """Convert to dict for JSON export / AI analysis."""
        return asdict(self)

    # Column order for PG INSERT (excluding id which is BIGSERIAL)
    _PG_COLUMNS = (
        "ts", "symbol", "trigger",
        "price", "vwap", "vwap_distance", "vwap_z",
        "atr_5m", "atr_30m", "atr_ratio", "atr_5m_pct",
        "orderflow_ratio", "orderflow_fill_count", "orderflow_neutralized",
        "liq_z", "rolling_liq_volume", "rolling_liq_z",
        "regime", "cascade_state",
        "proximity_count", "proximity_usd_at_risk", "closest_liq_pct",
        "bid_depth_2pct", "ask_depth_2pct",
        "absorption_ratio_longs", "absorption_ratio_shorts",
        "cap_confidence", "has_position", "position_side",
        "feed_age_ms", "raw_of_fills_60s",
        "raw_liq_events_baseline", "raw_liq_rate_1m",
        "raw_burst_count", "raw_burst_volume",
        "raw_rolling_history_count", "raw_rolling_warmed_up",
        "raw_l2_age_ms", "raw_cap_fills",
    )

    def to_pg_row(self) -> tuple:
        """Tuple matching _PG_COLUMNS order for INSERT."""
        return (
            self.timestamp, self.symbol, self.trigger,
            self.price, self.vwap, self.vwap_distance, self.vwap_z,
            self.atr_5m, self.atr_30m, self.atr_ratio, self.atr_5m_pct,
            self.orderflow_ratio, self.orderflow_fill_count, self.orderflow_neutralized,
            self.liq_z, self.rolling_liq_volume, self.rolling_liq_z,
            self.regime, self.cascade_state,
            self.proximity_count, self.proximity_usd_at_risk, self.closest_liq_pct,
            self.bid_depth_2pct, self.ask_depth_2pct,
            self.absorption_ratio_longs, self.absorption_ratio_shorts,
            self.cap_confidence, self.has_position, self.position_side,
            self.feed_age_ms, self.raw_of_fills_60s,
            self.raw_liq_events_baseline, self.raw_liq_rate_1m,
            self.raw_burst_count, self.raw_burst_volume,
            self.raw_rolling_history_count, self.raw_rolling_warmed_up,
            self.raw_l2_age_ms, self.raw_cap_fills,
        )

    @classmethod
    def pg_insert_sql(cls) -> str:
        """SQL INSERT statement with %s placeholders."""
        cols = ", ".join(cls._PG_COLUMNS)
        placeholders = ", ".join(["%s"] * len(cls._PG_COLUMNS))
        return f"INSERT INTO market_snapshots ({cols}) VALUES ({placeholders})"
