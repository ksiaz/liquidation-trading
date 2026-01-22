"""
Hyperliquid Transaction Parser

Extracts wallet addresses from Hyperliquid L1 block transactions.

Transaction types:
- order: Trader placing/canceling orders
- liquidation: Address being liquidated
- withdraw/deposit: User transfers
- vault_*: Vault operator actions
- spotOrder: Spot trading (if applicable)

Constitutional compliance:
- Only extracts factual data (addresses, tx types, values)
- No interpretation or filtering by "importance"
- Pure structural data extraction
"""

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Any
from enum import Enum

from .block_fetcher import Block


class TransactionType(Enum):
    """Types of Hyperliquid transactions."""
    ORDER = "order"
    CANCEL = "cancel"
    LIQUIDATION = "liquidation"
    DEPOSIT = "deposit"
    WITHDRAW = "withdraw"
    TRANSFER = "transfer"
    VAULT_DEPOSIT = "vault_deposit"
    VAULT_WITHDRAW = "vault_withdraw"
    SPOT_ORDER = "spot_order"
    UPDATE_LEVERAGE = "update_leverage"
    UPDATE_MARGIN = "update_margin"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ParsedTransaction:
    """Parsed transaction data."""
    block_num: int
    tx_index: int
    tx_hash: str
    tx_type: TransactionType
    from_address: str
    to_address: Optional[str]  # For transfers
    coin: str
    size: float
    price: float
    value_usd: float
    timestamp: float
    raw_data: Optional[Dict] = None


@dataclass
class AddressStats:
    """Statistics for a discovered address."""
    address: str
    first_block: int
    last_block: int
    tx_count: int
    total_volume: float
    coins_traded: Set[str]

    def to_dict(self) -> Dict:
        return {
            "address": self.address,
            "first_block": self.first_block,
            "last_block": self.last_block,
            "tx_count": self.tx_count,
            "total_volume": self.total_volume,
            "coins_traded": list(self.coins_traded)
        }


class TransactionParser:
    """
    Hyperliquid transaction parser.

    Extracts wallet addresses from block transactions.

    Usage:
        parser = TransactionParser()

        for block in blocks:
            txs = parser.parse_block(block)
            addresses = parser.extract_addresses(txs)
    """

    # Regex for Ethereum-style addresses
    ADDRESS_PATTERN = re.compile(r'0x[a-fA-F0-9]{40}')

    def __init__(self):
        self._logger = logging.getLogger("TransactionParser")

        # Stats accumulator
        self._address_stats: Dict[str, AddressStats] = {}
        self._total_txs_parsed = 0
        self._total_addresses_found = 0

    # =========================================================================
    # Block Parsing
    # =========================================================================

    def parse_block(self, block: Block) -> List[ParsedTransaction]:
        """
        Parse all transactions in a block.

        Returns list of ParsedTransaction with extracted data.
        """
        transactions = []

        for i, tx_data in enumerate(block.transactions):
            try:
                parsed = self._parse_transaction(
                    tx_data,
                    block_num=block.block_num,
                    tx_index=i,
                    timestamp=block.timestamp
                )
                if parsed:
                    transactions.append(parsed)
                    self._total_txs_parsed += 1

            except Exception as e:
                self._logger.debug(f"Failed to parse tx {i} in block {block.block_num}: {e}")

        return transactions

    def _parse_transaction(
        self,
        tx_data: Dict,
        block_num: int,
        tx_index: int,
        timestamp: float
    ) -> Optional[ParsedTransaction]:
        """
        Parse a single transaction.

        Handles various Hyperliquid transaction formats.
        """
        if not tx_data:
            return None

        # Determine transaction type and extract data
        tx_type = TransactionType.UNKNOWN
        from_address = ""
        to_address = None
        coin = ""
        size = 0.0
        price = 0.0
        value_usd = 0.0
        tx_hash = ""

        # Extract transaction type
        action = tx_data.get('action', {})
        if isinstance(action, dict):
            action_type = action.get('type', '')
        else:
            action_type = str(tx_data.get('type', ''))

        # Map action type to TransactionType
        action_lower = action_type.lower()
        if 'order' in action_lower and 'cancel' not in action_lower:
            tx_type = TransactionType.ORDER
        elif 'cancel' in action_lower:
            tx_type = TransactionType.CANCEL
        elif 'liquidat' in action_lower:
            tx_type = TransactionType.LIQUIDATION
        elif 'deposit' in action_lower:
            if 'vault' in action_lower:
                tx_type = TransactionType.VAULT_DEPOSIT
            else:
                tx_type = TransactionType.DEPOSIT
        elif 'withdraw' in action_lower:
            if 'vault' in action_lower:
                tx_type = TransactionType.VAULT_WITHDRAW
            else:
                tx_type = TransactionType.WITHDRAW
        elif 'transfer' in action_lower:
            tx_type = TransactionType.TRANSFER
        elif 'leverage' in action_lower:
            tx_type = TransactionType.UPDATE_LEVERAGE
        elif 'margin' in action_lower:
            tx_type = TransactionType.UPDATE_MARGIN
        elif 'spot' in action_lower:
            tx_type = TransactionType.SPOT_ORDER

        # Extract addresses from various locations
        from_address = self._extract_address(tx_data, [
            'user', 'from', 'sender', 'trader', 'address',
            ['action', 'user'],
            ['action', 'from'],
            ['action', 'trader']
        ])

        to_address = self._extract_address(tx_data, [
            'to', 'recipient', 'destination',
            ['action', 'to'],
            ['action', 'recipient'],
            ['action', 'destination']
        ])

        # Extract coin
        coin = self._extract_field(tx_data, [
            'coin', 'asset', 'symbol',
            ['action', 'coin'],
            ['action', 'asset']
        ], default="")

        # Extract size and price
        size = self._extract_float(tx_data, [
            'sz', 'size', 'amount', 'qty',
            ['action', 'sz'],
            ['action', 'size']
        ])

        price = self._extract_float(tx_data, [
            'px', 'price', 'limitPx',
            ['action', 'px'],
            ['action', 'limitPx']
        ])

        # Calculate value
        value_usd = abs(size * price) if price > 0 else 0.0

        # Extract tx hash
        tx_hash = str(tx_data.get('hash', tx_data.get('txHash', f"{block_num}_{tx_index}")))

        # Skip if no address found
        if not from_address:
            return None

        return ParsedTransaction(
            block_num=block_num,
            tx_index=tx_index,
            tx_hash=tx_hash,
            tx_type=tx_type,
            from_address=from_address.lower(),
            to_address=to_address.lower() if to_address else None,
            coin=coin,
            size=size,
            price=price,
            value_usd=value_usd,
            timestamp=timestamp,
            raw_data=tx_data
        )

    def _extract_address(
        self,
        data: Dict,
        paths: List
    ) -> Optional[str]:
        """
        Extract address from data using multiple possible paths.

        Args:
            data: Transaction data dict
            paths: List of keys or key paths to try

        Returns:
            Address string or None
        """
        for path in paths:
            value = self._get_nested(data, path)
            if value and isinstance(value, str):
                # Validate it's an address
                if self.ADDRESS_PATTERN.match(value):
                    return value

        # Fallback: search entire dict for addresses
        addresses = self._find_all_addresses(data)
        if addresses:
            return addresses[0]

        return None

    def _extract_field(
        self,
        data: Dict,
        paths: List,
        default: Any = None
    ) -> Any:
        """Extract field from data using multiple possible paths."""
        for path in paths:
            value = self._get_nested(data, path)
            if value is not None:
                return value
        return default

    def _extract_float(
        self,
        data: Dict,
        paths: List
    ) -> float:
        """Extract float value from data using multiple possible paths."""
        for path in paths:
            value = self._get_nested(data, path)
            if value is not None:
                try:
                    return float(value)
                except (ValueError, TypeError):
                    continue
        return 0.0

    def _get_nested(self, data: Dict, path) -> Any:
        """Get nested value from dict."""
        if isinstance(path, str):
            return data.get(path)

        # Path is a list of keys
        current = data
        for key in path:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return None
        return current

    def _find_all_addresses(self, data: Any, found: List[str] = None) -> List[str]:
        """Recursively find all addresses in data structure."""
        if found is None:
            found = []

        if isinstance(data, str):
            matches = self.ADDRESS_PATTERN.findall(data)
            found.extend(matches)
        elif isinstance(data, dict):
            for value in data.values():
                self._find_all_addresses(value, found)
        elif isinstance(data, list):
            for item in data:
                self._find_all_addresses(item, found)

        return found

    # =========================================================================
    # Address Extraction
    # =========================================================================

    def extract_addresses(self, transactions: List[ParsedTransaction]) -> Set[str]:
        """
        Extract unique addresses from transactions.

        Updates internal stats for each address.
        """
        addresses = set()

        for tx in transactions:
            # Add from address
            if tx.from_address:
                addresses.add(tx.from_address)
                self._update_address_stats(tx.from_address, tx)

            # Add to address
            if tx.to_address:
                addresses.add(tx.to_address)
                self._update_address_stats(tx.to_address, tx, is_receiver=True)

        return addresses

    def extract_addresses_from_block(self, block: Block) -> Set[str]:
        """
        Extract unique addresses directly from a block.

        Convenience method combining parse + extract.
        """
        txs = self.parse_block(block)
        return self.extract_addresses(txs)

    def _update_address_stats(
        self,
        address: str,
        tx: ParsedTransaction,
        is_receiver: bool = False
    ):
        """Update stats for an address."""
        addr = address.lower()

        if addr not in self._address_stats:
            self._address_stats[addr] = AddressStats(
                address=addr,
                first_block=tx.block_num,
                last_block=tx.block_num,
                tx_count=0,
                total_volume=0.0,
                coins_traded=set()
            )
            self._total_addresses_found += 1

        stats = self._address_stats[addr]
        stats.last_block = max(stats.last_block, tx.block_num)
        stats.tx_count += 1
        stats.total_volume += tx.value_usd

        if tx.coin:
            stats.coins_traded.add(tx.coin)

    # =========================================================================
    # Bulk Processing
    # =========================================================================

    def process_blocks(self, blocks: List[Block]) -> Set[str]:
        """
        Process multiple blocks and extract all addresses.

        Returns set of all unique addresses found.
        """
        all_addresses = set()

        for block in blocks:
            addresses = self.extract_addresses_from_block(block)
            all_addresses.update(addresses)

        return all_addresses

    # =========================================================================
    # Stats and Results
    # =========================================================================

    def get_address_stats(self, address: str) -> Optional[AddressStats]:
        """Get accumulated stats for an address."""
        return self._address_stats.get(address.lower())

    def get_all_address_stats(self) -> Dict[str, AddressStats]:
        """Get all accumulated address stats."""
        return dict(self._address_stats)

    def get_addresses_by_volume(self, min_volume: float = 0) -> List[str]:
        """Get addresses sorted by volume."""
        filtered = [
            (addr, stats.total_volume)
            for addr, stats in self._address_stats.items()
            if stats.total_volume >= min_volume
        ]
        filtered.sort(key=lambda x: x[1], reverse=True)
        return [addr for addr, _ in filtered]

    def get_addresses_by_tx_count(self, min_txs: int = 0) -> List[str]:
        """Get addresses sorted by transaction count."""
        filtered = [
            (addr, stats.tx_count)
            for addr, stats in self._address_stats.items()
            if stats.tx_count >= min_txs
        ]
        filtered.sort(key=lambda x: x[1], reverse=True)
        return [addr for addr, _ in filtered]

    def get_recent_addresses(self, min_block: int) -> List[str]:
        """Get addresses active after a certain block."""
        return [
            addr
            for addr, stats in self._address_stats.items()
            if stats.last_block >= min_block
        ]

    def get_stats(self) -> Dict:
        """Get parser statistics."""
        return {
            "total_txs_parsed": self._total_txs_parsed,
            "total_addresses_found": self._total_addresses_found,
            "unique_addresses": len(self._address_stats)
        }

    def reset_stats(self):
        """Reset accumulated statistics."""
        self._address_stats.clear()
        self._total_txs_parsed = 0
        self._total_addresses_found = 0


# =============================================================================
# Convenience Functions
# =============================================================================

def extract_addresses_from_raw(raw_data: bytes) -> Set[str]:
    """
    Extract addresses directly from raw bytes.

    Uses regex pattern matching without full parsing.
    Useful for quick scanning.
    """
    text = raw_data.decode('utf-8', errors='ignore')
    return set(TransactionParser.ADDRESS_PATTERN.findall(text))
