#!/usr/bin/env python3
"""Fetch Hyperliquid vault addresses."""
import asyncio
import sys
import json
import aiohttp

# Known vault addresses from documentation/research
KNOWN_VAULTS = [
    ("0xdfc24b077bc1425ad1dea75bcb6f8158e10df303", "HLP Vault"),
    ("0x1e37a337ed460039d1b15bd3bc489de789768d5e", "HLP Main"),
]

async def get_vault_details(session, address, name):
    """Get vault details."""
    payload = {"type": "vaultDetails", "vaultAddress": address}
    try:
        async with session.post(
            "https://api.hyperliquid.xyz/info",
            json=payload,
            headers={"Content-Type": "application/json"}
        ) as response:
            if response.status == 200:
                data = await response.json()
                return {
                    "address": address,
                    "name": data.get("name", name),
                    "raw": data
                }
    except Exception as e:
        print(f"Error: {e}")
    return None

async def get_all_vaults():
    """Fetch all available vaults."""
    async with aiohttp.ClientSession() as session:
        # vaultSummaries returns user-created vaults
        print("Fetching user vaults (vaultSummaries)...")
        payload = {"type": "vaultSummaries"}
        async with session.post(
            "https://api.hyperliquid.xyz/info",
            json=payload,
            headers={"Content-Type": "application/json"}
        ) as response:
            if response.status == 200:
                data = await response.json()
                print(f"Found {len(data)} user vaults\n")

                vaults = []
                for v in data:
                    tvl = float(v.get("tvl", 0))
                    vaults.append({
                        "address": v.get("vaultAddress", ""),
                        "name": v.get("name", "Unknown"),
                        "leader": v.get("leader", ""),
                        "tvl": tvl,
                        "closed": v.get("isClosed", False)
                    })

                # Sort by TVL
                vaults.sort(key=lambda x: -x["tvl"])

                print("USER VAULTS (by TVL):")
                print("=" * 90)
                for v in vaults[:15]:
                    status = " [CLOSED]" if v["closed"] else ""
                    print(f"  {v['name'][:35]:<35} | TVL: ${v['tvl']:>12,.0f}{status}")
                    print(f"    Address: {v['address']}")
                    print(f"    Leader:  {v['leader']}")
                    print()

        # Check protocol vaults
        print("\n" + "=" * 90)
        print("PROTOCOL VAULTS (HLP):")
        print("=" * 90)
        for addr, name in KNOWN_VAULTS:
            result = await get_vault_details(session, addr, name)
            if result:
                data = result["raw"]
                print(f"\n{result['name']}:")
                print(f"  Address: {addr}")
                # Print key fields
                for key in ["portfolio", "maxDistributable", "apr", "followerState"]:
                    if key in data:
                        val = data[key]
                        if isinstance(val, (list, dict)):
                            print(f"  {key}: {json.dumps(val)[:100]}...")
                        else:
                            print(f"  {key}: {val}")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(get_all_vaults())
