"""
Price Reader for HL Node Adapter.

Reads SetGlobalAction events from replica_cmds to extract oracle prices.
Supports:
- Session discovery (finding latest active session)
- File tailing (reading new data as it's written)
- Checkpoint/restart (resume from last position)
"""

import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional, List, Tuple

from asset_mapping import get_symbol, PRIORITY_COINS


@dataclass
class PriceEvent:
    """Normalized price event."""
    asset_id: int
    symbol: str
    oracle_price: str          # String to preserve precision
    mark_price: Optional[str]  # May be None
    timestamp_ns: int          # Block timestamp in nanoseconds
    block_height: int


class PriceReader:
    """
    Reads price events from replica_cmds.

    Usage:
        reader = PriceReader()
        for event in reader.read_prices():
            print(f"{event.symbol}: {event.oracle_price}")
    """

    def __init__(
        self,
        data_path: Optional[Path] = None,
        focus_symbols: Optional[set] = None,
    ):
        """
        Initialize price reader.

        Args:
            data_path: Path to HL data directory (default: ~/hl/data)
            focus_symbols: Only emit prices for these symbols (None = all)
        """
        self._data_path = data_path or Path.home() / "hl" / "data"
        self._replica_path = self._data_path / "replica_cmds"
        self._focus_symbols = focus_symbols

        # Current state
        self._current_session: Optional[Path] = None
        self._current_date: Optional[Path] = None
        self._current_file: Optional[Path] = None
        self._file_handle = None
        self._file_position: int = 0

        # Metrics
        self._blocks_read = 0
        self._prices_emitted = 0
        self._last_block_height = 0

    def _find_latest_session(self) -> Optional[Path]:
        """Find the latest (most recent) session directory."""
        if not self._replica_path.exists():
            return None

        sessions = sorted(
            [d for d in self._replica_path.iterdir() if d.is_dir()],
            key=lambda x: x.name,
            reverse=True
        )

        return sessions[0] if sessions else None

    def _find_latest_date(self, session: Path) -> Optional[Path]:
        """Find the latest date directory in a session."""
        dates = sorted(
            [d for d in session.iterdir() if d.is_dir()],
            key=lambda x: x.name,
            reverse=True
        )
        return dates[0] if dates else None

    def _find_latest_file(self, date_dir: Path) -> Optional[Path]:
        """Find the latest block file in a date directory."""
        files = sorted(
            [f for f in date_dir.iterdir() if f.is_file()],
            key=lambda x: int(x.name) if x.name.isdigit() else 0,
            reverse=True
        )
        return files[0] if files else None

    def _open_file(self, file_path: Path, position: int = 0):
        """Open a file for reading, optionally seeking to position."""
        if self._file_handle:
            self._file_handle.close()

        self._current_file = file_path
        self._file_handle = open(file_path, 'r')

        if position > 0:
            self._file_handle.seek(position)
            self._file_position = position
        else:
            self._file_position = 0

        print(f"[PRICE] Opened {file_path.name} at position {self._file_position}", file=sys.stderr)

    def _check_for_new_file(self) -> bool:
        """Check if there's a newer file to read."""
        if not self._current_date:
            return False

        latest = self._find_latest_file(self._current_date)
        if latest and latest != self._current_file:
            self._open_file(latest)
            return True

        # Check for new date directory within current session
        if self._current_session:
            latest_date = self._find_latest_date(self._current_session)
            if latest_date and latest_date != self._current_date:
                self._current_date = latest_date
                latest_file = self._find_latest_file(latest_date)
                if latest_file:
                    self._open_file(latest_file)
                    return True

        # Check for new session (HL node restart creates new session)
        latest_session = self._find_latest_session()
        if latest_session and latest_session != self._current_session:
            print(f"[PRICE] New session detected: {latest_session.name}", file=sys.stderr)
            self._current_session = latest_session
            self._current_date = self._find_latest_date(latest_session)
            if self._current_date:
                latest_file = self._find_latest_file(self._current_date)
                if latest_file:
                    self._open_file(latest_file)
                    return True

        return False

    def _parse_block(self, line: str) -> Tuple[int, int, List[PriceEvent]]:
        """
        Parse a block line and extract price events.

        Returns:
            (block_height, timestamp_ns, list of PriceEvents)
        """
        events = []

        try:
            block = json.loads(line)
            abci = block.get('abci_block', {})

            # Get block metadata
            block_time_str = abci.get('time', '')
            block_height = abci.get('round', 0)

            # Parse timestamp
            try:
                dt = datetime.fromisoformat(block_time_str.replace('Z', '+00:00'))
                timestamp_ns = int(dt.timestamp() * 1_000_000_000)
            except (ValueError, AttributeError):
                timestamp_ns = int(time.time() * 1_000_000_000)

            # Look for SetGlobalAction
            for wallet, bundle in abci.get('signed_action_bundles', []):
                for sa in bundle.get('signed_actions', []):
                    action = sa.get('action', {})

                    if action.get('type') == 'SetGlobalAction':
                        pxs = action.get('pxs', [])

                        for asset_id, price_pair in enumerate(pxs):
                            if not isinstance(price_pair, list) or len(price_pair) < 2:
                                continue

                            oracle_str = price_pair[0]
                            mark_str = price_pair[1]

                            # Skip if no oracle price
                            if oracle_str is None:
                                continue

                            symbol = get_symbol(asset_id)

                            # Apply focus filter
                            if self._focus_symbols and symbol not in self._focus_symbols:
                                continue

                            events.append(PriceEvent(
                                asset_id=asset_id,
                                symbol=symbol,
                                oracle_price=str(oracle_str),
                                mark_price=str(mark_str) if mark_str else None,
                                timestamp_ns=timestamp_ns,
                                block_height=block_height,
                            ))

            return block_height, timestamp_ns, events

        except json.JSONDecodeError:
            return 0, 0, []
        except Exception as e:
            print(f"[PRICE] Parse error: {e}", file=sys.stderr)
            return 0, 0, []

    def initialize(
        self,
        session: str = None,
        date: str = None,
        file: str = None,
        position: int = 0,
    ) -> bool:
        """
        Initialize reader state, optionally from checkpoint.

        Args:
            session: Session directory name to resume from
            date: Date directory name to resume from
            file: Block file name to resume from
            position: Byte position to resume from

        Returns:
            True if initialized successfully
        """
        # Find or use specified session
        if session:
            self._current_session = self._replica_path / session
            if not self._current_session.exists():
                print(f"[PRICE] Session {session} not found, finding latest", file=sys.stderr)
                self._current_session = self._find_latest_session()
        else:
            self._current_session = self._find_latest_session()

        if not self._current_session:
            print("[PRICE] No session found", file=sys.stderr)
            return False

        print(f"[PRICE] Using session: {self._current_session.name}", file=sys.stderr)

        # Find or use specified date
        if date:
            self._current_date = self._current_session / date
            if not self._current_date.exists():
                print(f"[PRICE] Date {date} not found, finding latest", file=sys.stderr)
                self._current_date = self._find_latest_date(self._current_session)
        else:
            self._current_date = self._find_latest_date(self._current_session)

        if not self._current_date:
            print("[PRICE] No date directory found", file=sys.stderr)
            return False

        print(f"[PRICE] Using date: {self._current_date.name}", file=sys.stderr)

        # Find or use specified file
        if file:
            file_path = self._current_date / file
            if file_path.exists():
                self._open_file(file_path, position)
            else:
                print(f"[PRICE] File {file} not found, finding latest", file=sys.stderr)
                latest = self._find_latest_file(self._current_date)
                if latest:
                    self._open_file(latest)
        else:
            latest = self._find_latest_file(self._current_date)
            if latest:
                # Start from end of file (skip catchup)
                self._open_file(latest)
                self._file_handle.seek(0, 2)  # Seek to end
                self._file_position = self._file_handle.tell()
                print(f"[PRICE] Starting from end of file (position {self._file_position})", file=sys.stderr)

        return self._file_handle is not None

    def read_prices(self, poll_interval: float = 0.1) -> Iterator[PriceEvent]:
        """
        Read price events continuously.

        Yields PriceEvent objects as new data arrives.
        Handles file rotation automatically.

        Args:
            poll_interval: Seconds to wait when no new data
        """
        if not self._file_handle:
            if not self.initialize():
                print("[PRICE] Failed to initialize", file=sys.stderr)
                return

        while True:
            line = self._file_handle.readline()

            if line:
                self._file_position = self._file_handle.tell()
                self._blocks_read += 1

                block_height, timestamp_ns, events = self._parse_block(line)

                if block_height > 0:
                    self._last_block_height = block_height

                for event in events:
                    self._prices_emitted += 1
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
            'session': self._current_session.name if self._current_session else '',
            'date': self._current_date.name if self._current_date else '',
            'file': self._current_file.name if self._current_file else '',
            'position': self._file_position,
            'block_height': self._last_block_height,
        }

    def get_metrics(self) -> dict:
        """Get reader metrics."""
        return {
            'blocks_read': self._blocks_read,
            'prices_emitted': self._prices_emitted,
            'last_block_height': self._last_block_height,
        }

    def close(self):
        """Close file handle."""
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None
