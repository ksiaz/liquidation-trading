"""
Session Manager Module
Week 10: Session-Aware Parameters

Manages session-specific parameters for Asia/Europe/US trading sessions.
Provides session detection, circuit breaker limits, threshold multipliers, and risk adjustments.

LOCKED PARAMETERS:
- Session definitions: Asia 00:00-08:00, Europe 08:00-16:00, US 16:00-24:00 UTC
- Signal limits: From Week 1 empirical data (2× normal per Expert Q7)
- Threshold/risk multipliers: Calibrated from historical analysis

Expert Compliance: 100% - All parameters locked, no optimization
"""

import logging
from datetime import datetime
from typing import Dict, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class TradingSession(Enum):
    """Trading session classification"""
    ASIA = "ASIA"
    EUROPE = "EUROPE"
    US = "US"


class SessionManager:
    """
    Manage session-specific parameters for optimal performance across time zones.
    
    Different sessions have distinct characteristics:
    - Liquidity depth varies
    - Volatility patterns differ
    - Participant mix changes
    - Signal quality varies
    
    This manager provides session-aware parameters for:
    - Circuit breaker limits
    - Threshold multipliers
    - Risk adjustments
    - Position limits
    """
    
    # 🔒 LOCKED PARAMETERS (DO NOT MODIFY)
    
    # Session time ranges (UTC hours)
    SESSION_DEFINITIONS = {
        TradingSession.ASIA: (0, 8),      # 00:00-08:00 UTC
        TradingSession.EUROPE: (8, 16),   # 08:00-16:00 UTC
        TradingSession.US: (16, 24),      # 16:00-00:00 UTC (wraps to next day)
    }
    
    # Signal limits per session (from Week 1 empirical data)
    # Format: {'normal': typical count, 'threshold': 2× normal per Expert Q7}
    SESSION_SIGNAL_LIMITS = {
        TradingSession.ASIA: {
            'normal': 15,
            'threshold': 30,  # 2× normal
        },
        TradingSession.EUROPE: {
            'normal': 35,
            'threshold': 70,  # 2× normal
        },
        TradingSession.US: {
            'normal': 60,
            'threshold': 120,  # 2× normal
        },
    }
    
    # Threshold multipliers (calibrated from historical analysis)
    SESSION_THRESHOLD_MULTIPLIERS = {
        TradingSession.ASIA: 1.10,    # 10% higher (thinner books, more false drains)
        TradingSession.EUROPE: 1.00,  # Baseline
        TradingSession.US: 0.95,      # 5% lower (deeper books, more aggressive)
    }
    
    # Risk multipliers for position sizing
    SESSION_RISK_MULTIPLIERS = {
        TradingSession.ASIA: 0.8,     # Reduce size 20% (lower confidence)
        TradingSession.EUROPE: 1.0,   # Standard
        TradingSession.US: 1.0,       # Standard
    }
    
    # Max concurrent positions by session
    SESSION_MAX_POSITIONS = {
        TradingSession.ASIA: 2,       # Fewer signals → Fewer concurrent
        TradingSession.EUROPE: 3,     # Standard
        TradingSession.US: 3,         # More signals but same limit
    }
    
    def __init__(self):
        """Initialize session manager with locked parameters."""
        logger.info("SessionManager initialized")
        logger.info(f"Session definitions: {self.SESSION_DEFINITIONS}")
        logger.info(f"Signal limits: {self.SESSION_SIGNAL_LIMITS}")
        logger.info(f"Threshold multipliers: {self.SESSION_THRESHOLD_MULTIPLIERS}")
        logger.info(f"Risk multipliers: {self.SESSION_RISK_MULTIPLIERS}")
    
    @staticmethod
    def get_current_session(timestamp: float) -> TradingSession:
        """
        Determine trading session from timestamp.
        
        Args:
            timestamp: Unix timestamp (seconds)
        
        Returns:
            TradingSession enum (ASIA, EUROPE, US)
        """
        dt = datetime.utcfromtimestamp(timestamp)
        hour = dt.hour
        
        if 0 <= hour < 8:
            return TradingSession.ASIA
        elif 8 <= hour < 16:
            return TradingSession.EUROPE
        else:  # 16 <= hour < 24
            return TradingSession.US
    
    def get_session_parameters(self, session: TradingSession) -> Dict:
        """
        Get all session-specific parameters.
        
        Args:
            session: Trading session
        
        Returns:
            Dictionary with all session parameters
        """
        return {
            'session': session.value,
            'time_range': self.SESSION_DEFINITIONS[session],
            'signal_normal': self.SESSION_SIGNAL_LIMITS[session]['normal'],
            'signal_threshold': self.SESSION_SIGNAL_LIMITS[session]['threshold'],
            'threshold_multiplier': self.SESSION_THRESHOLD_MULTIPLIERS[session],
            'risk_multiplier': self.SESSION_RISK_MULTIPLIERS[session],
            'max_positions': self.SESSION_MAX_POSITIONS[session],
        }
    
    def get_circuit_breaker_limit(self, session: TradingSession) -> int:
        """
        Get circuit breaker signal limit for session.
        
        This is the threshold at which we pause trading to prevent overtrading.
        Set at 2× normal for each session per Expert Q7 guidance.
        
        Args:
            session: Trading session
        
        Returns:
            Signal count threshold for circuit breaker
        """
        return self.SESSION_SIGNAL_LIMITS[session]['threshold']
    
    def get_normal_signal_count(self, session: TradingSession) -> int:
        """
        Get typical signal count for session (from Week 1 data).
        
        Args:
            session: Trading session
        
        Returns:
            Normal signal count (median from historical data)
        """
        return self.SESSION_SIGNAL_LIMITS[session]['normal']
    
    def get_threshold_multiplier(self, session: TradingSession) -> float:
        """
        Get threshold adjustment factor for session.
        
        Higher multiplier = higher threshold = less sensitive
        Lower multiplier = lower threshold = more sensitive
        
        Args:
            session: Trading session
        
        Returns:
            Multiplier for liquidity drain threshold
        """
        return self.SESSION_THRESHOLD_MULTIPLIERS[session]
    
    def get_risk_multiplier(self, session: TradingSession) -> float:
        """
        Get position size risk multiplier for session.
        
        Lower multiplier = smaller positions = more conservative
        
        Args:
            session: Trading session
        
        Returns:
            Multiplier for position sizing
        """
        return self.SESSION_RISK_MULTIPLIERS[session]
    
    def get_max_positions(self, session: TradingSession) -> int:
        """
        Get maximum concurrent positions for session.
        
        Args:
            session: Trading session
        
        Returns:
            Max number of concurrent positions
        """
        return self.SESSION_MAX_POSITIONS[session]
    
    def is_overtrading(self, session: TradingSession, signal_count: int) -> bool:
        """
        Check if signal count exceeds session threshold.
        
        Args:
            session: Trading session
            signal_count: Current signal count for session
        
        Returns:
            True if overtrading detected
        """
        threshold = self.get_circuit_breaker_limit(session)
        return signal_count >= threshold
    
    def get_session_comparison(self) -> Dict:
        """
        Get side-by-side comparison of all sessions.
        
        Returns:
            Dictionary comparing session parameters
        """
        comparison = {}
        for session in TradingSession:
            comparison[session.value] = self.get_session_parameters(session)
        
        return comparison


def test_session_manager():
    """Test session manager with various scenarios."""
    print("=" * 60)
    print("SESSION MANAGER TEST")
    print("=" * 60)
    
    mgr = SessionManager()
    
    # Test timestamps for each session
    test_times = [
        (1704096000, "2024-01-01 04:00:00 UTC", "ASIA"),      # 4 AM UTC
        (1704114000, "2024-01-01 09:00:00 UTC", "EUROPE"),    # 9 AM UTC
        (1704142800, "2024-01-01 17:00:00 UTC", "US"),        # 5 PM UTC
        (1704067200, "2024-01-01 00:00:00 UTC", "ASIA"),      # Midnight UTC
        (1704124800, "2024-01-01 12:00:00 UTC", "EUROPE"),    # Noon UTC
        (1704153600, "2024-01-01 20:00:00 UTC", "US"),        # 8 PM UTC
    ]
    
    print("\n" + "=" * 60)
    print("SESSION DETECTION TESTS")
    print("=" * 60)
    
    for timestamp, time_str, expected in test_times:
        session = mgr.get_current_session(timestamp)
        status = "✅" if session.value == expected else "❌"
        print(f"{status} {time_str} → {session.value} (expected: {expected})")
    
    # Test session parameters
    print("\n" + "=" * 60)
    print("SESSION PARAMETERS")
    print("=" * 60)
    
    for session in TradingSession:
        print(f"\n{session.value} Session:")
        print("-" * 60)
        params = mgr.get_session_parameters(session)
        print(f"  Time range: {params['time_range'][0]:02d}:00 - {params['time_range'][1]:02d}:00 UTC")
        print(f"  Normal signals: {params['signal_normal']}")
        print(f"  Circuit breaker: {params['signal_threshold']} (2× normal)")
        print(f"  Threshold mult: {params['threshold_multiplier']:.2f}")
        print(f"  Risk mult: {params['risk_multiplier']:.2f}")
        print(f"  Max positions: {params['max_positions']}")
    
    # Test circuit breaker logic
    print("\n" + "=" * 60)
    print("CIRCUIT BREAKER TESTS")
    print("=" * 60)
    
    test_scenarios = [
        (TradingSession.ASIA, 10, False),
        (TradingSession.ASIA, 30, True),
        (TradingSession.ASIA, 35, True),
        (TradingSession.EUROPE, 50, False),
        (TradingSession.EUROPE, 70, True),
        (TradingSession.US, 100, False),
        (TradingSession.US, 120, True),
    ]
    
    for session, count, should_trigger in test_scenarios:
        triggered = mgr.is_overtrading(session, count)
        status = "✅" if triggered == should_trigger else "❌"
        trigger_str = "TRIGGERED" if triggered else "OK"
        limit = mgr.get_circuit_breaker_limit(session)
        print(f"{status} {session.value}: {count} signals → {trigger_str} (limit: {limit})")
    
    # Comparison table
    print("\n" + "=" * 60)
    print("SESSION COMPARISON TABLE")
    print("=" * 60)
    print(f"{'Session':<10} {'Normal':<8} {'Limit':<8} {'Thresh':<8} {'Risk':<8} {'MaxPos':<8}")
    print("-" * 60)
    
    for session in TradingSession:
        params = mgr.get_session_parameters(session)
        print(
            f"{session.value:<10} "
            f"{params['signal_normal']:<8} "
            f"{params['signal_threshold']:<8} "
            f"{params['threshold_multiplier']:<8.2f} "
            f"{params['risk_multiplier']:<8.2f} "
            f"{params['max_positions']:<8}"
        )
    
    # Impact analysis
    print("\n" + "=" * 60)
    print("IMPACT ANALYSIS")
    print("=" * 60)
    
    print("\nThreshold Impact (assuming 25% base):")
    for session in TradingSession:
        mult = mgr.get_threshold_multiplier(session)
        base = 0.25
        adjusted = base * mult
        change = ((adjusted - base) / base) * 100
        
        change_str = f"{change:+.1f}%" if change != 0 else "baseline"
        print(f"  {session.value}: {base*100:.1f}% → {adjusted*100:.1f}% ({change_str})")
    
    print("\nPosition Size Impact (assuming 0.25% base):")
    for session in TradingSession:
        mult = mgr.get_risk_multiplier(session)
        base = 0.0025
        adjusted = base * mult
        change = ((adjusted - base) / base) * 100 if mult != 1.0 else 0
        
        change_str = f"{change:+.1f}%" if change != 0 else "baseline"
        print(f"  {session.value}: {base*100:.2f}% → {adjusted*100:.2f}% ({change_str})")
    
    print("\n" + "=" * 60)
    print("✅ TEST COMPLETE")
    print("=" * 60)


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    test_session_manager()
