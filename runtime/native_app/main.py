"""
Liquidation Trading System - Comprehensive Dashboard

Architecture:
1. Initializes ObservationSystem (M1-M5 Sealed).
2. Starts CollectorService (Runtime Driver).
3. Polls ObservationSystem for State.
4. Renders comprehensive dashboard with:
   - Price ticker for all symbols
   - Liquidation proximity table (sorted by $ value)
   - Cascade state panel
   - Positions & P&L tracking
   - Order book depth visualization
   - Trade history from database
"""

import sys
import os

# Fix path to include project root FIRST
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Configure temp directories to use D drive (must be early, before other imports)
import runtime.env_setup  # noqa: F401

import asyncio
import threading
import time
import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional

from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget,
                              QLabel, QHBoxLayout, QFrame, QStackedWidget,
                              QGridLayout, QGroupBox, QScrollArea, QSplitter,
                              QTableWidget, QTableWidgetItem, QHeaderView,
                              QAbstractItemView, QPushButton)
from PySide6.QtCore import QTimer, Slot, Qt
from PySide6.QtGui import QFont, QColor

from observation import ObservationSystem, ObservationSnapshot
from observation.types import ObservationStatus, SystemHaltedException
from runtime.collector.service import CollectorService, TOP_10_SYMBOLS


# ==============================================================================
# Constants
# ==============================================================================

DB_PATH = "D:/liquidation-trading/logs/execution.db"
HL_INDEXED_DB_PATH = "D:/liquidation-trading/indexed_wallets.db"

COLORS = {
    "background": "#0d0d1a",
    "panel_bg": "#151525",
    "header": "#6cf",
    "long": "#4f4",
    "short": "#f44",
    "profit": "#4f4",
    "loss": "#f44",
    "warning": "#ff0",
    "critical": "#f80",
    "running": "#4f4",
    "idle": "#666",
    "text": "#eee",
    "text_dim": "#888",
    "border": "#335",
}


# ==============================================================================
# Data Aggregation Functions
# ==============================================================================

def format_value(value: float) -> str:
    """Format large dollar values compactly."""
    if value >= 1_000_000:
        return f"${value/1_000_000:.1f}M"
    elif value >= 1_000:
        return f"${value/1_000:.0f}K"
    else:
        return f"${value:.0f}"


def aggregate_liquidation_proximity(snapshot: ObservationSnapshot) -> List[Dict]:
    """Collect all liquidations across all symbols, sort by value."""
    all_positions = []

    for symbol, bundle in snapshot.primitives.items():
        if bundle is None or bundle.liquidation_cascade_proximity is None:
            continue

        prox = bundle.liquidation_cascade_proximity
        price = prox.price_level

        # Add long positions
        if prox.long_positions_count > 0:
            # Calculate distance to closest liquidation
            if prox.long_closest_price and price > 0:
                dist_pct = abs(price - prox.long_closest_price) / price * 100
            else:
                dist_pct = 999

            all_positions.append({
                'symbol': symbol.replace("USDT", ""),
                'side': 'LONG',
                'value': prox.long_positions_value,
                'distance_pct': dist_pct,
                'closest_price': prox.long_closest_price,
                'count': prox.long_positions_count,
                'price': price
            })

        # Add short positions
        if prox.short_positions_count > 0:
            if prox.short_closest_price and price > 0:
                dist_pct = abs(prox.short_closest_price - price) / price * 100
            else:
                dist_pct = 999

            all_positions.append({
                'symbol': symbol.replace("USDT", ""),
                'side': 'SHORT',
                'value': prox.short_positions_value,
                'distance_pct': dist_pct,
                'closest_price': prox.short_closest_price,
                'count': prox.short_positions_count,
                'price': price
            })

    # Sort by distance to liquidation (closest first)
    return sorted(all_positions, key=lambda x: x['distance_pct'])


def aggregate_prices(snapshot: ObservationSnapshot) -> Dict[str, Dict]:
    """Get current prices for all symbols."""
    prices = {}

    for symbol, bundle in snapshot.primitives.items():
        if bundle is None:
            continue

        price = None
        if bundle.liquidation_cascade_proximity:
            price = bundle.liquidation_cascade_proximity.price_level

        prices[symbol] = {
            'price': price,
            'symbol_short': symbol.replace("USDT", "")
        }

    return prices


def aggregate_cascade_state(snapshot: ObservationSnapshot) -> Dict:
    """Aggregate cascade state across all symbols."""
    total_at_risk = 0
    total_positions = 0
    liquidations_30s = 0
    closest_liq = None
    closest_symbol = None
    phase = "NONE"

    for symbol, bundle in snapshot.primitives.items():
        if bundle is None:
            continue

        if bundle.liquidation_cascade_proximity:
            prox = bundle.liquidation_cascade_proximity
            total_at_risk += prox.aggregate_position_value
            total_positions += prox.positions_at_risk_count

            # Track closest liquidation
            if prox.long_closest_price and prox.price_level:
                dist = abs(prox.price_level - prox.long_closest_price) / prox.price_level * 100
                if closest_liq is None or dist < closest_liq:
                    closest_liq = dist
                    closest_symbol = symbol.replace("USDT", "")

            if prox.short_closest_price and prox.price_level:
                dist = abs(prox.short_closest_price - prox.price_level) / prox.price_level * 100
                if closest_liq is None or dist < closest_liq:
                    closest_liq = dist
                    closest_symbol = symbol.replace("USDT", "")

        if bundle.cascade_state:
            cs = bundle.cascade_state
            liquidations_30s += cs.liquidations_30s
            # Use highest phase observed
            p = cs.phase.name if hasattr(cs.phase, 'name') else str(cs.phase)
            phase_priority = {"NONE": 0, "PROXIMITY": 1, "LIQUIDATING": 2, "CASCADING": 3, "EXHAUSTED": 4}
            if phase_priority.get(p, 0) > phase_priority.get(phase, 0):
                phase = p

    return {
        'phase': phase,
        'liquidations_30s': liquidations_30s,
        'total_at_risk': total_at_risk,
        'total_positions': total_positions,
        'closest_pct': closest_liq,
        'closest_symbol': closest_symbol
    }


def get_orderbook_depth(snapshot: ObservationSnapshot) -> List[Dict]:
    """Get order book depth for top symbols."""
    depth = []

    for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
        bundle = snapshot.primitives.get(symbol)
        if bundle is None or bundle.resting_size is None:
            depth.append({
                'symbol': symbol.replace("USDT", ""),
                'bid_size': 0,
                'bid_price': 0,
                'ask_size': 0,
                'ask_price': 0
            })
            continue

        rs = bundle.resting_size
        bid_price = rs.best_bid_price or 0
        ask_price = rs.best_ask_price or 0

        # Convert quantity to dollar value (size * price)
        bid_qty = rs.bid_size if hasattr(rs, 'bid_size') else 0
        ask_qty = rs.ask_size if hasattr(rs, 'ask_size') else 0

        depth.append({
            'symbol': symbol.replace("USDT", ""),
            'bid_size': bid_qty * bid_price if bid_price else 0,  # Dollar value
            'bid_price': bid_price,
            'ask_size': ask_qty * ask_price if ask_price else 0,  # Dollar value
            'ask_price': ask_price
        })

    return depth


def load_recent_trades(limit: int = 15) -> List[Dict]:
    """Load recent ghost trades from execution.db."""
    if not os.path.exists(DB_PATH):
        return []

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT symbol, side, price, timestamp, is_entry, pnl, pnl_pct,
                   holding_duration_sec, exit_reason, winning_policy_name
            FROM ghost_trades
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        trades = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return trades
    except Exception as e:
        print(f"Error loading trades: {e}")
        return []


def load_hyperliquid_positions(limit: int = 30, max_distance_pct: float = 10.0, sort_by: str = "impact") -> List[Dict]:
    """
    Load individual Hyperliquid positions.

    Args:
        limit: Max positions to return
        max_distance_pct: Only show positions within this distance of liquidation
        sort_by: "impact" (size * impact DESC) or "distance" (closest to liq first)
    """
    if not os.path.exists(HL_INDEXED_DB_PATH):
        return []

    try:
        conn = sqlite3.connect(HL_INDEXED_DB_PATH)
        conn.row_factory = sqlite3.Row

        if sort_by == "distance":
            # Sort by distance to liquidation (closest first)
            cursor = conn.execute("""
                SELECT wallet_address, coin, side, entry_price, position_size,
                       position_value, leverage, liquidation_price, margin_used,
                       unrealized_pnl, distance_to_liq_pct, daily_volume, impact_score, updated_at
                FROM positions
                WHERE distance_to_liq_pct <= ? AND distance_to_liq_pct < 999
                ORDER BY distance_to_liq_pct ASC
                LIMIT ?
            """, (max_distance_pct, limit))
        else:
            # Sort by impact (size * impact, highest first)
            cursor = conn.execute("""
                SELECT wallet_address, coin, side, entry_price, position_size,
                       position_value, leverage, liquidation_price, margin_used,
                       unrealized_pnl, distance_to_liq_pct, daily_volume, impact_score, updated_at,
                       (position_value * impact_score) as combined_score
                FROM positions
                WHERE distance_to_liq_pct <= ? AND impact_score > 0
                ORDER BY combined_score DESC
                LIMIT ?
            """, (max_distance_pct, limit))

        positions = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return positions
    except Exception as e:
        print(f"Error loading HL positions: {e}")
        return []


def count_primitives(bundle) -> int:
    """Count non-None primitives in a bundle."""
    if bundle is None:
        return 0

    fields = [
        bundle.zone_penetration,
        bundle.price_traversal_velocity,
        bundle.traversal_compactness,
        bundle.structural_absence_duration,
        bundle.resting_size,
        bundle.order_consumption,
        bundle.refill_event,
        bundle.supply_demand_zone,
        bundle.order_block,
        bundle.liquidation_cascade_proximity,
        bundle.cascade_state,
    ]
    return sum(1 for f in fields if f is not None)


# ==============================================================================
# Widget Classes
# ==============================================================================

class RedScreenOfDeath(QWidget):
    """Fatal error display."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: #440000; color: #ff3333;")
        layout = QVBoxLayout()

        title = QLabel("SYSTEM HALTED")
        title.setFont(QFont("Consolas", 24, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.detail = QLabel("")
        self.detail.setStyleSheet("font-size: 16px; color: white;")
        self.detail.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.detail)
        layout.addStretch()
        self.setLayout(layout)

    def set_error(self, message):
        self.detail.setText(f"{message}")


class PriceTickerWidget(QFrame):
    """Horizontal price ticker showing all symbols."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {COLORS['panel_bg']}; border-radius: 4px;")
        self.setFixedHeight(32)

        layout = QHBoxLayout()
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(20)

        self.price_labels = {}
        for symbol in TOP_10_SYMBOLS:
            short = symbol.replace("USDT", "")
            label = QLabel(f"{short} --")
            label.setFont(QFont("Consolas", 10))
            label.setStyleSheet(f"color: {COLORS['text_dim']};")
            self.price_labels[symbol] = label
            layout.addWidget(label)

        layout.addStretch()
        self.setLayout(layout)

    def update_data(self, prices: Dict[str, Dict]):
        """Update price display."""
        for symbol, data in prices.items():
            if symbol in self.price_labels:
                price = data.get('price')
                short = data.get('symbol_short', symbol)
                if price:
                    if price >= 1000:
                        text = f"{short} ${price:,.0f}"
                    elif price >= 1:
                        text = f"{short} ${price:.2f}"
                    else:
                        text = f"{short} ${price:.4f}"
                    self.price_labels[symbol].setText(text)
                    self.price_labels[symbol].setStyleSheet(f"color: {COLORS['text']};")


class LiquidationProximityTable(QTableWidget):
    """Table showing all liquidation proximity data sorted by value."""

    def __init__(self):
        super().__init__()
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels(["Symbol", "Side", "Count", "Value", "Dist %"])

        # Style
        self.setStyleSheet(f"""
            QTableWidget {{
                background-color: {COLORS['panel_bg']};
                color: {COLORS['text']};
                border: none;
                gridline-color: #222;
                alternate-background-color: #1a1a2a;
            }}
            QHeaderView::section {{
                background-color: #1a1a2a;
                color: {COLORS['header']};
                font-weight: bold;
                padding: 4px;
                border: none;
            }}
            QTableWidget::item {{
                padding: 2px;
                background-color: {COLORS['panel_bg']};
            }}
            QTableWidget::item:alternate {{
                background-color: #1a1a2a;
            }}
        """)

        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.verticalHeader().setVisible(False)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)

    def update_data(self, positions: List[Dict]):
        """Update table with aggregated positions."""
        self.setRowCount(len(positions))

        for row, pos in enumerate(positions):
            # Symbol
            item = QTableWidgetItem(pos['symbol'])
            item.setFont(QFont("Consolas", 9, QFont.Bold))
            self.setItem(row, 0, item)

            # Side
            side_item = QTableWidgetItem(pos['side'])
            side_item.setFont(QFont("Consolas", 9))
            color = COLORS['long'] if pos['side'] == 'LONG' else COLORS['short']
            side_item.setForeground(QColor(color))
            self.setItem(row, 1, side_item)

            # Count
            count_item = QTableWidgetItem(str(pos['count']))
            count_item.setFont(QFont("Consolas", 9))
            self.setItem(row, 2, count_item)

            # Value
            value_item = QTableWidgetItem(format_value(pos['value']))
            value_item.setFont(QFont("Consolas", 9, QFont.Bold))
            self.setItem(row, 3, value_item)

            # Distance %
            dist = pos['distance_pct']
            dist_item = QTableWidgetItem(f"{dist:.2f}%")
            dist_item.setFont(QFont("Consolas", 9))

            # Color by proximity
            if dist < 0.2:
                dist_item.setForeground(QColor(COLORS['short']))  # Red - critical
            elif dist < 0.35:
                dist_item.setForeground(QColor(COLORS['critical']))  # Orange
            elif dist < 0.5:
                dist_item.setForeground(QColor(COLORS['warning']))  # Yellow
            else:
                dist_item.setForeground(QColor(COLORS['text_dim']))

            self.setItem(row, 4, dist_item)

        self.resizeRowsToContents()


class HyperliquidPositionsTable(QTableWidget):
    """Table showing individual Hyperliquid positions by potential market impact."""

    def __init__(self):
        super().__init__()
        self.setColumnCount(6)
        self.setHorizontalHeaderLabels(["Address", "Coin", "Side", "Value", "Dist %", "Impact"])

        # Style
        self.setStyleSheet(f"""
            QTableWidget {{
                background-color: {COLORS['panel_bg']};
                color: {COLORS['text']};
                border: none;
                gridline-color: #222;
                alternate-background-color: #1a1a2a;
            }}
            QHeaderView::section {{
                background-color: #1a1a2a;
                color: {COLORS['header']};
                font-weight: bold;
                padding: 4px;
                border: none;
            }}
            QTableWidget::item {{
                padding: 2px;
                background-color: {COLORS['panel_bg']};
            }}
            QTableWidget::item:alternate {{
                background-color: #1a1a2a;
            }}
        """)

        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.verticalHeader().setVisible(False)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)

    def update_data(self, positions: List[Dict]):
        """Update table with individual Hyperliquid positions."""
        self.setRowCount(len(positions))

        for row, pos in enumerate(positions):
            # Address (shortened)
            addr = pos.get('wallet_address', '')
            short_addr = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 10 else addr
            addr_item = QTableWidgetItem(short_addr)
            addr_item.setFont(QFont("Consolas", 8))
            addr_item.setForeground(QColor(COLORS['text_dim']))
            self.setItem(row, 0, addr_item)

            # Coin
            coin_item = QTableWidgetItem(pos.get('coin', ''))
            coin_item.setFont(QFont("Consolas", 9, QFont.Bold))
            self.setItem(row, 1, coin_item)

            # Side
            side = pos.get('side', '')
            side_item = QTableWidgetItem(side)
            side_item.setFont(QFont("Consolas", 9))
            color = COLORS['long'] if side == 'LONG' else COLORS['short']
            side_item.setForeground(QColor(color))
            self.setItem(row, 2, side_item)

            # Value
            value = pos.get('position_value', 0)
            value_item = QTableWidgetItem(format_value(value))
            value_item.setFont(QFont("Consolas", 9, QFont.Bold))
            self.setItem(row, 3, value_item)

            # Distance %
            dist = pos.get('distance_to_liq_pct', 999)
            dist_item = QTableWidgetItem(f"{dist:.1f}%")
            dist_item.setFont(QFont("Consolas", 9))

            # Color by proximity
            if dist < 1.0:
                dist_item.setForeground(QColor(COLORS['short']))  # Red - critical
            elif dist < 3.0:
                dist_item.setForeground(QColor(COLORS['critical']))  # Orange
            elif dist < 5.0:
                dist_item.setForeground(QColor(COLORS['warning']))  # Yellow
            else:
                dist_item.setForeground(QColor(COLORS['text_dim']))

            self.setItem(row, 4, dist_item)

            # Impact Score (% of daily volume)
            impact = pos.get('impact_score', 0)
            if impact >= 1.0:
                impact_text = f"{impact:.1f}%"
            elif impact >= 0.1:
                impact_text = f"{impact:.2f}%"
            else:
                impact_text = f"{impact:.3f}%"
            impact_item = QTableWidgetItem(impact_text)
            impact_item.setFont(QFont("Consolas", 9, QFont.Bold))

            # Color by impact (high impact = more dangerous)
            if impact >= 1.0:
                impact_item.setForeground(QColor(COLORS['short']))  # Red - huge impact
            elif impact >= 0.1:
                impact_item.setForeground(QColor(COLORS['critical']))  # Orange
            elif impact >= 0.01:
                impact_item.setForeground(QColor(COLORS['warning']))  # Yellow
            else:
                impact_item.setForeground(QColor(COLORS['text']))

            self.setItem(row, 5, impact_item)

        self.resizeRowsToContents()


class CascadeStateWidget(QFrame):
    """Panel showing cascade state machine status."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {COLORS['panel_bg']}; border-radius: 4px;")

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        # Title
        title = QLabel("CASCADE STATE")
        title.setFont(QFont("Consolas", 10, QFont.Bold))
        title.setStyleSheet(f"color: {COLORS['header']};")
        layout.addWidget(title)

        # Phase
        self.phase_label = QLabel("NONE")
        self.phase_label.setFont(QFont("Consolas", 16, QFont.Bold))
        self.phase_label.setAlignment(Qt.AlignCenter)
        self.phase_label.setStyleSheet(f"color: {COLORS['idle']}; padding: 5px;")
        layout.addWidget(self.phase_label)

        # Stats
        self.liq_label = QLabel("Liquidations (30s): 0")
        self.liq_label.setFont(QFont("Consolas", 9))
        self.liq_label.setStyleSheet(f"color: {COLORS['text_dim']};")
        layout.addWidget(self.liq_label)

        self.total_label = QLabel("Total at risk: $0 (0 pos)")
        self.total_label.setFont(QFont("Consolas", 9))
        self.total_label.setStyleSheet(f"color: {COLORS['text_dim']};")
        layout.addWidget(self.total_label)

        self.closest_label = QLabel("Closest: --")
        self.closest_label.setFont(QFont("Consolas", 9))
        self.closest_label.setStyleSheet(f"color: {COLORS['warning']};")
        layout.addWidget(self.closest_label)

        self.setLayout(layout)

    def update_data(self, state: Dict):
        """Update cascade state display."""
        phase = state.get('phase', 'NONE')
        self.phase_label.setText(phase)

        # Color by phase
        phase_colors = {
            "NONE": COLORS['idle'],
            "PROXIMITY": COLORS['warning'],
            "LIQUIDATING": COLORS['critical'],
            "CASCADING": COLORS['short'],
            "EXHAUSTED": COLORS['long'],
        }
        color = phase_colors.get(phase, COLORS['idle'])
        self.phase_label.setStyleSheet(f"color: {color}; padding: 5px;")

        self.liq_label.setText(f"Liquidations (30s): {state.get('liquidations_30s', 0)}")
        self.total_label.setText(
            f"Total at risk: {format_value(state.get('total_at_risk', 0))} "
            f"({state.get('total_positions', 0)} pos)"
        )

        closest = state.get('closest_pct')
        closest_sym = state.get('closest_symbol')
        if closest is not None and closest_sym:
            self.closest_label.setText(f"Closest: {closest_sym} ({closest:.2f}%)")
        else:
            self.closest_label.setText("Closest: --")


class PositionsPnLWidget(QTableWidget):
    """Table showing current positions and P&L."""

    def __init__(self):
        super().__init__()
        self.setColumnCount(5)
        self.setHorizontalHeaderLabels(["Symbol", "Side", "Entry", "Current", "P&L"])

        self.setStyleSheet(f"""
            QTableWidget {{
                background-color: {COLORS['panel_bg']};
                color: {COLORS['text']};
                border: none;
                alternate-background-color: #1a1a2a;
            }}
            QHeaderView::section {{
                background-color: #1a1a2a;
                color: {COLORS['header']};
                font-weight: bold;
                padding: 4px;
                border: none;
            }}
            QTableWidget::item {{
                background-color: {COLORS['panel_bg']};
            }}
            QTableWidget::item:alternate {{
                background-color: #1a1a2a;
            }}
        """)

        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.verticalHeader().setVisible(False)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setAlternatingRowColors(True)

        # Placeholder
        self.setRowCount(1)
        item = QTableWidgetItem("No open positions")
        item.setForeground(QColor(COLORS['text_dim']))
        self.setItem(0, 0, item)

    def update_data(self, positions: List[Dict]):
        """Update positions display."""
        if not positions:
            self.setRowCount(1)
            item = QTableWidgetItem("No open positions")
            item.setForeground(QColor(COLORS['text_dim']))
            self.setItem(0, 0, item)
            return

        self.setRowCount(len(positions))
        for row, pos in enumerate(positions):
            self.setItem(row, 0, QTableWidgetItem(pos.get('symbol', '')))

            side_item = QTableWidgetItem(pos.get('side', ''))
            color = COLORS['long'] if pos.get('side') == 'LONG' else COLORS['short']
            side_item.setForeground(QColor(color))
            self.setItem(row, 1, side_item)

            self.setItem(row, 2, QTableWidgetItem(f"${pos.get('entry_price', 0):,.2f}"))
            self.setItem(row, 3, QTableWidgetItem(f"${pos.get('current_price', 0):,.2f}"))

            pnl = pos.get('pnl_pct', 0)
            pnl_item = QTableWidgetItem(f"{pnl:+.2f}%")
            pnl_item.setForeground(QColor(COLORS['profit'] if pnl >= 0 else COLORS['loss']))
            self.setItem(row, 4, pnl_item)


class OrderBookDepthWidget(QFrame):
    """Widget showing order book depth for top symbols."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {COLORS['panel_bg']}; border-radius: 4px;")

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(4)

        title = QLabel("ORDER BOOK DEPTH")
        title.setFont(QFont("Consolas", 10, QFont.Bold))
        title.setStyleSheet(f"color: {COLORS['header']};")
        layout.addWidget(title)

        self.symbol_labels = {}
        for symbol in ["BTC", "ETH", "SOL"]:
            sym_layout = QVBoxLayout()
            sym_layout.setSpacing(1)

            sym_label = QLabel(f"{symbol}")
            sym_label.setFont(QFont("Consolas", 9, QFont.Bold))
            sym_label.setStyleSheet(f"color: {COLORS['text']};")
            sym_layout.addWidget(sym_label)

            bid_label = QLabel("Bid: --")
            bid_label.setFont(QFont("Consolas", 8))
            bid_label.setStyleSheet(f"color: {COLORS['long']};")
            sym_layout.addWidget(bid_label)

            ask_label = QLabel("Ask: --")
            ask_label.setFont(QFont("Consolas", 8))
            ask_label.setStyleSheet(f"color: {COLORS['short']};")
            sym_layout.addWidget(ask_label)

            self.symbol_labels[symbol] = {'bid': bid_label, 'ask': ask_label}
            layout.addLayout(sym_layout)

        layout.addStretch()
        self.setLayout(layout)

    def update_data(self, depth: List[Dict]):
        """Update order book depth display."""
        for d in depth:
            sym = d['symbol']
            if sym in self.symbol_labels:
                labels = self.symbol_labels[sym]

                bid_size = d.get('bid_size', 0)
                bid_price = d.get('bid_price', 0)
                if bid_size and bid_price:
                    labels['bid'].setText(f"Bid: {format_value(bid_size)} @ ${bid_price:,.0f}")
                else:
                    labels['bid'].setText("Bid: --")

                ask_size = d.get('ask_size', 0)
                ask_price = d.get('ask_price', 0)
                if ask_size and ask_price:
                    labels['ask'].setText(f"Ask: {format_value(ask_size)} @ ${ask_price:,.0f}")
                else:
                    labels['ask'].setText("Ask: --")


class TradeHistoryWidget(QFrame):
    """Widget showing recent trade history from database."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {COLORS['panel_bg']}; border-radius: 4px;")

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        title = QLabel("TRADE HISTORY")
        title.setFont(QFont("Consolas", 10, QFont.Bold))
        title.setStyleSheet(f"color: {COLORS['header']};")
        layout.addWidget(title)

        self.trade_labels = []
        for i in range(10):
            label = QLabel("")
            label.setFont(QFont("Consolas", 8))
            label.setStyleSheet(f"color: {COLORS['text_dim']};")
            self.trade_labels.append(label)
            layout.addWidget(label)

        layout.addStretch()
        self.setLayout(layout)

        # Load initial trades
        self.refresh_trades()

    def refresh_trades(self):
        """Reload trades from database."""
        trades = load_recent_trades(limit=10)
        self.update_data(trades)

    def update_data(self, trades: List[Dict]):
        """Update trade history display."""
        for i, label in enumerate(self.trade_labels):
            if i < len(trades):
                trade = trades[i]
                ts = trade.get('timestamp', 0)
                time_str = datetime.fromtimestamp(ts).strftime('%H:%M') if ts else '--:--'
                symbol = trade.get('symbol', '').replace('USDT', '')
                side = trade.get('side', '')
                price = trade.get('price', 0)
                is_entry = trade.get('is_entry', True)

                action = "ENTRY" if is_entry else "EXIT"
                text = f"{time_str} {action:5} {symbol:4} {side:5} @ ${price:,.0f}"
                label.setText(text)

                color = COLORS['long'] if is_entry else COLORS['short']
                label.setStyleSheet(f"color: {color};")
            else:
                label.setText("")


class PrimitivesStatusRow(QFrame):
    """Compact row showing primitives count per symbol."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {COLORS['panel_bg']}; border-radius: 4px;")
        self.setFixedHeight(24)

        layout = QHBoxLayout()
        layout.setContentsMargins(10, 2, 10, 2)
        layout.setSpacing(10)

        label = QLabel("Primitives:")
        label.setFont(QFont("Consolas", 9))
        label.setStyleSheet(f"color: {COLORS['text_dim']};")
        layout.addWidget(label)

        self.status_label = QLabel("")
        self.status_label.setFont(QFont("Consolas", 9))
        self.status_label.setStyleSheet(f"color: {COLORS['text']};")
        layout.addWidget(self.status_label)

        layout.addStretch()
        self.setLayout(layout)

    def update_data(self, counts: Dict[str, int]):
        """Update primitives count display."""
        parts = [f"{sym.replace('USDT', '')}({cnt})" for sym, cnt in counts.items() if cnt > 0]
        self.status_label.setText("  ".join(parts[:8]))  # Show up to 8


class ActivityLogRow(QFrame):
    """Single-line activity log at bottom."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background-color: {COLORS['panel_bg']}; border-radius: 4px;")
        self.setFixedHeight(24)

        layout = QHBoxLayout()
        layout.setContentsMargins(10, 2, 10, 2)

        self.label = QLabel("Waiting for activity...")
        self.label.setFont(QFont("Consolas", 9))
        self.label.setStyleSheet(f"color: {COLORS['text_dim']};")
        layout.addWidget(self.label)

        self.setLayout(layout)

        self.messages = []

    def add_message(self, msg: str):
        """Add a new activity message."""
        ts = time.strftime("%H:%M:%S")
        self.messages.append(f"[{ts}] {msg}")
        self.messages = self.messages[-3:]  # Keep last 3
        self.label.setText("  |  ".join(self.messages))
        self.label.setStyleSheet(f"color: {COLORS['text']};")


# ==============================================================================
# Main Window
# ==============================================================================

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Liquidation Trading System")
        self.resize(1200, 800)
        self.start_time = time.time()

        # 1. Initialize Core Systems
        self.obs_system = ObservationSystem(TOP_10_SYMBOLS)
        self.collector = CollectorService(self.obs_system, warmup_duration_sec=0)

        # 2. UI Setup
        self.stack = QStackedWidget()
        self.red_screen = RedScreenOfDeath()

        # Main Dashboard
        self.dashboard = QWidget()
        self.dashboard.setStyleSheet(f"background-color: {COLORS['background']}; color: {COLORS['text']};")
        main_layout = QVBoxLayout()
        main_layout.setSpacing(6)
        main_layout.setContentsMargins(8, 8, 8, 8)

        # ===== HEADER ROW =====
        header_layout = QHBoxLayout()

        title = QLabel("LIQUIDATION TRADING SYSTEM")
        title.setFont(QFont("Consolas", 14, QFont.Bold))
        title.setStyleSheet(f"color: {COLORS['header']};")
        header_layout.addWidget(title)

        header_layout.addStretch()

        self.status_indicator = QLabel("RUNNING")
        self.status_indicator.setFont(QFont("Consolas", 11, QFont.Bold))
        self.status_indicator.setStyleSheet(
            f"color: {COLORS['running']}; padding: 3px 10px; "
            f"background-color: #1a3a1a; border-radius: 4px;"
        )
        header_layout.addWidget(self.status_indicator)

        self.uptime_label = QLabel("0m 0s")
        self.uptime_label.setFont(QFont("Consolas", 10))
        self.uptime_label.setStyleSheet(f"color: {COLORS['text_dim']};")
        header_layout.addWidget(self.uptime_label)

        self.intervals_label = QLabel("| 0 int")
        self.intervals_label.setFont(QFont("Consolas", 10))
        self.intervals_label.setStyleSheet(f"color: {COLORS['text_dim']};")
        header_layout.addWidget(self.intervals_label)

        main_layout.addLayout(header_layout)

        # ===== PRICE TICKER =====
        self.price_ticker = PriceTickerWidget()
        main_layout.addWidget(self.price_ticker)

        # ===== MAIN CONTENT AREA =====
        content_layout = QHBoxLayout()

        # ----- LEFT COLUMN (55%) -----
        left_layout = QVBoxLayout()
        left_layout.setSpacing(6)

        # Hyperliquid Positions Section
        hl_group = QGroupBox("HYPERLIQUID POSITIONS")
        hl_group.setFont(QFont("Consolas", 9, QFont.Bold))
        hl_group.setStyleSheet(f"""
            QGroupBox {{
                color: {COLORS['critical']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }}
        """)
        hl_layout = QVBoxLayout()

        # Sort toggle buttons
        sort_row = QHBoxLayout()
        sort_label = QLabel("Sort:")
        sort_label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px;")
        sort_row.addWidget(sort_label)

        self.sort_impact_btn = QPushButton("Impact")
        self.sort_impact_btn.setCheckable(True)
        self.sort_impact_btn.setChecked(True)
        self.sort_impact_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['long']};
                color: white;
                border: none;
                padding: 3px 8px;
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:!checked {{
                background-color: {COLORS['panel_bg']};
                color: {COLORS['text_dim']};
            }}
        """)
        self.sort_impact_btn.clicked.connect(lambda: self._set_sort_mode("impact"))
        sort_row.addWidget(self.sort_impact_btn)

        self.sort_distance_btn = QPushButton("Distance")
        self.sort_distance_btn.setCheckable(True)
        self.sort_distance_btn.setChecked(False)
        self.sort_distance_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['short']};
                color: white;
                border: none;
                padding: 3px 8px;
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:!checked {{
                background-color: {COLORS['panel_bg']};
                color: {COLORS['text_dim']};
            }}
        """)
        self.sort_distance_btn.clicked.connect(lambda: self._set_sort_mode("distance"))
        sort_row.addWidget(self.sort_distance_btn)

        sort_row.addStretch()
        hl_layout.addLayout(sort_row)

        self.hl_sort_mode = "impact"  # Default sort mode
        self.hl_positions_table = HyperliquidPositionsTable()
        self.hl_positions_table.setMinimumHeight(250)
        hl_layout.addWidget(self.hl_positions_table)
        hl_group.setLayout(hl_layout)
        left_layout.addWidget(hl_group, stretch=4)

        # Cascade State
        self.cascade_widget = CascadeStateWidget()
        left_layout.addWidget(self.cascade_widget, stretch=1)

        # Primitives status
        self.primitives_row = PrimitivesStatusRow()
        left_layout.addWidget(self.primitives_row)

        content_layout.addLayout(left_layout, stretch=55)

        # ----- RIGHT COLUMN (45%) -----
        right_layout = QVBoxLayout()
        right_layout.setSpacing(6)

        # Positions & P&L
        pos_group = QGroupBox("POSITIONS & P&L")
        pos_group.setFont(QFont("Consolas", 9, QFont.Bold))
        pos_group.setStyleSheet(f"""
            QGroupBox {{
                color: {COLORS['header']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }}
        """)
        pos_layout = QVBoxLayout()
        self.positions_table = PositionsPnLWidget()
        self.positions_table.setMaximumHeight(120)
        pos_layout.addWidget(self.positions_table)
        pos_group.setLayout(pos_layout)
        right_layout.addWidget(pos_group)

        # Order Book Depth
        self.orderbook_widget = OrderBookDepthWidget()
        right_layout.addWidget(self.orderbook_widget)

        # Trade History
        trade_group = QGroupBox("TRADE HISTORY")
        trade_group.setFont(QFont("Consolas", 9, QFont.Bold))
        trade_group.setStyleSheet(f"""
            QGroupBox {{
                color: {COLORS['header']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                margin-top: 8px;
                padding-top: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }}
        """)
        trade_layout = QVBoxLayout()
        self.trade_history = TradeHistoryWidget()
        trade_layout.addWidget(self.trade_history)
        trade_group.setLayout(trade_layout)
        right_layout.addWidget(trade_group, stretch=2)

        content_layout.addLayout(right_layout, stretch=45)

        main_layout.addLayout(content_layout)

        # ===== ACTIVITY LOG =====
        self.activity_log = ActivityLogRow()
        main_layout.addWidget(self.activity_log)

        self.dashboard.setLayout(main_layout)

        self.stack.addWidget(self.dashboard)
        self.stack.addWidget(self.red_screen)
        self.setCentralWidget(self.stack)

        # Tracking
        self.last_trade_refresh = 0

        # 3. Start Update Loop
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(250)

        # 4. Start Collector Thread
        self.loop_thread = threading.Thread(target=self.run_async_loop, daemon=True)
        self.loop_thread.start()

    def run_async_loop(self):
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        import traceback
        error_log_file = open('THREAD_ERRORS.log', 'w', buffering=1)

        try:
            print("ASYNC THREAD: Starting collector", file=error_log_file)
            loop.run_until_complete(self.collector.start())
        except Exception as e:
            print(f"!!! EXCEPTION: {type(e).__name__} !!!", file=error_log_file)
            print(f"Error: {e}", file=error_log_file)
            traceback.print_exc(file=error_log_file)
            raise
        finally:
            error_log_file.close()

    def _set_sort_mode(self, mode: str):
        """Set the sort mode for Hyperliquid positions."""
        self.hl_sort_mode = mode
        self.sort_impact_btn.setChecked(mode == "impact")
        self.sort_distance_btn.setChecked(mode == "distance")
        # Immediately refresh the positions table
        hl_positions = load_hyperliquid_positions(limit=25, sort_by=self.hl_sort_mode)
        self.hl_positions_table.update_data(hl_positions)

    @Slot()
    def update_ui(self):
        try:
            snapshot: ObservationSnapshot = self.obs_system.query({'type': 'snapshot'})

            if snapshot.status == ObservationStatus.FAILED:
                raise SystemHaltedException("Status reports FAILED")

            # Update uptime
            uptime = int(time.time() - self.start_time)
            mins, secs = divmod(uptime, 60)
            self.uptime_label.setText(f"{mins}m {secs}s")

            # Update intervals
            intervals = snapshot.counters.intervals_processed or 0
            self.intervals_label.setText(f"| {intervals} int")

            # Update price ticker
            prices = aggregate_prices(snapshot)
            self.price_ticker.update_data(prices)

            # Update Hyperliquid positions (sort by impact or distance)
            hl_positions = load_hyperliquid_positions(limit=25, sort_by=self.hl_sort_mode)
            self.hl_positions_table.update_data(hl_positions)

            # Update cascade state
            cascade_state = aggregate_cascade_state(snapshot)
            self.cascade_widget.update_data(cascade_state)

            # Update order book depth
            depth = get_orderbook_depth(snapshot)
            self.orderbook_widget.update_data(depth)

            # Update primitives status
            prim_counts = {}
            for symbol in TOP_10_SYMBOLS:
                bundle = snapshot.primitives.get(symbol)
                prim_counts[symbol] = count_primitives(bundle)
            self.primitives_row.update_data(prim_counts)

            # Refresh trade history periodically (every 2 seconds)
            now = time.time()
            if now - self.last_trade_refresh > 2.0:
                self.trade_history.refresh_trades()
                self.last_trade_refresh = now

        except SystemHaltedException as e:
            self.red_screen.set_error(str(e))
            self.stack.setCurrentWidget(self.red_screen)
        except Exception as e:
            print(f"UI Error: {e}")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
