"""
Coinglass API Integration

Aggregates liquidation data across multiple exchanges:
- Binance, Bybit, OKX, Bitget, etc.
- Liquidation heatmaps
- Open interest tracking
- Funding rates

Free tier: 10 requests/minute
API Docs: https://open-api.coinglass.com/
"""

import requests
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import time
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CoinglassAPI:
    """Interface to Coinglass aggregated liquidation data."""
    
    BASE_URL = "https://open-api.coinglass.com/public/v2"
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Coinglass API client.
        
        Args:
            api_key: Optional API key for higher rate limits
        """
        self.api_key = api_key
        self.session = requests.Session()
        if api_key:
            self.session.headers.update({'coinglassSecret': api_key})
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 6  # 10 req/min = 6 sec between requests
    
    def _rate_limit(self):
        """Enforce rate limiting."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()
    
    def get_liquidation_history(self, symbol: str = 'BTC', time_type: str = '1') -> Dict:
        """
        Get liquidation history across all exchanges.
        
        Args:
            symbol: Coin symbol (BTC, ETH, SOL)
            time_type: Time range
                '1' = 24 hours
                '2' = 12 hours  
                '3' = 4 hours
                '4' = 1 hour
        
        Returns:
            Dict with liquidation data by exchange
        """
        self._rate_limit()
        
        try:
            url = f"{self.BASE_URL}/liquidation_history"
            params = {
                'symbol': symbol,
                'time_type': time_type
            }
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('success'):
                return data.get('data', {})
            else:
                logger.error(f"Coinglass API error: {data.get('msg')}")
                return {}
                
        except Exception as e:
            logger.error(f"Error fetching liquidation history: {e}")
            return {}
    
    def get_liquidation_heatmap(self, symbol: str = 'BTC', exchange: str = 'Binance') -> Dict:
        """
        Get liquidation heatmap data.
        
        Shows where liquidation clusters are located.
        
        Args:
            symbol: Coin symbol
            exchange: Exchange name (Binance, Bybit, OKX, etc.)
        
        Returns:
            Dict with heatmap data
        """
        self._rate_limit()
        
        try:
            url = f"{self.BASE_URL}/liquidation_heatmap"
            params = {
                'symbol': symbol,
                'ex': exchange
            }
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('success'):
                return data.get('data', {})
            else:
                logger.error(f"Coinglass API error: {data.get('msg')}")
                return {}
                
        except Exception as e:
            logger.error(f"Error fetching heatmap: {e}")
            return {}
    
    def get_aggregated_liquidations(self, time_range: str = '1h') -> Dict:
        """
        Get aggregated liquidations across all exchanges.
        
        Args:
            time_range: '1h', '4h', '12h', '24h'
        
        Returns:
            Dict with total longs/shorts liquidated
        """
        time_type_map = {
            '1h': '4',
            '4h': '3',
            '12h': '2',
            '24h': '1'
        }
        
        time_type = time_type_map.get(time_range, '1')
        
        # Get data for major coins
        symbols = ['BTC', 'ETH', 'SOL']
        results = {}
        
        for symbol in symbols:
            data = self.get_liquidation_history(symbol, time_type)
            if data:
                results[symbol] = self._parse_liquidation_data(data)
        
        return results
    
    def _parse_liquidation_data(self, data: Dict) -> Dict:
        """Parse liquidation data into usable format."""
        try:
            # Coinglass returns data by exchange
            total_longs = 0
            total_shorts = 0
            
            for exchange_data in data.values():
                if isinstance(exchange_data, dict):
                    total_longs += float(exchange_data.get('longLiquidationUsd', 0))
                    total_shorts += float(exchange_data.get('shortLiquidationUsd', 0))
            
            return {
                'long_liquidations_usd': total_longs,
                'short_liquidations_usd': total_shorts,
                'total_liquidations_usd': total_longs + total_shorts,
                'long_short_ratio': total_longs / total_shorts if total_shorts > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Error parsing liquidation data: {e}")
            return {
                'long_liquidations_usd': 0,
                'short_liquidations_usd': 0,
                'total_liquidations_usd': 0,
                'long_short_ratio': 0
            }
    
    def get_open_interest(self, symbol: str = 'BTC') -> Dict:
        """
        Get aggregated open interest across exchanges.
        
        Args:
            symbol: Coin symbol
        
        Returns:
            Dict with OI data
        """
        self._rate_limit()
        
        try:
            url = f"{self.BASE_URL}/open_interest"
            params = {'symbol': symbol}
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('success'):
                return data.get('data', {})
            else:
                logger.error(f"Coinglass API error: {data.get('msg')}")
                return {}
                
        except Exception as e:
            logger.error(f"Error fetching open interest: {e}")
            return {}
    
    def get_funding_rates(self, symbol: str = 'BTC') -> Dict:
        """
        Get funding rates across exchanges.
        
        Args:
            symbol: Coin symbol
        
        Returns:
            Dict with funding rates by exchange
        """
        self._rate_limit()
        
        try:
            url = f"{self.BASE_URL}/funding_rates"
            params = {'symbol': symbol}
            
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('success'):
                return data.get('data', {})
            else:
                logger.error(f"Coinglass API error: {data.get('msg')}")
                return {}
                
        except Exception as e:
            logger.error(f"Error fetching funding rates: {e}")
            return {}
    
    def get_liquidation_summary(self) -> Dict:
        """
        Get comprehensive liquidation summary for dashboard.
        
        Returns:
            Dict with liquidation data for BTC, ETH, SOL
        """
        summary = {}
        
        for symbol in ['BTC', 'ETH', 'SOL']:
            # Get 1h liquidations
            liq_data = self.get_liquidation_history(symbol, '4')
            parsed = self._parse_liquidation_data(liq_data)
            
            # Get heatmap for Binance
            heatmap = self.get_liquidation_heatmap(symbol, 'Binance')
            
            summary[symbol] = {
                'liquidations_1h': parsed,
                'heatmap': heatmap,
                'timestamp': datetime.now().isoformat()
            }
            
            logger.info(f"{symbol}: ${parsed['total_liquidations_usd']/1e6:.1f}M liquidated (1h)")
        
        return summary


class CoinglassMonitor:
    """Monitor Coinglass for multi-exchange liquidation data."""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize Coinglass monitor."""
        self.api = CoinglassAPI(api_key)
        self.running = False
    
    def start_monitoring(self, interval: int = 60):
        """
        Start periodic monitoring.
        
        Args:
            interval: Update interval in seconds (min 60 due to rate limits)
        """
        self.running = True
        
        logger.info("Coinglass monitor started")
        logger.info(f"Update interval: {interval}s")
        
        while self.running:
            try:
                summary = self.api.get_liquidation_summary()
                
                # Log summary
                for symbol, data in summary.items():
                    liq = data['liquidations_1h']
                    logger.info(
                        f"{symbol}: Longs ${liq['long_liquidations_usd']/1e6:.1f}M | "
                        f"Shorts ${liq['short_liquidations_usd']/1e6:.1f}M"
                    )
                
                time.sleep(interval)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                time.sleep(interval)
        
        logger.info("Coinglass monitor stopped")
    
    def stop(self):
        """Stop monitoring."""
        self.running = False


if __name__ == "__main__":
    # Test Coinglass API
    logger.info("=" * 60)
    logger.info("COINGLASS MULTI-EXCHANGE MONITOR")
    logger.info("=" * 60)
    logger.info("")
    
    # Load API key from environment
    api_key = os.getenv('COINGLASS_API_KEY')
    if not api_key:
        logger.warning("COINGLASS_API_KEY not found in .env file")
        logger.warning("Add it to .env: COINGLASS_API_KEY=your_key_here")
        exit(1)
    
    logger.info(f"API Key loaded: {api_key[:10]}...")
    api = CoinglassAPI(api_key)
    
    # Get liquidation summary
    logger.info("Fetching liquidation data...")
    summary = api.get_liquidation_summary()
    
    logger.info("")
    logger.info("=" * 60)
    logger.info("LIQUIDATION SUMMARY (Last 1 Hour)")
    logger.info("=" * 60)
    
    for symbol, data in summary.items():
        liq = data['liquidations_1h']
        logger.info(f"\n{symbol}:")
        logger.info(f"  Long Liquidations:  ${liq['long_liquidations_usd']/1e6:.2f}M")
        logger.info(f"  Short Liquidations: ${liq['short_liquidations_usd']/1e6:.2f}M")
        logger.info(f"  Total:              ${liq['total_liquidations_usd']/1e6:.2f}M")
        logger.info(f"  Long/Short Ratio:   {liq['long_short_ratio']:.2f}")

