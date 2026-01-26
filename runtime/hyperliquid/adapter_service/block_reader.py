"""
Block Reader for Hyperliquid Node

Reads blocks from replica_cmds using inotify for efficient file watching.
Handles file rotation as new block files are created.
"""

import asyncio
import json
import time
from pathlib import Path
from typing import AsyncIterator, Optional, Dict, List
from dataclasses import dataclass, field
from datetime import datetime

# Try to import inotify for efficient file watching (Linux only)
try:
    import inotify_simple
    INOTIFY_AVAILABLE = True
except ImportError:
    INOTIFY_AVAILABLE = False


@dataclass
class BlockReaderMetrics:
    """Metrics for block reader."""
    blocks_read: int = 0
    bytes_read: int = 0
    files_rotated: int = 0
    parse_errors: int = 0
    current_file: str = ""
    start_time: float = field(default_factory=time.time)


class BlockReader:
    """
    Reads blocks from replica_cmds directory.

    Uses inotify to efficiently watch for new data.
    Handles file rotation when new block files are created.
    """

    DEFAULT_REPLICA_PATH = '/root/hl/data/replica_cmds'

    def __init__(
        self,
        replica_path: str = DEFAULT_REPLICA_PATH,
        start_from_end: bool = True,
    ):
        """
        Initialize block reader.

        Args:
            replica_path: Path to replica_cmds directory
            start_from_end: If True, start from latest block (don't replay history)
        """
        self._replica_path = Path(replica_path)
        self._start_from_end = start_from_end
        self._running = False

        # File tracking
        self._current_file: Optional[Path] = None
        self._file_handle = None
        self._file_position = 0

        # inotify (if available)
        self._inotify = None
        self._watch_descriptor = None

        # Metrics
        self.metrics = BlockReaderMetrics()

    async def start(self) -> None:
        """Start the block reader."""
        self._running = True

        # Find latest file
        self._current_file = self._find_latest_file()
        if not self._current_file:
            raise RuntimeError(f"No replica files found in {self._replica_path}")

        self.metrics.current_file = str(self._current_file)
        print(f"[BlockReader] Starting from: {self._current_file}")

        # Set up inotify if available
        if INOTIFY_AVAILABLE:
            self._inotify = inotify_simple.INotify()
            self._watch_descriptor = self._inotify.add_watch(
                str(self._current_file.parent),
                inotify_simple.flags.MODIFY | inotify_simple.flags.CREATE
            )
            print(f"[BlockReader] Using inotify for file watching")
        else:
            print(f"[BlockReader] inotify not available, using polling")

    async def stop(self) -> None:
        """Stop the block reader."""
        self._running = False

        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None

        if self._inotify:
            self._inotify.close()
            self._inotify = None

    async def stream_blocks(self) -> AsyncIterator[Dict]:
        """
        Stream parsed blocks as they arrive.

        Yields:
            Parsed block dictionaries
        """
        if not self._current_file:
            return

        # Open file
        self._file_handle = open(self._current_file, 'r')

        # Seek to end if starting from latest
        if self._start_from_end:
            self._file_handle.seek(0, 2)
            self._file_position = self._file_handle.tell()

        while self._running:
            # Read available lines
            line = self._file_handle.readline()

            if line:
                self.metrics.bytes_read += len(line)

                # Parse and yield block
                try:
                    block = json.loads(line.strip())
                    self.metrics.blocks_read += 1
                    yield block
                except json.JSONDecodeError as e:
                    self.metrics.parse_errors += 1
                    continue
            else:
                # No data - check for file rotation
                new_file = self._find_latest_file()

                if new_file and new_file != self._current_file:
                    # File rotated - switch to new file
                    print(f"[BlockReader] Rotating to: {new_file}")
                    self._file_handle.close()
                    self._current_file = new_file
                    self._file_handle = open(self._current_file, 'r')
                    self.metrics.files_rotated += 1
                    self.metrics.current_file = str(new_file)
                else:
                    # Wait for new data
                    if self._inotify:
                        # Wait for inotify event (non-blocking check)
                        try:
                            events = self._inotify.read(timeout=100)  # 100ms
                        except:
                            await asyncio.sleep(0.01)
                    else:
                        await asyncio.sleep(0.01)  # 10ms polling

    def _find_latest_file(self) -> Optional[Path]:
        """Find the latest replica file."""
        try:
            # Structure: replica_cmds/{session}/{date}/{block_start}
            sessions = sorted(self._replica_path.iterdir(), reverse=True)

            for session in sessions:
                if not session.is_dir():
                    continue

                dates = sorted(session.iterdir(), reverse=True)

                for date_dir in dates:
                    if not date_dir.is_dir():
                        continue

                    files = sorted(date_dir.iterdir(), reverse=True)

                    for f in files:
                        if f.is_file() and f.name.isdigit():
                            return f
        except Exception as e:
            print(f"[BlockReader] Error finding file: {e}")

        return None

    def get_status(self) -> Dict:
        """Get current reader status."""
        return {
            'running': self._running,
            'current_file': str(self._current_file) if self._current_file else None,
            'blocks_read': self.metrics.blocks_read,
            'bytes_read': self.metrics.bytes_read,
            'files_rotated': self.metrics.files_rotated,
            'parse_errors': self.metrics.parse_errors,
            'uptime_seconds': time.time() - self.metrics.start_time,
        }
