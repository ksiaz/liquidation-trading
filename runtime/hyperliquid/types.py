"""
Hyperliquid Data Types

Pure data structures for position tracking and liquidation proximity.
No interpretation, no semantic labeling - only factual observations.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class PositionSide(Enum):
    """Position direction."""
    LONG = "LONG"
    SHORT = "SHORT"


class PositionEventType(Enum):
    """Position lifecycle events."""
    OPEN = "OPEN"
    UPDATE = "UPDATE"
    CLOSE = "CLOSE"
    LIQUIDATED = "LIQUIDATED"


@dataclass(frozen=True)
class HyperliquidPosition:
    """
    Single position from Hyperliquid clearinghouseState.

    All fields are factual observations from the API.
    """
    wallet_address: str
    coin: str  # e.g., "BTC", "ETH"
    entry_price: float
    position_size: float  # Signed: positive=long, negative=short
    leverage: float
    liquidation_price: float
    margin_used: float
    unrealized_pnl: float
    position_value: float
    timestamp: float

    # HLP24: Raw API response for append-only storage
    raw_position: Optional[Dict[str, Any]] = None

    @property
    def side(self) -> PositionSide:
        """Derive side from position size sign."""
        return PositionSide.LONG if self.position_size > 0 else PositionSide.SHORT

    @property
    def abs_size(self) -> float:
        """Absolute position size."""
        return abs(self.position_size)

    def distance_to_liquidation(self, current_price: float) -> float:
        """
        Calculate percentage distance from current price to liquidation.

        Direction-aware: positive means safe, negative means crossed (liquidated).

        For LONG: price above liq = positive (safe)
        For SHORT: price below liq = positive (safe)

        Returns:
            Signed percentage (0.005 = 0.5% safe, -0.005 = crossed by 0.5%)
        """
        if current_price <= 0:
            return float('inf')
        if self.side == PositionSide.LONG:
            # LONG: liquidated when price drops below liq_price
            return (current_price - self.liquidation_price) / current_price
        else:
            # SHORT: liquidated when price rises above liq_price
            return (self.liquidation_price - current_price) / current_price


@dataclass(frozen=True)
class LiquidationProximity:
    """
    Aggregate liquidation proximity for a price level.

    Structural observation: How much position value is within X% of liquidation.
    NOT a prediction - factual aggregation only.
    """
    coin: str
    current_price: float
    threshold_pct: float  # e.g., 0.005 for 0.5%

    # Long positions at risk (longs liquidate below current price)
    long_positions_count: int
    long_positions_size: float  # Total size
    long_positions_value: float  # Total notional value
    long_avg_distance_pct: float  # Average distance to liquidation
    long_closest_liquidation: Optional[float]  # Nearest liquidation price

    # Short positions at risk (shorts liquidate above current price)
    short_positions_count: int
    short_positions_size: float
    short_positions_value: float
    short_avg_distance_pct: float
    short_closest_liquidation: Optional[float]

    # Aggregate
    total_positions_at_risk: int
    total_value_at_risk: float

    timestamp: float

    def to_dict(self) -> Dict:
        """Convert to dictionary for logging."""
        return {
            'coin': self.coin,
            'current_price': self.current_price,
            'threshold_pct': self.threshold_pct,
            'long_count': self.long_positions_count,
            'long_value': self.long_positions_value,
            'long_closest': self.long_closest_liquidation,
            'short_count': self.short_positions_count,
            'short_value': self.short_positions_value,
            'short_closest': self.short_closest_liquidation,
            'total_at_risk': self.total_positions_at_risk,
            'total_value': self.total_value_at_risk,
            'timestamp': self.timestamp
        }


@dataclass(frozen=True)
class PositionEvent:
    """
    Position lifecycle event.

    Tracks when positions are opened, modified, or closed.
    """
    event_type: PositionEventType
    wallet_address: str
    coin: str
    side: PositionSide
    size: float
    price: float
    leverage: float
    liquidation_price: float
    margin: float
    timestamp: float

    # Optional: previous state for UPDATE events
    prev_size: Optional[float] = None
    prev_leverage: Optional[float] = None


@dataclass
class WalletState:
    """
    Complete state for a tracked wallet.

    Mutable - updated as positions change.
    """
    address: str
    positions: Dict[str, HyperliquidPosition]  # coin -> position
    account_value: float
    total_margin_used: float
    withdrawable: float
    last_updated: float

    # HLP24: Raw API response for append-only storage
    raw_summary: Optional[Dict[str, Any]] = None

    def get_position(self, coin: str) -> Optional[HyperliquidPosition]:
        """Get position for a specific coin."""
        return self.positions.get(coin)

    def has_position(self, coin: str) -> bool:
        """Check if wallet has position in coin."""
        return coin in self.positions and self.positions[coin].abs_size > 0


@dataclass(frozen=True)
class SystemWallets:
    """
    Known Hyperliquid system wallet addresses.

    From reverse engineering: https://blog.can.ac/2025/12/20/reverse-engineering-hyperliquid/
    """
    # HLP Vault - handles liquidations and market making
    HLP_VAULT: str = "0xdfc24b077bc1425ad1dea75bcb6f8158e10df303"

    # Assistance Fund - protocol reserve
    ASSISTANCE_FUND: str = "0xfefefefefefefefefefefefefefefefefefefefe"

    # HyperEVM USDC Deposit
    USDC_DEPOSIT: str = "0x6b9e773128f453f5c2c60935ee2de2cbc5390a24"

    # Broadcaster addresses (transaction submission)
    BROADCASTERS: tuple = (
        "0x1e9b90ab34427807dc25c7266beb188e86af7ed6",
        "0x2d9d6ae54b069fd372401b71dc4843d85babe3ea",
        "0x67e451964e0421f6e7d07be784f35c530667c2b3",
        "0x76d335fbd515969ed5facf98611ca6e3ba87ff01",
        "0x90eaf322d6e39adbdca7b632ec2436719a99fcd0",
        "0x940e4f78cfb16e07e1e2ef0994e186bde7e6478c",
        "0xf70a9d9a56fe5c75815a9eae6a8593bc59cb6a06",
        "0xffbb4dfc9455f0df2e973d7a371d8ad994264aa6",
    )
