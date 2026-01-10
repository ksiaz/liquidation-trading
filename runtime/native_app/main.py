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
        
    def run_async_loop(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.collector.start())
        
    @Slot()
    def update_ui(self):
        try:
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
