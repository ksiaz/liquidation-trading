#!/usr/bin/env python3
"""
Simple gRPC test server to verify WSL/Windows connectivity.
Run this in WSL, then connect from Windows with test_grpc_client.py
"""

import sys
import time
from pathlib import Path

# Add protos to path
script_dir = Path(__file__).parent.parent
sys.path.insert(0, str(script_dir / 'runtime/hyperliquid/adapter_service/protos'))

import grpc
from concurrent import futures
import adapter_pb2
import adapter_pb2_grpc


class TestAdapter(adapter_pb2_grpc.HyperliquidNodeAdapterServicer):
    """Simple test implementation."""

    def __init__(self):
        self.event_count = 0

    def GetStatus(self, request, context):
        """Return adapter status."""
        return adapter_pb2.AdapterStatus(
            connected=True,
            latest_block=12345678,
            latest_timestamp_ms=int(time.time() * 1000),
            events_emitted=self.event_count,
            clients_connected=1,
            replica_file='/root/hl/data/replica_cmds/test',
        )

    def StreamMarketPrices(self, request, context):
        """Stream test price events."""
        print(f"Client connected for price stream. Assets filter: {list(request.assets)}")

        # Stream 10 test events
        assets = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP']
        base_prices = [100000, 3200, 140, 600, 2.5]

        for i in range(10):
            for asset, base in zip(assets, base_prices):
                if request.assets and asset not in request.assets:
                    continue

                price = adapter_pb2.MarketPriceEvent(
                    asset=asset,
                    oracle_price=base + (i * 10),
                    mark_price=base + (i * 10) + 0.5,
                    timestamp_ms=int(time.time() * 1000),
                    block_height=12345678 + i,
                )
                self.event_count += 1
                yield price

            time.sleep(0.5)  # 500ms between batches

        print(f"Stream complete. Events sent: {self.event_count}")


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    adapter_pb2_grpc.add_HyperliquidNodeAdapterServicer_to_server(
        TestAdapter(), server
    )

    # Bind to all interfaces so Windows can connect
    server.add_insecure_port('[::]:50051')
    server.start()

    print("=" * 50)
    print("gRPC TEST SERVER")
    print("=" * 50)
    print("Listening on port 50051")
    print("Press Ctrl+C to stop")
    print()

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.stop(0)


if __name__ == '__main__':
    serve()
