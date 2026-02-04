"""
HL Node Adapter - Main Module.

Reads prices and liquidations from HL node files and emits canonical events.
This is the core adapter logic - no gRPC yet, just readers and output.

Usage:
    adapter = NodeAdapter()
    adapter.run()  # Prints events to stdout
"""

import json
import signal
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from checkpoint import CheckpointManager
from readers import PriceReader, LiquidationReader, FillReader


class NodeAdapter:
    """
    HL Node Adapter.

    Reads from:
    - replica_cmds (prices)
    - node_fills (liquidations)

    Outputs:
    - JSON events to stdout (one per line)
    """

    def __init__(
        self,
        data_path: Optional[Path] = None,
        focus_symbols: Optional[set] = None,
        checkpoint_path: Optional[Path] = None,
    ):
        """
        Initialize adapter.

        Args:
            data_path: Path to HL data directory
            focus_symbols: Only emit events for these symbols (None = all)
            checkpoint_path: Path to checkpoint file
        """
        self._data_path = data_path or Path.home() / "hl" / "data"
        self._focus_symbols = focus_symbols

        # Checkpoint manager
        self._checkpoint_mgr = CheckpointManager(checkpoint_path)

        # Readers
        self._price_reader = PriceReader(self._data_path, focus_symbols)
        self._liq_reader = LiquidationReader(self._data_path, focus_symbols)
        self._fill_reader = FillReader(self._data_path, focus_symbols)

        # State
        self._running = False
        self._start_time = 0.0
        self._prices_emitted = 0
        self._liquidations_emitted = 0
        self._fills_emitted = 0

        # Threads
        self._price_thread: Optional[threading.Thread] = None
        self._liq_thread: Optional[threading.Thread] = None
        self._fill_thread: Optional[threading.Thread] = None
        self._checkpoint_thread: Optional[threading.Thread] = None

        # Output lock (for thread-safe stdout)
        self._output_lock = threading.Lock()

    def _emit_event(self, event_type: str, data: dict):
        """Emit an event to stdout as JSON."""
        event = {
            'type': event_type,
            'timestamp': time.time(),
            'data': data,
        }

        with self._output_lock:
            print(json.dumps(event), flush=True)

    def _emit_price(self, event):
        """Emit a price event."""
        self._emit_event('price', {
            'asset_id': event.asset_id,
            'symbol': event.symbol,
            'oracle_price': event.oracle_price,
            'mark_price': event.mark_price,
            'timestamp_ns': event.timestamp_ns,
            'block_height': event.block_height,
        })
        self._prices_emitted += 1

    def _emit_liquidation(self, event):
        """Emit a liquidation event."""
        self._emit_event('liquidation', {
            'symbol': event.symbol,
            'side': event.side,
            'price': event.price,
            'size': event.size,
            'value_usd': event.value_usd,
            'liquidator_wallet': event.liquidator_wallet,
            'liquidated_wallet': event.liquidated_wallet,
            'mark_price': event.mark_price,
            'method': event.method,
            'timestamp_ms': event.timestamp_ms,
            'fill_id': event.fill_id,
            'tx_hash': event.tx_hash,
        })
        self._liquidations_emitted += 1

    def _emit_fill(self, event):
        """Emit a fill event (organic or liquidation)."""
        # Calculate USD value
        try:
            value_usd = str(float(event.price) * float(event.size))
        except (ValueError, TypeError):
            value_usd = '0'

        self._emit_event('fill', {
            'symbol': event.symbol,
            'side': event.side,
            'price': event.price,
            'size': event.size,
            'value_usd': value_usd,
            'timestamp_ms': event.timestamp_ms,
            'wallet': event.wallet,
            'is_liquidation': event.is_liquidation,
            'liquidated_wallet': event.liquidated_wallet,
            'mark_price': event.mark_price,
            'method': event.method,
            'fill_id': event.fill_id,
            'tx_hash': event.tx_hash,
        })
        self._fills_emitted += 1

    def _emit_status(self):
        """Emit a status event."""
        uptime = time.time() - self._start_time

        price_state = self._price_reader.get_state()
        liq_state = self._liq_reader.get_state()
        fill_state = self._fill_reader.get_state()

        self._emit_event('status', {
            'status': 'HEALTHY',
            'latest_block_height': price_state.get('block_height', 0),
            'prices_emitted': self._prices_emitted,
            'liquidations_emitted': self._liquidations_emitted,
            'fills_emitted': self._fills_emitted,
            'uptime_seconds': int(uptime),
            'price_file': price_state.get('file', ''),
            'liq_file': f"{liq_state.get('date', '')}/{liq_state.get('hour', '')}",
            'fill_file': f"{fill_state.get('date', '')}/{fill_state.get('hour', '')}",
        })

    def _run_price_reader(self):
        """Price reader thread."""
        print("[ADAPTER] Price reader starting...", file=sys.stderr)

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
            print(f"[ADAPTER] Price reader error: {e}", file=sys.stderr)

        print("[ADAPTER] Price reader stopped", file=sys.stderr)

    def _run_liq_reader(self):
        """Liquidation reader thread."""
        print("[ADAPTER] Liquidation reader starting...", file=sys.stderr)

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
            print(f"[ADAPTER] Liquidation reader error: {e}", file=sys.stderr)

        print("[ADAPTER] Liquidation reader stopped", file=sys.stderr)

    def _run_fill_reader(self):
        """Fill reader thread - streams ALL fills for absorption detection."""
        print("[ADAPTER] Fill reader starting...", file=sys.stderr)

        try:
            for event in self._fill_reader.read_fills():
                if not self._running:
                    break

                self._emit_fill(event)

                # Note: Fill reader doesn't update checkpoint separately
                # It starts from current position each time (skip_historical=True)

        except Exception as e:
            print(f"[ADAPTER] Fill reader error: {e}", file=sys.stderr)

        print("[ADAPTER] Fill reader stopped", file=sys.stderr)

    def _run_checkpoint_loop(self):
        """Checkpoint save loop."""
        while self._running:
            self._checkpoint_mgr.save()
            time.sleep(5.0)

    def _run_status_loop(self):
        """Periodic status emission."""
        while self._running:
            time.sleep(5.0)
            if self._running:
                self._emit_status()

    def run(self):
        """Run the adapter (blocking)."""
        self._running = True
        self._start_time = time.time()

        # Load checkpoint
        checkpoint = self._checkpoint_mgr.load()

        # Initialize readers from checkpoint
        print("[ADAPTER] Initializing readers...", file=sys.stderr)

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

        # Initialize fill reader (always starts from current, no historical replay)
        self._fill_reader.initialize(skip_historical=True)

        # Restore counters
        self._prices_emitted = checkpoint.prices_emitted
        self._liquidations_emitted = checkpoint.liquidations_emitted

        # Start threads
        print("[ADAPTER] Starting reader threads...", file=sys.stderr)

        self._price_thread = threading.Thread(target=self._run_price_reader, daemon=True)
        self._liq_thread = threading.Thread(target=self._run_liq_reader, daemon=True)
        self._fill_thread = threading.Thread(target=self._run_fill_reader, daemon=True)
        self._checkpoint_thread = threading.Thread(target=self._run_checkpoint_loop, daemon=True)
        status_thread = threading.Thread(target=self._run_status_loop, daemon=True)

        self._price_thread.start()
        self._liq_thread.start()
        self._fill_thread.start()
        self._checkpoint_thread.start()
        status_thread.start()

        # Emit initial status
        self._emit_status()

        print("[ADAPTER] Running. Press Ctrl+C to stop.", file=sys.stderr)

        # Wait for threads (they run forever until stopped)
        try:
            while self._running:
                time.sleep(1.0)
        except KeyboardInterrupt:
            print("\n[ADAPTER] Shutdown requested...", file=sys.stderr)

        self.stop()

    def stop(self):
        """Stop the adapter gracefully."""
        self._running = False

        # Close readers
        self._price_reader.close()
        self._liq_reader.close()
        self._fill_reader.close()

        # Save final checkpoint
        self._checkpoint_mgr.save(force=True)

        print(f"[ADAPTER] Stopped. Emitted {self._prices_emitted} prices, "
              f"{self._liquidations_emitted} liquidations, "
              f"{self._fills_emitted} fills.", file=sys.stderr)
