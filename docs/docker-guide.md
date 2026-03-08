# signal-cli Docker Guide

Run signal-cli as a self-contained Docker container with an HTTP API for sending and
receiving Signal messages from any language or tool.

---

## Table of Contents

1. [How It Works](#1-how-it-works)
2. [Prerequisites](#2-prerequisites)
3. [Build the Image](#3-build-the-image)
4. [Registration Phase — Link to Your Existing Phone](#4-registration-phase--link-to-your-existing-phone)
5. [Run the HTTP Daemon](#5-run-the-http-daemon)
6. [Using the JSON-RPC API](#6-using-the-json-rpc-api)
7. [Running with Docker Compose](#7-running-with-docker-compose)
8. [Data Persistence & Backup](#8-data-persistence--backup)
9. [scripts/signal-ollama.py — Reply to Yourself with Ollama](#9-scriptssignal-ollamapy--reply-to-yourself-with-ollama)
10. [Keeping signal-cli Up to Date](#10-keeping-signal-cli-up-to-date)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. How It Works

```
┌─────────────────────────────────────────────────┐
│                Docker container                 │
│                                                 │
│  signal-cli daemon                              │
│    │                                            │
│    ├── maintains a persistent WebSocket ──────────────► Signal servers
│    │   (receives messages automatically)        │
│    │                                            │
│    └── HTTP JSON-RPC on :8080 ◄─────────────────────── your app / curl
│                                                 │
│  /var/lib/signal-cli  (volume)                  │
│    └── keys, account data, attachments          │
└─────────────────────────────────────────────────┘
```

When the daemon is running:

- **Incoming messages** are received automatically over Signal's WebSocket. You can fetch them
  via the API at any time.
- **Outgoing messages** are sent by POSTing to the HTTP API.
- **Everything is JSON-RPC:** one endpoint (`POST /api/v1/rpc`), the action is the `"method"`
  field in your request body.

---

## 2. Prerequisites

- [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/) installed and running
- A phone with Signal installed (you'll link signal-cli as a secondary device — your phone
  stays active and remains the primary)
- Your phone number in international format, e.g. `+15551234567`

> **Apple Silicon (M1/M2/M3):** Add `--platform linux/amd64` to all `docker build` and
> `docker run` commands below, or set it once in your shell:
> ```bash
> export DOCKER_DEFAULT_PLATFORM=linux/amd64
> ```
> Docker on Apple Silicon emulates x86_64 Linux via Rosetta, which signal-cli's bundled
> native library requires.

---

## 3. Build the Image

The image downloads the latest signal-cli release from GitHub at build time — no local
Java installation or build tools needed.

```bash
# Clone the repo (if you haven't already)
git clone https://github.com/AsamK/signal-cli.git
cd signal-cli

# Build the image (this will download signal-cli from GitHub)
docker build -f Dockerfile.standalone -t signal-cli .

# On Apple Silicon:
docker build --platform linux/amd64 -f Dockerfile.standalone -t signal-cli .
```

The build takes ~30 seconds. The final image is around 250 MB.

Confirm it works:

```bash
docker run --rm signal-cli --version
```

---

## 4. Registration Phase — Link to Your Existing Phone

This is a one-time setup. You link signal-cli to your existing Signal account as a
secondary device. Your phone stays active as the primary.

### Step 1 — Create a named volume for persistent data

This is where signal-cli stores your account keys, session data, and attachments. It must
survive container restarts — without it you'd have to re-link every time.

```bash
docker volume create signal-cli-data
```

### Step 2 — Start the link process

```bash
docker run --rm -it \
  -v signal-cli-data:/var/lib/signal-cli \
  signal-cli link --name "My Server"
```

signal-cli will print a QR code directly in the terminal (v0.14.0+). It will also print
the raw `sgnl://linkdevice?...` URI above it in case the QR rendering is garbled.

### Step 3 — Scan on your phone

On your iPhone or Android:

1. Open Signal
2. Go to **Settings → Linked Devices**
3. Tap the **+** button
4. Scan the QR code from the terminal

You'll see "My Server" appear in your linked devices list. The terminal command will exit
automatically once linking succeeds.

### Step 4 — Verify the link

```bash
docker run --rm \
  -v signal-cli-data:/var/lib/signal-cli \
  signal-cli -a +15551234567 receive
```

Replace `+15551234567` with your actual phone number. You should see any pending messages
printed as JSON. No errors means you're linked and working.

---

## 5. Run the HTTP Daemon

The daemon is the long-running process you keep alive. It maintains the Signal connection
and serves the HTTP API.

```bash
docker run -d \
  --name signal-cli \
  --restart unless-stopped \
  -v signal-cli-data:/var/lib/signal-cli \
  -p 127.0.0.1:8088:8080 \
  signal-cli \
  -a +15551234567 daemon --http 0.0.0.0:8080
```

Key flags:
- `-d` — run in the background
- `--restart unless-stopped` — auto-restart if it crashes or the machine reboots
- `-p 127.0.0.1:8088:8080` — bind the API port to **localhost only** (never expose this
  port publicly — there is no authentication)
- `0.0.0.0:8080` inside the container means "all container interfaces", the host binding
  above constrains it to localhost

Check it started:

```bash
docker logs signal-cli
docker logs -f signal-cli   # follow live
```

You should see something like:
```
Started JSON-RPC HTTP server on localhost:8088
```

---

## 6. Using the JSON-RPC API

The API lives at: `POST http://localhost:8088/api/v1/rpc`

Every request has this shape:
```json
{
  "jsonrpc": "2.0",
  "method": "THE_ACTION",
  "params": { ... },
  "id": 1
}
```

Every response has this shape:
```json
{
  "jsonrpc": "2.0",
  "result": { ... },
  "id": 1
}
```

The `"id"` is any number you choose — it's echoed back in the response so you can match
them up if you're making multiple calls.

---

### Send a message

```bash
curl -s -X POST http://localhost:8088/api/v1/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "send",
    "params": {
      "recipient": ["+15559876543"],
      "message": "Hello from signal-cli!"
    },
    "id": 1
  }'
```

Send to multiple people:

```bash
curl -s -X POST http://localhost:8088/api/v1/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "send",
    "params": {
      "recipient": ["+15559876543", "+15551112222"],
      "message": "Group announcement!"
    },
    "id": 1
  }'
```

Send to a group:

```bash
curl -s -X POST http://localhost:8088/api/v1/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "send",
    "params": {
      "groupId": "BASE64_GROUP_ID_HERE",
      "message": "Hello group!"
    },
    "id": 1
  }'
```

Send a note to yourself:

```bash
curl -s -X POST http://localhost:8088/api/v1/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "send",
    "params": {
      "noteToSelf": true,
      "message": "Reminder: buy milk"
    },
    "id": 1
  }'
```

---

### Receive messages

Fetch all messages that have arrived since the last receive:

```bash
curl -s -X POST http://localhost:8088/api/v1/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "receive",
    "id": 1
  }'
```

The response is an array of envelope objects. A typical incoming message looks like:

```json
{
  "jsonrpc": "2.0",
  "result": [
    {
      "envelope": {
        "source": "+15559876543",
        "sourceDevice": 1,
        "timestamp": 1709123456789,
        "dataMessage": {
          "timestamp": 1709123456789,
          "message": "Hey, what's up?",
          "expiresInSeconds": 0,
          "groupInfo": null
        }
      }
    }
  ],
  "id": 1
}
```

Pull out just the sender and text using `jq`:

```bash
curl -s -X POST http://localhost:8088/api/v1/rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"receive","id":1}' \
  | jq -r '.result[]
      | select(.envelope.dataMessage.message != null)
      | "\(.envelope.source): \(.envelope.dataMessage.message)"'
```

---

### List contacts

```bash
curl -s -X POST http://localhost:8088/api/v1/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "listContacts",
    "id": 1
  }'
```

---

### List groups

```bash
curl -s -X POST http://localhost:8088/api/v1/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "listGroups",
    "id": 1
  }'
```

The `id` field in the group response is the base64 group ID you use when sending to a group.

---

### Send a reaction

```bash
curl -s -X POST http://localhost:8088/api/v1/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "sendReaction",
    "params": {
      "recipient": ["+15559876543"],
      "emoji": "👍",
      "targetAuthor": "+15559876543",
      "targetTimestamp": 1709123456789
    },
    "id": 1
  }'
```

---

### Subscribe to incoming messages — Server-Sent Events (SSE)

Polling `receive` works, but it means you only see messages when you ask. The better
approach is to **subscribe** — the daemon pushes messages to you the moment they arrive,
over a persistent HTTP connection. This uses the standard
[Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
protocol, which is built into every browser and most HTTP libraries.

The endpoint is:
```
GET http://localhost:8088/api/v1/events
```

The daemon keeps this connection open and streams a new JSON event each time a message
arrives. Your client just listens.

#### Try it with curl

```bash
curl -N http://localhost:8088/api/v1/events
```

`-N` disables buffering so events print immediately. Leave this running — you'll see output
every time a Signal message arrives, looking like:

```
data: {"envelope":{"source":"+15559876543","sourceNumber":"+15559876543","sourceName":"Alice","sourceDevice":1,"timestamp":1709123456789,"dataMessage":{"timestamp":1709123456789,"message":"Hey!","expiresInSeconds":0,"viewOnce":false,"mentions":[],"attachments":[]}},"account":"+15551234567"}
```

#### Filter with jq in real time

```bash
curl -N http://localhost:8088/api/v1/events \
  | grep --line-buffered '^data:' \
  | sed 's/^data: //' \
  | jq --unbuffered -r '
      select(.envelope.dataMessage.message != null)
      | "\(.envelope.sourceName // .envelope.source): \(.envelope.dataMessage.message)"'
```

This prints `Alice: Hey!` style output live as messages come in.

#### Listen from a shell script (persistent, restarts on disconnect)

```bash
#!/usr/bin/env bash
# signal-listen.sh — subscribe to messages and handle each one

while true; do
  curl -fsSN http://localhost:8088/api/v1/events \
    | grep --line-buffered '^data:' \
    | sed 's/^data: //' \
    | while IFS= read -r line; do
        SENDER=$(echo "$line" | jq -r '.envelope.sourceName // .envelope.source')
        MESSAGE=$(echo "$line" | jq -r '.envelope.dataMessage.message // empty')

        # Skip events that aren't plain text messages
        [ -z "$MESSAGE" ] && continue

        echo "$(date): [$SENDER] $MESSAGE"

        # Put your logic here — call a webhook, write to a file, trigger an action, etc.
      done

  echo "Disconnected — reconnecting in 5s..."
  sleep 5
done
```

#### Listen from Python

```python
import requests
import json

url = "http://localhost:8088/api/v1/events"

with requests.get(url, stream=True) as r:
    for line in r.iter_lines():
        if not line:
            continue
        line = line.decode("utf-8")
        if not line.startswith("data:"):
            continue

        event = json.loads(line[len("data:"):].strip())
        env = event.get("envelope", {})
        msg = env.get("dataMessage", {}).get("message")

        if msg:
            sender = env.get("sourceName") or env.get("source")
            print(f"{sender}: {msg}")
```

Install the one dependency: `pip install requests`

#### Listen from Node.js

```javascript
// npm install eventsource
const EventSource = require("eventsource");

const es = new EventSource("http://localhost:8088/api/v1/events");

es.onmessage = (event) => {
  const data = JSON.parse(event.data);
  const env = data.envelope;
  const msg = env?.dataMessage?.message;

  if (msg) {
    const sender = env.sourceName || env.source;
    console.log(`${sender}: ${msg}`);
  }
};

es.onerror = (err) => {
  console.error("SSE error, will auto-reconnect:", err);
};
```

> **SSE reconnects automatically.** If the daemon restarts, the `EventSource` client (in
> browsers and the Node.js library) will reconnect on its own. For plain `curl` or Python,
> wrap in a retry loop as shown above.

---

### Subscribe via UNIX socket (alternative — `subscribeReceive`)

If you prefer a UNIX socket over HTTP (more secure, no port involved), run the daemon with
`--socket` instead of `--http`:

```bash
docker run -d \
  --name signal-cli \
  --restart unless-stopped \
  -v signal-cli-data:/var/lib/signal-cli \
  -v /tmp/signal-cli:/run/signal-cli \
  signal-cli \
  -a +15551234567 daemon --socket /run/signal-cli/signal.sock --receive-mode=manual
```

The `-v /tmp/signal-cli:/run/signal-cli` mount exposes the socket on your host machine at
`/tmp/signal-cli/signal.sock`.

Then from the host, open a persistent connection to the socket and call `subscribeReceive`.
The daemon will push JSON-RPC notifications directly over that connection as messages arrive:

```bash
# Using socat (brew install socat)

# 1. Subscribe
echo '{"jsonrpc":"2.0","method":"subscribeReceive","id":1}' \
  | socat - UNIX-CONNECT:/tmp/signal-cli/signal.sock

# Response: {"jsonrpc":"2.0","result":0,"id":1}
# The "result" (0) is your subscription ID

# 2. Keep the connection open and stream all events
socat - UNIX-CONNECT:/tmp/signal-cli/signal.sock <<'EOF'
{"jsonrpc":"2.0","method":"subscribeReceive","id":1}
EOF
# Leave open — notifications arrive as JSON lines:
# {"jsonrpc":"2.0","method":"receive","params":{"subscription":0,"result":{"envelope":{...}}}}
```

To unsubscribe:
```bash
echo '{"jsonrpc":"2.0","method":"unsubscribeReceive","params":{"subscription":0},"id":2}' \
  | socat - UNIX-CONNECT:/tmp/signal-cli/signal.sock
```

---

### Which subscription approach should you use?

| | SSE (`/api/v1/events`) | `subscribeReceive` (socket) |
|---|---|---|
| Transport | HTTP | UNIX socket |
| Setup | None — just `GET` the URL | Requires socket mount + socat/client |
| Security | Localhost-only port | No port at all |
| Auto-reconnect | Yes (built into SSE spec) | Manual |
| Best for | Scripts, apps, browsers | Embedded / high-security setups |

**For most use cases, SSE is the right choice.** It works with any HTTP client, reconnects
automatically, and requires zero extra setup beyond the daemon already running.

---

### Quick reference — available methods

| Method | What it does |
|---|---|
| `send` | Send a message to a person or group |
| `receive` | Fetch pending received messages |
| `listContacts` | List all known contacts |
| `listGroups` | List all groups |
| `listAccounts` | List registered accounts |
| `sendReaction` | Send an emoji reaction to a message |
| `sendReceipt` | Send a read receipt |
| `sendTyping` | Trigger the typing indicator |
| `remoteDelete` | Delete a sent message for everyone |
| `updateGroup` | Create or modify a group |
| `updateContact` | Update a contact's local name |
| `updateProfile` | Update your Signal profile |
| `getUserStatus` | Check if a number is registered on Signal |
| `version` | Return the running signal-cli version |

---

## 7. Running with Docker Compose

The repo includes a `docker-compose.yml` for convenience. Edit the phone number first:

```bash
# Edit docker-compose.yml and replace +15551234567 with your number
nano docker-compose.yml
```

Then:

```bash
# Build and start
docker compose up -d --build

# Follow logs
docker compose logs -f

# Stop
docker compose down

# Stop and remove the data volume (WARNING: destroys account data)
docker compose down -v
```

---

## 8. Data Persistence & Backup

### How Registration Data Persists

Your Signal account credentials, keys, and message history are stored in the Docker
volume `signal-cli-data`, which maps to `/var/lib/signal-cli` inside the container.

**This volume persists across container rebuilds** — you only need to link/register once.

```
┌─────────────────────────────────────┐
│  Rebuilt when updating:             │
│  • signal-cli binary (latest)       │
│  • Java runtime                     │
│  • Container OS                     │
└─────────────────────────────────────┘
               ↓
┌─────────────────────────────────────┐
│  PERSISTS FOREVER:                  │
│  • signal-cli-data volume           │
│    - Account keys & credentials     │
│    - Linked device status           │
│    - Session data                   │
│    - Contact information            │
│    - Attachments                    │
└─────────────────────────────────────┘
```

When you rebuild the image (to get a newer signal-cli), the volume is untouched:
- ✅ No need to re-link your device
- ✅ Message history preserved
- ✅ Zero downtime beyond the restart

### Verify the Volume Exists

```bash
docker volume ls | grep signal-cli
```

Output should show:
```
local     signal-cli-data
```

### Inspect Volume Contents

```bash
docker run --rm -v signal-cli-data:/data alpine ls -la /data
```

You'll see numbered directories (your account) containing:
- `keys/` — cryptographic keys for your linked device
- `data/` — session information, contacts, groups
- `avatars/`, `attachments/` — media files

### Backup Your Registration Data

To safeguard against data loss (disk failure, accidental deletion), back up the volume:

```bash
# Export volume to a timestamped tarball
docker run --rm \
  -v signal-cli-data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/signal-cli-backup-$(date +%Y%m%d).tar.gz -C /data .
```

This creates `signal-cli-backup-20260308.tar.gz` in your current directory.

### Restore from Backup

If you ever need to restore:

```bash
# 1. Create a fresh volume
docker volume create signal-cli-data

# 2. Extract the backup into it
docker run --rm \
  -v signal-cli-data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/signal-cli-backup-20260308.tar.gz -C /data

# 3. Restart your container
docker compose up -d
```

Your device link and message history are now restored.

### The Only Way to Lose Your Registration

The volume is safe unless you explicitly delete it:

```bash
docker volume rm signal-cli-data  # ⚠️ DO NOT RUN — requires re-linking
```

The automated update script (see [launchd-autorebuild.md](launchd-autorebuild.md))
carefully preserves the volume during rebuilds.

---

## 9. scripts/signal-ollama.py — Reply to Yourself with Ollama

`scripts/signal-ollama.py` turns your Signal note-to-self conversation into a chat interface
backed by a local Ollama model. Send a message to yourself from your iPhone; the script
catches it over SSE, asks Ollama, and replies back into the same conversation — with a
typing indicator while it thinks.

```
iPhone (note-to-self)
      │  "What's the capital of France?"
      ▼
signal-cli daemon  ──SSE──►  scripts/signal-ollama.py
                                    │
                                    ▼
                              Ollama (gemma3:12b)
                                    │  "Paris."
                                    ▼
                             signal-cli JSON-RPC
                                    │
                                    ▼
                         iPhone ← reply in same chat
```

### Prerequisites

- signal-cli daemon running (Step 5 of this guide)
- [Ollama](https://ollama.com) installed and running locally
- `gemma3:12b` pulled: `ollama pull gemma3:12b`
- Python 3.11+
- For voice notes: `brew install ffmpeg`

### Install

```bash
# From the signal-cli repo root
pip install -r requirements.txt
```

Core dependency: `requests`. Optional: `faster-whisper` for voice note transcription
(already in requirements.txt — remove that line if you don't need it).

### Configure

The defaults match the setup in this guide. Override with environment variables if needed:

| Variable | Default | Description |
|---|---|---|
| `SIGNAL_HTTP` | `http://localhost:8088` | signal-cli HTTP daemon URL |
| `SIGNAL_ACCOUNT` | `+491738140746` | Your phone number (international format) |
| `OLLAMA_HTTP` | `http://localhost:11434` | Ollama API URL |
| `OLLAMA_MODEL` | `gemma3:12b` | Any model you have pulled |
| `WHISPER_MODEL_SIZE` | `base` | Whisper model size: tiny/base/small/medium/large |

Or edit the `CONFIGURATION` block at the top of `signal_ollama.py` directly.

### Multimodal support

The script handles all Signal input types:

| You send from iPhone | What happens |
|---|---|
| Text message | Forwarded to Ollama, reply sent back |
| Photo / image | Fetched from signal-cli, sent to Ollama vision, description replied |
| Image + caption | Caption and image sent together to Ollama |
| Voice note | Fetched, transcribed with Whisper, transcript echoed back, then sent to Ollama |
| Video / document / other | Polite "I can't process this" reply |

**How image history works:** base64 image data is never stored in the conversation history
(it would be enormous). Instead, the model's text description of the image is stored, so
future turns have context without the memory cost.

**How voice note history works:** the Whisper transcript is stored in history as
`[Voice note transcript]: ...`, so the model can refer back to what you said.

### Run

```bash
python scripts/signal-ollama.py
```

```
10:42:01  INFO      signal-ollama starting
10:42:01  INFO        Signal API   : http://localhost:8088  (account +491738140746)
10:42:01  INFO        Ollama       : http://localhost:11434  (model gemma3:12b)
10:42:01  INFO        Whisper      : base
10:42:01  INFO        Commands     : /new  /model <name>
10:42:01  INFO      Connected. Listening for messages from +491738140746 …
```

### Commands

| You send | What happens |
|---|---|
| `What time is it in Tokyo?` | Ollama answers, history grows |
| `And in New York?` | Ollama uses prior context to answer |
| `/new` | History wiped, fresh session |
| `/model llama3.2` | Switches model, history wiped |

### Change the model

Any Ollama model works — swap at startup or at runtime with `/model`:

```bash
# At startup
OLLAMA_MODEL=gemma3:4b python scripts/signal-ollama.py

# At runtime — send this to yourself on Signal:
/model llama3.2
```

For vision (images) you need a model that supports it. `gemma3:12b` and `llava` both work.
If you switch to a text-only model, image messages will fail gracefully.

### Customise the system prompt

Edit `SYSTEM_PROMPT` in `scripts/signal-ollama.py`:

```python
SYSTEM_PROMPT = (
    "You are a sarcastic assistant who responds only in haiku."
)
```

### Run in the background (macOS LaunchAgent)

Save as `~/Library/LaunchAgents/com.signal-cli.ollama.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.signal-cli.ollama</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/Users/YOUR_USERNAME/Code/signal-cli/scripts/signal-ollama.py</string>
    </array>

    <key>EnvironmentVariables</key>
    <dict>
        <key>SIGNAL_HTTP</key>    <string>http://localhost:8088</string>
        <key>SIGNAL_ACCOUNT</key> <string>+491738140746</string>
        <key>OLLAMA_HTTP</key>    <string>http://localhost:11434</string>
        <key>OLLAMA_MODEL</key>   <string>gemma3:12b</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>

    <key>StandardOutPath</key>
    <string>/Users/YOUR_USERNAME/Library/Logs/signal-ollama.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOUR_USERNAME/Library/Logs/signal-ollama.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/com.signal-cli.ollama.plist

# Watch logs
tail -f ~/Library/Logs/signal-ollama.log
```

---

## 10. Keeping signal-cli Up to Date

Signal's protocol expires clients that are **more than three months old**. You must
rebuild the image periodically to pull a newer release.

### Manual update

```bash
# Rebuild the image (pulls latest release from GitHub)
docker build --no-cache -f Dockerfile.standalone -t signal-cli .

# Restart the container with the new image
docker stop signal-cli && docker rm signal-cli

# Then re-run the daemon command from Step 5
# Your data volume is untouched — no re-linking needed
```

With Docker Compose:

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Automated monthly update (macOS LaunchAgent)

For automated rebuilds, see **[launchd-autorebuild.md](launchd-autorebuild.md)**.

This provides:
- A robust rebuild script with logging and error handling
- macOS LaunchAgent that runs monthly (1st of each month at 3 AM)
- Optional Signal notification on completion
- Complete installation and troubleshooting instructions

The script automatically:
1. Pulls the latest signal-cli release (via image rebuild)
2. Stops and restarts containers
3. Preserves your account data and linked device status
4. Logs all activity for monitoring

---

## 11. Troubleshooting

### "exec format error" on Apple Silicon

The bundled native library is x86_64. Add the platform flag:

```bash
docker build --platform linux/amd64 -f Dockerfile.standalone -t signal-cli .
docker run --platform linux/amd64 ...
```

Or set it globally for your shell session:
```bash
export DOCKER_DEFAULT_PLATFORM=linux/amd64
```

### Daemon exits immediately after linking

The `daemon` command requires an account to be linked first. Make sure Step 4 completed
successfully before running the daemon.

### "No account found" error

The `-a +15551234567` flag must match the phone number you linked. Check with:

```bash
docker run --rm \
  -v signal-cli-data:/var/lib/signal-cli \
  signal-cli listAccounts
```

### API returns connection refused

Check the daemon is actually running:
```bash
docker ps
docker logs signal-cli
```

### Messages not arriving

The daemon receives messages automatically, but if you've been offline a while:
```bash
curl -s -X POST http://localhost:8088/api/v1/rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"receive","id":1}'
```

Calling `receive` explicitly drains any backlog from the server.

### Inspect the data volume

```bash
docker run --rm \
  -v signal-cli-data:/var/lib/signal-cli \
  --entrypoint ls \
  signal-cli -la /var/lib/signal-cli/data
```

### Rebuild without cache (force fresh download of latest signal-cli)

```bash
docker build --no-cache -f Dockerfile.standalone -t signal-cli .
```
