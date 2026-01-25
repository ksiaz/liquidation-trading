"""
M6 Executor - Execution Layer Orchestrator

FROZEN: 2026-01-25
REASON: Production-verified EP4 pipeline implementation
REQUIRES: Logged evidence from Phase V1-LIVE runs to modify

Wires observation → policy → arbitration → execution pipeline.

Flow:
1. Receive ObservationSnapshot
2. Generate mandates via PolicyAdapter
3. Arbitrate mandates (highest authority wins)
4. Convert mandate to EP4 action
5. Execute via EP4 pipeline
6. Track position state

Constitutional Constraints:
- Halt on observation FAILED status
- Single position invariant
- No market interpretation
- Deterministic execution

Hardenings:
- E6: Full pipeline implementation
- Uses E1-E5 from OrderExecutor

See Also:
- runtime/executor/controller.py - Canonical theorem-verified execution path
"""

import time
import logging
import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from decimal import Decimal
from enum import Enum

from observation.types import (
    ObservationSnapshot,
    ObservationStatus,
    SystemHaltedException,
    TrendRegimeContext
)
from runtime.arbitration.types import (
    Mandate,
    MandateType,
    Action,
    ActionType
)
from runtime.position.types import (
    Position,
    PositionState,
    Direction
)
from runtime.policy_adapter import PolicyAdapter, AdapterConfig

# EP4 execution pipeline
from execution.ep4_execution import (
    ExecutionOrchestrator,
    PolicyDecision,
    DecisionCode,
    ExecutionContext,
    ExecutionResult,
    ExecutionResultCode
)
from execution.ep4_action_schemas import (
    OpenPositionAction,
    ClosePositionAction,
    NoOpAction,
    Side,
    OrderType as EP4OrderType
)
from execution.ep4_risk_gates import RiskConfig, RiskContext
from execution.ep4_hyperliquid_adapter import (
    HyperliquidExchangeAdapter,
    HyperliquidConfig
)

# Risk management
from runtime.risk.capital_manager import CapitalManager, CapitalManagerConfig
from runtime.validation.entry_quality import EntryQualityScorer


class M6State(Enum):
    """M6 executor state."""
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"
    HALTED = "HALTED"  # Observation FAILED


@dataclass
class M6Config:
    """M6 executor configuration."""
    # Symbols to trade
    symbols: List[str] = field(default_factory=lambda: ["BTC", "ETH"])

    # Single position invariant
    max_concurrent_positions: int = 1

    # Policy adapter config
    enable_cascade_sniper: bool = True
    cascade_sniper_entry_mode: str = "ABSORPTION_REVERSAL"

    # Risk config
    max_position_size: float = 1.0
    max_notional: float = 10000.0
    max_leverage: float = 5.0
    max_actions_per_minute: int = 10
    cooldown_seconds: float = 60.0  # H1-A entry cooldown

    # Hyperliquid config
    use_testnet: bool = True
    private_key: Optional[str] = None
    wallet_address: Optional[str] = None

    # Stop loss percentage (from entry)
    default_stop_pct: float = 0.02  # 2%


@dataclass
class ExecutionCycleResult:
    """Result of one execution cycle."""
    timestamp: float
    symbol: str
    mandates_generated: int
    winning_mandate: Optional[MandateType]
    action_taken: Optional[ActionType]
    execution_result: Optional[ExecutionResultCode]
    error: Optional[str] = None


class M6Executor:
    """
    M6 Execution Layer Orchestrator.

    Implements full observation → execution pipeline with:
    - Policy mandate generation
    - Authority-based arbitration
    - EP4 deterministic execution
    - Position state tracking
    """

    def __init__(
        self,
        config: M6Config = None,
        logger: logging.Logger = None
    ):
        self._config = config or M6Config()
        self._logger = logger or logging.getLogger(__name__)
        self._state = M6State.STOPPED

        # Position tracking (single position invariant)
        self._positions: Dict[str, Position] = {}
        for symbol in self._config.symbols:
            self._positions[symbol] = Position.create_flat(symbol)

        # Policy adapter
        adapter_config = AdapterConfig(
            enable_cascade_sniper=self._config.enable_cascade_sniper,
            cascade_sniper_entry_mode=self._config.cascade_sniper_entry_mode
        )
        self._policy_adapter = PolicyAdapter(adapter_config)

        # Entry quality scorer
        self._entry_scorer = EntryQualityScorer()

        # Capital manager
        self._capital_manager = CapitalManager(CapitalManagerConfig())

        # Risk config for EP4
        self._risk_config = RiskConfig(
            max_position_size=self._config.max_position_size,
            max_notional=self._config.max_notional,
            max_leverage=self._config.max_leverage,
            max_actions_per_minute=self._config.max_actions_per_minute,
            cooldown_seconds=self._config.cooldown_seconds
        )

        # Hyperliquid adapter
        hl_config = HyperliquidConfig(
            use_testnet=self._config.use_testnet,
            private_key=self._config.private_key,
            wallet_address=self._config.wallet_address
        )
        self._exchange_adapter = HyperliquidExchangeAdapter(config=hl_config)

        # EP4 orchestrator
        self._orchestrator = ExecutionOrchestrator(
            risk_config=self._risk_config,
            exchange_adapter=self._exchange_adapter
        )

        # Execution tracking
        self._last_action_time: float = 0.0
        self._actions_this_minute: int = 0
        self._minute_start: float = 0.0

        # Cycle results for telemetry
        self._recent_cycles: List[ExecutionCycleResult] = []

    def execute(self, observation_snapshot: ObservationSnapshot) -> Optional[ExecutionCycleResult]:
        """
        Execute one cycle of the M6 pipeline.

        Args:
            observation_snapshot: Current observation state

        Returns:
            ExecutionCycleResult or None if no action

        Raises:
            SystemHaltedException: If observation status is FAILED
        """
        timestamp = time.time()

        # HALT CHECK: Observation FAILED = system halt
        if observation_snapshot.status == ObservationStatus.FAILED:
            self._state = M6State.HALTED
            raise SystemHaltedException("Observation FAILED - M6 halted")

        # UNINITIALIZED = skip cycle (normal during warmup)
        if observation_snapshot.status == ObservationStatus.UNINITIALIZED:
            return None

        self._state = M6State.RUNNING

        # Process each symbol
        results = []
        for symbol in self._config.symbols:
            result = self._execute_symbol(
                symbol=symbol,
                snapshot=observation_snapshot,
                timestamp=timestamp
            )
            if result:
                results.append(result)
                self._recent_cycles.append(result)

        # Keep only recent cycles
        if len(self._recent_cycles) > 100:
            self._recent_cycles = self._recent_cycles[-100:]

        # Return first result (single position invariant)
        return results[0] if results else None

    def _execute_symbol(
        self,
        symbol: str,
        snapshot: ObservationSnapshot,
        timestamp: float
    ) -> Optional[ExecutionCycleResult]:
        """Execute pipeline for one symbol."""
        try:
            # Get current position
            position = self._positions.get(symbol, Position.create_flat(symbol))

            # STEP 1: Generate mandates via PolicyAdapter
            mandates = self._policy_adapter.generate_mandates(
                observation_snapshot=snapshot,
                symbol=symbol,
                timestamp=timestamp,
                position_state=position
            )

            if not mandates:
                return None

            # STEP 2: Arbitrate mandates (highest authority wins)
            winning_mandate = self._arbitrate(mandates)

            if winning_mandate is None:
                return None

            # STEP 3: Convert mandate to action
            action = Action.from_mandate(winning_mandate)

            # STEP 4: Check if action is valid for current position state
            if not self._is_action_valid(action, position):
                self._logger.debug(
                    f"M6: Action {action.type.value} invalid for position state {position.state.value}"
                )
                return ExecutionCycleResult(
                    timestamp=timestamp,
                    symbol=symbol,
                    mandates_generated=len(mandates),
                    winning_mandate=winning_mandate.type,
                    action_taken=None,
                    execution_result=None,
                    error="Invalid action for position state"
                )

            # STEP 5: Check single position invariant
            if action.type == ActionType.ENTRY:
                active_positions = sum(
                    1 for p in self._positions.values()
                    if p.state != PositionState.FLAT
                )
                if active_positions >= self._config.max_concurrent_positions:
                    self._logger.info(
                        f"M6: Entry blocked - {active_positions} active positions "
                        f"(max {self._config.max_concurrent_positions})"
                    )
                    return ExecutionCycleResult(
                        timestamp=timestamp,
                        symbol=symbol,
                        mandates_generated=len(mandates),
                        winning_mandate=winning_mandate.type,
                        action_taken=None,
                        execution_result=None,
                        error="Single position invariant"
                    )

            # STEP 6: Execute via EP4 pipeline
            result = self._execute_action(action, position, timestamp)

            # STEP 7: Update position state on success
            if result.result_code == ExecutionResultCode.SUCCESS:
                self._update_position_state(symbol, action)

            return ExecutionCycleResult(
                timestamp=timestamp,
                symbol=symbol,
                mandates_generated=len(mandates),
                winning_mandate=winning_mandate.type,
                action_taken=action.type,
                execution_result=result.result_code
            )

        except Exception as e:
            self._logger.error(f"M6: Error executing {symbol}: {e}")
            return ExecutionCycleResult(
                timestamp=timestamp,
                symbol=symbol,
                mandates_generated=0,
                winning_mandate=None,
                action_taken=None,
                execution_result=None,
                error=str(e)
            )

    def _arbitrate(self, mandates: List[Mandate]) -> Optional[Mandate]:
        """
        Arbitrate mandates - highest authority wins.

        Authority hierarchy: EXIT > BLOCK > REDUCE > ENTRY > HOLD
        """
        if not mandates:
            return None

        # Sort by type value (higher = more authority) then by authority score
        sorted_mandates = sorted(
            mandates,
            key=lambda m: (m.type.value, m.authority),
            reverse=True
        )

        winner = sorted_mandates[0]

        # BLOCK means no action (reject all lower mandates)
        if winner.type == MandateType.BLOCK:
            self._logger.info(f"M6: BLOCK mandate wins - no action")
            return None

        return winner

    def _is_action_valid(self, action: Action, position: Position) -> bool:
        """Check if action is valid for current position state."""
        state = position.state

        if action.type == ActionType.ENTRY:
            # Can only enter from FLAT
            return state == PositionState.FLAT

        elif action.type == ActionType.EXIT:
            # Can only exit from OPEN
            return state == PositionState.OPEN

        elif action.type == ActionType.REDUCE:
            # Can only reduce from OPEN
            return state == PositionState.OPEN

        elif action.type in (ActionType.HOLD, ActionType.NO_ACTION):
            # Always valid
            return True

        return False

    def _execute_action(
        self,
        action: Action,
        position: Position,
        timestamp: float
    ) -> ExecutionResult:
        """Execute action via EP4 pipeline."""
        # Build EP4 action
        ep4_action = self._build_ep4_action(action, position, timestamp)

        if ep4_action is None:
            # HOLD or NO_ACTION
            return ExecutionResult(
                result_code=ExecutionResultCode.NOOP,
                action_id=None,
                trace_id=f"m6_{timestamp}",
                timestamp=timestamp,
                reason_code="NO_ACTION",
                audit_log="{}"
            )

        # Build policy decision
        decision = PolicyDecision(
            decision_code=DecisionCode.AUTHORIZED_ACTION,
            action=ep4_action,
            reason_code="M6_MANDATE",
            timestamp=timestamp,
            trace_id=f"m6_{action.symbol}_{timestamp}"
        )

        # Build execution context
        context = ExecutionContext(
            exchange="HYPERLIQUID",
            symbol=action.symbol,
            account_id=self._config.wallet_address or "unknown",
            timestamp=timestamp
        )

        # Build risk context
        risk_context = self._build_risk_context(position, timestamp)

        # Execute via EP4 orchestrator
        result = self._orchestrator.execute_policy_decision(
            decision=decision,
            context=context,
            risk_context=risk_context
        )

        self._logger.info(
            f"M6: Executed {action.type.value} for {action.symbol}: {result.result_code.value}"
        )

        return result

    def _build_ep4_action(
        self,
        action: Action,
        position: Position,
        timestamp: float
    ):
        """Build EP4 action from M6 action."""
        action_id = f"m6_{action.symbol}_{int(timestamp * 1000)}"

        if action.type == ActionType.ENTRY:
            # Determine side from action direction
            side = Side.LONG if action.direction == "LONG" else Side.SHORT
            return OpenPositionAction(
                action_id=action_id,
                symbol=action.symbol,
                side=side,
                quantity=self._config.max_position_size,
                order_type=EP4OrderType.MARKET,
                limit_price=None
            )

        elif action.type == ActionType.EXIT:
            return ClosePositionAction(
                action_id=action_id,
                symbol=action.symbol,
                quantity=None  # Full close
            )

        elif action.type == ActionType.REDUCE:
            # Reduce by half
            reduce_qty = float(position.quantity) / 2
            return ClosePositionAction(
                action_id=action_id,
                symbol=action.symbol,
                quantity=reduce_qty
            )

        else:
            return NoOpAction(action_id=action_id)

    def _build_risk_context(
        self,
        position: Position,
        timestamp: float
    ) -> RiskContext:
        """Build EP4 risk context."""
        # Update action tracking
        if timestamp - self._minute_start > 60:
            self._minute_start = timestamp
            self._actions_this_minute = 0

        time_since_last = timestamp - self._last_action_time

        # Get current price from capital manager or use placeholder
        current_price = 50000.0  # Placeholder - should come from collector

        return RiskContext(
            current_price=current_price,
            account_balance=self._capital_manager._capital,
            current_position_size=float(position.quantity),
            actions_in_last_minute=self._actions_this_minute,
            time_since_last_action=time_since_last
        )

    def _update_position_state(self, symbol: str, action: Action):
        """Update position state after successful execution."""
        current = self._positions.get(symbol, Position.create_flat(symbol))

        if action.type == ActionType.ENTRY:
            direction = Direction.LONG if action.direction == "LONG" else Direction.SHORT
            self._positions[symbol] = Position(
                symbol=symbol,
                state=PositionState.ENTERING,
                direction=direction,
                quantity=Decimal(str(self._config.max_position_size)),
                entry_price=None  # Will be updated on fill
            )
            self._last_action_time = time.time()
            self._actions_this_minute += 1

        elif action.type == ActionType.EXIT:
            self._positions[symbol] = Position.create_flat(symbol)
            self._last_action_time = time.time()
            self._actions_this_minute += 1

        elif action.type == ActionType.REDUCE:
            new_qty = current.quantity / 2
            if new_qty > 0:
                self._positions[symbol] = Position(
                    symbol=symbol,
                    state=PositionState.OPEN,
                    direction=current.direction,
                    quantity=new_qty,
                    entry_price=current.entry_price
                )
            else:
                self._positions[symbol] = Position.create_flat(symbol)
            self._last_action_time = time.time()
            self._actions_this_minute += 1

    def get_position(self, symbol: str) -> Position:
        """Get current position for symbol."""
        return self._positions.get(symbol, Position.create_flat(symbol))

    def get_all_positions(self) -> Dict[str, Position]:
        """Get all positions."""
        return dict(self._positions)

    def get_state(self) -> M6State:
        """Get executor state."""
        return self._state

    def get_recent_cycles(self, limit: int = 10) -> List[ExecutionCycleResult]:
        """Get recent execution cycles."""
        return list(self._recent_cycles[-limit:])

    def get_stats(self) -> Dict[str, Any]:
        """Get executor statistics."""
        return {
            "state": self._state.value,
            "positions": {
                symbol: {
                    "state": pos.state.value,
                    "direction": pos.direction.value if pos.direction else None,
                    "quantity": str(pos.quantity)
                }
                for symbol, pos in self._positions.items()
            },
            "actions_this_minute": self._actions_this_minute,
            "recent_cycles": len(self._recent_cycles),
            "exchange_calls": self._exchange_adapter.get_call_count()
        }

    async def close(self):
        """Close executor and cleanup."""
        await self._exchange_adapter.close()
        self._state = M6State.STOPPED
