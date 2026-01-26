"""
Operator Gate - Human confirmation requirements.

Requires explicit operator input for dangerous operations.
Prevents accidental or automated execution of critical actions.

Constitutional: Gate is mechanical, no interpretation of operator intent.
"""

import time
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from threading import RLock


@dataclass(frozen=True)
class OperatorConfirmation:
    """
    Record of operator confirmation.

    Immutable proof that operator approved an action.
    """
    ts_ns: int
    action: str
    operator_input: str
    success: bool


@dataclass
class DangerousAction:
    """Configuration for a dangerous action."""
    name: str
    confirmation_phrase: str
    description: str
    cooldown_ns: int = 0  # Minimum time between confirmations


# Default dangerous actions requiring confirmation
DEFAULT_DANGEROUS_ACTIONS: Dict[str, DangerousAction] = {
    "reset_kill_switch": DangerousAction(
        name="reset_kill_switch",
        confirmation_phrase="CONFIRM KILL SWITCH RESET",
        description="Reset kill switch to allow trading",
        cooldown_ns=60 * 1_000_000_000,  # 60 second cooldown
    ),
    "override_circuit_breaker": DangerousAction(
        name="override_circuit_breaker",
        confirmation_phrase="CONFIRM OVERRIDE BREAKER",
        description="Override a tripped circuit breaker",
        cooldown_ns=60 * 1_000_000_000,
    ),
    "force_position_reconciliation": DangerousAction(
        name="force_position_reconciliation",
        confirmation_phrase="CONFIRM FORCE RECONCILE",
        description="Force position state to match exchange",
        cooldown_ns=30 * 1_000_000_000,
    ),
    "resume_from_halted": DangerousAction(
        name="resume_from_halted",
        confirmation_phrase="CONFIRM RESUME FROM HALT",
        description="Resume from HALTED catastrophe state",
        cooldown_ns=120 * 1_000_000_000,  # 2 minute cooldown
    ),
    "clear_daily_limits": DangerousAction(
        name="clear_daily_limits",
        confirmation_phrase="CONFIRM CLEAR LIMITS",
        description="Clear daily trade limits",
        cooldown_ns=300 * 1_000_000_000,  # 5 minute cooldown
    ),
    "manual_position_close": DangerousAction(
        name="manual_position_close",
        confirmation_phrase="CONFIRM MANUAL CLOSE",
        description="Manually close a position",
        cooldown_ns=10 * 1_000_000_000,
    ),
}


class OperatorGate:
    """
    Requires explicit operator input for dangerous operations.

    Usage:
        gate = OperatorGate()

        # Request confirmation
        if gate.request_confirmation("reset_kill_switch"):
            # User must input exact phrase
            success = gate.verify_confirmation(
                "reset_kill_switch",
                user_input,
            )
            if success:
                # Proceed with action

    All confirmations are logged for audit.
    """

    def __init__(
        self,
        dangerous_actions: Dict[str, DangerousAction] = None,
        logger: logging.Logger = None,
    ):
        """
        Initialize operator gate.

        Args:
            dangerous_actions: Custom dangerous actions (uses defaults if None)
            logger: Logger instance
        """
        self._actions = dangerous_actions or DEFAULT_DANGEROUS_ACTIONS
        self._logger = logger or logging.getLogger(__name__)
        self._lock = RLock()

        # Confirmation history for audit
        self._confirmations: List[OperatorConfirmation] = []

        # Last confirmation time per action (for cooldown)
        self._last_confirmed: Dict[str, int] = {}

        # Pending confirmations (action requested but not yet verified)
        self._pending: Set[str] = set()

    def _now_ns(self) -> int:
        return int(time.time() * 1_000_000_000)

    def is_dangerous(self, action: str) -> bool:
        """Check if an action requires confirmation."""
        return action in self._actions

    def get_required_phrase(self, action: str) -> Optional[str]:
        """Get the required confirmation phrase for an action."""
        if action in self._actions:
            return self._actions[action].confirmation_phrase
        return None

    def get_action_description(self, action: str) -> Optional[str]:
        """Get description of a dangerous action."""
        if action in self._actions:
            return self._actions[action].description
        return None

    def request_confirmation(self, action: str) -> bool:
        """
        Request confirmation for a dangerous action.

        Args:
            action: Action name

        Returns:
            True if confirmation can proceed (not on cooldown)
        """
        if action not in self._actions:
            self._logger.warning(f"Unknown dangerous action: {action}")
            return False

        ts_ns = self._now_ns()
        action_config = self._actions[action]

        with self._lock:
            # Check cooldown
            last_ts = self._last_confirmed.get(action, 0)
            if ts_ns - last_ts < action_config.cooldown_ns:
                remaining_ns = action_config.cooldown_ns - (ts_ns - last_ts)
                remaining_s = remaining_ns / 1_000_000_000
                self._logger.warning(
                    f"Action '{action}' on cooldown for {remaining_s:.1f}s"
                )
                return False

            # Mark as pending
            self._pending.add(action)
            self._logger.info(
                f"Confirmation requested for '{action}'. "
                f"Required phrase: '{action_config.confirmation_phrase}'"
            )
            return True

    def verify_confirmation(
        self,
        action: str,
        operator_input: str,
    ) -> bool:
        """
        Verify operator confirmation.

        Args:
            action: Action name
            operator_input: Input from operator

        Returns:
            True if confirmation matches
        """
        if action not in self._actions:
            self._logger.warning(f"Unknown action for verification: {action}")
            return False

        ts_ns = self._now_ns()
        action_config = self._actions[action]
        success = (operator_input == action_config.confirmation_phrase)

        # Record confirmation attempt
        confirmation = OperatorConfirmation(
            ts_ns=ts_ns,
            action=action,
            operator_input=operator_input,
            success=success,
        )

        with self._lock:
            self._confirmations.append(confirmation)

            # Keep only recent confirmations (last 100)
            if len(self._confirmations) > 100:
                self._confirmations = self._confirmations[-100:]

            # Remove from pending
            self._pending.discard(action)

            if success:
                self._last_confirmed[action] = ts_ns
                self._logger.info(f"Operator confirmed '{action}'")
            else:
                self._logger.warning(
                    f"Operator confirmation FAILED for '{action}'. "
                    f"Expected: '{action_config.confirmation_phrase}', "
                    f"Got: '{operator_input}'"
                )

        return success

    def cancel_pending(self, action: str) -> bool:
        """
        Cancel a pending confirmation request.

        Args:
            action: Action name

        Returns:
            True if was pending and cancelled
        """
        with self._lock:
            if action in self._pending:
                self._pending.discard(action)
                self._logger.info(f"Pending confirmation cancelled: {action}")
                return True
            return False

    def get_pending_actions(self) -> List[str]:
        """Get list of actions awaiting confirmation."""
        with self._lock:
            return list(self._pending)

    def get_confirmation_history(
        self,
        action: str = None,
        limit: int = 20,
    ) -> List[OperatorConfirmation]:
        """
        Get confirmation history.

        Args:
            action: Filter by action (all if None)
            limit: Maximum records

        Returns:
            List of confirmation records
        """
        with self._lock:
            history = list(self._confirmations)

        if action:
            history = [c for c in history if c.action == action]

        return history[-limit:]

    def get_cooldown_remaining(self, action: str) -> int:
        """
        Get remaining cooldown time in nanoseconds.

        Returns 0 if not on cooldown.
        """
        if action not in self._actions:
            return 0

        ts_ns = self._now_ns()
        action_config = self._actions[action]

        with self._lock:
            last_ts = self._last_confirmed.get(action, 0)
            elapsed = ts_ns - last_ts
            remaining = action_config.cooldown_ns - elapsed

            return max(0, remaining)

    def get_status(self) -> Dict:
        """Get operator gate status summary."""
        ts_ns = self._now_ns()

        with self._lock:
            cooldowns = {}
            for action in self._actions:
                remaining = self.get_cooldown_remaining(action)
                if remaining > 0:
                    cooldowns[action] = remaining / 1_000_000_000

            return {
                "pending_count": len(self._pending),
                "pending_actions": list(self._pending),
                "confirmation_count": len(self._confirmations),
                "cooldowns_seconds": cooldowns,
                "registered_actions": list(self._actions.keys()),
            }
