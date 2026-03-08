# signal-cli macOS Setup Guide

A complete guide to installing, registering, auto-updating, and polling messages with
[signal-cli](https://github.com/AsamK/signal-cli) on macOS.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Install signal-cli](#2-install-signal-cli)
3. [Register or Link an Account](#3-register-or-link-an-account)
4. [Verify the Installation](#4-verify-the-installation)
5. [Auto-Update Every Three Months (LaunchAgent)](#5-auto-update-every-three-months-launchagent)
6. [Polling for Messages](#6-polling-for-messages)
7. [Daemon Mode (Advanced)](#7-daemon-mode-advanced)
8. [Tips & Troubleshooting](#8-tips--troubleshooting)

---

## 1. Prerequisites

### Java 25 or later

signal-cli v0.14.0+ requires **Java Runtime Environment (JRE) 25**.

Install via [SDKMAN](https://sdkman.io/) (recommended — lets you manage multiple JDK versions):

```bash
# Install SDKMAN
curl -s "https://get.sdkman.io" | bash
source "$HOME/.sdkman/bin/sdkman-init.sh"

# Install Java 25 (use latest available if 25 isn't listed yet, e.g. 25.ea.*)
sdk install java 25.ea.5-open     # adjust identifier as needed
sdk default java 25.ea.5-open

# Confirm
java -version
```

Alternatively, install via Homebrew (if a Java 25 formula is available):

```bash
brew install --cask zulu25   # or openjdk@25 when available
```

> **Note:** Check `brew search openjdk` to find the right formula name for your Homebrew version.

---

## 2. Install signal-cli

### Option A — Pre-built binary (recommended)

Download the latest release tarball for the JVM build, which includes macOS native libraries.

```bash
# 1. Find the latest version number
VERSION=$(curl -Ls -o /dev/null -w '%{url_effective}' \
  https://github.com/AsamK/signal-cli/releases/latest \
  | sed 's/.*\/v//')

echo "Latest version: $VERSION"

# 2. Download
curl -L -O \
  "https://github.com/AsamK/signal-cli/releases/download/v${VERSION}/signal-cli-${VERSION}.tar.gz"

# 3. Extract to /opt
sudo tar xf "signal-cli-${VERSION}.tar.gz" -C /opt

# 4. Symlink the binary
sudo ln -sf "/opt/signal-cli-${VERSION}/bin/signal-cli" /usr/local/bin/signal-cli

# 5. Confirm
signal-cli --version
```

### Option B — Build from source

```bash
# Requires git and a recent Gradle (wrapper included)
git clone https://github.com/AsamK/signal-cli.git
cd signal-cli
./gradlew installDist

# Binary lands at: build/install/signal-cli/bin/signal-cli
sudo ln -sf "$(pwd)/build/install/signal-cli/bin/signal-cli" /usr/local/bin/signal-cli
```

---

## 3. Register or Link an Account

You need a phone number to use signal-cli. There are two paths:

### Path A — Fresh registration (new Signal account on this number)

> ⚠️ This will replace the Signal registration on your phone if you use the same number.
> Use **Path B** (link) if you want to keep your phone active.

```bash
# Replace +15551234567 with your number in international format
signal-cli -a +15551234567 register

# You'll receive an SMS. Verify with:
signal-cli -a +15551234567 verify 123-456
```

If registration requires a CAPTCHA:
1. Visit https://signalcaptchas.org/registration/generate.html
2. Solve it, then right-click "Open Signal" → copy link
3. Pass it: `signal-cli -a +15551234567 register --captcha signalcaptcha://...`

### Path B — Link to an existing device (phone stays primary)

```bash
# This prints a QR code directly in the terminal (v0.14.0+)
signal-cli link --name "My Mac"
```

On your phone: **Settings → Linked Devices → Link New Device** → scan the QR code.

---

## 4. Verify the Installation

Send a test message to yourself (note-to-self):

```bash
signal-cli -a +15551234567 send --note-to-self -m "signal-cli is working!"
```

Receive pending messages:

```bash
signal-cli -a +15551234567 receive
```

Data is stored at:
```
~/.local/share/signal-cli/data/
```

---

## 5. Auto-Update Every Three Months (LaunchAgent)

> **Why:** The Signal protocol treats clients older than **three months** as expired.
> Outdated signal-cli versions may stop working as Signal servers make protocol changes.
> Keeping the binary current is therefore essential for continued operation.

### Create the update script

```bash
mkdir -p ~/Library/Scripts
```

Save the following as `~/Library/Scripts/signal-cli-update.sh`:

```bash
#!/usr/bin/env bash
# signal-cli-update.sh — download and install the latest signal-cli release

set -euo pipefail

LOG="$HOME/Library/Logs/signal-cli-update.log"
exec >> "$LOG" 2>&1

echo ""
echo "=== signal-cli update started: $(date) ==="

# 1. Determine latest version
LATEST=$(curl -Ls -o /dev/null -w '%{url_effective}' \
  https://github.com/AsamK/signal-cli/releases/latest \
  | sed 's/.*\/v//')

echo "Latest version: $LATEST"

# 2. Check what's currently installed
CURRENT=$(signal-cli --version 2>/dev/null | awk '{print $NF}' || echo "none")
echo "Current version: $CURRENT"

if [ "$LATEST" = "$CURRENT" ]; then
  echo "Already up-to-date. Nothing to do."
  exit 0
fi

# 3. Download
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

TARBALL="signal-cli-${LATEST}.tar.gz"
curl -L -o "$TMPDIR/$TARBALL" \
  "https://github.com/AsamK/signal-cli/releases/download/v${LATEST}/${TARBALL}"

# 4. Install
sudo tar xf "$TMPDIR/$TARBALL" -C /opt
sudo ln -sf "/opt/signal-cli-${LATEST}/bin/signal-cli" /usr/local/bin/signal-cli

echo "Updated to $LATEST successfully."
```

Make it executable:

```bash
chmod +x ~/Library/Scripts/signal-cli-update.sh
```

### Create the LaunchAgent plist

Save the following as `~/Library/LaunchAgents/com.signal-cli.update.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <!-- Unique label for this agent -->
    <key>Label</key>
    <string>com.signal-cli.update</string>

    <!-- What to run -->
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/YOUR_USERNAME/Library/Scripts/signal-cli-update.sh</string>
    </array>

    <!-- Run once a month (well within the 3-month expiry window) -->
    <!-- StartCalendarInterval fires on the given day/hour/minute each month -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Day</key>
        <integer>1</integer>      <!-- 1st of the month -->
        <key>Hour</key>
        <integer>3</integer>      <!-- 3 AM -->
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <!-- Also run immediately on load if it missed the last scheduled time -->
    <key>RunAtLoad</key>
    <false/>

    <!-- Log output -->
    <key>StandardOutPath</key>
    <string>/Users/YOUR_USERNAME/Library/Logs/signal-cli-update.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOUR_USERNAME/Library/Logs/signal-cli-update.log</string>

    <!-- Keep trying if the network/command fails -->
    <key>ThrottleInterval</key>
    <integer>86400</integer>
</dict>
</plist>
```

> Replace `YOUR_USERNAME` with your actual macOS username (`whoami` will tell you).

### Load the LaunchAgent

```bash
launchctl load ~/Library/LaunchAgents/com.signal-cli.update.plist
```

### Test it immediately

```bash
launchctl start com.signal-cli.update

# Watch the log
tail -f ~/Library/Logs/signal-cli-update.log
```

### Manage the agent

```bash
# Disable (stop running on schedule)
launchctl unload ~/Library/LaunchAgents/com.signal-cli.update.plist

# Re-enable
launchctl load ~/Library/LaunchAgents/com.signal-cli.update.plist

# Check status
launchctl list | grep signal-cli
```

---

## 6. Polling for Messages

The Signal protocol requires **regular message retrieval** for encryption to work correctly
and for group/expiration-timer metadata to stay in sync. There are several approaches:

---

### Approach 1 — Periodic `receive` via LaunchAgent (simplest)

Run `signal-cli receive` on a schedule. Each invocation connects, drains pending messages,
then exits. Output can be piped to a script for processing.

**Create `~/Library/Scripts/signal-cli-receive.sh`:**

```bash
#!/usr/bin/env bash
set -euo pipefail

ACCOUNT="+15551234567"          # your number
LOG="$HOME/Library/Logs/signal-cli-receive.log"
TIMEOUT=10                      # seconds to wait for messages

# Optional: pipe JSON output to your own processing script
signal-cli -a "$ACCOUNT" -o json receive --timeout "$TIMEOUT" \
  >> "$LOG" 2>&1

# Or process inline:
# signal-cli -a "$ACCOUNT" -o json receive --timeout "$TIMEOUT" \
#   | jq -r 'select(.envelope.dataMessage) | .envelope | "\(.source): \(.dataMessage.message)"'
```

```bash
chmod +x ~/Library/Scripts/signal-cli-receive.sh
```

**Create `~/Library/LaunchAgents/com.signal-cli.receive.plist`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.signal-cli.receive</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/YOUR_USERNAME/Library/Scripts/signal-cli-receive.sh</string>
    </array>

    <!-- Run every 5 minutes -->
    <key>StartInterval</key>
    <integer>300</integer>

    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/Users/YOUR_USERNAME/Library/Logs/signal-cli-receive.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOUR_USERNAME/Library/Logs/signal-cli-receive.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.signal-cli.receive.plist
```

**Pros:** Simple, stateless, easy to debug.  
**Cons:** Up to 5-minute delay between message arrival and retrieval; JVM startup overhead per poll.

---

### Approach 2 — Long-running `receive --timeout -1` loop via LaunchAgent

Keep `receive` open indefinitely — it will block and stream messages as they arrive.
`launchd` will restart it automatically if it dies.

**Create `~/Library/LaunchAgents/com.signal-cli.receive-daemon.plist`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.signal-cli.receive-daemon</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/signal-cli</string>
        <string>-a</string>
        <string>+15551234567</string>
        <string>-o</string>
        <string>json</string>
        <string>receive</string>
        <string>--timeout</string>
        <string>-1</string>           <!-- block forever -->
    </array>

    <key>RunAtLoad</key>
    <true/>

    <!-- Restart automatically if it exits for any reason -->
    <key>KeepAlive</key>
    <true/>

    <!-- Throttle restart attempts to avoid a crash loop hammering CPU -->
    <key>ThrottleInterval</key>
    <integer>30</integer>

    <key>StandardOutPath</key>
    <string>/Users/YOUR_USERNAME/Library/Logs/signal-cli-receive.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOUR_USERNAME/Library/Logs/signal-cli-receive.log</string>
</dict>
</plist>
```

**Pros:** Near real-time delivery; only one JVM process.  
**Cons:** Log file grows unboundedly (add `newsyslog` or `logrotate`); no built-in processing pipeline.

---

### Approach 3 — `daemon --http` with your own consumer (most powerful)

Run signal-cli as a proper daemon exposing an HTTP/JSON-RPC endpoint. Poll or push from any
language or tool.

```bash
# Start in HTTP daemon mode (port 8080)
signal-cli -a +15551234567 daemon --http localhost:8080
```

Then call it from any HTTP client:

```bash
# Receive messages via JSON-RPC
curl -s -X POST http://localhost:8080/api/v1/rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"receive","id":1}'

# Send a message
curl -s -X POST http://localhost:8080/api/v1/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "send",
    "params": {
      "recipient": ["+15559876543"],
      "message": "Hello from curl!"
    },
    "id": 2
  }'
```

**LaunchAgent for daemon mode:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.signal-cli.daemon</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/signal-cli</string>
        <string>-a</string>
        <string>+15551234567</string>
        <string>daemon</string>
        <string>--http</string>
        <string>localhost:8080</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>ThrottleInterval</key>
    <integer>30</integer>

    <key>StandardOutPath</key>
    <string>/Users/YOUR_USERNAME/Library/Logs/signal-cli-daemon.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOUR_USERNAME/Library/Logs/signal-cli-daemon.log</string>
</dict>
</plist>
```

**Pros:** Full API access; language-agnostic; can serve multiple consumers; supports send + receive.  
**Cons:** More moving parts; port must be secured (localhost only, or use a UNIX socket with `--socket`).

---

### Approach 4 — UNIX socket daemon (most secure for local use)

```bash
signal-cli -a +15551234567 daemon --socket
# Default socket: $XDG_RUNTIME_DIR/signal-cli/socket
# i.e. typically /run/user/$(id -u)/signal-cli/socket
```

Connect from any JSON-RPC client that speaks UNIX sockets. The bundled Rust client in
`./client/` demonstrates this pattern.

---

### Approach Comparison

| Approach | Latency | Complexity | Restart Safety | Best For |
|---|---|---|---|---|
| Periodic `receive` (LaunchAgent) | Up to 5 min | ⭐ Low | ✅ Automatic | Simple notifications |
| Blocking `receive --timeout -1` | ~Real-time | ⭐ Low | ✅ via KeepAlive | Logging / archiving |
| `daemon --http` | ~Real-time | ⭐⭐ Medium | ✅ via KeepAlive | App integrations |
| `daemon --socket` | ~Real-time | ⭐⭐⭐ Higher | ✅ via KeepAlive | Secure local services |

---

## 7. Daemon Mode (Advanced)

For long-running setups, the `daemon` command is the recommended approach. It continuously
maintains the Signal connection, handles re-keying, group updates, and profile refreshes
automatically — which the `receive` command only does at poll time.

```bash
# Daemon with both HTTP API and UNIX socket simultaneously
signal-cli -a +15551234567 daemon --http localhost:8080 --socket

# All accounts (if multiple are registered)
signal-cli daemon --http localhost:8080
```

See the [JSON-RPC man page](https://github.com/AsamK/signal-cli/blob/master/man/signal-cli-jsonrpc.5.adoc)
for the full API reference.

---

## 8. Tips & Troubleshooting

### macOS Gatekeeper / quarantine

If macOS blocks the binary with "cannot be opened because the developer cannot be verified":

```bash
xattr -d com.apple.quarantine /opt/signal-cli-*/bin/signal-cli
```

Or allow it in **System Settings → Privacy & Security**.

### Java not found by LaunchAgent

LaunchAgents don't inherit your shell's `PATH`. Specify the full path to `java` in your
scripts, or add a `PATH` environment key to the plist:

```xml
<key>EnvironmentVariables</key>
<dict>
    <key>PATH</key>
    <string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin</string>
    <key>JAVA_HOME</key>
    <string>/Users/YOUR_USERNAME/.sdkman/candidates/java/current</string>
</dict>
```

### Log rotation

Prevent logs from growing without bound:

```bash
# Add to /etc/newsyslog.d/signal-cli.conf
# path                                          mode  count size  when  flags
/Users/YOUR_USERNAME/Library/Logs/signal-cli-*.log  644   7     1024  *     GJ
```

Or use `logrotate` via Homebrew:

```bash
brew install logrotate
```

### Check signal-cli data directory

```bash
ls -la ~/.local/share/signal-cli/data/
```

### Verbose logging for debugging

```bash
signal-cli -v -a +15551234567 receive
```

### Update reminder

> signal-cli must be updated **at least every 3 months**. The LaunchAgent in Step 5 runs
> monthly, which is a comfortable safety margin. Check the log after the first of each month:
>
> ```bash
> tail -50 ~/Library/Logs/signal-cli-update.log
> ```

---

## Quick Reference

```bash
# Install / update
VERSION=$(curl -Ls -o /dev/null -w '%{url_effective}' https://github.com/AsamK/signal-cli/releases/latest | sed 's/.*\/v//')
curl -LO "https://github.com/AsamK/signal-cli/releases/download/v${VERSION}/signal-cli-${VERSION}.tar.gz"
sudo tar xf signal-cli-${VERSION}.tar.gz -C /opt
sudo ln -sf /opt/signal-cli-${VERSION}/bin/signal-cli /usr/local/bin/signal-cli

# Link device (preferred — keeps phone active)
signal-cli link --name "My Mac"

# Send
signal-cli -a +15551234567 send -m "Hello" +15559876543

# Receive (one-shot)
signal-cli -a +15551234567 receive

# Daemon with HTTP API
signal-cli -a +15551234567 daemon --http localhost:8080

# Load all LaunchAgents
launchctl load ~/Library/LaunchAgents/com.signal-cli.update.plist
launchctl load ~/Library/LaunchAgents/com.signal-cli.receive.plist
```
