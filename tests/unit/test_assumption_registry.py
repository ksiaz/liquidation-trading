"""Unit tests for AssumptionRegistry."""

import pytest
import time

from runtime.meta.assumption_registry import (
    AssumptionRegistry,
    RegistryConfig,
    create_standard_assumptions,
)
from runtime.meta.types import Assumption, AssumptionStatus


class TestAssumptionRegistry:
    """Tests for AssumptionRegistry."""

    def test_init_defaults(self):
        """Test registry initialization."""
        registry = AssumptionRegistry()
        assert len(registry._assumptions) == 0
        assert len(registry._component_dependencies) == 0

    def test_register_assumption(self):
        """Test registering an assumption."""
        registry = AssumptionRegistry()

        assumption = Assumption(
            name="test_assumption",
            description="Test description",
            category="test",
            affected_components=["ComponentA", "ComponentB"]
        )
        registry.register(assumption)

        assert "test_assumption" in registry._assumptions
        assert "ComponentA" in registry._component_dependencies
        assert "ComponentB" in registry._component_dependencies

    def test_unregister_assumption(self):
        """Test unregistering an assumption."""
        registry = AssumptionRegistry()

        assumption = Assumption(
            name="test",
            description="Test",
            category="test",
            affected_components=["Component"]
        )
        registry.register(assumption)
        registry.unregister("test")

        assert "test" not in registry._assumptions

    def test_get_assumption(self):
        """Test getting an assumption."""
        registry = AssumptionRegistry()

        assumption = Assumption(
            name="test",
            description="Test",
            category="test"
        )
        registry.register(assumption)

        result = registry.get("test")
        assert result is not None
        assert result.name == "test"

        assert registry.get("nonexistent") is None

    def test_validate_passing(self):
        """Test validating a passing assumption."""
        registry = AssumptionRegistry()

        assumption = Assumption(
            name="always_true",
            description="Always passes",
            category="test",
            test_fn=lambda: True
        )
        registry.register(assumption)

        result = registry.validate("always_true")

        assert result is True
        assert assumption.status == AssumptionStatus.VALID
        assert assumption.consecutive_failures == 0

    def test_validate_failing(self):
        """Test validating a failing assumption."""
        config = RegistryConfig(
            max_consecutive_failures=3,
            warning_threshold_failures=2
        )
        registry = AssumptionRegistry(config=config)

        assumption = Assumption(
            name="always_false",
            description="Always fails",
            category="test",
            test_fn=lambda: False
        )
        registry.register(assumption)

        # First failure - still valid
        registry.validate("always_false")
        assert assumption.consecutive_failures == 1
        assert assumption.status == AssumptionStatus.UNTESTED  # Not yet warning

        # Second failure - warning
        registry.validate("always_false")
        assert assumption.consecutive_failures == 2
        assert assumption.status == AssumptionStatus.WARNING

        # Third failure - invalid
        registry.validate("always_false")
        assert assumption.consecutive_failures == 3
        assert assumption.status == AssumptionStatus.INVALID

    def test_validate_resets_on_success(self):
        """Test that success resets failure counter."""
        registry = AssumptionRegistry()

        counter = [0]

        def alternating():
            counter[0] += 1
            return counter[0] % 2 == 0  # Fail, Pass, Fail, Pass...

        assumption = Assumption(
            name="alternating",
            description="Alternates",
            category="test",
            test_fn=alternating
        )
        registry.register(assumption)

        # Fail
        registry.validate("alternating")
        assert assumption.consecutive_failures == 1

        # Pass - resets
        registry.validate("alternating")
        assert assumption.consecutive_failures == 0
        assert assumption.status == AssumptionStatus.VALID

    def test_validate_all(self):
        """Test validating all assumptions."""
        registry = AssumptionRegistry()

        for i, result in enumerate([True, False, True]):
            assumption = Assumption(
                name=f"test_{i}",
                description=f"Test {i}",
                category="test",
                test_fn=lambda r=result: r
            )
            registry.register(assumption)

        results = registry.validate_all()

        assert results["test_0"] is True
        assert results["test_1"] is False
        assert results["test_2"] is True

    def test_validate_category(self):
        """Test validating assumptions by category."""
        registry = AssumptionRegistry()

        # Use explicit unique names
        for i, category in enumerate(["cat_a", "cat_a", "cat_b"]):
            assumption = Assumption(
                name=f"test_{category}_{i}",
                description="Test",
                category=category,
                test_fn=lambda: True
            )
            registry.register(assumption)

        results = registry.validate_category("cat_a")
        assert len(results) == 2

    def test_is_valid(self):
        """Test checking assumption validity."""
        registry = AssumptionRegistry()

        assumption = Assumption(
            name="test",
            description="Test",
            category="test",
            test_fn=lambda: True
        )
        registry.register(assumption)

        # Before validation
        assert not registry.is_valid("test")

        # After validation
        registry.validate("test")
        assert registry.is_valid("test")

    def test_is_safe_to_use_no_dependencies(self):
        """Test component with no assumptions is safe."""
        registry = AssumptionRegistry()
        assert registry.is_safe_to_use("UnknownComponent") is True

    def test_is_safe_to_use_valid_assumptions(self):
        """Test component with valid assumptions is safe."""
        registry = AssumptionRegistry()

        assumption = Assumption(
            name="component_works",
            description="Component assumption",
            category="test",
            test_fn=lambda: True,
            affected_components=["MyComponent"]
        )
        registry.register(assumption)
        registry.validate("component_works")

        assert registry.is_safe_to_use("MyComponent") is True

    def test_is_safe_to_use_invalid_assumption(self):
        """Test component with invalid assumption is not safe."""
        config = RegistryConfig(max_consecutive_failures=1)
        registry = AssumptionRegistry(config=config)

        assumption = Assumption(
            name="broken",
            description="Broken assumption",
            category="test",
            test_fn=lambda: False,
            affected_components=["BrokenComponent"]
        )
        registry.register(assumption)
        registry.validate("broken")

        assert registry.is_safe_to_use("BrokenComponent") is False

    def test_is_safe_to_use_expired_assumption(self):
        """Test component with expired assumption is not safe."""
        registry = AssumptionRegistry()

        assumption = Assumption(
            name="expired",
            description="Expired assumption",
            category="test",
            valid_until_ns=1,  # Already expired
            affected_components=["ExpiredComponent"]
        )
        registry.register(assumption)

        assert registry.is_safe_to_use("ExpiredComponent") is False

    def test_get_component_assumptions(self):
        """Test getting assumptions for a component."""
        registry = AssumptionRegistry()

        for i in range(3):
            assumption = Assumption(
                name=f"test_{i}",
                description=f"Test {i}",
                category="test",
                affected_components=["SharedComponent"] if i < 2 else ["Other"]
            )
            registry.register(assumption)

        assumptions = registry.get_component_assumptions("SharedComponent")
        assert len(assumptions) == 2

    def test_get_invalid_assumptions(self):
        """Test getting invalid assumptions."""
        config = RegistryConfig(max_consecutive_failures=1)
        registry = AssumptionRegistry(config=config)

        for i, passes in enumerate([True, False, True]):
            assumption = Assumption(
                name=f"test_{i}",
                description=f"Test {i}",
                category="test",
                test_fn=lambda p=passes: p
            )
            registry.register(assumption)
            registry.validate(f"test_{i}")

        invalid = registry.get_invalid_assumptions()
        assert len(invalid) == 1
        assert invalid[0].name == "test_1"

    def test_get_expired_assumptions(self):
        """Test getting expired assumptions."""
        registry = AssumptionRegistry()

        # Non-expired
        registry.register(Assumption(
            name="fresh",
            description="Fresh",
            category="test"
        ))

        # Expired
        registry.register(Assumption(
            name="old",
            description="Old",
            category="test",
            valid_until_ns=1
        ))

        expired = registry.get_expired_assumptions()
        assert len(expired) == 1
        assert expired[0].name == "old"

    def test_get_assumptions_needing_revalidation(self):
        """Test getting assumptions needing revalidation."""
        registry = AssumptionRegistry()

        # Untested
        registry.register(Assumption(
            name="untested",
            description="Never tested",
            category="test"
        ))

        # Validated
        validated = Assumption(
            name="validated",
            description="Validated",
            category="test",
            test_fn=lambda: True
        )
        registry.register(validated)
        registry.validate("validated")

        needing = registry.get_assumptions_needing_revalidation()
        assert len(needing) == 1
        assert needing[0].name == "untested"

    def test_get_by_category(self):
        """Test getting assumptions by category."""
        registry = AssumptionRegistry()

        # Use explicit unique names
        for i, category in enumerate(["market", "market", "execution"]):
            registry.register(Assumption(
                name=f"test_{category}_{i}",
                description="Test",
                category=category
            ))

        market = registry.get_by_category("market")
        assert len(market) == 2

    def test_get_summary(self):
        """Test getting registry summary."""
        config = RegistryConfig(max_consecutive_failures=1)
        registry = AssumptionRegistry(config=config)

        # Various states
        registry.register(Assumption(
            name="valid",
            description="Valid",
            category="cat_a",
            test_fn=lambda: True
        ))
        registry.register(Assumption(
            name="invalid",
            description="Invalid",
            category="cat_b",
            test_fn=lambda: False,
            affected_components=["Broken"]
        ))

        registry.validate_all()

        summary = registry.get_summary()

        assert summary['total_assumptions'] == 2
        assert summary['invalid_count'] == 1
        assert "Broken" in summary['affected_components']

    def test_reset(self):
        """Test resetting an assumption."""
        registry = AssumptionRegistry()

        assumption = Assumption(
            name="test",
            description="Test",
            category="test",
            test_fn=lambda: True
        )
        registry.register(assumption)
        registry.validate("test")

        assert assumption.status == AssumptionStatus.VALID

        registry.reset("test")

        assert assumption.status == AssumptionStatus.UNTESTED
        assert assumption.last_tested_ns is None

    def test_reset_all(self):
        """Test resetting all assumptions."""
        registry = AssumptionRegistry()

        for i in range(3):
            assumption = Assumption(
                name=f"test_{i}",
                description=f"Test {i}",
                category="test",
                test_fn=lambda: True
            )
            registry.register(assumption)

        registry.validate_all()
        registry.reset_all()

        for assumption in registry.get_all():
            assert assumption.status == AssumptionStatus.UNTESTED

    def test_exception_handling(self):
        """Test handling of test function exceptions."""
        config = RegistryConfig(max_consecutive_failures=1)
        registry = AssumptionRegistry(config=config)

        assumption = Assumption(
            name="throws",
            description="Throws exception",
            category="test",
            test_fn=lambda: 1/0  # Will raise
        )
        registry.register(assumption)

        result = registry.validate("throws")

        assert result is False
        assert assumption.status == AssumptionStatus.INVALID


class TestAssumption:
    """Tests for Assumption dataclass."""

    def test_is_expired_by_valid_until(self):
        """Test expiration by valid_until."""
        assumption = Assumption(
            name="test",
            description="Test",
            category="test",
            valid_until_ns=1  # Already expired
        )
        assert assumption.is_expired() is True

    def test_is_expired_by_revalidation_period(self):
        """Test expiration by revalidation period."""
        now = int(time.time() * 1_000_000_000)

        assumption = Assumption(
            name="test",
            description="Test",
            category="test",
            requires_revalidation_after_ns=1,  # 1 nanosecond
            last_tested_ns=now - 1_000_000_000  # 1 second ago
        )
        assert assumption.is_expired() is True

    def test_not_expired(self):
        """Test non-expired assumption."""
        assumption = Assumption(
            name="test",
            description="Test",
            category="test"
        )
        assert assumption.is_expired() is False

    def test_to_dict(self):
        """Test conversion to dictionary."""
        assumption = Assumption(
            name="test",
            description="Test description",
            category="market",
            invalidation_action="disable feature",
            affected_components=["A", "B"]
        )

        d = assumption.to_dict()

        assert d['name'] == "test"
        assert d['description'] == "Test description"
        assert d['category'] == "market"
        assert d['affected_components'] == ["A", "B"]


class TestCreateStandardAssumptions:
    """Tests for create_standard_assumptions."""

    def test_returns_list(self):
        """Test that standard assumptions are created."""
        assumptions = create_standard_assumptions()

        assert isinstance(assumptions, list)
        assert len(assumptions) > 0

    def test_all_have_required_fields(self):
        """Test all assumptions have required fields."""
        assumptions = create_standard_assumptions()

        for a in assumptions:
            assert a.name
            assert a.description
            assert a.category

    def test_categories_are_valid(self):
        """Test all categories are from expected set."""
        valid_categories = {'market_structure', 'data_quality', 'execution', 'model'}
        assumptions = create_standard_assumptions()

        for a in assumptions:
            assert a.category in valid_categories
