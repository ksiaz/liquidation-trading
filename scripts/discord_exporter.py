"""
Discord Chat Exporter wrapper for Hyperliquid Discord channels.

Setup:
1. Download DiscordChatExporter CLI from:
   https://github.com/Tyrrrz/DiscordChatExporter/releases

2. Extract to D:/tools/DiscordChatExporter/ (or update DCE_PATH below)

3. Get your Discord token:
   - Open Discord in browser
   - Press Ctrl+Shift+I -> Console tab
   - Paste:
     let m;webpackChunkdiscord_app.push([[Math.random()],{},e=>{for(let i in e.c){let x=e.c[i];if(x?.exports?.$8&&x.exports.LP&&x.exports.gK){m=x;break}}}]);m&&console.log("Token:",m.exports.LP());
   - Copy the token

4. Get channel IDs:
   - Discord Settings -> Advanced -> Enable Developer Mode
   - Right-click channel -> Copy Channel ID

5. Set environment variable:
   set DISCORD_TOKEN=your_token_here

WARNING: Using user tokens violates Discord ToS. Use at your own risk.
"""

import os
import subprocess
import json
from pathlib import Path
from datetime import datetime

# Configuration
DCE_PATH = Path(os.getenv("DCE_PATH", "D:/tools/DiscordChatExporter/DiscordChatExporter.Cli.exe"))
OUTPUT_DIR = Path("D:/liquidation-trading/data/discord_exports")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")

# Hyperliquid Discord channels
HYPERLIQUID_GUILD_ID = "915323513438871573"  # Update with actual ID

CHANNELS = {
    "node-operators": "1262830101838561310",
    "api-traders": "1087879542049357935",
    "builders": "1262879465503981672",
}


def check_setup():
    """Verify DCE is installed and token is set."""
    if not DCE_PATH.exists():
        print(f"ERROR: DiscordChatExporter not found at {DCE_PATH}")
        print("Download from: https://github.com/Tyrrrz/DiscordChatExporter/releases")
        return False

    if not DISCORD_TOKEN:
        print("ERROR: DISCORD_TOKEN environment variable not set")
        print("Run: set DISCORD_TOKEN=your_token_here")
        return False

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return True


def run_dce(args: list[str]) -> str:
    """Run DiscordChatExporter CLI command."""
    cmd = [str(DCE_PATH)] + args + ["-t", DISCORD_TOKEN]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
    return result.stdout


def list_guilds():
    """List all Discord servers you're in."""
    print("Fetching servers...")
    output = run_dce(["guilds"])
    print(output)
    return output


def list_channels(guild_id: str = HYPERLIQUID_GUILD_ID):
    """List all channels in a server."""
    print(f"Fetching channels for guild {guild_id}...")
    output = run_dce(["channels", "-g", guild_id])
    print(output)
    return output


def export_channel(channel_id: str, channel_name: str, format: str = "Json"):
    """Export a single channel."""
    if not check_setup():
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = OUTPUT_DIR / f"{channel_name}_{timestamp}.json"

    print(f"Exporting #{channel_name} to {output_file}...")

    args = [
        "export",
        "-c", channel_id,
        "-f", format,
        "-o", str(output_file),
    ]

    run_dce(args)

    if output_file.exists():
        print(f"SUCCESS: Exported to {output_file}")
        return output_file
    else:
        print("FAILED: Export file not created")
        return None


def export_hyperliquid_channels():
    """Export node-operators and api-traders channels."""
    if not check_setup():
        return

    for name, channel_id in CHANNELS.items():
        if not channel_id:
            print(f"SKIP: {name} - no channel ID configured")
            print("Run list_channels() first and update CHANNELS dict")
            continue
        export_channel(channel_id, name)


def search_exports(keyword: str, channel: str = None):
    """Search exported JSON files for a keyword."""
    files = list(OUTPUT_DIR.glob("*.json"))

    if channel:
        files = [f for f in files if channel in f.name]

    results = []
    for file in files:
        with open(file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for msg in data.get("messages", []):
            content = msg.get("content", "")
            if keyword.lower() in content.lower():
                results.append({
                    "file": file.name,
                    "author": msg.get("author", {}).get("name", "Unknown"),
                    "timestamp": msg.get("timestamp", ""),
                    "content": content[:500],
                })

    print(f"Found {len(results)} messages containing '{keyword}':")
    for r in results:
        print(f"\n[{r['timestamp']}] {r['author']}:")
        print(f"  {r['content']}")

    return results


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python discord_exporter.py guilds          - List servers")
        print("  python discord_exporter.py channels        - List Hyperliquid channels")
        print("  python discord_exporter.py export          - Export configured channels")
        print("  python discord_exporter.py search <term>   - Search exports")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "guilds":
        list_guilds()
    elif cmd == "channels":
        list_channels()
    elif cmd == "export":
        export_hyperliquid_channels()
    elif cmd == "search" and len(sys.argv) > 2:
        search_exports(sys.argv[2])
    else:
        print(f"Unknown command: {cmd}")
