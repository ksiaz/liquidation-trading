"""
Node Client - Direct access to Hyperliquid node data

Connects to the node proxy running on the VM for unlimited data access.
No rate limits, sub-second latency.
"""

import requests
import time
from typing import Dict, List, Optional
from dataclasses import dataclass

# Node proxy endpoint
NODE_PROXY_URL = "http://64.176.65.252:8080"

# Asset ID to coin name mapping (Hyperliquid perps)
ASSET_ID_TO_COIN = {
    0: "BTC", 1: "ETH", 2: "ATOM", 3: "MATIC", 4: "DYDX", 5: "SOL",
    6: "AVAX", 7: "BNB", 8: "APE", 9: "OP", 10: "LTC", 11: "ARB",
    12: "DOGE", 13: "INJ", 14: "SUI", 15: "kPEPE", 16: "XRP", 17: "LINK",
    18: "CRV", 19: "RNDR", 20: "FTM", 21: "ADA", 22: "FIL", 23: "LDO",
    24: "GMX", 25: "NEAR", 26: "TIA", 27: "AAVE", 28: "SEI", 29: "RUNE",
    30: "DOT", 31: "BLUR", 32: "WLD", 33: "ORDI", 34: "MEME", 35: "PYTH",
    36: "JTO", 37: "STRK", 38: "PENDLE", 39: "W", 40: "ENA", 41: "TON",
    42: "BOME", 43: "WIF", 44: "NOT", 45: "POPCAT", 46: "HYPE",
    # Add more as needed
}

# Reverse mapping
COIN_TO_ASSET_ID = {v: k for k, v in ASSET_ID_TO_COIN.items()}


@dataclass
class NodeStatus:
    height: int
    consensus_time: str
    wall_clock_time: str
    lag_seconds: float
    synced: bool


class NodeClient:
    """Client for the Hyperliquid node proxy."""

    def __init__(self, base_url: str = NODE_PROXY_URL, timeout: float = 5.0):
        self.base_url = base_url
        self.timeout = timeout
        self._last_mids: Dict[str, float] = {}
        self._last_mids_time = 0
        self._cache_ttl = 0.1  # 100ms cache

    def get_mids(self, use_cache: bool = True) -> Dict[str, float]:
        """Get all mid prices from node.

        Returns dict of coin -> price (e.g., {'BTC': 93500.0, 'ETH': 3200.0})
        """
        now = time.time()
        if use_cache and (now - self._last_mids_time) < self._cache_ttl:
            return self._last_mids

        try:
            resp = requests.get(
                f"{self.base_url}/mids",
                timeout=self.timeout
            )
            if resp.status_code == 200:
                raw_mids = resp.json()
                # Convert asset IDs to coin names
                mids = {}
                for asset_id_str, price in raw_mids.items():
                    asset_id = int(asset_id_str)
                    coin = ASSET_ID_TO_COIN.get(asset_id, f"ASSET_{asset_id}")
                    mids[coin] = float(price)

                self._last_mids = mids
                self._last_mids_time = now
                return mids
        except Exception as e:
            print(f"[NodeClient] Error getting mids: {e}")

        return self._last_mids

    def get_trades(self, limit: int = 100) -> List[Dict]:
        """Get recent trades from node."""
        try:
            resp = requests.get(
                f"{self.base_url}/trades",
                timeout=self.timeout
            )
            if resp.status_code == 200:
                trades = resp.json()
                # Convert asset IDs to coin names
                for trade in trades:
                    asset_id = trade.get('asset')
                    if asset_id is not None:
                        trade['coin'] = ASSET_ID_TO_COIN.get(asset_id, f"ASSET_{asset_id}")
                return trades[-limit:]
        except Exception as e:
            print(f"[NodeClient] Error getting trades: {e}")

        return []

    def get_health(self) -> Optional[NodeStatus]:
        """Get node health/sync status."""
        try:
            resp = requests.get(
                f"{self.base_url}/health",
                timeout=self.timeout
            )
            if resp.status_code == 200:
                data = resp.json()
                # Calculate lag
                lag = 0.0
                if data.get('consensus_time') and data.get('wall_clock_time'):
                    try:
                        from datetime import datetime
                        ct = datetime.fromisoformat(data['consensus_time'][:26])
                        wt = datetime.fromisoformat(data['wall_clock_time'][:26])
                        lag = (wt - ct).total_seconds()
                    except:
                        pass

                return NodeStatus(
                    height=data.get('height', 0),
                    consensus_time=data.get('consensus_time', ''),
                    wall_clock_time=data.get('wall_clock_time', ''),
                    lag_seconds=lag,
                    synced=lag < 5.0
                )
        except Exception as e:
            print(f"[NodeClient] Error getting health: {e}")

        return None

    def is_available(self) -> bool:
        """Check if node proxy is available."""
        try:
            resp = requests.get(
                f"{self.base_url}/health",
                timeout=1.0
            )
            return resp.status_code == 200
        except:
            return False

    def get_active_wallets(self) -> List[str]:
        """Get list of wallets with open perp positions from node state.

        Returns list of wallet addresses (e.g., ['0x123...', '0x456...'])
        """
        try:
            resp = requests.get(
                f"{self.base_url}/active_wallets",
                timeout=30.0  # Longer timeout for large data
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get('wallets', [])
        except Exception as e:
            print(f"[NodeClient] Error getting active wallets: {e}")
        return []

    def get_position_sizes(self) -> Dict[str, Dict[str, Dict]]:
        """Get all position sizes from node state.

        Returns dict of wallet -> coin -> {side, size, asset_id}
        e.g., {'0x123...': {'BTC': {'side': 'LONG', 'size': 1.5, 'asset_id': 0}}}
        """
        try:
            resp = requests.get(
                f"{self.base_url}/position_sizes",
                timeout=60.0  # Long timeout for large data transfer
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            print(f"[NodeClient] Error getting position sizes: {e}")
        return {}

    def get_wallet_positions(self, wallet: str) -> Dict[str, Dict]:
        """Get position sizes for a specific wallet.

        Returns dict of coin -> {side, size, asset_id}
        e.g., {'BTC': {'side': 'LONG', 'size': 1.5, 'asset_id': 0}}
        """
        try:
            resp = requests.get(
                f"{self.base_url}/positions/{wallet}",
                timeout=15.0  # Longer timeout if cache needs refresh
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get('positions', {})
        except Exception as e:
            print(f"[NodeClient] Error getting wallet positions: {e}")
        return {}

    def has_position(self, wallet: str, coin: str = None) -> bool:
        """Check if a wallet has an open position (optionally for specific coin)."""
        positions = self.get_wallet_positions(wallet)
        if coin:
            return coin in positions
        return len(positions) > 0


# Singleton instance
_node_client: Optional[NodeClient] = None


def get_node_client() -> NodeClient:
    """Get or create the node client singleton."""
    global _node_client
    if _node_client is None:
        _node_client = NodeClient()
    return _node_client


def get_node_mids() -> Dict[str, float]:
    """Convenience function to get mid prices from node."""
    return get_node_client().get_mids()


def get_node_trades(limit: int = 100) -> List[Dict]:
    """Convenience function to get recent trades from node."""
    return get_node_client().get_trades(limit)


def get_node_health() -> Optional[NodeStatus]:
    """Convenience function to get node health."""
    return get_node_client().get_health()


def get_active_wallets() -> List[str]:
    """Convenience function to get wallets with positions."""
    return get_node_client().get_active_wallets()


def get_position_sizes() -> Dict[str, Dict[str, Dict]]:
    """Convenience function to get all position sizes."""
    return get_node_client().get_position_sizes()


def get_wallet_positions(wallet: str) -> Dict[str, Dict]:
    """Convenience function to get positions for a wallet."""
    return get_node_client().get_wallet_positions(wallet)


def has_position(wallet: str, coin: str = None) -> bool:
    """Convenience function to check if wallet has position."""
    return get_node_client().has_position(wallet, coin)


if __name__ == "__main__":
    # Test the client
    client = NodeClient()

    print("Testing node client...")

    # Health check
    health = client.get_health()
    if health:
        print(f"Node height: {health.height:,}")
        print(f"Lag: {health.lag_seconds:.2f}s")
        print(f"Synced: {health.synced}")
    else:
        print("Node not available")

    # Get prices
    mids = client.get_mids()
    print(f"\nGot {len(mids)} prices")
    for coin in ['BTC', 'ETH', 'SOL', 'DOGE']:
        if coin in mids:
            print(f"  {coin}: ${mids[coin]:,.2f}")

    # Get trades
    trades = client.get_trades(limit=5)
    print(f"\nLast {len(trades)} trades:")
    for trade in trades[:5]:
        print(f"  {trade.get('coin', '?')} {trade.get('side')} {trade.get('size')} @ {trade.get('price')}")

    # Get active wallets
    wallets = client.get_active_wallets()
    print(f"\nActive wallets with positions: {len(wallets)}")
    print(f"  Sample: {wallets[:3]}")

    # Get position for first wallet
    if wallets:
        positions = client.get_wallet_positions(wallets[0])
        print(f"\nPositions for {wallets[0][:16]}...:")
        for coin, pos in positions.items():
            print(f"  {coin}: {pos['side']} {pos['size']:.4f}")
