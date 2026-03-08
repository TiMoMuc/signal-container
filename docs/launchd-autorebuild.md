# Automated Monthly Container Rebuild

Signal's servers change every ~3 months, and signal-cli clients older than 90 days may stop working. To stay ahead of this, we use a macOS LaunchAgent to automatically rebuild the container monthly.

---

## What It Does

The automation:
1. **Runs monthly** (1st day of each month at 3 AM)
2. **Rebuilds the Docker image** — which downloads the latest signal-cli release
3. **Restarts the containers** with the updated image
4. **Logs everything** to `~/Library/Logs/signal-container-rebuild.log`

This ensures you're never running an outdated signal-cli version.

---

## Files

- **`scripts/rebuild-container.sh`** — the rebuild script
- **`scripts/com.user.signal-container-rebuild.plist`** — the LaunchAgent configuration

---

## Installation

### 1. Make the script executable

```bash
chmod +x scripts/rebuild-container.sh
```

### 2. Install the LaunchAgent

Copy the plist to your LaunchAgents directory:

```bash
cp scripts/com.user.signal-container-rebuild.plist ~/Library/LaunchAgents/
```

### 3. Load the LaunchAgent

```bash
launchctl load ~/Library/LaunchAgents/com.user.signal-container-rebuild.plist
```

Verify it's loaded:

```bash
launchctl list | grep signal-container-rebuild
```

You should see output like:
```
-	0	com.user.signal-container-rebuild
```

---

## Manual Testing

Before waiting a month, test the script manually:

```bash
./scripts/rebuild-container.sh
```

Check the log:

```bash
tail -f ~/Library/Logs/signal-container-rebuild.log
```

You should see:
- Current signal-cli version detection
- Image rebuild process
- New version installation
- Container restart
- Success confirmation

---

## Configuration

### Adjust the schedule

Edit the plist's `StartCalendarInterval` section:

```xml
<key>StartCalendarInterval</key>
<dict>
    <key>Day</key>
    <integer>1</integer>       <!-- Day of month (1-31) -->
    <key>Hour</key>
    <integer>3</integer>        <!-- Hour (0-23) -->
    <key>Minute</key>
    <integer>0</integer>        <!-- Minute (0-59) -->
</dict>
```

After changes, reload:
```bash
launchctl unload ~/Library/LaunchAgents/com.user.signal-container-rebuild.plist
launchctl load ~/Library/LaunchAgents/com.user.signal-container-rebuild.plist
```

### Enable Signal notifications (optional)

Uncomment the notification section at the end of `scripts/rebuild-container.sh` to receive a note-to-self message after each rebuild:

```bash
# Lines 93-105 in scripts/rebuild-container.sh
# Remove the # symbols to enable
```

Make sure to update `SIGNAL_ACCOUNT` to your actual phone number.

---

## Monitoring

### View the schedule

```bash
launchctl print user/$(id -u)/com.user.signal-container-rebuild
```

Look for the `next invocation` timestamp in the output.

### Check logs

The script logs to:
- **Main log:** `~/Library/Logs/signal-container-rebuild.log` (detailed rebuild output)
- **Stdout:** `~/Library/Logs/com.user.signal-container-rebuild.stdout.log`
- **Stderr:** `~/Library/Logs/com.user.signal-container-rebuild.stderr.log`

Tail the main log:
```bash
tail -f ~/Library/Logs/signal-container-rebuild.log
```

### Force a test run

Trigger the job manually without waiting for the schedule:

```bash
launchctl start com.user.signal-container-rebuild
```

---

## Troubleshooting

### Docker not running

If the script fails with "Docker is not running":
- Ensure Docker Desktop is running before the scheduled time
- Consider making Docker Desktop start at login (Preferences → General → Start Docker Desktop when you log in)

### Permission denied

If the script can't access Docker:
- Your user must be in the `docker` group (default on macOS with Docker Desktop)
- Test with: `docker ps`

### Container doesn't restart

Check `docker-compose.yml` is in the same directory as the script:
```bash
ls -la scripts/rebuild-container.sh docker-compose.yml
```

### LaunchAgent not triggering

Check if it's loaded:
```bash
launchctl list | grep signal-container
```

View its state:
```bash
launchctl print user/$(id -u)/com.user.signal-container-rebuild
```

Reload if needed:
```bash
launchctl unload ~/Library/LaunchAgents/com.user.signal-container-rebuild.plist
launchctl load ~/Library/LaunchAgents/com.user.signal-container-rebuild.plist
```

---

## Uninstallation

Remove the LaunchAgent:

```bash
launchctl unload ~/Library/LaunchAgents/com.user.signal-container-rebuild.plist
rm ~/Library/LaunchAgents/com.user.signal-container-rebuild.plist
```

Remove the logs:
```bash
rm ~/Library/Logs/signal-container-rebuild.log
rm ~/Library/Logs/com.user.signal-container-rebuild.*
```

---

## Alternative: Watchtower (Docker-based auto-update)

If you prefer an entirely Docker-based solution, consider [Watchtower](https://containrrr.dev/watchtower/):

```yaml
services:
  watchtower:
    image: containrrr/watchtower
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    command: --interval 2592000  # 30 days in seconds
```

However, this only works if signal-cli publishes regular Docker images to a registry. Since this project builds locally, the LaunchAgent approach is more appropriate.

---

## Notes

- **Frequency:** Monthly is conservative (safer than the 3-month limit)
- **Downtime:** Expect ~2-5 minutes of downtime during rebuilds
- **Data safety:** Account data persists in the Docker volume (`signal-cli-data`)
- **Idempotency:** Running the script multiple times is safe

The automation ensures your signal-cli stays current without manual intervention. Set it and forget it! 🔄
