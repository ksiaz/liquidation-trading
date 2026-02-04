"""
Checkpoint Management for Node Adapter.

Persists adapter state to enable restart without data loss.
Tracks:
- Current replica_cmds session and file position
- Current node_fills file and position
- Last processed block height
"""

import json
import os
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


@dataclass
class AdapterCheckpoint:
    """Adapter state checkpoint."""

    # Price reader state
    price_session: str = ""           # Current replica_cmds session
    price_date: str = ""              # Current date directory (YYYYMMDD)
    price_file: str = ""              # Current block file name
    price_file_position: int = 0      # Byte position in file
    last_block_height: int = 0        # Last processed block height

    # Liquidation reader state
    liq_date: str = ""                # Current node_fills date
    liq_hour: int = -1                # Current hour file (0-23)
    liq_file_position: int = 0        # Byte position in file
    last_liq_fill_id: int = 0         # Last processed fill ID

    # Metrics
    prices_emitted: int = 0
    liquidations_emitted: int = 0
    last_update_time: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'AdapterCheckpoint':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class CheckpointManager:
    """
    Manages checkpoint persistence.

    Saves state to JSON file periodically and on shutdown.
    Loads state on startup for seamless restart.
    """

    DEFAULT_PATH = Path.home() / ".hl-adapter" / "checkpoint.json"
    SAVE_INTERVAL_SEC = 10.0  # Save every 10 seconds

    def __init__(self, checkpoint_path: Optional[Path] = None):
        self._path = checkpoint_path or self.DEFAULT_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)

        self._checkpoint = AdapterCheckpoint()
        self._last_save_time = 0.0
        self._dirty = False

    def load(self) -> AdapterCheckpoint:
        """Load checkpoint from disk, or return fresh checkpoint if none exists."""
        if self._path.exists():
            try:
                with open(self._path, 'r') as f:
                    data = json.load(f)
                self._checkpoint = AdapterCheckpoint.from_dict(data)
                print(f"[CHECKPOINT] Loaded: block={self._checkpoint.last_block_height}, "
                      f"prices={self._checkpoint.prices_emitted}, "
                      f"liqs={self._checkpoint.liquidations_emitted}", file=sys.stderr)
            except (json.JSONDecodeError, KeyError) as e:
                print(f"[CHECKPOINT] Failed to load, starting fresh: {e}", file=sys.stderr)
                self._checkpoint = AdapterCheckpoint()
        else:
            print("[CHECKPOINT] No checkpoint found, starting fresh", file=sys.stderr)
            self._checkpoint = AdapterCheckpoint()

        return self._checkpoint

    def save(self, force: bool = False) -> bool:
        """
        Save checkpoint to disk.

        Args:
            force: Save immediately even if interval hasn't elapsed

        Returns:
            True if saved, False if skipped (interval not elapsed)
        """
        now = time.time()

        if not force and (now - self._last_save_time) < self.SAVE_INTERVAL_SEC:
            return False

        if not self._dirty and not force:
            return False

        self._checkpoint.last_update_time = now

        try:
            # Write to temp file first, then rename (atomic)
            temp_path = self._path.with_suffix('.tmp')
            with open(temp_path, 'w') as f:
                json.dump(self._checkpoint.to_dict(), f, indent=2)
            temp_path.rename(self._path)

            self._last_save_time = now
            self._dirty = False
            return True

        except Exception as e:
            print(f"[CHECKPOINT] Save failed: {e}", file=sys.stderr)
            return False

    def update_price_state(
        self,
        session: str = None,
        date: str = None,
        file: str = None,
        position: int = None,
        block_height: int = None,
    ):
        """Update price reader state."""
        if session is not None:
            self._checkpoint.price_session = session
        if date is not None:
            self._checkpoint.price_date = date
        if file is not None:
            self._checkpoint.price_file = file
        if position is not None:
            self._checkpoint.price_file_position = position
        if block_height is not None:
            self._checkpoint.last_block_height = block_height
        self._dirty = True

    def update_liq_state(
        self,
        date: str = None,
        hour: int = None,
        position: int = None,
        fill_id: int = None,
    ):
        """Update liquidation reader state."""
        if date is not None:
            self._checkpoint.liq_date = date
        if hour is not None:
            self._checkpoint.liq_hour = hour
        if position is not None:
            self._checkpoint.liq_file_position = position
        if fill_id is not None:
            self._checkpoint.last_liq_fill_id = fill_id
        self._dirty = True

    def increment_prices(self, count: int = 1):
        """Increment prices emitted counter."""
        self._checkpoint.prices_emitted += count
        self._dirty = True

    def increment_liquidations(self, count: int = 1):
        """Increment liquidations emitted counter."""
        self._checkpoint.liquidations_emitted += count
        self._dirty = True

    @property
    def checkpoint(self) -> AdapterCheckpoint:
        """Get current checkpoint state."""
        return self._checkpoint
