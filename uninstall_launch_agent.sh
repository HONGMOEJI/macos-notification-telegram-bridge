#!/usr/bin/env bash
set -euo pipefail

APP_NAME="messages-to-telegram"
LABEL="com.codex.messages-to-telegram"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)" "$PLIST_PATH" >/dev/null 2>&1 || true
rm -f "$PLIST_PATH"

echo "Uninstalled $LABEL"
echo "App files remain at: $HOME/Library/Application Support/$APP_NAME"
