# HL Node Adapter Event Schema

**Version:** 1.1.0
**Status:** Frozen
**Last Updated:** 2026-02-01

---

## Overview

This document defines the canonical event types emitted by the HL Node Adapter.
All consumers must use these types. Direct node file access is prohibited.

## Versioning

Schema version follows semantic versioning:
- **Major**: Breaking changes (field removal, type change)
- **Minor**: Additive changes (new fields, new event types)
- **Patch**: Documentation/comment changes only

Clients should call the `Handshake` RPC before subscribing to verify compatibility.

---

## Event Types

### MarketPriceEvent

**Source:** `replica_cmds/SetGlobalAction`
**Frequency:** Every block (~500ms)
**Purpose:** Oracle and mark prices for all 228 assets

| Field | Type | Description |
|-------|------|-------------|
| `asset_id` | uint32 | Asset identifier (0=BTC, 1=ETH, etc.) |
| `symbol` | string | Human-readable symbol (BTC, ETH, SOL) |
| `oracle_price` | string | Oracle price - authoritative for liquidations |
| `mark_price` | string | Mark price - used for unrealized PnL |
| `timestamp_ns` | int64 | Block timestamp in nanoseconds |
| `block_height` | uint64 | Block height for ordering |

**Example:**
```json
{
  "asset_id": 0,
  "symbol": "BTC",
  "oracle_price": "78489",
  "mark_price": "78461",
  "timestamp_ns": 1769928481758734848,
  "block_height": 1165953505
}
```

---

### LiquidationEvent

**Source:** `node_fills/hourly/` (fills with `liquidation` field)
**Frequency:** Per liquidation trade
**Purpose:** Individual liquidation fill events

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | string | Asset symbol (BTC, ETH) |
| `side` | string | Liquidated position side: "LONG" or "SHORT" |
| `price` | string | Execution price |
| `size` | string | Position size liquidated |
| `value_usd` | string | USD notional value (price * size) |
| `liquidator_wallet` | string | Wallet that received the fill |
| `liquidated_wallet` | string | Wallet that was liquidated |
| `mark_price` | string | Mark price at liquidation time |
| `method` | string | "market" or "backstop" |
| `timestamp_ms` | int64 | Fill timestamp in milliseconds |
| `fill_id` | uint64 | Unique fill ID for deduplication |
| `tx_hash` | string | Transaction hash |

**Side interpretation:**
- `LONG` = Long position was liquidated (forced sell)
- `SHORT` = Short position was liquidated (forced buy)

**Example:**
```json
{
  "symbol": "BTC",
  "side": "SHORT",
  "price": "78215.0",
  "size": "0.48023",
  "value_usd": "37561.18945",
  "liquidator_wallet": "0xecb63caa...",
  "liquidated_wallet": "0x16edade1...",
  "mark_price": "78219.0",
  "method": "market",
  "timestamp_ms": 1769929473445,
  "fill_id": 565157617789996,
  "tx_hash": "0x3bb1e94c..."
}
```

---

### FillEvent

**Source:** `node_fills/hourly/` (all fills)  
**Frequency:** Per fill  
**Purpose:** Raw fill stream for organic vs liquidation flow separation

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | string | Asset symbol (BTC, ETH) |
| `side` | string | "B" (buy) or "A" (ask/sell) |
| `price` | string | Execution price |
| `size` | string | Fill size |
| `value_usd` | string | USD notional value (price * size) |
| `timestamp_ms` | int64 | Fill timestamp in milliseconds |
| `block_height` | uint64 | Block height (0 if unknown) |
| `wallet` | string | Wallet that received the fill |
| `is_liquidation` | bool | True if liquidation |
| `liquidated_wallet` | string | Wallet liquidated (empty if not) |
| `mark_price` | string | Mark price at liquidation (empty if not) |
| `method` | string | "market" or "backstop" (empty if not) |
| `fill_id` | uint64 | Unique fill ID |
| `tx_hash` | string | Transaction hash |

---

### SyncStatusEvent

**Source:** Adapter internal state
**Frequency:** Every 5 seconds or on status change
**Purpose:** Adapter health and sync status

| Field | Type | Description |
|-------|------|-------------|
| `status` | enum | UNKNOWN, HEALTHY, LAGGING, STALE, ERROR |
| `latest_block_height` | uint64 | Last processed block |
| `latest_block_time_ns` | int64 | Timestamp of last block |
| `blocks_behind` | uint32 | Estimated blocks behind tip |
| `current_session` | string | Current replica_cmds session |
| `prices_emitted` | uint64 | Total prices emitted |
| `liquidations_emitted` | uint64 | Total liquidations emitted |
| `last_error` | string | Error message if status=ERROR |
| `uptime_seconds` | uint64 | Adapter uptime |
| `timestamp_ns` | int64 | Status event timestamp |
| `schema_version` | SchemaVersion | Current schema version |

**Status values:**
| Status | Meaning |
|--------|---------|
| UNKNOWN | Initial state |
| HEALTHY | Reading data normally |
| LAGGING | Behind by > 10 blocks |
| STALE | No new data for > 30 seconds |
| ERROR | Read errors occurring |

---

## gRPC Service

### HLNodeAdapter

| RPC | Request | Response | Description |
|-----|---------|----------|-------------|
| `StreamPrices` | StreamRequest | stream MarketPriceEvent | Continuous price stream |
| `StreamLiquidations` | StreamRequest | stream LiquidationEvent | Continuous liquidation stream |
| `StreamFills` | StreamRequest | stream FillEvent | Continuous fill stream |
| `StreamStatus` | StreamRequest | stream SyncStatusEvent | Periodic status updates |
| `GetStatus` | Empty | SyncStatusEvent | Current status (unary) |
| `Handshake` | HandshakeRequest | HandshakeResponse | Version compatibility check |

### StreamRequest

| Field | Type | Description |
|-------|------|-------------|
| `symbols` | repeated string | Filter by symbols (empty = all) |
| `start_block` | uint64 | Start from block (0 = current) |

### HandshakeRequest

| Field | Type | Description |
|-------|------|-------------|
| `client_version` | SchemaVersion | Client's expected version |
| `client_id` | string | Client identifier for logging |

### HandshakeResponse

| Field | Type | Description |
|-------|------|-------------|
| `server_version` | SchemaVersion | Server's schema version |
| `compatible` | bool | Whether versions are compatible |
| `message` | string | Compatibility message |
| `server_uptime_seconds` | uint64 | Server uptime |

---

## Connection Example

```python
import grpc
import events_pb2
import events_pb2_grpc

# Connect to adapter
channel = grpc.insecure_channel('localhost:50051')
stub = events_pb2_grpc.HLNodeAdapterStub(channel)

# Handshake
response = stub.Handshake(events_pb2.HandshakeRequest(
    client_version=events_pb2.SchemaVersion(major=1, minor=1, patch=0),
    client_id="my-consumer"
))
if not response.compatible:
    raise Exception(f"Incompatible: {response.message}")

# Subscribe to prices
for price in stub.StreamPrices(events_pb2.StreamRequest(symbols=["BTC", "ETH"])):
    print(f"{price.symbol}: {price.oracle_price}")
```

---

## Changelog

### v1.1.0 (2026-02-04)
- Added FillEvent stream for organic vs liquidation separation

### v1.0.0 (2026-02-01)
- Initial schema release
- MarketPriceEvent, LiquidationEvent, SyncStatusEvent
- gRPC streaming service
- Handshake for version checking
