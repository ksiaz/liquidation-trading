"""
Hyperliquid Node Adapter gRPC Server

Main server that:
- Reads blocks from replica_cmds
- Normalizes to typed events
- Streams to connected clients via gRPC
"""

import asyncio
import sys
import time
from pathlib import Path
from concurrent import futures
from typing import Dict, Set, Optional
from collections import deque

import grpc

# Add protos to path
_protos_path = Path(__file__).parent / 'protos'
sys.path.insert(0, str(_protos_path))

import adapter_pb2
import adapter_pb2_grpc

from .block_reader import BlockReader
from .normalizer import EventNormalizer, NormalizedPriceEvent, NormalizedActionEvent


class HyperliquidNodeAdapterServicer(adapter_pb2_grpc.HyperliquidNodeAdapterServicer):
    """
    gRPC servicer for Hyperliquid node adapter.

    Streams normalized events to connected clients.
    """

    def __init__(
        self,
        replica_path: str = '/root/hl/data/replica_cmds',
    ):
        """Initialize the servicer."""
        self._replica_path = replica_path
        self._block_reader: Optional[BlockReader] = None
        self._normalizer = EventNormalizer()

        # Event buffers for clients
        self._price_buffer: deque = deque(maxlen=10000)
        self._action_buffer: deque = deque(maxlen=10000)

        # Client tracking
        self._price_clients: Set = set()
        self._action_clients: Set = set()

        # State
        self._running = False
        self._latest_block = 0
        self._latest_timestamp_ms = 0
        self._events_emitted = 0

        # Processing task
        self._process_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the adapter."""
        print("[Adapter] Starting...")

        # Start block reader
        self._block_reader = BlockReader(
            replica_path=self._replica_path,
            start_from_end=True,
        )
        await self._block_reader.start()

        self._running = True

        # Start processing loop
        self._process_task = asyncio.create_task(self._process_loop())

        print("[Adapter] Running")

    async def stop(self) -> None:
        """Stop the adapter."""
        print("[Adapter] Stopping...")
        self._running = False

        if self._process_task:
            self._process_task.cancel()
            try:
                await self._process_task
            except asyncio.CancelledError:
                pass

        if self._block_reader:
            await self._block_reader.stop()

        print("[Adapter] Stopped")

    async def _process_loop(self) -> None:
        """Main processing loop - reads blocks and normalizes events."""
        async for block in self._block_reader.stream_blocks():
            if not self._running:
                break

            # Normalize block
            price_events, action_events = self._normalizer.normalize_block(block)

            # Update state
            if price_events:
                self._latest_timestamp_ms = price_events[0].timestamp_ms
                self._latest_block = price_events[0].block_height

            # Buffer events
            for pe in price_events:
                self._price_buffer.append(pe)
                self._events_emitted += 1

            for ae in action_events:
                self._action_buffer.append(ae)
                self._events_emitted += 1

    def _price_to_proto(self, event: NormalizedPriceEvent) -> adapter_pb2.MarketPriceEvent:
        """Convert normalized price to protobuf."""
        return adapter_pb2.MarketPriceEvent(
            asset=event.asset,
            oracle_price=event.oracle_price,
            mark_price=event.mark_price if event.mark_price else 0.0,
            timestamp_ms=event.timestamp_ms,
            block_height=event.block_height,
        )

    def _action_to_proto(self, event: NormalizedActionEvent) -> adapter_pb2.ActionEvent:
        """Convert normalized action to protobuf."""
        # Map action type
        action_type = adapter_pb2.ACTION_TYPE_ORDER
        if event.action_type == 'CANCEL':
            action_type = adapter_pb2.ACTION_TYPE_CANCEL
        elif event.action_type == 'FORCE_ORDER':
            action_type = adapter_pb2.ACTION_TYPE_FORCE_ORDER

        # Map side
        side = adapter_pb2.SIDE_BUY if event.side == 'BUY' else adapter_pb2.SIDE_SELL

        # Map order type
        order_type = adapter_pb2.ORDER_TYPE_LIMIT
        if event.order_type == 'MARKET':
            order_type = adapter_pb2.ORDER_TYPE_MARKET
        elif event.order_type == 'TRIGGER':
            order_type = adapter_pb2.ORDER_TYPE_TRIGGER

        return adapter_pb2.ActionEvent(
            block_height=event.block_height,
            timestamp_ms=event.timestamp_ms,
            wallet=event.wallet,
            action_type=action_type,
            asset=event.asset,
            side=side,
            price=event.price,
            size=event.size,
            order_type=order_type,
            is_liquidation=event.is_liquidation,
            is_reduce_only=event.is_reduce_only,
            cloid=event.cloid or '',
        )

    # ==================== gRPC Methods ====================

    def GetStatus(self, request, context):
        """Return adapter status."""
        return adapter_pb2.AdapterStatus(
            connected=self._running,
            latest_block=self._latest_block,
            latest_timestamp_ms=self._latest_timestamp_ms,
            events_emitted=self._events_emitted,
            clients_connected=len(self._price_clients) + len(self._action_clients),
            replica_file=self._block_reader.metrics.current_file if self._block_reader else '',
        )

    def StreamMarketPrices(self, request, context):
        """Stream market price events."""
        client_id = id(context)
        self._price_clients.add(client_id)
        print(f"[Adapter] Price client connected: {client_id}")

        # Asset filter
        asset_filter = set(request.assets) if request.assets else None

        # Track position in buffer
        seen_count = 0

        try:
            while self._running and context.is_active():
                # Send new events from buffer
                buffer_list = list(self._price_buffer)

                for event in buffer_list[seen_count:]:
                    # Apply filter
                    if asset_filter and event.asset not in asset_filter:
                        continue

                    yield self._price_to_proto(event)

                seen_count = len(buffer_list)
                time.sleep(0.01)  # 10ms check interval

        finally:
            self._price_clients.discard(client_id)
            print(f"[Adapter] Price client disconnected: {client_id}")

    def StreamActions(self, request, context):
        """Stream action events."""
        client_id = id(context)
        self._action_clients.add(client_id)
        print(f"[Adapter] Action client connected: {client_id}")

        # Asset filter
        asset_filter = set(request.assets) if request.assets else None

        # Track position in buffer
        seen_count = 0

        try:
            while self._running and context.is_active():
                # Send new events from buffer
                buffer_list = list(self._action_buffer)

                for event in buffer_list[seen_count:]:
                    # Apply filter
                    if asset_filter and event.asset not in asset_filter:
                        continue

                    yield self._action_to_proto(event)

                seen_count = len(buffer_list)
                time.sleep(0.01)  # 10ms check interval

        finally:
            self._action_clients.discard(client_id)
            print(f"[Adapter] Action client disconnected: {client_id}")

    def StreamPositions(self, request, context):
        """Stream position state events."""
        # TODO: Implement when state reader is added
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Position streaming not yet implemented')
        return


async def serve(
    host: str = '0.0.0.0',
    port: int = 50051,
    replica_path: str = '/root/hl/data/replica_cmds',
):
    """Run the gRPC server."""
    # Create servicer
    servicer = HyperliquidNodeAdapterServicer(replica_path=replica_path)

    # Create server
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
    adapter_pb2_grpc.add_HyperliquidNodeAdapterServicer_to_server(servicer, server)
    server.add_insecure_port(f'{host}:{port}')

    print("=" * 60)
    print("HYPERLIQUID NODE ADAPTER SERVICE")
    print("=" * 60)
    print(f"gRPC server: {host}:{port}")
    print(f"Replica path: {replica_path}")
    print()

    # Start server and adapter
    await server.start()
    await servicer.start()

    print("Press Ctrl+C to stop")
    print("-" * 60)

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        await servicer.stop()
        await server.stop(0)


def main():
    """Entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Hyperliquid Node Adapter Service')
    parser.add_argument('--host', default='0.0.0.0', help='gRPC host')
    parser.add_argument('--port', type=int, default=50051, help='gRPC port')
    parser.add_argument(
        '--replica-path',
        default='/root/hl/data/replica_cmds',
        help='Path to replica_cmds directory'
    )

    args = parser.parse_args()

    asyncio.run(serve(
        host=args.host,
        port=args.port,
        replica_path=args.replica_path,
    ))


if __name__ == '__main__':
    main()
