#!/usr/bin/env python3
"""
HL Node Adapter Server.

Combined adapter that:
1. Reads node data (prices, liquidations)
2. Serves events over gRPC streaming

Usage:
    python server.py [--port PORT] [--data-path PATH]
"""

import argparse
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import events_pb2
from checkpoint import CheckpointManager
from grpc_server import GRPCServer, SCHEMA_VERSION
from readers import PriceReader, LiquidationReader, FillReader


class AdapterServer:
    """
    Combined adapter and gRPC server.

    Reads from node files and broadcasts events to gRPC clients.
    """

    def __init__(
        self,
        data_path: Optional[Path] = None,
        grpc_port: int = 50051,
        checkpoint_path: Optional[Path] = None,
    ):
        self._data_path = data_path or Path.home() / "hl" / "data"
        self._grpc_port = grpc_port

        # Checkpoint manager
        self._checkpoint_mgr = CheckpointManager(checkpoint_path)

        # File readers
        self._price_reader = PriceReader(self._data_path)
        self._liq_reader = LiquidationReader(self._data_path)
        self._fill_reader = FillReader(self._data_path)

        # gRPC server
        self._grpc_server = GRPCServer(port=grpc_port)

        # State
        self._running = False
        self._start_time = 0.0
        self._prices_emitted = 0
        self._liquidations_emitted = 0
        self._fills_emitted = 0
        self._last_block_height = 0
        self._last_block_time_ns = 0

        # Threads
        self._price_thread: Optional[threading.Thread] = None
        self._liq_thread: Optional[threading.Thread] = None
        self._fill_thread: Optional[threading.Thread] = None
        self._status_thread: Optional[threading.Thread] = None
        self._checkpoint_thread: Optional[threading.Thread] = None

    def _emit_price(self, event):
        """Convert price event to proto and broadcast."""
        proto_event = events_pb2.MarketPriceEvent(
            asset_id=event.asset_id,
            symbol=event.symbol,
            oracle_price=event.oracle_price,
            mark_price=event.mark_price or "",
            timestamp_ns=event.timestamp_ns,
            block_height=event.block_height,
        )

        self._grpc_server.servicer.push_price(proto_event)
        self._prices_emitted += 1
        self._last_block_height = max(self._last_block_height, event.block_height)
        self._last_block_time_ns = event.timestamp_ns

    def _emit_liquidation(self, event):
        """Convert liquidation event to proto and broadcast."""
        proto_event = events_pb2.LiquidationEvent(
            symbol=event.symbol,
            side=event.side,
            price=event.price,
            size=event.size,
            value_usd=event.value_usd,
            liquidator_wallet=event.liquidator_wallet,
            liquidated_wallet=event.liquidated_wallet,
            mark_price=event.mark_price,
            method=event.method,
            timestamp_ms=event.timestamp_ms,
            fill_id=event.fill_id,
            tx_hash=event.tx_hash,
        )

        self._grpc_server.servicer.push_liquidation(proto_event)
        self._liquidations_emitted += 1

    def _emit_fill(self, event):
        """Convert fill event to proto and broadcast."""
        proto_event = events_pb2.FillEvent(
            symbol=event.symbol,
            side=event.side,
            price=event.price,
            size=event.size,
            value_usd=event.value_usd,
            timestamp_ms=event.timestamp_ms,
            block_height=event.block_height,
            wallet=event.wallet,
            is_liquidation=event.is_liquidation,
            liquidated_wallet=event.liquidated_wallet,
            method=event.method,
            mark_price=event.mark_price,
            fill_id=event.fill_id,
            tx_hash=event.tx_hash,
        )

        self._grpc_server.servicer.push_fill(proto_event)
        self._fills_emitted += 1

    def _emit_status(self):
        """Emit current status to subscribers."""
        uptime = int(time.time() - self._start_time)

        # Determine status
        price_state = self._price_reader.get_state()
        time_since_block = time.time() - (self._last_block_time_ns / 1_000_000_000)

        if self._last_block_height == 0:
            status = events_pb2.SyncStatusEvent.UNKNOWN
        elif time_since_block > 30:
            status = events_pb2.SyncStatusEvent.STALE
        elif time_since_block > 5:
            status = events_pb2.SyncStatusEvent.LAGGING
        else:
            status = events_pb2.SyncStatusEvent.HEALTHY

        proto_event = events_pb2.SyncStatusEvent(
            status=status,
            latest_block_height=self._last_block_height,
            latest_block_time_ns=self._last_block_time_ns,
            blocks_behind=0,  # TODO: calculate from expected block rate
            current_session=price_state.get('session', ''),
            prices_emitted=self._prices_emitted,
            liquidations_emitted=self._liquidations_emitted,
            last_error="",
            uptime_seconds=uptime,
            timestamp_ns=int(time.time() * 1_000_000_000),
        )

        self._grpc_server.servicer.push_status(proto_event)

    def _run_price_reader(self):
        """Price reader thread."""
        print("[SERVER] Price reader starting...", file=sys.stderr)

        try:
            for event in self._price_reader.read_prices():
                if not self._running:
                    break

                self._emit_price(event)

                # Update checkpoint
                state = self._price_reader.get_state()
                self._checkpoint_mgr.update_price_state(
                    session=state['session'],
                    date=state['date'],
                    file=state['file'],
                    position=state['position'],
                    block_height=state['block_height'],
                )
                self._checkpoint_mgr.increment_prices()

        except Exception as e:
            print(f"[SERVER] Price reader error: {e}", file=sys.stderr)

        print("[SERVER] Price reader stopped", file=sys.stderr)

    def _run_liq_reader(self):
        """Liquidation reader thread."""
        print("[SERVER] Liquidation reader starting...", file=sys.stderr)

        try:
            for event in self._liq_reader.read_liquidations():
                if not self._running:
                    break

                self._emit_liquidation(event)

                # Update checkpoint
                state = self._liq_reader.get_state()
                self._checkpoint_mgr.update_liq_state(
                    date=state['date'],
                    hour=state['hour'],
                    position=state['position'],
                    fill_id=state['last_fill_id'],
                )
                self._checkpoint_mgr.increment_liquidations()

        except Exception as e:
            print(f"[SERVER] Liquidation reader error: {e}", file=sys.stderr)

        print("[SERVER] Liquidation reader stopped", file=sys.stderr)

    def _run_fill_reader(self):
        """Fill reader thread."""
        print("[SERVER] Fill reader starting...", file=sys.stderr)

        try:
            for event in self._fill_reader.read_fills():
                if not self._running:
                    break

                self._emit_fill(event)

        except Exception as e:
            print(f"[SERVER] Fill reader error: {e}", file=sys.stderr)

        print("[SERVER] Fill reader stopped", file=sys.stderr)

    def _run_status_loop(self):
        """Periodic status emission."""
        while self._running:
            time.sleep(5.0)
            if self._running:
                self._emit_status()

    def _run_checkpoint_loop(self):
        """Checkpoint save loop."""
        while self._running:
            self._checkpoint_mgr.save()
            time.sleep(5.0)

    def run(self):
        """Run the server (blocking)."""
        self._running = True
        self._start_time = time.time()

        # Load checkpoint
        checkpoint = self._checkpoint_mgr.load()

        # Initialize readers from checkpoint
        print("[SERVER] Initializing readers...", file=sys.stderr)

        self._price_reader.initialize(
            session=checkpoint.price_session or None,
            date=checkpoint.price_date or None,
            file=checkpoint.price_file or None,
            position=checkpoint.price_file_position,
        )

        self._liq_reader.initialize(
            date=checkpoint.liq_date or None,
            hour=checkpoint.liq_hour if checkpoint.liq_hour >= 0 else None,
            position=checkpoint.liq_file_position,
            last_fill_id=checkpoint.last_liq_fill_id,
        )

        # Restore counters
        self._prices_emitted = checkpoint.prices_emitted
        self._liquidations_emitted = checkpoint.liquidations_emitted
        self._last_block_height = checkpoint.last_block_height

        # Start gRPC server
        print(f"[SERVER] Starting gRPC server on port {self._grpc_port}...", file=sys.stderr)
        self._grpc_server.start()

        # Wait for at least one liquidation subscriber before starting historical replay
        # This ensures paper trade doesn't miss the replay events
        print("[SERVER] Waiting for liquidation subscriber before starting historical replay...",
              file=sys.stderr)
        wait_start = time.time()
        max_wait = 30.0  # Maximum wait time
        while self._running and (time.time() - wait_start) < max_wait:
            metrics = self._grpc_server.servicer.get_metrics()
            if metrics['liq_subscribers'] > 0:
                print(f"[SERVER] Liquidation subscriber connected. Starting replay.",
                      file=sys.stderr)
                break
            time.sleep(0.5)
        else:
            if self._running:
                print(f"[SERVER] No subscriber after {max_wait}s. Starting anyway.",
                      file=sys.stderr)

        # Start reader threads
        print("[SERVER] Starting reader threads...", file=sys.stderr)

        self._price_thread = threading.Thread(target=self._run_price_reader, daemon=True)
        self._liq_thread = threading.Thread(target=self._run_liq_reader, daemon=True)
        self._fill_thread = threading.Thread(target=self._run_fill_reader, daemon=True)
        self._status_thread = threading.Thread(target=self._run_status_loop, daemon=True)
        self._checkpoint_thread = threading.Thread(target=self._run_checkpoint_loop, daemon=True)

        self._price_thread.start()
        self._liq_thread.start()
        self._fill_thread.start()
        self._status_thread.start()
        self._checkpoint_thread.start()

        # Emit initial status
        self._emit_status()

        print(f"[SERVER] Running. gRPC port: {self._grpc_port}. Press Ctrl+C to stop.",
              file=sys.stderr)

        # Wait for termination
        try:
            while self._running:
                time.sleep(1.0)

                # Log metrics periodically
                metrics = self._grpc_server.servicer.get_metrics()
                if (metrics['price_subscribers'] > 0 or
                        metrics['liq_subscribers'] > 0 or
                        metrics['fill_subscribers'] > 0):
                    print(f"[SERVER] Subscribers: prices={metrics['price_subscribers']}, "
                          f"liqs={metrics['liq_subscribers']}, "
                          f"fills={metrics['fill_subscribers']} | "
                          f"Broadcast: prices={metrics['prices_broadcast']}, "
                          f"liqs={metrics['liquidations_broadcast']}, "
                          f"fills={metrics['fills_broadcast']}", file=sys.stderr)

        except KeyboardInterrupt:
            print("\n[SERVER] Shutdown requested...", file=sys.stderr)

        self.stop()

    def stop(self):
        """Stop the server gracefully."""
        self._running = False

        # Stop gRPC server
        self._grpc_server.stop()

        # Close readers
        self._price_reader.close()
        self._liq_reader.close()
        self._fill_reader.close()

        # Save final checkpoint
        self._checkpoint_mgr.save(force=True)

        print(f"[SERVER] Stopped. Emitted {self._prices_emitted} prices, "
              f"{self._liquidations_emitted} liquidations, "
              f"{self._fills_emitted} fills.", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description='HL Node Adapter gRPC Server'
    )

    parser.add_argument(
        '--port',
        type=int,
        default=50051,
        help='gRPC server port (default: 50051)'
    )

    parser.add_argument(
        '--data-path',
        type=Path,
        default=None,
        help='Path to HL data directory (default: ~/hl/data)'
    )

    parser.add_argument(
        '--checkpoint',
        type=Path,
        default=None,
        help='Path to checkpoint file'
    )

    args = parser.parse_args()

    # Create and run server
    server = AdapterServer(
        data_path=args.data_path,
        grpc_port=args.port,
        checkpoint_path=args.checkpoint,
    )

    # Setup signal handlers
    def signal_handler(signum, frame):
        print(f"\n[MAIN] Received signal {signum}", file=sys.stderr)
        server.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    server.run()


if __name__ == '__main__':
    main()
