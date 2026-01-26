"""
Sync Monitor

Monitors Hyperliquid node sync status from visor_abci_state.json.
Tracks block height, consensus time, and sync lag.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass

from .metrics import SyncMetrics


@dataclass
class SyncStatus:
    """Current node sync status."""
    height: int
    consensus_time: str
    wall_clock_time: str
    lag_seconds: float
    is_synced: bool

    def to_dict(self) -> Dict:
        return {
            'height': self.height,
            'consensus_time': self.consensus_time,
            'wall_clock_time': self.wall_clock_time,
            'lag_seconds': round(self.lag_seconds, 2),
            'is_synced': self.is_synced,
        }


class SyncMonitor:
    """
    Monitors node sync status from visor_abci_state.json.

    File structure:
    {
        "initial_height": 871512000,
        "height": 873759938,
        "scheduled_freeze_height": null,
        "consensus_time": "2026-01-26T11:02:32.346725263",
        "wall_clock_time": "2026-01-26T11:02:34.262515308",
        "reference_lag": null
    }
    """

    def __init__(
        self,
        state_path: str,
        max_lag_warning: float = 5.0,
        max_lag_error: float = 30.0,
    ):
        """
        Initialize sync monitor.

        Args:
            state_path: Path to hyperliquid_data directory
            max_lag_warning: Lag threshold for warning (seconds)
            max_lag_error: Lag threshold for error (seconds)
        """
        self._state_path = Path(state_path)
        self._visor_file = self._state_path / "visor_abci_state.json"
        self._max_lag_warning = max_lag_warning
        self._max_lag_error = max_lag_error

        # Metrics
        self.metrics = SyncMetrics()

        # Last known status
        self._last_status: Optional[SyncStatus] = None

    def get_status(self) -> Optional[SyncStatus]:
        """
        Get current sync status.

        Returns None if status file cannot be read.
        """
        self.metrics.sync_checks += 1

        try:
            with open(self._visor_file, 'r') as f:
                data = json.load(f)

            height = data.get('height', 0)
            consensus_time = data.get('consensus_time', '')
            wall_clock_time = data.get('wall_clock_time', '')

            # Calculate lag
            lag = 0.0
            if consensus_time and wall_clock_time:
                try:
                    ct = datetime.fromisoformat(consensus_time[:26])
                    wt = datetime.fromisoformat(wall_clock_time[:26])
                    lag = (wt - ct).total_seconds()
                except:
                    pass

            # Determine if synced
            is_synced = lag < self._max_lag_warning

            status = SyncStatus(
                height=height,
                consensus_time=consensus_time,
                wall_clock_time=wall_clock_time,
                lag_seconds=lag,
                is_synced=is_synced,
            )

            # Update metrics
            self.metrics.block_height = height
            self.metrics.consensus_time = consensus_time
            self.metrics.wall_clock_time = wall_clock_time
            self.metrics.lag_seconds = lag
            self.metrics.is_synced = is_synced

            if lag > self.metrics.max_lag_observed:
                self.metrics.max_lag_observed = lag

            self._last_status = status
            return status

        except FileNotFoundError:
            self.metrics.sync_failures += 1
            return None
        except json.JSONDecodeError:
            self.metrics.sync_failures += 1
            return None
        except Exception:
            self.metrics.sync_failures += 1
            return None

    def is_synced(self) -> bool:
        """Check if node is currently synced."""
        status = self.get_status()
        return status.is_synced if status else False

    def get_lag(self) -> float:
        """Get current sync lag in seconds."""
        status = self.get_status()
        return status.lag_seconds if status else float('inf')

    def get_height(self) -> int:
        """Get current block height."""
        status = self.get_status()
        return status.height if status else 0

    @property
    def last_status(self) -> Optional[SyncStatus]:
        """Get last known status without re-reading file."""
        return self._last_status
