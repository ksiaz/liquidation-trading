"""
Hyperliquid Node Adapter Service

gRPC service that streams normalized events from the Hyperliquid node.
Runs in WSL where the node data is located.

Responsibilities:
- Parse node raw formats (replica_cmds JSON, abci_state.rmp msgpack)
- Normalize timestamps to milliseconds
- Normalize asset identifiers (ID → symbol)
- Deduplicate events within blocks
- Maintain strict ordering per block
- Emit clean structured events via gRPC streaming

Does NOT:
- Trade
- Filter by importance
- Predict
- Detect signals
- Apply strategy logic
"""
