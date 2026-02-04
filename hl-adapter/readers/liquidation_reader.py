"""
Liquidation Reader for HL Node Adapter.

Reads liquidation events from node_fills/hourly.
Supports:
- Hourly file rotation
- Checkpoint/restart
- Deduplication by fill ID
"""

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional, Set


@dataclass
class LiquidationEvent:
    """Normalized liquidation event."""
    symbol: str
    side: str                  # "LONG" or "SHORT"
    price: str                 # Execution price
    size: str                  # Position size
    value_usd: str             # Notional value
    liquidator_wallet: str     # Wallet that received fill
    liquidated_wallet: str     # Wallet that was liquidated
    mark_price: str            # Mark price at liquidation
    method: str                # "market" or "backstop"
    timestamp_ms: int          # Unix timestamp in ms
    fill_id: int               # Unique fill ID
    tx_hash: str               # Transaction hash


class LiquidationReader:
    """
    Reads liquidation events from node_fills.

    Usage:
        reader = LiquidationReader()
        for event in reader.read_liquidations():
            print(f"{event.symbol} {event.side} @ {event.price}")
    """

    def __init__(
        self,
        data_path: Optional[Path] = None,
        focus_symbols: Optional[set] = None,
    ):
        """
        Initialize liquidation reader.

        Args:
            data_path: Path to HL data directory (default: ~/hl/data)
            focus_symbols: Only emit liquidations for these symbols (None = all)
        """
        self._data_path = data_path or Path.home() / "hl" / "data"
        self._fills_path = self._data_path / "node_fills" / "hourly"
        self._focus_symbols = focus_symbols

        # Current state
        self._current_date: Optional[str] = None
        self._current_hour: int = -1
        self._current_file: Optional[Path] = None
        self._file_handle = None
        self._file_position: int = 0

        # Deduplication
        self._seen_fill_ids: Set[int] = set()
        self._max_seen_ids = 100000  # Limit memory usage

        # Metrics
        self._fills_read = 0
        self._liquidations_emitted = 0
        self._last_fill_id = 0

    def _find_latest_date(self) -> Optional[str]:
        """Find latest date directory."""
        if not self._fills_path.exists():
            return None

        dates = sorted(
            [d.name for d in self._fills_path.iterdir() if d.is_dir()],
            reverse=True
        )
        return dates[0] if dates else None

    def _find_latest_hour(self, date: str) -> int:
        """Find latest hour file in date directory."""
        date_path = self._fills_path / date
        if not date_path.exists():
            return -1

        hours = sorted(
            [int(f.name) for f in date_path.iterdir() if f.is_file() and f.name.isdigit()],
            reverse=True
        )
        return hours[0] if hours else -1

    def _open_file(self, date: str, hour: int, position: int = 0):
        """Open a fill file for reading."""
        if self._file_handle:
            self._file_handle.close()

        file_path = self._fills_path / date / str(hour)
        if not file_path.exists():
            print(f"[LIQ] File not found: {file_path}", file=sys.stderr)
            return False

        self._current_date = date
        self._current_hour = hour
        self._current_file = file_path
        self._file_handle = open(file_path, 'r')

        if position > 0:
            self._file_handle.seek(position)
            self._file_position = position
        else:
            self._file_position = 0

        print(f"[LIQ] Opened {date}/{hour} at position {self._file_position}", file=sys.stderr)
        return True

    def _check_for_new_file(self) -> bool:
        """Check if there's a newer file to read.

        Uses filesystem state only - no system time dependency.
        This handles clock drift between local system and HL node.
        """
        # Find latest date and hour based on what actually exists
        latest_date = self._find_latest_date()
        if not latest_date:
            return False

        latest_hour = self._find_latest_hour(latest_date)
        if latest_hour < 0:
            return False

        # Check if this is newer than what we currently have
        if latest_date != self._current_date or latest_hour != self._current_hour:
            print(f"[LIQ] Detected newer file: {latest_date}/{latest_hour} "
                  f"(was {self._current_date}/{self._current_hour})", file=sys.stderr)
            return self._open_file(latest_date, latest_hour)

        return False

    def _parse_fill(self, line: str) -> Optional[LiquidationEvent]:
        """
        Parse a fill line and extract liquidation event if present.

        Returns:
            LiquidationEvent if this is a liquidation, None otherwise
        """
        try:
            data = json.loads(line.strip())

            if not isinstance(data, list) or len(data) < 2:
                return None

            liquidator_wallet = data[0]
            fill = data[1]

            if not isinstance(fill, dict):
                return None

            # Check if this is a liquidation
            liq_info = fill.get('liquidation')
            if not liq_info:
                return None

            # Extract fill data
            symbol = fill.get('coin', '')
            fill_side = fill.get('side', '')  # "B" or "S"
            price = fill.get('px', '0')
            size = fill.get('sz', '0')
            timestamp_ms = fill.get('time', 0)
            fill_id = fill.get('tid', 0)
            tx_hash = fill.get('hash', '')

            # Apply focus filter
            if self._focus_symbols and symbol not in self._focus_symbols:
                return None

            # Deduplication
            if fill_id in self._seen_fill_ids:
                return None

            self._seen_fill_ids.add(fill_id)

            # Limit memory usage
            if len(self._seen_fill_ids) > self._max_seen_ids:
                # Remove oldest half
                to_remove = sorted(self._seen_fill_ids)[:self._max_seen_ids // 2]
                self._seen_fill_ids -= set(to_remove)

            # Determine liquidated position side
            # If fill side is "B" (buy), the liquidated position was SHORT (forced buy to close)
            # If fill side is "S" (sell), the liquidated position was LONG (forced sell to close)
            if fill_side == 'B':
                liq_side = 'SHORT'
            elif fill_side == 'S':
                liq_side = 'LONG'
            else:
                liq_side = 'UNKNOWN'

            # Calculate value
            try:
                value_usd = str(float(price) * float(size))
            except (ValueError, TypeError):
                value_usd = '0'

            # Extract liquidation details
            liquidated_wallet = liq_info.get('liquidatedUser', '')
            mark_price = liq_info.get('markPx', '')
            method = liq_info.get('method', 'market')

            return LiquidationEvent(
                symbol=symbol,
                side=liq_side,
                price=price,
                size=size,
                value_usd=value_usd,
                liquidator_wallet=liquidator_wallet,
                liquidated_wallet=liquidated_wallet,
                mark_price=mark_price,
                method=method,
                timestamp_ms=timestamp_ms,
                fill_id=fill_id,
                tx_hash=tx_hash,
            )

        except json.JSONDecodeError:
            return None
        except Exception as e:
            print(f"[LIQ] Parse error: {e}", file=sys.stderr)
            return None

    def _find_start_hour(self, date: str, latest_hour: int, lookback_hours: int = 1) -> int:
        """
        Find the earliest hour to start from for historical context.

        On fresh start (no checkpoint), always look back to ensure the system
        has liquidation history. This is critical because:
        1. Most fills are NOT liquidations (liquidation rate is ~1-5%)
        2. Current hour may have 0 liquidations but plenty of regular fills
        3. Trading system needs historical liquidations for z-scores, cascades

        Returns: hour to start from
        """
        # Always look back on fresh start
        start_hour = max(0, latest_hour - lookback_hours)

        # Find earliest existing hour in lookback window
        for h in range(start_hour, latest_hour + 1):
            hour_file = self._fills_path / date / str(h)
            if hour_file.exists():
                if h < latest_hour:
                    print(f"[LIQ] Fresh start: reading from hour {h} (lookback={lookback_hours}) "
                          f"for historical context", file=sys.stderr)
                return h

        return latest_hour

    def initialize(
        self,
        date: str = None,
        hour: int = None,
        position: int = 0,
        last_fill_id: int = 0,
        skip_historical: bool = False,
        lookback_hours: int = 1,
    ) -> bool:
        """
        Initialize reader state, optionally from checkpoint.

        Args:
            date: Date directory to resume from (YYYYMMDD)
            hour: Hour file to resume from (0-23)
            position: Byte position to resume from
            last_fill_id: Last processed fill ID for deduplication
            skip_historical: If True, start from end of file (skip catchup).
                             Default False - read from beginning with lookback.
            lookback_hours: How many hours to look back if current hour is empty.
                           Default 1 hour. Only used on fresh start (no checkpoint).

        Returns:
            True if initialized successfully
        """
        self._last_fill_id = last_fill_id

        # Use checkpoint or find latest
        if date and hour is not None and hour >= 0:
            if self._open_file(date, hour, position):
                return True

        # Find latest date and hour
        latest_date = self._find_latest_date()
        if not latest_date:
            print("[LIQ] No date directory found", file=sys.stderr)
            return False

        latest_hour = self._find_latest_hour(latest_date)
        if latest_hour < 0:
            print(f"[LIQ] No hour file found in {latest_date}", file=sys.stderr)
            return False

        if skip_historical:
            # Explicitly requested: start from end of latest file
            if self._open_file(latest_date, latest_hour):
                self._file_handle.seek(0, 2)
                self._file_position = self._file_handle.tell()
                print(f"[LIQ] Starting from end of file (position {self._file_position})", file=sys.stderr)
                return True
        else:
            # Fresh start: find best hour with lookback for historical context
            start_hour = self._find_start_hour(latest_date, latest_hour, lookback_hours)

            if self._open_file(latest_date, start_hour):
                # Always start from beginning on fresh start
                self._file_position = 0
                file_size = self._file_handle.seek(0, 2)
                self._file_handle.seek(0)
                liq_estimate = file_size // 500  # ~500 bytes per fill line
                print(f"[LIQ] Starting from beginning of {latest_date}/{start_hour} "
                      f"(~{liq_estimate} fills to process, {file_size} bytes)", file=sys.stderr)
                return True

        return False

    def read_liquidations(self, poll_interval: float = 0.1) -> Iterator[LiquidationEvent]:
        """
        Read liquidation events continuously.

        Yields LiquidationEvent objects as new data arrives.
        Handles hourly file rotation automatically.

        Args:
            poll_interval: Seconds to wait when no new data
        """
        if not self._file_handle:
            if not self.initialize():
                print("[LIQ] Failed to initialize", file=sys.stderr)
                return

        while True:
            line = self._file_handle.readline()

            if line:
                self._file_position = self._file_handle.tell()
                self._fills_read += 1

                event = self._parse_fill(line)

                if event:
                    self._liquidations_emitted += 1
                    self._last_fill_id = event.fill_id
                    yield event

            else:
                # No new data - check for file rotation
                if self._check_for_new_file():
                    continue

                # Wait for new data
                time.sleep(poll_interval)

    def get_state(self) -> dict:
        """Get current reader state for checkpointing."""
        return {
            'date': self._current_date or '',
            'hour': self._current_hour,
            'position': self._file_position,
            'last_fill_id': self._last_fill_id,
        }

    def get_metrics(self) -> dict:
        """Get reader metrics."""
        return {
            'fills_read': self._fills_read,
            'liquidations_emitted': self._liquidations_emitted,
            'last_fill_id': self._last_fill_id,
        }

    def close(self):
        """Close file handle."""
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None
