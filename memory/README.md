# Liquidity Memory Layer

**Phase:** M  
**Purpose:** Observational memory system for market microstructure  
**Status:** In development

---

## Overview

The Liquidity Memory Layer builds probabilistic memory of price levels that have historically mattered in the market. It is:

- **Observational only** - No signal generation
- **Strategy-agnostic** - No SLBRS/EFFCS logic
- **Temporal** - Memory strengthens with interaction, decays with time
- **Deterministic** - Reproducible on replay

---

## Core Abstraction: LiquidityMemoryNode (LMN)

A `LiquidityMemoryNode` represents a price band with historical significance.

### Node Lifecycle

1. **Creation** - Created from evidence (persistence, execution, liquidation, rejection)
2. **Strengthening** - Gains strength from repeated interactions
3. **Decay** - Loses strength over time without interaction
4. **Archival** - Becomes inactive when strength drops below threshold

### Fields

| Field | Type | Purpose |
|:------|:-----|:--------|
| `id` | str | Unique identifier |
| `price_center` | float | Center of price band |
| `price_band` | float | Width of band (absolute) |
| `side` | Literal | bid/ask/both |
| `first_seen_ts` | float | Creation timestamp |
| `last_interaction_ts` | float | Most recent interaction |
| `strength` | float | Current memory strength [0,1] |
| `confidence` | float | Relevance confidence [0,1] |
| `creation_reason` | Enum | Why node was created |
| `decay_rate` | float | Strength decay per second |
| `active` | bool | Whether node is active |

---

## Design Principles

### 1. Evidence-Based Creation

Nodes are created only when empirical evidence suggests a price level matters:
- Orderbook zones that persist
- Liquidity that gets executed
- Liquidation clustering
- Price rejection patterns

### 2. Temporal Memory

- **Strength** increases with interactions
- **Decay** reduces strength over time
- **Archival** when strength < 0.01

### 3. No Forward-Looking

- Uses only historical + current data
- Deterministic on replay
- No predictions or forecasts

### 4. Strategy Independence

- No SLBRS-specific fields
- No EFFCS-specific fields
- No absorption/expansion classification
- Pure observation of market structure

---

## Usage (Future)

The memory layer will be consumed by strategies, but does NOT emit signals itself.

Example (conceptual):
```python
# Strategy can query memory
memory_layer = LiquidityMemoryLayer()
strong_nodes = memory_layer.get_active_nodes(min_strength=0.7)

# But memory layer does NOT tell strategy what to do
# Strategy makes its own decisions based on memory state
```

---

## Implementation Status

**M1: Data Model** ✅ COMPLETE
- [x] M1.1: LiquidityMemoryNode dataclass

**M2: Memory Manager** 🔄 NEXT
- [ ] M2.1: Node creation logic
- [ ] M2.2: Decay system
- [ ] M2.3: Query interface

**M3: Evidence Detection** ⏸️ PLANNED
- [ ] M3.1: Orderbook persistence
- [ ] M3.2: Executed liquidity
- [ ] M3.3: Liquidation interaction
- [ ] M3.4: Price rejection

---

**NO SIGNALS. NO STRATEGY LOGIC. OBSERVATION ONLY.**
