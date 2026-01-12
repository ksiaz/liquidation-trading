"""
Runtime Collector Service

The Driver of the Observation System.
Responsibility:
1. IO: Connect to Binance WebSockets.
2. Clock: Drive System Time (advance_time).
3. Ingest: Feed Raw Data to M5 (ingest_observation).
4. Loop: Asyncio Main Loop.
5. M6: Invoke PolicyAdapter and Execution (Phase 8)
"""

import asyncio
import json
import time
import logging
from typing import List, Dict, Callable
from collections import deque
from decimal import Decimal
import aiohttp

# Import sealed Observation System
from observation import ObservationSystem, ObservationSnapshot
from observation.types import ObservationStatus

# Import M6 components (Phase 8)
from runtime.policy_adapter import PolicyAdapter, AdapterConfig
from runtime.arbitration.arbitrator import MandateArbitrator
from runtime.executor.controller import ExecutionController
from runtime.risk.types import RiskConfig, AccountState

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

        # Phase 8: M6 Integration
        self.policy_adapter = PolicyAdapter(AdapterConfig())
        self.arbitrator = MandateArbitrator()
        self.executor = ExecutionController(RiskConfig())

        # Track mark prices for execution (estimated from trade stream)
        self._mark_prices: Dict[str, Decimal] = {}

        # Mock account state (in production, this comes from exchange API)
        self._account = AccountState(
            equity=Decimal("100000.0"),
            margin_available=Decimal("100000.0"),
            timestamp=time.time()
        )
        
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
        """Push Wall Clock time to System every 100ms and drive M6 execution cycle."""
        while self._running:
            current_time = time.time()
            try:
                # 1. Advance System Time
                self._obs.advance_time(current_time)

                # 2. Query Observation Snapshot
                snapshot = self._obs.query({'type': 'snapshot'})

                # 3. M6 Execution Cycle (only if observation is ACTIVE)
                if snapshot.status == ObservationStatus.ACTIVE:
                    self._execute_m6_cycle(snapshot, current_time)

            except Exception as e:
                # Fail silently per constitutional rules - log but don't halt
                self._logger.debug(f"Clock/Execution cycle error: {e}")
                pass

            await asyncio.sleep(0.1)

    def _execute_m6_cycle(self, snapshot: ObservationSnapshot, timestamp: float):
        """Execute one M6 cycle: Policies -> Arbitration -> Execution.

        Pure mechanical flow - no interpretation.

        Args:
            snapshot: Current observation snapshot
            timestamp: Current timestamp
        """
        try:
            # Collect mandates from all active symbols
            all_mandates = []

            for symbol in snapshot.symbols_active:
                # Invoke PolicyAdapter for this symbol
                mandates = self.policy_adapter.generate_mandates(
                    observation_snapshot=snapshot,
                    symbol=symbol,
                    timestamp=timestamp
                )
                all_mandates.extend(mandates)

            # Arbitrate conflicts (resolve to single action per symbol or HOLD)
            actions_by_symbol = self.arbitrator.arbitrate_all(all_mandates)

            # Execute actions
            mark_prices = self._mark_prices  # Pass current mark prices
            self.executor.process_cycle(
                mandates=all_mandates,
                account=self._account,
                mark_prices=mark_prices
            )

        except Exception as e:
            # Log but don't halt system
            self._logger.debug(f"M6 execution cycle error: {e}")
            pass

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
                                    # Track mark price from trades
                                    if 'p' in payload:
                                        self._mark_prices[symbol] = Decimal(str(payload['p']))
                                elif 'forceOrder' in stream:
                                    event_type = "LIQUIDATION"
                                    print(f"DEBUG: Liquidation received for {symbol}: {payload}")
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


    def get_execution_log(self):
        """Get execution trace from controller.

        Returns:
            List of execution records
        """
        return self.executor.get_execution_log()

    async def stop(self):
        self._running = False
