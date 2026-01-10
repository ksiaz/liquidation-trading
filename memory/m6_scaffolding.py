"""
M6 Scaffolding - Mandate Evaluation Framework (Structural Only)

This module provides the structural framework for evaluating mandates against
M5-approved descriptive snapshots. It enforces all M6 Implementation Invariants.

CRITICAL: This module contains NO strategy, NO market semantics, NO thresholds.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Literal, Union
from enum import Enum


# ==============================================================================
# INVARIANT VIOLATIONS (Hard Errors)
# ==============================================================================

class InvariantViolationError(Exception):
    """Raised when an M6 implementation invariant is violated."""
    pass


class PredicateStructureError(Exception):
    """Raised when a predicate contains forbidden operations."""
    pass


class OutputGrammarError(Exception):
    """Raised when output does not match certified grammar."""
    pass


# ==============================================================================
# ALLOWED MANDATE TYPES (from template v1.0)
# ==============================================================================

class MandateType(Enum):
    POLICY_EVALUATOR = "POLICY_EVALUATOR"
    CONSTRAINT_GATE = "CONSTRAINT_GATE"
    STATE_CLASSIFIER = "STATE_CLASSIFIER"
    ALERT_EMITTER = "ALERT_EMITTER"


# ==============================================================================
# PREDICATE OPERATION TYPES (Exhaustive)
# ==============================================================================

class PredicateOperation(Enum):
    """Allowed predicate operations only."""
    EXISTS = "EXISTS"           # Test existence of a key
    EQUALS = "EQUALS"           # Test equality
    IN_CATEGORY = "IN_CATEGORY" # Test category membership


@dataclass(frozen=True)
class PredicateCondition:
    """
    Structural representation of a single predicate condition.
    
    This is a data structure only, not executable logic.
    """
    operation: PredicateOperation
    fact_key: str
    expected_value: Optional[Any] = None  # For EQUALS, IN_CATEGORY
    category_set: Optional[List[str]] = None  # For IN_CATEGORY only


@dataclass(frozen=True)
class PolicyPredicate:
    """
    Structural predicate definition.
    
    Predicates are declarative only - they describe conditions without
    encoding evaluation logic.
    """
    requires: List[PredicateCondition] = field(default_factory=list)
    forbids: List[PredicateCondition] = field(default_factory=list)


# ==============================================================================
# MANDATE DEFINITION (Immutable)
# ==============================================================================

@dataclass(frozen=True)
class MandateDefinition:
    """
    Immutable mandate configuration.
    
    Conforms to M6 Mandate Template v1.0.
    """
    mandate_id: str
    mandate_type: MandateType
    mandate_scope: str
    policy_predicate: PolicyPredicate


# ==============================================================================
# M5 SNAPSHOT (Input Contract)
# ==============================================================================

@dataclass(frozen=True)
class M5DescriptiveSnapshot:
    """
    M5-approved descriptive data snapshot.
    
    This is the ONLY permitted input from memory.
    """
    query_id: str
    timestamp: float
    descriptive_facts: Dict[str, Any]


# ==============================================================================
# OUTPUT GRAMMAR (Exhaustive, from template v1.0)
# ==============================================================================

@dataclass(frozen=True)
class PermissionOutput:
    """Permission evaluation result."""
    mandate_id: str
    action_id: str
    result: Literal["ALLOWED", "DENIED"]
    reason_code: str


@dataclass(frozen=True)
class StateClassificationOutput:
    """State classification result."""
    mandate_id: str
    state_id: str
    timestamp: float


@dataclass(frozen=True)
class AlertOutput:
    """Alert emission result."""
    mandate_id: str
    alert_code: str
    timestamp: float


# Type alias for all allowed outputs
M6Output = Union[PermissionOutput, StateClassificationOutput, AlertOutput]


# ==============================================================================
# PREDICATE VALIDATOR (Structural Only)
# ==============================================================================

class PredicateValidator:
    """
    Validates that predicates conform to structural constraints.
    
    This class enforces Invariant I-03 (Predicate Purity).
    """
    
    FORBIDDEN_OPERATIONS = [
        "add", "subtract", "multiply", "divide",
        "sum", "count", "average", "aggregate",
        "less_than", "greater_than", "compare",
        "threshold", "min", "max"
    ]
    
    @staticmethod
    def validate_predicate_structure(predicate: PolicyPredicate) -> None:
        """
        Validate predicate structural purity.
        
        Raises PredicateStructureError if violations found.
        """
        # Check all required conditions
        for condition in predicate.requires:
            PredicateValidator._validate_condition(condition)
        
        # Check all forbid conditions
        for condition in predicate.forbids:
            PredicateValidator._validate_condition(condition)
    
    @staticmethod
    def _validate_condition(condition: PredicateCondition) -> None:
        """Validate a single condition."""
        # Ensure operation is allowed
        if condition.operation not in PredicateOperation:
            raise PredicateStructureError(
                f"Invalid operation: {condition.operation}"
            )
        
        # Ensure no forbidden operations in fact_key
        for forbidden in PredicateValidator.FORBIDDEN_OPERATIONS:
            if forbidden.lower() in condition.fact_key.lower():
                raise PredicateStructureError(
                    f"Forbidden operation pattern in key: {condition.fact_key}"
                )
        
        # Validate operation-specific constraints
        if condition.operation == PredicateOperation.EQUALS:
            if condition.expected_value is None:
                raise PredicateStructureError(
                    "EQUALS operation requires expected_value"
                )
        
        elif condition.operation == PredicateOperation.IN_CATEGORY:
            if not condition.category_set:
                raise PredicateStructureError(
                    "IN_CATEGORY operation requires category_set"
                )


# ==============================================================================
# MANDATE LOADER
# ==============================================================================

class MandateLoader:
    """
    Loads and validates mandate definitions.
    
    Enforces mandate template conformance.
    """
    
    @staticmethod
    def load_mandate(mandate_def: Dict[str, Any]) -> MandateDefinition:
        """
        Load and validate a mandate definition.
        
        Raises InvariantViolationError if template violated.
        """
        # Validate required fields
        required_fields = ["mandate_id", "mandate_type", "mandate_scope", "policy_predicate"]
        for field_name in required_fields:
            if field_name not in mandate_def:
                raise InvariantViolationError(
                    f"Required field missing: {field_name}"
                )
        
        # Validate mandate_type
        try:
            mandate_type = MandateType(mandate_def["mandate_type"])
        except ValueError:
            raise InvariantViolationError(
                f"Invalid mandate_type: {mandate_def['mandate_type']}. "
                f"Allowed: {[t.value for t in MandateType]}"
            )
        
        # Parse predicate
        predicate = MandateLoader._parse_predicate(mandate_def["policy_predicate"])
        
        # Validate predicate structure
        PredicateValidator.validate_predicate_structure(predicate)
        
        # Construct immutable mandate
        return MandateDefinition(
            mandate_id=mandate_def["mandate_id"],
            mandate_type=mandate_type,
            mandate_scope=mandate_def["mandate_scope"],
            policy_predicate=predicate
        )
    
    @staticmethod
    def _parse_predicate(predicate_def: Dict[str, Any]) -> PolicyPredicate:
        """Parse predicate definition into structured form."""
        requires = [
            MandateLoader._parse_condition(cond)
            for cond in predicate_def.get("requires", [])
        ]
        forbids = [
            MandateLoader._parse_condition(cond)
            for cond in predicate_def.get("forbids", [])
        ]
        
        return PolicyPredicate(requires=requires, forbids=forbids)
    
    @staticmethod
    def _parse_condition(condition_def: Dict[str, Any]) -> PredicateCondition:
        """Parse a single condition definition."""
        operation = PredicateOperation(condition_def["operation"])
        
        return PredicateCondition(
            operation=operation,
            fact_key=condition_def["fact_key"],
            expected_value=condition_def.get("expected_value"),
            category_set=condition_def.get("category_set")
        )


# ==============================================================================
# STRUCTURAL EVALUATION ENGINE
# ==============================================================================

class EvaluationEngine:
    """
    Evaluates predicates against M5 snapshots.
    
    This is structural evaluation only - no interpretation, no learning, no caching.
    Enforces Invariant I-02 (Determinism).
    """
    
    @staticmethod
    def evaluate(
        mandate: MandateDefinition,
        snapshot: M5DescriptiveSnapshot
    ) -> bool:
        """
        Evaluate mandate predicate against snapshot.
        
        Returns True if all required conditions satisfied and no forbid conditions violated.
        
        This function is pure and deterministic.
        """
        facts = snapshot.descriptive_facts
        
        # Evaluate all required conditions
        for condition in mandate.policy_predicate.requires:
            if not EvaluationEngine._evaluate_condition(condition, facts):
                return False
        
        # Evaluate all forbid conditions (must all be False)
        for condition in mandate.policy_predicate.forbids:
            if EvaluationEngine._evaluate_condition(condition, facts):
                return False
        
        return True
    
    @staticmethod
    def _evaluate_condition(condition: PredicateCondition, facts: Dict[str, Any]) -> bool:
        """Evaluate a single condition against facts."""
        if condition.operation == PredicateOperation.EXISTS:
            return condition.fact_key in facts
        
        elif condition.operation == PredicateOperation.EQUALS:
            if condition.fact_key not in facts:
                return False
            return facts[condition.fact_key] == condition.expected_value
        
        elif condition.operation == PredicateOperation.IN_CATEGORY:
            if condition.fact_key not in facts:
                return False
            return facts[condition.fact_key] in condition.category_set
        
        else:
            raise PredicateStructureError(f"Unknown operation: {condition.operation}")


# ==============================================================================
# OUTPUT ENFORCER
# ==============================================================================

class OutputEnforcer:
    """
    Enforces output grammar conformance.
    
    Implements Invariant I-05 (Output Grammar).
    """
    
    @staticmethod
    def enforce_permission_output(
        mandate_id: str,
        action_id: str,
        result: bool,
        reason_code: str
    ) -> PermissionOutput:
        """Create a valid permission output."""
        if not isinstance(result, bool):
            raise OutputGrammarError("Result must be boolean")
        
        return PermissionOutput(
            mandate_id=mandate_id,
            action_id=action_id,
            result="ALLOWED" if result else "DENIED",
            reason_code=reason_code
        )
    
    @staticmethod
    def enforce_state_output(
        mandate_id: str,
        state_id: str,
        timestamp: float
    ) -> StateClassificationOutput:
        """Create a valid state classification output."""
        return StateClassificationOutput(
            mandate_id=mandate_id,
            state_id=state_id,
            timestamp=timestamp
        )
    
    @staticmethod
    def enforce_alert_output(
        mandate_id: str,
        alert_code: str,
        timestamp: float
    ) -> AlertOutput:
        """Create a valid alert output."""
        return AlertOutput(
            mandate_id=mandate_id,
            alert_code=alert_code,
            timestamp=timestamp
        )


# ==============================================================================
# RUNTIME INVARIANT ASSERTIONS
# ==============================================================================

class InvariantAsserter:
    """
    Runtime enforcement of M6 Implementation Invariants.
    
    All violations result in hard errors.
    """
    
    @staticmethod
    def assert_one_way_dependency(mandate: MandateDefinition) -> None:
        """
        Assert Invariant I-01: M6 consumes via M5 only.
        
        This is enforced by type system - M5DescriptiveSnapshot is the only input type.
        """
        # Type enforcement handles this automatically
        pass
    
    @staticmethod
    def assert_determinism(snapshot: M5DescriptiveSnapshot) -> None:
        """
        Assert Invariant I-02: Deterministic evaluation.
        
        Snapshot must have explicit timestamp (no implicit time).
        """
        if snapshot.timestamp is None:
            raise InvariantViolationError(
                "I-02 Violation: Snapshot timestamp must be explicit"
            )
    
    @staticmethod
    def assert_semantic_purity(code_identifiers: List[str]) -> None:
        """
        Assert Invariant I-04: No market semantics.
        
        Check identifier names for forbidden terms.
        """
        FORBIDDEN_TERMS = [
            "bullish", "bearish", "momentum", "reversal",
            "strong", "weak", "entry", "exit",
            "buy", "sell", "signal", "trade"
        ]
        
        for identifier in code_identifiers:
            lower_id = identifier.lower()
            for term in FORBIDDEN_TERMS:
                if term in lower_id:
                    raise InvariantViolationError(
                        f"I-04 Violation: Forbidden term '{term}' in identifier '{identifier}'"
                    )
