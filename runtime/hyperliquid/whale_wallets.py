"""
Hyperliquid Whale Wallet Registry

Known high-activity wallets on Hyperliquid for position tracking.
Sources: On-chain analysis, community research, public dashboards.

To discover more wallets:
1. Monitor large liquidations and trace the liquidated addresses
2. Check hyperdash.info, hyperliquid.chrisling.dev for top traders
3. Use Nansen API for verified whale addresses
"""

from typing import List, Dict
from dataclasses import dataclass


@dataclass
class WalletInfo:
    """Information about a tracked wallet."""
    address: str
    label: str
    wallet_type: str  # WHALE, SYSTEM, FUND, TRADER
    notes: str = ""


# ==============================================================================
# System Wallets (Infrastructure)
# ==============================================================================

SYSTEM_WALLETS = [
    # HLP Vault moved to VAULT_WALLETS (0xdfc24b077bc1425ad1dea75bcb6f8158e10df303)
    WalletInfo(
        address="0xfefefefefefefefefefefefefefefefefefefefe",
        label="Assistance Fund",
        wallet_type="SYSTEM",
        notes="Protocol reserve fund"
    ),
    WalletInfo(
        address="0x6b9e773128f453f5c2c60935ee2de2cbc5390a24",
        label="USDC Deposit",
        wallet_type="SYSTEM",
        notes="HyperEVM USDC deposit wallet"
    ),
]

# ==============================================================================
# Known Whale Wallets (Community Research)
# ==============================================================================

# These addresses are from public on-chain analysis and community tracking
# Sources: hyperdash.info, dune analytics, twitter/x research threads

WHALE_WALLETS = [
    # =========================================================================
    # High-Profile Traders (Verified from public sources)
    # Sources: CoinGlass, CryptoSlate, BeInCrypto, CoinDesk
    # =========================================================================

    # James Wynn - Famous high-leverage trader ($1B+ positions)
    # Known for 40x BTC longs, significant PnL swings
    WalletInfo(
        address="0x5078c2fbea2b2ad61bc840bc023e35fce56bedb6",
        label="James Wynn",
        wallet_type="WHALE",
        notes="High-leverage trader, 40x positions, $100M+ PnL swings"
    ),

    # Insider Bro - Counter-trader, notable short positions
    WalletInfo(
        address="0x51d99a4022a55cad07a3c958f0600d8bb0b39921",
        label="Insider Bro",
        wallet_type="WHALE",
        notes="Counter-trader, high-leverage shorts"
    ),

    # =========================================================================
    # NOTE: "Hyperliquid Whale" (William Parker) addresses were partial
    # Full addresses needed - placeholder removed until verified
    # =========================================================================

    # =========================================================================
    # Active Traders (from Dwellir docs / on-chain analysis)
    # =========================================================================
    WalletInfo(
        address="0xe3b6e3443c8f2080704e7421bad9340f13950acb",
        label="Active-Trader-001",
        wallet_type="TRADER",
        notes="From on-chain trade records"
    ),
    WalletInfo(
        address="0x7839e2f2c375dd2935193f2736167514efff9916",
        label="Active-Trader-002",
        wallet_type="TRADER",
        notes="From on-chain trade records"
    ),
    WalletInfo(
        address="0xa68c548f3acd23a7fe3e867cc47f302559794419",
        label="Active-Trader-003",
        wallet_type="TRADER",
        notes="From on-chain trade records"
    ),
    # NOTE: 0xecb63caa47c7c4e77f60f1ce858cf28dc2b82b00 returns no data - may need verification

    # =========================================================================
    # Counter-traders (profitable betting against whales)
    # NOTE: Address 0x2258... made $17M vs James Wynn - full address needed
    # =========================================================================

    # =========================================================================
    # Verified Hyperdash Whales (Jan 2026)
    # Top traders by position size, verified via Hyperliquid API
    # Total tracked: $2.7B+ in positions
    # =========================================================================

    # #1 - Massive whale, $798M positions (BTC/ETH/SOL LONG)
    WalletInfo(
        address="0xb317d2bc2d3d2df5fa441b5bae0ab9d8b07283ae",
        label="Hyperdash-Top-01",
        wallet_type="WHALE",
        notes="Position: $798M, BTC/ETH/SOL LONG"
    ),
    # #2 - $277M positions (ETH/XRP/HYPE LONG)
    WalletInfo(
        address="0x9eec98d048d06d9cd75318fffa3f3960e081daab",
        label="Hyperdash-Top-02",
        wallet_type="WHALE",
        notes="Position: $277M, ETH/XRP/HYPE LONG"
    ),
    # #3 - $260M positions (ETH/SOL LONG)
    WalletInfo(
        address="0x94d3735543ecb3d339064151118644501c933814",
        label="Hyperdash-Top-03",
        wallet_type="WHALE",
        notes="Position: $260M, ETH/SOL LONG"
    ),
    # #4 - $174M positions (BTC/ETH/SOL SHORT)
    WalletInfo(
        address="0x7fdafde5cfb5465924316eced2d3715494c517d1",
        label="Hyperdash-Top-04",
        wallet_type="WHALE",
        notes="Position: $174M, BTC/ETH/SOL SHORT"
    ),
    # #5 - $134M positions (BTC/ETH/ATOM SHORT)
    WalletInfo(
        address="0x45d26f28196d226497130c4bac709d808fed4029",
        label="Hyperdash-Top-05",
        wallet_type="WHALE",
        notes="Position: $134M, BTC/ETH/ATOM SHORT, +$34M PnL"
    ),
    # #6 - $93M positions (Mixed long/short)
    WalletInfo(
        address="0x8af700ba841f30e0a3fcb0ee4c4a9d223e1efa05",
        label="Hyperdash-Top-06",
        wallet_type="WHALE",
        notes="Position: $93M, BTC LONG, ETH/SOL SHORT"
    ),
    # #7 - $79M positions (BTC/ETH/LTC SHORT)
    WalletInfo(
        address="0x8e096995c3e4a3f0bc5b3ea1cba94de2aa4d70c9",
        label="Hyperdash-Top-07",
        wallet_type="WHALE",
        notes="Position: $79M, BTC/ETH/LTC SHORT"
    ),
    # #8 - $77M positions (BTC/ETH/SOL SHORT)
    WalletInfo(
        address="0x35d1151ef1aab579cbb3109e69fa82f94ff5acb1",
        label="Hyperdash-Top-08",
        wallet_type="WHALE",
        notes="Position: $77M, BTC/ETH/SOL SHORT"
    ),
    # #9 - $75M positions (BTC SHORT)
    WalletInfo(
        address="0x1b526ff54f9f66c777fd34b7a802bb8d216ed41b",
        label="Hyperdash-Top-09",
        wallet_type="WHALE",
        notes="Position: $75M, BTC SHORT"
    ),
    # #10 - $57M positions (BTC/ETH/SOL SHORT)
    WalletInfo(
        address="0x99b1098d9d50aa076f78bd26ab22e6abd3710729",
        label="Hyperdash-Top-10",
        wallet_type="WHALE",
        notes="Position: $57M, BTC/ETH/SOL SHORT"
    ),
    # #11 - $56M positions (BTC/LIT SHORT)
    WalletInfo(
        address="0x5d2f4460ac3514ada79f5d9838916e508ab39bb7",
        label="Hyperdash-Top-11",
        wallet_type="WHALE",
        notes="Position: $56M, BTC/LIT SHORT, +$8M PnL"
    ),
    # #12 - $46M positions (Mixed)
    WalletInfo(
        address="0x939f95036d2e7b6d7419ec072bf9d967352204d2",
        label="Hyperdash-Top-12",
        wallet_type="WHALE",
        notes="Position: $46M, BTC LONG, ETH/SOL SHORT"
    ),
    # #13 - $45M positions (ETH/ENA/ZEC SHORT)
    WalletInfo(
        address="0x4196dc4a1dc7d3bfd5434adf04c829f4ccaf480d",
        label="Hyperdash-Top-13",
        wallet_type="WHALE",
        notes="Position: $45M, ETH/ENA/ZEC SHORT"
    ),
    # #14 - $44M positions (ETH LONG)
    WalletInfo(
        address="0xa5b0edf6b55128e0ddae8e51ac538c3188401d41",
        label="Hyperdash-Top-14",
        wallet_type="WHALE",
        notes="Position: $44M, ETH LONG, +$5.5M PnL"
    ),
    # #15 - $43M positions (ETH/HYPE/ZEC LONG)
    WalletInfo(
        address="0x020ca66c30bec2c4fe3861a94e4db4a498a35872",
        label="Hyperdash-Top-15",
        wallet_type="WHALE",
        notes="Position: $43M, ETH/HYPE/ZEC LONG"
    ),
    # #16 - $40M positions (BTC/ETH/DOGE LONG)
    WalletInfo(
        address="0xec0b9ebf2a304c99cafe85c548c14dd7783cb078",
        label="Hyperdash-Top-16",
        wallet_type="WHALE",
        notes="Position: $40M, BTC/ETH/DOGE LONG"
    ),
    # #17 - $39M positions (BTC/ETH/SOL LONG)
    WalletInfo(
        address="0xffbd3e51ae0e2c4407434e157965c064f2a11628",
        label="Hyperdash-Top-17",
        wallet_type="WHALE",
        notes="Position: $39M, BTC/ETH/SOL LONG"
    ),
    # #18 - $38M positions (BTC/ETH/SOL SHORT)
    WalletInfo(
        address="0x3fc56e944aa7b1594c85861b2d46a07f82a2c0c1",
        label="Hyperdash-Top-18",
        wallet_type="WHALE",
        notes="Position: $38M, BTC/ETH/SOL SHORT"
    ),
    # #19 - $36M positions (BTC SHORT)
    WalletInfo(
        address="0xc613bd93c62e62bf3e583c36ae8c4118f1fb2456",
        label="Hyperdash-Top-19",
        wallet_type="WHALE",
        notes="Position: $36M, BTC SHORT"
    ),
    # #20 - $33M positions (BTC/SUI LONG)
    WalletInfo(
        address="0x4efdb6c6813c648ed775ce7f3ff6e08bca83fc7a",
        label="Hyperdash-Top-20",
        wallet_type="WHALE",
        notes="Position: $33M, BTC/SUI LONG"
    ),
]

# ==============================================================================
# Vault Addresses
# ==============================================================================

VAULT_WALLETS = [
    # =========================================================================
    # Protocol Vaults (HLP - Hyperliquidity Provider)
    # These are the main liquidity/liquidation vaults
    # =========================================================================
    WalletInfo(
        address="0xdfc24b077bc1425ad1dea75bcb6f8158e10df303",
        label="HLP Main",
        wallet_type="FUND",
        notes="Main HLP vault, ~$270M TVL, handles liquidations"
    ),
    WalletInfo(
        address="0x1e37a337ed460039d1b15bd3bc489de789768d5e",
        label="Growi HF",
        wallet_type="FUND",
        notes="HLP vault, ~$8M TVL, high APR"
    ),
]


def get_all_tracked_wallets() -> List[WalletInfo]:
    """Get all wallets that should be tracked."""
    return SYSTEM_WALLETS + WHALE_WALLETS + VAULT_WALLETS


def get_system_wallets() -> List[WalletInfo]:
    """Get system infrastructure wallets only."""
    return SYSTEM_WALLETS


def get_whale_wallets() -> List[WalletInfo]:
    """Get whale trader wallets only."""
    return WHALE_WALLETS


def get_wallet_addresses() -> List[str]:
    """Get just the addresses for all tracked wallets."""
    return [w.address for w in get_all_tracked_wallets()]


# ==============================================================================
# Wallet Discovery (from on-chain activity)
# ==============================================================================

async def discover_whales_from_liquidations(
    client,  # HyperliquidClient
    min_position_value: float = 100_000.0,
    limit: int = 50
) -> List[str]:
    """
    Discover whale addresses by analyzing large liquidation events.

    Strategy: Large liquidations = large positions = whale activity.
    Track these addresses for future monitoring.

    Args:
        client: HyperliquidClient instance
        min_position_value: Minimum position value to consider whale
        limit: Maximum addresses to return

    Returns:
        List of discovered wallet addresses
    """
    # This would require historical liquidation data
    # For now, return empty - implement when we have liquidation history
    return []


async def fetch_top_traders_from_api(limit: int = 20) -> List[WalletInfo]:
    """
    Fetch top traders from third-party APIs.

    Sources (in priority order):
    1. CoinGlass API (best for whale tracking)
    2. Hyperliquid clearinghouse state (for position verification)

    Args:
        limit: Number of top traders to fetch

    Returns:
        List of WalletInfo for top traders
    """
    import aiohttp

    wallets = []

    # CoinGlass has Hyperliquid whale tracking at coinglass.com/hl
    # Their API may require authentication - check for public endpoints
    try:
        async with aiohttp.ClientSession() as session:
            # CoinGlass public API endpoint (if available)
            async with session.get(
                'https://open-api.coinglass.com/public/v2/hyperliquid/whale',
                headers={'accept': 'application/json'},
                params={'limit': limit}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    for trader in data.get('data', []):
                        wallets.append(WalletInfo(
                            address=trader.get('address', ''),
                            label=f"CG-Whale-{len(wallets)+1}",
                            wallet_type="WHALE",
                            notes=f"PnL: ${trader.get('pnl', 0):,.0f}"
                        ))
    except Exception:
        pass

    return wallets


async def fetch_large_position_holders(
    client,  # HyperliquidClient
    known_wallets: List[str],
    min_position_usd: float = 1_000_000.0
) -> List[WalletInfo]:
    """
    Verify and filter wallet list based on current position sizes.

    This queries each known wallet to verify they still hold
    significant positions (filters out inactive wallets).

    Args:
        client: HyperliquidClient instance
        known_wallets: List of wallet addresses to check
        min_position_usd: Minimum total position value to include

    Returns:
        List of WalletInfo for active large position holders
    """
    active_whales = []

    for address in known_wallets:
        try:
            state = await client.get_clearinghouse_state(address)
            if state and 'assetPositions' in state:
                total_value = 0.0
                for pos in state['assetPositions']:
                    pos_info = pos.get('position', {})
                    size = float(pos_info.get('szi', 0))
                    entry = float(pos_info.get('entryPx', 0))
                    total_value += abs(size * entry)

                if total_value >= min_position_usd:
                    active_whales.append(WalletInfo(
                        address=address,
                        label=f"Active-Whale-{address[:8]}",
                        wallet_type="WHALE",
                        notes=f"Position value: ${total_value:,.0f}"
                    ))
        except Exception:
            continue

    return active_whales


# ==============================================================================
# Manual Address Addition
# ==============================================================================

# Instructions to add whale addresses manually:
#
# 1. Go to https://hyperdash.info/top-traders
# 2. Click on a trader to see their address
# 3. Add to WHALE_WALLETS list above
#
# Or use the CLI:
# python -c "from runtime.hyperliquid.whale_wallets import add_whale; add_whale('0x...')"

def add_whale_to_file(address: str, label: str = None, notes: str = ""):
    """
    Helper to print the code to add a whale address.
    (Actually modifying the file requires manual edit)
    """
    label = label or f"Whale-{address[:8]}"
    print(f"""
Add this to WHALE_WALLETS in whale_wallets.py:

    WalletInfo(
        address="{address.lower()}",
        label="{label}",
        wallet_type="WHALE",
        notes="{notes}"
    ),
""")
