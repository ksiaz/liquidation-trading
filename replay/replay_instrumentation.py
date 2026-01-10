"""
Replay Instrumentation - Replay Harness v1.0

Logging and metrics tracking for replay validation.
Zero interpretation. Pure observation.

Authority: Replay Harness Specification v1.0
"""

from dataclasses import dataclass, field
from typing import Optional, List
from collections import defaultdict
import json


# ==============================================================================
# Instrumentation Metrics
# ==============================================================================

@dataclass
class ObservationMetrics:
    """Metrics from M4 primitive outputs."""
    tier_a_nonzero_count: int = 0
    tier_b1_nonzero_count: int = 0
    tier_b2_nonzero_count: int = 0
    primitive_outputs: List[dict] = field(default_factory=list)


@dataclass
class ProposalMetrics:
    """Metrics from EP-2 strategy proposals."""
    strategy1_proposal_count: int = 0
    strategy2_proposal_count: int = 0
    strategy3_proposal_count: int = 0
    total_proposals: int = 0
    conflict_count: int = 0  # Multiple proposals simultaneously
    m6_denial_count: int = 0


@dataclass
class ArbitrationMetrics:
    """Metrics from EP-3 arbitration."""
    authorized_count: int = 0
    no_action_count: int = 0
    rejected_count: int = 0
    reason_codes: dict = field(default_factory=lambda: defaultdict(int))


@dataclass
class ExecutionMetrics:
    """Metrics from EP-4 execution (DRY-RUN)."""
    success_count: int = 0
    failed_safe_count: int = 0
    noop_count: int = 0
    rejected_count: int = 0
    risk_gate_failures: dict = field(default_factory=lambda: defaultdict(int))
    exchange_constraint_failures: dict = field(default_factory=lambda: defaultdict(int))


@dataclass
class TemporalMetrics:
    """Temporal pattern metrics."""
    action_timestamps: List[float] = field(default_factory=list)
    time_between_actions: List[float] = field(default_factory=list)
    longest_inactivity: float = 0.0
    burst_count: int = 0  # Actions within 1 minute


# ==============================================================================
# Instrumentation Logger
# ==============================================================================

class ReplayInstrumentationLogger:
    """
    Centralized instrumentation logger for replay runs.
    
    Records all metrics per specification.
    Zero filtering. Zero interpretation.
    """
    
    def __init__(self):
        """Initialize instrumentation logger."""
        self.observation = ObservationMetrics()
        self.proposal = ProposalMetrics()
        self.arbitration = ArbitrationMetrics()
        self.execution = ExecutionMetrics()
        self.temporal = TemporalMetrics()
        
        self._events: List[dict] = []
    
    def log_observation(self, *, tier: str, primitive: str, output: dict, is_nonzero: bool):
        """
        Log M4 primitive observation.
        
        Args:
            tier: Tier identifier (A, B1, B2)
            primitive: Primitive name
            output: Primitive output (as dict)
            is_nonzero: Whether output represents non-zero measurement
        """
        if is_nonzero:
            if tier == "A":
                self.observation.tier_a_nonzero_count += 1
            elif tier == "B1":
                self.observation.tier_b1_nonzero_count += 1
            elif tier == "B2":
                self.observation.tier_b2_nonzero_count += 1
        
        self.observation.primitive_outputs.append({
            "tier": tier,
            "primitive": primitive,
            "output": output,
            "is_nonzero": is_nonzero
        })
    
    def log_proposal(self, *, strategy_id: str, proposal: Optional[dict]):
        """
        Log EP-2 strategy proposal.
        
        Args:
            strategy_id: Strategy identifier
            proposal: Proposal dict (None if no proposal)
        """
        if proposal is not None:
            self.proposal.total_proposals += 1
            
            if "GEOMETRY" in strategy_id:
                self.proposal.strategy1_proposal_count += 1
            elif "KINEMATICS" in strategy_id:
                self.proposal.strategy2_proposal_count += 1
            elif "ABSENCE" in strategy_id:
                self.proposal.strategy3_proposal_count += 1
    
    def log_m6_denial(self):
        """Log M6 permission denial."""
        self.proposal.m6_denial_count += 1
    
    def log_conflict(self):
        """Log proposal conflict (multiple proposals)."""
        self.proposal.conflict_count += 1
    
    def log_arbitration(self, *, decision_code: str, reason_code: str):
        """
        Log EP-3 arbitration decision.
        
        Args:
            decision_code: Decision code (AUTHORIZED_ACTION, NO_ACTION, REJECTED_ACTION)
            reason_code: Reason code
        """
        if decision_code == "AUTHORIZED_ACTION":
            self.arbitration.authorized_count += 1
        elif decision_code == "NO_ACTION":
            self.arbitration.no_action_count += 1
        elif decision_code == "REJECTED_ACTION":
            self.arbitration.rejected_count += 1
        
        self.arbitration.reason_codes[reason_code] += 1
    
    def log_execution(
        self,
        *,
        result_code: str,
        reason_code: str,
        timestamp: float
    ):
        """
        Log EP-4 execution result.
        
        Args:
            result_code: Result code (SUCCESS, FAILED_SAFE, NOOP, REJECTED)
            reason_code: Reason code
            timestamp: Execution timestamp
        """
        if result_code == "SUCCESS":
            self.execution.success_count += 1
            self.temporal.action_timestamps.append(timestamp)
        elif result_code == "FAILED_SAFE":
            self.execution.failed_safe_count += 1
            # Parse reason for categorization
            if "RISK_GATE" in reason_code:
                self.execution.risk_gate_failures[reason_code] += 1
            elif "EXCHANGE_CONSTRAINT" in reason_code:
                self.execution.exchange_constraint_failures[reason_code] += 1
        elif result_code == "NOOP":
            self.execution.noop_count += 1
        elif result_code == "REJECTED":
            self.execution.rejected_count += 1
    
    def finalize_temporal_metrics(self):
        """Compute final temporal metrics."""
        if len(self.temporal.action_timestamps) < 2:
            return
        
        # Compute time between actions
        for i in range(1, len(self.temporal.action_timestamps)):
            delta = self.temporal.action_timestamps[i] - self.temporal.action_timestamps[i-1]
            self.temporal.time_between_actions.append(delta)
        
        # Find longest inactivity
        if self.temporal.time_between_actions:
            self.temporal.longest_inactivity = max(self.temporal.time_between_actions)
        
        # Count bursts (actions within 60 seconds)
        burst_threshold = 60.0
        for delta in self.temporal.time_between_actions:
            if delta < burst_threshold:
                self.temporal.burst_count += 1
    
    def to_dict(self) -> dict:
        """
        Export all metrics as dict.
        
        Returns:
            Complete metrics dictionary
        """
        self.finalize_temporal_metrics()
        
        return {
            "observation": {
                "tier_a_nonzero": self.observation.tier_a_nonzero_count,
                "tier_b1_nonzero": self.observation.tier_b1_nonzero_count,
                "tier_b2_nonzero": self.observation.tier_b2_nonzero_count,
                "total_outputs": len(self.observation.primitive_outputs)
            },
            "proposal": {
                "strategy1_proposals": self.proposal.strategy1_proposal_count,
                "strategy2_proposals": self.proposal.strategy2_proposal_count,
                "strategy3_proposals": self.proposal.strategy3_proposal_count,
                "total_proposals": self.proposal.total_proposals,
                "conflicts": self.proposal.conflict_count,
                "m6_denials": self.proposal.m6_denial_count
            },
            "arbitration": {
                "authorized": self.arbitration.authorized_count,
                "no_action": self.arbitration.no_action_count,
                "rejected": self.arbitration.rejected_count,
                "reason_codes": dict(self.arbitration.reason_codes)
            },
            "execution": {
                "success": self.execution.success_count,
                "failed_safe": self.execution.failed_safe_count,
                "noop": self.execution.noop_count,
                "rejected": self.execution.rejected_count,
                "risk_gate_failures": dict(self.execution.risk_gate_failures),
                "exchange_constraint_failures": dict(self.execution.exchange_constraint_failures)
            },
            "temporal": {
                "total_actions": len(self.temporal.action_timestamps),
                "longest_inactivity": self.temporal.longest_inactivity,
                "burst_count": self.temporal.burst_count,
                "avg_time_between_actions": (
                    sum(self.temporal.time_between_actions) / len(self.temporal.time_between_actions)
                    if self.temporal.time_between_actions else 0.0
                )
            }
        }
    
    def save_to_file(self, *, output_path: str):
        """
        Save metrics to JSON file.
        
        Args:
            output_path: Output file path
        """
        with open(output_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
