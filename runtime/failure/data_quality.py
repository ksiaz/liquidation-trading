"""
HLP16: Data Quality Validator.

Validates incoming market data for quality issues:
- Stale data detection (timestamp age)
- Corruption detection (invalid values)
- Sequence gap detection
- Future timestamp rejection

Actions on failure:
- STALE: Stop trading, maintain stops
- CORRUPT: Reject tick, increment counter, check rate
- SEQUENCE_GAP: Request recovery data

Integration points:
- DegradationManager: Triggers degradation on sustained quality issues
- CircuitBreaker: Can trip on high corruption rate
- NetworkHandler: Coordinates with sequence gap handling
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from enum import Enum, auto
from threading import Lock
from collections import deque


class ValidationStatus(Enum):
    """Result of data validation."""
    VALID = auto()
    STALE = auto()
    CORRUPT = auto()
    SEQUENCE_GAP = auto()
    FUTURE_TIMESTAMP = auto()
    INVALID_PRICE = auto()
    INVALID_BOOK = auto()


@dataclass
class DataQualityConfig:
    """Configuration for data quality validation."""
    # Staleness thresholds
    max_stale_ms: int = 1000              # Stop trading if data >1s old
    exit_stale_ms: int = 10000            # Exit positions if >10s old
    warn_stale_ms: int = 500              # Warn if data >500ms old

    # Sequence validation
    max_sequence_gap: int = 10            # Request full snapshot if gap >10

    # Timestamp validation
    max_future_timestamp_ms: int = 5000   # Reject timestamps >5s in future
    max_clock_drift_ms: int = 1000        # Allow 1s clock drift

    # Corruption detection
    max_corruption_rate: float = 0.05     # 5% corruption rate triggers alert
    corruption_window_size: int = 100     # Window for rate calculation
    min_samples_for_rate: int = 20        # Minimum samples before rate check

    # Price validation
    max_price_change_pct: float = 50.0    # Reject >50% price change in single tick
    min_price: float = 0.0                # Reject negative prices
    max_price: float = 1_000_000_000.0    # Reject unreasonably high prices

    # Orderbook validation
    require_bid_lt_ask: bool = True       # Bid must be < ask
    max_spread_pct: float = 50.0          # Reject >50% spread

    # OI validation
    require_non_negative_oi: bool = True


@dataclass
class ValidationResult:
    """Result of validating a single tick."""
    status: ValidationStatus
    timestamp: int  # nanoseconds
    symbol: str
    details: Dict = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return self.status == ValidationStatus.VALID


@dataclass
class MarketTick:
    """Generic market data tick for validation."""
    timestamp: int           # nanoseconds
    symbol: str
    price: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    open_interest: Optional[float] = None
    funding_rate: Optional[float] = None
    sequence: Optional[int] = None

    # Raw data for pass-through
    raw_data: Optional[Dict] = None


class DataQualityValidator:
    """
    Validate incoming market data quality.

    Tracks:
    - Per-symbol last valid tick
    - Per-symbol last sequence number
    - Rolling corruption rate

    Usage:
        validator = DataQualityValidator(config)

        result = validator.validate_tick(tick)
        if not result.is_valid:
            validator.on_validation_failure(result)
    """

    def __init__(
        self,
        config: DataQualityConfig = None,
        logger: logging.Logger = None
    ):
        self._config = config or DataQualityConfig()
        self._logger = logger or logging.getLogger(__name__)

        # Per-symbol tracking
        self._last_valid_tick: Dict[str, MarketTick] = {}
        self._last_sequence: Dict[str, int] = {}
        self._last_price: Dict[str, float] = {}

        # Corruption tracking
        self._validation_results: deque = deque(maxlen=self._config.corruption_window_size)
        self._corruption_count: int = 0
        self._total_validated: int = 0

        # Staleness tracking
        self._stale_symbols: Dict[str, int] = {}  # symbol -> first_stale_ts

        # Callbacks
        self._on_stale_data: Optional[Callable] = None
        self._on_corruption: Optional[Callable] = None
        self._on_sequence_gap: Optional[Callable] = None
        self._on_critical_quality: Optional[Callable] = None

        self._lock = Lock()

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    def set_stale_callback(self, callback: Callable):
        """Set callback for stale data detection."""
        self._on_stale_data = callback

    def set_corruption_callback(self, callback: Callable):
        """Set callback for corruption detection."""
        self._on_corruption = callback

    def set_sequence_gap_callback(self, callback: Callable):
        """Set callback for sequence gap detection."""
        self._on_sequence_gap = callback

    def set_critical_quality_callback(self, callback: Callable):
        """Set callback for critical quality issues."""
        self._on_critical_quality = callback

    def validate_tick(self, tick: MarketTick) -> ValidationResult:
        """
        Validate a market data tick.

        Checks:
        1. Timestamp not in future (>5s)
        2. Timestamp not too old (staleness)
        3. Sequence number monotonic
        4. Price > 0, OI >= 0
        5. Bid < ask

        Returns:
            ValidationResult with status and details
        """
        ts = self._now_ns()
        result = ValidationResult(
            status=ValidationStatus.VALID,
            timestamp=ts,
            symbol=tick.symbol
        )

        with self._lock:
            # 1. Check future timestamp
            if tick.timestamp > ts + (self._config.max_future_timestamp_ms * 1_000_000):
                result.status = ValidationStatus.FUTURE_TIMESTAMP
                result.details['tick_ts'] = tick.timestamp
                result.details['now_ts'] = ts
                result.details['future_ms'] = (tick.timestamp - ts) / 1_000_000
                self._record_validation(result)
                return result

            # 2. Check staleness
            age_ms = (ts - tick.timestamp) / 1_000_000

            if age_ms > self._config.exit_stale_ms:
                result.status = ValidationStatus.STALE
                result.details['age_ms'] = age_ms
                result.details['threshold_ms'] = self._config.exit_stale_ms
                result.details['severity'] = 'CRITICAL'
                self._record_validation(result)
                self._handle_stale(tick.symbol, ts)
                return result

            if age_ms > self._config.max_stale_ms:
                result.status = ValidationStatus.STALE
                result.details['age_ms'] = age_ms
                result.details['threshold_ms'] = self._config.max_stale_ms
                result.details['severity'] = 'WARNING'
                self._record_validation(result)
                self._handle_stale(tick.symbol, ts)
                return result

            # Clear stale tracking if data is fresh
            if tick.symbol in self._stale_symbols:
                del self._stale_symbols[tick.symbol]

            # 3. Check sequence
            if tick.sequence is not None:
                last_seq = self._last_sequence.get(tick.symbol, 0)
                if last_seq > 0 and tick.sequence > last_seq + 1:
                    gap = tick.sequence - last_seq - 1
                    if gap > self._config.max_sequence_gap:
                        result.status = ValidationStatus.SEQUENCE_GAP
                        result.details['expected'] = last_seq + 1
                        result.details['received'] = tick.sequence
                        result.details['gap'] = gap
                        self._record_validation(result)
                        return result

                self._last_sequence[tick.symbol] = tick.sequence

            # 4. Check price validity
            if tick.price is not None:
                if tick.price < self._config.min_price:
                    result.status = ValidationStatus.INVALID_PRICE
                    result.details['price'] = tick.price
                    result.details['reason'] = 'negative_or_zero'
                    self._record_validation(result)
                    return result

                if tick.price > self._config.max_price:
                    result.status = ValidationStatus.INVALID_PRICE
                    result.details['price'] = tick.price
                    result.details['reason'] = 'exceeds_max'
                    self._record_validation(result)
                    return result

                # Check price change
                last_price = self._last_price.get(tick.symbol)
                if last_price and last_price > 0:
                    change_pct = abs(tick.price - last_price) / last_price * 100
                    if change_pct > self._config.max_price_change_pct:
                        result.status = ValidationStatus.CORRUPT
                        result.details['price'] = tick.price
                        result.details['last_price'] = last_price
                        result.details['change_pct'] = change_pct
                        result.details['reason'] = 'excessive_change'
                        self._record_validation(result)
                        return result

                self._last_price[tick.symbol] = tick.price

            # 5. Check bid/ask validity
            if tick.bid is not None and tick.ask is not None:
                if self._config.require_bid_lt_ask and tick.bid >= tick.ask:
                    result.status = ValidationStatus.INVALID_BOOK
                    result.details['bid'] = tick.bid
                    result.details['ask'] = tick.ask
                    result.details['reason'] = 'bid_gte_ask'
                    self._record_validation(result)
                    return result

                mid = (tick.bid + tick.ask) / 2
                if mid > 0:
                    spread_pct = (tick.ask - tick.bid) / mid * 100
                    if spread_pct > self._config.max_spread_pct:
                        result.status = ValidationStatus.INVALID_BOOK
                        result.details['spread_pct'] = spread_pct
                        result.details['reason'] = 'excessive_spread'
                        self._record_validation(result)
                        return result

            # 6. Check OI validity
            if tick.open_interest is not None:
                if self._config.require_non_negative_oi and tick.open_interest < 0:
                    result.status = ValidationStatus.CORRUPT
                    result.details['open_interest'] = tick.open_interest
                    result.details['reason'] = 'negative_oi'
                    self._record_validation(result)
                    return result

            # All checks passed
            self._last_valid_tick[tick.symbol] = tick
            self._record_validation(result)
            return result

    def _record_validation(self, result: ValidationResult):
        """Record validation result for rate tracking."""
        self._validation_results.append(result)
        self._total_validated += 1

        if result.status != ValidationStatus.VALID:
            self._corruption_count += 1

            # Check corruption rate
            if self._total_validated >= self._config.min_samples_for_rate:
                rate = self._get_corruption_rate()
                if rate > self._config.max_corruption_rate:
                    self._logger.error(
                        f"High corruption rate: {rate*100:.1f}% "
                        f"(threshold: {self._config.max_corruption_rate*100:.1f}%)"
                    )
                    if self._on_critical_quality:
                        try:
                            self._on_critical_quality(rate, result)
                        except Exception as e:
                            self._logger.error(f"Critical quality callback error: {e}")

    def _get_corruption_rate(self) -> float:
        """Calculate current corruption rate from window."""
        if not self._validation_results:
            return 0.0

        corrupt_count = sum(
            1 for r in self._validation_results
            if r.status != ValidationStatus.VALID
        )
        return corrupt_count / len(self._validation_results)

    def _handle_stale(self, symbol: str, ts: int):
        """Handle stale data for a symbol."""
        if symbol not in self._stale_symbols:
            self._stale_symbols[symbol] = ts
            self._logger.warning(f"Data stale for {symbol}")

            if self._on_stale_data:
                try:
                    self._on_stale_data(symbol, ts)
                except Exception as e:
                    self._logger.error(f"Stale data callback error: {e}")

    def on_validation_failure(self, result: ValidationResult):
        """
        Handle validation failure with appropriate action.

        Actions:
        - STALE: Stop trading, maintain stops
        - CORRUPT: Reject tick, increment counter, check rate
        - SEQUENCE_GAP: Request recovery data
        """
        if result.status == ValidationStatus.STALE:
            self._logger.warning(
                f"Stale data for {result.symbol}: {result.details.get('age_ms', 0):.0f}ms old"
            )
            if self._on_stale_data:
                try:
                    self._on_stale_data(result.symbol, result.timestamp)
                except Exception as e:
                    self._logger.error(f"Stale callback error: {e}")

        elif result.status in (ValidationStatus.CORRUPT, ValidationStatus.INVALID_PRICE, ValidationStatus.INVALID_BOOK):
            self._logger.warning(
                f"Corrupt data for {result.symbol}: {result.details}"
            )
            if self._on_corruption:
                try:
                    self._on_corruption(result)
                except Exception as e:
                    self._logger.error(f"Corruption callback error: {e}")

        elif result.status == ValidationStatus.SEQUENCE_GAP:
            self._logger.warning(
                f"Sequence gap for {result.symbol}: expected {result.details.get('expected')}, "
                f"got {result.details.get('received')}"
            )
            if self._on_sequence_gap:
                try:
                    self._on_sequence_gap(result.symbol, result.details)
                except Exception as e:
                    self._logger.error(f"Sequence gap callback error: {e}")

        elif result.status == ValidationStatus.FUTURE_TIMESTAMP:
            self._logger.warning(
                f"Future timestamp for {result.symbol}: {result.details.get('future_ms', 0):.0f}ms ahead"
            )

    def get_stale_symbols(self) -> List[str]:
        """Get list of symbols currently stale."""
        with self._lock:
            return list(self._stale_symbols.keys())

    def get_staleness_duration_ms(self, symbol: str) -> Optional[float]:
        """Get how long a symbol has been stale."""
        with self._lock:
            first_stale = self._stale_symbols.get(symbol)
            if first_stale is None:
                return None
            return (self._now_ns() - first_stale) / 1_000_000

    def is_data_fresh(self, symbol: str, max_age_ms: int = None) -> bool:
        """Check if data for symbol is fresh."""
        if max_age_ms is None:
            max_age_ms = self._config.max_stale_ms

        with self._lock:
            last_tick = self._last_valid_tick.get(symbol)
            if not last_tick:
                return False

            age_ms = (self._now_ns() - last_tick.timestamp) / 1_000_000
            return age_ms <= max_age_ms

    def get_corruption_rate(self) -> float:
        """Get current corruption rate."""
        with self._lock:
            return self._get_corruption_rate()

    def get_summary(self) -> Dict:
        """Get data quality summary."""
        with self._lock:
            return {
                'total_validated': self._total_validated,
                'corruption_count': self._corruption_count,
                'corruption_rate': self._get_corruption_rate(),
                'stale_symbols': list(self._stale_symbols.keys()),
                'symbols_tracked': len(self._last_valid_tick),
                'window_size': len(self._validation_results),
            }

    def reset(self):
        """Reset validator state."""
        with self._lock:
            self._last_valid_tick.clear()
            self._last_sequence.clear()
            self._last_price.clear()
            self._validation_results.clear()
            self._corruption_count = 0
            self._total_validated = 0
            self._stale_symbols.clear()
