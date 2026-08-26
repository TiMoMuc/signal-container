#!/usr/bin/env bash
# install-autoupdate.sh — install the monthly rebuild scheduler (macOS or Linux)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REBUILD_SCRIPT="$PROJECT_DIR/scripts/rebuild-container.sh"

if [ ! -f "$REBUILD_SCRIPT" ]; then
    echo "ERROR: Rebuild script not found: $REBUILD_SCRIPT"
    exit 1
fi
chmod +x "$REBUILD_SCRIPT"

OS="$(uname -s)"

# ── macOS ──────────────────────────────────────────────────────────────
if [ "$OS" = "Darwin" ]; then
    TEMPLATE="$SCRIPT_DIR/com.user.signal-container-rebuild.plist"
    TARGET="$HOME/Library/LaunchAgents/com.user.signal-container-rebuild.plist"
    STDOUT_LOG="$HOME/Library/Logs/com.user.signal-container-rebuild.stdout.log"
    STDERR_LOG="$HOME/Library/Logs/com.user.signal-container-rebuild.stderr.log"

    if [ ! -f "$TEMPLATE" ]; then
        echo "ERROR: LaunchAgent template not found: $TEMPLATE"
        exit 1
    fi

    xml_escape() { printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'; }
    sed_escape()  { printf '%s' "$1" | sed -e 's/[&|]/\\&/g'; }

    mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"

    SCRIPT_PATH_XML=$(sed_escape "$(xml_escape "$REBUILD_SCRIPT")")
    STDOUT_PATH_XML=$(sed_escape "$(xml_escape "$STDOUT_LOG")")
    STDERR_PATH_XML=$(sed_escape "$(xml_escape "$STDERR_LOG")")

    sed \
      -e "s|__SCRIPT_PATH__|$SCRIPT_PATH_XML|g" \
      -e "s|__STDOUT_PATH__|$STDOUT_PATH_XML|g" \
      -e "s|__STDERR_PATH__|$STDERR_PATH_XML|g" \
      "$TEMPLATE" > "$TARGET"

    launchctl unload "$TARGET" >/dev/null 2>&1 || true
    launchctl load "$TARGET"

    echo "Installed macOS LaunchAgent: $TARGET"
    echo "Rebuild script:            $REBUILD_SCRIPT"

# ── Linux ──────────────────────────────────────────────────────────────
elif [ "$OS" = "Linux" ]; then
    SYSTEMD_DIR="$HOME/.config/systemd/user"
    SERVICE_FILE="$SYSTEMD_DIR/signal-container-rebuild.service"
    TIMER_FILE="$SYSTEMD_DIR/signal-container-rebuild.timer"

    mkdir -p "$SYSTEMD_DIR"

    cat > "$SERVICE_FILE" << SERVICEOF
[Unit]
Description=Rebuild signal-cli Docker image (monthly)

[Service]
Type=oneshot
ExecStart=/bin/bash "$REBUILD_SCRIPT"
SERVICEOF

    cat > "$TIMER_FILE" << TIMEREOF
[Unit]
Description=Monthly signal-cli container rebuild

[Timer]
OnCalendar=monthly
Persistent=true

[Install]
WantedBy=timers.target
TIMEREOF

    systemctl --user daemon-reload
    systemctl --user enable --now signal-container-rebuild.timer

    echo "Installed Linux systemd timer: $TIMER_FILE"
    echo "Service unit:                 $SERVICE_FILE"
    echo "Rebuild script:               $REBUILD_SCRIPT"

# ── Unsupported ────────────────────────────────────────────────────────
else
    echo "ERROR: Unsupported OS: $OS"
    echo "This script supports macOS (LaunchAgent) and Linux (systemd user timer)."
    exit 1
fi

echo ""
echo "Reminder: if you move this repo, rerun ./scripts/install-autoupdate.sh from the new location."