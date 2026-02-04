"""
Event types for Node Client.

These are pure Python types that don't depend on protobuf,
so consumers don't need grpcio installed just to use the types.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


@dataclass(frozen=True)
class PriceEvent:
    """
    Market price event from node adapter.

    Represents oracle and mark prices for a single asset.
    """
    asset_id: int
    symbol: str
    oracle_price: str      # String to preserve precision
    mark_price: str        # May be empty string
    timestamp_ns: int      # Block timestamp in nanoseconds
    block_height: int

    @property
    def oracle_float(self) -> float:
        """Get oracle price as float."""
        return float(self.oracle_price) if self.oracle_price else 0.0

    @property
    def mark_float(self) -> Optional[float]:
        """Get mark price as float, or None if not set."""
        return float(self.mark_price) if self.mark_price else None


@dataclass(frozen=True)
class LiquidationEvent:
    """
    Liquidation event from node adapter.

    Represents a single liquidation fill.
    """
    symbol: str
    side: str              # "LONG" or "SHORT"
    price: str             # Execution price
    size: str              # Position size
    value_usd: str         # Notional value
    liquidator_wallet: str
    liquidated_wallet: str
    mark_price: str
    method: str            # "market" or "backstop"
    timestamp_ms: int
    fill_id: int
    tx_hash: str

    @property
    def price_float(self) -> float:
        """Get price as float."""
        return float(self.price) if self.price else 0.0

    @property
    def size_float(self) -> float:
        """Get size as float."""
        return float(self.size) if self.size else 0.0

    @property
    def value_usd_float(self) -> float:
        """Get USD value as float."""
        return float(self.value_usd) if self.value_usd else 0.0

    @property
    def is_long_liquidation(self) -> bool:
        """True if a long position was liquidated."""
        return self.side == "LONG"

    @property
    def is_short_liquidation(self) -> bool:
        """True if a short position was liquidated."""
        return self.side == "SHORT"


@dataclass(frozen=True)
class FillEvent:
    """
    Fill event from node adapter.

    Represents a single fill (organic or liquidation).
    """
    symbol: str
    side: str              # "B" (buy) or "A" (ask/sell)
    price: str
    size: str
    value_usd: str
    timestamp_ms: int
    block_height: int
    wallet: str
    is_liquidation: bool
    liquidated_wallet: str
    mark_price: str
    method: str
    fill_id: int
    tx_hash: str

    @property
    def price_float(self) -> float:
        """Get price as float."""
        return float(self.price) if self.price else 0.0

    @property
    def size_float(self) -> float:
        """Get size as float."""
        return float(self.size) if self.size else 0.0

class SyncStatusCode(Enum):
    """Sync status codes from adapter."""
    UNKNOWN = 0
    HEALTHY = 1
    LAGGING = 2
    STALE = 3
    ERROR = 4


@dataclass(frozen=True)
class SyncStatus:
    """
    Sync status from node adapter.

    Indicates adapter health and sync progress.
    """
    status: SyncStatusCode
    latest_block_height: int
    latest_block_time_ns: int
    blocks_behind: int
    current_session: str
    prices_emitted: int
    liquidations_emitted: int
    last_error: str
    uptime_seconds: int
    timestamp_ns: int
    schema_major: int
    schema_minor: int
    schema_patch: int

    @property
    def is_healthy(self) -> bool:
        """True if adapter is healthy."""
        return self.status == SyncStatusCode.HEALTHY

    @property
    def is_stale(self) -> bool:
        """True if data is stale."""
        return self.status in (SyncStatusCode.STALE, SyncStatusCode.ERROR)
