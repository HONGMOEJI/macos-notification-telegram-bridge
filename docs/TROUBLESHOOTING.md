# Troubleshooting / 문제 해결

## `unable to open database file`

English:

Most likely macOS privacy permissions. Grant Full Disk Access to the process running the script.

한국어:

대부분 macOS 개인정보 권한 문제입니다. 스크립트를 실행하는 프로세스에 Full Disk Access를 부여하세요.

## `Operation not permitted`

English:

The path exists, but macOS denied access. This is common for:

한국어:

경로는 존재하지만 macOS가 접근을 거부한 상태입니다. 다음 경로에서 자주 발생합니다.

```text
~/Library/Messages/chat.db
~/Library/Group Containers/group.com.apple.usernoted/db2/db
```

## No chat IDs printed / chat ID가 안 나옴

English:

Send a new message to the bot, then run `chat-id` again. Telegram `getUpdates` only returns updates the bot has seen.

한국어:

봇에게 새 메시지를 보낸 다음 `chat-id`를 다시 실행하세요. Telegram `getUpdates`는 봇이 본 업데이트만 반환합니다.

## Test message works but no Messages forwarding / 테스트는 되는데 Messages 전달이 안 됨

Check:

확인:

- `WATCH_MESSAGES=1`
- Full Disk Access
- The Mac is actually receiving/syncing the message
- Mac이 실제로 메시지를 받거나 동기화하고 있는지
- `FORWARD_INCOMING_ONLY=1` is not excluding the row you expect
- 기대한 row가 `FORWARD_INCOMING_ONLY=1` 때문에 제외되는지
- `SENDER_ALLOWLIST`, `CHAT_ALLOWLIST`, `SERVICE_ALLOWLIST`

Preview parsing:

파싱 미리 보기:

```bash
python3 messages_to_telegram.py sample --limit 5
```

## Notifications do not forward / 알림 전달이 안 됨

Check:

확인:

- `WATCH_NOTIFICATIONS=1`
- Full Disk Access for Notification Center storage
- Notification database path for the current macOS version
- 현재 macOS 버전의 Notification database 경로
- `NOTIFICATION_APP_ALLOWLIST`
- `NOTIFICATION_APP_DENYLIST`
- `NOTIFICATION_PRESENTED_ONLY`

Preview parsing:

파싱 미리 보기:

```bash
python3 messages_to_telegram.py notification-sample --limit 5
```

## Duplicate iMessage or SMS events / iMessage 또는 SMS 중복

English:

If `WATCH_MESSAGES=1` and `WATCH_NOTIFICATIONS=1`, the same iMessage or SMS can appear once from `chat.db` and once from Notification Center. Keep Messages bundle IDs in `NOTIFICATION_APP_DENYLIST`.

한국어:

`WATCH_MESSAGES=1`과 `WATCH_NOTIFICATIONS=1`을 같이 켜면 같은 iMessage 또는 SMS가 `chat.db`와 Notification Center에서 한 번씩 잡힐 수 있습니다. Messages 번들 ID를 `NOTIFICATION_APP_DENYLIST`에 유지하세요.

```env
NOTIFICATION_APP_DENYLIST=com.apple.MobileSMS,com.apple.iChat
```

## LaunchAgent is not running / LaunchAgent가 실행되지 않음

Inspect logs:

로그 확인:

```bash
tail -f "$HOME/Library/Logs/messages-to-telegram.out.log"
tail -f "$HOME/Library/Logs/messages-to-telegram.err.log"
```

Restart:

재시작:

```bash
launchctl kickstart -k "gui/$(id -u)/com.codex.messages-to-telegram"
```

Reinstall:

재설치:

```bash
./uninstall_launch_agent.sh
./install_launch_agent.sh
```
