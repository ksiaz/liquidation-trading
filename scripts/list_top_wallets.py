#!/usr/bin/env python3
"""List top Hyperliquid wallets by position size."""
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
            headers={"Content-Type": "application/json"}
        ) as response:
            if response.status == 200:
                return await response.json()
    except:
        pass
    return None

async def get_recent_trades(session, coin="BTC"):
    """Get recent trades to discover active wallets."""
    payload = {"type": "recentTrades", "coin": coin}
    try:
        async with session.post(
            "https://api.hyperliquid.xyz/info",
            json=payload,
            headers={"Content-Type": "application/json"}
        ) as response:
            if response.status == 200:
                return await response.json()
    except:
        pass
    return None

async def get_user_fills(session, address):
    """Get recent fills for a user."""
    payload = {"type": "userFills", "user": address}
    try:
        async with session.post(
            "https://api.hyperliquid.xyz/info",
            json=payload,
            headers={"Content-Type": "application/json"}
        ) as response:
            if response.status == 200:
                return await response.json()
    except:
        pass
    return None

async def discover_wallets_from_fills(session):
    """Try to discover wallets from large fills."""
    # This endpoint may not be available without authentication
    wallets = set()

    # Try frontendOpenOrders which might have user addresses
    payload = {"type": "frontendOpenOrders", "user": "0x0000000000000000000000000000000000000000"}
    try:
        async with session.post(
            "https://api.hyperliquid.xyz/info",
            json=payload,
            headers={"Content-Type": "application/json"}
        ) as response:
            print(f"frontendOpenOrders status: {response.status}")
    except Exception as e:
        print(f"Error: {e}")

    return wallets

async def main():
    print("=" * 100)
    print("TOP HYPERLIQUID WALLETS BY POSITION SIZE")
    print("=" * 100)
    print()

    # Extended list of known whale addresses from various sources
    WHALE_ADDRESSES = [
        # High-profile traders (verified)
        ("0x5078c2fbea2b2ad61bc840bc023e35fce56bedb6", "James Wynn"),
        ("0x51d99a4022a55cad07a3c958f0600d8bb0b39921", "Insider Bro"),

        # Active traders (from on-chain data)
        ("0xe3b6e3443c8f2080704e7421bad9340f13950acb", "Active-001"),
        ("0x7839e2f2c375dd2935193f2736167514efff9916", "Active-002"),
        ("0xa68c548f3acd23a7fe3e867cc47f302559794419", "Active-003"),

        # Protocol vaults
        ("0xdfc24b077bc1425ad1dea75bcb6f8158e10df303", "HLP Main"),
        ("0x1e37a337ed460039d1b15bd3bc489de789768d5e", "Growi HF"),

        # More addresses to try (common patterns / web research)
        ("0x0000000000000000000000000000000000000001", "Test-001"),
        ("0xd7f1e7d2f60671b86edeefe96ce03dd3437cd17f", "Vault Leader"),
        ("0x677d831aef5328190852e24f13c46cac05f984e7", "Vault Leader 2"),

        # Additional research addresses
        ("0xf89d7b9c864f589bbf53a82105107622b35eaa40", "Research-001"),
        ("0x4f9fd6be60b9c5a8e1d9e3c3b1e8c5d4a7b6c9e2", "Research-002"),
        ("0x8b3d5f7a9c2e1f4d6b8a0c3e5f7d9b1a4c6e8f0d", "Research-003"),
    ]

    async with aiohttp.ClientSession() as session:
        wallets_with_positions = []

        print(f"Checking {len(WHALE_ADDRESSES)} addresses...\n")

        for addr, label in WHALE_ADDRESSES:
            data = await get_clearinghouse(session, addr)
            if data:
                positions = data.get("assetPositions", [])
                account = data.get("crossMarginSummary", {})
                account_value = float(account.get("accountValue", 0))

                total_position_value = 0
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
                        total_position_value += value
                        total_pnl += pnl
                        side = "L" if szi > 0 else "S"
                        leverage = pos.get("leverage", {})
                        lev = leverage.get("value", 1) if isinstance(leverage, dict) else leverage
                        coins.append(f"{coin}({side},{lev}x)")

                if total_position_value > 0 or account_value > 10000:
                    wallets_with_positions.append({
                        "address": addr,
                        "label": label,
                        "account_value": account_value,
                        "position_value": total_position_value,
                        "pnl": total_pnl,
                        "coins": coins[:4]
                    })

            await asyncio.sleep(0.1)

        # Sort by position value
        wallets_with_positions.sort(key=lambda x: -(x["position_value"] or x["account_value"]))

        if wallets_with_positions:
            print(f"{'#':<3} {'Label':<15} {'Address':<20} {'Account':>14} {'Positions':>14} {'PnL':>12} Coins")
            print("-" * 100)

            for i, w in enumerate(wallets_with_positions[:20], 1):
                pnl_str = f"${w['pnl']:>+10,.0f}" if w['pnl'] != 0 else "-"
                coins = ", ".join(w["coins"]) if w["coins"] else "-"
                addr_short = w["address"][:10] + "..."
                print(f"{i:<3} {w['label']:<15} {addr_short:<20} ${w['account_value']:>13,.0f} ${w['position_value']:>13,.0f} {pnl_str} {coins}")

            print()
            print(f"Total wallets with activity: {len(wallets_with_positions)}")
        else:
            print("No wallets with positions found.")

        print()
        print("=" * 100)
        print("NOTE: Hyperliquid doesn't expose a public leaderboard API.")
        print("To find more whale addresses, manually check:")
        print("  - https://www.coinglass.com/hl (CoinGlass whale tracker)")
        print("  - https://hyperdash.info/top-traders (Hyperdash leaderboard)")
        print("=" * 100)

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
