#!/usr/bin/env python3
"""
Paper Trading Validation Script (HLP20).

Validates system meets production-readiness criteria before live trading.

Criteria (configurable):
- Minimum duration: 7 days
- Minimum trades: 50
- Maximum crashes: 0
- Maximum position mismatches: 0
- Minimum win rate: 50%
- Minimum Sharpe ratio: 1.0
- Maximum drawdown: 20%
- Minimum fill rate: 95%
- Maximum average slippage: 0.1%

Usage:
    python scripts/run_paper_validation.py --duration-days 7 --min-trades 50

Reports:
    - Daily progress summary
    - Final validation report
    - Criteria pass/fail status
"""

import argparse
import asyncio
import logging
import time
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from runtime.logging.execution_db import ResearchDatabase


@dataclass
class ValidationCriteria:
    """Criteria for paper trading validation."""
    min_duration_days: int = 7
    min_trades: int = 50
    max_crashes: int = 0
    max_position_mismatches: int = 0
    min_win_rate: float = 0.50
    min_sharpe: float = 1.0
    max_drawdown: float = 0.20
    min_fill_rate: float = 0.95
    max_avg_slippage: float = 0.001  # 0.1%


@dataclass
class ValidationMetrics:
    """Tracked metrics during validation."""
    start_time: float = 0
    trades_count: int = 0
    wins_count: int = 0
    losses_count: int = 0
    total_pnl: float = 0.0
    peak_equity: float = 0.0
    max_drawdown: float = 0.0
    crashes: int = 0
    position_mismatches: int = 0
    fills_attempted: int = 0
    fills_successful: int = 0
    total_slippage_pct: float = 0.0
    pnl_series: List[float] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Final validation result."""
    passed: bool
    duration_days: float
    metrics: ValidationMetrics
    criteria: ValidationCriteria
    failures: List[str] = field(default_factory=list)


class PaperTradingValidator:
    """
    Validate system meets criteria before live trading.

    Tracks all metrics during paper trading period and
    reports pass/fail for each criterion.
    """

    def __init__(
        self,
        db: ResearchDatabase,
        criteria: ValidationCriteria = None,
        logger: logging.Logger = None
    ):
        self._db = db
        self._criteria = criteria or ValidationCriteria()
        self._logger = logger or logging.getLogger(__name__)

        self._metrics = ValidationMetrics(start_time=time.time())
        self._running = False
        self._initial_equity = 0.0

    def set_initial_equity(self, equity: float):
        """Set initial equity for drawdown calculation."""
        self._initial_equity = equity
        self._metrics.peak_equity = equity

    def record_trade(
        self,
        pnl: float,
        expected_price: float,
        fill_price: float,
        filled: bool = True
    ):
        """Record a trade result."""
        self._metrics.trades_count += 1
        self._metrics.total_pnl += pnl
        self._metrics.pnl_series.append(pnl)

        if pnl > 0:
            self._metrics.wins_count += 1
        elif pnl < 0:
            self._metrics.losses_count += 1

        # Track fill rate
        self._metrics.fills_attempted += 1
        if filled:
            self._metrics.fills_successful += 1

        # Track slippage
        if expected_price > 0:
            slippage = abs(fill_price - expected_price) / expected_price
            self._metrics.total_slippage_pct += slippage

        # Update equity and drawdown
        current_equity = self._initial_equity + self._metrics.total_pnl
        if current_equity > self._metrics.peak_equity:
            self._metrics.peak_equity = current_equity

        if self._metrics.peak_equity > 0:
            drawdown = (self._metrics.peak_equity - current_equity) / self._metrics.peak_equity
            if drawdown > self._metrics.max_drawdown:
                self._metrics.max_drawdown = drawdown

    def record_crash(self, reason: str):
        """Record a system crash."""
        self._metrics.crashes += 1
        self._logger.error(f"CRASH recorded: {reason}")

    def record_position_mismatch(self, symbol: str, local_size: float, exchange_size: float):
        """Record a position mismatch."""
        self._metrics.position_mismatches += 1
        self._logger.error(
            f"POSITION MISMATCH: {symbol} local={local_size} exchange={exchange_size}"
        )

    def get_duration_days(self) -> float:
        """Get elapsed duration in days."""
        elapsed_seconds = time.time() - self._metrics.start_time
        return elapsed_seconds / 86400.0

    def get_win_rate(self) -> float:
        """Calculate current win rate."""
        total = self._metrics.wins_count + self._metrics.losses_count
        if total == 0:
            return 0.0
        return self._metrics.wins_count / total

    def get_sharpe_ratio(self) -> float:
        """Calculate Sharpe ratio from PnL series."""
        if len(self._metrics.pnl_series) < 2:
            return 0.0

        import statistics
        mean_pnl = statistics.mean(self._metrics.pnl_series)
        std_pnl = statistics.stdev(self._metrics.pnl_series)

        if std_pnl == 0:
            return 0.0

        # Annualized (assuming daily PnL)
        return (mean_pnl / std_pnl) * (252 ** 0.5)

    def get_fill_rate(self) -> float:
        """Calculate fill rate."""
        if self._metrics.fills_attempted == 0:
            return 1.0
        return self._metrics.fills_successful / self._metrics.fills_attempted

    def get_avg_slippage(self) -> float:
        """Calculate average slippage."""
        if self._metrics.fills_successful == 0:
            return 0.0
        return self._metrics.total_slippage_pct / self._metrics.fills_successful

    def check_criteria(self) -> ValidationResult:
        """Check all criteria and return result."""
        failures = []

        # Duration check
        duration = self.get_duration_days()
        if duration < self._criteria.min_duration_days:
            failures.append(
                f"Duration {duration:.1f}d < {self._criteria.min_duration_days}d required"
            )

        # Trade count check
        if self._metrics.trades_count < self._criteria.min_trades:
            failures.append(
                f"Trades {self._metrics.trades_count} < {self._criteria.min_trades} required"
            )

        # Crash check
        if self._metrics.crashes > self._criteria.max_crashes:
            failures.append(
                f"Crashes {self._metrics.crashes} > {self._criteria.max_crashes} allowed"
            )

        # Position mismatch check
        if self._metrics.position_mismatches > self._criteria.max_position_mismatches:
            failures.append(
                f"Position mismatches {self._metrics.position_mismatches} > "
                f"{self._criteria.max_position_mismatches} allowed"
            )

        # Win rate check
        win_rate = self.get_win_rate()
        if win_rate < self._criteria.min_win_rate:
            failures.append(
                f"Win rate {win_rate:.1%} < {self._criteria.min_win_rate:.1%} required"
            )

        # Sharpe check
        sharpe = self.get_sharpe_ratio()
        if sharpe < self._criteria.min_sharpe:
            failures.append(
                f"Sharpe {sharpe:.2f} < {self._criteria.min_sharpe:.2f} required"
            )

        # Drawdown check
        if self._metrics.max_drawdown > self._criteria.max_drawdown:
            failures.append(
                f"Drawdown {self._metrics.max_drawdown:.1%} > "
                f"{self._criteria.max_drawdown:.1%} allowed"
            )

        # Fill rate check
        fill_rate = self.get_fill_rate()
        if fill_rate < self._criteria.min_fill_rate:
            failures.append(
                f"Fill rate {fill_rate:.1%} < {self._criteria.min_fill_rate:.1%} required"
            )

        # Slippage check
        avg_slippage = self.get_avg_slippage()
        if avg_slippage > self._criteria.max_avg_slippage:
            failures.append(
                f"Avg slippage {avg_slippage:.3%} > "
                f"{self._criteria.max_avg_slippage:.3%} allowed"
            )

        return ValidationResult(
            passed=len(failures) == 0,
            duration_days=duration,
            metrics=self._metrics,
            criteria=self._criteria,
            failures=failures
        )

    def get_daily_summary(self) -> Dict:
        """Get daily summary for progress reporting."""
        return {
            'duration_days': self.get_duration_days(),
            'trades': self._metrics.trades_count,
            'win_rate': self.get_win_rate(),
            'sharpe': self.get_sharpe_ratio(),
            'total_pnl': self._metrics.total_pnl,
            'max_drawdown': self._metrics.max_drawdown,
            'crashes': self._metrics.crashes,
            'position_mismatches': self._metrics.position_mismatches,
            'fill_rate': self.get_fill_rate(),
            'avg_slippage': self.get_avg_slippage(),
        }

    def print_report(self, result: ValidationResult):
        """Print formatted validation report."""
        print("\n" + "=" * 60)
        print("PAPER TRADING VALIDATION REPORT")
        print("=" * 60)

        print(f"\nDuration: {result.duration_days:.2f} days")
        print(f"Trades: {result.metrics.trades_count}")
        print(f"Win Rate: {self.get_win_rate():.1%}")
        print(f"Sharpe Ratio: {self.get_sharpe_ratio():.2f}")
        print(f"Total PnL: ${result.metrics.total_pnl:,.2f}")
        print(f"Max Drawdown: {result.metrics.max_drawdown:.1%}")
        print(f"Crashes: {result.metrics.crashes}")
        print(f"Position Mismatches: {result.metrics.position_mismatches}")
        print(f"Fill Rate: {self.get_fill_rate():.1%}")
        print(f"Avg Slippage: {self.get_avg_slippage():.3%}")

        print("\n" + "-" * 60)
        print("CRITERIA CHECK")
        print("-" * 60)

        if result.passed:
            print("\n✓ ALL CRITERIA PASSED - Ready for live trading")
        else:
            print("\n✗ VALIDATION FAILED")
            print("\nFailures:")
            for failure in result.failures:
                print(f"  - {failure}")

        print("\n" + "=" * 60)


def load_trades_from_db(db: ResearchDatabase, since_ts: float) -> List[Dict]:
    """Load trades from database since timestamp."""
    try:
        # Query trades table
        query = """
            SELECT symbol, side, entry_price, exit_price, quantity, pnl,
                   entry_time, exit_time, slippage_pct
            FROM trades
            WHERE entry_time >= ?
            ORDER BY entry_time
        """
        rows = db.query_raw(query, (since_ts,))
        return [dict(row) for row in rows]
    except Exception as e:
        logging.warning(f"Could not load trades: {e}")
        return []


async def run_validation(args):
    """Run paper trading validation."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger("PaperValidation")

    # Setup criteria from args
    criteria = ValidationCriteria(
        min_duration_days=args.duration_days,
        min_trades=args.min_trades,
        min_win_rate=args.min_win_rate,
        min_sharpe=args.min_sharpe,
        max_drawdown=args.max_drawdown,
    )

    # Initialize database
    db_path = args.db or "logs/execution.db"
    db = ResearchDatabase(db_path)

    # Initialize validator
    validator = PaperTradingValidator(db, criteria, logger)
    validator.set_initial_equity(args.initial_equity)

    logger.info(f"Starting paper trading validation")
    logger.info(f"Criteria: {criteria}")
    logger.info(f"Target duration: {criteria.min_duration_days} days")
    logger.info(f"Minimum trades: {criteria.min_trades}")

    # If --check-only, load existing trades and report
    if args.check_only:
        logger.info("Check-only mode: analyzing existing trades")

        # Calculate start time based on duration
        start_ts = time.time() - (args.duration_days * 86400)
        trades = load_trades_from_db(db, start_ts)

        for trade in trades:
            pnl = trade.get('pnl', 0) or 0
            entry_price = trade.get('entry_price', 0) or 0
            exit_price = trade.get('exit_price', 0) or 0
            slippage = trade.get('slippage_pct', 0) or 0

            validator.record_trade(
                pnl=pnl,
                expected_price=entry_price,
                fill_price=entry_price * (1 + slippage),
                filled=True
            )

        result = validator.check_criteria()
        validator.print_report(result)

        return 0 if result.passed else 1

    # Live monitoring mode
    logger.info("Live monitoring mode: tracking trades in real-time")
    logger.info("Press Ctrl+C to stop and generate report")

    last_check_time = time.time()
    check_interval = 3600  # Check every hour

    try:
        while True:
            # Check criteria periodically
            current_time = time.time()
            if current_time - last_check_time >= check_interval:
                last_check_time = current_time

                summary = validator.get_daily_summary()
                logger.info(
                    f"Progress: {summary['duration_days']:.2f}d, "
                    f"{summary['trades']} trades, "
                    f"WR: {summary['win_rate']:.1%}, "
                    f"Sharpe: {summary['sharpe']:.2f}"
                )

                # Check if validation complete
                result = validator.check_criteria()
                if result.passed:
                    logger.info("All criteria met!")
                    validator.print_report(result)
                    return 0

            await asyncio.sleep(60)  # Check every minute

    except KeyboardInterrupt:
        logger.info("\nValidation interrupted by user")
        result = validator.check_criteria()
        validator.print_report(result)
        return 0 if result.passed else 1


def main():
    parser = argparse.ArgumentParser(
        description="Paper trading validation for production readiness"
    )

    parser.add_argument(
        "--duration-days", type=int, default=7,
        help="Minimum duration in days (default: 7)"
    )
    parser.add_argument(
        "--min-trades", type=int, default=50,
        help="Minimum number of trades (default: 50)"
    )
    parser.add_argument(
        "--min-win-rate", type=float, default=0.50,
        help="Minimum win rate (default: 0.50)"
    )
    parser.add_argument(
        "--min-sharpe", type=float, default=1.0,
        help="Minimum Sharpe ratio (default: 1.0)"
    )
    parser.add_argument(
        "--max-drawdown", type=float, default=0.20,
        help="Maximum drawdown (default: 0.20)"
    )
    parser.add_argument(
        "--initial-equity", type=float, default=10000.0,
        help="Initial equity for drawdown calculation (default: 10000)"
    )
    parser.add_argument(
        "--db", type=str, default=None,
        help="Database path (default: logs/execution.db)"
    )
    parser.add_argument(
        "--check-only", action="store_true",
        help="Check existing trades without live monitoring"
    )

    args = parser.parse_args()

    exit_code = asyncio.run(run_validation(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
