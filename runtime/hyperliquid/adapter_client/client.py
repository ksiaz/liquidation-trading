"""
Hyperliquid Node Adapter gRPC Client

Connects to the adapter service and receives typed events.
Runs on Windows, connects to WSL adapter.
"""

import sys
import time
import asyncio
from pathlib import Path
from typing import AsyncIterator, Callable, Optional, Dict, List, Set
from dataclasses import dataclass

import grpc

# Add protos to path
_protos_path = Path(__file__).parent.parent / 'adapter_service/protos'
sys.path.insert(0, str(_protos_path))

import adapter_pb2
import adapter_pb2_grpc


@dataclass
class ClientMetrics:
    """Client metrics."""
    connected: bool = False
    events_received: int = 0
    price_events: int = 0
    action_events: int = 0
    reconnect_attempts: int = 0
    last_event_time: float = 0.0


class AdapterClient:
    """
    gRPC client for Hyperliquid node adapter.

    Connects to the adapter service and receives typed events.
    """

    def __init__(
        self,
        host: str = 'localhost',
        port: int = 50051,
        reconnect_delay: float = 5.0,
    ):
        """
        Initialize the client.

        Args:
            host: Adapter host
            port: Adapter port
            reconnect_delay: Seconds between reconnect attempts
        """
        self._host = host
        self._port = port
        self._reconnect_delay = reconnect_delay

        # Connection
        self._channel: Optional[grpc.aio.Channel] = None
        self._stub: Optional[adapter_pb2_grpc.HyperliquidNodeAdapterStub] = None

        # State
        self._running = False

        # Callbacks
        self.on_price: Optional[Callable[[adapter_pb2.MarketPriceEvent], None]] = None
        self.on_action: Optional[Callable[[adapter_pb2.ActionEvent], None]] = None
        self.on_connected: Optional[Callable[[], None]] = None
        self.on_disconnected: Optional[Callable[[], None]] = None

        # Metrics
        self.metrics = ClientMetrics()

        # Streaming tasks
        self._price_task: Optional[asyncio.Task] = None
        self._action_task: Optional[asyncio.Task] = None

    async def connect(self) -> bool:
        """
        Connect to adapter service.

        Returns:
            True if connected successfully
        """
        try:
            self._channel = grpc.aio.insecure_channel(f'{self._host}:{self._port}')
            self._stub = adapter_pb2_grpc.HyperliquidNodeAdapterStub(self._channel)

            # Test connection with GetStatus
            status = await self._stub.GetStatus(adapter_pb2.Empty())

            self.metrics.connected = True
            print(f"[AdapterClient] Connected to {self._host}:{self._port}")
            print(f"[AdapterClient] Adapter status: block={status.latest_block}, "
                  f"events={status.events_emitted}")

            if self.on_connected:
                self.on_connected()

            return True

        except grpc.aio.AioRpcError as e:
            print(f"[AdapterClient] Connection failed: {e.code()}: {e.details()}")
            self.metrics.connected = False
            return False

    async def disconnect(self) -> None:
        """Disconnect from adapter."""
        self._running = False

        # Cancel streaming tasks
        if self._price_task:
            self._price_task.cancel()
            try:
                await self._price_task
            except asyncio.CancelledError:
                pass

        if self._action_task:
            self._action_task.cancel()
            try:
                await self._action_task
            except asyncio.CancelledError:
                pass

        # Close channel
        if self._channel:
            await self._channel.close()

        self.metrics.connected = False

        if self.on_disconnected:
            self.on_disconnected()

        print("[AdapterClient] Disconnected")

    async def get_status(self) -> Optional[adapter_pb2.AdapterStatus]:
        """Get adapter status."""
        if not self._stub:
            return None

        try:
            return await self._stub.GetStatus(adapter_pb2.Empty())
        except grpc.aio.AioRpcError:
            return None

    async def start_streaming(
        self,
        assets: Optional[List[str]] = None,
        stream_prices: bool = True,
        stream_actions: bool = True,
    ) -> None:
        """
        Start streaming events from adapter.

        Args:
            assets: Filter by assets (None = all)
            stream_prices: Whether to stream price events
            stream_actions: Whether to stream action events
        """
        self._running = True

        if stream_prices:
            self._price_task = asyncio.create_task(
                self._stream_prices(assets)
            )

        if stream_actions:
            self._action_task = asyncio.create_task(
                self._stream_actions(assets)
            )

    async def _stream_prices(self, assets: Optional[List[str]]) -> None:
        """Stream price events."""
        request = adapter_pb2.StreamRequest(
            assets=assets or [],
            from_latest=True,
        )

        while self._running:
            try:
                async for event in self._stub.StreamMarketPrices(request):
                    if not self._running:
                        break

                    self.metrics.events_received += 1
                    self.metrics.price_events += 1
                    self.metrics.last_event_time = time.time()

                    if self.on_price:
                        self.on_price(event)

            except grpc.aio.AioRpcError as e:
                if self._running:
                    print(f"[AdapterClient] Price stream error: {e.code()}")
                    self.metrics.reconnect_attempts += 1
                    await asyncio.sleep(self._reconnect_delay)
            except asyncio.CancelledError:
                break

    async def _stream_actions(self, assets: Optional[List[str]]) -> None:
        """Stream action events."""
        request = adapter_pb2.StreamRequest(
            assets=assets or [],
            from_latest=True,
        )

        while self._running:
            try:
                async for event in self._stub.StreamActions(request):
                    if not self._running:
                        break

                    self.metrics.events_received += 1
                    self.metrics.action_events += 1
                    self.metrics.last_event_time = time.time()

                    if self.on_action:
                        self.on_action(event)

            except grpc.aio.AioRpcError as e:
                if self._running:
                    print(f"[AdapterClient] Action stream error: {e.code()}")
                    self.metrics.reconnect_attempts += 1
                    await asyncio.sleep(self._reconnect_delay)
            except asyncio.CancelledError:
                break


class ObservationBridge:
    """
    Bridge between adapter client and ObservationSystem.

    Converts gRPC events to observation system format.
    """

    def __init__(self, observation_system, client: AdapterClient):
        """
        Initialize bridge.

        Args:
            observation_system: ObservationSystem instance
            client: AdapterClient instance
        """
        self._obs = observation_system
        self._client = client

        # Wire up callbacks
        self._client.on_price = self._handle_price
        self._client.on_action = self._handle_action

    def _handle_price(self, event: adapter_pb2.MarketPriceEvent) -> None:
        """Handle price event - feed to M1.

        Note: Uses time.time() for governance freshness check to avoid
        dropping data due to node/Binance time domain mismatch.
        """
        try:
            # Use wall clock for governance freshness check
            now = time.time()
            self._obs.ingest_observation(
                timestamp=now,  # Wall clock for governance validation
                symbol=event.asset,
                event_type='HL_PRICE',
                payload={
                    'oracle_price': event.oracle_price,
                    'mark_price': event.mark_price if event.mark_price else None,
                    'block_height': event.block_height,
                    'exchange': 'HYPERLIQUID',
                    'timestamp': event.timestamp_ms / 1000.0,  # Original timestamp for data accuracy
                },
            )
        except Exception as e:
            print(f"[ObservationBridge] Error handling price: {e}")

    def _handle_action(self, event: adapter_pb2.ActionEvent) -> None:
        """Handle action event - feed to M1 if relevant.

        Note: Uses time.time() for governance freshness check to avoid
        dropping data due to node/Binance time domain mismatch.
        """
        try:
            # Only feed liquidations to M1
            if event.is_liquidation:
                # Use wall clock for governance freshness check
                now = time.time()
                self._obs.ingest_observation(
                    timestamp=now,  # Wall clock for governance validation
                    symbol=event.asset,
                    event_type='HL_LIQUIDATION',
                    payload={
                        'wallet': event.wallet,
                        'side': 'LONG' if event.side == adapter_pb2.SIDE_SELL else 'SHORT',
                        'size': event.size,
                        'price': event.price,
                        'value': event.size * event.price,
                        'block_height': event.block_height,
                        'exchange': 'HYPERLIQUID',
                        'timestamp': event.timestamp_ms / 1000.0,  # Original timestamp for data accuracy
                    },
                )
        except Exception as e:
            print(f"[ObservationBridge] Error handling action: {e}")
