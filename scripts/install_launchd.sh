#!/bin/bash
set -euo pipefail
ROOT="/Users/harshboricha/Desktop/TelegramBot"
PLIST_SRC="$ROOT/launchd/com.telegrambot.ipogmp.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.telegrambot.ipogmp.plist"

mkdir -p "$ROOT/logs" "$HOME/Library/LaunchAgents"
cp "$PLIST_SRC" "$PLIST_DST"

echo "NOTE: Projects on Desktop are blocked for LaunchAgents by macOS privacy."
echo "After install, open System Settings → Privacy & Security → Full Disk Access"
echo "and add: $ROOT/.venv/bin/python"
echo "Then re-run: launchctl kickstart -k gui/\$(id -u)/com.telegrambot.ipogmp"
echo

launchctl bootout "gui/$(id -u)/com.telegrambot.ipogmp" 2>/dev/null || true
pkill -f "python -m src.listen" 2>/dev/null || true

launchctl bootstrap "gui/$(id -u)" "$PLIST_DST" 2>/dev/null || true
launchctl enable "gui/$(id -u)/com.telegrambot.ipogmp" 2>/dev/null || true
launchctl kickstart -k "gui/$(id -u)/com.telegrambot.ipogmp" 2>/dev/null || true

echo "Plist installed at $PLIST_DST"
echo "Until Full Disk Access works, start manually with:"
echo "  cd $ROOT && nohup .venv/bin/python -m src.listen >> logs/bot.out.log 2>> logs/bot.err.log &"
