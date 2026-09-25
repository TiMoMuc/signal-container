# Signal container

A private, single-account [signal-cli](https://github.com/AsamK/signal-cli)
HTTP daemon. It is the Signal companion service for a pai-server instance,
but it remains a standalone source repository: a bridge consumes its local
HTTP API and does not own this container or its account state.

## Boundaries

- The API exposes `POST /api/v1/rpc` for JSON-RPC sends and
  `GET /api/v1/events` for Server-Sent Event receives.
- The API has **no authentication**. The host bind is its access boundary.
  The default is localhost only; never bind it publicly.
- `.env` is the only application configuration source. Copy
  `.env.example`; do not record actual values in docs or Compose files.
- `state/` is instance-owned mutable state: the linked-device identity,
  account keys, attachments, and message data. It is ignored by Git.
- One Signal number and its `state/` belong to one instance only. Never copy
  them to create another server. A backup may restore the *same* instance.

The image is deliberately `linux/amd64`, including on Apple Silicon, because
signal-cli's native libraries require it. Docker Desktop supplies emulation.

## Set up a new instance

These steps work for a human operator and are safe for an agent to prepare.
The QR scan is intentionally a human trust step.

1. Clone this repository and enter it.

   ```bash
   git clone https://github.com/TiMoMuc/signal-container.git
   cd signal-container
   ```

2. Create the ignored runtime env file from its tracked shape. Assign a
   number that is new and exclusive to this instance. Keep the default
   localhost bind unless the consuming bridge has a deliberately private
   network route to this host.

   ```bash
   cp .env.example .env
   chmod 600 .env
   ```

3. Build the image and create the fresh instance state directory.

   ```bash
   docker compose build
   mkdir -p state
   chmod 700 state
   ```

4. Link the Signal account as a secondary device. Choose a device name that
   identifies this instance. Scan the terminal QR code on the phone:
   **Signal → Settings → Linked devices → Link new device**.

   ```bash
   docker run --rm -it --platform linux/amd64 \
     -v "$PWD/state:/var/lib/signal-cli" \
     signal-cli:latest link --name '<instance-device-name>'
   ```

   The command exits after the phone confirms the link. It must use this
   instance's `state/`, never state copied from another host.

5. Start and verify the daemon.

   ```bash
   docker compose up -d
   curl --fail http://127.0.0.1:8088/api/v1/check
   docker compose logs --tail=100 app
   ```

A successful health check is necessary but not sufficient: verify an inbound
message and an outbound reply with the eventual consumer before declaring the
transport ready.

## Connect pai-bridge on the same Docker Desktop host

Keep this daemon on its localhost bind. A Dockerized local pai-bridge reaches
that host binding through `host.docker.internal`; configure the bridge's
Signal client endpoint accordingly in the bridge's own ignored `.env` file.
The bridge must also name the same Signal account. Do not put bridge settings
or credentials into this repository.

Before starting or restarting the bridge, verify its Docker-side route without
making the Signal API public:

```bash
docker run --rm --add-host host.docker.internal:host-gateway \
  curlimages/curl:8.12.1 --fail \
  http://host.docker.internal:8088/api/v1/check
```

On a remote private instance, prefer an isolated shared Docker network. If a
host port is necessary, bind only to a specific private interface and make the
consumer route explicit.

## Operate and recover

### Normal restart

```bash
docker compose restart
curl --fail http://127.0.0.1:8088/api/v1/check
```

A normal restart preserves `state/`. Do **not** use destructive volume/state
cleanup for routine operation.

### Update deliberately

The Dockerfile resolves the current signal-cli release at image-build time.
Rebuild deliberately, then verify the daemon and a real message flow:

```bash
docker compose build --pull
docker compose up -d
curl --fail http://127.0.0.1:8088/api/v1/check
```

### Back up and restore

Back up `state/` only for recovery of this same named instance, with the
daemon stopped. The archive contains account identity and message material;
store it as a secret.

```bash
docker compose stop
archive="signal-state-$(date +%Y%m%d).tar.gz"
tar czf "$archive" state
docker compose up -d
```

To restore after loss on the same instance, stop the daemon, replace its empty
`state/` with the archived directory, preserve restrictive local permissions,
and start it again. Restoring that archive on another instance violates the
identity-ownership rule and is not a provisioning method.

## API reference and troubleshooting

- Health: `GET /api/v1/check`
- Send: `POST /api/v1/rpc`
- Receive: `GET /api/v1/events`

See the [signal-cli daemon API](https://github.com/AsamK/signal-cli) for
method and event payload detail. For a local problem, inspect in this order:

```bash
docker compose ps
docker compose logs --tail=100 app
curl --fail http://127.0.0.1:8088/api/v1/check
docker run --rm --platform linux/amd64 \
  -v "$PWD/state:/var/lib/signal-cli" \
  signal-cli:latest listAccounts
```

If the account is absent, link it again using this instance's existing
`state/`. Treat a deleted or intentionally replaced `state/` directory as a
new identity requiring a new link.
