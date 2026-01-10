"""
System Execution Wrapper

Wraps trading system for replay execution with per-timestamp interface.

INVARIANTS:
- One call per timestamp
- No internal time loops
- No lookahead
- Captures system state

GOAL:
Clean interface between replay infrastructure and trading system.
"""

from typing import Dict, Any, Optional
from masterframe.controller import MasterController
from masterframe.data_ingestion import SynchronizedData
from masterframe.regime_classifier import RegimeType


class ReplaySystemWrapper:
    """
    Wraps MasterController for replay execution.
    
    RULE: One execute() call per timestamp.
    RULE: No internal loops.
    RULE: No lookahead.
    """
    
    def __init__(self):
        """Initialize system wrapper."""
        self.controller = MasterController()
        self.execution_count = 0
        self.last_timestamp: Optional[float] = None
    
    def execute(
        self, 
        snapshot: SynchronizedData,
        timestamp: float,
        klines_1m_all: tuple = None,
        klines_5m_all: tuple = None
    ) -> Dict[str, Any]:
        """
        Execute trading system at timestamp.
        
        RULE: One call per timestamp only.
        RULE: Pass synchronized snapshot to controller.
        RULE: Capture and return state.
        
        Args:
            snapshot: Synchronized market data
            timestamp: Current simulation time
            klines_1m_all: All 1m klines for ATR calculation
            klines_5m_all: All 5m klines for ATR calculation
            
        Returns:
            Execution result dict containing:
            - timestamp: Execution timestamp
            - regime: Current regime
            - active_strategy: Active strategy (or None)
            - in_cooldown: Cooldown status
            - slbrs_state: SLBRS state machine state
            - effcs_state: EFFCS state machine state
            - execution_count: Total executions
        """
        # Use empty tuples if not provided
        if klines_1m_all is None:
            klines_1m_all = ()
        if klines_5m_all is None:
            klines_5m_all = ()
        
        # Update controller with snapshot
        self.controller.update(snapshot, klines_1m_all, klines_5m_all, timestamp)
        
        # Capture system state
        result = {
            'timestamp': timestamp,
            'regime': self.controller.get_current_regime().name if self.controller.get_current_regime() else 'UNKNOWN',
            'active_strategy': self.controller.get_active_strategy(),
            'in_cooldown': self.controller.is_in_cooldown(),
            'slbrs_state': self.controller.get_slbrs_state().name if self.controller.get_slbrs_state() else 'UNKNOWN',
            'effcs_state': self.controller.get_effcs_state().name if self.controller.get_effcs_state() else 'UNKNOWN',
            'execution_count': self.execution_count + 1,
        }
        
        self.execution_count += 1
        self.last_timestamp = timestamp
        
        return result
    
    def get_controller(self) -> MasterController:
        """
        Get underlying controller.
        
        Useful for accessing detailed state or metrics.
        
        Returns:
            MasterController instance
        """
        return self.controller
    
    def get_execution_count(self) -> int:
        """Get total number of executions."""
        return self.execution_count
    
    def __repr__(self) -> str:
        return f"ReplaySystemWrapper(executions={self.execution_count}, last_ts={self.last_timestamp})"
