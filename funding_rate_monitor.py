"""
Funding Rate Monitor

Tracks funding rates from Binance to identify overcrowded positions.
Generates fade signals when funding becomes extreme.

Strategy:
- High positive funding → Too many longs → SHORT signal
- High negative funding → Too many shorts → LONG signal
"""

import requests
import logging
import time
from typing import Dict, Optional, List
from collections import deque
import numpy as np

logger = logging.getLogger(__name__)


class FundingRateMonitor:
    """
    Monitor funding rates and detect overcrowded positions.
    
    Funding Rate Basics:
    - Positive: Longs pay shorts (bullish sentiment)
    - Negative: Shorts pay longs (bearish sentiment)
    - Extreme rates indicate overcrowding → mean reversion opportunity
    """
    
    def __init__(self, symbols: List[str]):
        """
        Initialize funding rate monitor.
        
        Args:
            symbols: List of symbols to monitor (e.g., ['BTCUSDT', 'ETHUSDT'])
        """
        self.symbols = symbols
        
        # Current funding rates
        self.current_rates = {s: 0.0 for s in symbols}
        
        # Historical rates (for percentile calculation)
        self.rate_history = {s: deque(maxlen=1000) for s in symbols}
        
        # Funding velocity (rate of change)
        self.prev_rates = {s: 0.0 for s in symbols}
        self.velocities = {s: 0.0 for s in symbols}
        
        # Last update time
        self.last_update = {s: 0 for s in symbols}
        
        # Binance API endpoint
        self.api_url = "https://fapi.binance.com/fapi/v1/premiumIndex"
    
    def update(self):
        """Fetch latest funding rates from Binance."""
        max_retries = 3
        retry_delay = 1  # seconds
        
        for attempt in range(max_retries):
            try:
                response = requests.get(self.api_url, timeout=10)  # Increased timeout
                response.raise_for_status()
                
                data = response.json()
                
                # Update rates for our symbols
                for item in data:
                    symbol = item['symbol']
                    if symbol in self.symbols:
                        # Get funding rate (as decimal, e.g., 0.0001 = 0.01%)
                        rate = float(item.get('lastFundingRate', 0))
                        
                        # Calculate velocity
                        prev_rate = self.prev_rates[symbol]
                        current_time = time.time()
                        time_delta = current_time - self.last_update.get(symbol, current_time)
                        
                        if time_delta > 0:
                            velocity = (rate - prev_rate) / time_delta
                            self.velocities[symbol] = velocity
                        
                        # Update current rate
                        self.prev_rates[symbol] = self.current_rates[symbol]
                        self.current_rates[symbol] = rate
                        self.last_update[symbol] = current_time
                        
                        # Add to history
                        self.rate_history[symbol].append(rate)
                
                logger.info(f"💰 Funding rates updated: BTC={self.current_rates.get('BTCUSDT', 0)*100:.4f}%, ETH={self.current_rates.get('ETHUSDT', 0)*100:.4f}%, SOL={self.current_rates.get('SOLUSDT', 0)*100:.4f}%")
                return  # Success, exit retry loop
                
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    logger.warning(f"Funding rate fetch timeout (attempt {attempt + 1}/{max_retries}), retrying...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Funding rate fetch failed after {max_retries} attempts (timeout)")
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Funding rate fetch error (attempt {attempt + 1}/{max_retries}): {e}, retrying...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Funding rate fetch failed after {max_retries} attempts: {e}")
            except Exception as e:
                logger.error(f"Unexpected error fetching funding rates: {e}")
                break  # Don't retry on unexpected errors
    
    def get_funding_signal(self, symbol: str) -> Optional[Dict]:
        """
        Generate funding rate arbitrage signal.
        
        Args:
            symbol: Trading pair
        
        Returns:
            Signal dict or None
        """
        if symbol not in self.current_rates:
            return None
        
        rate = self.current_rates[symbol]
        velocity = self.velocities.get(symbol, 0)
        
        # Convert to percentage for display
        rate_pct = rate * 100
        velocity_pct = velocity * 100
        
        # Calculate percentile (where is current rate vs history)
        percentile = self._get_percentile(symbol, rate)
        
        # Thresholds (ADJUSTED FOR REALISTIC MARKET CONDITIONS)
        # Current typical rates: BTC=0.0044%, ETH=0.0040%, SOL=0.0100%
        EXTREME_HIGH = 0.015   # 0.015% = 1.5 basis points (was 0.04%)
        HIGH = 0.01            # 0.01% = 1 basis point (was 0.025%)
        EXTREME_LOW = -0.015   # -0.015% (was -0.04%)
        LOW = -0.01            # -0.01% (was -0.025%)
        
        # Strategy 1: Extreme Funding (Highest Priority)
        if rate >= EXTREME_HIGH:
            logger.info(f"  ✅ EXTREME HIGH funding signal (SHORT)")
            return {
                'type': 'FUNDING_FADE',
                'direction': 'SHORT',
                'confidence': 0.85,
                'reason': f'Extreme funding ({rate_pct:.3f}%) - Overcrowded longs',
                'funding_rate': rate_pct,
                'funding_velocity': velocity_pct,
                'percentile': percentile,
                'details': f'Longs paying {rate_pct:.3f}% every 8h - unsustainable'
            }
        
        elif rate <= EXTREME_LOW:
            logger.info(f"  ✅ EXTREME LOW funding signal (LONG)")
            return {
                'type': 'FUNDING_FADE',
                'direction': 'LONG',
                'confidence': 0.85,
                'reason': f'Extreme funding ({rate_pct:.3f}%) - Overcrowded shorts',
                'funding_rate': rate_pct,
                'funding_velocity': velocity_pct,
                'percentile': percentile,
                'details': f'Shorts paying {abs(rate_pct):.3f}% every 8h - unsustainable'
            }
        
        # Strategy 2: High Funding + Accelerating
        elif rate >= HIGH and velocity > 0.0001:
            logger.info(f"  ✅ HIGH funding + accelerating signal (SHORT)")
            return {
                'type': 'FUNDING_FADE',
                'direction': 'SHORT',
                'confidence': 0.75,
                'reason': f'High funding ({rate_pct:.3f}%) accelerating - Longs piling in',
                'funding_rate': rate_pct,
                'funding_velocity': velocity_pct,
                'percentile': percentile,
                'details': f'Funding rising {velocity_pct:.4f}%/s - fade the crowd'
            }
        
        elif rate <= LOW and velocity < -0.0001:
            logger.info(f"  ✅ LOW funding + accelerating signal (LONG)")
            return {
                'type': 'FUNDING_FADE',
                'direction': 'LONG',
                'confidence': 0.75,
                'reason': f'Low funding ({rate_pct:.3f}%) accelerating - Shorts piling in',
                'funding_rate': rate_pct,
                'funding_velocity': velocity_pct,
                'percentile': percentile,
                'details': f'Funding falling {abs(velocity_pct):.4f}%/s - fade the crowd'
            }
        
        # Strategy 3: Historical Extremes (95th percentile)
        elif percentile > 95:
            return {
                'type': 'FUNDING_FADE',
                'direction': 'SHORT',
                'confidence': 0.70,
                'reason': f'Funding at {percentile:.0f}th percentile - Historical extreme',
                'funding_rate': rate_pct,
                'funding_velocity': velocity_pct,
                'percentile': percentile,
                'details': f'Funding higher than 95% of historical values'
            }
        
        elif percentile < 5:
            return {
                'type': 'FUNDING_FADE',
                'direction': 'LONG',
                'confidence': 0.70,
                'reason': f'Funding at {percentile:.0f}th percentile - Historical extreme',
                'funding_rate': rate_pct,
                'funding_velocity': velocity_pct,
                'percentile': percentile,
                'details': f'Funding lower than 95% of historical values'
            }
        
        return None
    
    def _get_percentile(self, symbol: str, rate: float) -> float:
        """Calculate percentile of current rate vs historical."""
        history = list(self.rate_history.get(symbol, []))
        
        if len(history) < 100:
            return 50  # Not enough data
        
        count_below = sum(1 for r in history if r < rate)
        percentile = (count_below / len(history)) * 100
        
        return percentile
    
    def get_stats(self, symbol: str) -> Dict:
        """Get funding rate statistics for a symbol."""
        if symbol not in self.current_rates:
            return {}
        
        rate = self.current_rates[symbol]
        velocity = self.velocities.get(symbol, 0)
        percentile = self._get_percentile(symbol, rate)
        
        # Convert to percentage
        rate_pct = rate * 100
        velocity_pct = velocity * 100
        
        return {
            'current_rate': rate_pct,
            'velocity': velocity_pct,
            'percentile': percentile,
            'direction': 'BULLISH' if rate > 0 else 'BEARISH' if rate < 0 else 'NEUTRAL',
            'extremity': 'EXTREME' if abs(rate) > 0.03 else 'HIGH' if abs(rate) > 0.02 else 'NORMAL'
        }


if __name__ == "__main__":
    """Test funding rate monitor."""
    
    logging.basicConfig(level=logging.INFO)
    
    monitor = FundingRateMonitor(['BTCUSDT', 'ETHUSDT', 'SOLUSDT'])
    
    print("="*60)
    print("FUNDING RATE MONITOR TEST")
    print("="*60)
    
    # Fetch rates
    monitor.update()
    
    print("\nCurrent Funding Rates:")
    for symbol in monitor.symbols:
        stats = monitor.get_stats(symbol)
        if stats:
            print(f"\n{symbol}:")
            print(f"  Rate: {stats['current_rate']:.4f}%")
            print(f"  Direction: {stats['direction']}")
            print(f"  Extremity: {stats['extremity']}")
            print(f"  Percentile: {stats['percentile']:.1f}")
            
            # Check for signal
            signal = monitor.get_funding_signal(symbol)
            if signal:
                print(f"\n  🎯 SIGNAL: {signal['direction']}")
                print(f"  Confidence: {signal['confidence']*100:.0f}%")
                print(f"  Reason: {signal['reason']}")
                print(f"  Details: {signal['details']}")
    
    print("\n" + "="*60)
