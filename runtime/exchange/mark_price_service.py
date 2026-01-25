"""
P3: Mark Price Service with Freshness Validation.

Tracks mark prices with timestamps and validates freshness before use.

Production Safety:
- Stale mark prices can lead to incorrect risk calculations
- Fresh mark prices required for:
  - Liquidation price estimation
  - PnL calculations
  - Risk checks (leverage, margin)

Constitutional: No interpretation of price values.
"""

import time
import logging
from dataclasses import dataclass
from typing import Dict, Optional, List, Tuple
from decimal import Decimal
from threading import RLock


@dataclass
class MarkPriceEntry:
    """Mark price with timestamp and source."""
    price: Decimal
    timestamp: float  # Unix timestamp
    source: str  # "STREAM", "API", "ORDERBOOK"


@dataclass
class FreshnessConfig:
    """Configuration for mark price freshness validation."""
    # Maximum age in seconds for mark price to be considered fresh
    max_age_seconds: float = 5.0  # 5 seconds default

    # Maximum age for critical operations (entry/exit)
    critical_max_age_seconds: float = 2.0  # 2 seconds for critical

    # Whether to reject operations on stale prices
    reject_on_stale: bool = True

    # Whether to log staleness warnings
    log_staleness: bool = True


class MarkPriceService:
    """
    P3: Mark price tracking with freshness validation.

    Features:
    - Tracks mark prices with timestamps
    - Validates freshness before use
    - Provides fresh-only access methods
    - Logs staleness warnings

    Usage:
        service = get_mark_price_service()
        service.update("BTC", Decimal("50000"), source="STREAM")

        # For display (may be stale)
        price = service.get_price("BTC")

        # For critical operations (must be fresh)
        price = service.get_fresh_price("BTC", max_age=2.0)
    """

    def __init__(
        self,
        config: Optional[FreshnessConfig] = None,
        logger: Optional[logging.Logger] = None
    ):
        self._config = config or FreshnessConfig()
        self._logger = logger or logging.getLogger(__name__)
        self._lock = RLock()

        # Price storage: symbol -> MarkPriceEntry
        self._prices: Dict[str, MarkPriceEntry] = {}

        # Staleness tracking
        self._stale_warnings: Dict[str, float] = {}  # Last warning time per symbol
        self._warning_cooldown: float = 10.0  # Seconds between warnings

    def update(
        self,
        symbol: str,
        price: Decimal,
        timestamp: Optional[float] = None,
        source: str = "STREAM"
    ):
        """
        Update mark price for a symbol.

        Args:
            symbol: Symbol (e.g., "BTC", "BTCUSDT")
            price: Mark price
            timestamp: Price timestamp (uses current time if None)
            source: Price source ("STREAM", "API", "ORDERBOOK")
        """
        if timestamp is None:
            timestamp = time.time()

        entry = MarkPriceEntry(
            price=price,
            timestamp=timestamp,
            source=source
        )

        with self._lock:
            self._prices[symbol] = entry

    def update_batch(self, prices: Dict[str, Decimal], timestamp: Optional[float] = None):
        """Update multiple mark prices at once."""
        if timestamp is None:
            timestamp = time.time()

        with self._lock:
            for symbol, price in prices.items():
                self._prices[symbol] = MarkPriceEntry(
                    price=price,
                    timestamp=timestamp,
                    source="BATCH"
                )

    def get_price(self, symbol: str) -> Optional[Decimal]:
        """
        Get mark price for symbol (may be stale).

        Use get_fresh_price() for critical operations.

        Args:
            symbol: Symbol to lookup

        Returns:
            Mark price or None if not found
        """
        with self._lock:
            entry = self._prices.get(symbol)
        return entry.price if entry else None

    def get_entry(self, symbol: str) -> Optional[MarkPriceEntry]:
        """Get full mark price entry with timestamp."""
        with self._lock:
            return self._prices.get(symbol)

    def get_fresh_price(
        self,
        symbol: str,
        max_age: Optional[float] = None
    ) -> Optional[Decimal]:
        """
        Get mark price only if fresh.

        P3: Returns None if price is stale.

        Args:
            symbol: Symbol to lookup
            max_age: Maximum age in seconds (uses config default if None)

        Returns:
            Mark price if fresh, None if stale or not found
        """
        if max_age is None:
            max_age = self._config.max_age_seconds

        now = time.time()

        with self._lock:
            entry = self._prices.get(symbol)

        if entry is None:
            return None

        age = now - entry.timestamp
        if age > max_age:
            self._log_staleness_warning(symbol, age, max_age)
            return None

        return entry.price

    def get_fresh_prices(
        self,
        symbols: List[str],
        max_age: Optional[float] = None
    ) -> Dict[str, Decimal]:
        """
        Get fresh prices for multiple symbols.

        Only includes symbols with fresh prices.
        """
        if max_age is None:
            max_age = self._config.max_age_seconds

        now = time.time()
        result = {}

        with self._lock:
            for symbol in symbols:
                entry = self._prices.get(symbol)
                if entry and (now - entry.timestamp) <= max_age:
                    result[symbol] = entry.price

        return result

    def get_all_prices(self) -> Dict[str, Decimal]:
        """Get all prices (may include stale)."""
        with self._lock:
            return {s: e.price for s, e in self._prices.items()}

    def is_fresh(self, symbol: str, max_age: Optional[float] = None) -> bool:
        """
        Check if mark price is fresh.

        Args:
            symbol: Symbol to check
            max_age: Maximum age in seconds

        Returns:
            True if price exists and is fresh
        """
        if max_age is None:
            max_age = self._config.max_age_seconds

        now = time.time()

        with self._lock:
            entry = self._prices.get(symbol)

        if entry is None:
            return False

        return (now - entry.timestamp) <= max_age

    def get_staleness(self, symbol: str) -> Optional[float]:
        """
        Get age of mark price in seconds.

        Args:
            symbol: Symbol to check

        Returns:
            Age in seconds or None if not found
        """
        with self._lock:
            entry = self._prices.get(symbol)

        if entry is None:
            return None

        return time.time() - entry.timestamp

    def validate_for_execution(
        self,
        symbol: str,
        require_fresh: bool = True
    ) -> Tuple[bool, Optional[Decimal], Optional[str]]:
        """
        Validate mark price for execution use.

        P3: Strict validation for critical execution paths.

        Args:
            symbol: Symbol to validate
            require_fresh: Whether to require freshness

        Returns:
            (is_valid, price, error_message)
        """
        with self._lock:
            entry = self._prices.get(symbol)

        if entry is None:
            return (False, None, f"No mark price for {symbol}")

        if require_fresh:
            age = time.time() - entry.timestamp
            max_age = self._config.critical_max_age_seconds

            if age > max_age:
                return (
                    False,
                    entry.price,
                    f"Mark price for {symbol} is stale: {age:.1f}s old (max {max_age}s)"
                )

        return (True, entry.price, None)

    def _log_staleness_warning(
        self,
        symbol: str,
        age: float,
        max_age: float
    ):
        """Log staleness warning with cooldown."""
        if not self._config.log_staleness:
            return

        now = time.time()

        with self._lock:
            last_warning = self._stale_warnings.get(symbol, 0)
            if now - last_warning < self._warning_cooldown:
                return
            self._stale_warnings[symbol] = now

        self._logger.warning(
            f"P3: Mark price for {symbol} is stale: {age:.1f}s old (max {max_age}s)"
        )

    def get_statistics(self) -> Dict:
        """Get mark price statistics."""
        now = time.time()

        with self._lock:
            fresh_count = sum(
                1 for e in self._prices.values()
                if (now - e.timestamp) <= self._config.max_age_seconds
            )
            stale_count = len(self._prices) - fresh_count

            ages = [now - e.timestamp for e in self._prices.values()]

        return {
            'total_symbols': len(self._prices),
            'fresh_count': fresh_count,
            'stale_count': stale_count,
            'avg_age_seconds': sum(ages) / len(ages) if ages else 0,
            'max_age_seconds': max(ages) if ages else 0,
        }

    def clear(self):
        """Clear all prices (for testing)."""
        with self._lock:
            self._prices.clear()
            self._stale_warnings.clear()


# ==============================================================================
# Singleton Instance
# ==============================================================================

_service_instance: Optional[MarkPriceService] = None
_service_lock = RLock()


def get_mark_price_service(
    config: Optional[FreshnessConfig] = None
) -> MarkPriceService:
    """Get or create the singleton mark price service."""
    global _service_instance
    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                _service_instance = MarkPriceService(config=config)
    return _service_instance


def reset_mark_price_service():
    """Reset the singleton (for testing)."""
    global _service_instance
    with _service_lock:
        _service_instance = None
