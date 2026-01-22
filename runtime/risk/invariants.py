"""Risk Invariant Validators.

Formal validation of all 15 risk invariants (R1-R15) per RISK&EXPOSUREINVARIANTS.md.

These validators enforce constitutional risk constraints.
They return ValidationResult indicating pass/fail with specific violation details.

CRITICAL: These are hard constraints, not guidelines.
Any violation must block the proposed action.
"""

from decimal import Decimal
from typing import Dict, Optional, List

from runtime.position.types import Position, PositionState, Direction
from .types import RiskConfig, AccountState, PositionRisk, PortfolioRisk, ValidationResult
from .calculator import RiskCalculator


class RiskInvariantValidator:
    """Validates all 15 constitutional risk invariants.

    Each validator returns ValidationResult.
    Validators are pure functions - deterministic, no side effects.
    """

    def __init__(self, config: RiskConfig):
        """Initialize with risk configuration."""
        config.validate()
        self.config = config
        self.calculator = RiskCalculator(config)

    # ========== R1: Per-Position Risk Cap ==========

    def validate_R1_position_risk_cap(
        self,
        position: Position,
        mark_price: Decimal,
        stop_distance: Decimal,
        account: AccountState
    ) -> ValidationResult:
        """R1: MaxLoss(symbol) ≤ RiskFraction × Equity

        Validates that maximum loss on this position cannot exceed
        configured risk fraction of total equity.

        Args:
            position: Position to validate
            mark_price: Current mark price
            stop_distance: Distance to stop loss
            account: Account state

        Returns:
            ValidationResult (valid=True if valid)
        """
        if account.equity <= 0:
            return ValidationResult(
                valid=False,
                reason="R1 violation: Zero or negative equity",
                blocking=True
            )

        # MaxLoss = |Q| × stop_distance
        max_loss = abs(position.quantity) * stop_distance

        # Threshold = RiskFraction × Equity
        max_allowed_loss = account.equity * Decimal(str(self.config.risk_fraction_per_trade))

        if max_loss > max_allowed_loss:
            return ValidationResult(
                valid=False,
                reason=f"R1 violation: MaxLoss {max_loss} > {self.config.risk_fraction_per_trade:.1%} × Equity {account.equity} = {max_allowed_loss}",
                blocking=True
            )

        return ValidationResult(valid=True, reason="R1: Position risk within cap")

    # ========== R2: Absolute Leverage Cap ==========

    def validate_R2_leverage_cap(
        self,
        positions: Dict[str, Position],
        account: AccountState,
        mark_prices: Dict[str, Decimal],
        proposed_position: Optional[Position] = None,
        proposed_price: Optional[Decimal] = None
    ) -> ValidationResult:
        """R2: Leverage(symbol) ≤ MaxLeverage

        Validates total leverage does not exceed absolute maximum.
        Checks both current state and proposed state if new position provided.

        Args:
            positions: All current positions
            account: Account state
            mark_prices: Mark prices per symbol
            proposed_position: Optional new position to add
            proposed_price: Optional entry price for proposed position

        Returns:
            ValidationResult (valid=True if valid)
        """
        # Calculate current leverage
        current_leverage = self.calculator.calculate_total_leverage(
            positions, account, mark_prices
        )

        # If no proposed position, just check current
        if proposed_position is None:
            if current_leverage > self.config.L_max:
                return ValidationResult(
                    valid=False,
                    reason=f"R2 violation: Current leverage {current_leverage:.2f}x > L_max {self.config.L_max}x",
                    blocking=True
                )
            return ValidationResult(valid=True, reason=f"R2: Leverage {current_leverage:.2f}x within cap")

        # Calculate leverage with proposed position
        if proposed_price is None:
            return ValidationResult(
                valid=False,
                reason="R2 validation: proposed_position requires proposed_price",
                blocking=True
            )

        proposed_exposure = abs(proposed_position.quantity * proposed_price)
        total_exposure = Decimal("0")

        for symbol, pos in positions.items():
            if pos.state not in (PositionState.FLAT, PositionState.ENTERING):
                if symbol in mark_prices:
                    total_exposure += abs(pos.quantity * mark_prices[symbol])

        total_exposure += proposed_exposure

        if account.equity <= 0:
            return ValidationResult(
                valid=False,
                reason="R2 violation: Zero or negative equity",
                blocking=True
            )

        proposed_leverage = float(total_exposure / account.equity)

        if proposed_leverage > self.config.L_max:
            return ValidationResult(
                valid=False,
                reason=f"R2 violation: Proposed leverage {proposed_leverage:.2f}x > L_max {self.config.L_max}x",
                blocking=True
            )

        return ValidationResult(valid=True, reason=f"R2: Proposed leverage {proposed_leverage:.2f}x within cap")

    # ========== R3: Liquidation Safety Margin ==========

    def validate_R3_liquidation_buffer(
        self,
        position: Position,
        mark_price: Decimal,
        leverage: float
    ) -> ValidationResult:
        """R3: DistanceToLiquidation(symbol) ≥ MinLiquidationBuffer

        Validates position maintains minimum buffer from liquidation price.

        Args:
            position: Position to validate
            mark_price: Current mark price
            leverage: Current leverage

        Returns:
            ValidationResult (valid=True if valid)
        """
        if position.state == PositionState.FLAT:
            return ValidationResult(valid=True, reason="R3: No position (FLAT)")

        if position.entry_price is None:
            return ValidationResult(
                valid=False,
                reason="R3 validation: Position missing entry price",
                blocking=True
            )

        # Calculate position risk (includes liquidation distance)
        pos_risk = self.calculator.calculate_position_risk(position, mark_price, leverage)

        if pos_risk.liquidation_distance < self.config.D_min_safe:
            return ValidationResult(
                valid=False,
                reason=f"R3 violation: Liquidation distance {pos_risk.liquidation_distance:.2%} < D_min_safe {self.config.D_min_safe:.2%}",
                blocking=True
            )

        # Critical threshold check
        if pos_risk.liquidation_distance < self.config.D_critical:
            return ValidationResult(
                valid=False,
                reason=f"R3 CRITICAL: Liquidation distance {pos_risk.liquidation_distance:.2%} < D_critical {self.config.D_critical:.2%}",
                blocking=True
            )

        return ValidationResult(
            valid=True,
            reason=f"R3: Liquidation buffer {pos_risk.liquidation_distance:.2%} sufficient"
        )

    # ========== R5: Account-Wide Exposure Cap ==========

    def validate_R5_total_exposure_cap(
        self,
        positions: Dict[str, Position],
        account: AccountState,
        mark_prices: Dict[str, Decimal]
    ) -> ValidationResult:
        """R5: Σ PositionNotional(all symbols) ≤ ExposureCap × Equity

        Validates total exposure across all positions does not exceed cap.

        Args:
            positions: All positions
            account: Account state
            mark_prices: Mark prices per symbol

        Returns:
            ValidationResult (valid=True if valid)
        """
        portfolio_risk = self.calculator.calculate_portfolio_risk(
            positions, account, mark_prices
        )

        max_allowed_exposure = account.equity * Decimal(str(self.config.L_max))

        if portfolio_risk.total_exposure > max_allowed_exposure:
            return ValidationResult(
                valid=False,
                reason=f"R5 violation: Total exposure {portfolio_risk.total_exposure} > {self.config.L_max}x × Equity {account.equity} = {max_allowed_exposure}",
                blocking=True
            )

        return ValidationResult(
            valid=True,
            reason=f"R5: Total exposure {portfolio_risk.total_exposure} within cap"
        )

    # ========== R6: Single-Symbol Exposure Limit ==========

    def validate_R6_symbol_exposure_cap(
        self,
        position: Position,
        mark_price: Decimal,
        account: AccountState
    ) -> ValidationResult:
        """R6: PositionNotional(symbol) ≤ SymbolExposureCap × Equity

        Validates single position exposure does not exceed per-symbol limit.

        Args:
            position: Position to validate
            mark_price: Current mark price
            account: Account state

        Returns:
            ValidationResult (valid=True if valid)
        """
        if position.state == PositionState.FLAT:
            return ValidationResult(valid=True, reason="R6: No position (FLAT)")

        position_exposure = abs(position.quantity * mark_price)
        max_allowed_exposure = account.equity * Decimal(str(self.config.L_symbol_max))

        if position_exposure > max_allowed_exposure:
            return ValidationResult(
                valid=False,
                reason=f"R6 violation: Symbol exposure {position_exposure} > L_symbol_max {self.config.L_symbol_max}x × Equity {account.equity} = {max_allowed_exposure}",
                blocking=True
            )

        return ValidationResult(
            valid=True,
            reason=f"R6: Symbol exposure {position_exposure} within cap"
        )

    # ========== R7: Direction Neutrality ==========

    def validate_R7_direction_neutrality(
        self,
        long_max_size: Decimal,
        short_max_size: Decimal
    ) -> ValidationResult:
        """R7: Risk limits apply identically to LONG and SHORT

        Validates risk calculations are symmetric across directions.

        Args:
            long_max_size: Calculated max size for LONG
            short_max_size: Calculated max size for SHORT

        Returns:
            ValidationResult (valid=True if valid)
        """
        # Max sizes should be identical (within rounding tolerance)
        relative_diff = abs(long_max_size - short_max_size) / max(long_max_size, short_max_size)

        if relative_diff > Decimal("0.001"):  # 0.1% tolerance
            return ValidationResult(
                valid=False,
                reason=f"R7 violation: Asymmetric sizing (LONG: {long_max_size}, SHORT: {short_max_size})",
                blocking=True
            )

        return ValidationResult(valid=True, reason="R7: Direction-neutral sizing")

    # ========== R9: Risk-First Reduction ==========

    def validate_R9_reduce_before_exit(
        self,
        position: Position,
        proposed_action: str,  # 'REDUCE' or 'EXIT'
        leverage: float,
        mark_price: Decimal
    ) -> ValidationResult:
        """R9: REDUCE must be attempted before EXIT

        Validates that REDUCE action is prioritized over full EXIT
        when position violates risk constraints.

        Args:
            position: Current position
            proposed_action: Proposed action ('REDUCE' or 'EXIT')
            leverage: Current leverage
            mark_price: Current mark price

        Returns:
            ValidationResult (valid=True if valid)
        """
        if proposed_action not in ('REDUCE', 'EXIT'):
            return ValidationResult(
                valid=False,
                reason=f"R9 validation: Invalid action '{proposed_action}'",
                blocking=True
            )

        # Check if position violates liquidation buffer
        pos_risk = self.calculator.calculate_position_risk(position, mark_price, leverage)

        violates_buffer = pos_risk.liquidation_distance < self.config.D_min_safe
        is_critical = pos_risk.liquidation_distance < self.config.D_critical

        # If proposing EXIT but not critical, should REDUCE first
        if proposed_action == 'EXIT' and violates_buffer and not is_critical:
            # Check if REDUCE would be sufficient
            reduced_qty = position.quantity * Decimal(str(1 - self.config.reduction_pct_default))

            if abs(reduced_qty) > Decimal("0"):  # Reduction is possible
                return ValidationResult(
                    valid=False,
                    reason=f"R9 violation: Must attempt REDUCE before EXIT (distance {pos_risk.liquidation_distance:.2%} < {self.config.D_min_safe:.2%} but > {self.config.D_critical:.2%})",
                    blocking=True
                )

        return ValidationResult(valid=True, reason=f"R9: Action '{proposed_action}' valid")

    # ========== R12: Partial Exit Validity ==========

    def validate_R12_partial_exit_validity(
        self,
        position: Position,
        reduction_qty: Decimal,
        mark_price: Decimal,
        leverage: float,
        account: AccountState
    ) -> ValidationResult:
        """R12: Partial exits only if post-reduce state satisfies all invariants

        Validates that reducing position by specified quantity leaves
        remaining position in valid risk state.

        Args:
            position: Current position
            reduction_qty: Quantity to reduce
            mark_price: Current mark price
            leverage: Current leverage
            account: Account state

        Returns:
            ValidationResult (valid=True if valid)
        """
        if abs(reduction_qty) >= abs(position.quantity):
            # Full exit, no partial validation needed
            return ValidationResult(valid=True, reason="R12: Full exit (no partial remaining)")

        # Create simulated reduced position
        remaining_qty = position.quantity - (reduction_qty if position.direction == Direction.LONG else -reduction_qty)

        if abs(remaining_qty) < Decimal("0.001"):  # Effectively closing
            return ValidationResult(valid=True, reason="R12: Near-full exit")

        # Check remaining position would satisfy R3 (liquidation buffer)
        # Note: Using same entry price and direction as original
        simulated_position = Position(
            symbol=position.symbol,
            state=PositionState.OPEN,
            direction=position.direction,
            quantity=remaining_qty,
            entry_price=position.entry_price
        )

        r3_result = self.validate_R3_liquidation_buffer(
            simulated_position, mark_price, leverage
        )

        if not r3_result.passed:
            return ValidationResult(
                valid=False,
                reason=f"R12 violation: Remaining position after reduction would violate R3: {r3_result.reason}",
                blocking=True
            )

        # Check remaining position would satisfy R6 (symbol exposure cap)
        r6_result = self.validate_R6_symbol_exposure_cap(
            simulated_position, mark_price, account
        )

        if not r6_result.passed:
            return ValidationResult(
                valid=False,
                reason=f"R12 violation: Remaining position after reduction would violate R6: {r6_result.reason}",
                blocking=True
            )

        return ValidationResult(valid=True, reason="R12: Partial exit valid (remaining position safe)")

    # ========== R13: No Averaging Down ==========

    def validate_R13_no_averaging_down(
        self,
        existing_position: Optional[Position],
        proposed_direction: Direction,
        proposed_entry_price: Decimal
    ) -> ValidationResult:
        """R13: No additional ENTRY if it increases MaxLoss or reduces buffer

        Validates that adding to position does not average down
        (add to losing position in same direction).

        Args:
            existing_position: Current position (None if new)
            proposed_direction: Direction of proposed entry
            proposed_entry_price: Entry price of proposed entry

        Returns:
            ValidationResult (valid=True if valid)
        """
        if existing_position is None or existing_position.state == PositionState.FLAT:
            return ValidationResult(valid=True, reason="R13: New position (no averaging)")

        if existing_position.entry_price is None:
            return ValidationResult(
                valid=False,
                reason="R13 validation: Existing position missing entry price",
                blocking=True
            )

        # Check if adding to existing position in same direction
        if existing_position.direction != proposed_direction:
            return ValidationResult(valid=True, reason="R13: Opposite direction (reducing exposure)")

        # Check if adding at worse price (averaging down)
        is_averaging_down = False

        if existing_position.direction == Direction.LONG:
            # Adding LONG at lower price = averaging down
            if proposed_entry_price < existing_position.entry_price:
                is_averaging_down = True
        elif existing_position.direction == Direction.SHORT:
            # Adding SHORT at higher price = averaging down
            if proposed_entry_price > existing_position.entry_price:
                is_averaging_down = True

        if is_averaging_down:
            return ValidationResult(
                valid=False,
                reason=f"R13 violation: Averaging down prohibited (existing entry: {existing_position.entry_price}, proposed entry: {proposed_entry_price})",
                blocking=True
            )

        return ValidationResult(valid=True, reason="R13: Not averaging down")

    # ========== R14: Free Margin Floor ==========

    def validate_R14_free_margin_floor(
        self,
        account: AccountState
    ) -> ValidationResult:
        """R14: FreeMargin ≥ MinFreeMargin

        Validates account maintains minimum free margin buffer.

        Args:
            account: Account state

        Returns:
            ValidationResult (valid=True if valid)
        """
        min_free_margin = account.equity * Decimal(str(self.config.min_free_margin_pct))

        if account.margin_available < min_free_margin:
            return ValidationResult(
                valid=False,
                reason=f"R14 violation: Free margin {account.margin_available} < {self.config.min_free_margin_pct:.1%} × Equity {account.equity} = {min_free_margin}",
                blocking=True
            )

        return ValidationResult(
            valid=True,
            reason=f"R14: Free margin {account.margin_available} sufficient"
        )

    # ========== Composite Validation ==========

    def validate_entry_action(
        self,
        positions: Dict[str, Position],
        proposed_position: Position,
        proposed_price: Decimal,
        stop_distance: Decimal,
        account: AccountState,
        mark_prices: Dict[str, Decimal]
    ) -> ValidationResult:
        """Validate ENTRY action against all applicable invariants.

        Checks: R1, R2, R3, R5, R6, R7, R13, R14

        Args:
            positions: All current positions
            proposed_position: New position to open
            proposed_price: Entry price
            stop_distance: Distance to stop loss
            account: Account state
            mark_prices: Mark prices per symbol

        Returns:
            ValidationResult with aggregated validation
        """
        violations: List[str] = []

        # R1: Position risk cap
        r1 = self.validate_R1_position_risk_cap(
            proposed_position, proposed_price, stop_distance, account
        )
        if not r1.passed:
            violations.append(r1.reason)

        # R2: Leverage cap (with proposed position)
        r2 = self.validate_R2_leverage_cap(
            positions, account, mark_prices,
            proposed_position=proposed_position,
            proposed_price=proposed_price
        )
        if not r2.passed:
            violations.append(r2.reason)

        # R3: Liquidation buffer (for proposed position)
        leverage = self.calculator.calculate_total_leverage(positions, account, mark_prices)
        r3 = self.validate_R3_liquidation_buffer(
            proposed_position, proposed_price, leverage
        )
        if not r3.passed:
            violations.append(r3.reason)

        # R5: Total exposure cap (current state - entry will be checked via R2)
        r5 = self.validate_R5_total_exposure_cap(positions, account, mark_prices)
        if not r5.passed:
            violations.append(r5.reason)

        # R6: Symbol exposure cap
        r6 = self.validate_R6_symbol_exposure_cap(
            proposed_position, proposed_price, account
        )
        if not r6.passed:
            violations.append(r6.reason)

        # R13: No averaging down
        existing_position = positions.get(proposed_position.symbol)
        r13 = self.validate_R13_no_averaging_down(
            existing_position,
            proposed_position.direction,
            proposed_price
        )
        if not r13.passed:
            violations.append(r13.reason)

        # R14: Free margin floor
        r14 = self.validate_R14_free_margin_floor(account)
        if not r14.passed:
            violations.append(r14.reason)

        if violations:
            return ValidationResult(
                valid=False,
                reason=f"ENTRY validation failed: {'; '.join(violations)}",
                blocking=True
            )

        return ValidationResult(valid=True, reason="ENTRY validation passed all invariants")

    def validate_reduce_action(
        self,
        position: Position,
        reduction_qty: Decimal,
        mark_price: Decimal,
        leverage: float,
        account: AccountState
    ) -> ValidationResult:
        """Validate REDUCE action against all applicable invariants.

        Checks: R9, R12

        Args:
            position: Position to reduce
            reduction_qty: Quantity to reduce
            mark_price: Current mark price
            leverage: Current leverage
            account: Account state

        Returns:
            ValidationResult with aggregated validation
        """
        violations: List[str] = []

        # R9: Reduce before exit (checking REDUCE action is valid)
        r9 = self.validate_R9_reduce_before_exit(
            position, 'REDUCE', leverage, mark_price
        )
        if not r9.passed:
            violations.append(r9.reason)

        # R12: Partial exit validity
        r12 = self.validate_R12_partial_exit_validity(
            position, reduction_qty, mark_price, leverage, account
        )
        if not r12.passed:
            violations.append(r12.reason)

        if violations:
            return ValidationResult(
                valid=False,
                reason=f"REDUCE validation failed: {'; '.join(violations)}",
                blocking=True
            )

        return ValidationResult(valid=True, reason="REDUCE validation passed all invariants")

    def validate_exit_action(
        self,
        position: Position,
        mark_price: Decimal,
        leverage: float
    ) -> ValidationResult:
        """Validate EXIT action against all applicable invariants.

        Checks: R9

        Args:
            position: Position to exit
            mark_price: Current mark price
            leverage: Current leverage

        Returns:
            ValidationResult with aggregated validation
        """
        # R9: Reduce before exit (checking if EXIT is premature)
        r9 = self.validate_R9_reduce_before_exit(
            position, 'EXIT', leverage, mark_price
        )

        if not r9.passed:
            return ValidationResult(
                valid=False,
                reason=f"EXIT validation failed: {r9.reason}",
                blocking=True
            )

        return ValidationResult(valid=True, reason="EXIT validation passed")
