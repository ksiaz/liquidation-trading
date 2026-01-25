"""
Asset Metadata Service.

Fetches and caches asset metadata from Hyperliquid exchange.
Provides:
- Asset indices for order submission
- Size decimals for quantity formatting
- Max leverage per asset
- Thread-safe caching with TTL refresh

P1: Dynamic asset index mapping (replaces hardcoded asset_map).
"""

import time
import logging
import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional
from threading import Lock
import aiohttp


@dataclass
class AssetInfo:
    """Metadata for a single asset."""
    name: str
    index: int
    sz_decimals: int
    max_leverage: int
    only_isolated: bool

    @property
    def step_size(self) -> float:
        """Calculate step size from sz_decimals."""
        return 10 ** (-self.sz_decimals)


class AssetMetadataService:
    """
    Centralized asset metadata service.

    Features:
    - Fetches metadata from Hyperliquid on first use
    - Thread-safe caching
    - TTL-based refresh (default: 1 hour)
    - Fallback to cached data on refresh failure

    Usage:
        service = get_asset_metadata_service()
        await service.ensure_loaded()
        idx = service.get_asset_index("BTC")
        size_str = service.format_size("BTC", 0.0123456)
    """

    MAINNET_API_URL = "https://api.hyperliquid.xyz"
    TESTNET_API_URL = "https://api.hyperliquid-testnet.xyz"

    def __init__(
        self,
        use_testnet: bool = False,
        cache_ttl_seconds: float = 3600,  # 1 hour
        logger: Optional[logging.Logger] = None
    ):
        self._api_url = self.TESTNET_API_URL if use_testnet else self.MAINNET_API_URL
        self._cache_ttl = cache_ttl_seconds
        self._logger = logger or logging.getLogger(__name__)

        # Asset data
        self._assets: Dict[str, AssetInfo] = {}
        self._assets_by_index: Dict[int, AssetInfo] = {}

        # Cache management
        self._last_fetch_time: float = 0
        self._lock = Lock()
        self._loaded = False

        # Fallback mapping for common assets (used before first fetch)
        self._fallback_map = {
            "BTC": 0, "ETH": 1, "SOL": 2, "DOGE": 3, "XRP": 4,
            "AVAX": 5, "LINK": 6, "ARB": 7, "OP": 8, "SUI": 9,
            "ATOM": 10, "APT": 11, "INJ": 12, "SEI": 13, "TIA": 14,
            "WIF": 15, "PEPE": 16, "BONK": 17, "RNDR": 18, "FTM": 19,
            "NEAR": 20, "LTC": 21, "BCH": 22, "ORDI": 23, "STX": 24,
            "HYPE": 130,
        }

    async def ensure_loaded(self) -> bool:
        """
        Ensure metadata is loaded, fetching if needed.

        Returns:
            True if metadata is available
        """
        if self._is_cache_fresh():
            return True

        return await self.refresh()

    async def refresh(self) -> bool:
        """
        Refresh metadata from exchange.

        Returns:
            True if refresh succeeded
        """
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            ) as session:
                async with session.post(
                    f"{self._api_url}/info",
                    json={"type": "meta"},
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status != 200:
                        self._logger.warning(
                            f"Failed to fetch metadata: HTTP {response.status}"
                        )
                        return self._loaded  # Return True if we have cached data

                    data = await response.json()

            # Parse universe
            universe = data.get("universe", [])
            if not universe:
                self._logger.warning("Empty universe in metadata response")
                return self._loaded

            with self._lock:
                self._assets.clear()
                self._assets_by_index.clear()

                for idx, asset in enumerate(universe):
                    name = asset.get("name", "")
                    if not name:
                        continue

                    info = AssetInfo(
                        name=name,
                        index=idx,
                        sz_decimals=int(asset.get("szDecimals", 0)),
                        max_leverage=int(asset.get("maxLeverage", 50)),
                        only_isolated=bool(asset.get("onlyIsolated", False))
                    )

                    self._assets[name] = info
                    self._assets_by_index[idx] = info

                self._last_fetch_time = time.time()
                self._loaded = True

            self._logger.info(
                f"AssetMetadataService: Loaded {len(self._assets)} assets"
            )
            return True

        except Exception as e:
            self._logger.error(f"Failed to refresh metadata: {e}")
            return self._loaded  # Return True if we have cached data

    def _is_cache_fresh(self) -> bool:
        """Check if cache is still valid."""
        return (
            self._loaded and
            (time.time() - self._last_fetch_time) < self._cache_ttl
        )

    def get_asset_index(self, symbol: str) -> int:
        """
        Get asset index for symbol.

        Falls back to static mapping if metadata not loaded.
        """
        with self._lock:
            if symbol in self._assets:
                return self._assets[symbol].index

        # Fallback
        return self._fallback_map.get(symbol, 0)

    def get_asset_info(self, symbol: str) -> Optional[AssetInfo]:
        """Get full asset info."""
        with self._lock:
            return self._assets.get(symbol)

    def get_sz_decimals(self, symbol: str) -> int:
        """Get size decimals for symbol."""
        with self._lock:
            if symbol in self._assets:
                return self._assets[symbol].sz_decimals
        # Fallback based on typical values
        if symbol in ("BTC",):
            return 5
        elif symbol in ("ETH",):
            return 4
        elif symbol in ("SOL", "AVAX", "LINK"):
            return 2
        else:
            return 0

    def format_size(self, symbol: str, size: float) -> str:
        """
        Format size using exchange precision.

        Uses sz_decimals from exchange metadata.
        """
        decimals = self.get_sz_decimals(symbol)
        step = 10 ** (-decimals)
        rounded = round(size / step) * step
        return f"{rounded:.{decimals}f}"

    def format_price(self, symbol: str, price: float) -> str:
        """
        Format price for exchange.

        Hyperliquid uses 5 significant figures for prices.
        """
        if price == 0:
            return "0"

        # 5 significant figures
        if price >= 10000:
            return f"{price:.0f}"
        elif price >= 1000:
            return f"{price:.1f}"
        elif price >= 100:
            return f"{price:.2f}"
        elif price >= 10:
            return f"{price:.3f}"
        elif price >= 1:
            return f"{price:.4f}"
        elif price >= 0.1:
            return f"{price:.5f}"
        else:
            return f"{price:.6f}"

    def get_all_symbols(self) -> List[str]:
        """Get list of all available symbols."""
        with self._lock:
            return list(self._assets.keys())

    def is_loaded(self) -> bool:
        """Check if metadata is loaded."""
        return self._loaded


# ==============================================================================
# Singleton Instance
# ==============================================================================

_service_instance: Optional[AssetMetadataService] = None
_service_lock = Lock()


def get_asset_metadata_service(
    use_testnet: bool = False
) -> AssetMetadataService:
    """Get or create the singleton asset metadata service."""
    global _service_instance
    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                _service_instance = AssetMetadataService(use_testnet=use_testnet)
    return _service_instance


def reset_asset_metadata_service():
    """Reset the singleton (for testing)."""
    global _service_instance
    with _service_lock:
        _service_instance = None
