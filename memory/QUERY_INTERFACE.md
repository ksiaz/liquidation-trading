# MEMORY QUERY INTERFACE — API Reference

## Overview

Read-only query interface for M2 memory layer.  
All methods return RAW data structures - NO signals, NO actions.

---

## Method Signatures

### 1. get_active_nodes()

```python
def get_active_nodes(
    current_price: Optional[float] = None,
    radius: Optional[float] = None,
    min_strength: float = 0.0
) -> List[EnrichedLiquidityMemoryNode]:
```

**Returns:** Active nodes (sorted by strength DESC)

**Example Response:**
```python
[
  EnrichedLiquidityMemoryNode(
    id='level_2.15',
    price_center=2.15,
    strength=0.5918,
    interactions=2,
    volume_total=52364.0
  ),
  ...
]
```

---

### 2. get_dormant_nodes()

```python
def get_dormant_nodes(
    current_price: Optional[float] = None,
    radius: Optional[float] = None
) -> List[EnrichedLiquidityMemoryNode]:
```

**Returns:** Dormant nodes (historical context)

**Example Response:**
```python
[
  EnrichedLiquidityMemoryNode(
    id='level_2.00',
    price_center=2.00,
    strength=0.05,  # Low (dormant)
    decay_rate=0.00001  # 10× slower
  ),
  ...
]
```

---

### 3. get_node_density()

```python
def get_node_density(
    price_range: Tuple[float, float]
) -> Dict[str, float]:
```

**Returns:** Density metrics for price range

**Example Response:**
```python
{
  'neighbor_count': 4,
  'density': 40.0,  # nodes per $0.01
  'strength_weighted_density': 17.3459,
  'avg_neighbor_strength': 0.4336
}
```

---

### 4. get_pressure_map()

```python
def get_pressure_map(
    price_range: Tuple[float, float]  
) -> PressureMap:
```

**Returns:** Pressure metrics (historical density)

**Example Response:**
```python
PressureMap(
  price_start=2.00,
  price_end=2.30,
  price_width=0.30,
  
  events_per_unit=166.67,
  interactions_per_unit=166.67,
  volume_per_unit=3262983.0,
  liquidations_per_unit=23.33,
  
  nodes_per_unit=36.67,
  active_nodes_per_unit=0.0,
  dormant_nodes_per_unit=36.67
)
```

**CRITICAL:** Pressure = historical density, NOT trade pressure

---

### 5. get_topological_clusters()

```python
def get_topological_clusters(
    price_threshold: float = 0.01,
    min_cluster_size: int = 2
) -> List[TopologyCluster]:
```

**Returns:** Topological clusters (neutral IDs)

**Example Response:**
```python
[
  TopologyCluster(
    cluster_id='cluster_0',  # NOT 'support_zone'
    price_center=2.0505,
    price_range=0.0210,
    node_count=8,
    total_interactions=0,
    avg_strength=0.5651
  ),
  ...
]
```

---

## XRPUSDT Pressure Metrics (Sample)

**Full Range: $2.00 - $2.30**

| Range | Nodes/Unit | Volume/Unit | Liqs/Unit | Density |
|:------|:-----------|:------------|:----------|:--------|
| $2.00-$2.05 | 60.0 | $3.6M | 0.00 | 160.0 |
| $2.05-$2.10 | 60.0 | $6.3M | 0.00 | 260.0 |
| $2.10-$2.15 | 60.0 | $5.8M | 60.00 | 280.0 |
| $2.15-$2.20 | 60.0 | $7.1M | 100.00 | 360.0 |
| $2.20-$2.25 | 60.0 | $8.0M | 80.00 | 420.0 |
| $2.25-$2.30 | 20.0 | $3.0M | 40.00 | 180.0 |

**Global Metrics:**
- Total nodes: 11
- Total interactions: 48
- Total volume: $922k
- Total liquidations: 7

---

## Prohibition Compliance

✅ **Verified absence of:**
- Signal-generating methods (`generate_signal`, `should_buy`)
- Interpretive labels (`support_zone`, `resistance_area`)
- Directional bias (`is_bullish`, `is_bearish`)  
- Action recommendations (`get_action`, `optimal_entry`)

✅ **All queries return:**
- Raw data structures
- Factual counts and ratios
- Numeric ordersonly (no 'best' or 'optimal')

---

## Usage Examples

```python
from memory import ContinuityMemoryStore

store = ContinuityMemoryStore()

# Query 1: Active nodes near price
nodes = store.get_active_nodes(
    current_price=2.10,
    radius=0.05,
    min_strength=0.3
)
print(f"Found {len(nodes)} nodes")

# Query 2: Dormant historical context
dormant = store.get_dormant_nodes(
    current_price=2.15,
    radius=0.10
)
print(f"Historical nodes: {len(dormant)}")

# Query 3: Density for range
density = store.get_node_density((2.10, 2.20))
print(f"Density: {density['density']} nodes/unit")

# Query 4: Pressure map
pressure = store.get_pressure_map((2.00, 2.30))
print(f"Volume/unit: ${pressure.volume_per_unit:.0f}")

# Query 5: Topological clusters
clusters = store.get_topological_clusters(
    price_threshold=0.02,
    min_cluster_size=2
)
print(f"Clusters: {len(clusters)}")
```

---

## Key Principles

✓ **Read-only:** No mutations via queries  
✓ **Raw data:** No processed signals  
✓ **Factual:** Counts, ratios, measurements only  
✓ **Numeric sorting:** By strength/price, not "best"  
✓ **No interpretation:** Historical density, not prediction  

**Query interface is purely observational.**
