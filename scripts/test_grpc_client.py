#!/usr/bin/env python3
"""
Simple gRPC test client to verify WSL/Windows connectivity.
Run test_grpc_server.py in WSL first, then run this on Windows.
"""

import sys
import time
from pathlib import Path

# Add protos to path
script_dir = Path(__file__).parent.parent
sys.path.insert(0, str(script_dir / 'runtime/hyperliquid/adapter_service/protos'))

import grpc
import adapter_pb2
import adapter_pb2_grpc


def test_connection(host='localhost', port=50051):
    """Test gRPC connection to adapter."""
    print("=" * 50)
    print("gRPC TEST CLIENT")
    print("=" * 50)
    print(f"Connecting to {host}:{port}...")

    channel = grpc.insecure_channel(f'{host}:{port}')
    stub = adapter_pb2_grpc.HyperliquidNodeAdapterStub(channel)

    # Test 1: GetStatus
    print("\n1. Testing GetStatus...")
    try:
        status = stub.GetStatus(adapter_pb2.Empty())
        print(f"   Connected: {status.connected}")
        print(f"   Latest block: {status.latest_block}")
        print(f"   Events emitted: {status.events_emitted}")
        print(f"   Replica file: {status.replica_file}")
        print("   GetStatus: OK")
    except grpc.RpcError as e:
        print(f"   GetStatus FAILED: {e.code()}: {e.details()}")
        return False

    # Test 2: StreamMarketPrices
    print("\n2. Testing StreamMarketPrices...")
    try:
        request = adapter_pb2.StreamRequest(
            assets=['BTC', 'ETH'],
            from_latest=True,
        )

        count = 0
        start = time.time()

        for price in stub.StreamMarketPrices(request):
            count += 1
            print(f"   {price.asset}: ${price.oracle_price:,.2f} (block {price.block_height})")

            if count >= 20:  # Limit for test
                break

        elapsed = time.time() - start
        print(f"   Received {count} events in {elapsed:.2f}s")
        print("   StreamMarketPrices: OK")

    except grpc.RpcError as e:
        print(f"   StreamMarketPrices FAILED: {e.code()}: {e.details()}")
        return False

    print("\n" + "=" * 50)
    print("ALL TESTS PASSED - gRPC connectivity works!")
    print("=" * 50)
    return True


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='localhost')
    parser.add_argument('--port', type=int, default=50051)
    args = parser.parse_args()

    success = test_connection(args.host, args.port)
    sys.exit(0 if success else 1)
