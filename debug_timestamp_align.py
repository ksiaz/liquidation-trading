"""Quick debug script to understand timestamp alignment"""
import time
from masterframe.data_ingestion import *

def create_test_orderbook(timestamp: float) -> OrderbookSnapshot:
    return OrderbookSnapshot(
        timestamp=timestamp,
        bids=((100.0, 1.0), (99.0, 2.0)),
        asks=((101.0, 1.0), (102.0, 2.0)),
        mid_price=100.5
    )

def create_test_trade(timestamp: float, is_buy: bool) -> AggressiveTrade:
    return AggressiveTrade(
        timestamp=timestamp,
        price=100.0,
        quantity=0.5,
        is_buyer_aggressor=is_buy
    )

def create_test_liquidation(timestamp: float) -> LiquidationEvent:
    return LiquidationEvent(
        timestamp=timestamp,
        symbol="BTCUSDT",
        side="SELL",
        quantity=0.1,
        price=100.0,
        value_usd=10.0
    )

def create_test_kline(timestamp: float, interval: str) -> Kline:
    return Kline(
        timestamp=timestamp,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1000.0,
        interval=interval
    )

sync = DataSynchronizer("BTCUSDT")
current_time = time.time()

# Warm up
for i in range(35):
    ts = current_time - 35 + i
    sync.push_orderbook(create_test_orderbook(ts))
    sync.push_trade(create_test_trade(ts, i % 2 == 0))
    sync.push_liquidation(create_test_liquidation(ts))
    sync.push_kline(create_test_kline(ts, '1m'))
    
    if i % 5 == 0:
        sync.push_kline(create_test_kline(ts, '5m'))
        print(f"Pushed 5m kline at i={i}, ts={ts}, current_time={current_time}, diff={current_time - ts}")

# Push final aligned
sync.push_orderbook(create_test_orderbook(current_time))
sync.push_kline(create_test_kline(current_time, '1m'))
sync.push_kline(create_test_kline(current_time, '5m'))

print(f"\nStatus: {sync.get_status()}")
print(f"\nCurrent time: {current_time}")
print(f"Latest OB: {sync.orderbook_buffer.get_latest().timestamp if sync.orderbook_buffer.get_latest() else None}")
print(f"Latest 1m: {sync.kline_buffer_1m.get_latest().timestamp if sync.kline_buffer_1m.get_latest() else None}")
print(f"Latest 5m: {sync.kline_buffer_5m.get_latest().timestamp if sync.kline_buffer_5m.get_latest() else None}")

snapshot = sync.get_aligned_snapshot(current_time)
print(f"\nSnapshot: {snapshot}")

if snapshot:
    print("SUCCESS")
else:
    print(f"FAILED - checking alignment:")
    ob_ts = sync.orderbook_buffer.get_latest().timestamp
    k1m_ts = sync.kline_buffer_1m.get_latest().timestamp
    k5m_ts = sync.kline_buffer_5m.get_latest().timestamp
    
    print(f"  OB diff: {abs(ob_ts - current_time)}")
    print(f"  1m diff: {abs(k1m_ts - current_time)}")
    print(f"  5m diff: {abs(k5m_ts - current_time)}")
    print(f"  Tolerance: {sync.TIMESTAMP_TOLERANCE_SECONDS}")
