"""
Master Controller

Orchestrates all components of the Market Regime Masterframe.

RULES:
- SLBRS and EFFCS never active simultaneously (mutual exclusion)
- Strategies cannot self-activate (controller-only)
- Cooldown blocks ALL evaluations (no exceptions)
"""

from typing import Optional, Dict, List
import sys
sys.path.append('d:/liquidation-trading')

from masterframe.data_ingestion.types import SynchronizedData
from masterframe.metrics import MetricsEngine
from masterframe.orderbook_zoning import ZoneState
from masterframe.regime_classifier import RegimeClassifier, RegimeType
from masterframe.slbrs import (
    BlockDetector,
    BlockTracker,
    SLBRSStateMachine,
    SLBRSState,
)
from masterframe.effcs import EFFCSStateMachine, EFFCSState


class MasterController:
    """
    Master controller for Market Regime Masterframe.
    
    INVARIANT: SLBRS and EFFCS never active simultaneously.
    INVARIANT: Strategies disabled when regime = DISABLED.
    INVARIANT: Cooldown blocks all evaluations.
    """
    
    # Cooldown period after trade exit (PROMPT 10: 5 minutes)
    COOLDOWN_SECONDS = 300.0
    
    def __init__(self):
        """Initialize master controller."""
        # Core components
        self.regime_classifier = RegimeClassifier()
        self.metrics_engine = MetricsEngine()
        self.zone_state = ZoneState()
        
        # SLBRS components
        self.block_detector = BlockDetector()
        self.block_tracker = BlockTracker()
        self.slbrs = SLBRSStateMachine()
        
        # EFFCS components
        self.effcs = EFFCSStateMachine()
        
        # Controller state
        self.active_strategy: Optional[str] = None  # 'SLBRS' or 'EFFCS'
        self.current_regime: RegimeType = RegimeType.DISABLED
        self.last_trade_exit_time: Optional[float] = None
        self.in_cooldown: bool = False
    
    def update(
        self,
        synchronized_data: SynchronizedData,
        klines_1m_all: List,
        klines_5m_all: List,
        current_time: float
    ) -> Optional[str]:
        """
        Main controller update.
        
        Args:
            synchronized_data: Aligned data snapshot
            klines_1m_all: All 1m klines for ATR
            klines_5m_all: All 5m klines for ATR
            current_time: Current timestamp
        
        Returns:
            Trade signal ('ENTER', 'EXIT', or None)
        
        RULE: Check cooldown first.
        RULE: Classify regime.
        RULE: Enforce mutual exclusion.
        RULE: Route to active strategy only.
        """
        # 1. CHECK COOLDOWN
        if self._check_cooldown(current_time):
            return None  # Block all evaluations
        
        # 2. COMPUTE ZONES AND METRICS
        zones, zone_metrics = self.zone_state.update(
            synchronized_data.orderbook,
            synchronized_data.trades,
            synchronized_data.timestamp
        )
        
        metrics = self.metrics_engine.compute_metrics(
            synchronized_data,
            klines_1m_all,
            klines_5m_all,
            current_time
        )
        
        # 3. CLASSIFY REGIME
        regime_state = self.regime_classifier.classify(
            current_price=zones.mid_price,
            metrics=metrics,
            current_time=current_time
        )
        
        self.current_regime = regime_state.regime
        
        # 4. ENFORCE MUTUAL EXCLUSION
        self._enforce_mutual_exclusion(regime_state.regime)
        
        # 5. ROUTE TO ACTIVE STRATEGY
        signal = self._route_to_strategy(
            regime_state.regime,
            zones,
            zone_metrics,
            metrics,
            current_time
        )
        
        # 6. HANDLE SIGNAL
        if signal:
            self._handle_signal(signal, current_time)
        
        return signal
    
    def _check_cooldown(self, current_time: float) -> bool:
        """
        Check if in cooldown period.
        
        Returns:
            True if in cooldown (blocks evaluation)
        
        RULE: Cooldown blocks ALL evaluations.
        """
        if self.last_trade_exit_time is None:
            self.in_cooldown = False
            return False
        
        elapsed = current_time - self.last_trade_exit_time
        self.in_cooldown = elapsed < self.COOLDOWN_SECONDS
        
        return self.in_cooldown
    
    def _enforce_mutual_exclusion(self, regime: RegimeType) -> None:
        """
        Enforce mutual exclusion: SLBRS ⊕ EFFCS.
        
        RULE: At most ONE strategy active.
        RULE: Regime determines which strategy.
        
        Routing:
        - SIDEWAYS → SLBRS active, EFFCS disabled
        - EXPANSION → EFFCS active, SLBRS disabled
        - DISABLED → Both disabled
        """
        if regime == RegimeType.SIDEWAYS:
            self.active_strategy = 'SLBRS'
        elif regime == RegimeType.EXPANSION:
            self.active_strategy = 'EFFCS'
        else:  # DISABLED
            self.active_strategy = None
    
    def _route_to_strategy(
        self,
        regime: RegimeType,
        zones,
        zone_metrics: Dict,
        metrics,
        current_time: float
    ) -> Optional[str]:
        """
        Route data to active strategy only.
        
        Returns:
            Trade signal from active strategy
        
        RULE: Only active strategy receives updates.
        RULE: Inactive strategies do not evaluate.
        """
        if self.active_strategy == 'SLBRS':
            # SLBRS-specific logic
            blocks = self.block_detector.detect_blocks(
                zones, zone_metrics, current_time
            )
            
            active_blocks = self.block_tracker.update(
                blocks, zones.mid_price, current_time
            )
            
            tradable_blocks = self.block_tracker.get_tradable_blocks()
            
            return self.slbrs.update(
                regime=regime,
                tradable_blocks=tradable_blocks,
                current_price=zones.mid_price,
                current_time=current_time,
                atr=metrics.atr_5m if metrics.atr_5m else 1.0
            )
        
        elif self.active_strategy == 'EFFCS':
            # EFFCS-specific logic
            return self.effcs.update(
                regime=regime,
                current_price=zones.mid_price,
                metrics=metrics,
                current_time=current_time
            )
        
        # No active strategy
        return None
    
    def _handle_signal(self, signal: str, current_time: float) -> None:
        """
        Handle trade signal.
        
        RULE: Start cooldown on EXIT.
        """
        if signal == 'EXIT':
            self.last_trade_exit_time = current_time
            self.in_cooldown = True
    
    def get_active_strategy(self) -> Optional[str]:
        """Get currently active strategy name."""
        return self.active_strategy
    
    def get_current_regime(self) -> RegimeType:
        """Get current regime."""
        return self.current_regime
    
    def is_in_cooldown(self) -> bool:
        """Check if in cooldown."""
        return self.in_cooldown
    
    def get_slbrs_state(self) -> SLBRSState:
        """Get SLBRS state."""
        return self.slbrs.get_state()
    
    def get_effcs_state(self) -> EFFCSState:
        """Get EFFCS state."""
        return self.effcs.get_state()
    
    def verify_mutual_exclusion(self) -> bool:
        """
        Verify mutual exclusion invariant.
        
        Returns:
            True if invariant holds
        
        INVARIANT: SLBRS and EFFCS never both active.
        """
        slbrs_active = self.slbrs.get_state() != SLBRSState.DISABLED
        effcs_active = self.effcs.get_state() != EFFCSState.DISABLED
        
        # Both cannot be active
        return not (slbrs_active and effcs_active)
    
    def reset(self) -> None:
        """Hard reset controller and all components."""
        self.regime_classifier = RegimeClassifier()
        self.slbrs.reset()
        self.effcs.reset()
        self.block_detector.reset()
        self.block_tracker.reset()
        
        self.active_strategy = None
        self.current_regime = RegimeType.DISABLED
        self.last_trade_exit_time = None
        self.in_cooldown = False
