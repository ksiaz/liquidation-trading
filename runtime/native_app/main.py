"""
New Peak Pressure Detector App (Remediated)

Architecture:
1. Initializes ObservationSystem (M1-M5 Sealed).
2. Starts CollectorService (Runtime Driver).
3. Polls ObservationSystem for State.
4. Renders UI or RED SCREEN OF DEATH.
"""

import sys
import os
import asyncio
import threading
import signal
import json
import argparse
from datetime import datetime
import time
from PySide6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget, 
                              QLabel, QHBoxLayout, QFrame, QStackedWidget)
from PySide6.QtCore import QTimer, Slot, Qt

# Fix path to include project root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from observation import ObservationSystem, ObservationSnapshot
from observation.types import ObservationStatus, SystemHaltedException
from runtime.collector.service import CollectorService, TOP_10_SYMBOLS

class RedScreenOfDeath(QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: #440000; color: #ff3333;")
        layout = QVBoxLayout()
        self.detail = QLabel("")
        self.detail.setStyleSheet("font-size: 16px; color: white;")
        layout.addWidget(self.detail)
        layout.addStretch()
        self.setLayout(layout)
        
    def set_error(self, message):
        self.detail.setText(f"{message}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Observation Viewer")
        self.resize(1200, 800)
        
        # 1. Initialize Core Systems
        self.obs_system = ObservationSystem(TOP_10_SYMBOLS)
        self.collector = CollectorService(self.obs_system)
        
        # 2. UI Setup
        self.stack = QStackedWidget()
        self.red_screen = RedScreenOfDeath()
        
        # Main Dashboard (Placeholder for migrated UI components)
        self.dashboard = QWidget()
        dash_layout = QVBoxLayout()
        self.status_label = QLabel("")
        dash_layout.addWidget(self.status_label)
        self.dashboard.setLayout(dash_layout)
        
        self.stack.addWidget(self.dashboard)
        self.stack.addWidget(self.red_screen)
        
        self.setCentralWidget(self.stack)
        
        # 3. Start Update Loop (250ms)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        self.timer.start(250)
        
        # 4. Start Collector Thread
        self.loop_thread = threading.Thread(target=self.run_async_loop, daemon=True)
        self.loop_thread.start()
        
    def closeEvent(self, event):
        """Handle window close event for graceful shutdown."""
        print("\nShutdown initiated via Window Close...")
        self.shutdown()
        event.accept()

    def shutdown(self):
        """Execute graceful shutdown sequence."""
        if hasattr(self, 'collector'):
            print("Stopping collector...")
            # Simple flag flip, async loop will exit
            self.collector._running = False
            
            # Export Trace
            self.export_trace()
            
    def export_trace(self):
        """Export execution trace to JSON."""
        try:
            log = self.collector.executor.get_execution_log()
            
            # Convert to dictionary format
            records = [record.to_log_dict() for record in log]
            
            trace_data = {
                "timestamp": time.time(),
                "records": records,
                "count": len(records)
            }
            
            # Save to file
            filename = "trace_latest.json"
            with open(filename, 'w') as f:
                json.dump(trace_data, f, indent=2)
                
            print(f"Trace exported to {filename} ({len(records)} records)")
            
        except Exception as e:
            print(f"Failed to export trace: {e}")
        
    def run_async_loop(self):
        # Fix for Windows event loop with aiodns
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.collector.start())
        
    @Slot()
    def update_ui(self):
        try:
            import time
            snapshot: ObservationSnapshot = self.obs_system.query({'type': 'snapshot'})

            if snapshot.status == ObservationStatus.FAILED:
                raise SystemHaltedException("Status reports FAILED")

            if snapshot.status == ObservationStatus.UNINITIALIZED:
                self.status_label.setText(
                    f"UNINITIALIZED\n"
                    f"Time: {snapshot.timestamp:.2f}\n"
                    f"Symbols: {len(snapshot.symbols_active)}"
                )
                self.dashboard.setStyleSheet("background-color: #222244;")

            elif snapshot.status == ObservationStatus.ACTIVE:
                # Get M2 metrics
                m2_metrics = self.obs_system._m2_store.get_metrics()
                
                # Calculate primitive counts per symbol and overall
                total_primitives = 0
                primitive_breakdown = {}
                
                for symbol, bundle in snapshot.primitives.items():
                    count = 0
                    if bundle.zone_penetration is not None: count += 1
                    if bundle.displacement_origin_anchor is not None: count += 1
                    if bundle.price_traversal_velocity is not None: count += 1
                    if bundle.traversal_compactness is not None: count += 1
                    if bundle.price_acceptance_ratio is not None: count += 1
                    if bundle.central_tendency_deviation is not None: count += 1
                    if bundle.structural_absence_duration is not None: count += 1
                    if bundle.structural_persistence_duration is not None: count += 1
                    if bundle.traversal_void_span is not None: count += 1
                    if bundle.event_non_occurrence_counter is not None: count += 1
                    if bundle.resting_size is not None: count += 1
                    if bundle.order_consumption is not None: count += 1
                    if bundle.absorption_event is not None: count += 1
                    if bundle.refill_event is not None: count += 1
                    if bundle.liquidation_density is not None: count += 1
                    if bundle.directional_continuity is not None: count += 1
                    if bundle.trade_burst is not None: count += 1
                    
                    if count > 0:
                        primitive_breakdown[symbol] = count
                    total_primitives += count

                # Get execution stats
                exec_log = self.collector.executor.get_execution_log()
                mandate_count = len(exec_log)
                
                # Build comprehensive display
                display_text = (
                    f"🟢 SYSTEM ACTIVE\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"⏱️  System Time: {datetime.fromtimestamp(snapshot.timestamp).strftime('%H:%M:%S')}\n"
                    f"📊 Symbols Active: {len(snapshot.symbols_active)}\n\n"
                    
                    f"━━━ M2 MEMORY NODES ━━━\n"
                    f"  Total Created: {m2_metrics['total_nodes_created']}\n"
                    f"  🟢 Active: {m2_metrics['active_nodes']}\n"
                    f"  ⚪ Dormant: {m2_metrics['dormant_nodes']}\n"
                    f"  📦 Archived: {m2_metrics['archived_nodes']}\n"
                    f"  Interactions: {m2_metrics['total_interactions']}\n\n"
                    
                    f"━━━ M4 PRIMITIVES ━━━\n"
                    f"  Total Computing: {total_primitives} / {len(snapshot.primitives) * 17}\n"
                )
                
                if primitive_breakdown:
                    display_text += "  By Symbol:\n"
                    for sym, cnt in sorted(primitive_breakdown.items(), key=lambda x: x[1], reverse=True):
                        display_text += f"    • {sym}: {cnt}/17\n"
                else:
                    display_text += "  [Awaiting M2 data]\n"
                
                display_text += (
                    f"\n━━━ M6 EXECUTION ━━━\n"
                    f"  Mandates Processed: {mandate_count}\n"
                    f"  Policy Adapter: ACTIVE\n"
                    f"  Arbitrator: READY\n"
                    f"  Controller: OPERATIONAL\n\n"
                )
                
                # Add critical primitive highlights
                for symbol, bundle in snapshot.primitives.items():
                    if bundle.price_acceptance_ratio is not None or bundle.structural_persistence_duration is not None:
                        display_text += f"⭐ {symbol} - Critical primitives active\n"
                
                self.status_label.setText(display_text)
                self.status_label.setStyleSheet("font-family: 'Consolas', 'Courier New', monospace; font-size: 11pt; color: #00ff00;")
                self.dashboard.setStyleSheet("background-color: #001100;")

        except SystemHaltedException as e:
            self.red_screen.set_error(str(e))
            self.stack.setCurrentWidget(self.red_screen)
        except Exception as e:
            print(f"UI Error: {e}")

def main():
    # Parse Arguments
    parser = argparse.ArgumentParser(description='Liquidation Trading Runtime')
    parser.add_argument('--export-trace', action='store_true', help='Export execution trace on exit')
    args = parser.parse_args()

    app = QApplication(sys.argv)
    window = MainWindow()
    
    # Store args in window for access during shutdown
    window.args = args
    
    # Signal Handling for Console (Ctrl+C)
    # We need a timer to let the python interpretter run to catch signals
    signal.signal(signal.SIGINT, lambda sig, frame: window.close())
    
    # Timer hack to allow Ctrl+C to work in PySide6 app
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)
    
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
