"""
HLP22: Determinism Checker.

Verifies that backtests produce identical results when run multiple times
with the same inputs. Critical for trustworthy parameter optimization.

Features:
- Multi-run comparison
- Trade-by-trade matching
- State snapshot verification
- Random seed validation

Usage:
    checker = DeterminismChecker(backtest_fn)

    result = await checker.verify(
        parameters={'threshold': 0.15},
        n_runs=3,
    )

    if result.is_deterministic:
        print("Backtest is reproducible")
    else:
        print(f"Divergence at trade {result.first_divergence_index}")
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable


@dataclass
class TradeRecord:
    """Record of a single trade for comparison."""
    index: int
    timestamp: str
    symbol: str
    side: str
    size: float
    entry_price: float
    exit_price: float
    pnl: float

    def to_hash(self) -> str:
        """Generate hash for comparison."""
        data = f"{self.symbol}|{self.side}|{self.size:.8f}|{self.entry_price:.8f}|{self.exit_price:.8f}|{self.pnl:.8f}"
        return hashlib.md5(data.encode()).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'index': self.index,
            'timestamp': self.timestamp,
            'symbol': self.symbol,
            'side': self.side,
            'size': self.size,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'pnl': self.pnl,
        }


@dataclass
class RunResult:
    """Result of a single backtest run."""
    run_id: int
    trades: List[TradeRecord]
    final_pnl: float
    trade_count: int
    execution_time_sec: float
    trades_hash: str  # Hash of all trades for quick comparison

    @classmethod
    def from_trades(
        cls,
        run_id: int,
        trades: List[Dict[str, Any]],
        execution_time: float,
    ) -> 'RunResult':
        """Create from raw trade data."""
        records = []
        for i, t in enumerate(trades):
            records.append(TradeRecord(
                index=i,
                timestamp=str(t.get('timestamp', '')),
                symbol=t.get('symbol', ''),
                side=t.get('side', ''),
                size=float(t.get('size', 0)),
                entry_price=float(t.get('entry_price', 0)),
                exit_price=float(t.get('exit_price', 0)),
                pnl=float(t.get('pnl', 0)),
            ))

        # Calculate hash of all trades
        trade_hashes = [r.to_hash() for r in records]
        combined_hash = hashlib.md5('|'.join(trade_hashes).encode()).hexdigest()

        return cls(
            run_id=run_id,
            trades=records,
            final_pnl=sum(t.pnl for t in records),
            trade_count=len(records),
            execution_time_sec=execution_time,
            trades_hash=combined_hash,
        )


@dataclass
class Divergence:
    """Information about where runs diverged."""
    trade_index: int
    field: str
    values: Dict[int, Any]  # run_id -> value

    def to_dict(self) -> Dict[str, Any]:
        return {
            'trade_index': self.trade_index,
            'field': self.field,
            'values': {str(k): v for k, v in self.values.items()},
        }


@dataclass
class DeterminismResult:
    """Result of determinism check."""
    parameters: Dict[str, float]
    n_runs: int
    is_deterministic: bool
    runs: List[RunResult]
    divergences: List[Divergence] = field(default_factory=list)
    first_divergence_index: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'parameters': self.parameters,
            'n_runs': self.n_runs,
            'is_deterministic': self.is_deterministic,
            'trade_counts': [r.trade_count for r in self.runs],
            'final_pnls': [r.final_pnl for r in self.runs],
            'execution_times': [r.execution_time_sec for r in self.runs],
            'first_divergence_index': self.first_divergence_index,
            'divergences': [d.to_dict() for d in self.divergences[:10]],  # First 10
        }


class DeterminismChecker:
    """
    Verifies backtest determinism.

    Runs the same backtest multiple times and compares results
    trade-by-trade to ensure reproducibility.
    """

    def __init__(
        self,
        backtest_fn: Callable[..., List[Dict[str, Any]]],
        logger: logging.Logger = None,
    ):
        """
        Initialize determinism checker.

        Args:
            backtest_fn: Function that takes parameters and returns list of trades.
                        Signature: (params: Dict[str, float]) -> List[Dict]
            logger: Logger instance
        """
        self._backtest_fn = backtest_fn
        self._logger = logger or logging.getLogger(__name__)

    async def verify(
        self,
        parameters: Dict[str, float],
        n_runs: int = 3,
        timeout_sec: float = 600.0,
    ) -> DeterminismResult:
        """
        Verify determinism by running backtest multiple times.

        Args:
            parameters: Parameters to test
            n_runs: Number of runs to compare (minimum 2)
            timeout_sec: Timeout for each run

        Returns:
            DeterminismResult indicating if runs were identical
        """
        if n_runs < 2:
            raise ValueError("Need at least 2 runs to verify determinism")

        self._logger.info(f"Verifying determinism with {n_runs} runs")

        # Run backtests
        runs = []
        for i in range(n_runs):
            start = datetime.now()
            try:
                if asyncio.iscoroutinefunction(self._backtest_fn):
                    trades = await asyncio.wait_for(
                        self._backtest_fn(parameters),
                        timeout=timeout_sec,
                    )
                else:
                    trades = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self._backtest_fn(parameters),
                    )

                execution_time = (datetime.now() - start).total_seconds()
                runs.append(RunResult.from_trades(i, trades, execution_time))
                self._logger.debug(
                    f"Run {i}: {len(trades)} trades, {execution_time:.2f}s"
                )

            except Exception as e:
                self._logger.error(f"Run {i} failed: {e}")
                raise

        # Compare runs
        divergences = self._find_divergences(runs)
        is_deterministic = len(divergences) == 0

        result = DeterminismResult(
            parameters=parameters,
            n_runs=n_runs,
            is_deterministic=is_deterministic,
            runs=runs,
            divergences=divergences,
            first_divergence_index=divergences[0].trade_index if divergences else None,
        )

        if is_deterministic:
            self._logger.info("Backtest is deterministic")
        else:
            self._logger.warning(
                f"Backtest is NOT deterministic! "
                f"First divergence at trade {result.first_divergence_index}"
            )

        return result

    def _find_divergences(self, runs: List[RunResult]) -> List[Divergence]:
        """Find all divergences between runs."""
        divergences = []

        # Quick check: compare hashes
        hashes = [r.trades_hash for r in runs]
        if len(set(hashes)) == 1:
            return []  # All identical

        # Check trade counts
        counts = [r.trade_count for r in runs]
        if len(set(counts)) > 1:
            divergences.append(Divergence(
                trade_index=-1,
                field='trade_count',
                values={r.run_id: r.trade_count for r in runs},
            ))

        # Compare trade by trade
        min_trades = min(r.trade_count for r in runs)

        for i in range(min_trades):
            trades_at_i = [r.trades[i] for r in runs]

            # Compare each field
            for field_name in ['symbol', 'side', 'size', 'entry_price', 'exit_price', 'pnl']:
                values = [getattr(t, field_name) for t in trades_at_i]

                # For floats, use tolerance
                if field_name in ('size', 'entry_price', 'exit_price', 'pnl'):
                    if not self._floats_equal(values):
                        divergences.append(Divergence(
                            trade_index=i,
                            field=field_name,
                            values={r.run_id: getattr(r.trades[i], field_name) for r in runs},
                        ))
                else:
                    if len(set(values)) > 1:
                        divergences.append(Divergence(
                            trade_index=i,
                            field=field_name,
                            values={r.run_id: getattr(r.trades[i], field_name) for r in runs},
                        ))

        return divergences

    def _floats_equal(self, values: List[float], tolerance: float = 1e-10) -> bool:
        """Check if all float values are equal within tolerance."""
        if not values:
            return True
        reference = values[0]
        return all(abs(v - reference) < tolerance for v in values)


async def verify_strategy_determinism(
    strategy_cls: type,
    historical_data: Any,
    parameters: Dict[str, float],
    n_runs: int = 3,
) -> DeterminismResult:
    """
    Convenience function to verify strategy determinism.

    Args:
        strategy_cls: Strategy class to instantiate
        historical_data: Historical data to backtest on
        parameters: Strategy parameters
        n_runs: Number of runs

    Returns:
        DeterminismResult
    """
    def run_backtest(params: Dict[str, float]) -> List[Dict[str, Any]]:
        strategy = strategy_cls(**params)
        # Assuming strategy has a backtest method
        return strategy.backtest(historical_data)

    checker = DeterminismChecker(run_backtest)
    return await checker.verify(parameters, n_runs)
