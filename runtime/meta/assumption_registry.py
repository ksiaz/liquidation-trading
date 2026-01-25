"""
Assumption Registry.

Tracks explicit design assumptions and validates them against reality.
Makes implicit beliefs testable so violations can trigger defensive actions.

Philosophy:
- Every design decision rests on assumptions about reality
- Make assumptions explicit so they can be tested
- When assumptions fail, know which components to distrust
"""

import time
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Callable, Set
from threading import RLock

from .types import Assumption, AssumptionStatus


@dataclass
class RegistryConfig:
    """Configuration for assumption registry."""
    # Validation
    max_consecutive_failures: int = 3  # Mark invalid after N failures
    warning_threshold_failures: int = 2  # Mark warning after N failures

    # Revalidation
    default_revalidation_period_ns: int = 7 * 24 * 3600 * 1_000_000_000  # 7 days
    check_expiration_on_access: bool = True

    # Storage
    persist_results: bool = True
    results_file: str = "logs/assumption_results.jsonl"


class AssumptionRegistry:
    """
    Registry for tracking and validating design assumptions.

    Usage:
        registry = AssumptionRegistry()

        # Register an assumption
        registry.register(Assumption(
            name="liquidations_cluster",
            description="Liquidations cluster in time during cascades",
            category="market_structure",
            test_fn=lambda: check_cluster_coefficient() > 0.3,
            invalidation_action="disable cascade detection",
            affected_components=["CascadeLabeler", "WaveDetector"]
        ))

        # Validate all assumptions
        results = registry.validate_all()

        # Check before using a component
        if registry.is_safe_to_use("CascadeLabeler"):
            # proceed
    """

    def __init__(
        self,
        config: RegistryConfig = None,
        logger: logging.Logger = None
    ):
        self._config = config or RegistryConfig()
        self._logger = logger or logging.getLogger(__name__)

        # Assumption storage
        self._assumptions: Dict[str, Assumption] = {}

        # Component -> assumptions mapping
        self._component_dependencies: Dict[str, Set[str]] = {}

        # Validation history
        self._validation_history: List[Dict] = []

        self._lock = RLock()

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    def register(self, assumption: Assumption):
        """
        Register a design assumption.

        Args:
            assumption: The assumption to register
        """
        with self._lock:
            self._assumptions[assumption.name] = assumption

            # Build reverse mapping: component -> assumptions
            for component in assumption.affected_components:
                if component not in self._component_dependencies:
                    self._component_dependencies[component] = set()
                self._component_dependencies[component].add(assumption.name)

            self._logger.info(
                f"Registered assumption: {assumption.name} "
                f"(affects: {assumption.affected_components})"
            )

    def unregister(self, name: str):
        """Unregister an assumption."""
        with self._lock:
            if name in self._assumptions:
                assumption = self._assumptions.pop(name)
                # Clean up component mappings
                for component in assumption.affected_components:
                    if component in self._component_dependencies:
                        self._component_dependencies[component].discard(name)

    def get(self, name: str) -> Optional[Assumption]:
        """Get an assumption by name."""
        with self._lock:
            assumption = self._assumptions.get(name)
            if assumption and self._config.check_expiration_on_access:
                if assumption.is_expired(self._now_ns()):
                    assumption.status = AssumptionStatus.EXPIRED
            return assumption

    def validate(self, name: str) -> bool:
        """
        Validate a single assumption.

        Args:
            name: Assumption name

        Returns:
            True if assumption is valid, False otherwise
        """
        with self._lock:
            if name not in self._assumptions:
                self._logger.warning(f"Unknown assumption: {name}")
                return False

            assumption = self._assumptions[name]

            if assumption.test_fn is None:
                self._logger.warning(f"No test function for: {name}")
                return assumption.status == AssumptionStatus.VALID

            try:
                result = assumption.test_fn()
                assumption.last_tested_ns = self._now_ns()
                assumption.last_result = result

                if result:
                    assumption.consecutive_failures = 0
                    assumption.status = AssumptionStatus.VALID
                else:
                    assumption.consecutive_failures += 1

                    if assumption.consecutive_failures >= self._config.max_consecutive_failures:
                        assumption.status = AssumptionStatus.INVALID
                        self._logger.error(
                            f"ASSUMPTION INVALID: {name} - {assumption.invalidation_action}"
                        )
                    elif assumption.consecutive_failures >= self._config.warning_threshold_failures:
                        assumption.status = AssumptionStatus.WARNING
                        self._logger.warning(
                            f"Assumption degrading: {name} "
                            f"({assumption.consecutive_failures} consecutive failures)"
                        )

                # Record history
                self._validation_history.append({
                    'name': name,
                    'timestamp_ns': assumption.last_tested_ns,
                    'result': result,
                    'status': assumption.status.name,
                })

                return result

            except Exception as e:
                self._logger.error(f"Assumption test failed for {name}: {e}")
                assumption.consecutive_failures += 1
                if assumption.consecutive_failures >= self._config.max_consecutive_failures:
                    assumption.status = AssumptionStatus.INVALID
                return False

    def validate_all(self) -> Dict[str, bool]:
        """
        Validate all registered assumptions.

        Returns:
            Dict mapping assumption name to validation result
        """
        results = {}
        with self._lock:
            for name in self._assumptions:
                results[name] = self.validate(name)
        return results

    def validate_category(self, category: str) -> Dict[str, bool]:
        """Validate all assumptions in a category."""
        results = {}
        with self._lock:
            for name, assumption in self._assumptions.items():
                if assumption.category == category:
                    results[name] = self.validate(name)
        return results

    def get_status(self, name: str) -> AssumptionStatus:
        """Get status of an assumption."""
        assumption = self.get(name)
        if assumption is None:
            return AssumptionStatus.UNTESTED
        return assumption.status

    def is_valid(self, name: str) -> bool:
        """Check if an assumption is currently valid."""
        status = self.get_status(name)
        return status == AssumptionStatus.VALID

    def is_safe_to_use(self, component: str) -> bool:
        """
        Check if a component is safe to use based on its assumptions.

        Returns True only if ALL assumptions the component depends on are valid.
        """
        with self._lock:
            if component not in self._component_dependencies:
                return True  # No assumptions = safe

            for assumption_name in self._component_dependencies[component]:
                assumption = self._assumptions.get(assumption_name)
                if assumption is None:
                    continue

                # Check expiration
                if assumption.is_expired(self._now_ns()):
                    self._logger.warning(
                        f"Component {component} has expired assumption: {assumption_name}"
                    )
                    return False

                # Check validity
                if assumption.status in (AssumptionStatus.INVALID, AssumptionStatus.EXPIRED):
                    self._logger.warning(
                        f"Component {component} has invalid assumption: {assumption_name}"
                    )
                    return False

            return True

    def get_component_assumptions(self, component: str) -> List[Assumption]:
        """Get all assumptions a component depends on."""
        with self._lock:
            if component not in self._component_dependencies:
                return []
            return [
                self._assumptions[name]
                for name in self._component_dependencies[component]
                if name in self._assumptions
            ]

    def get_invalid_assumptions(self) -> List[Assumption]:
        """Get all invalid assumptions."""
        with self._lock:
            return [
                a for a in self._assumptions.values()
                if a.status == AssumptionStatus.INVALID
            ]

    def get_expired_assumptions(self) -> List[Assumption]:
        """Get all expired assumptions."""
        now_ns = self._now_ns()
        with self._lock:
            return [
                a for a in self._assumptions.values()
                if a.is_expired(now_ns)
            ]

    def get_assumptions_needing_revalidation(self) -> List[Assumption]:
        """Get assumptions that need revalidation."""
        now_ns = self._now_ns()
        with self._lock:
            needing = []
            for assumption in self._assumptions.values():
                if assumption.status == AssumptionStatus.UNTESTED:
                    needing.append(assumption)
                elif assumption.is_expired(now_ns):
                    needing.append(assumption)
                elif assumption.status == AssumptionStatus.WARNING:
                    needing.append(assumption)
            return needing

    def get_by_category(self, category: str) -> List[Assumption]:
        """Get all assumptions in a category."""
        with self._lock:
            return [
                a for a in self._assumptions.values()
                if a.category == category
            ]

    def get_all(self) -> List[Assumption]:
        """Get all registered assumptions."""
        with self._lock:
            return list(self._assumptions.values())

    def get_summary(self) -> Dict:
        """Get registry summary."""
        now_ns = self._now_ns()
        with self._lock:
            by_status = {}
            by_category = {}

            for assumption in self._assumptions.values():
                # Check expiration
                if assumption.is_expired(now_ns):
                    assumption.status = AssumptionStatus.EXPIRED

                status = assumption.status.name
                by_status[status] = by_status.get(status, 0) + 1

                category = assumption.category
                by_category[category] = by_category.get(category, 0) + 1

            invalid = self.get_invalid_assumptions()
            expired = self.get_expired_assumptions()

            return {
                'total_assumptions': len(self._assumptions),
                'by_status': by_status,
                'by_category': by_category,
                'invalid_count': len(invalid),
                'expired_count': len(expired),
                'invalid_names': [a.name for a in invalid],
                'expired_names': [a.name for a in expired],
                'affected_components': self._get_affected_components(invalid + expired),
            }

    def _get_affected_components(self, assumptions: List[Assumption]) -> List[str]:
        """Get components affected by given assumptions."""
        components = set()
        for assumption in assumptions:
            components.update(assumption.affected_components)
        return list(components)

    def reset(self, name: str):
        """Reset an assumption to untested state."""
        with self._lock:
            if name in self._assumptions:
                assumption = self._assumptions[name]
                assumption.status = AssumptionStatus.UNTESTED
                assumption.consecutive_failures = 0
                assumption.last_tested_ns = None
                assumption.last_result = None

    def reset_all(self):
        """Reset all assumptions to untested state."""
        with self._lock:
            for name in self._assumptions:
                self.reset(name)


def create_standard_assumptions() -> List[Assumption]:
    """
    Create standard assumptions for the liquidation trading system.

    These represent beliefs baked into the design that should be validated.
    """
    return [
        # Market structure assumptions
        Assumption(
            name="liquidations_are_observable",
            description="Liquidation events are visible in the data feed",
            category="market_structure",
            test_description="Check that liquidation events appear in recent data",
            invalidation_action="Disable liquidation-based strategies",
            affected_components=["CascadeLabeler", "LiquidationTracker"],
        ),
        Assumption(
            name="oi_reflects_positions",
            description="Open interest accurately reflects aggregate positions",
            category="market_structure",
            test_description="OI changes correlate with position changes",
            invalidation_action="Reduce confidence in OI-based signals",
            affected_components=["OITracker", "CascadeLabeler"],
        ),
        Assumption(
            name="cascades_have_structure",
            description="Cascade events have detectable wave structure",
            category="market_structure",
            test_description="Most cascades show 2+ distinct waves",
            invalidation_action="Disable wave-based entry timing",
            affected_components=["WaveDetector", "WaveStructureValidator"],
        ),

        # Data quality assumptions
        Assumption(
            name="data_latency_acceptable",
            description="Data feed latency is under acceptable threshold",
            category="data_quality",
            test_description="Median latency < 100ms",
            invalidation_action="Switch to more conservative strategies",
            affected_components=["DataCollector", "OrderExecutor"],
        ),
        Assumption(
            name="timestamps_monotonic",
            description="Timestamps in data are monotonically increasing",
            category="data_quality",
            test_description="No time reversals in recent data",
            invalidation_action="Halt system - data integrity compromised",
            affected_components=["TemporalGovernor", "DataCollector"],
        ),

        # Execution assumptions
        Assumption(
            name="fills_within_slippage",
            description="Order fills occur within expected slippage bounds",
            category="execution",
            test_description="95% of fills within 2x expected slippage",
            invalidation_action="Increase slippage estimates",
            affected_components=["OrderExecutor", "SlippageTracker"],
        ),
        Assumption(
            name="exchange_responsive",
            description="Exchange API responds within timeout",
            category="execution",
            test_description="99% of API calls complete within timeout",
            invalidation_action="Increase timeouts or reduce position size",
            affected_components=["HyperliquidClient", "OrderExecutor"],
        ),

        # Model assumptions
        Assumption(
            name="thresholds_still_valid",
            description="Calibrated thresholds still match current market",
            category="model",
            test_description="Recent success rate within expected range",
            invalidation_action="Trigger recalibration",
            affected_components=["ThresholdDiscovery", "Validators"],
        ),
        Assumption(
            name="distributions_stable",
            description="Key distributions have not significantly shifted",
            category="model",
            test_description="KS test shows no significant distribution shift",
            invalidation_action="Flag for model review",
            affected_components=["ModelHealthTracker", "PerformanceTracker"],
        ),
    ]
