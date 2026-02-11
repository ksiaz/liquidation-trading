"""
Node Bridge - Connects NodeSubscriber to ObservationSystem.

Receives events from the gRPC adapter and feeds them to the observation layer.
"""

import sys
import time
import threading
from typing import Optional, Callable

from .subscriber import NodeSubscriber
from .types import PriceEvent, LiquidationEvent, FillEvent, SyncStatus, SyncStatusCode


class NodeBridge:
    """
    Bridge between NodeSubscriber and ObservationSystem.

    Converts gRPC events to observation system format and ingests them.

    Usage:
        bridge = NodeBridge(observation_system, 'localhost:50051')
        bridge.start()
        # ... events flow automatically ...
        bridge.stop()
    """

    def __init__(
        self,
        observation_system,
        address: str = 'localhost:50051',
        symbols: Optional[list] = None,
        on_stale: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize bridge.

        Args:
            observation_system: ObservationSystem instance
            address: gRPC server address
            symbols: Filter to these symbols (None = all)
            on_stale: Callback when data becomes stale
        """
        self._obs = observation_system
        self._address = address
        self._symbols = symbols
        self._on_stale = on_stale

        # Create subscriber
        self._subscriber = NodeSubscriber(
            address=address,
            client_id='observation-bridge',
            symbols=symbols,
        )

        # Wire callbacks
        self._subscriber.on_price(self._handle_price)
        self._subscriber.on_liquidation(self._handle_liquidation)
        self._subscriber.on_fill(self._handle_fill)
        self._subscriber.on_status(self._handle_status)
        self._subscriber.on_disconnect(self._handle_disconnect)

        # State
        self._running = False
        self._last_status: Optional[SyncStatus] = None

        # External price callbacks (for mark price + ATR updates)
        self._price_callbacks: list = []

        # External fill callbacks (for organic flow detection)
        self._fill_callbacks: list = []

        # Extended fill callbacks (for capitulation tracking - receives full FillEvent)
        self._extended_fill_callbacks: list = []

        # External liquidation callbacks (for cascade detector)
        self._liquidation_callbacks: list = []

        # Metrics
        self._prices_ingested = 0
        self._liquidations_ingested = 0
        self._liquidations_forwarded = 0  # Forwarded to callbacks
        self._fills_ingested = 0
        self._organic_fills_forwarded = 0
        self._errors = 0

    def _handle_price(self, event: PriceEvent):
        """Handle price event - feed to observation system."""
        try:
            # Use wall clock for governance freshness check
            # (avoids dropping data due to node time domain mismatch)
            now = time.time()

            self._obs.ingest_observation(
                timestamp=now,
                symbol=event.symbol,
                event_type='HL_PRICE',
                payload={
                    'oracle_price': event.oracle_float,
                    'mark_price': event.mark_float,
                    'block_height': event.block_height,
                    'exchange': 'HYPERLIQUID',
                    'timestamp': event.timestamp_ns / 1_000_000_000,  # Original timestamp
                },
            )
            self._prices_ingested += 1

            # Forward to price callbacks (mark price + ATR updates)
            if self._price_callbacks and event.oracle_float:
                timestamp = event.timestamp_ns / 1_000_000_000
                for callback in self._price_callbacks:
                    try:
                        callback(event.symbol, event.oracle_float, timestamp)
                    except Exception as cb_err:
                        print(f"[NodeBridge] Price callback error: {cb_err}", file=sys.stderr)

        except Exception as e:
            self._errors += 1
            print(f"[NodeBridge] Error handling price: {e}", file=sys.stderr)

    def _handle_liquidation(self, event: LiquidationEvent):
        """Handle liquidation event - feed to observation system.

        Normalizes HL liquidation to canonical M1 LIQUIDATION format.
        HL uses position side (LONG/SHORT), canonical uses order side (BUY/SELL):
        - LONG liquidation → SELL (must sell to close long)
        - SHORT liquidation → BUY (must buy to close short)
        """
        try:
            now = time.time()

            # Map position side to order side (canonical format)
            # LONG liquidation = forced SELL, SHORT liquidation = forced BUY
            canonical_side = 'SELL' if event.side == 'LONG' else 'BUY'

            # Build canonical payload for normalize_liquidation
            # Format: {'E': timestamp_ms, 'o': {'p': price, 'q': quantity, 'S': side}}
            self._obs.ingest_observation(
                timestamp=now,
                symbol=event.symbol,
                event_type='LIQUIDATION',  # Canonical event type
                payload={
                    'E': event.timestamp_ms,  # Event timestamp (ms)
                    'o': {
                        'p': str(event.price_float),   # Price as string
                        'q': str(event.size_float),    # Quantity as string
                        'S': canonical_side,           # Order side (BUY/SELL)
                    },
                    # HL-specific metadata preserved but not used by normalize_liquidation
                    '_hl_metadata': {
                        'wallet': event.liquidated_wallet,
                        'liquidator': event.liquidator_wallet,
                        'mark_price': float(event.mark_price) if event.mark_price else None,
                        'method': event.method,
                        'fill_id': event.fill_id,
                        'tx_hash': event.tx_hash,
                        'original_side': event.side,  # Preserve original LONG/SHORT
                    },
                },
            )
            self._liquidations_ingested += 1

            # Forward to external callbacks (for zscore calculator and burst aggregator)
            if self._liquidation_callbacks:
                # Pass price and size separately for flexibility
                # Side is LONG/SHORT (position side) - caller maps to order side
                timestamp = event.timestamp_ms / 1000.0  # Convert to seconds

                for callback in self._liquidation_callbacks:
                    try:
                        callback(
                            event.symbol,      # coin (e.g., "BTC")
                            event.side,        # position side: "LONG" or "SHORT"
                            event.price_float, # liquidation price
                            event.size_float,  # size in base units
                            timestamp          # Unix timestamp in seconds
                        )
                        self._liquidations_forwarded += 1
                    except Exception as cb_err:
                        print(f"[NodeBridge] Liquidation callback error: {cb_err}", file=sys.stderr)

        except Exception as e:
            self._errors += 1
            print(f"[NodeBridge] Error handling liquidation: {e}", file=sys.stderr)

    def _handle_fill(self, event: FillEvent):
        """Handle fill event - feed to observation system.

        Fills are used for absorption detection during cascades.
        Side semantics:
        - "B" = buy (taker lifted asks) = buying pressure
        - "A" = sell (taker hit bids) = selling pressure
        """
        try:
            now = time.time()

            self._obs.ingest_observation(
                timestamp=now,
                symbol=event.symbol,
                event_type='HL_FILL',
                payload={
                    'side': event.side,  # "B" or "A"
                    'price': event.price_float,
                    'size': event.size_float,
                    'value_usd': float(event.value_usd) if event.value_usd else 0.0,
                    'timestamp_ms': event.timestamp_ms,
                    'wallet': event.wallet,
                    'is_liquidation': event.is_liquidation,
                    'liquidated_wallet': event.liquidated_wallet,
                    'method': event.method,
                    'fill_id': event.fill_id,
                    'exchange': 'HYPERLIQUID',
                },
            )
            self._fills_ingested += 1

            # Forward organic fills to external callbacks
            # Used for: VWAP, ATR, Orderflow calculators, absorption detection
            # Liquidation fills are already tracked via liquidation events
            if not event.is_liquidation and self._fill_callbacks:
                # Pass raw data - let callback handle mapping
                timestamp = event.timestamp_ms / 1000.0  # Convert to seconds

                for callback in self._fill_callbacks:
                    try:
                        callback(
                            event.symbol,       # coin (e.g., "BTC")
                            event.side,         # "B" (buy) or "A" (sell)
                            event.price_float,  # fill price
                            event.size_float,   # size in base units
                            timestamp           # Unix timestamp in seconds
                        )
                        self._organic_fills_forwarded += 1
                    except Exception as cb_err:
                        print(f"[NodeBridge] Fill callback error: {cb_err}", file=sys.stderr)

            # Forward ALL fills (including liquidation) with extended data
            # Used for: CapitulationTracker (needs dir, closedPnl, startPosition)
            if self._extended_fill_callbacks:
                for callback in self._extended_fill_callbacks:
                    try:
                        callback(event)
                    except Exception as cb_err:
                        print(f"[NodeBridge] Extended fill callback error: {cb_err}", file=sys.stderr)

        except Exception as e:
            self._errors += 1
            print(f"[NodeBridge] Error handling fill: {e}", file=sys.stderr)

    def on_price_update(self, callback: Callable[[str, float, float], None]):
        """
        Register callback for HL oracle price updates.

        Callback signature: callback(symbol, price, timestamp)
        - symbol: Asset symbol (e.g., "BTC")
        - price: Oracle price
        - timestamp: Unix timestamp in seconds

        Use this to keep _mark_prices and ATR fresh from oracle prices
        (arrives every ~1s vs sparse fills).
        """
        self._price_callbacks.append(callback)

    def on_organic_fill(self, callback: Callable[[str, str, float, float, float], None]):
        """
        Register callback for organic (non-liquidation) fills.

        Callback signature: callback(symbol, side, price, size, timestamp)
        - symbol: Asset symbol (e.g., "BTC")
        - side: "B" (buy/taker lifted asks) or "A" (sell/taker hit bids)
        - price: Fill price
        - size: Fill size in base units
        - timestamp: Unix timestamp in seconds

        Use this to feed fills to VWAP, ATR, Orderflow calculators.
        Caller must map:
        - Symbol: "BTC" -> "BTCUSDT"
        - Side for orderflow: "B" -> is_buyer_maker=False, "A" -> is_buyer_maker=True
        """
        self._fill_callbacks.append(callback)

    def on_fill_extended(self, callback: Callable):
        """
        Register callback for ALL fills with extended data (full FillEvent).

        Callback signature: callback(event: FillEvent)
        Called for BOTH organic and liquidation fills.
        FillEvent includes dir, start_position, closed_pnl for capitulation tracking.
        """
        self._extended_fill_callbacks.append(callback)

    def on_hl_liquidation(self, callback: Callable[[str, str, float, float, float], None]):
        """
        Register callback for HL liquidation events.

        Callback signature: callback(symbol, side, price, size, timestamp)
        - symbol: Asset symbol (e.g., "BTC")
        - side: "LONG" or "SHORT" (position side that was liquidated)
        - price: Liquidation price
        - size: Liquidation size in base units (e.g., BTC quantity)
        - timestamp: Unix timestamp in seconds

        Use this to feed liquidations to zscore calculator and burst aggregator.
        The side is the POSITION side (LONG/SHORT), not order side (BUY/SELL).
        Caller must map: LONG -> SELL, SHORT -> BUY for order-side metrics.
        """
        self._liquidation_callbacks.append(callback)

    def _handle_status(self, status: SyncStatus):
        """Handle status event."""
        self._last_status = status

        # Check for stale data
        if status.is_stale and self._on_stale:
            self._on_stale(f"Node adapter status: {status.status.name}")

    def _handle_disconnect(self, reason: str):
        """Handle disconnect from adapter."""
        print(f"[NodeBridge] Disconnected: {reason}", file=sys.stderr)

        if self._on_stale:
            self._on_stale(f"Disconnected from adapter: {reason}")

    def start(self) -> bool:
        """
        Start receiving events.

        Returns:
            True if connected successfully
        """
        if self._running:
            return True

        if not self._subscriber.start():
            print("[NodeBridge] Failed to connect to adapter", file=sys.stderr)
            return False

        self._running = True
        print(f"[NodeBridge] Started, connected to {self._address}", file=sys.stderr)
        return True

    def stop(self):
        """Stop receiving events."""
        self._running = False
        self._subscriber.stop()
        print(f"[NodeBridge] Stopped. Ingested {self._prices_ingested} prices, "
              f"{self._liquidations_ingested} liquidations, "
              f"{self._fills_ingested} fills.", file=sys.stderr)

    @property
    def is_connected(self) -> bool:
        """True if connected to adapter."""
        return self._subscriber.is_connected

    @property
    def is_healthy(self) -> bool:
        """True if adapter is healthy."""
        if not self._last_status:
            return False
        return self._last_status.is_healthy

    def get_status(self) -> Optional[SyncStatus]:
        """Get current adapter status (also updates cached status)."""
        status = self._subscriber.get_status()
        if status is not None:
            self._last_status = status
        return status

    def get_metrics(self) -> dict:
        """Get bridge metrics."""
        subscriber_metrics = self._subscriber.get_metrics()
        return {
            **subscriber_metrics,
            'prices_ingested': self._prices_ingested,
            'liquidations_ingested': self._liquidations_ingested,
            'liquidations_forwarded': self._liquidations_forwarded,
            'fills_ingested': self._fills_ingested,
            'organic_fills_forwarded': self._organic_fills_forwarded,
            'errors': self._errors,
            'is_healthy': self.is_healthy,
        }


def create_node_bridge(
    observation_system,
    address: str = 'localhost:50051',
    symbols: Optional[list] = None,
) -> NodeBridge:
    """
    Factory function to create a NodeBridge.

    Args:
        observation_system: ObservationSystem instance
        address: gRPC server address
        symbols: Filter to these symbols

    Returns:
        Configured NodeBridge instance
    """
    return NodeBridge(
        observation_system=observation_system,
        address=address,
        symbols=symbols,
    )
