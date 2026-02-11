"""
Node Subscriber - gRPC client for HL Node Adapter.

Subscribes to price and liquidation streams from the out-of-process adapter.
Provides callbacks for event processing.
"""

import sys
import threading
import time
from typing import Callable, Optional, List, Set

import grpc

# Import proto-generated modules
# These are expected to be in the hl-adapter directory
# We add the path dynamically
import os
_adapter_path = os.path.join(os.path.dirname(__file__), '..', '..', 'hl-adapter')
if _adapter_path not in sys.path:
    sys.path.insert(0, _adapter_path)

try:
    import events_pb2
    import events_pb2_grpc
except ImportError:
    # Fallback: try from current directory (for testing)
    events_pb2 = None
    events_pb2_grpc = None

from .types import PriceEvent, LiquidationEvent, FillEvent, SyncStatus, SyncStatusCode


# Callback type aliases
PriceCallback = Callable[[PriceEvent], None]
LiquidationCallback = Callable[[LiquidationEvent], None]
StatusCallback = Callable[[SyncStatus], None]
FillCallback = Callable[[FillEvent], None]
DisconnectCallback = Callable[[str], None]


class NodeSubscriber:
    """
    Subscribes to events from HL Node Adapter over gRPC.

    Usage:
        subscriber = NodeSubscriber('localhost:50051')

        # Register callbacks
        subscriber.on_price(handle_price)
        subscriber.on_liquidation(handle_liquidation)

        # Start receiving events
        subscriber.start()

        # ... later ...
        subscriber.stop()
    """

    RECONNECT_DELAY_SEC = 5.0
    SCHEMA_VERSION = (1, 1, 0)

    def __init__(
        self,
        address: str = 'localhost:50051',
        client_id: str = 'trading-system',
        symbols: Optional[List[str]] = None,
    ):
        """
        Initialize subscriber.

        Args:
            address: gRPC server address (host:port)
            client_id: Client identifier for logging
            symbols: Filter events to these symbols (None = all)
        """
        if events_pb2 is None:
            raise ImportError(
                "gRPC proto modules not found. "
                "Ensure hl-adapter/events_pb2.py exists."
            )

        self._address = address
        self._client_id = client_id
        self._symbols = symbols or []

        # Callbacks
        self._price_callbacks: List[PriceCallback] = []
        self._liq_callbacks: List[LiquidationCallback] = []
        self._fill_callbacks: List[FillCallback] = []
        self._status_callbacks: List[StatusCallback] = []
        self._disconnect_callbacks: List[DisconnectCallback] = []

        # State
        self._running = False
        self._connected = False
        self._channel: Optional[grpc.Channel] = None
        self._stub = None

        # Threads
        self._price_thread: Optional[threading.Thread] = None
        self._liq_thread: Optional[threading.Thread] = None
        self._fill_thread: Optional[threading.Thread] = None
        self._status_thread: Optional[threading.Thread] = None

        # Metrics
        self._prices_received = 0
        self._liquidations_received = 0
        self._fills_received = 0
        self._reconnect_count = 0
        self._last_price_time = 0.0
        self._last_liq_time = 0.0
        self._last_fill_time = 0.0

    def on_price(self, callback: PriceCallback):
        """Register price event callback."""
        self._price_callbacks.append(callback)

    def on_liquidation(self, callback: LiquidationCallback):
        """Register liquidation event callback."""
        self._liq_callbacks.append(callback)

    def on_fill(self, callback: FillCallback):
        """Register fill event callback."""
        self._fill_callbacks.append(callback)

    def on_status(self, callback: StatusCallback):
        """Register status event callback."""
        self._status_callbacks.append(callback)

    def on_disconnect(self, callback: DisconnectCallback):
        """Register disconnect callback."""
        self._disconnect_callbacks.append(callback)

    def _connect(self) -> bool:
        """Connect to gRPC server."""
        try:
            self._channel = grpc.insecure_channel(
                self._address,
                options=[
                    ('grpc.keepalive_time_ms', 30000),
                    ('grpc.keepalive_timeout_ms', 10000),
                    ('grpc.keepalive_permit_without_calls', True),
                ]
            )
            self._stub = events_pb2_grpc.HLNodeAdapterStub(self._channel)

            # Handshake
            response = self._stub.Handshake(events_pb2.HandshakeRequest(
                client_version=events_pb2.SchemaVersion(
                    major=self.SCHEMA_VERSION[0],
                    minor=self.SCHEMA_VERSION[1],
                    patch=self.SCHEMA_VERSION[2],
                ),
                client_id=self._client_id,
            ))

            if not response.compatible:
                print(f"[NODE_CLIENT] Incompatible schema: {response.message}",
                      file=sys.stderr)
                return False

            self._connected = True
            print(f"[NODE_CLIENT] Connected to {self._address}: {response.message}",
                  file=sys.stderr)
            return True

        except grpc.RpcError as e:
            print(f"[NODE_CLIENT] Connection failed: {e}", file=sys.stderr)
            return False

    def _disconnect(self, reason: str = ""):
        """Disconnect from server."""
        self._connected = False

        if self._channel:
            self._channel.close()
            self._channel = None
            self._stub = None

        # Notify callbacks
        for callback in self._disconnect_callbacks:
            try:
                callback(reason)
            except Exception as e:
                print(f"[NODE_CLIENT] Disconnect callback error: {e}",
                      file=sys.stderr)

    def _convert_price(self, proto: events_pb2.MarketPriceEvent) -> PriceEvent:
        """Convert proto to Python type."""
        return PriceEvent(
            asset_id=proto.asset_id,
            symbol=proto.symbol,
            oracle_price=proto.oracle_price,
            mark_price=proto.mark_price,
            timestamp_ns=proto.timestamp_ns,
            block_height=proto.block_height,
        )

    def _convert_liquidation(self, proto: events_pb2.LiquidationEvent) -> LiquidationEvent:
        """Convert proto to Python type."""
        return LiquidationEvent(
            symbol=proto.symbol,
            side=proto.side,
            price=proto.price,
            size=proto.size,
            value_usd=proto.value_usd,
            liquidator_wallet=proto.liquidator_wallet,
            liquidated_wallet=proto.liquidated_wallet,
            mark_price=proto.mark_price,
            method=proto.method,
            timestamp_ms=proto.timestamp_ms,
            fill_id=proto.fill_id,
            tx_hash=proto.tx_hash,
        )

    def _convert_fill(self, proto: events_pb2.FillEvent) -> FillEvent:
        """Convert proto to Python type."""
        return FillEvent(
            symbol=proto.symbol,
            side=proto.side,
            price=proto.price,
            size=proto.size,
            value_usd=proto.value_usd,
            timestamp_ms=proto.timestamp_ms,
            block_height=proto.block_height,
            wallet=proto.wallet,
            is_liquidation=proto.is_liquidation,
            liquidated_wallet=proto.liquidated_wallet,
            mark_price=proto.mark_price,
            method=proto.method,
            fill_id=proto.fill_id,
            tx_hash=proto.tx_hash,
            dir=proto.dir,
            start_position=proto.start_position,
            closed_pnl=proto.closed_pnl,
        )

    def _convert_status(self, proto: events_pb2.SyncStatusEvent) -> SyncStatus:
        """Convert proto to Python type."""
        return SyncStatus(
            status=SyncStatusCode(proto.status),
            latest_block_height=proto.latest_block_height,
            latest_block_time_ns=proto.latest_block_time_ns,
            blocks_behind=proto.blocks_behind,
            current_session=proto.current_session,
            prices_emitted=proto.prices_emitted,
            liquidations_emitted=proto.liquidations_emitted,
            last_error=proto.last_error,
            uptime_seconds=proto.uptime_seconds,
            timestamp_ns=proto.timestamp_ns,
            schema_major=proto.schema_version.major,
            schema_minor=proto.schema_version.minor,
            schema_patch=proto.schema_version.patch,
        )

    def _run_price_stream(self):
        """Price stream thread."""
        while self._running:
            if not self._connected:
                time.sleep(self.RECONNECT_DELAY_SEC)
                if self._running and not self._connected:
                    if self._connect():
                        self._reconnect_count += 1
                continue

            try:
                request = events_pb2.StreamRequest(symbols=self._symbols)

                for proto in self._stub.StreamPrices(request):
                    if not self._running:
                        break

                    event = self._convert_price(proto)
                    self._prices_received += 1
                    self._last_price_time = time.time()

                    for callback in self._price_callbacks:
                        try:
                            callback(event)
                        except Exception as e:
                            print(f"[NODE_CLIENT] Price callback error: {e}",
                                  file=sys.stderr)

            except grpc.RpcError as e:
                if self._running:
                    print(f"[NODE_CLIENT] Price stream error: {e}", file=sys.stderr)
                    self._disconnect(str(e))

    def _run_liq_stream(self):
        """Liquidation stream thread with reconnect."""
        while self._running:
            if not self._connected:
                time.sleep(self.RECONNECT_DELAY_SEC)
                continue

            try:
                request = events_pb2.StreamRequest(symbols=self._symbols)

                for proto in self._stub.StreamLiquidations(request):
                    if not self._running:
                        break

                    event = self._convert_liquidation(proto)
                    self._liquidations_received += 1
                    self._last_liq_time = time.time()

                    for callback in self._liq_callbacks:
                        try:
                            callback(event)
                        except Exception as e:
                            print(f"[NODE_CLIENT] Liquidation callback error: {e}",
                                  file=sys.stderr)

                # Stream ended normally - server closed it
                if self._running:
                    print("[NODE_CLIENT] Liq stream ended, will retry...",
                          file=sys.stderr)
                    time.sleep(self.RECONNECT_DELAY_SEC)

            except grpc.RpcError as e:
                if self._running:
                    print(f"[NODE_CLIENT] Liq stream error: {e}",
                          file=sys.stderr)
                    time.sleep(self.RECONNECT_DELAY_SEC)
            except Exception as e:
                if self._running:
                    print(f"[NODE_CLIENT] Liq stream FATAL: {e}",
                          file=sys.stderr)
                    time.sleep(self.RECONNECT_DELAY_SEC)

    def _run_fill_stream(self):
        """Fill stream thread with reconnect."""
        while self._running:
            if not self._connected:
                time.sleep(self.RECONNECT_DELAY_SEC)
                continue

            try:
                request = events_pb2.StreamRequest(symbols=self._symbols)
                print("[NODE_CLIENT] Fill stream subscribing...", file=sys.stderr)

                for proto in self._stub.StreamFills(request):
                    if not self._running:
                        break

                    event = self._convert_fill(proto)
                    self._fills_received += 1
                    self._last_fill_time = time.time()

                    for callback in self._fill_callbacks:
                        try:
                            callback(event)
                        except Exception as e:
                            print(f"[NODE_CLIENT] Fill callback error: {e}",
                                  file=sys.stderr)

                # Stream ended normally - server closed it
                if self._running:
                    print("[NODE_CLIENT] Fill stream ended, will retry...",
                          file=sys.stderr)
                    time.sleep(self.RECONNECT_DELAY_SEC)

            except grpc.RpcError as e:
                if self._running:
                    print(f"[NODE_CLIENT] Fill stream error: {e}",
                          file=sys.stderr)
                    time.sleep(self.RECONNECT_DELAY_SEC)
            except Exception as e:
                if self._running:
                    print(f"[NODE_CLIENT] Fill stream FATAL: {e}",
                          file=sys.stderr)
                    time.sleep(self.RECONNECT_DELAY_SEC)

    def _run_status_stream(self):
        """Status stream thread."""
        while self._running:
            if not self._connected:
                time.sleep(self.RECONNECT_DELAY_SEC)
                continue

            try:
                request = events_pb2.StreamRequest()

                for proto in self._stub.StreamStatus(request):
                    if not self._running:
                        break

                    event = self._convert_status(proto)

                    for callback in self._status_callbacks:
                        try:
                            callback(event)
                        except Exception as e:
                            print(f"[NODE_CLIENT] Status callback error: {e}",
                                  file=sys.stderr)

            except grpc.RpcError as e:
                if self._running:
                    print(f"[NODE_CLIENT] Status stream error: {e}",
                          file=sys.stderr)

    def start(self) -> bool:
        """
        Start receiving events.

        Returns:
            True if connected successfully
        """
        if self._running:
            return True

        # Initial connection
        if not self._connect():
            print("[NODE_CLIENT] Initial connection failed", file=sys.stderr)
            return False

        self._running = True

        # Start stream threads
        self._price_thread = threading.Thread(
            target=self._run_price_stream,
            name="node-price-stream",
            daemon=True
        )
        self._liq_thread = threading.Thread(
            target=self._run_liq_stream,
            name="node-liq-stream",
            daemon=True
        )
        self._fill_thread = threading.Thread(
            target=self._run_fill_stream,
            name="node-fill-stream",
            daemon=True
        )
        self._status_thread = threading.Thread(
            target=self._run_status_stream,
            name="node-status-stream",
            daemon=True
        )

        self._price_thread.start()
        self._liq_thread.start()
        self._fill_thread.start()
        self._status_thread.start()

        print("[NODE_CLIENT] Started", file=sys.stderr)
        return True

    def stop(self):
        """Stop receiving events."""
        self._running = False
        self._disconnect("shutdown")

        print(f"[NODE_CLIENT] Stopped. Received {self._prices_received} prices, "
              f"{self._liquidations_received} liquidations.", file=sys.stderr)

    def get_status(self) -> Optional[SyncStatus]:
        """Get current sync status (unary call)."""
        if not self._connected or not self._stub:
            return None

        try:
            proto = self._stub.GetStatus(events_pb2.Empty())
            return self._convert_status(proto)
        except grpc.RpcError:
            return None

    @property
    def is_connected(self) -> bool:
        """True if connected to server."""
        return self._connected

    @property
    def prices_received(self) -> int:
        """Total prices received."""
        return self._prices_received

    @property
    def liquidations_received(self) -> int:
        """Total liquidations received."""
        return self._liquidations_received

    def get_metrics(self) -> dict:
        """Get client metrics."""
        return {
            'connected': self._connected,
            'address': self._address,
            'prices_received': self._prices_received,
            'liquidations_received': self._liquidations_received,
            'fills_received': self._fills_received,
            'reconnect_count': self._reconnect_count,
            'last_price_time': self._last_price_time,
            'last_liq_time': self._last_liq_time,
            'last_fill_time': self._last_fill_time,
        }
