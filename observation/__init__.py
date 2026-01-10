"""
Memory-Centric Observation System (Sealed)

Exposes ONLY the Governance Gate.
"""

from .governance import ObservationSystem
from .types import ObservationSnapshot

__all__ = ['ObservationSystem', 'ObservationSnapshot']
