"""Policy Adapter - Pure Wiring Layer.

Translates between observation primitives and execution mandates.

Architecture:
    ObservationSystem (M1-M5) → M4 Primitives
                                      ↓
                                PolicyAdapter (this module)
                                      ↓
                        External Policies (EP2, frozen)
                                      ↓
                             Policy Proposals
                                      ↓
                          Mandate Normalization
                                      ↓
                            ExecutionController

Properties:
- Stateless (no memory between calls)
- Deterministic (same inputs → same outputs)
- Pure wiring (no interpretation, no strategy)
- Replaceable (can be swapped without affecting system)

Authority: Architectural ruling 2026-01-10
"""

import os
import time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from decimal import Decimal

# Diagnostic logging control: set DIAG_MANDATE=1 to enable
_DIAG_ENABLED = os.environ.get('DIAG_MANDATE', '').lower() in ('1', 'true', 'yes')

from observation.types import ObservationSnapshot, ObservationStatus
from runtime.arbitration.types import Mandate, MandateType
from runtime.position.types import PositionState

# External policy imports (frozen)
from external_policy.ep2_strategy_geometry import (
    generate_geometry_proposal,
    StrategyContext,
    PermissionOutput,
    StrategyProposal
)
from external_policy.ep2_strategy_kinematics import generate_kinematics_proposal
from external_policy.ep2_strategy_absence import generate_absence_proposal
# Test policy for order book primitives (verification only)
from external_policy.ep2_strategy_orderbook_test import generate_orderbook_test_proposal

# Phase 5: SLBRS/EFFCS strategies with regime gating
from external_policy.ep2_slbrs_strategy import generate_slbrs_proposal, RegimeState as SLBRSRegimeState
from external_policy.ep2_effcs_strategy import generate_effcs_proposal

# Phase 6: Cascade Sniper strategy (Hyperliquid proximity)
from external_policy.ep2_strategy_cascade_sniper import (
    generate_cascade_sniper_proposal,
    ProximityData,
    AbsorptionAnalysis,
    EntryMode as CascadeSniperEntryMode
)
from runtime.liquidations import LiquidationBurst

# Directional context for kill-switch (via observation layer)
from observation.types import TrendRegimeContext


@dataclass(frozen=True)
class AdapterConfig:
    """Configuration for policy adapter.

    Contains only wiring parameters, no strategy logic.
    """
    default_authority: float = 5.0  # Authority level for policy mandates
    enable_geometry: bool = True
    enable_kinematics: bool = True
    enable_absence: bool = True
    enable_orderbook_test: bool = False  # Test policy for verification

    # Phase 5: Regime-gated strategies (SLBRS/EFFCS)
    enable_slbrs: bool = False  # SLBRS strategy (SIDEWAYS regime)
    enable_effcs: bool = False  # EFFCS strategy (EXPANSION regime)

    # Position sizing: default notional value per trade (USD)
    # F5: Real quantity calculation for mandates
    default_notional_usd: float = 100.0  # $100 per trade

    # Phase 6: Cascade Sniper strategy (Hyperliquid proximity)
    enable_cascade_sniper: bool = False  # Cascade sniper (liquidation proximity)
    cascade_sniper_entry_mode: str = "ABSORPTION_REVERSAL"  # "ABSORPTION_REVERSAL" or "CASCADE_MOMENTUM"


class PolicyAdapter:
    """Pure wiring layer connecting observation to execution.

    Responsibilities:
    1. Query M4 primitives from observation
    2. Invoke frozen external policies
    3. Convert proposals to Mandates
    4. No interpretation, scoring, or aggregation
    5. Enforce global entry grace period (prevent immediate exits)

    Not Responsible For:
    - Strategy logic (in external_policy/)
    - Risk constraints (in runtime/risk/)
    - Arbitration (in runtime/arbitration/)
    - State management (in runtime/position/)
    """

    # Global entry tracking: symbol -> (entry_time, entry_strategy)
    # Prevents immediate exit oscillation by enforcing grace period
    _entry_tracker: dict = {}

    # Grace period (seconds) - no EXIT allowed within this time of ENTRY
    ENTRY_GRACE_PERIOD_SEC = 10.0

    def __init__(self, config: Optional[AdapterConfig] = None):
        """Initialize adapter with configuration."""
        self.config = config or AdapterConfig()

    def generate_mandates(
        self,
        observation_snapshot: ObservationSnapshot,
        symbol: str,
        timestamp: float,
        position_state: Optional[PositionState] = None,
        regime_state: Optional[Any] = None,  # RegimeState from regime classifier
        regime_metrics: Optional[Any] = None,  # RegimeMetrics from regime classifier
        current_price: Optional[float] = None,  # Current price from collector
        hl_proximity: Optional[ProximityData] = None,  # Hyperliquid proximity data
        liquidation_burst: Optional[LiquidationBurst] = None,  # Recent Binance liquidations
        absorption: Optional[AbsorptionAnalysis] = None,  # Order book absorption analysis
        trend_context: Optional[TrendRegimeContext] = None  # Trend regime for kill-switch
    ) -> List[Mandate]:
        """Generate mandates from observation for a single symbol.

        Pure wiring - no decisions made here.

        TREND KILL-SWITCH:
        When trend_context is provided, the cascade sniper strategy will use it
        to block dangerous reversal entries during strong directional moves.

        Args:
            observation_snapshot: Current observation state
            symbol: Symbol to generate mandates for
            timestamp: Current timestamp
            position_state: Current position state for symbol (from executor)
            regime_state: Regime classification (Phase 5)
            regime_metrics: Regime metrics (VWAP distance, ATR, orderflow, liquidations)
            current_price: Current market price
            hl_proximity: Hyperliquid liquidation proximity data (Phase 6)
            liquidation_burst: Recent Binance liquidation burst (Phase 6)
            absorption: Order book absorption analysis (Phase 6)
            trend_context: Trend regime context for kill-switch (blocks fading strong trends)

        Returns:
            List of Mandates (possibly empty)
        """
        # Handle observation status per EPISTEMIC_CONSTITUTION.md
        # Only two valid states: UNINITIALIZED (normal operation) or FAILED (halt)
        if observation_snapshot.status == ObservationStatus.FAILED:
            # Observation FAILED -> emit BLOCK mandate (halt execution)
            return [Mandate(
                symbol=symbol,
                type=MandateType.BLOCK,
                authority=10.0,  # Maximum authority
                timestamp=timestamp
            )]

        # Status is UNINITIALIZED (normal operation) - proceed with mandate generation
        # Extract M4 primitives from observation
        # NOTE: This is a stub - actual implementation needs M5 query interface
        # For now, we simulate primitive extraction
        primitives = self._extract_primitives(observation_snapshot, symbol)

        # Generate strategy context (neutral framing)
        context = StrategyContext(
            context_id=f"{symbol}_{timestamp}",
            timestamp=timestamp
        )

        # Generate M6 permission (stub - actual implementation needs M6 scaffolding)
        permission = PermissionOutput(
            result="ALLOWED",  # Simplified - real M6 has governance
            mandate_id=f"mandate_{symbol}_{timestamp}",
            action_id=f"action_{symbol}_{timestamp}",
            reason_code="WIRING_STUB",
            timestamp=timestamp
        )

        # DIAGNOSTIC: Log inputs to mandate generation
        if _DIAG_ENABLED:
            # Count non-None primitives
            active_primitives = [k for k, v in primitives.items() if v is not None]
            print(f"\n[DIAG] {symbol} mandate generation:")
            print(f"  position_state: {position_state}")
            print(f"  regime_state: {regime_state.name if regime_state else 'None'}")
            print(f"  regime_metrics: {regime_metrics is not None}")
            print(f"  current_price: {current_price}")
            print(f"  hl_proximity: {hl_proximity is not None}")
            print(f"  liquidation_burst: {liquidation_burst is not None}")
            print(f"  primitives ({len(active_primitives)}/{len(primitives)}): {active_primitives if active_primitives else 'NONE'}")
            print(f"  policies enabled: geometry={self.config.enable_geometry}, kinematics={self.config.enable_kinematics}, "
                  f"slbrs={self.config.enable_slbrs}, effcs={self.config.enable_effcs}, cascade={self.config.enable_cascade_sniper}")

        # Invoke frozen external policies
        proposals: List[StrategyProposal] = []

        if self.config.enable_geometry:
            # Create context with current_price for zone break detection
            geometry_context = StrategyContext(
                context_id=f"{symbol}_{timestamp}",
                timestamp=timestamp,
                current_price=current_price
            )
            proposal = generate_geometry_proposal(
                # Pattern primitive (B5) - supply/demand zone with confirmation
                supply_demand_zone=primitives.get("supply_demand_zone"),
                context=geometry_context,
                permission=permission,
                position_state=position_state,
                # Instantaneous primitives as fallback (with stability requirement)
                zone_penetration=primitives.get("zone_penetration"),
                traversal_compactness=primitives.get("traversal_compactness"),
                central_tendency_deviation=primitives.get("central_tendency_deviation")
            )
            if _DIAG_ENABLED:
                if proposal:
                    print(f"  [geometry] → {proposal.action_type} ({proposal.confidence})")
                else:
                    zone = primitives.get("supply_demand_zone")
                    if zone:
                        # Show why zone isn't confirmed
                        print(f"  [geometry] → None (zone={zone.zone_type}, disp={zone.displacement_detected}, "
                              f"retest={zone.retest_detected}, rt_count={zone.retest_count}, "
                              f"nodes={zone.node_count}, strength={zone.avg_node_strength:.2f})")
                    else:
                        has_pen = primitives.get("zone_penetration") is not None
                        print(f"  [geometry] → None (zone=None, pen={has_pen})")
            if proposal:
                proposals.append(proposal)

        if self.config.enable_kinematics:
            proposal = generate_kinematics_proposal(
                # Pattern primitive (B5) - order block with confirmation
                order_block=primitives.get("order_block"),
                permission=permission,
                context=context,
                position_state=position_state,
                # Instantaneous primitives as fallback (with stability requirement)
                velocity=primitives.get("price_traversal_velocity"),
                compactness=primitives.get("traversal_compactness"),
                acceptance=primitives.get("price_acceptance_ratio")
            )
            if _DIAG_ENABLED:
                if proposal:
                    print(f"  [kinematics] → {proposal.action_type} ({proposal.confidence})")
                else:
                    has_ob = primitives.get("order_block") is not None
                    has_vel = primitives.get("price_traversal_velocity") is not None
                    print(f"  [kinematics] → None (order_block={has_ob}, velocity={has_vel})")
            if proposal:
                proposals.append(proposal)

        if self.config.enable_absence:
            proposal = generate_absence_proposal(
                permission=permission,
                absence=primitives.get("structural_absence_duration"),
                persistence=primitives.get("structural_persistence_duration"),
                geometry=primitives.get("zone_penetration"),
                context=context,
                position_state=position_state
            )
            if proposal:
                proposals.append(proposal)

        if self.config.enable_orderbook_test:
            proposal = generate_orderbook_test_proposal(
                resting_size=primitives.get("resting_size"),
                order_consumption=primitives.get("order_consumption"),
                refill_event=primitives.get("refill_event"),
                context=context,
                permission=permission,
                position_state=position_state
            )
            if proposal:
                proposals.append(proposal)

        # Phase 5: SLBRS/EFFCS strategies with regime gating
        if regime_state is None or regime_metrics is None:
            if _DIAG_ENABLED:
                print(f"  [SLBRS/EFFCS] SKIPPED - regime_state={regime_state is not None}, regime_metrics={regime_metrics is not None}")
        if regime_state is not None and regime_metrics is not None:
            # Convert regime_state to strategy-compatible format
            regime_state_obj = SLBRSRegimeState(
                regime=regime_state.name,  # "SIDEWAYS_ACTIVE", "EXPANSION_ACTIVE", or "DISABLED"
                vwap_distance=regime_metrics.vwap_distance,
                atr_5m=regime_metrics.atr_5m,
                atr_30m=regime_metrics.atr_30m
            )

            # Use current price from collector (if not available, skip strategy calls)
            if current_price is None:
                return mandates

            if self.config.enable_slbrs:
                # SLBRS strategy (SIDEWAYS regime)
                proposal = generate_slbrs_proposal(
                    symbol=symbol,
                    regime_state=regime_state_obj,
                    zone_penetration=primitives.get("zone_penetration"),
                    resting_size=primitives.get("resting_size"),
                    order_consumption=primitives.get("order_consumption"),
                    structural_persistence=primitives.get("structural_persistence_duration"),
                    price=current_price,
                    context=context,
                    permission=permission,
                    position_state=position_state
                )
                if _DIAG_ENABLED:
                    if proposal:
                        print(f"  [slbrs] → {proposal.action_type} ({proposal.confidence})")
                    else:
                        print(f"  [slbrs] → None (regime={regime_state_obj.regime})")
                if proposal:
                    proposals.append(proposal)

            if self.config.enable_effcs:
                # EFFCS strategy (EXPANSION regime)
                proposal = generate_effcs_proposal(
                    symbol=symbol,
                    regime_state=regime_state_obj,
                    price_velocity=primitives.get("price_traversal_velocity"),
                    displacement=primitives.get("displacement_origin_anchor"),
                    liquidation_zscore=regime_metrics.liquidation_zscore,
                    price=current_price,
                    price_high=current_price,  # TODO: Track recent high separately
                    price_low=current_price,  # TODO: Track recent low separately
                    context=context,
                    permission=permission,
                    position_state=position_state
                )
                if _DIAG_ENABLED:
                    if proposal:
                        print(f"  [effcs] → {proposal.action_type} ({proposal.confidence})")
                    else:
                        print(f"  [effcs] → None (regime={regime_state_obj.regime}, liq_z={regime_metrics.liquidation_zscore:.2f})")
                if proposal:
                    proposals.append(proposal)

        # Phase 6: Cascade Sniper strategy (Hyperliquid proximity) with TREND KILL-SWITCH
        if self.config.enable_cascade_sniper and (hl_proximity is not None or liquidation_burst is not None):
            # Determine entry mode from config
            entry_mode = CascadeSniperEntryMode.ABSORPTION_REVERSAL
            if self.config.cascade_sniper_entry_mode == "CASCADE_MOMENTUM":
                entry_mode = CascadeSniperEntryMode.CASCADE_MOMENTUM

            proposal = generate_cascade_sniper_proposal(
                permission=permission,
                proximity=hl_proximity,
                liquidations=liquidation_burst,
                context=context,
                position_state=position_state,
                entry_mode=entry_mode,
                absorption=absorption,  # Pass orderbook absorption analysis
                trend_context=trend_context  # Pass trend context for kill-switch
            )
            if _DIAG_ENABLED:
                if proposal:
                    print(f"  [cascade] → {proposal.action_type} ({proposal.confidence})")
                else:
                    prox_count = hl_proximity.total_positions_at_risk if hl_proximity else 0
                    burst_vol = liquidation_burst.total_volume if liquidation_burst else 0
                    print(f"  [cascade] → None (proximity_pos={prox_count}, burst_vol={burst_vol:.0f})")
            if proposal:
                proposals.append(proposal)
        elif self.config.enable_cascade_sniper and _DIAG_ENABLED:
            print(f"  [cascade] SKIPPED - no proximity or burst data")

        # Convert proposals to mandates (pure normalization)
        # F5: Pass current_price for quantity calculation
        mandates = self._proposals_to_mandates(proposals, symbol, timestamp, current_price)

        # Only log when mandates are generated (not empty cycles)
        if len(mandates) > 0:
            print(f"[PolicyAdapter] {symbol}: {len(proposals)} proposals → {len(mandates)} mandates")
            for mandate in mandates:
                direction_str = f", dir={mandate.direction}" if mandate.direction else ""
                quantity_str = f", qty={mandate.quantity}" if mandate.quantity else ""
                print(f"  - Mandate: {mandate.type.name}{direction_str}{quantity_str}")

        return mandates

    def _extract_primitives(
        self,
        observation_snapshot: ObservationSnapshot,
        symbol: str
    ) -> Dict[str, Any]:
        """Extract M4 primitives from observation snapshot.

        Reads pre-computed primitives - does NOT query M5.

        Per ANNEX_M4_PRIMITIVE_FLOW.md:
        - Primitives are pre-computed at snapshot creation
        - PolicyAdapter (M6) never queries M5 directly
        - Primitives flow via ObservationSnapshot only

        Args:
            observation_snapshot: Snapshot with pre-computed primitives
            symbol: Symbol to extract primitives for

        Returns:
            Dictionary of primitive name -> primitive object
        """
        # Get pre-computed bundle for symbol
        bundle = observation_snapshot.primitives.get(symbol)

        if bundle is None:
            # Symbol not in snapshot (should not happen if symbol in symbols_active)
            # Return empty dict with all None primitives
            return {
                "zone_penetration": None,
                "traversal_compactness": None,
                "central_tendency_deviation": None,
                "price_traversal_velocity": None,
                "displacement_origin_anchor": None,
                "structural_absence_duration": None,
                "traversal_void_span": None,
                "event_non_occurrence_counter": None,
                "resting_size": None,
                "order_consumption": None,
                "refill_event": None,
                "order_block": None,
                "supply_demand_zone": None,
                "liquidation_cascade_proximity": None,
                "cascade_state": None,
                "leverage_concentration_ratio": None,
                "open_interest_directional_bias": None,
            }

        # Extract primitives from bundle (read-only access)
        return {
            "zone_penetration": bundle.zone_penetration,
            "traversal_compactness": bundle.traversal_compactness,
            "central_tendency_deviation": bundle.central_tendency_deviation,
            "price_traversal_velocity": bundle.price_traversal_velocity,
            "displacement_origin_anchor": bundle.displacement_origin_anchor,
            "structural_absence_duration": bundle.structural_absence_duration,
            "traversal_void_span": bundle.traversal_void_span,
            "event_non_occurrence_counter": bundle.event_non_occurrence_counter,
            "resting_size": bundle.resting_size,
            "order_consumption": bundle.order_consumption,
            "refill_event": bundle.refill_event,
            "order_block": bundle.order_block,
            "supply_demand_zone": bundle.supply_demand_zone,
            # Tier B-6 - Cascade observation primitives (from Hyperliquid)
            "liquidation_cascade_proximity": bundle.liquidation_cascade_proximity,
            "cascade_state": bundle.cascade_state,
            "leverage_concentration_ratio": bundle.leverage_concentration_ratio,
            "open_interest_directional_bias": bundle.open_interest_directional_bias,
        }

    def _proposals_to_mandates(
        self,
        proposals: List[StrategyProposal],
        symbol: str,
        timestamp: float,
        current_price: Optional[float] = None
    ) -> List[Mandate]:
        """Convert strategy proposals to execution mandates.

        Pure normalization - no interpretation, no aggregation, no scoring.
        F5: Copies direction, strategy_id, and calculates quantity from proposal.

        GRACE PERIOD: Blocks EXIT proposals within ENTRY_GRACE_PERIOD_SEC of entry
        to prevent immediate oscillation from zone/condition instability.

        Args:
            proposals: List of strategy proposals
            symbol: Symbol mandates apply to
            timestamp: Current timestamp
            current_price: Current market price (for quantity calculation)

        Returns:
            List of Mandates
        """
        mandates = []

        for proposal in proposals:
            # Map proposal action_type to MandateType
            # This is opaque translation - no interpretation
            mandate_type = self._map_action_to_mandate(proposal.action_type)

            # F5: Extract direction from proposal (if available)
            direction = getattr(proposal, 'direction', None)

            # F5: Extract strategy_id from proposal
            strategy_id = getattr(proposal, 'strategy_id', None)

            # GRACE PERIOD: Block EXIT within grace period of ENTRY
            if mandate_type == MandateType.EXIT:
                entry_info = PolicyAdapter._entry_tracker.get(symbol)
                if entry_info:
                    entry_time, entry_strategy = entry_info
                    time_since_entry = timestamp - entry_time
                    if time_since_entry < self.ENTRY_GRACE_PERIOD_SEC:
                        # Within grace period - skip this EXIT proposal
                        print(f"[PolicyAdapter] {symbol}: EXIT blocked (grace period: {time_since_entry:.1f}s < {self.ENTRY_GRACE_PERIOD_SEC}s)")
                        continue
                    else:
                        # Grace period passed - allow EXIT and clear tracker
                        PolicyAdapter._entry_tracker.pop(symbol, None)

            # Track ENTRY for grace period enforcement
            if mandate_type == MandateType.ENTRY:
                PolicyAdapter._entry_tracker[symbol] = (timestamp, strategy_id)

            # F5: Calculate quantity from notional and current price
            # Only for ENTRY mandates with valid price
            quantity = None
            entry_price = None
            if mandate_type == MandateType.ENTRY and current_price and current_price > 0:
                entry_price = Decimal(str(current_price))
                # quantity = notional / price
                quantity = Decimal(str(self.config.default_notional_usd)) / entry_price

            mandates.append(Mandate(
                symbol=symbol,
                type=mandate_type,
                authority=self.config.default_authority,
                timestamp=timestamp,
                direction=direction,
                strategy_id=strategy_id,
                quantity=quantity,
                entry_price=entry_price
            ))

        return mandates

    def _map_action_to_mandate(self, action_type: str) -> MandateType:
        """Map proposal action type to mandate type.

        Opaque mechanical mapping - no interpretation.

        Args:
            action_type: Opaque action string from proposal

        Returns:
            MandateType
        """
        # Mechanical mapping based on frozen policy conventions
        # These mappings are defined by external policy contracts

        if action_type == "ENTRY":
            return MandateType.ENTRY
        elif action_type == "EXIT":
            return MandateType.EXIT
        elif action_type == "REDUCE":
            return MandateType.REDUCE
        else:
            # Default fallback (should not reach here with well-formed policies)
            return MandateType.ENTRY
