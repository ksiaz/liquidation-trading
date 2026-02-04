#!/usr/bin/env python3
"""
Test client for HL Node Adapter gRPC server.

Usage:
    python test_client.py [--host HOST] [--port PORT] [--stream-count N]
"""

import argparse
import grpc
import time

import events_pb2
import events_pb2_grpc


def test_handshake(stub):
    """Test handshake RPC."""
    print("=== Handshake ===")
    response = stub.Handshake(events_pb2.HandshakeRequest(
        client_version=events_pb2.SchemaVersion(major=1, minor=0, patch=0),
        client_id='test-client'
    ))
    print(f"Compatible: {response.compatible}")
    print(f"Message: {response.message}")
    print(f"Server uptime: {response.server_uptime_seconds}s")
    return response.compatible


def test_status(stub):
    """Test GetStatus RPC."""
    print("\n=== Status ===")
    status = stub.GetStatus(events_pb2.Empty())
    status_name = events_pb2.SyncStatusEvent.Status.Name(status.status)
    print(f"Status: {status_name}")
    print(f"Block height: {status.latest_block_height}")
    print(f"Prices emitted: {status.prices_emitted}")
    print(f"Liquidations emitted: {status.liquidations_emitted}")
    print(f"Schema: {status.schema_version.major}.{status.schema_version.minor}.{status.schema_version.patch}")
    return status


def test_price_stream(stub, count=5, symbols=None):
    """Test StreamPrices RPC."""
    print(f"\n=== Price Stream ({count} events) ===")
    request = events_pb2.StreamRequest(symbols=symbols or [])

    received = 0
    start = time.time()

    for price in stub.StreamPrices(request):
        elapsed = time.time() - start
        print(f"[{elapsed:.1f}s] {price.symbol}: oracle={price.oracle_price}, "
              f"mark={price.mark_price}, block={price.block_height}")
        received += 1
        if received >= count:
            break

    print(f"Received {received} price events")
    return received


def test_liquidation_stream(stub, count=3, symbols=None):
    """Test StreamLiquidations RPC."""
    print(f"\n=== Liquidation Stream ({count} events) ===")
    request = events_pb2.StreamRequest(symbols=symbols or [])

    received = 0
    start = time.time()

    for liq in stub.StreamLiquidations(request):
        elapsed = time.time() - start
        print(f"[{elapsed:.1f}s] {liq.symbol} {liq.side}: size={liq.size} @ {liq.price} "
              f"(${float(liq.value_usd):,.0f})")
        received += 1
        if received >= count:
            break

    print(f"Received {received} liquidation events")
    return received


def main():
    parser = argparse.ArgumentParser(description='Test HL Node Adapter gRPC server')
    parser.add_argument('--host', default='localhost', help='Server host')
    parser.add_argument('--port', type=int, default=50051, help='Server port')
    parser.add_argument('--stream-count', type=int, default=5, help='Events to receive per stream')
    parser.add_argument('--symbols', nargs='*', help='Filter by symbols')
    parser.add_argument('--no-stream', action='store_true', help='Skip streaming tests')

    args = parser.parse_args()

    # Connect
    address = f"{args.host}:{args.port}"
    print(f"Connecting to {address}...")

    channel = grpc.insecure_channel(address)
    stub = events_pb2_grpc.HLNodeAdapterStub(channel)

    try:
        # Test handshake
        if not test_handshake(stub):
            print("ERROR: Incompatible version!")
            return 1

        # Test status
        test_status(stub)

        # Test streaming (if not disabled)
        if not args.no_stream:
            test_price_stream(stub, args.stream_count, args.symbols)
            test_liquidation_stream(stub, min(3, args.stream_count), args.symbols)

        print("\n=== All tests passed ===")
        return 0

    except grpc.RpcError as e:
        print(f"ERROR: gRPC error: {e}")
        return 1

    finally:
        channel.close()


if __name__ == '__main__':
    exit(main())
