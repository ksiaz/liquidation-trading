"""
Ghost Exchange Adapter - Live Market Execution v1.0

Simulated matching based on real order book (HL L2 data).
ZERO actual orders placed.

Authority: System v1.0 Freeze, Ghost Execution Correction
"""

from dataclasses import dataclass
from typing import Optional, Dict, List
from enum import Enum
import time
import requests


# ==============================================================================
# Ghost Execution Types
# ==============================================================================

class ExecutionMode(Enum):
    """Execution mode indicator."""
    GHOST_LIVE = "GHOST_LIVE"
    GHOST_SNAPSHOT = "GHOST_SNAPSHOT"


class FillEstimate(Enum):
    """Estimated fill outcome."""
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    NONE = "NONE"


# ==============================================================================
# Normalized Orderbook Schema (Exchange-Agnostic)
# ==============================================================================

@dataclass(frozen=True)
class NormalizedOrderbook:
    """
    Exchange-agnostic orderbook representation.

    Populated from Hyperliquid L2 book.

    Levels are (price, quantity) tuples sorted by price.
    """
    symbol: str               # Base symbol (e.g., "BTC")
    timestamp: float          # Unix timestamp
    bids: tuple               # ((price, qty), ...) descending by price
    asks: tuple               # ((price, qty), ...) ascending by price
    source: str = "UNKNOWN"   # "HL_NODE", "HL_WS", "BINANCE", etc.

    @property
    def best_bid(self) -> float:
        return self.bids[0][0] if self.bids else 0.0

    @property
    def best_ask(self) -> float:
        return self.asks[0][0] if self.asks else 0.0

    @property
    def spread(self) -> float:
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return 0.0

    @property
    def mid_price(self) -> float:
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2
        return self.best_bid or self.best_ask or 0.0

    @classmethod
    def from_hl_book(cls, hl_book: Dict, symbol: str) -> 'NormalizedOrderbook':
        """Convert HL client orderbook to normalized format.

        HL book format from runtime/hyperliquid/client.py:
        {
            'timestamp': float,
            'coin': str,
            'mid_price': float,
            'bids': [{'price': float, 'size': float, ...}, ...],
            'asks': [{'price': float, 'size': float, ...}, ...],
        }
        """
        bids = tuple(
            (level['price'], level['size'])
            for level in hl_book.get('bids', [])
        )
        asks = tuple(
            (level['price'], level['size'])
            for level in hl_book.get('asks', [])
        )
        return cls(
            symbol=symbol,
            timestamp=hl_book.get('timestamp', time.time()),
            bids=bids,
            asks=asks,
            source="HL_WS"
        )



@dataclass(frozen=True)
class OrderBookSnapshot:
    """
    Order book snapshot at specific time.
    Used for ghost execution and replay.
    """
    snapshot_id: str
    timestamp: float
    symbol: str
    bids: tuple[tuple[float, float], ...]  # (price, quantity)
    asks: tuple[tuple[float, float], ...]
    best_bid: float
    best_ask: float
    spread: float


@dataclass(frozen=True)
class GhostExecutionResult:
    """
    Result of ghost execution attempt.
    Contains order book state and simulation outcome.
    """
    execution_mode: ExecutionMode
    exchange: str
    symbol: str
    order_side: str  # BUY / SELL
    order_type: str  # MARKET / LIMIT
    price: Optional[float]
    quantity: float
    orderbook_snapshot_id: str
    best_bid: float
    best_ask: float
    spread: float
    would_execute: bool
    fill_estimate: FillEstimate
    reject_reason: Optional[str]
    timestamp: float


# ==============================================================================
# HL Asset Metadata
# ==============================================================================

# Cache HL meta globally — one fetch per process, all adapters share it
_HL_META_CACHE: Optional[Dict] = None


def _fetch_hl_meta() -> Dict[str, int]:
    """Fetch szDecimals for all HL perp assets. Cached per process."""
    global _HL_META_CACHE
    if _HL_META_CACHE is not None:
        return _HL_META_CACHE

    resp = requests.post(
        "https://api.hyperliquid.xyz/info",
        json={"type": "meta"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    result = {}
    for asset in data.get("universe", []):
        name = asset.get("name", "")
        if name:
            result[name] = int(asset.get("szDecimals", 0))

    _HL_META_CACHE = result
    return result


def _hl_filters_for_coin(coin: str) -> Dict:
    """Build ghost adapter filters from HL asset metadata."""
    meta = _fetch_hl_meta()
    sz_decimals = meta.get(coin, 2)  # default 2 decimals
    step_size = 10 ** (-sz_decimals)

    return {
        "tick_size": 0.0001,       # HL uses sig-fig pricing, permissive default
        "min_price": 0.0001,
        "max_price": 100000000.0,
        "step_size": step_size,
        "min_qty": step_size,
        "max_qty": 100000000.0,
        "min_notional": 10.0,      # HL minimum ~$10
    }


# ==============================================================================
# Ghost Exchange Adapter
# ==============================================================================

class GhostExchangeAdapter:
    """
    Ghost execution adapter for live market data.

    Uses HL L2 orderbook for fill simulation.
    Validates constraints from HL asset metadata (szDecimals).

    NEVER places actual orders.
    """

    def __init__(
        self,
        *,
        symbol: str,
        api_key: Optional[str] = None,
        execution_mode: ExecutionMode = ExecutionMode.GHOST_LIVE
    ):
        """
        Initialize ghost exchange adapter.

        Args:
            symbol: Trading symbol (USDT format, e.g. BTCUSDT)
            api_key: Unused, kept for interface compatibility
            execution_mode: GHOST_LIVE or GHOST_SNAPSHOT
        """
        self._symbol = symbol
        self._execution_mode = execution_mode

        # Get filters from HL asset metadata (szDecimals)
        coin = symbol.replace("USDT", "")
        self._filters = _hl_filters_for_coin(coin)
        self._exchange_info = {"symbol": symbol}

        # For snapshot mode
        self._current_snapshot: Optional[OrderBookSnapshot] = None
    
    def capture_snapshot(
        self,
        orderbook: Optional[NormalizedOrderbook] = None
    ) -> OrderBookSnapshot:
        """
        Capture current order book snapshot from HL L2 data.

        Args:
            orderbook: Normalized orderbook from HL L2 WebSocket.

        Returns:
            OrderBookSnapshot
        """
        if orderbook is None:
            raise RuntimeError(f"No orderbook provided for {self._symbol}")

        snapshot = OrderBookSnapshot(
            snapshot_id=f"{self._symbol}_{int(orderbook.timestamp * 1000)}",
            timestamp=orderbook.timestamp,
            symbol=self._symbol,
            bids=orderbook.bids,
            asks=orderbook.asks,
            best_bid=orderbook.best_bid,
            best_ask=orderbook.best_ask,
            spread=orderbook.spread
        )

        if self._execution_mode == ExecutionMode.GHOST_SNAPSHOT:
            self._current_snapshot = snapshot

        return snapshot
    
    def execute_ghost_order(
        self,
        *,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float] = None,
        orderbook: Optional[NormalizedOrderbook] = None
    ) -> GhostExecutionResult:
        """
        Execute ghost order (simulated).

        Args:
            side: BUY or SELL
            order_type: MARKET or LIMIT
            quantity: Order quantity
            price: Limit price (required for LIMIT orders)
            orderbook: Normalized orderbook from HL L2 WebSocket.

        Returns:
            GhostExecutionResult with simulation outcome
        """
        # Get current snapshot
        if self._execution_mode == ExecutionMode.GHOST_LIVE:
            snapshot = self.capture_snapshot(orderbook=orderbook)
        elif self._current_snapshot is not None:
            snapshot = self._current_snapshot
        else:
            raise RuntimeError("No snapshot available in GHOST_SNAPSHOT mode")
        
        # Validate constraints
        reject_reason = self._validate_constraints(quantity, price)
        if reject_reason:
            return self._create_result(
                snapshot=snapshot,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                would_execute=False,
                fill_estimate=FillEstimate.NONE,
                reject_reason=reject_reason
            )
        
        # Simulate matching
        would_execute, fill_estimate = self._simulate_matching(
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            snapshot=snapshot
        )
        
        return self._create_result(
            snapshot=snapshot,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            would_execute=would_execute,
            fill_estimate=fill_estimate,
            reject_reason=None
        )
    
    def _validate_constraints(
        self,
        quantity: float,
        price: Optional[float]
    ) -> Optional[str]:
        """
        Validate order against exchange constraints.
        
        Returns:
            Rejection reason or None if valid
        """
        # Quantity constraints
        if quantity < self._filters["min_qty"]:
            return f"Quantity below minimum: {quantity} < {self._filters['min_qty']}"
        
        if quantity > self._filters["max_qty"]:
            return f"Quantity above maximum: {quantity} > {self._filters['max_qty']}"
        
        # Step size
        steps = quantity / self._filters["step_size"]
        if abs(steps - round(steps)) > 1e-8:
            return f"Quantity not multiple of step size: {self._filters['step_size']}"
        
        # Price constraints (if limit order)
        if price is not None:
            if price < self._filters["min_price"]:
                return f"Price below minimum: {price} < {self._filters['min_price']}"
            
            if price > self._filters["max_price"]:
                return f"Price above maximum: {price} > {self._filters['max_price']}"
            
            # Tick size
            ticks = price / self._filters["tick_size"]
            if abs(ticks - round(ticks)) > 1e-8:
                return f"Price not multiple of tick size: {self._filters['tick_size']}"
        
        return None
    
    def _simulate_matching(
        self,
        *,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float],
        snapshot: OrderBookSnapshot
    ) -> tuple[bool, FillEstimate]:
        """
        Simulate order matching against order book.
        
        Returns:
            (would_execute, fill_estimate)
        """
        if order_type == "MARKET":
            # Market orders always execute if liquidity exists
            book_side = snapshot.asks if side == "BUY" else snapshot.bids
            if not book_side:
                return (False, FillEstimate.NONE)
            
            available_liquidity = sum(q for _, q in book_side[:5])  # Top 5 levels
            if quantity <= available_liquidity:
                return (True, FillEstimate.FULL)
            else:
                return (True, FillEstimate.PARTIAL)
        
        elif order_type == "LIMIT":
            if price is None:
                return (False, FillEstimate.NONE)
            
            # Check if limit order would cross spread
            if side == "BUY":
                # Buy limit crosses if price >= best ask
                if price >= snapshot.best_ask:
                    # Would execute immediately
                    available_at_price = sum(
                        q for p, q in snapshot.asks if p <= price
                    )
                    if quantity <= available_at_price:
                        return (True, FillEstimate.FULL)
                    else:
                        return (True, FillEstimate.PARTIAL)
                else:
                    # Would rest in book
                    return (False, FillEstimate.NONE)
            else:  # SELL
                # Sell limit crosses if price <= best bid
                if price <= snapshot.best_bid:
                    available_at_price = sum(
                        q for p, q in snapshot.bids if p >= price
                    )
                    if quantity <= available_at_price:
                        return (True, FillEstimate.FULL)
                    else:
                        return (True, FillEstimate.PARTIAL)
                else:
                    return (False, FillEstimate.NONE)
        
        return (False, FillEstimate.NONE)
    
    def _create_result(
        self,
        *,
        snapshot: OrderBookSnapshot,
        side: str,
        order_type: str,
        quantity: float,
        price: Optional[float],
        would_execute: bool,
        fill_estimate: FillEstimate,
        reject_reason: Optional[str]
    ) -> GhostExecutionResult:
        """Create ghost execution result."""
        return GhostExecutionResult(
            execution_mode=self._execution_mode,
            exchange="BINANCE_FUTURES",
            symbol=self._symbol,
            order_side=side,
            order_type=order_type,
            price=price,
            quantity=quantity,
            orderbook_snapshot_id=snapshot.snapshot_id,
            best_bid=snapshot.best_bid,
            best_ask=snapshot.best_ask,
            spread=snapshot.spread,
            would_execute=would_execute,
            fill_estimate=fill_estimate,
            reject_reason=reject_reason,
            timestamp=snapshot.timestamp
        )
    
    def get_filters(self) -> Dict:
        """Get exchange filters."""
        return self._filters.copy()
