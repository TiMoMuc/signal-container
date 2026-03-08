# signal-cli Docker Container

Run [signal-cli](https://github.com/AsamK/signal-cli) as a self-contained Docker container with an HTTP API for sending and receiving Signal messages programmatically.

## Features

- 🐳 **Dockerized** — No local Java installation needed, fully self-contained
- 🔄 **Auto-update** — Monthly container rebuilds via macOS LaunchAgent keep signal-cli current
- 💬 **HTTP API** — JSON-RPC interface for sending/receiving messages from any language
- 🤖 **Ollama integration** — Optional AI chatbot for your Signal note-to-self
- 📱 **Secondary device** — Links to your existing Signal account without disrupting your phone
- 💾 **Persistent data** — Account credentials survive container rebuilds

## Quick Start

### 1. Build the Container

```bash
docker compose build
```

### 2. Link to Your Signal Account

```bash
docker run --rm -it \
  -v signal-cli-data:/var/lib/signal-cli \
  signal-cli link --name "My Server"
```

Scan the QR code with your Signal app: **Settings → Linked Devices → + → Link New Device**

### 3. Start the HTTP Daemon

```bash
docker compose up -d
```

The API is now available at `http://localhost:8080`

### 4. Send Your First Message

```bash
curl -X POST http://localhost:8080/api/v1/rpc \
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

## Documentation

### 📚 Guides

- **[docker-guide.md](docs/docker-guide.md)** — Complete Docker setup, API usage, and examples
- **[macos-setup.md](docs/macos-setup.md)** — Native macOS installation (non-Docker)
- **[launchd-autorebuild.md](docs/launchd-autorebuild.md)** — Automated monthly container updates

### 🛠️ Scripts

- **[rebuild-container.sh](scripts/rebuild-container.sh)** — Manual container rebuild script
- **[signal-ollama.py](scripts/signal-ollama.py)** — AI chatbot for Signal note-to-self (requires Ollama)
- **[com.user.signal-container-rebuild.plist](scripts/com.user.signal-container-rebuild.plist)** — LaunchAgent for automatic updates

## Architecture

```
┌─────────────────────────────────────────────────┐
│                Docker container                 │
│                                                 │
│  signal-cli daemon                              │
│    │                                            │
│    ├── WebSocket ──────────────────────────► Signal servers
│    │   (receives messages automatically)        │
│    │                                            │
│    └── HTTP JSON-RPC on :8080 ◄─────────────── your app / curl
│                                                 │
│  /var/lib/signal-cli  (volume)                  │
│    └── keys, account data, attachments          │
└─────────────────────────────────────────────────┘
```

## Why Auto-Update?

Signal's protocol **expires clients older than 90 days**. The included LaunchAgent automatically rebuilds the container monthly, downloading the latest signal-cli release to ensure uninterrupted service.

### Set Up Auto-Updates

```bash
# Make script executable
chmod +x scripts/rebuild-container.sh

# Install LaunchAgent
cp scripts/com.user.signal-container-rebuild.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.user.signal-container-rebuild.plist
```

See [launchd-autorebuild.md](docs/launchd-autorebuild.md) for details.

## API Examples

### Send a message

```bash
curl -X POST http://localhost:8080/api/v1/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "send",
    "params": {
      "recipient": ["+15551234567"],
      "message": "Hello!"
    },
    "id": 1
  }'
```

### Receive messages

```bash
curl -X POST http://localhost:8080/api/v1/rpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "receive",
    "id": 1
  }'
```

### Subscribe to live messages (Server-Sent Events)

```bash
curl -N http://localhost:8080/api/v1/events
```

Full API documentation: [docs/docker-guide.md](docs/docker-guide.md)

## AI Chatbot (Optional)

Chat with an Ollama-powered AI through your Signal note-to-self:

1. Install [Ollama](https://ollama.ai) and pull a model: `ollama pull gemma3:12b`
2. Edit `scripts/signal-ollama.py` configuration
3. Run: `python3 scripts/signal-ollama.py`

Supports text, images (vision models), and voice notes (via faster-whisper).

## File Structure

```
signal-container/
├── README.md                   # This file
├── docker-compose.yml          # Container orchestration
├── Dockerfile.standalone       # Image definition
├── requirements.txt            # Python dependencies
│
├── docs/                       # Documentation
│   ├── docker-guide.md         # Main Docker guide
│   ├── macos-setup.md          # Native macOS setup
│   └── launchd-autorebuild.md  # Auto-update guide
│
└── scripts/                    # Automation scripts
    ├── rebuild-container.sh    # Rebuild script
    ├── signal-ollama.py        # AI chatbot
    └── com.user.signal-container-rebuild.plist  # LaunchAgent
```

## Requirements

- **Docker Desktop for Mac** — [Download](https://www.docker.com/products/docker-desktop/)
- **Apple Silicon note:** Runs via Rosetta (x86_64 emulation) — set `DOCKER_DEFAULT_PLATFORM=linux/amd64`
- **Signal account** — Existing phone number (container acts as secondary device)

## Troubleshooting

### Container won't start
- Ensure Docker is running: `docker info`
- Check logs: `docker compose logs -f`

### Can't link device
- Verify volume exists: `docker volume ls | grep signal-cli`
- Re-run link command: `docker run --rm -it -v signal-cli-data:/var/lib/signal-cli signal-cli link --name "My Server"`

### API not responding
- Check container status: `docker compose ps`
- Verify port binding: `curl http://localhost:8080/api/v1/rpc`

See [docs/docker-guide.md](docs/docker-guide.md) for comprehensive troubleshooting.

## Data Persistence

Your Signal account data lives in the Docker volume `signal-cli-data` and **persists across container rebuilds**. You only register once — ever.

### Backup your registration

```bash
docker run --rm \
  -v signal-cli-data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/signal-cli-backup-$(date +%Y%m%d).tar.gz -C /data .
```

## Credits

- [signal-cli](https://github.com/AsamK/signal-cli) by AsamK — The amazing CLI tool this project wraps
- [Signal](https://signal.org) — Private messaging for everyone

## License

This repository contains configuration and documentation. signal-cli itself is GPL-3.0-licensed.
