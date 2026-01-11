"""
Runtime Collector Service

The Driver of the Observation System.
Responsibility:
1. IO: Connect to Binance WebSockets.
2. Clock: Drive System Time (advance_time).
3. Ingest: Feed Raw Data to M5 (ingest_observation).
4. Loop: Asyncio Main Loop.
"""

import asyncio
import json
import time
import logging
from typing import List, Dict, Callable
from collections import deque
import aiohttp

# Import sealed Observation System
from observation import ObservationSystem, ObservationSnapshot

# Constants
TOP_10_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", 
    "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT", 
    "TRXUSDT", "DOTUSDT"
]

class CollectorService:
    def __init__(self, observation_system: ObservationSystem):
        self._obs = observation_system
        self._running = False
        self._logger = logging.getLogger("CollectorService")
        
    async def start(self):
        """Start all collectors."""
        self._running = True
        
        # 1. Start Clock Driver (Heartbeat)
        asyncio.create_task(self._drive_clock())
        
        # 2. Start WebSocket Consumers (Simulated for now, or ported real logic)
        # For Remediation Phase, we will implement the SHELL of the collectors 
        # that drives the real M5, effectively verifying integration.
        # Ideally we port the actual binance connection logic here.
        # Given the task complexity, I will port the structure and stub the actual socket for safety,
        # or reuse the logic if I can import 'scripts' (but I shouldn't).
        # I will re-implement the basic websocket client here.
        
        await self._run_binance_stream()

    async def _drive_clock(self):
        """Push Wall Clock time to System every 100ms."""
        while self._running:
            current_time = time.time()
            try:
                self._obs.advance_time(current_time)
            except Exception as e:
                print(f"Clock Driver Error: {e}")
                pass
            
            await asyncio.sleep(0.1)

    async def _run_binance_stream(self):
        """Connect to Binance Filtered Stream."""
        import websockets
        
        streams = [
            f"{s.lower()}@aggTrade" for s in TOP_10_SYMBOLS
        ] + [
            f"{s.lower()}@forceOrder" for s in TOP_10_SYMBOLS
        ] + [
            f"{s.lower()}@depth@100ms" for s in TOP_10_SYMBOLS
        ]
        
        stream_url = f"wss://fstream.binance.com/stream?streams={'/'.join(streams)}"
        
        async with aiohttp.ClientSession() as session:
            while self._running:
                try:
                    import websockets
                    async with websockets.connect(stream_url) as ws:
                        print("Connected to Binance Stream")
                        while self._running:
                            try:
                                msg = await ws.recv()
                                data = json.loads(msg)
                                stream = data['stream']
                                payload = data['data']
                                
                                # Parse Symbol & Type
                                symbol = stream.split('@')[0].upper()
                                event_type = "UNKNOWN"

                                if 'aggTrade' in stream:
                                    event_type = "TRADE"
                                elif 'forceOrder' in stream:
                                    event_type = "LIQUIDATION"
                                elif 'depth' in stream:
                                    event_type = "DEPTH"
                                    
                                # TIMESTAMP EXTRACTION
                                ts = time.time()
                                if 'T' in payload:
                                    ts = int(payload['T']) / 1000.0
                                elif 'E' in payload:
                                    ts = int(payload['E']) / 1000.0
                                    
                                # INGEST
                                self._obs.ingest_observation(ts, symbol, event_type, payload)
                                
                            except Exception as e:
                                print(f"Processing Error: {e}")
                                await asyncio.sleep(1)
                                
                except Exception as e:
                    print(f"Connection Failed: {e}. Retrying in 5s...")
                    await asyncio.sleep(5)
             
    async def stop(self):
        self._running = False
