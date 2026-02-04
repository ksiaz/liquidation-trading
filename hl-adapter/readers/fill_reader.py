"""
Fill Reader for HL Node Adapter.

Reads all fill events from node_fills/hourly.
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
class FillEvent:
    """Normalized fill event."""
    symbol: str
    side: str                  # "B" (buy) or "A" (ask/sell)
    price: str                 # Execution price
    size: str                  # Fill size
    value_usd: str             # USD notional (price * size)
    timestamp_ms: int          # Unix timestamp in ms
    block_height: int          # Block height (0 if unknown)
    wallet: str                # Wallet that received the fill
    is_liquidation: bool       # True if liquidation
    liquidated_wallet: str     # Wallet liquidated (empty if none)
    mark_price: str            # Mark price at liquidation (empty if none)
    method: str                # "market" or "backstop" (empty if none)
    fill_id: int               # Unique fill ID
    tx_hash: str               # Transaction hash


class FillReader:
    """
    Reads fill events from node_fills.

    Usage:
        reader = FillReader()
        for event in reader.read_fills():
            print(f"{event.symbol} {event.side} @ {event.price}")
    """

    def __init__(
        self,
        data_path: Optional[Path] = None,
        focus_symbols: Optional[set] = None,
    ):
        """
        Initialize fill reader.

        Args:
            data_path: Path to HL data directory (default: ~/hl/data)
            focus_symbols: Only emit fills for these symbols (None = all)
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
        self._fills_emitted = 0
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

    def _open_file(self, date: str, hour: int, position: int = 0) -> bool:
        """Open a fill file for reading."""
        if self._file_handle:
            self._file_handle.close()

        file_path = self._fills_path / date / str(hour)
        if not file_path.exists():
            print(f"[FILL] File not found: {file_path}", file=sys.stderr)
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

        print(f"[FILL] Opened {date}/{hour} at position {self._file_position}", file=sys.stderr)
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
            print(f"[FILL] Detected newer file: {latest_date}/{latest_hour} "
                  f"(was {self._current_date}/{self._current_hour})", file=sys.stderr)
            return self._open_file(latest_date, latest_hour)

        return False

    def _parse_fill(self, line: str) -> Optional[FillEvent]:
        """
        Parse a fill line and extract FillEvent.

        Returns:
            FillEvent if parsed, None otherwise
        """
        try:
            data = json.loads(line.strip())

            if not isinstance(data, list) or len(data) < 2:
                return None

            wallet = data[0]
            fill = data[1]

            if not isinstance(fill, dict):
                return None

            # Extract fill data
            symbol = fill.get('coin', '')
            side = fill.get('side', '')  # "B" or "A"
            price = fill.get('px', '0')
            size = fill.get('sz', '0')
            timestamp_ms = int(fill.get('time', 0) or 0)
            fill_id = int(fill.get('tid', 0) or 0)
            tx_hash = fill.get('hash', '')

            # Apply focus filter
            if self._focus_symbols and symbol not in self._focus_symbols:
                return None

            # Deduplication
            if fill_id and fill_id in self._seen_fill_ids:
                return None

            if fill_id:
                self._seen_fill_ids.add(fill_id)
                if len(self._seen_fill_ids) > self._max_seen_ids:
                    to_remove = sorted(self._seen_fill_ids)[:self._max_seen_ids // 2]
                    self._seen_fill_ids -= set(to_remove)

            # Calculate USD value
            try:
                value_usd = str(float(price) * float(size))
            except (ValueError, TypeError):
                value_usd = '0'

            # Liquidation metadata
            liq_info = fill.get('liquidation')
            is_liquidation = liq_info is not None
            liquidated_wallet = liq_info.get('liquidatedUser', '') if liq_info else ''
            mark_price = liq_info.get('markPx', '') if liq_info else ''
            method = liq_info.get('method', '') if liq_info else ''

            return FillEvent(
                symbol=symbol,
                side=side,
                price=str(price),
                size=str(size),
                value_usd=value_usd,
                timestamp_ms=timestamp_ms,
                block_height=0,
                wallet=wallet,
                is_liquidation=is_liquidation,
                liquidated_wallet=liquidated_wallet,
                mark_price=str(mark_price),
                method=method,
                fill_id=fill_id,
                tx_hash=tx_hash,
            )

        except json.JSONDecodeError:
            return None
        except Exception as e:
            print(f"[FILL] Parse error: {e}", file=sys.stderr)
            return None

    def initialize(
        self,
        date: str = None,
        hour: int = None,
        position: int = 0,
        last_fill_id: int = 0,
        skip_historical: bool = True,
    ) -> bool:
        """
        Initialize reader state, optionally from checkpoint.

        Args:
            date: Date directory to resume from (YYYYMMDD)
            hour: Hour file to resume from (0-23)
            position: Byte position to resume from
            last_fill_id: Last processed fill ID for deduplication
            skip_historical: If True, start from end of file (skip catchup)

        Returns:
            True if initialized successfully
        """
        self._last_fill_id = last_fill_id

        if date and hour is not None and hour >= 0:
            if self._open_file(date, hour, position):
                return True

        latest_date = self._find_latest_date()
        if not latest_date:
            print("[FILL] No date directory found", file=sys.stderr)
            return False

        latest_hour = self._find_latest_hour(latest_date)
        if latest_hour < 0:
            print(f"[FILL] No hour file found in {latest_date}", file=sys.stderr)
            return False

        if self._open_file(latest_date, latest_hour):
            if skip_historical:
                self._file_handle.seek(0, 2)
                self._file_position = self._file_handle.tell()
                print(f"[FILL] Starting from end of file (position {self._file_position})", file=sys.stderr)
            else:
                self._file_position = 0
            return True

        return False

    def read_fills(self, poll_interval: float = 0.1) -> Iterator[FillEvent]:
        """
        Read fill events continuously.

        Yields FillEvent objects as new data arrives.
        Handles hourly file rotation automatically.

        Args:
            poll_interval: Seconds to wait when no new data
        """
        if not self._file_handle:
            if not self.initialize():
                print("[FILL] Failed to initialize", file=sys.stderr)
                return

        while True:
            line = self._file_handle.readline()

            if line:
                self._file_position = self._file_handle.tell()
                self._fills_read += 1

                event = self._parse_fill(line)

                if event:
                    self._fills_emitted += 1
                    self._last_fill_id = event.fill_id
                    yield event

            else:
                if self._check_for_new_file():
                    continue

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
            'fills_emitted': self._fills_emitted,
            'last_fill_id': self._last_fill_id,
        }

    def close(self):
        """Close file handle."""
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None
