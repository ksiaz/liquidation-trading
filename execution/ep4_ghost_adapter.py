"""
Ghost Exchange Adapter - Live Market Execution v1.0

Real Binance Futures APIs with ZERO actual orders.
Simulated matching based on real order book.

Authority: System v1.0 Freeze, Ghost Execution Correction
"""

from dataclasses import dataclass
from typing import Optional, Dict, List
from enum import Enum
import time
import hmac
import hashlib
import requests
from urllib.parse import urlencode


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
# Binance API Client (Read-Only)
# ==============================================================================

class BinanceAPIClient:
    """
    Binance Futures API client.
    READ-ONLY operations only.
    """
    
    BASE_URL = "https://fapi.binance.com"
    
    def __init__(self, *, api_key: Optional[str] = None):
        """
        Initialize Binance API client.
        
        Args:
            api_key: Optional API key for rate limit benefits (read-only)
        """
        self._api_key = api_key
        self._session = requests.Session()
        if api_key:
            self._session.headers.update({"X-MBX-APIKEY": api_key})
    
    def get_exchange_info(self, *, symbol: str) -> Dict:
        """
        Get exchange trading rules for symbol.
        
        Args:
            symbol: Trading symbol (e.g. BTCUSDT)
        
        Returns:
            Exchange info dict with filters
        
        Raises:
            requests.HTTPError: If API call fails
        """
        url = f"{self.BASE_URL}/fapi/v1/exchangeInfo"
        params = {"symbol": symbol}
        
        response = self._session.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract symbol info
        for sym in data.get("symbols", []):
            if sym["symbol"] == symbol:
                return sym
        
        raise ValueError(f"Symbol {symbol} not found in exchange info")
    
    def get_order_book(self, *, symbol: str, limit: int = 20) -> Dict:
        """
        Get current order book depth.
        
        Args:
            symbol: Trading symbol
            limit: Depth limit (5, 10, 20, 50, 100, 500, 1000)
        
        Returns:
            Order book dict with bids/asks
        
        Raises:
            requests.HTTPError: If API call fails
        """
        url = f"{self.BASE_URL}/fapi/v1/depth"
        params = {"symbol": symbol, "limit": limit}
        
        response = self._session.get(url, params=params)
        response.raise_for_status()
        
        return response.json()
    
    def get_ticker_price(self, *, symbol: str) -> float:
        """
        Get current ticker price.
        
        Args:
            symbol: Trading symbol
        
        Returns:
            Current price
        """
        url = f"{self.BASE_URL}/fapi/v1/ticker/price"
        params = {"symbol": symbol}
        
        response = self._session.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        return float(data["price"])


# ==============================================================================
# Ghost Exchange Adapter
# ==============================================================================

class GhostExchangeAdapter:
    """
    Ghost execution adapter for live market data.
    
    Uses real Binance APIs to:
    - Fetch order book
    - Validate exchange constraints
    - Simulate order matching
    
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
            symbol: Trading symbol
            api_key: Optional read-only API key
            execution_mode: GHOST_LIVE or GHOST_SNAPSHOT
        """
        self._symbol = symbol
        self._execution_mode = execution_mode
        self._api_client = BinanceAPIClient(api_key=api_key)
        
        # Fetch and cache exchange info
        self._exchange_info = self._api_client.get_exchange_info(symbol=symbol)
        self._filters = self._parse_filters(self._exchange_info)
        
        # For snapshot mode
        self._current_snapshot: Optional[OrderBookSnapshot] = None
    
    def _parse_filters(self, exchange_info: Dict) -> Dict:
        """Parse exchange filters into usable format."""
        filters = {}
        for f in exchange_info.get("filters", []):
            filter_type = f["filterType"]
            if filter_type == "PRICE_FILTER":
                filters["tick_size"] = float(f["tickSize"])
                filters["min_price"] = float(f["minPrice"])
                filters["max_price"] = float(f["maxPrice"])
            elif filter_type == "LOT_SIZE":
                filters["step_size"] = float(f["stepSize"])
                filters["min_qty"] = float(f["minQty"])
                filters["max_qty"] = float(f["maxQty"])
            elif filter_type == "MIN_NOTIONAL":
                filters["min_notional"] = float(f["notional"])
        
        return filters
    
    def capture_snapshot(self) -> OrderBookSnapshot:
        """
        Capture current order book snapshot.
        
        Returns:
            OrderBookSnapshot
        """
        timestamp = time.time()
        ob_data = self._api_client.get_order_book(symbol=self._symbol, limit=20)
        
        bids = tuple((float(p), float(q)) for p, q in ob_data["bids"])
        asks = tuple((float(p), float(q)) for p, q in ob_data["asks"])
        
        best_bid = bids[0][0] if bids else 0.0
        best_ask = asks[0][0] if asks else 0.0
        spread = best_ask - best_bid if (best_bid and best_ask) else 0.0
        
        snapshot = OrderBookSnapshot(
            snapshot_id=f"{self._symbol}_{int(timestamp * 1000)}",
            timestamp=timestamp,
            symbol=self._symbol,
            bids=bids,
            asks=asks,
            best_bid=best_bid,
            best_ask=best_ask,
            spread=spread
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
        price: Optional[float] = None
    ) -> GhostExecutionResult:
        """
        Execute ghost order (simulated).
        
        Args:
            side: BUY or SELL
            order_type: MARKET or LIMIT
            quantity: Order quantity
            price: Limit price (required for LIMIT orders)
        
        Returns:
            GhostExecutionResult with simulation outcome
        """
        # Get current snapshot
        if self._execution_mode == ExecutionMode.GHOST_LIVE:
            snapshot = self.capture_snapshot()
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
