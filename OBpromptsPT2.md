CODING AGENT PROMPTS
REPLAY / SIMULATION INFRASTRUCTURE
==============================================

GLOBAL INSTRUCTION
------------------
This module provides infrastructure ONLY.
No strategy logic may be implemented here.
No indicators.
No shortcuts.

The goal is to make historical replay behave IDENTICALLY to live trading.

==============================================
PROMPT R1 — EVENT LOOP & CLOCK MODULE
==============================================

TASK:
Implement a deterministic event loop with explicit time control.

REQUIREMENTS:
- Maintain a monotonic simulation clock
- Advance time ONLY via replayed events
- No implicit time jumps
- No batching of events

IMPLEMENT:
- Event queue sorted by timestamp
- Single-threaded execution
- One event processed at a time

RULES:
- Strategy logic may only execute when an event is processed
- No polling
- No sleeping

OUTPUT:
- EventLoop object
- Current simulation timestamp

==============================================
PROMPT R2 — HISTORICAL DATA FEED ADAPTERS
==============================================

TASK:
Wrap historical data streams so they behave like live feeds.

STREAMS:
- Orderbook snapshots
- Trades
- Liquidations
- OHLCV candles

REQUIREMENTS:
- Each event must have a timestamp
- Events must be emitted strictly in time order
- Identical interface to live feed handlers

RULES:
- No peeking ahead
- No buffering future events
- Emit events one-by-one

OUTPUT:
- FeedAdapter classes per stream

==============================================
PROMPT R3 — FEED SYNCHRONIZATION LAYER
==============================================

TASK:
Ensure multi-stream synchronization.

IMPLEMENT:
- Time alignment checks
- Tolerance windows
- Explicit "data missing" flags

RULES:
- If any required stream missing at timestamp → evaluation skipped
- No interpolation
- No backfilling

OUTPUT:
- Synchronized market snapshot per timestamp

==============================================
PROMPT R4 — SYSTEM EXECUTION WRAPPER
==============================================

TASK:
Wrap the entire trading system so it can be called per timestamp.

REQUIREMENTS:
- One call per simulation timestamp
- Pass synchronized snapshot
- Capture decisions and state transitions

RULES:
- No internal loops over time
- No lookahead
- No aggregation inside wrapper

OUTPUT:
- execute(snapshot, timestamp) interface

==============================================
PROMPT R5 — REPLAY CONTROLLER
==============================================

TASK:
Implement a ReplayController to orchestrate replay runs.

REQUIREMENTS:
- Load historical datasets
- Initialize EventLoop
- Register feed adapters
- Run until data exhausted

RULES:
- Deterministic execution
- Reproducible results
- Identical behavior across runs

OUTPUT:
- run_replay(start_time, end_time) function

==============================================
FINAL INFRASTRUCTURE RULE
==============================================

Simulation infrastructure must be completed BEFORE
any simulation/replay test logic is implemented.

Once this infrastructure exists:
- ALL existing simulation test prompts must be runnable
- NO simulation test prompts may be modified

END OF REPLAY ENGINE PROMPTS
==============================================