#!/usr/bin/env python3
"""Verify Hyperdash addresses and find active whales."""
import asyncio
import sys
import aiohttp

async def get_clearinghouse(session, address):
    """Get wallet positions."""
    payload = {"type": "clearinghouseState", "user": address}
    try:
        async with session.post(
            "https://api.hyperliquid.xyz/info",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=5
        ) as response:
            if response.status == 200:
                return await response.json()
    except:
        pass
    return None

async def main():
    print("=" * 100)
    print("VERIFYING HYPERDASH ADDRESSES")
    print("=" * 100)
    print()

    # Read addresses from file
    try:
        with open("hyperdash_addresses.txt", "r") as f:
            addresses = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print("hyperdash_addresses.txt not found")
        return

    print(f"Checking {len(addresses)} addresses...")
    print()

    active_wallets = []

    async with aiohttp.ClientSession() as session:
        for i, addr in enumerate(addresses):
            data = await get_clearinghouse(session, addr)

            if data:
                positions = data.get("assetPositions", [])
                account = data.get("crossMarginSummary", {})
                account_value = float(account.get("accountValue", 0))

                total_position = 0
                total_pnl = 0
                coins = []

                for p in positions:
                    pos = p.get("position", {})
                    szi = float(pos.get("szi", 0))
                    entry = float(pos.get("entryPx", 0))
                    pnl = float(pos.get("unrealizedPnl", 0))
                    coin = pos.get("coin", "")
                    value = abs(szi * entry)

                    if value > 0:
                        total_position += value
                        total_pnl += pnl
                        side = "L" if szi > 0 else "S"
                        coins.append(f"{coin}({side})")

                if total_position > 0:
                    active_wallets.append({
                        "address": addr,
                        "account": account_value,
                        "position": total_position,
                        "pnl": total_pnl,
                        "coins": coins[:3]
                    })
                    print(f"  [{i+1:3}/{len(addresses)}] {addr[:12]}... ACTIVE ${total_position:>12,.0f}")
                elif account_value > 100000:
                    active_wallets.append({
                        "address": addr,
                        "account": account_value,
                        "position": 0,
                        "pnl": 0,
                        "coins": []
                    })

            # Progress
            if (i + 1) % 50 == 0:
                print(f"  Checked {i+1}/{len(addresses)}...")

            await asyncio.sleep(0.05)  # Rate limit

    # Sort by position size
    active_wallets.sort(key=lambda x: -(x["position"] or x["account"]))

    print()
    print("=" * 100)
    print(f"FOUND {len(active_wallets)} WALLETS WITH ACTIVITY")
    print("=" * 100)
    print()

    print(f"{'#':<3} {'Address':<44} {'Account':>14} {'Position':>14} {'PnL':>12} Coins")
    print("-" * 100)

    for i, w in enumerate(active_wallets[:30], 1):
        pnl_str = f"${w['pnl']:>+10,.0f}" if w['pnl'] != 0 else "-"
        coins = ", ".join(w["coins"]) if w["coins"] else "-"
        print(f"{i:<3} {w['address']:<44} ${w['account']:>13,.0f} ${w['position']:>13,.0f} {pnl_str} {coins}")

    # Generate code for top 20
    print()
    print("=" * 100)
    print("CODE FOR whale_wallets.py (top 20 by position size):")
    print("=" * 100)

    for i, w in enumerate(active_wallets[:20], 1):
        note = f"Position: ${w['position']:,.0f}" if w['position'] > 0 else f"Account: ${w['account']:,.0f}"
        print(f'''    WalletInfo(
        address="{w['address'].lower()}",
        label="Hyperdash-Top-{i:02d}",
        wallet_type="WHALE",
        notes="{note}"
    ),''')

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
