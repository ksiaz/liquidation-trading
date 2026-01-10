"""
Replay Controller

Master orchestrator for historical replay runs.

INVARIANTS:
- Deterministic execution
- Reproducible results
- Identical behavior across runs

GOAL:
Complete orchestration of replay infrastructure (R1-R5).
"""

from typing import List, Dict, Any, Optional
from masterframe.data_ingestion import (
    OrderbookEvent, TradeEvent,
    LiquidationEvent, CandleEvent, BookTickerEvent
)
from .event_loop import EventLoop, Event
from .feed_adapters import (
    OrderbookFeedAdapter, TradeFeedAdapter,
    LiquidationFeedAdapter, KlineFeedAdapter,
    BookTickerFeedAdapter,
    schedule_all_events
)
from .synchronizer import ReplayDataSync
from .system_wrapper import ReplaySystemWrapper


class ReplayController:
    """
    Master controller for historical replay.
    
    RULE: Deterministic execution.
    RULE: Reproducible results.
    RULE: Orchestrates all replay components.
    
    This is the final R5 component that ties together:
    - R1: EventLoop (time control)
    - R2: FeedAdapters (data streaming)
    - R3: ReplayDataSync (synchronization)
    - R4: ReplaySystemWrapper (system execution)
    """
    
    def __init__(self, symbol: str = "BTCUSDT"):
        """
        Initialize replay controller.
        
        Args:
            symbol: Trading symbol
        """
        self.symbol = symbol
        self.results: List[Dict[str, Any]] = []
    
    def run_replay(
        self,
        orderbooks: List[OrderbookEvent],
        trades: List[TradeEvent],
        liquidations: List[LiquidationEvent],
        klines_1m: List[CandleEvent],
        klines_5m: List[CandleEvent],
        booktickers: List[BookTickerEvent],
        start_time: Optional[float] = None,
        end_time: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Run complete replay with historical data.
        
        RULE: All data must be provided.
        RULE: Execution is deterministic.
        RULE: Results are reproducible.
        
        Args:
            orderbooks: Historical orderbook snapshots
            trades: Historical trades
            liquidations: Historical liquidations
            klines_1m: 1m klines
            klines_5m: 5m klines
            start_time: Optional start timestamp (defaults to first orderbook)
            end_time: Optional end timestamp (unused, for future filtering)
            
        Returns:
            Summary dict with:
            - symbol: Trading symbol
            - events_processed: Total events processed
            - executions: Number of system executions
            - results: List of all execution results
            - final_time: Final simulation timestamp
        """
        # Clear previous results
        self.results = []
        
        # 1. CREATE FEED ADAPTERS
        adapters = [
            OrderbookFeedAdapter(orderbooks),
            TradeFeedAdapter(trades),
            LiquidationFeedAdapter(liquidations),
            KlineFeedAdapter(klines_1m, '1m'),
            KlineFeedAdapter(klines_5m, '5m'),
            BookTickerFeedAdapter(booktickers),
        ]
        
        # 2. INITIALIZE COMPONENTS
        initial_time = start_time if start_time else orderbooks[0].timestamp
        loop = EventLoop(start_time=initial_time)
        sync = ReplayDataSync(self.symbol)
        wrapper = ReplaySystemWrapper()
        
        # 3. REGISTER EVENT HANDLER
        def handle_event(event: Event):
            """Process each event through sync → wrapper."""
            # Update synchronizer
            sync.handle_event(event)
            
            # Get aligned snapshot
            snapshot = sync.get_snapshot(event.timestamp)
            
            if snapshot is not None:
                # Get all klines for ATR calculation
                klines_1m_all = sync.get_all_klines_1m()
                klines_5m_all = sync.get_all_klines_5m()
                
                # Execute system
                result = wrapper.execute(
                    snapshot, 
                    event.timestamp,
                    klines_1m_all,
                    klines_5m_all
                )
                self.results.append(result)
        
        # Register handler for all event types
        for event_type in ['orderbook', 'trade', 'liquidation', 'kline_1m', 'kline_5m', 'bookticker']:
            loop.register_handler(event_type, handle_event)
        
        # 4. SCHEDULE ALL EVENTS
        events_scheduled = schedule_all_events(adapters, loop)
        
        # 5. RUN REPLAY
        loop.run()
        
        # 6. RETURN SUMMARY
        return {
            'symbol': self.symbol,
            'events_processed': loop.get_events_processed(),
            'events_scheduled': events_scheduled,
            'executions': len(self.results),
            'results': self.results,
            'final_time': loop.get_current_time(),
        }
    
    def get_results(self) -> List[Dict[str, Any]]:
        """
        Get all execution results.
        
        Returns:
            List of execution result dicts
        """
        return self.results
    
    def get_execution_count(self) -> int:
        """Get number of executions."""
        return len(self.results)
    
    def __repr__(self) -> str:
        return f"ReplayController(symbol={self.symbol}, executions={len(self.results)})"
