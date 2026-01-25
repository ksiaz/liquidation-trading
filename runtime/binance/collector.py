"""
Binance Data Collector Service.

Continuously collects funding rates and spot prices from Binance
for cross-exchange analysis (HLP25 Part 1 and Part 8 validation).

Runs as a background service alongside the main HLP24 collector.
"""

import time
import logging
import threading
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum, auto

from .client import BinanceClient, FundingInfo, SpotPrice


class CollectorState(Enum):
    """Collector service state."""
    STOPPED = auto()
    RUNNING = auto()
    PAUSED = auto()
    ERROR = auto()


@dataclass
class CollectorConfig:
    """Configuration for Binance collector."""
    # Symbols to track (Hyperliquid format)
    symbols: List[str] = field(default_factory=lambda: [
        'BTC', 'ETH', 'SOL', 'DOGE', 'XRP',
        'AVAX', 'LINK', 'ARB', 'OP', 'SUI'
    ])

    # Poll intervals (seconds)
    funding_poll_interval: float = 60.0  # 1 minute
    spot_poll_interval: float = 10.0  # 10 seconds

    # Rate limiting
    rate_limit_delay: float = 0.1  # 100ms between API calls

    # Error handling
    max_consecutive_errors: int = 5
    error_backoff_seconds: float = 30.0


@dataclass
class CollectorStats:
    """Statistics for collector monitoring."""
    funding_polls: int = 0
    spot_polls: int = 0
    funding_records: int = 0
    spot_records: int = 0
    errors: int = 0
    consecutive_errors: int = 0
    last_funding_poll_ts: int = 0
    last_spot_poll_ts: int = 0
    started_at: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'funding_polls': self.funding_polls,
            'spot_polls': self.spot_polls,
            'funding_records': self.funding_records,
            'spot_records': self.spot_records,
            'errors': self.errors,
            'consecutive_errors': self.consecutive_errors,
            'last_funding_poll_ts': self.last_funding_poll_ts,
            'last_spot_poll_ts': self.last_spot_poll_ts,
            'started_at': self.started_at,
        }


class BinanceCollector:
    """
    Binance data collector service.

    Collects funding rates and spot prices at configurable intervals
    and stores them in the database for cross-exchange analysis.
    """

    def __init__(
        self,
        db,
        config: CollectorConfig = None,
        logger: logging.Logger = None
    ):
        """
        Initialize collector.

        Args:
            db: ResearchDatabase instance
            config: Collector configuration
            logger: Optional logger
        """
        self._db = db
        self._config = config or CollectorConfig()
        self._logger = logger or logging.getLogger(__name__)

        self._client = BinanceClient(
            rate_limit_delay=self._config.rate_limit_delay,
            logger=self._logger
        )

        self._state = CollectorState.STOPPED
        self._stats = CollectorStats()

        self._funding_thread: Optional[threading.Thread] = None
        self._spot_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    @property
    def state(self) -> CollectorState:
        """Get current collector state."""
        return self._state

    @property
    def stats(self) -> CollectorStats:
        """Get collector statistics."""
        return self._stats

    def _now_ns(self) -> int:
        """Current time in nanoseconds."""
        return int(time.time() * 1_000_000_000)

    def start(self):
        """Start the collector service."""
        if self._state == CollectorState.RUNNING:
            self._logger.warning("Collector already running")
            return

        self._logger.info("Starting Binance collector")
        self._stop_event.clear()
        self._state = CollectorState.RUNNING
        self._stats.started_at = self._now_ns()

        # Start funding rate polling thread
        self._funding_thread = threading.Thread(
            target=self._funding_poll_loop,
            name="binance-funding-collector",
            daemon=True
        )
        self._funding_thread.start()

        # Start spot price polling thread
        self._spot_thread = threading.Thread(
            target=self._spot_poll_loop,
            name="binance-spot-collector",
            daemon=True
        )
        self._spot_thread.start()

        self._logger.info(
            f"Binance collector started - "
            f"tracking {len(self._config.symbols)} symbols"
        )

    def stop(self):
        """Stop the collector service."""
        if self._state == CollectorState.STOPPED:
            return

        self._logger.info("Stopping Binance collector")
        self._stop_event.set()
        self._state = CollectorState.STOPPED

        # Wait for threads to finish
        if self._funding_thread and self._funding_thread.is_alive():
            self._funding_thread.join(timeout=5.0)

        if self._spot_thread and self._spot_thread.is_alive():
            self._spot_thread.join(timeout=5.0)

        self._logger.info("Binance collector stopped")

    def pause(self):
        """Pause the collector (threads keep running but skip polls)."""
        if self._state == CollectorState.RUNNING:
            self._state = CollectorState.PAUSED
            self._logger.info("Binance collector paused")

    def resume(self):
        """Resume a paused collector."""
        if self._state == CollectorState.PAUSED:
            self._state = CollectorState.RUNNING
            self._logger.info("Binance collector resumed")

    def _funding_poll_loop(self):
        """Background loop for funding rate polling."""
        self._logger.info("Funding poll loop started")

        while not self._stop_event.is_set():
            try:
                if self._state == CollectorState.RUNNING:
                    self._poll_funding_rates()

                # Wait for next poll
                self._stop_event.wait(self._config.funding_poll_interval)

            except Exception as e:
                self._handle_error(f"Funding poll error: {e}")

        self._logger.info("Funding poll loop stopped")

    def _spot_poll_loop(self):
        """Background loop for spot price polling."""
        self._logger.info("Spot poll loop started")

        while not self._stop_event.is_set():
            try:
                if self._state == CollectorState.RUNNING:
                    self._poll_spot_prices()

                # Wait for next poll
                self._stop_event.wait(self._config.spot_poll_interval)

            except Exception as e:
                self._handle_error(f"Spot poll error: {e}")

        self._logger.info("Spot poll loop stopped")

    def _poll_funding_rates(self):
        """Poll and store funding rates for all symbols."""
        ts = self._now_ns()

        # Batch fetch all funding rates
        results = self._client.get_funding_rates_batch(self._config.symbols)

        records_stored = 0
        for symbol, info in results.items():
            if info is not None:
                self._store_funding_info(info)
                records_stored += 1

        self._stats.funding_polls += 1
        self._stats.funding_records += records_stored
        self._stats.last_funding_poll_ts = ts
        self._stats.consecutive_errors = 0

        self._logger.debug(
            f"Funding poll complete: {records_stored}/{len(self._config.symbols)} records"
        )

    def _poll_spot_prices(self):
        """Poll and store spot prices for all symbols."""
        ts = self._now_ns()

        # Batch fetch all spot prices
        results = self._client.get_spot_prices_batch(self._config.symbols)

        records_stored = 0
        for symbol, price in results.items():
            if price is not None:
                self._store_spot_price(price)
                records_stored += 1

        self._stats.spot_polls += 1
        self._stats.spot_records += records_stored
        self._stats.last_spot_poll_ts = ts
        self._stats.consecutive_errors = 0

        self._logger.debug(
            f"Spot poll complete: {records_stored}/{len(self._config.symbols)} records"
        )

    def _store_funding_info(self, info: FundingInfo):
        """Store funding info in database."""
        try:
            self._db.log_binance_funding_snapshot(
                snapshot_ts=info.timestamp,
                coin=info.symbol,
                funding_rate=str(info.funding_rate),
                funding_time=info.next_funding_time,
                mark_price=str(info.mark_price),
                index_price=str(info.index_price)
            )
        except Exception as e:
            self._logger.error(f"Failed to store funding info: {e}")

    def _store_spot_price(self, price: SpotPrice):
        """Store spot price in database."""
        try:
            self._db.log_spot_price_snapshot(
                snapshot_ts=price.timestamp,
                coin=price.symbol,
                price=str(price.price),
                source='binance'
            )
        except Exception as e:
            self._logger.error(f"Failed to store spot price: {e}")

    def _handle_error(self, message: str):
        """Handle collector error."""
        self._stats.errors += 1
        self._stats.consecutive_errors += 1
        self._logger.error(message)

        if self._stats.consecutive_errors >= self._config.max_consecutive_errors:
            self._logger.error(
                f"Max consecutive errors ({self._config.max_consecutive_errors}) reached, "
                f"backing off for {self._config.error_backoff_seconds}s"
            )
            self._state = CollectorState.ERROR
            time.sleep(self._config.error_backoff_seconds)
            self._state = CollectorState.RUNNING
            self._stats.consecutive_errors = 0

    def poll_once(self) -> Dict[str, Any]:
        """
        Perform a single poll cycle (for testing/manual use).

        Returns:
            Dict with poll results
        """
        funding_results = self._client.get_funding_rates_batch(self._config.symbols)
        spot_results = self._client.get_spot_prices_batch(self._config.symbols)

        funding_count = sum(1 for v in funding_results.values() if v is not None)
        spot_count = sum(1 for v in spot_results.values() if v is not None)

        # Store results
        for symbol, info in funding_results.items():
            if info is not None:
                self._store_funding_info(info)

        for symbol, price in spot_results.items():
            if price is not None:
                self._store_spot_price(price)

        return {
            'funding_records': funding_count,
            'spot_records': spot_count,
            'symbols': self._config.symbols,
            'timestamp': self._now_ns()
        }

    def get_status(self) -> Dict[str, Any]:
        """
        Get collector status.

        Returns:
            Status dictionary
        """
        return {
            'state': self._state.name,
            'symbols': self._config.symbols,
            'funding_interval': self._config.funding_poll_interval,
            'spot_interval': self._config.spot_poll_interval,
            'stats': self._stats.to_dict()
        }
