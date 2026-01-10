"""
Antigravity Terminal - Desktop Application
Wraps the Flask dashboard in a native Windows window using PyWebView
"""
import webview
import threading
import time
from dashboard_server import app
from monitor import LiquidationMonitor
import logging

# Suppress Flask development server warnings
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

class DesktopApp:
    def __init__(self):
        self.server_thread = None
        self.monitor_thread = None
        self.port = 5000
        
    def start_server(self):
        """Start Flask server in background thread"""
        app.run(host='127.0.0.1', port=self.port, debug=False, use_reloader=False, threaded=True)
    
    def start_monitor(self):
        """Start liquidation monitor in background thread"""
        # Import dashboard queue
        from dashboard_server import liquidation_queue
        from datetime import datetime
        
        # Callback to push liquidations to dashboard
        def on_liquidation(event):
            liquidation_queue.put({
                'timestamp': event.get('timestamp', datetime.now().isoformat()),
                'symbol': event['symbol'],
                'side': event['side'],
                'value_usd': event['value_usd'],
                'price': event.get('avg_price', event.get('price', 0)),
                'quantity': event.get('quantity', 0)
            })
        
        # Pass setup_signals=False since we're in a background thread
        # Pass callback to receive live liquidations
        monitor = LiquidationMonitor(setup_signals=False, live_callback=on_liquidation)
        monitor.start()
    
    def launch(self):
        """Launch the desktop application"""
        # Start Flask server in background
        self.server_thread = threading.Thread(target=self.start_server, daemon=True)
        self.server_thread.start()
        
        # Start liquidation monitor in background
        self.monitor_thread = threading.Thread(target=self.start_monitor, daemon=True)
        self.monitor_thread.start()
        
        # Wait for server to start
        time.sleep(3)
        
        # Create native window using EdgeChromium (avoids pythonnet issues)
        window = webview.create_window(
            title='Antigravity Terminal',
            url=f'http://127.0.0.1:{self.port}',
            width=1400,
            height=900,
            resizable=True,
            fullscreen=False,
            min_size=(1200, 700),
            background_color='#050607',
            text_select=True
        )
        
        # Start the GUI event loop with edgechromium backend
        webview.start(gui='edgechromium', debug=False)

if __name__ == '__main__':
    print("=" * 60)
    print("ANTIGRAVITY TERMINAL - DESKTOP APP")
    print("=" * 60)
    print("\nStarting application...")
    print("Please wait while the terminal loads...\n")
    
    app_instance = DesktopApp()
    app_instance.launch()
