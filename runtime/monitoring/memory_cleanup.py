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
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    None, lambda: prune_fn(*args, **kwargs)
                )

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

    async def run_disk_cleanup(self, keep_hours: int = 12) -> dict:
        """
        Run HL node disk cleanup to reclaim disk space.

        Called by resource_monitor when disk warning is triggered.

        Args:
            keep_hours: Hours of data to keep (default 12)

        Returns:
            dict with cleanup results
        """
        try:
            # Import here to avoid circular imports
            from scripts.cleanup_hl_data import cleanup_hl_data

            logger.info(f"[CLEANUP] Running HL disk cleanup (keep_hours={keep_hours})")

            # Run cleanup in executor to not block event loop
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: cleanup_hl_data(
                    keep_hours=keep_hours,
                    keep_abci_states=3,
                    dry_run=False,
                    verbose=False,
                )
            )

            total_bytes = result.get('total_bytes', 0)
            if total_bytes > 0:
                from scripts.cleanup_hl_data import format_size
                logger.info(f"[CLEANUP] HL disk cleanup freed {format_size(total_bytes)}")

            return result

        except Exception as e:
            logger.error(f"[CLEANUP] HL disk cleanup failed: {e}")
            return {'error': str(e)}

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
