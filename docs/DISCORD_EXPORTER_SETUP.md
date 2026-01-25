# Discord Chat Exporter Setup

Export Hyperliquid Discord channels (#node-operators, #api-traders) for offline search and analysis.

## Installation

### 1. Download DiscordChatExporter CLI

```powershell
# Create tools directory
mkdir D:\tools\DiscordChatExporter

# Download latest release from:
# https://github.com/Tyrrrz/DiscordChatExporter/releases
# Get: DiscordChatExporter.Cli.win-x64.zip

# Extract to D:\tools\DiscordChatExporter\
```

Or use Docker:
```bash
docker pull tyrrrz/discordchatexporter
```

### 2. Get Your Discord Token

1. Open Discord **in browser** (not desktop app)
2. Press `Ctrl+Shift+I` to open DevTools
3. Go to **Console** tab
4. Paste this code and press Enter:

```javascript
let m;webpackChunkdiscord_app.push([[Math.random()],{},e=>{for(let i in e.c){let x=e.c[i];if(x?.exports?.$8&&x.exports.LP&&x.exports.gK){m=x;break}}}]);m&&console.log("Token:",m.exports.LP());
```

5. Copy the token that appears

**⚠️ WARNING:** Treat this token like a password. Anyone with it has full access to your Discord account.

### 3. Get Channel IDs

1. Discord Settings → Advanced → Enable **Developer Mode**
2. Right-click on #node-operators → **Copy Channel ID**
3. Right-click on #api-traders → **Copy Channel ID**
4. Right-click on server name → **Copy Server ID**

### 4. Set Environment Variable

```powershell
# Temporary (current session)
set DISCORD_TOKEN=your_token_here

# Permanent (user level)
setx DISCORD_TOKEN "your_token_here"
```

## Usage

### Direct CLI Commands

```bash
# Set token for session
set DISCORD_TOKEN=your_token_here

# List servers you're in
D:\tools\DiscordChatExporter\DiscordChatExporter.Cli.exe guilds -t %DISCORD_TOKEN%

# List channels in Hyperliquid server
D:\tools\DiscordChatExporter\DiscordChatExporter.Cli.exe channels -t %DISCORD_TOKEN% -g GUILD_ID

# Export single channel to JSON
D:\tools\DiscordChatExporter\DiscordChatExporter.Cli.exe export -t %DISCORD_TOKEN% -c CHANNEL_ID -f Json -o output.json

# Export with date range
D:\tools\DiscordChatExporter\DiscordChatExporter.Cli.exe export -t %DISCORD_TOKEN% -c CHANNEL_ID -f Json --after "2025-01-01" --before "2025-01-31"

# Export entire server
D:\tools\DiscordChatExporter\DiscordChatExporter.Cli.exe exportguild -t %DISCORD_TOKEN% -g GUILD_ID -f Json

# Include threads
D:\tools\DiscordChatExporter\DiscordChatExporter.Cli.exe exportguild -t %DISCORD_TOKEN% -g GUILD_ID -f Json --include-threads all
```

### Python Wrapper Script

```bash
# List servers
python scripts/discord_exporter.py guilds

# List Hyperliquid channels
python scripts/discord_exporter.py channels

# Export configured channels
python scripts/discord_exporter.py export

# Search exported messages
python scripts/discord_exporter.py search "early eof"
```

## Export Formats

| Format | Use Case |
|--------|----------|
| Json | Programmatic analysis, search |
| HtmlDark | Human-readable archive |
| HtmlLight | Printable version |
| PlainText | Simple text search |
| Csv | Spreadsheet analysis |

## Hyperliquid Discord IDs

Update `scripts/discord_exporter.py` with actual IDs:

```python
HYPERLIQUID_GUILD_ID = "XXXXXXXXXXXXXXXXXX"  # Server ID

CHANNELS = {
    "node-operators": "XXXXXXXXXXXXXXXXXX",
    "api-traders": "XXXXXXXXXXXXXXXXXX",
    "builders": "XXXXXXXXXXXXXXXXXX",
}
```

## Workflow

### Initial Export
```bash
# 1. Get server ID
python scripts/discord_exporter.py guilds

# 2. Get channel IDs
python scripts/discord_exporter.py channels

# 3. Update CHANNELS dict in discord_exporter.py

# 4. Export
python scripts/discord_exporter.py export
```

### Search for Troubleshooting Info
```bash
# Search for specific errors
python scripts/discord_exporter.py search "early eof"
python scripts/discord_exporter.py search "port 4001"
python scripts/discord_exporter.py search "CGNAT"
```

## Legal Warning

⚠️ **Using user tokens violates Discord's Terms of Service.**

- Your account may be terminated
- Only use for personal backup/research
- Don't share your token
- Don't automate at high frequency

## References

- [DiscordChatExporter GitHub](https://github.com/Tyrrrz/DiscordChatExporter)
- [CLI Usage Guide](https://github.com/Tyrrrz/DiscordChatExporter/blob/master/.docs/Using-the-CLI.md)
- [Token & IDs Guide](https://github.com/Tyrrrz/DiscordChatExporter/blob/master/.docs/Token-and-IDs.md)
