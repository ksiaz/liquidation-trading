"""
M4 Views - Schema Compliance Module.

Provides schema-compliant import path per SYSTEM_MAP_SCHEMA.yaml.

M4 Layer Constraints (SYSTEM_GUIDANCE.md):
- Forbidden: view_quality_ranking, metric_interpretation, composite_scores
- Epistemic class: structural_only

Individual primitives are in memory/m4_*.py (27 modules).
Actual primitive computation is handled by observation/governance.py.

Authority: SYSTEM_MAP_SCHEMA.yaml declares memory/m4_views.py
"""

from typing import Dict, Optional, Any, TYPE_CHECKING

# Re-export M4PrimitiveBundle from observation types
from observation.types import M4PrimitiveBundle

# Type-only imports for primitives (avoid circular imports)
if TYPE_CHECKING:
    from memory.m4_zone_geometry import ZonePenetrationDepth, DisplacementOriginAnchor
    from memory.m4_traversal_kinematics import PriceTraversalVelocity, TraversalCompactness
    from memory.m4_structural_absence import StructuralAbsenceDuration
    from memory.m4_cascade_proximity import LiquidationCascadeProximity
    from memory.m4_cascade_state import CascadeStateObservation
    from memory.m4_leverage_concentration import LeverageConcentrationRatio
    from memory.m4_open_interest_bias import OpenInterestDirectionalBias


class M4Views:
    """
    Schema-compliant M4 views entry point.

    NOTE: Actual primitive computation is performed by observation/governance.py
    via _compute_primitives_for_symbol(). This class provides schema compliance
    and can be used for direct primitive access if needed.

    Constraints:
    - No quality ranking of views
    - No metric interpretation
    - No composite score creation
    - All outputs are structural facts only
    """

    @staticmethod
    def get_empty_bundle(symbol: str) -> M4PrimitiveBundle:
        """Return an empty primitive bundle for a symbol."""
        return M4PrimitiveBundle.empty(symbol)


__all__ = [
    "M4Views",
    "M4PrimitiveBundle",
]
