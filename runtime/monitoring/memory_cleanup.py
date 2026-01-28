"""
Cleanup Coordinator - Periodic Memory Cleanup

Coordinates pruning across all components to prevent memory leaks.
Runs periodically (default: every 5 minutes) and calls prune methods
on registered components.

Usage:
    coordinator = CleanupCoordinator(interval_sec=300)
    coordinator.register_pruner("organic_detector", detector.prune_stale)
    coordinator.register_pruner("position_manager", psm.prune_empty_wallets)
    await coordinator.start()
"""

import asyncio
import logging
import time
from typing import Dict, Callable, Optional, Any, List
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PruneResult:
    """Result of a prune operation."""
    component: str
    items_pruned: int
    duration_ms: float
    error: Optional[str] = None


@dataclass
class CleanupReport:
    """Report from a cleanup cycle."""
    timestamp: float
    results: List[PruneResult]
    total_pruned: int
    total_duration_ms: float


class CleanupCoordinator:
    """
    Coordinates periodic cleanup across all components.

    Calls registered prune functions and logs results.
    """

    def __init__(
        self,
        interval_sec: float = 300.0,  # 5 minutes
        enabled: bool = True,
    ):
        self._interval = interval_sec
        self._enabled = enabled

        # Registered pruners: name -> (callable, args)
        self._pruners: Dict[str, tuple] = {}

        # History
        self._history: List[CleanupReport] = []
        self._max_history = 50

        # Metrics
        self._cycles_completed = 0
        self._total_items_pruned = 0

        # State
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def register_pruner(
        self,
        name: str,
        prune_fn: Callable,
        *args,
        **kwargs
    ):
        """
        Register a prune function.

        Args:
            name: Component name for logging
            prune_fn: Callable that returns int (items pruned) or None
            *args, **kwargs: Arguments to pass to prune_fn
        """
        self._pruners[name] = (prune_fn, args, kwargs)
        logger.debug(f"[CLEANUP] Registered pruner: {name}")

    def unregister_pruner(self, name: str):
        """Remove a pruner."""
        self._pruners.pop(name, None)

    async def run_cleanup(self) -> CleanupReport:
        """
        Run a single cleanup cycle.

        Returns CleanupReport with results from all components.
        """
        start_time = time.time()
        results = []
        total_pruned = 0

        for name, (prune_fn, args, kwargs) in self._pruners.items():
            result = await self._run_single_prune(name, prune_fn, args, kwargs)
            results.append(result)
            if result.items_pruned > 0:
                total_pruned += result.items_pruned

        total_duration = (time.time() - start_time) * 1000

        report = CleanupReport(
            timestamp=time.time(),
            results=results,
            total_pruned=total_pruned,
            total_duration_ms=total_duration,
        )

        # Update metrics
        self._cycles_completed += 1
        self._total_items_pruned += total_pruned

        # Store history
        self._history.append(report)
        if len(self._history) > self._max_history:
            self._history.pop(0)

        # Log results
        self._log_report(report)

        return report

    async def _run_single_prune(
        self,
        name: str,
        prune_fn: Callable,
        args: tuple,
        kwargs: dict
    ) -> PruneResult:
        """Run a single prune function safely."""
        start = time.time()

        try:
            # Handle both sync and async functions
            if asyncio.iscoroutinefunction(prune_fn):
                result = await prune_fn(*args, **kwargs)
            else:
                result = prune_fn(*args, **kwargs)

            items_pruned = result if isinstance(result, int) else 0
            duration = (time.time() - start) * 1000

            return PruneResult(
                component=name,
                items_pruned=items_pruned,
                duration_ms=duration,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            logger.error(f"[CLEANUP] Error pruning {name}: {e}")
            return PruneResult(
                component=name,
                items_pruned=0,
                duration_ms=duration,
                error=str(e),
            )

    def _log_report(self, report: CleanupReport):
        """Log cleanup report."""
        if report.total_pruned > 0:
            details = ", ".join(
                f"{r.component}={r.items_pruned}"
                for r in report.results
                if r.items_pruned > 0
            )
            logger.info(
                f"[CLEANUP] Pruned {report.total_pruned} items in "
                f"{report.total_duration_ms:.1f}ms: {details}"
            )
        else:
            logger.debug(
                f"[CLEANUP] Cycle complete, nothing to prune "
                f"({report.total_duration_ms:.1f}ms)"
            )

        # Log errors
        for result in report.results:
            if result.error:
                logger.warning(f"[CLEANUP] {result.component} error: {result.error}")

    async def _cleanup_loop(self):
        """Main cleanup loop."""
        logger.info(
            f"[CLEANUP] Coordinator started (interval={self._interval}s, "
            f"pruners={list(self._pruners.keys())})"
        )

        while self._running:
            await asyncio.sleep(self._interval)

            if not self._enabled:
                continue

            try:
                await self.run_cleanup()
            except Exception as e:
                logger.error(f"[CLEANUP] Loop error: {e}")

    async def start(self):
        """Start the cleanup loop."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._cleanup_loop())

    async def stop(self):
        """Stop the cleanup loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[CLEANUP] Coordinator stopped")

    def get_metrics(self) -> Dict:
        """Get coordinator metrics."""
        return {
            "cycles_completed": self._cycles_completed,
            "total_items_pruned": self._total_items_pruned,
            "pruners_registered": len(self._pruners),
            "interval_sec": self._interval,
            "enabled": self._enabled,
        }

    def get_history(self) -> List[CleanupReport]:
        """Get cleanup history."""
        return list(self._history)


# Singleton instance
_coordinator: Optional[CleanupCoordinator] = None


def get_coordinator(interval_sec: float = 300.0) -> CleanupCoordinator:
    """Get or create the global cleanup coordinator."""
    global _coordinator
    if _coordinator is None:
        _coordinator = CleanupCoordinator(interval_sec=interval_sec)
    return _coordinator


def reset_coordinator():
    """Reset the global coordinator (for testing)."""
    global _coordinator
    _coordinator = None
