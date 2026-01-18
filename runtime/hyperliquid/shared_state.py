"""
Shared state for decoupled detection and UI.

Architecture:
- Detection loop (headless) writes to SharedPositionState
- UI reads from SharedPositionState at throttled intervals (250ms)
- Thread-safe access via RLock

This eliminates UI from the hot path entirely.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any
from collections import defaultdict


@dataclass
class PositionSnapshot:
    """Immutable snapshot of a tracked position."""
    wallet: str
    coin: str
    side: str  # 'LONG' or 'SHORT'
    size: float
    notional: float
    entry_price: float
    liq_price: float
    current_price: float
    distance_pct: float
    leverage: float
    danger_level: int = 0  # 0=safe, 1=watch, 2=warning, 3=critical
    updated_at: float = 0.0


@dataclass
class DangerAlert:
    """Alert for position entering danger zone."""
    wallet: str
    coin: str
    side: str
    notional: float
    distance_pct: float
    danger_level: int
    liq_price: float
    current_price: float
    timestamp: float


class SharedPositionState:
    """
    Thread-safe shared state between detection and UI.

    Detection writes:
    - update_position() - single position update
    - update_positions_batch() - bulk update
    - add_alert() - danger zone alert

    UI reads:
    - get_snapshot() - all positions (cached, ~0ms)
    - get_danger_positions() - positions in danger zone
    - get_alerts() - recent alerts
    - get_market_positions() - positions by market
    """

    def __init__(self):
        self._lock = threading.RLock()

        # Position storage (wallet -> coin -> PositionSnapshot)
        self._positions: Dict[str, Dict[str, PositionSnapshot]] = defaultdict(dict)

        # Market-indexed view (coin -> wallet -> PositionSnapshot)
        self._market_positions: Dict[str, Dict[str, PositionSnapshot]] = defaultdict(dict)

        # Danger zone positions (key = "wallet:coin")
        self._danger_positions: Dict[str, PositionSnapshot] = {}

        # Recent alerts (ring buffer, max 100)
        self._alerts: List[DangerAlert] = []
        self._max_alerts = 100

        # Cached snapshots for fast UI reads
        self._cached_all_positions: List[PositionSnapshot] = []
        self._cached_danger_positions: List[PositionSnapshot] = []
        self._cache_time: float = 0
        self._cache_ttl: float = 0.1  # 100ms cache

        # Stats
        self._stats = {
            'updates': 0,
            'alerts': 0,
            'last_update': 0.0
        }

        # Mid prices (for UI display)
        self._mid_prices: Dict[str, float] = {}

    # ===================
    # WRITE METHODS (Detection)
    # ===================

    def update_position(self, pos: PositionSnapshot):
        """Update single position (called from detection loop)."""
        with self._lock:
            # Update wallet-indexed
            self._positions[pos.wallet][pos.coin] = pos

            # Update market-indexed
            self._market_positions[pos.coin][pos.wallet] = pos

            # Update danger tracking
            key = f"{pos.wallet}:{pos.coin}"
            if pos.danger_level > 0 and pos.distance_pct > 0:
                self._danger_positions[key] = pos
            elif key in self._danger_positions:
                del self._danger_positions[key]

            self._stats['updates'] += 1
            self._stats['last_update'] = time.time()

            # Invalidate cache - force rebuild on next read
            self._cache_time = 0

    def update_positions_batch(self, positions: List[PositionSnapshot]):
        """Bulk update positions (more efficient)."""
        with self._lock:
            for pos in positions:
                self._positions[pos.wallet][pos.coin] = pos
                self._market_positions[pos.coin][pos.wallet] = pos

                key = f"{pos.wallet}:{pos.coin}"
                if pos.danger_level > 0 and pos.distance_pct > 0:
                    self._danger_positions[key] = pos
                elif key in self._danger_positions:
                    del self._danger_positions[key]

            self._stats['updates'] += len(positions)
            self._stats['last_update'] = time.time()

            # Invalidate cache - force rebuild on next read
            self._cache_time = 0

    def remove_position(self, wallet: str, coin: str):
        """Remove closed position."""
        with self._lock:
            if coin in self._positions.get(wallet, {}):
                del self._positions[wallet][coin]
            if wallet in self._market_positions.get(coin, {}):
                del self._market_positions[coin][wallet]

            key = f"{wallet}:{coin}"
            if key in self._danger_positions:
                del self._danger_positions[key]

            # Invalidate cache - force rebuild on next read
            self._cache_time = 0

    def add_alert(self, alert: DangerAlert):
        """Add danger zone alert."""
        with self._lock:
            self._alerts.append(alert)
            if len(self._alerts) > self._max_alerts:
                self._alerts = self._alerts[-self._max_alerts:]
            self._stats['alerts'] += 1

    def update_mid_prices(self, prices: Dict[str, float]):
        """Update mid prices for UI display."""
        with self._lock:
            self._mid_prices.update(prices)

    # ===================
    # READ METHODS (UI)
    # ===================

    def get_all_positions(self) -> List[PositionSnapshot]:
        """Get all positions (cached for fast UI reads)."""
        now = time.time()

        # Return cached if fresh
        if now - self._cache_time < self._cache_ttl:
            return self._cached_all_positions

        with self._lock:
            # Rebuild cache
            self._cached_all_positions = [
                pos for wallet_positions in self._positions.values()
                for pos in wallet_positions.values()
            ]
            self._cache_time = now
            return self._cached_all_positions

    def get_danger_positions(self, min_notional: float = 0) -> List[PositionSnapshot]:
        """Get positions in danger zone, sorted by distance."""
        with self._lock:
            positions = [
                pos for pos in self._danger_positions.values()
                if pos.notional >= min_notional
            ]
            # Sort by distance (closest to liq first)
            positions.sort(key=lambda p: p.distance_pct)
            return positions

    def get_market_positions(self, coin: str) -> List[PositionSnapshot]:
        """Get all positions for a specific market."""
        with self._lock:
            return list(self._market_positions.get(coin, {}).values())

    def get_wallet_positions(self, wallet: str) -> List[PositionSnapshot]:
        """Get all positions for a specific wallet."""
        with self._lock:
            return list(self._positions.get(wallet, {}).values())

    def get_alerts(self, since: float = 0, limit: int = 20) -> List[DangerAlert]:
        """Get recent alerts."""
        with self._lock:
            if since > 0:
                alerts = [a for a in self._alerts if a.timestamp > since]
            else:
                alerts = self._alerts[-limit:]
            return list(alerts)

    def get_mid_price(self, coin: str) -> float:
        """Get mid price for a coin."""
        with self._lock:
            return self._mid_prices.get(coin, 0)

    def get_stats(self) -> Dict[str, Any]:
        """Get state statistics."""
        with self._lock:
            return {
                'total_positions': sum(len(p) for p in self._positions.values()),
                'danger_positions': len(self._danger_positions),
                'total_alerts': self._stats['alerts'],
                'updates': self._stats['updates'],
                'last_update': self._stats['last_update'],
                'wallets_tracked': len(self._positions),
                'markets_tracked': len(self._market_positions)
            }

    # ===================
    # UTILITY METHODS
    # ===================

    def clear(self):
        """Clear all state (for testing)."""
        with self._lock:
            self._positions.clear()
            self._market_positions.clear()
            self._danger_positions.clear()
            self._alerts.clear()
            self._cached_all_positions.clear()
            self._cached_danger_positions.clear()


# Global singleton instance
_shared_state: Optional[SharedPositionState] = None
_state_lock = threading.Lock()


def get_shared_state() -> SharedPositionState:
    """Get or create the global shared state instance."""
    global _shared_state
    if _shared_state is None:
        with _state_lock:
            if _shared_state is None:
                _shared_state = SharedPositionState()
    return _shared_state
