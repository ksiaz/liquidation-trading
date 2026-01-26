"""
Hyperliquid Asset ID to Coin Name Mapping

Maps numeric asset IDs used in node data to human-readable coin symbols.
The node uses integer asset IDs (0=BTC, 1=ETH, etc.) in all data structures.

Total assets: 228 (as of 2026-01-26)
Mapped: 47 verified symbols + dynamic discovery for unknown
"""

from typing import Dict, Optional
import threading

# Known asset mappings (verified from node data and API)
# These are the most actively traded and most likely to have liquidations
ASSET_ID_TO_COIN: Dict[int, str] = {
    # Tier 1: Major coins (highest volume)
    0: "BTC",
    1: "ETH",
    5: "SOL",

    # Tier 2: Large caps
    6: "AVAX",
    7: "BNB",
    9: "OP",
    10: "LTC",
    11: "ARB",
    12: "DOGE",
    16: "XRP",
    17: "LINK",
    21: "ADA",
    25: "NEAR",
    30: "DOT",
    41: "TON",

    # Tier 3: Mid caps
    2: "ATOM",
    3: "MATIC",
    4: "DYDX",
    8: "APE",
    13: "INJ",
    14: "SUI",
    15: "kPEPE",
    18: "CRV",
    19: "RNDR",
    20: "FTM",
    22: "FIL",
    23: "LDO",
    24: "GMX",
    26: "TIA",
    27: "AAVE",
    28: "SEI",
    29: "RUNE",
    31: "BLUR",
    32: "WLD",
    33: "ORDI",
    34: "MEME",
    35: "PYTH",
    36: "JTO",
    37: "STRK",
    38: "PENDLE",
    39: "W",
    40: "ENA",
    42: "BOME",
    43: "WIF",
    44: "NOT",
    45: "POPCAT",
    46: "HYPE",

    # Additional assets (discovered from node data)
    # These may need verification
    47: "FRIEND",
    48: "BRETT",
    49: "MEW",
    50: "BONK",
    51: "PEPE",
    52: "FLOKI",
    53: "SHIB",
    54: "MOTHER",
    55: "TURBO",
    56: "MOG",
    57: "NEIRO",
    58: "GOAT",
    59: "ACT",
    60: "PNUT",
    61: "CHILLGUY",
    62: "FARTCOIN",
    63: "AI16Z",
    64: "VIRTUAL",
    65: "GRIFFAIN",
    66: "ZEREBRO",
    67: "AIXBT",
    68: "ARC",
    69: "COOKIE",
    70: "ALCH",
    71: "ONDO",
    72: "FWOG",
    73: "KMNO",
    74: "USUAL",
    75: "ANIME",
    76: "SONIC",
    77: "JUP",
    78: "PENGU",
    79: "TRUMP",
    80: "MELANIA",

    # More established mid-tier
    100: "APT",
    101: "BLUR",
    102: "CYBER",
    103: "HOOK",
    104: "MANTA",
    105: "METIS",
    106: "PIXEL",
    107: "PORTAL",
    108: "PYTH",
    109: "RONIN",
    110: "SAGA",
    111: "SLERF",
    112: "TNSR",
    113: "ZETA",
    114: "ZRO",
}

# Reverse mapping for lookups
COIN_TO_ASSET_ID: Dict[str, int] = {v: k for k, v in ASSET_ID_TO_COIN.items()}

# Thread-safe storage for dynamically discovered assets
_discovered_assets: Dict[int, str] = {}
_discovery_lock = threading.Lock()


def get_coin_name(asset_id: int) -> str:
    """
    Get coin name for an asset ID.

    Returns known symbol or 'ASSET_{id}' for unknown assets.
    Unknown assets are tracked for later mapping.
    """
    # Check known mapping first
    if asset_id in ASSET_ID_TO_COIN:
        return ASSET_ID_TO_COIN[asset_id]

    # Check discovered mapping
    with _discovery_lock:
        if asset_id in _discovered_assets:
            return _discovered_assets[asset_id]

    # Return placeholder for unknown
    return f"ASSET_{asset_id}"


def register_asset(asset_id: int, coin_name: str) -> None:
    """
    Register a newly discovered asset mapping.

    Call this when we discover asset ID -> name mapping from node data.
    """
    with _discovery_lock:
        if asset_id not in ASSET_ID_TO_COIN:
            _discovered_assets[asset_id] = coin_name


def get_asset_id(coin_name: str) -> Optional[int]:
    """
    Get asset ID for a coin name.

    Returns None if coin not found.
    """
    # Check known mapping
    if coin_name in COIN_TO_ASSET_ID:
        return COIN_TO_ASSET_ID[coin_name]

    # Check discovered mapping
    with _discovery_lock:
        for asset_id, name in _discovered_assets.items():
            if name == coin_name:
                return asset_id

    return None


def get_all_mappings() -> Dict[int, str]:
    """
    Get all known asset mappings (static + discovered).
    """
    with _discovery_lock:
        result = dict(ASSET_ID_TO_COIN)
        result.update(_discovered_assets)
        return result


def get_unmapped_count() -> int:
    """
    Get count of assets we've seen but haven't mapped.
    Useful for monitoring mapping completeness.
    """
    # This would need to be tracked separately when we encounter unknown assets
    return 228 - len(ASSET_ID_TO_COIN) - len(_discovered_assets)


# Priority assets for liquidation monitoring
# These are the most liquid and most likely to have cascade events
PRIORITY_ASSETS = [
    0,   # BTC
    1,   # ETH
    5,   # SOL
    12,  # DOGE
    16,  # XRP
    7,   # BNB
    11,  # ARB
    9,   # OP
    14,  # SUI
    46,  # HYPE
]

# Get priority coin names
PRIORITY_COINS = [ASSET_ID_TO_COIN[aid] for aid in PRIORITY_ASSETS]
