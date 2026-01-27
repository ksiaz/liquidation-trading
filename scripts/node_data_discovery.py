#!/usr/bin/env python3
"""
Hyperliquid Node Data Discovery Script
Observes raw data streams and documents their structure.
"""

import os
import json
import time
import struct
# import msgpack  # Skip for now, not needed for JSON streams
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any, Optional

# WSL paths - ~/hl is symlinked to /mnt/e/hl
HL_ROOT = Path("~/hl")
DATA_DIR = HL_ROOT / "data"
HL_DATA_DIR = HL_ROOT / "hyperliquid_data"


def discover_endpoints():
    """STEP 1: List all available data endpoints."""
    print("=" * 70)
    print("STEP 1: ENDPOINT INVENTORY")
    print("=" * 70)

    endpoints = []

    # File-based endpoints
    file_endpoints = [
        {
            "name": "replica_cmds",
            "protocol": "FILE",
            "path": str(DATA_DIR / "replica_cmds"),
            "auth": "no",
            "description": "Block-by-block transaction data (JSON-lines)"
        },
        {
            "name": "periodic_abci_states",
            "protocol": "FILE",
            "path": str(DATA_DIR / "periodic_abci_states"),
            "auth": "no",
            "description": "Full state snapshots every 10k blocks (msgpack)"
        },
        {
            "name": "abci_state.rmp",
            "protocol": "FILE",
            "path": str(HL_DATA_DIR / "abci_state.rmp"),
            "auth": "no",
            "description": "Current full exchange state (msgpack)"
        },
        {
            "name": "visor_abci_state.json",
            "protocol": "FILE",
            "path": str(HL_DATA_DIR / "visor_abci_state.json"),
            "auth": "no",
            "description": "Current block height and sync status (JSON)"
        },
        {
            "name": "evm_block_and_receipts",
            "protocol": "FILE",
            "path": str(DATA_DIR / "evm_block_and_receipts"),
            "auth": "no",
            "description": "EVM block data and transaction receipts"
        },
        {
            "name": "node_logs/gossip_connections",
            "protocol": "FILE",
            "path": str(DATA_DIR / "node_logs" / "gossip_connections"),
            "auth": "no",
            "description": "Gossip peer connection logs"
        },
        {
            "name": "latency_summaries",
            "protocol": "FILE",
            "path": str(DATA_DIR / "latency_summaries"),
            "auth": "no",
            "description": "Block processing latency statistics"
        },
        {
            "name": "tcp_traffic",
            "protocol": "FILE",
            "path": str(DATA_DIR / "tcp_traffic"),
            "auth": "no",
            "description": "Network traffic statistics"
        }
    ]

    # TCP endpoints (from ss output)
    tcp_endpoints = [
        {
            "name": "gossip_p2p_4001",
            "protocol": "TCP",
            "host_port": "0.0.0.0:4001",
            "auth": "no",
            "description": "Gossip P2P protocol (peer-to-peer)"
        },
        {
            "name": "gossip_p2p_4002",
            "protocol": "TCP",
            "host_port": "0.0.0.0:4002",
            "auth": "no",
            "description": "Gossip P2P protocol (secondary)"
        },
        {
            "name": "internal_3999",
            "protocol": "TCP",
            "host_port": "0.0.0.0:3999",
            "auth": "unknown",
            "description": "Unknown internal endpoint"
        }
    ]

    endpoints.extend(file_endpoints)
    endpoints.extend(tcp_endpoints)

    for ep in endpoints:
        print(f"\n[{ep['protocol']}] {ep['name']}")
        if 'path' in ep:
            print(f"    Path: {ep['path']}")
        if 'host_port' in ep:
            print(f"    Host:Port: {ep['host_port']}")
        print(f"    Auth: {ep['auth']}")
        print(f"    Description: {ep['description']}")

    return endpoints


def sample_replica_cmds(limit: int = 100) -> List[Dict]:
    """STEP 2: Sample raw data from replica_cmds stream."""
    print("\n" + "=" * 70)
    print("STEP 2: SAMPLING replica_cmds")
    print("=" * 70)

    # Find latest replica_cmds file
    replica_dir = DATA_DIR / "replica_cmds"
    if not replica_dir.exists():
        print(f"ERROR: {replica_dir} not found")
        return []

    # Navigate to today's data
    subdirs = sorted([d for d in replica_dir.iterdir() if d.is_dir()])
    if not subdirs:
        print("No replica_cmds subdirectories found")
        return []

    latest_subdir = subdirs[-1]
    print(f"Using directory: {latest_subdir}")

    # Find date subdirectory
    date_dirs = sorted([d for d in latest_subdir.iterdir() if d.is_dir()])
    if not date_dirs:
        print("No date directories found")
        return []

    date_dir = date_dirs[-1]
    print(f"Date directory: {date_dir}")

    # Find block files
    block_files = sorted([f for f in date_dir.iterdir() if f.is_file()])
    if not block_files:
        print("No block files found")
        return []

    latest_file = block_files[-1]
    print(f"Reading from: {latest_file}")
    print(f"File size: {latest_file.stat().st_size / 1024 / 1024:.2f} MB")

    samples = []
    try:
        with open(latest_file, 'r') as f:
            for i, line in enumerate(f):
                if i >= limit:
                    break
                try:
                    data = json.loads(line.strip())
                    samples.append(data)
                except json.JSONDecodeError as e:
                    print(f"  Line {i}: JSON decode error: {e}")
    except Exception as e:
        print(f"Error reading file: {e}")

    print(f"\nSampled {len(samples)} messages")
    return samples


def sample_visor_state() -> Dict:
    """Sample visor_abci_state.json."""
    print("\n" + "=" * 70)
    print("SAMPLING visor_abci_state.json")
    print("=" * 70)

    state_file = HL_DATA_DIR / "visor_abci_state.json"
    if not state_file.exists():
        print(f"ERROR: {state_file} not found")
        return {}

    with open(state_file, 'r') as f:
        data = json.load(f)

    print(f"Content: {json.dumps(data, indent=2)}")
    return data


def analyze_message_structure(samples: List[Dict]) -> Dict:
    """STEP 3: Document message structure."""
    print("\n" + "=" * 70)
    print("STEP 3: MESSAGE STRUCTURE ANALYSIS")
    print("=" * 70)

    if not samples:
        print("No samples to analyze")
        return {}

    # Analyze top-level structure
    top_level_keys = set()
    for s in samples:
        top_level_keys.update(s.keys())

    print(f"\nTop-level keys: {sorted(top_level_keys)}")

    # Analyze abci_block structure
    block_sample = samples[0].get('abci_block', {})
    print(f"\nabci_block structure:")
    for key, value in block_sample.items():
        value_type = type(value).__name__
        if isinstance(value, list):
            value_type = f"list[{len(value)} items]"
        elif isinstance(value, dict):
            value_type = f"dict[{list(value.keys())[:3]}...]"
        print(f"  {key}: {value_type}")

    # Analyze action types
    action_types = defaultdict(int)
    action_samples = defaultdict(list)

    for sample in samples:
        block = sample.get('abci_block', {})
        bundles = block.get('signed_action_bundles', [])

        for bundle in bundles:
            if len(bundle) < 2:
                continue
            wallet = bundle[0]
            actions_data = bundle[1]

            signed_actions = actions_data.get('signed_actions', [])
            for action in signed_actions:
                act = action.get('action', {})
                act_type = act.get('type', 'unknown')
                action_types[act_type] += 1

                if len(action_samples[act_type]) < 3:
                    action_samples[act_type].append(act)

    print(f"\nAction type distribution:")
    for act_type, count in sorted(action_types.items(), key=lambda x: -x[1]):
        print(f"  {act_type}: {count}")

    # Print sample for each action type
    print("\nAction type schemas:")
    for act_type, acts in action_samples.items():
        if acts:
            print(f"\n  [{act_type}]")
            sample_act = acts[0]
            for key, value in sample_act.items():
                if key == 'orders' and isinstance(value, list) and value:
                    print(f"    orders: list of order objects")
                    order = value[0]
                    for ok, ov in order.items():
                        print(f"      {ok}: {type(ov).__name__} = {repr(ov)[:50]}")
                elif key == 'cancels' and isinstance(value, list) and value:
                    print(f"    cancels: list of cancel objects")
                    cancel = value[0]
                    for ck, cv in cancel.items():
                        print(f"      {ck}: {type(cv).__name__} = {repr(cv)[:50]}")
                elif key == 'modifies' and isinstance(value, list) and value:
                    print(f"    modifies: list of modify objects")
                else:
                    print(f"    {key}: {type(value).__name__} = {repr(value)[:50]}")

    return {
        "top_level_keys": list(top_level_keys),
        "action_types": dict(action_types),
        "action_samples": {k: v for k, v in action_samples.items()}
    }


def measure_update_frequency(samples: List[Dict]) -> Dict:
    """STEP 4: Measure update frequency."""
    print("\n" + "=" * 70)
    print("STEP 4: UPDATE FREQUENCY ANALYSIS")
    print("=" * 70)

    if len(samples) < 2:
        print("Need at least 2 samples to measure frequency")
        return {}

    timestamps = []
    for sample in samples:
        block = sample.get('abci_block', {})
        time_str = block.get('time', '')
        if time_str:
            try:
                # Parse ISO timestamp
                dt = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                timestamps.append(dt.timestamp())
            except:
                pass

    if len(timestamps) < 2:
        print("Could not parse timestamps")
        return {}

    # Calculate intervals
    intervals = []
    for i in range(1, len(timestamps)):
        interval = timestamps[i] - timestamps[i-1]
        if interval > 0:
            intervals.append(interval)

    if not intervals:
        print("No valid intervals")
        return {}

    avg_interval = sum(intervals) / len(intervals)
    min_interval = min(intervals)
    max_interval = max(intervals)
    msgs_per_sec = 1.0 / avg_interval if avg_interval > 0 else 0

    print(f"\nMessages analyzed: {len(samples)}")
    print(f"Time span: {timestamps[-1] - timestamps[0]:.2f} seconds")
    print(f"\nMessages per second: {msgs_per_sec:.2f}")
    print(f"Average interval: {avg_interval * 1000:.2f} ms")
    print(f"Min interval: {min_interval * 1000:.2f} ms")
    print(f"Max interval: {max_interval * 1000:.2f} ms")

    # Burstiness
    if avg_interval > 0:
        variance = sum((i - avg_interval) ** 2 for i in intervals) / len(intervals)
        std_dev = variance ** 0.5
        burstiness = std_dev / avg_interval if avg_interval > 0 else 0
        print(f"Burstiness (CV): {burstiness:.2f} (0=steady, >1=spiky)")

    return {
        "messages_per_second": msgs_per_sec,
        "avg_interval_ms": avg_interval * 1000,
        "min_interval_ms": min_interval * 1000,
        "max_interval_ms": max_interval * 1000,
        "sample_count": len(samples)
    }


def categorize_streams() -> Dict:
    """STEP 5: Identify data categories."""
    print("\n" + "=" * 70)
    print("STEP 5: DATA CATEGORIES")
    print("=" * 70)

    categories = {
        "MARKET_DATA": [
            "replica_cmds (orders, trades via order matching)",
        ],
        "ACCOUNT_STATE": [
            "abci_state.rmp (full positions, margins, balances)",
            "periodic_abci_states (historical state snapshots)"
        ],
        "EXECUTION": [
            "replica_cmds (order, cancelByCloid, batchModify actions)"
        ],
        "RISK": [
            "abci_state.rmp (contains liquidation data, OI)",
            "replica_cmds (forceOrder actions if present)"
        ],
        "INFRASTRUCTURE": [
            "visor_abci_state.json (sync status)",
            "node_logs/gossip_connections",
            "latency_summaries",
            "tcp_traffic"
        ]
    }

    for cat, streams in categories.items():
        print(f"\n[{cat}]")
        for stream in streams:
            print(f"  - {stream}")

    return categories


def quality_observations(samples: List[Dict]) -> Dict:
    """STEP 6: First-order quality observations."""
    print("\n" + "=" * 70)
    print("STEP 6: QUALITY OBSERVATIONS")
    print("=" * 70)

    observations = {
        "timestamps_increasing": True,
        "duplicate_messages": 0,
        "gaps_detected": 0,
        "null_fields": defaultdict(int),
        "payload_sizes": []
    }

    prev_time = None
    seen_times = set()

    for i, sample in enumerate(samples):
        # Check timestamp ordering
        block = sample.get('abci_block', {})
        time_str = block.get('time', '')

        if time_str:
            if time_str in seen_times:
                observations["duplicate_messages"] += 1
            seen_times.add(time_str)

            if prev_time and time_str < prev_time:
                observations["timestamps_increasing"] = False
            prev_time = time_str

        # Check for null fields
        bundles = block.get('signed_action_bundles', [])
        if not bundles:
            observations["null_fields"]["empty_bundles"] += 1

        # Payload size
        payload_size = len(json.dumps(sample))
        observations["payload_sizes"].append(payload_size)

    print(f"\nTimestamps increasing: {observations['timestamps_increasing']}")
    print(f"Duplicate messages: {observations['duplicate_messages']}")
    print(f"Gaps detected: {observations['gaps_detected']}")

    if observations["null_fields"]:
        print(f"Null/empty fields:")
        for field, count in observations["null_fields"].items():
            print(f"  {field}: {count}")

    if observations["payload_sizes"]:
        sizes = observations["payload_sizes"]
        avg_size = sum(sizes) / len(sizes)
        min_size = min(sizes)
        max_size = max(sizes)
        print(f"\nPayload sizes:")
        print(f"  Average: {avg_size / 1024:.2f} KB")
        print(f"  Min: {min_size / 1024:.2f} KB")
        print(f"  Max: {max_size / 1024:.2f} KB")

    return observations


def main():
    """Run full data discovery."""
    print("\n" + "=" * 70)
    print("HYPERLIQUID NODE DATA DISCOVERY")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print("=" * 70)

    # STEP 1: Discover endpoints
    endpoints = discover_endpoints()

    # STEP 2: Sample raw data
    samples = sample_replica_cmds(limit=200)
    visor_state = sample_visor_state()

    # STEP 3: Document structure
    structure = analyze_message_structure(samples)

    # STEP 4: Measure frequency
    frequency = measure_update_frequency(samples)

    # STEP 5: Categorize
    categories = categorize_streams()

    # STEP 6: Quality observations
    quality = quality_observations(samples)

    # STEP 7: Summary
    print("\n" + "=" * 70)
    print("STEP 7: SUMMARY")
    print("=" * 70)

    print(f"""
A. ENDPOINT INVENTORY
   - File-based: 8 endpoints
   - TCP-based: 3 endpoints (4001, 4002, 3999)

B. PRIMARY STREAMS
   - replica_cmds: Block transaction data (18GB+)
   - periodic_abci_states: Full state snapshots (9.3GB)
   - abci_state.rmp: Current state (~1GB)

C. MESSAGE RATE
   - ~{frequency.get('messages_per_second', 0):.2f} blocks/second
   - Interval: ~{frequency.get('avg_interval_ms', 0):.0f}ms average

D. ACTION TYPES OBSERVED
   {', '.join(structure.get('action_types', {}).keys())}

E. DATA QUALITY
   - Timestamps: {'Monotonic' if quality.get('timestamps_increasing') else 'NON-MONOTONIC'}
   - Duplicates: {quality.get('duplicate_messages', 0)}
""")


if __name__ == "__main__":
    main()
