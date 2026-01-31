#!/usr/bin/env python3
"""
Diagnostic script to verify mandate flow end-to-end.

Instruments:
1. Mandate generation (policies)
2. Arbitration (conflict resolution)
3. Execution (state machine transitions)
4. Ghost trades (paper trading)

Run: python scripts/diagnostic_mandate_flow.py
"""

import os
import sys
import asyncio
import time

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Enable node mode and diagnostics
os.environ['USE_HL_NODE'] = 'true'
os.environ['DEBUG_EXIT'] = 'true'  # Enable exit debugging in service.py

from observation.governance import ObservationSystem
from runtime.collector.service import CollectorService
from runtime.arbitration.types import MandateType, ActionType
from runtime.position.types import PositionState

# Track flow statistics
stats = {
    'cycles': 0,
    'mandates_generated': 0,
    'mandates_by_type': {},
    'arbitration_results': 0,
    'executions': 0,
    'executions_by_type': {},
    'ghost_entries': 0,
    'ghost_exits': 0,
    'positions_open': set(),
}


def patch_for_diagnostics(service):
    """Patch service methods to add diagnostic output."""

    # Store original methods
    original_execute_m6 = service._execute_m6_cycle
    original_process_ghost = service._process_ghost_trades

    def diagnostic_execute_m6(snapshot, timestamp):
        """Wrapped M6 cycle with diagnostics."""
        stats['cycles'] += 1

        # Call original
        original_execute_m6(snapshot, timestamp)

        # Log cycle summary every 50 cycles
        if stats['cycles'] % 50 == 0:
            print(f"\n{'='*60}")
            print(f"DIAGNOSTIC SUMMARY (cycle {stats['cycles']})")
            print(f"{'='*60}")
            print(f"Mandates generated: {stats['mandates_generated']}")
            print(f"  By type: {stats['mandates_by_type']}")
            print(f"Executions: {stats['executions']}")
            print(f"  By type: {stats['executions_by_type']}")
            print(f"Ghost trades: entries={stats['ghost_entries']}, exits={stats['ghost_exits']}")
            print(f"Open positions: {stats['positions_open']}")
            print(f"{'='*60}\n")

    def diagnostic_process_ghost():
        """Wrapped ghost trade processing with diagnostics."""
        # Get execution log before
        log_before = len(service.executor.get_execution_log())

        # Call original
        original_process_ghost()

        # Check what was processed
        log_after = service.executor.get_execution_log()
        new_results = log_after[log_before:]

        for result in new_results:
            stats['executions'] += 1
            action_name = result.action.name if hasattr(result.action, 'name') else str(result.action)
            stats['executions_by_type'][action_name] = stats['executions_by_type'].get(action_name, 0) + 1

            if result.success:
                if action_name == 'ENTRY':
                    stats['positions_open'].add(result.symbol)
                elif action_name == 'EXIT':
                    stats['positions_open'].discard(result.symbol)

                print(f"  [EXEC] {result.symbol}: {action_name} "
                      f"{result.state_before.name if result.state_before else '?'} -> "
                      f"{result.state_after.name if result.state_after else '?'} "
                      f"{'✓' if result.success else '✗'}")

    # Patch the service
    service._execute_m6_cycle = diagnostic_execute_m6
    service._process_ghost_trades = diagnostic_process_ghost

    # Also patch policy adapter to count mandates
    original_generate = service.policy_adapter.generate_mandates

    def diagnostic_generate(*args, **kwargs):
        mandates = original_generate(*args, **kwargs)
        if mandates:
            stats['mandates_generated'] += len(mandates)
            for m in mandates:
                type_name = m.type.name if hasattr(m.type, 'name') else str(m.type)
                stats['mandates_by_type'][type_name] = stats['mandates_by_type'].get(type_name, 0) + 1
        return mandates

    service.policy_adapter.generate_mandates = diagnostic_generate


async def run_diagnostic(duration_sec=120):
    """Run diagnostic for specified duration."""
    print("=" * 60)
    print("MANDATE FLOW DIAGNOSTIC")
    print("=" * 60)
    print(f"Duration: {duration_sec} seconds")
    print(f"Node mode: {os.environ.get('USE_HL_NODE')}")
    print("=" * 60)
    print()

    # Reduced symbol set for faster testing
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'HYPEUSDT']

    # Create observation system
    print("Creating ObservationSystem...")
    obs = ObservationSystem(allowed_symbols=symbols)

    # Create collector service
    print("Creating CollectorService...")
    service = CollectorService(obs, warmup_duration_sec=5)  # Short warmup

    # Apply diagnostic patches
    print("Applying diagnostic instrumentation...")
    patch_for_diagnostics(service)

    print(f"Node mode active: {service._use_node_mode}")
    print(f"HL enabled: {service._hyperliquid_enabled}")
    print()

    # Start service
    print("Starting service...")
    service_task = asyncio.create_task(service.start())

    # Run for duration
    start = time.time()
    try:
        while time.time() - start < duration_sec:
            await asyncio.sleep(10)
            elapsed = time.time() - start
            print(f"\n[{elapsed:.0f}s] Cycles: {stats['cycles']}, "
                  f"Mandates: {stats['mandates_generated']}, "
                  f"Executions: {stats['executions']}")

            # Show position states
            for symbol in symbols:
                pos = service.executor.state_machine.get_position(symbol)
                if pos.state != PositionState.FLAT:
                    print(f"  Position: {symbol} = {pos.state.name} "
                          f"(dir={pos.direction}, qty={pos.quantity})")

    except asyncio.CancelledError:
        pass
    finally:
        print("\n" + "=" * 60)
        print("FINAL DIAGNOSTIC REPORT")
        print("=" * 60)
        print(f"Total cycles: {stats['cycles']}")
        print(f"Total mandates: {stats['mandates_generated']}")
        print(f"  By type: {stats['mandates_by_type']}")
        print(f"Total executions: {stats['executions']}")
        print(f"  By type: {stats['executions_by_type']}")
        print(f"Ghost entries: {stats['ghost_entries']}")
        print(f"Ghost exits: {stats['ghost_exits']}")
        print(f"Final open positions: {stats['positions_open']}")
        print()

        # Show final position states
        print("Position States:")
        for symbol in symbols:
            pos = service.executor.state_machine.get_position(symbol)
            print(f"  {symbol}: {pos.state.name}")

        print("=" * 60)

        # Cleanup
        service._running = False
        service_task.cancel()
        try:
            await service_task
        except asyncio.CancelledError:
            pass


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--duration', type=int, default=120, help='Duration in seconds')
    args = parser.parse_args()

    try:
        asyncio.run(run_diagnostic(args.duration))
    except KeyboardInterrupt:
        print("\nInterrupted.")
