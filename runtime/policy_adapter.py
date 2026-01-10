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

import time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from observation.types import ObservationSnapshot, ObservationStatus
from runtime.arbitration.types import Mandate, MandateType

# External policy imports (frozen)
from external_policy.ep2_strategy_geometry import (
    generate_geometry_proposal,
    StrategyContext,
    PermissionOutput,
    StrategyProposal
)
from external_policy.ep2_strategy_kinematics import generate_kinematics_proposal
from external_policy.ep2_strategy_absence import generate_absence_proposal


@dataclass(frozen=True)
class AdapterConfig:
    """Configuration for policy adapter.

    Contains only wiring parameters, no strategy logic.
    """
    default_authority: float = 5.0  # Authority level for policy mandates
    enable_geometry: bool = True
    enable_kinematics: bool = True
    enable_absence: bool = True


class PolicyAdapter:
    """Pure wiring layer connecting observation to execution.

    Responsibilities:
    1. Query M4 primitives from observation
    2. Invoke frozen external policies
    3. Convert proposals to Mandates
    4. No interpretation, scoring, or aggregation

    Not Responsible For:
    - Strategy logic (in external_policy/)
    - Risk constraints (in runtime/risk/)
    - Arbitration (in runtime/arbitration/)
    - State management (in runtime/position/)
    """

    def __init__(self, config: Optional[AdapterConfig] = None):
        """Initialize adapter with configuration."""
        self.config = config or AdapterConfig()

    def generate_mandates(
        self,
        observation_snapshot: ObservationSnapshot,
        symbol: str,
        timestamp: float
    ) -> List[Mandate]:
        """Generate mandates from observation for a single symbol.

        Pure wiring - no decisions made here.

        Args:
            observation_snapshot: Current observation state
            symbol: Symbol to generate mandates for
            timestamp: Current timestamp

        Returns:
            List of Mandates (possibly empty)
        """
        # Handle observation status per M6_CONSUMPTION_CONTRACT.md
        if observation_snapshot.status == ObservationStatus.FAILED:
            # Observation FAILED -> emit BLOCK mandate (halt execution)
            return [Mandate(
                symbol=symbol,
                type=MandateType.BLOCK,
                authority=10.0,  # Maximum authority
                timestamp=timestamp
            )]

        if observation_snapshot.status == ObservationStatus.UNINITIALIZED:
            # Observation not ready -> no mandates
            return []

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

        # Invoke frozen external policies
        proposals: List[StrategyProposal] = []

        if self.config.enable_geometry:
            proposal = generate_geometry_proposal(
                zone_penetration=primitives.get("zone_penetration"),
                traversal_compactness=primitives.get("traversal_compactness"),
                central_tendency_deviation=primitives.get("central_tendency_deviation"),
                context=context,
                permission=permission
            )
            if proposal:
                proposals.append(proposal)

        if self.config.enable_kinematics:
            proposal = generate_kinematics_proposal(
                price_traversal_velocity=primitives.get("price_traversal_velocity"),
                traversal_compactness=primitives.get("traversal_compactness"),
                displacement_origin_anchor=primitives.get("displacement_origin_anchor"),
                context=context,
                permission=permission
            )
            if proposal:
                proposals.append(proposal)

        if self.config.enable_absence:
            proposal = generate_absence_proposal(
                structural_absence_duration=primitives.get("structural_absence_duration"),
                traversal_void_span=primitives.get("traversal_void_span"),
                event_non_occurrence_counter=primitives.get("event_non_occurrence_counter"),
                context=context,
                permission=permission
            )
            if proposal:
                proposals.append(proposal)

        # Convert proposals to mandates (pure normalization)
        mandates = self._proposals_to_mandates(proposals, symbol, timestamp)

        return mandates

    def _extract_primitives(
        self,
        observation_snapshot: ObservationSnapshot,
        symbol: str
    ) -> Dict[str, Any]:
        """Extract M4 primitives from observation snapshot.

        NOTE: This is a stub implementation.
        Real implementation needs M5 query interface to pull specific primitives.

        Args:
            observation_snapshot: Observation state
            symbol: Symbol to extract primitives for

        Returns:
            Dictionary of primitive name -> primitive object
        """
        # STUB: In real implementation, this would:
        # 1. Use M5 governance layer to query M4 primitives
        # 2. Return actual primitive dataclasses
        # 3. Handle missing/None primitives explicitly

        # For now, return empty dict (all None primitives)
        return {
            "zone_penetration": None,
            "traversal_compactness": None,
            "central_tendency_deviation": None,
            "price_traversal_velocity": None,
            "displacement_origin_anchor": None,
            "structural_absence_duration": None,
            "traversal_void_span": None,
            "event_non_occurrence_counter": None,
        }

    def _proposals_to_mandates(
        self,
        proposals: List[StrategyProposal],
        symbol: str,
        timestamp: float
    ) -> List[Mandate]:
        """Convert strategy proposals to execution mandates.

        Pure normalization - no interpretation, no aggregation, no scoring.

        Args:
            proposals: List of strategy proposals
            symbol: Symbol mandates apply to
            timestamp: Current timestamp

        Returns:
            List of Mandates
        """
        mandates = []

        for proposal in proposals:
            # Map proposal action_type to MandateType
            # This is opaque translation - no interpretation
            mandate_type = self._map_action_to_mandate(proposal.action_type)

            mandates.append(Mandate(
                symbol=symbol,
                type=mandate_type,
                authority=self.config.default_authority,
                timestamp=timestamp
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

        # Currently all proposals map to ENTRY (structural events suggest entry)
        # This is intentionally simple - real logic in arbitration layer
        return MandateType.ENTRY
