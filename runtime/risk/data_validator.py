"""
HLP16: Data Quality Validator.

Validates incoming market data for quality and consistency.

Validation checks:
1. Staleness - Data too old
2. Consistency - Price within expected bounds
3. Completeness - Required fields present
4. Sequence - Timestamps monotonic
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from enum import Enum, auto
from threading import Lock


class DataQuality(Enum):
    """Quality level of data."""
    GOOD = auto()
    STALE = auto()
    SUSPICIOUS = auto()
    INVALID = auto()


class ValidationIssue(Enum):
    """Types of validation issues."""
    STALE_DATA = auto()
    PRICE_OUT_OF_BOUNDS = auto()
    MISSING_FIELD = auto()
    TIMESTAMP_REGRESSION = auto()
    EXCESSIVE_SPREAD = auto()
    ZERO_DEPTH = auto()
    DUPLICATE_DATA = auto()


@dataclass
class ValidationConfig:
    """Configuration for data validation."""
    # Staleness thresholds
    price_stale_ms: int = 5_000  # 5 seconds
    book_stale_ms: int = 2_000  # 2 seconds
    funding_stale_ms: int = 60_000  # 1 minute

    # Price bounds (percentage from last known)
    max_price_change_pct: float = 0.10  # 10% instant change
    max_spread_pct: float = 0.05  # 5% bid-ask spread

    # Depth requirements
    min_book_depth_usd: float = 10_000.0

    # Sequence requirements
    max_timestamp_regression_ms: int = 100  # Allow small regression


@dataclass
class ValidationResult:
    """Result of data validation."""
    quality: DataQuality
    issues: List[ValidationIssue] = field(default_factory=list)
    details: Dict = field(default_factory=dict)
    timestamp: int = 0  # nanoseconds


@dataclass
class DataRecord:
    """Record of validated data point."""
    symbol: str
    data_type: str  # price, book, funding, etc.
    timestamp: int  # nanoseconds
    quality: DataQuality
    value: float


class DataValidator:
    """
    Validates market data quality.

    Tracks data history to detect:
    - Staleness
    - Sudden jumps
    - Missing data
    - Sequence violations
    """

    def __init__(
        self,
        config: ValidationConfig = None,
        logger: logging.Logger = None
    ):
        self._config = config or ValidationConfig()
        self._logger = logger or logging.getLogger(__name__)

        # Price tracking
        self._last_prices: Dict[str, DataRecord] = {}  # symbol -> last price
        self._price_history: Dict[str, List[DataRecord]] = {}

        # Book tracking
        self._last_books: Dict[str, DataRecord] = {}

        # Timestamp tracking for sequence validation
        self._last_timestamps: Dict[str, int] = {}  # key -> last ts

        # Issue counters
        self._issue_counts: Dict[ValidationIssue, int] = {
            issue: 0 for issue in ValidationIssue
        }

        self._lock = Lock()

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    def validate_price(
        self,
        symbol: str,
        price: float,
        timestamp: int = None
    ) -> ValidationResult:
        """Validate a price update."""
        ts = timestamp or self._now_ns()
        issues = []
        details = {}

        with self._lock:
            # Check for staleness
            age_ms = (self._now_ns() - ts) / 1_000_000
            if age_ms > self._config.price_stale_ms:
                issues.append(ValidationIssue.STALE_DATA)
                details['age_ms'] = age_ms

            # Check timestamp sequence
            key = f"price:{symbol}"
            if key in self._last_timestamps:
                last_ts = self._last_timestamps[key]
                if ts < last_ts:
                    regression_ms = (last_ts - ts) / 1_000_000
                    if regression_ms > self._config.max_timestamp_regression_ms:
                        issues.append(ValidationIssue.TIMESTAMP_REGRESSION)
                        details['regression_ms'] = regression_ms

            # Check price bounds
            if symbol in self._last_prices:
                last_price = self._last_prices[symbol].value
                if last_price > 0:
                    change_pct = abs(price - last_price) / last_price
                    if change_pct > self._config.max_price_change_pct:
                        issues.append(ValidationIssue.PRICE_OUT_OF_BOUNDS)
                        details['change_pct'] = change_pct
                        details['last_price'] = last_price

            # Check for zero/negative price
            if price <= 0:
                issues.append(ValidationIssue.PRICE_OUT_OF_BOUNDS)
                details['invalid_price'] = price

            # Determine quality
            quality = self._issues_to_quality(issues)

            # Update tracking
            if quality in (DataQuality.GOOD, DataQuality.SUSPICIOUS):
                record = DataRecord(
                    symbol=symbol,
                    data_type='price',
                    timestamp=ts,
                    quality=quality,
                    value=price
                )
                self._last_prices[symbol] = record
                self._last_timestamps[key] = ts

                # Update history
                if symbol not in self._price_history:
                    self._price_history[symbol] = []
                self._price_history[symbol].append(record)

                # Keep only last 100 prices
                if len(self._price_history[symbol]) > 100:
                    self._price_history[symbol] = self._price_history[symbol][-100:]

            # Update issue counts
            for issue in issues:
                self._issue_counts[issue] += 1

            return ValidationResult(
                quality=quality,
                issues=issues,
                details=details,
                timestamp=ts
            )

    def validate_orderbook(
        self,
        symbol: str,
        bid_price: float,
        ask_price: float,
        bid_depth_usd: float,
        ask_depth_usd: float,
        timestamp: int = None
    ) -> ValidationResult:
        """Validate orderbook data."""
        ts = timestamp or self._now_ns()
        issues = []
        details = {}

        with self._lock:
            # Check staleness
            age_ms = (self._now_ns() - ts) / 1_000_000
            if age_ms > self._config.book_stale_ms:
                issues.append(ValidationIssue.STALE_DATA)
                details['age_ms'] = age_ms

            # Check spread
            if bid_price > 0 and ask_price > 0:
                mid_price = (bid_price + ask_price) / 2
                spread_pct = (ask_price - bid_price) / mid_price
                if spread_pct > self._config.max_spread_pct:
                    issues.append(ValidationIssue.EXCESSIVE_SPREAD)
                    details['spread_pct'] = spread_pct

                # Check crossed book
                if bid_price >= ask_price:
                    issues.append(ValidationIssue.PRICE_OUT_OF_BOUNDS)
                    details['crossed_book'] = True

            # Check depth
            total_depth = bid_depth_usd + ask_depth_usd
            if total_depth < self._config.min_book_depth_usd:
                issues.append(ValidationIssue.ZERO_DEPTH)
                details['total_depth_usd'] = total_depth

            # Determine quality
            quality = self._issues_to_quality(issues)

            # Update tracking
            key = f"book:{symbol}"
            if quality in (DataQuality.GOOD, DataQuality.SUSPICIOUS):
                self._last_books[symbol] = DataRecord(
                    symbol=symbol,
                    data_type='book',
                    timestamp=ts,
                    quality=quality,
                    value=(bid_price + ask_price) / 2
                )
                self._last_timestamps[key] = ts

            # Update issue counts
            for issue in issues:
                self._issue_counts[issue] += 1

            return ValidationResult(
                quality=quality,
                issues=issues,
                details=details,
                timestamp=ts
            )

    def validate_funding(
        self,
        symbol: str,
        funding_rate: float,
        timestamp: int = None
    ) -> ValidationResult:
        """Validate funding rate data."""
        ts = timestamp or self._now_ns()
        issues = []
        details = {}

        with self._lock:
            # Check staleness
            age_ms = (self._now_ns() - ts) / 1_000_000
            if age_ms > self._config.funding_stale_ms:
                issues.append(ValidationIssue.STALE_DATA)
                details['age_ms'] = age_ms

            # Check bounds (funding rarely exceeds +/- 1%)
            if abs(funding_rate) > 0.01:
                issues.append(ValidationIssue.PRICE_OUT_OF_BOUNDS)
                details['extreme_funding'] = funding_rate

            quality = self._issues_to_quality(issues)

            for issue in issues:
                self._issue_counts[issue] += 1

            return ValidationResult(
                quality=quality,
                issues=issues,
                details=details,
                timestamp=ts
            )

    def check_completeness(
        self,
        required_symbols: Set[str],
        data_type: str = 'price'
    ) -> ValidationResult:
        """Check if all required symbols have recent data."""
        ts = self._now_ns()
        issues = []
        details = {'missing': [], 'stale': []}

        with self._lock:
            if data_type == 'price':
                data_source = self._last_prices
                stale_ms = self._config.price_stale_ms
            else:
                data_source = self._last_books
                stale_ms = self._config.book_stale_ms

            for symbol in required_symbols:
                if symbol not in data_source:
                    issues.append(ValidationIssue.MISSING_FIELD)
                    details['missing'].append(symbol)
                else:
                    record = data_source[symbol]
                    age_ms = (ts - record.timestamp) / 1_000_000
                    if age_ms > stale_ms:
                        issues.append(ValidationIssue.STALE_DATA)
                        details['stale'].append(symbol)

            quality = self._issues_to_quality(issues)

            return ValidationResult(
                quality=quality,
                issues=issues,
                details=details,
                timestamp=ts
            )

    def _issues_to_quality(self, issues: List[ValidationIssue]) -> DataQuality:
        """Convert list of issues to overall quality."""
        if not issues:
            return DataQuality.GOOD

        severe_issues = {
            ValidationIssue.TIMESTAMP_REGRESSION,
            ValidationIssue.ZERO_DEPTH,
        }

        invalid_issues = {
            ValidationIssue.PRICE_OUT_OF_BOUNDS,
        }

        for issue in issues:
            if issue in invalid_issues:
                return DataQuality.INVALID

        for issue in issues:
            if issue in severe_issues:
                return DataQuality.SUSPICIOUS

        if ValidationIssue.STALE_DATA in issues:
            return DataQuality.STALE

        return DataQuality.SUSPICIOUS

    def get_issue_counts(self) -> Dict[str, int]:
        """Get counts of each issue type."""
        with self._lock:
            return {issue.name: count for issue, count in self._issue_counts.items()}

    def get_last_price(self, symbol: str) -> Optional[float]:
        """Get last validated price for a symbol."""
        with self._lock:
            record = self._last_prices.get(symbol)
            return record.value if record else None

    def get_data_quality_summary(self) -> Dict:
        """Get summary of data quality across all symbols."""
        with self._lock:
            price_symbols = set(self._last_prices.keys())
            book_symbols = set(self._last_books.keys())

            ts = self._now_ns()
            stale_prices = []
            stale_books = []

            for symbol, record in self._last_prices.items():
                age_ms = (ts - record.timestamp) / 1_000_000
                if age_ms > self._config.price_stale_ms:
                    stale_prices.append(symbol)

            for symbol, record in self._last_books.items():
                age_ms = (ts - record.timestamp) / 1_000_000
                if age_ms > self._config.book_stale_ms:
                    stale_books.append(symbol)

            return {
                'price_symbols': len(price_symbols),
                'book_symbols': len(book_symbols),
                'stale_prices': stale_prices,
                'stale_books': stale_books,
                'issue_counts': self.get_issue_counts()
            }

    def reset_counters(self):
        """Reset issue counters."""
        with self._lock:
            self._issue_counts = {issue: 0 for issue in ValidationIssue}
