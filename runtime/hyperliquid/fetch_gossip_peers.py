"""Fetch current Hyperliquid gossip peer IPs from the API."""

import json
import httpx


def fetch_gossip_peers() -> list[str]:
    """Fetch gossip root IPs from Hyperliquid API."""
    response = httpx.post(
        "https://api.hyperliquid.xyz/info",
        json={"type": "gossipRootIps"},
        headers={"Content-Type": "application/json"},
    )
    response.raise_for_status()
    return response.json()


def generate_override_config(peers: list[str], chain: str = "Mainnet") -> dict:
    """Generate override_gossip_config.json format."""
    return {
        "root_node_ips": [{"Ip": ip} for ip in peers],
        "try_new_peers": True,
        "chain": chain,
    }


if __name__ == "__main__":
    peers = fetch_gossip_peers()
    print(f"Fetched {len(peers)} gossip peers:\n")

    for ip in peers:
        print(f"  {ip}")

    print("\n--- override_gossip_config.json format ---\n")
    config = generate_override_config(peers)
    print(json.dumps(config, indent=2))
