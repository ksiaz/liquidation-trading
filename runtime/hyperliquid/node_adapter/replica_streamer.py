"""
Replica Command Streamer

Efficiently streams new blocks from Hyperliquid node replica_cmds files.
Uses inotify on Linux for instant notification, polling fallback on Windows.

File structure:
    /root/hl/data/replica_cmds/{session_id}/{date}/{block_start}

Each file contains newline-delimited JSON blocks.
Files rotate when they reach a certain size/block count.
"""

import asyncio
import os
import sys
import glob
import time
from pathlib import Path
from typing import Optional, AsyncIterator
from dataclasses import dataclass

from .metrics import StreamerMetrics


@dataclass
class FileState:
    """Tracks state of current file being read."""
    path: Path
    position: int  # Byte position in file
    inode: int  # For detecting file replacement


class ReplicaCmdStreamer:
    """
    Async streamer for replica_cmds block files.

    Efficiently reads new blocks as they're written to the node's
    replica_cmds directory. Uses inotify on Linux for instant
    notification, falls back to polling on other platforms.

    Usage:
        streamer = ReplicaCmdStreamer("/root/hl/data/replica_cmds")
        await streamer.start()

        async for block_json in streamer.stream_blocks():
            # Process block
            pass

        await streamer.stop()
    """

    def __init__(
        self,
        replica_path: str,
        buffer_size: int = 100,
        poll_interval_ms: int = 50,
        start_from_end: bool = True,
    ):
        """
        Initialize streamer.

        Args:
            replica_path: Path to replica_cmds directory
            buffer_size: Max blocks to buffer
            poll_interval_ms: Polling interval when inotify unavailable
            start_from_end: If True, start reading from end of current file
        """
        self._replica_path = Path(replica_path)
        self._buffer_size = buffer_size
        self._poll_interval = poll_interval_ms / 1000.0
        self._start_from_end = start_from_end

        # State
        self._running = False
        self._current_file: Optional[FileState] = None
        self._buffer: asyncio.Queue = asyncio.Queue(maxsize=buffer_size)

        # Metrics
        self.metrics = StreamerMetrics()

        # inotify (Linux only)
        self._inotify = None
        self._inotify_available = False

    async def start(self) -> None:
        """Start streaming blocks."""
        if self._running:
            return

        self._running = True
        self.metrics.start_time = time.time()

        # Try to setup inotify
        await self._setup_inotify()

        # Find initial file
        await self._find_latest_file()

        # Start watcher task
        asyncio.create_task(self._watch_loop())

    async def stop(self) -> None:
        """Stop streaming."""
        self._running = False

        if self._inotify:
            try:
                self._inotify.close()
            except:
                pass

    async def stream_blocks(self) -> AsyncIterator[str]:
        """
        Async generator yielding block JSON strings.

        Blocks until new data is available.
        """
        while self._running:
            try:
                block_json = await asyncio.wait_for(
                    self._buffer.get(),
                    timeout=1.0
                )
                yield block_json
            except asyncio.TimeoutError:
                # No data, check if still running
                continue
            except asyncio.CancelledError:
                break

    async def get_block(self, timeout: float = 1.0) -> Optional[str]:
        """
        Get next block with timeout.

        Returns None if timeout reached.
        """
        try:
            return await asyncio.wait_for(
                self._buffer.get(),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            return None

    @property
    def buffer_utilization(self) -> float:
        """Current buffer utilization (0.0 to 1.0)."""
        return self._buffer.qsize() / self._buffer_size

    # ==================== Internal Methods ====================

    async def _setup_inotify(self) -> None:
        """Setup inotify if available (Linux only)."""
        if sys.platform != 'linux':
            return

        try:
            import inotify_simple
            self._inotify = inotify_simple.INotify()
            self._inotify_available = True
        except ImportError:
            # inotify_simple not installed, fall back to polling
            pass
        except Exception:
            # Other error, fall back to polling
            pass

    async def _find_latest_file(self) -> None:
        """Find the latest block file to read from."""
        # Pattern: replica_cmds/{session}/{date}/{block_start}
        # Sessions are numeric directories
        # Dates are like "2026-01-26"
        # Block files are numeric

        try:
            # Find latest session directory
            session_dirs = sorted(
                [d for d in self._replica_path.iterdir() if d.is_dir()],
                key=lambda d: d.name
            )

            if not session_dirs:
                return

            latest_session = session_dirs[-1]

            # Find latest date directory
            date_dirs = sorted(
                [d for d in latest_session.iterdir() if d.is_dir()],
                key=lambda d: d.name
            )

            if not date_dirs:
                return

            latest_date = date_dirs[-1]

            # Find latest block file
            block_files = sorted(
                [f for f in latest_date.iterdir() if f.is_file()],
                key=lambda f: int(f.name) if f.name.isdigit() else 0
            )

            if not block_files:
                return

            latest_file = block_files[-1]

            # Get file stat
            stat = latest_file.stat()

            # Set current file
            self._current_file = FileState(
                path=latest_file,
                position=stat.st_size if self._start_from_end else 0,
                inode=stat.st_ino
            )

            self.metrics.current_file = str(latest_file)

            # Setup inotify watch on the directory
            if self._inotify_available and self._inotify:
                import inotify_simple
                self._inotify.add_watch(
                    str(latest_date),
                    inotify_simple.flags.MODIFY | inotify_simple.flags.CREATE
                )

        except Exception as e:
            self.metrics.read_errors += 1

    async def _watch_loop(self) -> None:
        """Main watch loop - reads new blocks as they appear."""
        while self._running:
            try:
                if self._inotify_available:
                    await self._watch_inotify()
                else:
                    await self._watch_polling()
            except Exception as e:
                self.metrics.read_errors += 1
                await asyncio.sleep(0.1)

    async def _watch_inotify(self) -> None:
        """Watch using inotify (Linux)."""
        import inotify_simple

        # Check for events (non-blocking)
        events = self._inotify.read(timeout=100)  # 100ms timeout

        for event in events:
            if event.mask & inotify_simple.flags.MODIFY:
                await self._read_new_lines()
            elif event.mask & inotify_simple.flags.CREATE:
                await self._check_file_rotation()

        # Also check periodically in case we missed events
        await self._read_new_lines()

    async def _watch_polling(self) -> None:
        """Watch using polling (fallback for non-Linux)."""
        await self._read_new_lines()
        await self._check_file_rotation()
        await asyncio.sleep(self._poll_interval)

    async def _read_new_lines(self) -> None:
        """Read new lines from current file."""
        if not self._current_file:
            return

        try:
            # Check if file still exists and hasn't been replaced
            if not self._current_file.path.exists():
                await self._find_latest_file()
                return

            stat = self._current_file.path.stat()
            if stat.st_ino != self._current_file.inode:
                # File was replaced
                await self._find_latest_file()
                return

            # Check if there's new data
            if stat.st_size <= self._current_file.position:
                return

            # Read new data
            # Run in thread pool since file I/O is blocking
            new_lines = await asyncio.get_event_loop().run_in_executor(
                None,
                self._read_lines_sync,
                str(self._current_file.path),
                self._current_file.position
            )

            for line, new_position in new_lines:
                self._current_file.position = new_position
                self.metrics.bytes_read += len(line)

                # Check if it's a valid JSON block
                stripped = line.strip()
                if stripped.startswith('{'):
                    self.metrics.blocks_read += 1
                    self.metrics.last_block_time = time.time()

                    # Add to buffer
                    try:
                        self._buffer.put_nowait(stripped)
                    except asyncio.QueueFull:
                        # Buffer full - drop oldest
                        try:
                            self._buffer.get_nowait()
                            self._buffer.put_nowait(stripped)
                        except:
                            pass

        except Exception as e:
            self.metrics.read_errors += 1

    def _read_lines_sync(self, path: str, position: int) -> list:
        """
        Synchronously read new lines from file.

        Returns list of (line, new_position) tuples.
        """
        results = []

        try:
            with open(path, 'r', encoding='utf-8') as f:
                f.seek(position)

                while True:
                    line = f.readline()
                    if not line:
                        break

                    new_pos = f.tell()
                    results.append((line, new_pos))

        except Exception:
            pass

        return results

    async def _check_file_rotation(self) -> None:
        """Check if a new file has been created (file rotation)."""
        if not self._current_file:
            await self._find_latest_file()
            return

        try:
            # Get current file's directory
            current_dir = self._current_file.path.parent

            # Check for newer files
            all_files = sorted(
                [f for f in current_dir.iterdir() if f.is_file()],
                key=lambda f: int(f.name) if f.name.isdigit() else 0
            )

            if all_files:
                latest = all_files[-1]
                if latest != self._current_file.path:
                    # New file detected
                    self.metrics.files_rotated += 1

                    # Read remaining data from old file first
                    await self._read_new_lines()

                    # Switch to new file
                    stat = latest.stat()
                    self._current_file = FileState(
                        path=latest,
                        position=0,  # Start from beginning of new file
                        inode=stat.st_ino
                    )
                    self.metrics.current_file = str(latest)

            # Also check for new date directories
            # (this handles day rollover)
            session_dir = current_dir.parent
            date_dirs = sorted(
                [d for d in session_dir.iterdir() if d.is_dir()],
                key=lambda d: d.name
            )

            if date_dirs and date_dirs[-1] != current_dir:
                # New date directory - re-find latest file
                await self._find_latest_file()

        except Exception as e:
            self.metrics.read_errors += 1
