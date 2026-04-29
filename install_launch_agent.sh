#!/usr/bin/env bash
set -euo pipefail

APP_NAME="messages-to-telegram"
LABEL="com.codex.messages-to-telegram"
APP_DIR="$HOME/Library/Application Support/$APP_NAME"
CONFIG_PATH="$APP_DIR/config.env"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$HOME/Library/Logs"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$(command -v python3 || true)"

if [[ -z "$PYTHON_BIN" ]]; then
  echo "python3 was not found on PATH." >&2
  exit 1
fi

mkdir -p "$APP_DIR" "$HOME/Library/LaunchAgents" "$LOG_DIR"
cp "$SOURCE_DIR/messages_to_telegram.py" "$APP_DIR/messages_to_telegram.py"
chmod 700 "$APP_DIR/messages_to_telegram.py"

if [[ ! -f "$CONFIG_PATH" ]]; then
  cp "$SOURCE_DIR/config.example.env" "$CONFIG_PATH"
  chmod 600 "$CONFIG_PATH"
  echo "Created config: $CONFIG_PATH"
  echo "Edit TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID, then run this installer again."
  exit 0
fi

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON_BIN</string>
    <string>$APP_DIR/messages_to_telegram.py</string>
    <string>run</string>
    <string>--config</string>
    <string>$CONFIG_PATH</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/$APP_NAME.out.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/$APP_NAME.err.log</string>
  <key>WorkingDirectory</key>
  <string>$APP_DIR</string>
</dict>
</plist>
PLIST

chmod 644 "$PLIST_PATH"

launchctl bootout "gui/$(id -u)" "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_PATH"
launchctl kickstart -k "gui/$(id -u)/$LABEL"

echo "Installed and started $LABEL"
echo "Python executable:"
echo "  $PYTHON_BIN"
echo "Logs:"
echo "  $LOG_DIR/$APP_NAME.out.log"
echo "  $LOG_DIR/$APP_NAME.err.log"
