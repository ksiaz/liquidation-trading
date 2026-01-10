"""
Replay Infrastructure Package

Provides deterministic event loop and clock for historical replay.

CRITICAL RULES:
- No strategy logic in this module
- No indicators
- No shortcuts
- Replay must behave IDENTICALLY to live trading

Components:
- event_loop: Deterministic event processing (R1)
- feed_adapters: Historical data wrappers (R2)
- synchronizer: Multi-stream synchronization (R3)
- system_wrapper: System execution interface (R4)
- replay_controller: Complete orchestration (R5)
"""

from .event_loop import Event, SimulationClock, EventLoop
from .replay_controller import ReplayController

__all__ = [
    'Event',
    'SimulationClock',
    'EventLoop',
    'ReplayController',
]
