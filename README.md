# signal-cli Docker Container

Run [signal-cli](https://github.com/AsamK/signal-cli) as a self-contained Docker container — send and receive Signal messages from any language or tool, no local Java installation needed.

> 🚀 **Pre-built image:** `ghcr.io/timomuc/signal-container:main` &ensp;|&ensp; [`#quick-start`](#quick-start) &ensp;|&ensp; [`#api-reference`](#api-reference)

---

## Contents

- [What this is](#what-this-is)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
- [Security](#security)
- [Container image](#container-image)
- [Auto-update](#auto-update)
- [Data persistence & backup](#data-persistence--backup)
- [Troubleshooting](#troubleshooting)

---

## What this is

A thin Docker wrapper around [signal-cli](https://github.com/AsamK/signal-cli). It runs signal-cli as an HTTP daemon with **two endpoints**:

| Endpoint | Direction | Purpose |
|---|---|---|
| `POST /api/v1/rpc` | Send | JSON-RPC — send messages and attachments |
| `GET /api/v1/events` | Receive | [Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events) — live incoming messages |

That's it. signal-cli supports additional transports (UNIX socket, TCP, DBus) and additional receive modes (`subscribeReceive`, polling `receive`), but this container exposes only the two above to keep the surface minimal and maintenance predictable.

---

## Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) installed and running
- A phone with Signal (you'll link this container as a secondary device)

### 1. Get the image

**Option A — Pull from GHCR** (recommended, no local build):

```bash
# Apple Silicon: always add --platform linux/amd64
docker pull --platform linux/amd64 ghcr.io/timomuc/signal-container:main
```

**Option B — Build locally:**

```bash
git clone https://github.com/TiMoMuc/signal-container.git
cd signal-container
docker compose build
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env`:

```env
SIGNAL_PHONE_NUMBER=+15551234567   # your number in international format
SIGNAL_BIND_HOST=127.0.0.1         # 127.0.0.1 = localhost only; 0.0.0.0 = LAN-accessible
```

### 3. Link your phone number

Create the persistent volume (stores your account data):

```bash
docker volume create signal-cli-data
```

Start the link process — this prints a QR code in your terminal:

```bash
docker run --rm -it \
  -v signal-cli-data:/var/lib/signal-cli \
  signal-cli:latest link --name "My Server"
```

On your phone: **Signal → Settings → Linked Devices → + → Link New Device** — scan the QR code.  
The name you pass with `--name` becomes the device name shown in Signal's linked devices list.

The command exits automatically once linking succeeds.

### 4. Start the daemon

```bash
docker compose up -d
```

Check it's healthy:

```bash
curl http://localhost:8088/api/v1/check
# → 200 OK
```

> Next: [set up auto-updates](#auto-update) to keep signal-cli current.

### 5. Send a message

```bash
curl -X POST http://localhost:8088/api/v1/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "send",
    "params": {
      "noteToSelf": true,
      "message": "Hello from signal-cli!"
    },
    "id": 1
  }'
```

### 6. Receive messages (live stream)

```bash
curl -N http://localhost:8088/api/v1/events
```

Leave this running — incoming messages print as they arrive.  
`-N` disables curl buffering so events appear immediately.

---

## API Reference

### Send — `POST /api/v1/rpc`

Every request has this shape:

```json
{
  "jsonrpc": "2.0",
  "method": "send",
  "params": { … },
  "id": 1
}
```

`id` is any number you choose — it's echoed back so you can match responses to requests.

#### Send to a recipient

```bash
curl -X POST http://localhost:8088/api/v1/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "send",
    "params": {
      "recipient": ["+15559876543"],
      "message": "Hello!"
    },
    "id": 1
  }'
```

#### Send to multiple recipients

```bash
curl -X POST http://localhost:8088/api/v1/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "send",
    "params": {
      "recipient": ["+15559876543", "+15551112222"],
      "message": "Group announcement"
    },
    "id": 1
  }'
```

#### Send an attachment (file)

Attachments are passed as **inline base64 data URIs** — no bind mounts, temp directories, or helper services needed:

```bash
B64=$(base64 < document.pdf | tr -d '\n')

curl -X POST http://localhost:8088/api/v1/rpc \
  -H "Content-Type: application/json" \
  -d "{
    \"jsonrpc\": \"2.0\",
    \"method\": \"send\",
    \"params\": {
      \"recipient\": [\"+15559876543\"],
      \"message\": \"Here is the document\",
      \"attachments\": [\"data:application/pdf;filename=document.pdf;base64,${B64}\"]
    },
    \"id\": 1
  }"
```

The data URI format is: `data:<MIME-type>;filename=<name>;base64,<base64-data>`

**Size limit:** Signal enforces a ~100 MB limit on attachments (including encryption overhead). Base64 encoding inflates data by ~33%, so plan accordingly. Exceeding the limit will result in a send failure.

#### Additional send params

| Param | Description |
|---|---|
| `noteToSelf: true` | Send to your own "Note to Self" |
| `groupId: "BASE64_ID"` | Send to a Signal group |
| `recipient: ["+1…"]` | Send to one or more phone numbers |
| `mention` | Mention a group member (syntax: `start:length:number`) |
| `quoteTimestamp`, `quoteAuthor` | Quote a previous message |
| `editTimestamp` | Edit a previously sent message |

### Receive — `GET /api/v1/events`

[Server-Sent Events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events) (SSE) — the daemon pushes each incoming message as it arrives over a persistent HTTP connection. Built into every browser and most HTTP libraries. Reconnects automatically.

#### With curl

```bash
curl -N http://localhost:8088/api/v1/events
```

#### Filter in real time

```bash
curl -N http://localhost:8088/api/v1/events \
  | grep --line-buffered '^data:' \
  | sed 's/^data: //' \
  | jq --unbuffered -r '
      select(.envelope.dataMessage.message != null)
      | "\(.envelope.sourceName // .envelope.source): \(.envelope.dataMessage.message)"'
```

#### With Python

```python
import requests, json

with requests.get("http://localhost:8088/api/v1/events", stream=True) as r:
    for line in r.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        event = json.loads(line[5:].strip())
        env = event.get("envelope", {})
        msg = env.get("dataMessage", {}).get("message")
        if msg:
            print(f"{env.get('sourceName') or env.get('source')}: {msg}")
```

#### With Node.js

```javascript
const EventSource = require("eventsource");
const es = new EventSource("http://localhost:8088/api/v1/events");
es.onmessage = (event) => {
  const { envelope } = JSON.parse(event.data);
  const msg = envelope?.dataMessage?.message;
  if (msg) console.log(`${envelope.sourceName || envelope.source}: ${msg}`);
};
```

#### Persistent listener (shell, auto-reconnects)

```bash
#!/usr/bin/env bash
while true; do
  curl -fsSN http://localhost:8088/api/v1/events \
    | grep --line-buffered '^data:' \
    | sed 's/^data: //' \
    | while IFS= read -r line; do
        SENDER=$(echo "$line" | jq -r '.envelope.sourceName // .envelope.source')
        MESSAGE=$(echo "$line" | jq -r '.envelope.dataMessage.message // empty')
        [ -z "$MESSAGE" ] && continue
        echo "$(date): [$SENDER] $MESSAGE"
      done
  echo "Disconnected — reconnecting in 5s..."
  sleep 5
done
```

### Health check — `GET /api/v1/check`

```bash
curl http://localhost:8088/api/v1/check
# → 200 OK
```

---

## Security

**There is no authentication on the HTTP API.** The port binding controls who can reach it:

| `SIGNAL_BIND_HOST` | Effect |
|---|---|
| `127.0.0.1` (default) | Only processes on the same machine can connect |
| `0.0.0.0` | Any device on your LAN can connect |

**Never expose this port to the public internet.**

If another Docker container needs access, skip the port entirely and connect both containers to the same Docker network:

```yaml
# In the consuming stack's compose file:
services:
  signal-cli:
    image: ghcr.io/timomuc/signal-container:main
    platform: linux/amd64
    environment:
      SIGNAL_PHONE_NUMBER: "+15551234567"
    volumes:
      - signal-cli-data:/var/lib/signal-cli
    # no ports: — the other container reaches it via http://signal-cli:8080
```

---

## Container image

### Pre-built (GHCR)

The image is published to GitHub Container Registry on every push to `main` and every `v*` tag:

```
ghcr.io/timomuc/signal-container:main
```

| Tag | Description |
|---|---|
| `:main` | Latest commit on `main` — **rolling** |
| `:sha-<hash>` | Specific commit |
| `:<YYYYMMDD-HHMMSS>` | Build timestamp |
| `:v*` | Git tags (when pushed) |

The image is `linux/amd64` only. On Apple Silicon (M1–M4), always add `--platform linux/amd64` to `docker pull` and `docker run`, or set `platform: linux/amd64` in your compose file. Docker emulates x86_64 automatically.

#### Using the pre-built image with Docker Compose

```yaml
services:
  signal-cli:
    image: ghcr.io/timomuc/signal-container:main
    platform: linux/amd64
    container_name: signal-cli
    restart: unless-stopped
    env_file: .env
    ports:
      - "${SIGNAL_BIND_HOST}:8088:8080"
    volumes:
      - signal-cli-data:/var/lib/signal-cli
    command: ["-a", "${SIGNAL_PHONE_NUMBER}", "daemon", "--http", "0.0.0.0:8080"]

volumes:
  signal-cli-data:
    name: signal-cli-data
```

### Build locally

```bash
docker compose build
```

This downloads the latest signal-cli release at build time and tags the image as `signal-cli:latest`.

### Image update with GHCR

If you're using the pre-built image, pull new versions periodically:

```bash
docker compose pull
docker compose up -d
```

Or use [Watchtower](https://containrrr.dev/watchtower/) to automate this.

---

## Auto-update

Signal's protocol expires clients older than ~90 days. The included scheduler automatically rebuilds the container monthly to stay current.

> **Note:** The auto-update scripts rebuild from the local `Dockerfile`. If you're using the [GHCR pre-built image](#pre-built-ghcr), use `docker compose pull` instead — the rebuild scripts are not needed.

### Install

```bash
./scripts/install-autoupdate.sh
```

This detects your OS and installs the appropriate scheduler:

| OS | Scheduler | Runs |
|---|---|---|
| macOS | LaunchAgent | 1st of every month, 3 AM |
| Linux | systemd user timer | Monthly |

The scheduler runs `scripts/rebuild-container.sh`, which:

1. Pulls the latest signal-cli release (via image rebuild)
2. Stops and restarts the container
3. Preserves your account data in the `signal-cli-data` volume
4. Logs to `~/Library/Logs/` (macOS) or journald (Linux)

### Test it manually

```bash
./scripts/rebuild-container.sh
```

### Uninstall

```bash
./scripts/uninstall-autoupdate.sh
```

### If you move the repo

Rerun `./scripts/install-autoupdate.sh` from the new location.

---

## Data persistence & backup

Your Signal account credentials, keys, and message history are stored in the Docker volume `signal-cli-data`. This volume **persists across container rebuilds** — you only link your phone number once.

### Backup

```bash
docker run --rm \
  -v signal-cli-data:/data \
  -v "$(pwd):/backup" \
  alpine tar czf "/backup/signal-cli-backup-$(date +%Y%m%d).tar.gz" -C /data .
```

### Restore

```bash
docker volume create signal-cli-data
docker run --rm \
  -v signal-cli-data:/data \
  -v "$(pwd):/backup" \
  alpine tar xzf "/backup/signal-cli-backup-20260308.tar.gz" -C /data
docker compose up -d
```

### ⚠️ The only way to lose your registration

```bash
docker compose down -v         # removes the volume
docker volume rm signal-cli-data
```

Either of these deletes your account data and requires re-linking.

---

## Troubleshooting

### `exec format error` / `no matching manifest` on Apple Silicon

Add `--platform linux/amd64`:

```bash
docker pull --platform linux/amd64 ghcr.io/timomuc/signal-container:main
docker run --platform linux/amd64 …
```

Or set it globally:

```bash
export DOCKER_DEFAULT_PLATFORM=linux/amd64
# add to ~/.zshrc to make permanent
```

### Can't link device

- Verify the volume exists: `docker volume ls | grep signal-cli`
- Rerun: `docker run --rm -it -v signal-cli-data:/var/lib/signal-cli signal-cli:latest link --name "My Server"`

### API not responding

```bash
docker compose ps              # is it running?
curl http://localhost:8088/api/v1/check  # health check
docker compose logs signal-cli
```

### Daemon exits immediately

The daemon requires a linked account. Run `docker run --rm -v signal-cli-data:/var/lib/signal-cli signal-cli:latest listAccounts` to verify one exists.

### Container won't start / WebSocket reconnects

Check Docker is running (`docker info`) and review logs (`docker compose logs`). Temporary WebSocket disconnects are normal — signal-cli reconnects automatically.

### Registration via SMS/voice

If you need to register a new number (instead of linking as secondary device), see [signal-cli's registration docs](https://github.com/AsamK/signal-cli?tab=readme-ov-file#usage). Replace `signal-cli` with:

```bash
docker run --rm -it -v signal-cli-data:/var/lib/signal-cli signal-cli:latest …
```

---

## Credits

- [signal-cli](https://github.com/AsamK/signal-cli) by AsamK — the tool this container wraps
- [Signal](https://signal.org) — private messaging for everyone

## License

This repository contains configuration and documentation. signal-cli itself is GPL-3.0-licensed.