"""
gRPC Server for HL Node Adapter.

Serves price, liquidation, and status events over gRPC streaming.
Multiple clients can connect simultaneously.
"""

import sys
import time
import threading
from concurrent import futures
from typing import Dict, Set, Optional
from queue import Queue, Empty

import grpc

import events_pb2
import events_pb2_grpc


# Schema version
SCHEMA_VERSION = events_pb2.SchemaVersion(major=1, minor=1, patch=0)


class EventBroadcaster:
    """
    Thread-safe broadcaster for events to multiple subscribers.

    Each subscriber gets their own queue. Events are broadcast to all.
    """

    def __init__(self, name: str, max_queue_size: int = 10000):
        self._name = name
        self._max_queue_size = max_queue_size
        self._subscribers: Dict[str, Queue] = {}
        self._lock = threading.Lock()
        self._event_count = 0

    def subscribe(self, client_id: str) -> Queue:
        """Add a subscriber and return their queue."""
        with self._lock:
            queue = Queue(maxsize=self._max_queue_size)
            self._subscribers[client_id] = queue
            print(f"[GRPC] {self._name}: client '{client_id}' subscribed "
                  f"(total: {len(self._subscribers)})", file=sys.stderr)
            return queue

    def unsubscribe(self, client_id: str):
        """Remove a subscriber."""
        with self._lock:
            if client_id in self._subscribers:
                del self._subscribers[client_id]
                print(f"[GRPC] {self._name}: client '{client_id}' unsubscribed "
                      f"(total: {len(self._subscribers)})", file=sys.stderr)

    def is_subscribed(self, client_id: str) -> bool:
        """Return True if client is still an active subscriber."""
        with self._lock:
            return client_id in self._subscribers

    def broadcast(self, event):
        """Broadcast event to all subscribers."""
        with self._lock:
            self._event_count += 1
            dead_clients = []

            for client_id, queue in self._subscribers.items():
                try:
                    queue.put_nowait(event)
                except Exception:
                    # Queue full - client too slow, drop them
                    dead_clients.append(client_id)

            # Remove slow clients
            for client_id in dead_clients:
                del self._subscribers[client_id]
                print(f"[GRPC] {self._name}: dropped slow client '{client_id}'",
                      file=sys.stderr)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    @property
    def event_count(self) -> int:
        return self._event_count


class HLNodeAdapterServicer(events_pb2_grpc.HLNodeAdapterServicer):
    """
    gRPC service implementation for HL Node Adapter.
    """

    def __init__(self):
        self._price_broadcaster = EventBroadcaster("prices")
        self._liq_broadcaster = EventBroadcaster("liquidations")
        self._fill_broadcaster = EventBroadcaster("fills")
        self._status_broadcaster = EventBroadcaster("status")

        self._start_time = time.time()
        self._latest_status: Optional[events_pb2.SyncStatusEvent] = None
        self._status_lock = threading.Lock()

        # Client tracking
        self._client_counter = 0
        self._client_lock = threading.Lock()

    def _next_client_id(self, prefix: str = "client") -> str:
        """Generate unique client ID."""
        with self._client_lock:
            self._client_counter += 1
            return f"{prefix}-{self._client_counter}"

    def _matches_filter(self, symbol: str, request: events_pb2.StreamRequest) -> bool:
        """Check if event matches request filter."""
        if not request.symbols:
            return True  # No filter = all symbols
        return symbol in request.symbols

    def Handshake(self, request, context):
        """Verify schema compatibility."""
        client_version = request.client_version

        # Check compatibility (major version must match)
        compatible = (client_version.major == SCHEMA_VERSION.major)

        if compatible:
            message = f"Compatible (server v{SCHEMA_VERSION.major}.{SCHEMA_VERSION.minor}.{SCHEMA_VERSION.patch})"
        else:
            message = (f"Incompatible: client major={client_version.major}, "
                      f"server major={SCHEMA_VERSION.major}")

        print(f"[GRPC] Handshake from '{request.client_id}': "
              f"v{client_version.major}.{client_version.minor}.{client_version.patch} "
              f"-> {message}", file=sys.stderr)

        return events_pb2.HandshakeResponse(
            server_version=SCHEMA_VERSION,
            compatible=compatible,
            message=message,
            server_uptime_seconds=int(time.time() - self._start_time),
        )

    def GetStatus(self, request, context):
        """Get current sync status (unary)."""
        with self._status_lock:
            if self._latest_status:
                return self._latest_status

        # Return default status if none available
        return events_pb2.SyncStatusEvent(
            status=events_pb2.SyncStatusEvent.UNKNOWN,
            uptime_seconds=int(time.time() - self._start_time),
            timestamp_ns=int(time.time() * 1_000_000_000),
            schema_version=SCHEMA_VERSION,
        )

    def StreamPrices(self, request, context):
        """Stream price events to client."""
        client_id = self._next_client_id("price")
        queue = self._price_broadcaster.subscribe(client_id)

        try:
            while context.is_active():
                if not self._price_broadcaster.is_subscribed(client_id):
                    print(f"[GRPC] prices: client '{client_id}' dropped, closing stream",
                          file=sys.stderr)
                    break

                try:
                    event = queue.get(timeout=1.0)

                    # Apply symbol filter
                    if self._matches_filter(event.symbol, request):
                        yield event

                except Empty:
                    continue

        finally:
            self._price_broadcaster.unsubscribe(client_id)

    def StreamLiquidations(self, request, context):
        """Stream liquidation events to client."""
        client_id = self._next_client_id("liq")
        queue = self._liq_broadcaster.subscribe(client_id)

        try:
            while context.is_active():
                if not self._liq_broadcaster.is_subscribed(client_id):
                    print(f"[GRPC] liquidations: client '{client_id}' dropped, closing stream",
                          file=sys.stderr)
                    break

                try:
                    event = queue.get(timeout=1.0)

                    # Apply symbol filter
                    if self._matches_filter(event.symbol, request):
                        yield event

                except Empty:
                    continue

        finally:
            self._liq_broadcaster.unsubscribe(client_id)

    def StreamFills(self, request, context):
        """Stream ALL fill events to client (organic + liquidation)."""
        client_id = self._next_client_id("fill")
        queue = self._fill_broadcaster.subscribe(client_id)

        try:
            while context.is_active():
                if not self._fill_broadcaster.is_subscribed(client_id):
                    print(f"[GRPC] fills: client '{client_id}' dropped, closing stream",
                          file=sys.stderr)
                    break

                try:
                    event = queue.get(timeout=1.0)

                    # Apply symbol filter
                    if self._matches_filter(event.symbol, request):
                        yield event

                except Empty:
                    continue

        finally:
            self._fill_broadcaster.unsubscribe(client_id)

    def StreamStatus(self, request, context):
        """Stream status events to client."""
        client_id = self._next_client_id("status")
        queue = self._status_broadcaster.subscribe(client_id)

        try:
            while context.is_active():
                if not self._status_broadcaster.is_subscribed(client_id):
                    print(f"[GRPC] status: client '{client_id}' dropped, closing stream",
                          file=sys.stderr)
                    break

                try:
                    event = queue.get(timeout=1.0)
                    yield event
                except Empty:
                    continue

        finally:
            self._status_broadcaster.unsubscribe(client_id)

    # Methods for adapter to push events

    def push_price(self, event: events_pb2.MarketPriceEvent):
        """Push price event to all subscribers."""
        self._price_broadcaster.broadcast(event)

    def push_liquidation(self, event: events_pb2.LiquidationEvent):
        """Push liquidation event to all subscribers."""
        self._liq_broadcaster.broadcast(event)

    def push_fill(self, event: events_pb2.FillEvent):
        """Push fill event to all subscribers."""
        self._fill_broadcaster.broadcast(event)

    def push_status(self, event: events_pb2.SyncStatusEvent):
        """Push status event to all subscribers."""
        # Add schema version
        event.schema_version.CopyFrom(SCHEMA_VERSION)

        with self._status_lock:
            self._latest_status = event

        self._status_broadcaster.broadcast(event)

    def get_metrics(self) -> dict:
        """Get server metrics."""
        return {
            'price_subscribers': self._price_broadcaster.subscriber_count,
            'liq_subscribers': self._liq_broadcaster.subscriber_count,
            'fill_subscribers': self._fill_broadcaster.subscriber_count,
            'status_subscribers': self._status_broadcaster.subscriber_count,
            'prices_broadcast': self._price_broadcaster.event_count,
            'liquidations_broadcast': self._liq_broadcaster.event_count,
            'fills_broadcast': self._fill_broadcaster.event_count,
            'status_broadcast': self._status_broadcaster.event_count,
            'uptime_seconds': int(time.time() - self._start_time),
        }


class GRPCServer:
    """
    gRPC server wrapper with lifecycle management.
    """

    def __init__(self, port: int = 50051, max_workers: int = 10):
        self._port = port
        self._max_workers = max_workers
        self._server: Optional[grpc.Server] = None
        self._servicer = HLNodeAdapterServicer()

    @property
    def servicer(self) -> HLNodeAdapterServicer:
        """Get servicer for pushing events."""
        return self._servicer

    def start(self):
        """Start the gRPC server."""
        self._server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=self._max_workers),
            options=[
                ('grpc.max_send_message_length', 50 * 1024 * 1024),
                ('grpc.max_receive_message_length', 50 * 1024 * 1024),
            ]
        )

        events_pb2_grpc.add_HLNodeAdapterServicer_to_server(
            self._servicer, self._server
        )

        self._server.add_insecure_port(f'[::]:{self._port}')
        self._server.start()

        print(f"[GRPC] Server started on port {self._port}", file=sys.stderr)

    def stop(self, grace: float = 5.0):
        """Stop the gRPC server gracefully."""
        if self._server:
            self._server.stop(grace)
            print("[GRPC] Server stopped", file=sys.stderr)

    def wait_for_termination(self):
        """Block until server terminates."""
        if self._server:
            self._server.wait_for_termination()


if __name__ == '__main__':
    # Simple test - start server and wait
    server = GRPCServer(port=50051)
    server.start()

    print("[GRPC] Server running. Press Ctrl+C to stop.", file=sys.stderr)

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop()
