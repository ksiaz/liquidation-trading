# MEMORY TOPOLOGY LAYER — Example Outputs

## Overview

Topology Layer describes **RELATIONSHIPS**, not meaning.  
All outputs are **geometric facts**, no interpretive labels.

---

## 1. Neighborhood Density

**Input:**
- Center price: $2.05
- Radius: ±$0.01

**Output:**
```python
{
  'neighbor_count': 7,
  'density': 350.00,  # nodes per $0.01
  'strength_weighted_density': 168.28,
  'avg_neighbor_strength': 0.4808
}
```

**Interpretation:** NONE - Pure counts and ratios

---

## 2. Clustering (Price Proximity)

**Parameters:**
- Price threshold: $0.01
- Min cluster size: 2 nodes

**Output:**
```python
[
  TopologyCluster(
    cluster_id='cluster_0',
    price_center=2.0505,
    price_range=0.0210,
    node_count=8,
    total_interactions=0,
    total_volume=0.00,
    avg_strength=0.4560
  ),
  TopologyCluster(
    cluster_id='cluster_1',
    price_center=2.1475,
    price_range=0.0150,
    node_count=4,
    total_interactions=0,
    total_volume=0.00,
    avg_strength=0.6799
  )
]
```

**Cluster IDs:** Neutral ('cluster_N'), NOT semantic ('support_zone')

---

## 3. Gap Detection

**Parameters:**
- Price range: $2.00 - $2.30
- Gap threshold: >$0.02

**Output:**
```python
[
  {'gap_start': 2.0000, 'gap_end': 2.0400, 'gap_width': 0.0400},
  {'gap_start': 2.0610, 'gap_end': 2.1400, 'gap_width': 0.0790},
  {'gap_start': 2.1550, 'gap_end': 2.2400, 'gap_width': 0.0850},
  {'gap_start': 2.2550, 'gap_end': 2.3000, 'gap_width': 0.0450}
]
```

**Each gap:** Start, end, width (factual measurements only)

---

## Prohibition Compliance

**Forbidden terms checked:** 16  
**Topology outputs checked:** 10  

**Result:** ✅ **NO VIOLATIONS**

Verified absence of:
- support, resistance
- bullish, bearish
- trend, bias
- breakout, reversal
- buy_zone, sell_zone

---

## Data Structures

All structures contain **ONLY factual measurements:**

**Dict fields:** `neighbor_count`, `density`, `gap_width`  
**NOT:** `confidence_level`, `breakout_probability`

**Cluster IDs:** `'cluster_0'`, `'cluster_1'`  
**NOT:** `'support_zone'`, `'resistance_area'`

---

## Usage Example

```python
from memory import ContinuityMemoryStore

store = ContinuityMemoryStore()

# Get neighborhood density (factual)
density = store.get_node_density(price_range=(2.04, 2.06))
print(f"Nodes per unit: {density['density']}")

# Get clusters (geometric grouping)
clusters = store.get_topological_clusters(price_threshold=0.01)
print(f"Found {len(clusters)} clusters")

# Get gaps (sparse regions)
gaps = store.topology.identify_gaps(nodes, (2.00, 2.30), 0.02)
print(f"Gap width: ${gaps[0]['gap_width']}")
```

**All outputs:** Counts, ratios, measurements - NO semantics

---

## Key Principles

✓ **Topology = Relationships:** Spatial, temporal, statistical  
✓ **No semantic labels:** Neutral IDs only  
✓ **No directional bias:** Pure geometry  
✓ **No interpretation:** Facts, not predictions  

**Topology describes structure. It does not interpret meaning.**
