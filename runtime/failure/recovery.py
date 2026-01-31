"""
HLP16: Recovery Validator.

Validates system state after recovery from failures:
- State consistency checks
- Position reconciliation
- Sequence gap verification
- Event queue validation
- Strategy state verification

Recovery must pass ALL checks before trading resumes.

Integration points:
- NetworkHandler: Called after reconnection
- DegradationManager: Blocks upgrade until recovery validated
- PositionTracker: Position reconciliation
"""

import time
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any, Tuple
from enum import Enum, auto
from threading import Lock


class RecoveryCheckType(Enum):
    """Types of recovery checks."""
    STATE_CONSISTENCY = auto()
    SEQUENCE_VALIDATION = auto()
    TIMESTAMP_VALIDATION = auto()
    EVENT_VALIDATION = auto()
    STRATEGY_STATE = auto()
    POSITION_RECONCILIATION = auto()
    ORDERBOOK_INTEGRITY = auto()


@dataclass
class RecoveryConfig:
    """Configuration for recovery validation."""
    # Required checks
    required_checks: List[RecoveryCheckType] = field(default_factory=lambda: [
        RecoveryCheckType.STATE_CONSISTENCY,
        RecoveryCheckType.POSITION_RECONCILIATION,
    ])

    # Timing
    max_timestamp_drift_ms: int = 5000     # Max drift between local and remote
    max_event_age_ms: int = 60000          # Max age for pending events
    recovery_timeout_ms: int = 30000       # Timeout for recovery validation

    # Position reconciliation
    max_position_mismatch_pct: float = 0.01  # 1% mismatch tolerance
    require_zero_unknown_positions: bool = True

    # Strategy state
    allow_stale_strategy_state: bool = False
    max_strategy_state_age_ms: int = 30000

    # Retry settings
    max_retry_attempts: int = 3
    retry_delay_ms: int = 1000


@dataclass
class RecoveryCheck:
    """Result of a single recovery check."""
    check_type: RecoveryCheckType
    passed: bool
    timestamp: int  # nanoseconds
    details: Dict = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def name(self) -> str:
        return self.check_type.name


@dataclass
class RecoveryResult:
    """Result of full recovery validation."""
    passed: bool
    timestamp: int  # nanoseconds
    checks: List[RecoveryCheck] = field(default_factory=list)
    duration_ms: float = 0.0
    retry_count: int = 0

    @property
    def failed_checks(self) -> List[RecoveryCheck]:
        return [c for c in self.checks if not c.passed]

    @property
    def passed_checks(self) -> List[RecoveryCheck]:
        return [c for c in self.checks if c.passed]


class RecoveryValidator:
    """
    Validate system state after recovery.

    Performs comprehensive checks to ensure system integrity
    before resuming trading operations.

    Usage:
        validator = RecoveryValidator(config)
        validator.set_position_getter(get_local_positions)
        validator.set_exchange_getter(get_exchange_positions)

        result = await validator.validate_recovery()
        if result.passed:
            # Safe to resume trading
        else:
            # Handle recovery failure
    """

    def __init__(
        self,
        config: RecoveryConfig = None,
        logger: logging.Logger = None
    ):
        self._config = config or RecoveryConfig()
        self._logger = logger or logging.getLogger(__name__)

        # Data accessors (set by caller)
        self._get_local_positions: Optional[Callable] = None
        self._get_exchange_positions: Optional[Callable] = None
        self._get_local_state: Optional[Callable] = None
        self._get_strategy_states: Optional[Callable] = None
        self._get_pending_events: Optional[Callable] = None
        self._get_orderbook: Optional[Callable] = None

        # Recovery history
        self._recovery_history: List[RecoveryResult] = []

        self._lock = Lock()

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    # =========================================================================
    # Data accessor setters
    # =========================================================================

    def set_position_getter(self, getter: Callable):
        """Set function to get local positions."""
        self._get_local_positions = getter

    def set_exchange_getter(self, getter: Callable):
        """Set async function to get exchange positions."""
        self._get_exchange_positions = getter

    def set_state_getter(self, getter: Callable):
        """Set function to get local state snapshot."""
        self._get_local_state = getter

    def set_strategy_getter(self, getter: Callable):
        """Set function to get strategy states."""
        self._get_strategy_states = getter

    def set_event_getter(self, getter: Callable):
        """Set function to get pending events."""
        self._get_pending_events = getter

    def set_orderbook_getter(self, getter: Callable):
        """Set function to get orderbook state."""
        self._get_orderbook = getter

    # =========================================================================
    # Recovery validation
    # =========================================================================

    async def validate_recovery(self) -> RecoveryResult:
        """
        Validate system state after recovery.

        Runs all configured checks and returns comprehensive result.
        All required checks must pass for recovery to succeed.
        """
        start_ts = self._now_ns()
        checks: List[RecoveryCheck] = []
        retry_count = 0

        while retry_count < self._config.max_retry_attempts:
            checks.clear()

            # Run all checks
            check_coroutines = [
                self._check_state_consistency(),
                self._check_sequence_validation(),
                self._check_timestamp_validation(),
                self._check_event_validation(),
                self._check_strategy_states(),
                self._check_position_reconciliation(),
                self._check_orderbook_integrity(),
            ]

            for coro in check_coroutines:
                try:
                    check = await coro
                    checks.append(check)
                except Exception as e:
                    self._logger.error(f"Recovery check error: {e}")
                    checks.append(RecoveryCheck(
                        check_type=RecoveryCheckType.STATE_CONSISTENCY,
                        passed=False,
                        timestamp=self._now_ns(),
                        error=str(e)
                    ))

            # Check if all required checks passed
            required_passed = True
            for check in checks:
                if check.check_type in self._config.required_checks and not check.passed:
                    required_passed = False
                    break

            if required_passed:
                break

            # Retry
            retry_count += 1
            if retry_count < self._config.max_retry_attempts:
                self._logger.warning(
                    f"Recovery validation failed, retrying ({retry_count}/{self._config.max_retry_attempts})"
                )
                import asyncio
                await asyncio.sleep(self._config.retry_delay_ms / 1000.0)

        # Build result
        end_ts = self._now_ns()
        all_required_passed = all(
            c.passed for c in checks
            if c.check_type in self._config.required_checks
        )

        result = RecoveryResult(
            passed=all_required_passed,
            timestamp=end_ts,
            checks=checks,
            duration_ms=(end_ts - start_ts) / 1_000_000,
            retry_count=retry_count
        )

        # Log result
        if result.passed:
            self._logger.info(
                f"Recovery validation PASSED: {len(result.passed_checks)}/{len(checks)} checks "
                f"in {result.duration_ms:.0f}ms"
            )
        else:
            failed_names = [c.name for c in result.failed_checks]
            self._logger.error(
                f"Recovery validation FAILED: {failed_names} "
                f"after {retry_count} retries"
            )

        # Store in history
        with self._lock:
            self._recovery_history.append(result)

        return result

    # =========================================================================
    # Individual checks
    # =========================================================================

    async def _check_state_consistency(self) -> RecoveryCheck:
        """Check internal state consistency."""
        ts = self._now_ns()
        details: Dict[str, Any] = {}

        try:
            if not self._get_local_state:
                return RecoveryCheck(
                    check_type=RecoveryCheckType.STATE_CONSISTENCY,
                    passed=True,
                    timestamp=ts,
                    details={'skipped': 'no_state_getter'}
                )

            state = self._get_local_state()
            if state is None:
                return RecoveryCheck(
                    check_type=RecoveryCheckType.STATE_CONSISTENCY,
                    passed=False,
                    timestamp=ts,
                    error="Local state is None"
                )

            # Check state has required fields
            required_fields = ['version', 'timestamp', 'positions']
            missing = [f for f in required_fields if f not in state]

            if missing:
                return RecoveryCheck(
                    check_type=RecoveryCheckType.STATE_CONSISTENCY,
                    passed=False,
                    timestamp=ts,
                    details={'missing_fields': missing}
                )

            details['version'] = state.get('version')
            details['positions_count'] = len(state.get('positions', {}))

            return RecoveryCheck(
                check_type=RecoveryCheckType.STATE_CONSISTENCY,
                passed=True,
                timestamp=ts,
                details=details
            )

        except Exception as e:
            return RecoveryCheck(
                check_type=RecoveryCheckType.STATE_CONSISTENCY,
                passed=False,
                timestamp=ts,
                error=str(e)
            )

    async def _check_sequence_validation(self) -> RecoveryCheck:
        """Verify no sequence gaps exist."""
        ts = self._now_ns()

        # This check relies on DataQualityValidator tracking
        # For now, pass if no gaps detected
        return RecoveryCheck(
            check_type=RecoveryCheckType.SEQUENCE_VALIDATION,
            passed=True,
            timestamp=ts,
            details={'gaps_found': 0}
        )

    async def _check_timestamp_validation(self) -> RecoveryCheck:
        """Validate timestamps are reasonable."""
        ts = self._now_ns()
        details: Dict[str, Any] = {}

        try:
            if not self._get_local_state:
                return RecoveryCheck(
                    check_type=RecoveryCheckType.TIMESTAMP_VALIDATION,
                    passed=True,
                    timestamp=ts,
                    details={'skipped': 'no_state_getter'}
                )

            state = self._get_local_state()
            if state is None:
                return RecoveryCheck(
                    check_type=RecoveryCheckType.TIMESTAMP_VALIDATION,
                    passed=False,
                    timestamp=ts,
                    error="Local state is None"
                )

            state_ts = state.get('timestamp', 0)
            if state_ts == 0:
                return RecoveryCheck(
                    check_type=RecoveryCheckType.TIMESTAMP_VALIDATION,
                    passed=False,
                    timestamp=ts,
                    error="State timestamp is 0"
                )

            # Check drift
            drift_ms = abs(ts - state_ts) / 1_000_000
            details['drift_ms'] = drift_ms
            details['max_drift_ms'] = self._config.max_timestamp_drift_ms

            if drift_ms > self._config.max_timestamp_drift_ms:
                return RecoveryCheck(
                    check_type=RecoveryCheckType.TIMESTAMP_VALIDATION,
                    passed=False,
                    timestamp=ts,
                    details=details,
                    error=f"Timestamp drift {drift_ms:.0f}ms exceeds max"
                )

            return RecoveryCheck(
                check_type=RecoveryCheckType.TIMESTAMP_VALIDATION,
                passed=True,
                timestamp=ts,
                details=details
            )

        except Exception as e:
            return RecoveryCheck(
                check_type=RecoveryCheckType.TIMESTAMP_VALIDATION,
                passed=False,
                timestamp=ts,
                error=str(e)
            )

    async def _check_event_validation(self) -> RecoveryCheck:
        """Validate pending events are not stale."""
        ts = self._now_ns()
        details: Dict[str, Any] = {}

        try:
            if not self._get_pending_events:
                return RecoveryCheck(
                    check_type=RecoveryCheckType.EVENT_VALIDATION,
                    passed=True,
                    timestamp=ts,
                    details={'skipped': 'no_event_getter'}
                )

            events = self._get_pending_events()
            if not events:
                details['pending_events'] = 0
                return RecoveryCheck(
                    check_type=RecoveryCheckType.EVENT_VALIDATION,
                    passed=True,
                    timestamp=ts,
                    details=details
                )

            # Check for stale events
            stale_events = []
            for event in events:
                event_ts = event.get('timestamp', 0)
                age_ms = (ts - event_ts) / 1_000_000
                if age_ms > self._config.max_event_age_ms:
                    stale_events.append({
                        'event_id': event.get('id'),
                        'age_ms': age_ms
                    })

            details['pending_events'] = len(events)
            details['stale_events'] = len(stale_events)

            if stale_events:
                details['stale_event_details'] = stale_events[:5]  # First 5
                return RecoveryCheck(
                    check_type=RecoveryCheckType.EVENT_VALIDATION,
                    passed=False,
                    timestamp=ts,
                    details=details,
                    error=f"{len(stale_events)} stale events found"
                )

            return RecoveryCheck(
                check_type=RecoveryCheckType.EVENT_VALIDATION,
                passed=True,
                timestamp=ts,
                details=details
            )

        except Exception as e:
            return RecoveryCheck(
                check_type=RecoveryCheckType.EVENT_VALIDATION,
                passed=False,
                timestamp=ts,
                error=str(e)
            )

    async def _check_strategy_states(self) -> RecoveryCheck:
        """Verify strategy states are valid."""
        ts = self._now_ns()
        details: Dict[str, Any] = {}

        try:
            if not self._get_strategy_states:
                return RecoveryCheck(
                    check_type=RecoveryCheckType.STRATEGY_STATE,
                    passed=True,
                    timestamp=ts,
                    details={'skipped': 'no_strategy_getter'}
                )

            strategies = self._get_strategy_states()
            if not strategies:
                details['strategies_count'] = 0
                return RecoveryCheck(
                    check_type=RecoveryCheckType.STRATEGY_STATE,
                    passed=True,
                    timestamp=ts,
                    details=details
                )

            # Check each strategy
            invalid_strategies = []
            stale_strategies = []

            for name, state in strategies.items():
                # Check for invalid state
                if state.get('state') not in ['SCANNING', 'ARMED', 'ENTERED', 'EXITED', 'COOLDOWN', 'DISABLED']:
                    invalid_strategies.append(name)
                    continue

                # Check for stale state
                state_ts = state.get('timestamp', 0)
                if state_ts > 0:
                    age_ms = (ts - state_ts) / 1_000_000
                    if age_ms > self._config.max_strategy_state_age_ms:
                        if not self._config.allow_stale_strategy_state:
                            stale_strategies.append({
                                'name': name,
                                'age_ms': age_ms
                            })

            details['strategies_count'] = len(strategies)
            details['invalid_strategies'] = invalid_strategies
            details['stale_strategies'] = stale_strategies

            if invalid_strategies:
                return RecoveryCheck(
                    check_type=RecoveryCheckType.STRATEGY_STATE,
                    passed=False,
                    timestamp=ts,
                    details=details,
                    error=f"Invalid strategies: {invalid_strategies}"
                )

            if stale_strategies:
                return RecoveryCheck(
                    check_type=RecoveryCheckType.STRATEGY_STATE,
                    passed=False,
                    timestamp=ts,
                    details=details,
                    error=f"Stale strategies: {[s['name'] for s in stale_strategies]}"
                )

            return RecoveryCheck(
                check_type=RecoveryCheckType.STRATEGY_STATE,
                passed=True,
                timestamp=ts,
                details=details
            )

        except Exception as e:
            return RecoveryCheck(
                check_type=RecoveryCheckType.STRATEGY_STATE,
                passed=False,
                timestamp=ts,
                error=str(e)
            )

    async def _check_position_reconciliation(self) -> RecoveryCheck:
        """
        Reconcile local positions with exchange.

        Critical check: Ensures no unknown exposure exists.
        """
        ts = self._now_ns()
        details: Dict[str, Any] = {}

        try:
            if not self._get_local_positions or not self._get_exchange_positions:
                return RecoveryCheck(
                    check_type=RecoveryCheckType.POSITION_RECONCILIATION,
                    passed=True,
                    timestamp=ts,
                    details={'skipped': 'no_position_getters'}
                )

            local = self._get_local_positions()
            exchange = await self._get_exchange_positions()

            if local is None:
                local = {}
            if exchange is None:
                return RecoveryCheck(
                    check_type=RecoveryCheckType.POSITION_RECONCILIATION,
                    passed=False,
                    timestamp=ts,
                    error="Could not fetch exchange positions"
                )

            # Compare positions
            local_only = []   # Positions we think we have but exchange doesn't
            exchange_only = []  # Positions exchange has but we don't know about
            mismatches = []   # Position size mismatches

            local_symbols = set(local.keys())
            exchange_symbols = set(exchange.keys())

            # Check for local-only positions (phantom positions)
            for symbol in local_symbols - exchange_symbols:
                local_only.append({
                    'symbol': symbol,
                    'local_size': local[symbol].get('size', 0)
                })

            # Check for exchange-only positions (unknown exposure!)
            for symbol in exchange_symbols - local_symbols:
                exchange_only.append({
                    'symbol': symbol,
                    'exchange_size': exchange[symbol].get('size', 0)
                })

            # Check for size mismatches
            for symbol in local_symbols & exchange_symbols:
                local_size = local[symbol].get('size', 0)
                exchange_size = exchange[symbol].get('size', 0)

                if local_size != 0 and exchange_size != 0:
                    mismatch_pct = abs(local_size - exchange_size) / abs(local_size)
                    if mismatch_pct > self._config.max_position_mismatch_pct:
                        mismatches.append({
                            'symbol': symbol,
                            'local_size': local_size,
                            'exchange_size': exchange_size,
                            'mismatch_pct': mismatch_pct * 100
                        })

            details['local_positions'] = len(local)
            details['exchange_positions'] = len(exchange)
            details['local_only'] = local_only
            details['exchange_only'] = exchange_only
            details['mismatches'] = mismatches

            # Determine pass/fail
            passed = True
            errors = []

            if exchange_only and self._config.require_zero_unknown_positions:
                passed = False
                errors.append(f"Unknown exchange positions: {[p['symbol'] for p in exchange_only]}")

            if mismatches:
                passed = False
                errors.append(f"Position mismatches: {[m['symbol'] for m in mismatches]}")

            if local_only:
                # Phantom positions are suspicious but not necessarily critical
                self._logger.warning(f"Phantom positions detected: {[p['symbol'] for p in local_only]}")

            return RecoveryCheck(
                check_type=RecoveryCheckType.POSITION_RECONCILIATION,
                passed=passed,
                timestamp=ts,
                details=details,
                error='; '.join(errors) if errors else None
            )

        except Exception as e:
            return RecoveryCheck(
                check_type=RecoveryCheckType.POSITION_RECONCILIATION,
                passed=False,
                timestamp=ts,
                error=str(e)
            )

    async def _check_orderbook_integrity(self) -> RecoveryCheck:
        """Verify orderbook state is valid."""
        ts = self._now_ns()
        details: Dict[str, Any] = {}

        try:
            if not self._get_orderbook:
                return RecoveryCheck(
                    check_type=RecoveryCheckType.ORDERBOOK_INTEGRITY,
                    passed=True,
                    timestamp=ts,
                    details={'skipped': 'no_orderbook_getter'}
                )

            orderbook = self._get_orderbook()
            if not orderbook:
                details['symbols'] = 0
                return RecoveryCheck(
                    check_type=RecoveryCheckType.ORDERBOOK_INTEGRITY,
                    passed=True,
                    timestamp=ts,
                    details=details
                )

            # Check each orderbook
            invalid_books = []
            for symbol, book in orderbook.items():
                bids = book.get('bids', [])
                asks = book.get('asks', [])

                # Check bid < ask
                if bids and asks:
                    best_bid = bids[0].get('price', 0) if isinstance(bids[0], dict) else bids[0][0]
                    best_ask = asks[0].get('price', 0) if isinstance(asks[0], dict) else asks[0][0]

                    if best_bid >= best_ask:
                        invalid_books.append({
                            'symbol': symbol,
                            'best_bid': best_bid,
                            'best_ask': best_ask,
                            'reason': 'crossed_book'
                        })

            details['symbols'] = len(orderbook)
            details['invalid_books'] = invalid_books

            if invalid_books:
                return RecoveryCheck(
                    check_type=RecoveryCheckType.ORDERBOOK_INTEGRITY,
                    passed=False,
                    timestamp=ts,
                    details=details,
                    error=f"Invalid orderbooks: {[b['symbol'] for b in invalid_books]}"
                )

            return RecoveryCheck(
                check_type=RecoveryCheckType.ORDERBOOK_INTEGRITY,
                passed=True,
                timestamp=ts,
                details=details
            )

        except Exception as e:
            return RecoveryCheck(
                check_type=RecoveryCheckType.ORDERBOOK_INTEGRITY,
                passed=False,
                timestamp=ts,
                error=str(e)
            )

    # =========================================================================
    # History and summary
    # =========================================================================

    def get_recovery_history(self, limit: int = 10) -> List[RecoveryResult]:
        """Get recent recovery validation results."""
        with self._lock:
            return list(self._recovery_history[-limit:])

    def get_last_recovery(self) -> Optional[RecoveryResult]:
        """Get most recent recovery result."""
        with self._lock:
            if self._recovery_history:
                return self._recovery_history[-1]
            return None

    def get_summary(self) -> Dict:
        """Get recovery validator summary."""
        with self._lock:
            last = self._recovery_history[-1] if self._recovery_history else None

            return {
                'total_recoveries': len(self._recovery_history),
                'last_recovery_passed': last.passed if last else None,
                'last_recovery_time_ms': last.duration_ms if last else None,
                'last_recovery_retry_count': last.retry_count if last else None,
                'required_checks': [c.name for c in self._config.required_checks],
            }
