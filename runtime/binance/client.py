"""
Binance API Client.

Fetches funding rates and spot prices from Binance public API.
No authentication required for public endpoints.

Endpoints used:
- GET /fapi/v1/premiumIndex - Funding rate info
- GET /fapi/v1/fundingRate - Historical funding rates
- GET /api/v3/ticker/price - Spot prices
"""

import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


@dataclass
class FundingInfo:
    """Current funding rate information."""
    symbol: str
    mark_price: float
    index_price: float
    funding_rate: float
    next_funding_time: int  # milliseconds
    timestamp: int  # nanoseconds


@dataclass
class SpotPrice:
    """Spot price snapshot."""
    symbol: str
    price: float
    timestamp: int  # nanoseconds


class BinanceClient:
    """Client for Binance public API endpoints.

    Provides synchronous and asynchronous methods for fetching
    funding rates and spot prices.
    """

    # API endpoints
    FUTURES_BASE = "https://fapi.binance.com"
    SPOT_BASE = "https://api.binance.com"

    # Rate limiting
    DEFAULT_RATE_LIMIT_DELAY = 0.1  # 100ms between requests

    # Symbol mapping (HL symbol -> Binance symbol)
    SYMBOL_MAP = {
        'BTC': 'BTCUSDT',
        'ETH': 'ETHUSDT',
        'SOL': 'SOLUSDT',
        'DOGE': 'DOGEUSDT',
        'XRP': 'XRPUSDT',
        'AVAX': 'AVAXUSDT',
        'LINK': 'LINKUSDT',
        'ARB': 'ARBUSDT',
        'OP': 'OPUSDT',
        'SUI': 'SUIUSDT',
    }

    def __init__(
        self,
        rate_limit_delay: float = DEFAULT_RATE_LIMIT_DELAY,
        logger: logging.Logger = None
    ):
        """Initialize Binance client.

        Args:
            rate_limit_delay: Delay between requests in seconds
            logger: Optional logger instance
        """
        self._rate_limit_delay = rate_limit_delay
        self._logger = logger or logging.getLogger(__name__)
        self._last_request_time = 0

    def _now_ns(self) -> int:
        """Current time in nanoseconds."""
        return int(time.time() * 1_000_000_000)

    def _to_binance_symbol(self, hl_symbol: str) -> str:
        """Convert Hyperliquid symbol to Binance symbol.

        Args:
            hl_symbol: Hyperliquid symbol (e.g., 'BTC')

        Returns:
            Binance symbol (e.g., 'BTCUSDT')
        """
        return self.SYMBOL_MAP.get(hl_symbol.upper(), f"{hl_symbol.upper()}USDT")

    def _rate_limit(self):
        """Apply rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit_delay:
            time.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    # Synchronous methods (using requests)

    def get_funding_rate(self, symbol: str) -> Optional[FundingInfo]:
        """Get current funding rate for a symbol.

        Args:
            symbol: Hyperliquid symbol (e.g., 'BTC')

        Returns:
            FundingInfo or None if failed
        """
        if not REQUESTS_AVAILABLE:
            self._logger.error("requests library not available")
            return None

        binance_symbol = self._to_binance_symbol(symbol)
        url = f"{self.FUTURES_BASE}/fapi/v1/premiumIndex"

        try:
            self._rate_limit()
            response = requests.get(url, params={'symbol': binance_symbol}, timeout=10)
            response.raise_for_status()
            data = response.json()

            return FundingInfo(
                symbol=symbol,
                mark_price=float(data['markPrice']),
                index_price=float(data['indexPrice']),
                funding_rate=float(data['lastFundingRate']),
                next_funding_time=int(data['nextFundingTime']),
                timestamp=self._now_ns()
            )

        except Exception as e:
            self._logger.error(f"Failed to get funding rate for {symbol}: {e}")
            return None

    def get_funding_rates_batch(
        self,
        symbols: List[str]
    ) -> Dict[str, Optional[FundingInfo]]:
        """Get funding rates for multiple symbols.

        Args:
            symbols: List of Hyperliquid symbols

        Returns:
            Dict mapping symbol to FundingInfo (or None if failed)
        """
        if not REQUESTS_AVAILABLE:
            self._logger.error("requests library not available")
            return {s: None for s in symbols}

        # Binance allows fetching all premium indexes at once
        url = f"{self.FUTURES_BASE}/fapi/v1/premiumIndex"

        try:
            self._rate_limit()
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Build lookup by Binance symbol
            lookup = {item['symbol']: item for item in data}

            results = {}
            ts = self._now_ns()

            for symbol in symbols:
                binance_symbol = self._to_binance_symbol(symbol)
                item = lookup.get(binance_symbol)

                if item:
                    results[symbol] = FundingInfo(
                        symbol=symbol,
                        mark_price=float(item['markPrice']),
                        index_price=float(item['indexPrice']),
                        funding_rate=float(item['lastFundingRate']),
                        next_funding_time=int(item['nextFundingTime']),
                        timestamp=ts
                    )
                else:
                    results[symbol] = None

            return results

        except Exception as e:
            self._logger.error(f"Failed to get batch funding rates: {e}")
            return {s: None for s in symbols}

    def get_spot_price(self, symbol: str) -> Optional[SpotPrice]:
        """Get current spot price for a symbol.

        Args:
            symbol: Hyperliquid symbol (e.g., 'BTC')

        Returns:
            SpotPrice or None if failed
        """
        if not REQUESTS_AVAILABLE:
            self._logger.error("requests library not available")
            return None

        binance_symbol = self._to_binance_symbol(symbol)
        url = f"{self.SPOT_BASE}/api/v3/ticker/price"

        try:
            self._rate_limit()
            response = requests.get(url, params={'symbol': binance_symbol}, timeout=10)
            response.raise_for_status()
            data = response.json()

            return SpotPrice(
                symbol=symbol,
                price=float(data['price']),
                timestamp=self._now_ns()
            )

        except Exception as e:
            self._logger.error(f"Failed to get spot price for {symbol}: {e}")
            return None

    def get_spot_prices_batch(
        self,
        symbols: List[str]
    ) -> Dict[str, Optional[SpotPrice]]:
        """Get spot prices for multiple symbols.

        Args:
            symbols: List of Hyperliquid symbols

        Returns:
            Dict mapping symbol to SpotPrice (or None if failed)
        """
        if not REQUESTS_AVAILABLE:
            self._logger.error("requests library not available")
            return {s: None for s in symbols}

        url = f"{self.SPOT_BASE}/api/v3/ticker/price"

        try:
            self._rate_limit()
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Build lookup by Binance symbol
            lookup = {item['symbol']: item for item in data}

            results = {}
            ts = self._now_ns()

            for symbol in symbols:
                binance_symbol = self._to_binance_symbol(symbol)
                item = lookup.get(binance_symbol)

                if item:
                    results[symbol] = SpotPrice(
                        symbol=symbol,
                        price=float(item['price']),
                        timestamp=ts
                    )
                else:
                    results[symbol] = None

            return results

        except Exception as e:
            self._logger.error(f"Failed to get batch spot prices: {e}")
            return {s: None for s in symbols}

    def get_historical_funding_rates(
        self,
        symbol: str,
        start_time: int = None,
        end_time: int = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get historical funding rates.

        Args:
            symbol: Hyperliquid symbol (e.g., 'BTC')
            start_time: Start timestamp in milliseconds
            end_time: End timestamp in milliseconds
            limit: Maximum number of records (max 1000)

        Returns:
            List of historical funding rate records
        """
        if not REQUESTS_AVAILABLE:
            self._logger.error("requests library not available")
            return []

        binance_symbol = self._to_binance_symbol(symbol)
        url = f"{self.FUTURES_BASE}/fapi/v1/fundingRate"

        params = {
            'symbol': binance_symbol,
            'limit': min(limit, 1000)
        }

        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time

        try:
            self._rate_limit()
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Convert to standard format
            results = []
            for item in data:
                results.append({
                    'symbol': symbol,
                    'funding_rate': float(item['fundingRate']),
                    'funding_time': int(item['fundingTime']),
                    'mark_price': float(item.get('markPrice', 0))
                })

            return results

        except Exception as e:
            self._logger.error(f"Failed to get historical funding for {symbol}: {e}")
            return []

    # Async methods (using aiohttp)

    async def get_funding_rate_async(self, symbol: str) -> Optional[FundingInfo]:
        """Get current funding rate asynchronously.

        Args:
            symbol: Hyperliquid symbol (e.g., 'BTC')

        Returns:
            FundingInfo or None if failed
        """
        if not AIOHTTP_AVAILABLE:
            self._logger.error("aiohttp library not available")
            return None

        binance_symbol = self._to_binance_symbol(symbol)
        url = f"{self.FUTURES_BASE}/fapi/v1/premiumIndex"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params={'symbol': binance_symbol},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    response.raise_for_status()
                    data = await response.json()

                    return FundingInfo(
                        symbol=symbol,
                        mark_price=float(data['markPrice']),
                        index_price=float(data['indexPrice']),
                        funding_rate=float(data['lastFundingRate']),
                        next_funding_time=int(data['nextFundingTime']),
                        timestamp=self._now_ns()
                    )

        except Exception as e:
            self._logger.error(f"Failed to get async funding rate for {symbol}: {e}")
            return None

    async def get_spot_price_async(self, symbol: str) -> Optional[SpotPrice]:
        """Get current spot price asynchronously.

        Args:
            symbol: Hyperliquid symbol (e.g., 'BTC')

        Returns:
            SpotPrice or None if failed
        """
        if not AIOHTTP_AVAILABLE:
            self._logger.error("aiohttp library not available")
            return None

        binance_symbol = self._to_binance_symbol(symbol)
        url = f"{self.SPOT_BASE}/api/v3/ticker/price"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params={'symbol': binance_symbol},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    response.raise_for_status()
                    data = await response.json()

                    return SpotPrice(
                        symbol=symbol,
                        price=float(data['price']),
                        timestamp=self._now_ns()
                    )

        except Exception as e:
            self._logger.error(f"Failed to get async spot price for {symbol}: {e}")
            return None
