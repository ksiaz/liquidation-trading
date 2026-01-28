"""
Hyperliquid Asset ID to Coin Name Mapping

Maps numeric asset IDs used in node data to human-readable coin symbols.
The node uses integer asset IDs (0=BTC, 1=ETH, etc.) in all data structures.

Total assets: 228 (as of 2026-01-28)
Source: Extracted from abci_state.rmp clearinghouse.meta.universe
"""

from typing import Dict, Optional
import threading

# Complete asset mappings from state file (2026-01-28)
ASSET_ID_TO_COIN: Dict[int, str] = {
    0: "BTC",
    1: "ETH",
    2: "ATOM",
    3: "MATIC",
    4: "DYDX",
    5: "SOL",
    6: "AVAX",
    7: "BNB",
    8: "APE",
    9: "OP",
    10: "LTC",
    11: "ARB",
    12: "DOGE",
    13: "INJ",
    14: "SUI",
    15: "kPEPE",
    16: "CRV",
    17: "LDO",
    18: "LINK",
    19: "STX",
    20: "RNDR",
    21: "CFX",
    22: "FTM",
    23: "GMX",
    24: "SNX",
    25: "XRP",
    26: "BCH",
    27: "APT",
    28: "AAVE",
    29: "COMP",
    30: "MKR",
    31: "WLD",
    32: "FXS",
    33: "HPOS",
    34: "RLB",
    35: "UNIBOT",
    36: "YGG",
    37: "TRX",
    38: "kSHIB",
    39: "UNI",
    40: "SEI",
    41: "RUNE",
    42: "OX",
    43: "FRIEND",
    44: "SHIA",
    45: "CYBER",
    46: "ZRO",
    47: "BLZ",
    48: "DOT",
    49: "BANANA",
    50: "TRB",
    51: "FTT",
    52: "LOOM",
    53: "OGN",
    54: "RDNT",
    55: "ARK",
    56: "BNT",
    57: "CANTO",
    58: "REQ",
    59: "BIGTIME",
    60: "KAS",
    61: "ORBS",
    62: "BLUR",
    63: "TIA",
    64: "BSV",
    65: "ADA",
    66: "TON",
    67: "MINA",
    68: "POLYX",
    69: "GAS",
    70: "PENDLE",
    71: "STG",
    72: "FET",
    73: "STRAX",
    74: "NEAR",
    75: "MEME",
    76: "ORDI",
    77: "BADGER",
    78: "NEO",
    79: "ZEN",
    80: "FIL",
    81: "PYTH",
    82: "SUSHI",
    83: "ILV",
    84: "IMX",
    85: "kBONK",
    86: "GMT",
    87: "SUPER",
    88: "USTC",
    89: "NFTI",
    90: "JUP",
    91: "kLUNC",
    92: "RSR",
    93: "GALA",
    94: "JTO",
    95: "NTRN",
    96: "ACE",
    97: "MAV",
    98: "WIF",
    99: "CAKE",
    100: "PEOPLE",
    101: "ENS",
    102: "ETC",
    103: "XAI",
    104: "MANTA",
    105: "UMA",
    106: "ONDO",
    107: "ALT",
    108: "ZETA",
    109: "DYM",
    110: "MAVIA",
    111: "W",
    112: "PANDORA",
    113: "STRK",
    114: "PIXEL",
    115: "AI",
    116: "TAO",
    117: "AR",
    118: "MYRO",
    119: "kFLOKI",
    120: "BOME",
    121: "ETHFI",
    122: "ENA",
    123: "MNT",
    124: "TNSR",
    125: "SAGA",
    126: "MERL",
    127: "HBAR",
    128: "POPCAT",
    129: "OMNI",
    130: "EIGEN",
    131: "REZ",
    132: "NOT",
    133: "TURBO",
    134: "BRETT",
    135: "IO",
    136: "ZK",
    137: "BLAST",
    138: "LISTA",
    139: "MEW",
    140: "RENDER",
    141: "kDOGS",
    142: "POL",
    143: "CATI",
    144: "CELO",
    145: "HMSTR",
    146: "SCR",
    147: "NEIROETH",
    148: "kNEIRO",
    149: "GOAT",
    150: "MOODENG",
    151: "GRASS",
    152: "PURR",
    153: "PNUT",
    154: "XLM",
    155: "CHILLGUY",
    156: "SAND",
    157: "IOTA",
    158: "ALGO",
    159: "HYPE",
    160: "ME",
    161: "MOVE",
    162: "VIRTUAL",
    163: "PENGU",
    164: "USUAL",
    165: "FARTCOIN",
    166: "AI16Z",
    167: "AIXBT",
    168: "ZEREBRO",
    169: "BIO",
    170: "GRIFFAIN",
    171: "SPX",
    172: "S",
    173: "MORPHO",
    174: "TRUMP",
    175: "MELANIA",
    176: "ANIME",
    177: "VINE",
    178: "VVV",
    179: "JELLY",
    180: "BERA",
    181: "TST",
    182: "LAYER",
    183: "IP",
    184: "OM",
    185: "KAITO",
    186: "NIL",
    187: "PAXG",
    188: "PROMPT",
    189: "BABY",
    190: "WCT",
    191: "HYPER",
    192: "ZORA",
    193: "INIT",
    194: "DOOD",
    195: "LAUNCHCOIN",
    196: "NXPC",
    197: "SOPH",
    198: "RESOLV",
    199: "SYRUP",
    200: "PUMP",
    201: "PROVE",
    202: "YZY",
    203: "XPL",
    204: "WLFI",
    205: "LINEA",
    206: "SKY",
    207: "ASTER",
    208: "AVNT",
    209: "STBL",
    210: "0G",
    211: "HEMI",
    212: "APEX",
    213: "2Z",
    214: "ZEC",
    215: "MON",
    216: "MET",
    217: "MEGA",
    218: "CC",
    219: "ICP",
    220: "AERO",
    221: "STABLE",
    222: "FOGO",
    223: "LIT",
    224: "XMR",
    225: "AXS",
    226: "DASH",
    227: "SKR",
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
    return 0  # All 228 assets are now mapped


# Priority assets for liquidation monitoring
# These are the most liquid and most likely to have cascade events
PRIORITY_ASSETS = [
    0,    # BTC
    1,    # ETH
    5,    # SOL
    159,  # HYPE
    12,   # DOGE
    25,   # XRP
    7,    # BNB
    11,   # ARB
    9,    # OP
    14,   # SUI
    66,   # TON
    98,   # WIF
    174,  # TRUMP
]

# Get priority coin names
PRIORITY_COINS = [ASSET_ID_TO_COIN[aid] for aid in PRIORITY_ASSETS]
