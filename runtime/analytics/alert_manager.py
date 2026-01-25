"""
HLP19: Alert Manager.

Rule-based alerting for system health and trading performance.

Alert levels:
- INFO: Informational only
- WARNING: Potential issue
- ERROR: Issue requiring attention
- CRITICAL: Immediate action required
- EMERGENCY: System safety at risk
"""

import time
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Callable, Set
from threading import RLock
from collections import deque

from .types import Alert, AlertLevel


@dataclass
class AlertRule:
    """Defines an alert rule."""
    name: str
    category: str  # health, performance, risk
    level: AlertLevel
    condition: Callable[[], bool]
    message_template: str
    metric_name: Optional[str] = None
    threshold: Optional[float] = None
    cooldown_ms: int = 60000  # 1 minute default cooldown


@dataclass
class AlertConfig:
    """Configuration for alert manager."""
    # Storage
    max_alerts_in_memory: int = 1000

    # Default cooldowns
    default_cooldown_ms: int = 60000
    critical_cooldown_ms: int = 30000
    emergency_cooldown_ms: int = 10000

    # Escalation
    auto_escalate_after_repeats: int = 3
    escalation_window_ms: int = 300000  # 5 minutes


class AlertManager:
    """
    Manages rule-based alerts.

    Provides:
    - Rule registration and evaluation
    - Alert deduplication and cooldown
    - Alert escalation
    - Alert acknowledgment
    - Callback notifications
    """

    def __init__(
        self,
        config: AlertConfig = None,
        logger: logging.Logger = None
    ):
        self._config = config or AlertConfig()
        self._logger = logger or logging.getLogger(__name__)

        # Alert rules
        self._rules: Dict[str, AlertRule] = {}

        # Alert storage
        self._alerts: deque = deque(maxlen=self._config.max_alerts_in_memory)
        self._active_alerts: Dict[str, Alert] = {}  # alert_id -> Alert

        # Cooldown tracking: rule_name -> last_trigger_ns
        self._last_triggered: Dict[str, int] = {}

        # Alert count for escalation: rule_name -> count in window
        self._trigger_counts: Dict[str, List[int]] = {}

        # Callbacks
        self._on_alert: List[Callable[[Alert], None]] = []
        self._on_resolve: List[Callable[[Alert], None]] = []

        # Suppressed rules (temporarily disabled)
        self._suppressed_rules: Set[str] = set()

        # Alert counter for ID generation
        self._alert_counter = 0

        self._lock = RLock()

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    def _generate_alert_id(self) -> str:
        """Generate unique alert ID."""
        self._alert_counter += 1
        ts = int(time.time() * 1000)
        return f"alert_{ts}_{self._alert_counter}"

    def register_rule(self, rule: AlertRule):
        """Register an alert rule."""
        with self._lock:
            self._rules[rule.name] = rule
            self._logger.debug(f"Registered alert rule: {rule.name}")

    def unregister_rule(self, rule_name: str):
        """Unregister an alert rule."""
        with self._lock:
            self._rules.pop(rule_name, None)
            self._last_triggered.pop(rule_name, None)
            self._trigger_counts.pop(rule_name, None)

    def suppress_rule(self, rule_name: str):
        """Temporarily suppress a rule."""
        with self._lock:
            self._suppressed_rules.add(rule_name)

    def unsuppress_rule(self, rule_name: str):
        """Re-enable a suppressed rule."""
        with self._lock:
            self._suppressed_rules.discard(rule_name)

    def evaluate_rules(self) -> List[Alert]:
        """
        Evaluate all registered rules.

        Returns:
            List of new alerts triggered
        """
        new_alerts = []
        now_ns = self._now_ns()

        with self._lock:
            for rule_name, rule in self._rules.items():
                # Skip suppressed rules
                if rule_name in self._suppressed_rules:
                    continue

                # Check cooldown
                if not self._check_cooldown(rule_name, rule, now_ns):
                    continue

                # Evaluate condition
                try:
                    triggered = rule.condition()
                except Exception as e:
                    self._logger.debug(f"Rule {rule_name} evaluation error: {e}")
                    continue

                if triggered:
                    # Check for escalation
                    level = self._check_escalation(rule_name, rule, now_ns)

                    # Create alert
                    alert = Alert(
                        alert_id=self._generate_alert_id(),
                        level=level,
                        category=rule.category,
                        message=rule.message_template,
                        metric_name=rule.metric_name,
                        threshold=rule.threshold,
                        timestamp_ns=now_ns
                    )

                    self._alerts.append(alert)
                    self._active_alerts[alert.alert_id] = alert
                    self._last_triggered[rule_name] = now_ns

                    # Track for escalation
                    if rule_name not in self._trigger_counts:
                        self._trigger_counts[rule_name] = []
                    self._trigger_counts[rule_name].append(now_ns)

                    new_alerts.append(alert)

                    self._logger.warning(
                        f"ALERT [{alert.level.name}] {rule.category}: {alert.message}"
                    )

                    # Notify callbacks
                    for callback in self._on_alert:
                        try:
                            callback(alert)
                        except Exception as e:
                            self._logger.debug(f"Alert callback error: {e}")

        return new_alerts

    def _check_cooldown(self, rule_name: str, rule: AlertRule, now_ns: int) -> bool:
        """Check if rule is past cooldown period."""
        if rule_name not in self._last_triggered:
            return True

        last_ns = self._last_triggered[rule_name]
        elapsed_ms = (now_ns - last_ns) / 1_000_000

        # Use level-specific cooldown
        if rule.level == AlertLevel.EMERGENCY:
            cooldown = self._config.emergency_cooldown_ms
        elif rule.level == AlertLevel.CRITICAL:
            cooldown = self._config.critical_cooldown_ms
        else:
            cooldown = rule.cooldown_ms

        return elapsed_ms >= cooldown

    def _check_escalation(self, rule_name: str, rule: AlertRule, now_ns: int) -> AlertLevel:
        """Check if alert should be escalated based on repeated triggers."""
        if rule_name not in self._trigger_counts:
            return rule.level

        # Clean old counts outside window
        window_start = now_ns - (self._config.escalation_window_ms * 1_000_000)
        self._trigger_counts[rule_name] = [
            ts for ts in self._trigger_counts[rule_name]
            if ts >= window_start
        ]

        count = len(self._trigger_counts[rule_name])

        if count >= self._config.auto_escalate_after_repeats:
            # Escalate by one level
            levels = list(AlertLevel)
            current_idx = levels.index(rule.level)
            if current_idx < len(levels) - 1:
                escalated = levels[current_idx + 1]
                self._logger.warning(
                    f"Alert {rule_name} escalated from {rule.level.name} to {escalated.name} "
                    f"after {count} triggers in window"
                )
                return escalated

        return rule.level

    def trigger_alert(
        self,
        level: AlertLevel,
        category: str,
        message: str,
        metric_name: str = None,
        metric_value: float = None,
        threshold: float = None,
        details: Dict = None
    ) -> Alert:
        """
        Manually trigger an alert.

        Args:
            level: Alert severity
            category: Alert category
            message: Alert message
            metric_name: Associated metric name
            metric_value: Current metric value
            threshold: Threshold that was exceeded
            details: Additional details

        Returns:
            Created alert
        """
        with self._lock:
            alert = Alert(
                alert_id=self._generate_alert_id(),
                level=level,
                category=category,
                message=message,
                metric_name=metric_name,
                metric_value=metric_value,
                threshold=threshold,
                timestamp_ns=self._now_ns(),
                details=details or {}
            )

            self._alerts.append(alert)
            self._active_alerts[alert.alert_id] = alert

            self._logger.warning(
                f"ALERT [{level.name}] {category}: {message}"
            )

            for callback in self._on_alert:
                try:
                    callback(alert)
                except Exception as e:
                    self._logger.debug(f"Alert callback error: {e}")

            return alert

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        with self._lock:
            if alert_id not in self._active_alerts:
                return False

            alert = self._active_alerts[alert_id]
            alert.acknowledged = True
            return True

    def resolve_alert(self, alert_id: str) -> bool:
        """Resolve an alert."""
        with self._lock:
            if alert_id not in self._active_alerts:
                return False

            alert = self._active_alerts.pop(alert_id)
            alert.resolved = True

            self._logger.info(f"Alert resolved: {alert_id}")

            for callback in self._on_resolve:
                try:
                    callback(alert)
                except Exception as e:
                    self._logger.debug(f"Resolve callback error: {e}")

            return True

    def get_active_alerts(self, level: AlertLevel = None) -> List[Alert]:
        """Get active (unresolved) alerts."""
        with self._lock:
            alerts = list(self._active_alerts.values())
            if level:
                alerts = [a for a in alerts if a.level == level]
            return alerts

    def get_unacknowledged_alerts(self) -> List[Alert]:
        """Get unacknowledged alerts."""
        with self._lock:
            return [
                a for a in self._active_alerts.values()
                if not a.acknowledged
            ]

    def get_alerts_by_category(self, category: str, limit: int = 50) -> List[Alert]:
        """Get alerts by category."""
        with self._lock:
            matching = [a for a in self._alerts if a.category == category]
            return list(matching)[-limit:]

    def get_alert_history(self, limit: int = 100) -> List[Alert]:
        """Get recent alert history."""
        with self._lock:
            return list(self._alerts)[-limit:]

    def get_alert_counts(self) -> Dict[str, int]:
        """Get alert counts by level."""
        with self._lock:
            counts = {level.name: 0 for level in AlertLevel}
            for alert in self._active_alerts.values():
                counts[alert.level.name] += 1
            return counts

    def get_summary(self) -> Dict:
        """Get alert manager summary."""
        with self._lock:
            active = list(self._active_alerts.values())
            unacked = [a for a in active if not a.acknowledged]

            by_level = {}
            by_category = {}
            for alert in active:
                by_level[alert.level.name] = by_level.get(alert.level.name, 0) + 1
                by_category[alert.category] = by_category.get(alert.category, 0) + 1

            return {
                'active_alerts': len(active),
                'unacknowledged': len(unacked),
                'total_alerts': len(self._alerts),
                'registered_rules': len(self._rules),
                'suppressed_rules': len(self._suppressed_rules),
                'by_level': by_level,
                'by_category': by_category,
            }

    def add_alert_callback(self, callback: Callable[[Alert], None]):
        """Add callback for new alerts."""
        self._on_alert.append(callback)

    def add_resolve_callback(self, callback: Callable[[Alert], None]):
        """Add callback for resolved alerts."""
        self._on_resolve.append(callback)

    def clear_callbacks(self):
        """Clear all callbacks."""
        self._on_alert.clear()
        self._on_resolve.clear()


def create_standard_rules(
    metrics_collector,
    performance_tracker,
    thresholds: Dict = None
) -> List[AlertRule]:
    """
    Create standard alert rules.

    Args:
        metrics_collector: MetricsCollector instance
        performance_tracker: PerformanceTracker instance
        thresholds: Optional threshold overrides

    Returns:
        List of AlertRule instances
    """
    thresholds = thresholds or {}

    # Default thresholds
    data_staleness_warning = thresholds.get('data_staleness_warning_ms', 500)
    data_staleness_critical = thresholds.get('data_staleness_critical_ms', 1000)
    win_rate_warning = thresholds.get('win_rate_warning', 0.45)
    win_rate_critical = thresholds.get('win_rate_critical', 0.35)
    drawdown_warning = thresholds.get('drawdown_warning_pct', 0.15)
    drawdown_critical = thresholds.get('drawdown_critical_pct', 0.25)
    cpu_warning = thresholds.get('cpu_warning_pct', 70)
    cpu_critical = thresholds.get('cpu_critical_pct', 90)
    memory_warning = thresholds.get('memory_warning_pct', 75)
    memory_critical = thresholds.get('memory_critical_pct', 85)

    rules = []

    # Data staleness alerts
    rules.append(AlertRule(
        name='data_staleness_warning',
        category='health',
        level=AlertLevel.WARNING,
        condition=lambda: any(
            metrics_collector.get_data_staleness_ms(s) > data_staleness_warning
            for s in ['orderbook', 'trades', 'positions']
            if metrics_collector.get_data_staleness_ms(s) != float('inf')
        ),
        message_template=f"Data staleness exceeds {data_staleness_warning}ms",
        metric_name='data_staleness_ms',
        threshold=data_staleness_warning
    ))

    rules.append(AlertRule(
        name='data_staleness_critical',
        category='health',
        level=AlertLevel.CRITICAL,
        condition=lambda: any(
            metrics_collector.get_data_staleness_ms(s) > data_staleness_critical
            for s in ['orderbook', 'trades', 'positions']
            if metrics_collector.get_data_staleness_ms(s) != float('inf')
        ),
        message_template=f"Data staleness exceeds {data_staleness_critical}ms - CRITICAL",
        metric_name='data_staleness_ms',
        threshold=data_staleness_critical
    ))

    # Win rate alerts
    rules.append(AlertRule(
        name='win_rate_warning',
        category='performance',
        level=AlertLevel.WARNING,
        condition=lambda: (
            performance_tracker.get_win_rate() < win_rate_warning
            and len(performance_tracker._trades) >= 20
        ),
        message_template=f"Win rate below {win_rate_warning*100:.0f}%",
        metric_name='win_rate',
        threshold=win_rate_warning,
        cooldown_ms=300000  # 5 minute cooldown
    ))

    rules.append(AlertRule(
        name='win_rate_critical',
        category='performance',
        level=AlertLevel.CRITICAL,
        condition=lambda: (
            performance_tracker.get_win_rate() < win_rate_critical
            and len(performance_tracker._trades) >= 20
        ),
        message_template=f"Win rate below {win_rate_critical*100:.0f}% - CRITICAL",
        metric_name='win_rate',
        threshold=win_rate_critical,
        cooldown_ms=180000  # 3 minute cooldown
    ))

    # Drawdown alerts
    rules.append(AlertRule(
        name='drawdown_warning',
        category='risk',
        level=AlertLevel.WARNING,
        condition=lambda: performance_tracker._calculate_current_drawdown() > drawdown_warning,
        message_template=f"Drawdown exceeds {drawdown_warning*100:.0f}%",
        metric_name='drawdown_pct',
        threshold=drawdown_warning
    ))

    rules.append(AlertRule(
        name='drawdown_critical',
        category='risk',
        level=AlertLevel.CRITICAL,
        condition=lambda: performance_tracker._calculate_current_drawdown() > drawdown_critical,
        message_template=f"Drawdown exceeds {drawdown_critical*100:.0f}% - CRITICAL",
        metric_name='drawdown_pct',
        threshold=drawdown_critical
    ))

    # Resource alerts
    rules.append(AlertRule(
        name='cpu_warning',
        category='health',
        level=AlertLevel.WARNING,
        condition=lambda: metrics_collector.get_cpu_usage() > cpu_warning,
        message_template=f"CPU usage exceeds {cpu_warning}%",
        metric_name='cpu_pct',
        threshold=cpu_warning
    ))

    rules.append(AlertRule(
        name='cpu_critical',
        category='health',
        level=AlertLevel.CRITICAL,
        condition=lambda: metrics_collector.get_cpu_usage() > cpu_critical,
        message_template=f"CPU usage exceeds {cpu_critical}% - CRITICAL",
        metric_name='cpu_pct',
        threshold=cpu_critical
    ))

    rules.append(AlertRule(
        name='memory_warning',
        category='health',
        level=AlertLevel.WARNING,
        condition=lambda: metrics_collector.get_memory_usage() > memory_warning,
        message_template=f"Memory usage exceeds {memory_warning}%",
        metric_name='memory_pct',
        threshold=memory_warning
    ))

    rules.append(AlertRule(
        name='memory_critical',
        category='health',
        level=AlertLevel.CRITICAL,
        condition=lambda: metrics_collector.get_memory_usage() > memory_critical,
        message_template=f"Memory usage exceeds {memory_critical}% - CRITICAL",
        metric_name='memory_pct',
        threshold=memory_critical
    ))

    return rules
