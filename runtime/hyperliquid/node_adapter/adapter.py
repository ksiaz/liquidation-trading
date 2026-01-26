"""
Hyperliquid Node Adapter

Main orchestrator that combines:
- ReplicaCmdStreamer: Efficient block streaming
- BlockActionExtractor: Action extraction
- SyncMonitor: Node health tracking
- TCP Server: Event distribution to clients

Designed to run as a service in WSL, exposing events via TCP
to Windows-based observation system.
"""

import asyncio
import json
import time
from typing import Callable, Awaitable, Dict, List, Optional, Set
from dataclasses import dataclass

from .config import NodeAdapterConfig
from .metrics import AdapterMetrics
from .replica_streamer import ReplicaCmdStreamer
from .action_extractor import BlockActionExtractor, PriceEvent, LiquidationEvent, OrderActivity
from .sync_monitor import SyncMonitor


@dataclass
class ConnectedClient:
    """Represents a connected TCP client."""
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    address: str
    connected_at: float


class HyperliquidNodeAdapter:
    """
    Production adapter from Hyperliquid node to observation system.

    Streams blocks from replica_cmds, extracts relevant actions,
    and distributes normalized events via TCP.

    Usage:
        config = NodeAdapterConfig()
        adapter = HyperliquidNodeAdapter(config)

        # Option 1: Run as standalone service with TCP server
        await adapter.start()
        # ... adapter runs until stopped
        await adapter.stop()

        # Option 2: Use callback for events
        async def on_event(event: Dict):
            print(event)

        adapter.set_event_callback(on_event)
        await adapter.start()
    """

    def __init__(self, config: Optional[NodeAdapterConfig] = None):
        """
        Initialize adapter.

        Args:
            config: Adapter configuration (uses defaults if None)
        """
        self._config = config or NodeAdapterConfig()

        # Components
        self._streamer = ReplicaCmdStreamer(
            replica_path=f"{self._config.node_data_path}/replica_cmds",
            buffer_size=self._config.block_buffer_size,
            start_from_end=True,
        )

        self._extractor = BlockActionExtractor(
            extract_orders=self._config.extract_orders,
            extract_cancels=self._config.extract_cancels,
            focus_coins=self._config.focus_coins if self._config.focus_coins else None,
        )

        self._sync_monitor = SyncMonitor(
            state_path=self._config.node_state_path,
            max_lag_warning=self._config.max_sync_lag_warning,
            max_lag_error=self._config.max_sync_lag_error,
        )

        # Metrics
        self.metrics = AdapterMetrics()

        # State
        self._running = False
        self._event_callback: Optional[Callable[[Dict], Awaitable[None]]] = None

        # TCP server
        self._server: Optional[asyncio.Server] = None
        self._clients: Set[ConnectedClient] = set()

        # Tasks
        self._tasks: List[asyncio.Task] = []

        # Latest prices (for callback context)
        self._latest_prices: Dict[str, float] = {}

    async def start(self) -> None:
        """Start the adapter."""
        if self._running:
            return

        self._running = True
        self.metrics.is_running = True
        self.metrics.start_time = time.time()

        # Start TCP server
        self._server = await asyncio.start_server(
            self._handle_client,
            self._config.tcp_host,
            self._config.tcp_port,
        )

        # Start streamer
        await self._streamer.start()

        # Start processing tasks
        self._tasks = [
            asyncio.create_task(self._process_loop()),
            asyncio.create_task(self._sync_check_loop()),
            asyncio.create_task(self._metrics_log_loop()),
        ]

        print(f"[NodeAdapter] Started on {self._config.tcp_host}:{self._config.tcp_port}")

    async def stop(self) -> None:
        """Stop the adapter."""
        self._running = False
        self.metrics.is_running = False

        # Stop streamer
        await self._streamer.stop()

        # Cancel tasks
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Close clients
        for client in list(self._clients):
            try:
                client.writer.close()
                await client.writer.wait_closed()
            except:
                pass
        self._clients.clear()

        # Close server
        if self._server:
            self._server.close()
            await self._server.wait_closed()

        print("[NodeAdapter] Stopped")

    def set_event_callback(
        self,
        callback: Callable[[Dict], Awaitable[None]]
    ) -> None:
        """
        Set callback for events.

        Callback receives normalized event dicts.
        Called in addition to TCP distribution.
        """
        self._event_callback = callback

    def get_metrics(self) -> AdapterMetrics:
        """Get current metrics."""
        # Update component metrics
        self.metrics.streamer = self._streamer.metrics
        self.metrics.extractor = self._extractor.metrics
        self.metrics.sync = self._sync_monitor.metrics
        return self.metrics

    def get_latest_prices(self) -> Dict[str, float]:
        """Get latest oracle prices."""
        return dict(self._latest_prices)

    # ==================== Internal Methods ====================

    async def _process_loop(self) -> None:
        """Main processing loop - reads blocks and extracts events."""
        blocks_since_log = 0

        async for block_json in self._streamer.stream_blocks():
            if not self._running:
                break

            try:
                # Extract actions
                price_events, liq_events, order_activities = \
                    self._extractor.extract_from_block(block_json)

                # Process price events
                for price_event in price_events:
                    event_dict = price_event.to_dict()

                    # Update latest prices
                    self._latest_prices[price_event.symbol] = price_event.oracle_price

                    # Record latency
                    self.metrics.record_latency(price_event.timestamp, time.time())

                    # Distribute
                    await self._distribute_event(event_dict)

                # Process liquidation events
                for liq_event in liq_events:
                    event_dict = liq_event.to_dict()
                    await self._distribute_event(event_dict)

                # Process order activities
                for activity in order_activities:
                    event_dict = {
                        'event_type': 'HL_ORDER_ACTIVITY',
                        'wallet': activity.wallet,
                        'coin': activity.coin,
                        'timestamp': activity.timestamp,
                        'side': activity.side,
                        'is_reduce_only': activity.is_reduce_only,
                        'size': activity.size,
                        'notional': activity.notional,
                        'exchange': 'HYPERLIQUID',
                    }
                    # Send over TCP for position refresh triggering
                    await self._distribute_event(event_dict)

                # Logging
                blocks_since_log += 1
                if self._config.log_block_interval > 0 and \
                   blocks_since_log >= self._config.log_block_interval:
                    print(f"[NodeAdapter] Processed {self._streamer.metrics.blocks_read} blocks, "
                          f"{self._extractor.metrics.price_events} prices, "
                          f"{self._extractor.metrics.liquidation_events} liquidations")
                    blocks_since_log = 0

            except Exception as e:
                self.metrics.extractor.extraction_errors += 1

    async def _distribute_event(self, event: Dict) -> None:
        """Distribute event to all clients and callback."""
        # Call callback if set
        if self._event_callback:
            try:
                await self._event_callback(event)
            except Exception:
                pass

        # Send to TCP clients
        event_json = json.dumps(event) + '\n'
        event_bytes = event_json.encode('utf-8')

        # Send to all connected clients
        disconnected = []
        for client in self._clients:
            try:
                client.writer.write(event_bytes)
                await client.writer.drain()
                self.metrics.tcp_server.events_sent += 1
                self.metrics.tcp_server.bytes_sent += len(event_bytes)
            except Exception:
                disconnected.append(client)

        # Remove disconnected clients
        for client in disconnected:
            self._clients.discard(client)
            self.metrics.tcp_server.active_connections = len(self._clients)

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle new TCP client connection."""
        addr = writer.get_extra_info('peername')
        address_str = f"{addr[0]}:{addr[1]}" if addr else "unknown"

        self.metrics.tcp_server.total_connections += 1

        # Check max clients
        if len(self._clients) >= self._config.max_clients:
            try:
                writer.write(b'{"error": "max_clients_reached"}\n')
                await writer.drain()
                writer.close()
                await writer.wait_closed()
            except:
                pass
            return

        client = ConnectedClient(
            reader=reader,
            writer=writer,
            address=address_str,
            connected_at=time.time(),
        )

        self._clients.add(client)
        self.metrics.tcp_server.active_connections = len(self._clients)

        print(f"[NodeAdapter] Client connected: {address_str}")

        # Send welcome message with current state
        try:
            welcome = {
                'event_type': 'CONNECTED',
                'adapter_version': '1.0.0',
                'sync_status': self._sync_monitor.get_status().to_dict() if self._sync_monitor.get_status() else None,
                'latest_prices_count': len(self._latest_prices),
            }
            writer.write((json.dumps(welcome) + '\n').encode())
            await writer.drain()
        except:
            pass

        # Wait for client disconnect
        try:
            while self._running:
                # Just wait for disconnect - clients don't send data
                data = await reader.read(1024)
                if not data:
                    break
                await asyncio.sleep(0.1)
        except:
            pass
        finally:
            self._clients.discard(client)
            self.metrics.tcp_server.active_connections = len(self._clients)
            print(f"[NodeAdapter] Client disconnected: {address_str}")
            try:
                writer.close()
                await writer.wait_closed()
            except:
                pass

    async def _sync_check_loop(self) -> None:
        """Periodically check node sync status."""
        while self._running:
            try:
                status = self._sync_monitor.get_status()
                if status:
                    if not status.is_synced:
                        print(f"[NodeAdapter] WARNING: Node lag {status.lag_seconds:.1f}s")
                else:
                    print("[NodeAdapter] WARNING: Cannot read sync status")

                await asyncio.sleep(10.0)  # Check every 10 seconds
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(10.0)

    async def _metrics_log_loop(self) -> None:
        """Periodically log metrics."""
        if self._config.log_metrics_interval <= 0:
            return

        while self._running:
            try:
                await asyncio.sleep(self._config.log_metrics_interval)

                metrics = self.get_metrics()
                print(f"[NodeAdapter] Metrics: {json.dumps(metrics.to_dict(), indent=2)}")

            except asyncio.CancelledError:
                break
            except Exception:
                pass


async def main():
    """Run adapter as standalone service."""
    import argparse

    parser = argparse.ArgumentParser(description='Hyperliquid Node Adapter')
    parser.add_argument('--host', default='127.0.0.1', help='TCP host')
    parser.add_argument('--port', type=int, default=8090, help='TCP port')
    parser.add_argument('--data-path', default='/root/hl/data', help='Node data path')
    parser.add_argument('--state-path', default='/root/hl/hyperliquid_data', help='Node state path')
    parser.add_argument('--log-interval', type=int, default=1000, help='Log every N blocks')
    args = parser.parse_args()

    config = NodeAdapterConfig(
        node_data_path=args.data_path,
        node_state_path=args.state_path,
        tcp_host=args.host,
        tcp_port=args.port,
        log_block_interval=args.log_interval,
    )

    adapter = HyperliquidNodeAdapter(config)

    try:
        await adapter.start()

        # Run until interrupted
        while True:
            await asyncio.sleep(1.0)

    except KeyboardInterrupt:
        print("\n[NodeAdapter] Shutting down...")
    finally:
        await adapter.stop()


if __name__ == '__main__':
    asyncio.run(main())
