#!/usr/bin/env bash
# uninstall-autoupdate.sh — remove the monthly rebuild scheduler (macOS or Linux)
set -euo pipefail

OS="$(uname -s)"

if [ "$OS" = "Darwin" ]; then
    TARGET="$HOME/Library/LaunchAgents/com.user.signal-container-rebuild.plist"
    launchctl unload "$TARGET" >/dev/null 2>&1 || true
    rm -f "$TARGET"
    echo "Removed macOS LaunchAgent: $TARGET"
    echo "Logs were left in ~/Library/Logs/"

elif [ "$OS" = "Linux" ]; then
    SYSTEMD_DIR="$HOME/.config/systemd/user"
    systemctl --user disable --now signal-container-rebuild.timer >/dev/null 2>&1 || true
    rm -f "$SYSTEMD_DIR/signal-container-rebuild.service" "$SYSTEMD_DIR/signal-container-rebuild.timer"
    systemctl --user daemon-reload
    echo "Removed Linux systemd timer + service"

else
    echo "ERROR: Unsupported OS: $OS"
    exit 1
fi