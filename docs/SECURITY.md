# Security / 보안

## Data Boundary / 데이터 경계

English:

This bridge intentionally moves local macOS message or notification content into Telegram. That changes the privacy boundary. Content that was previously only in Apple's local storage may become visible to Telegram infrastructure and members of the destination chat.

한국어:

이 브리지는 macOS 로컬 메시지 또는 알림 내용을 Telegram으로 옮깁니다. 따라서 개인정보 경계가 바뀝니다. Apple 로컬 저장소 안에 있던 내용이 Telegram 인프라와 대상 채팅 구성원에게 보일 수 있습니다.

## Secrets / 비밀값

The config file contains the bot token and must not be committed.

설정 파일에는 봇 토큰이 들어가므로 커밋하면 안 됩니다.

Protected by `.gitignore`:

`.gitignore`로 보호되는 예:

```text
config.env
*.local.env
state.json
```

Recommended permissions:

권장 권한:

```bash
chmod 600 "$HOME/Library/Application Support/messages-to-telegram/config.env"
```

## macOS Permissions / macOS 권한

macOS may require Full Disk Access for:

macOS는 다음 대상에 Full Disk Access를 요구할 수 있습니다.

- Terminal or iTerm for manual runs
- 수동 실행용 Terminal 또는 iTerm
- Python used by LaunchAgent
- LaunchAgent가 사용하는 Python
- The Codex or editor process if running from an assistant workspace
- assistant workspace에서 실행하는 경우 Codex 또는 에디터 프로세스

The bridge does not bypass these controls.

이 브리지는 이러한 권한 제어를 우회하지 않습니다.

## Recommended Safe Configuration / 권장 안전 설정

For sensitive environments:

민감한 환경:

```env
MESSAGE_TEXT_MODE=redacted
NOTIFICATION_TEXT_MODE=redacted
SENDER_ALLOWLIST=+15551234567,person@example.com
NOTIFICATION_APP_ALLOWLIST=com.apple.mail,com.tinyspeck.slackmacgap
PROTECT_CONTENT=1
```

For a low-noise notification setup:

노이즈를 줄인 알림 설정:

```env
WATCH_MESSAGES=1
WATCH_NOTIFICATIONS=1
NOTIFICATION_APP_ALLOWLIST=com.apple.mail,com.tinyspeck.slackmacgap
NOTIFICATION_APP_DENYLIST=com.apple.MobileSMS,com.apple.iChat,com.tdesktop.telegram,org.telegram.desktop,ru.keepcoder.Telegram
```

## Threat Model / 위협 모델

Consider these risks:

고려할 위험:

- Telegram bot token exposure allows other parties to send through the bot.
- Telegram 봇 토큰이 노출되면 다른 사람이 봇으로 메시지를 보낼 수 있습니다.
- Destination chat compromise exposes forwarded content.
- 대상 채팅이 노출되면 전달된 내용도 노출됩니다.
- Full Disk Access grants broad local read permissions to the runner.
- Full Disk Access는 실행 주체에 넓은 로컬 읽기 권한을 부여합니다.
- Notification Center parsing may capture sensitive alerts from unrelated apps if allowlists are not used.
- allowlist 없이 Notification Center를 켜면 관련 없는 앱의 민감한 알림도 잡힐 수 있습니다.
- Bot commands can control forwarding, so keep `TELEGRAM_CHAT_ID` and `BOT_ALLOWED_CHAT_IDS` narrow.
- 봇 명령어가 전달 상태를 제어하므로 `TELEGRAM_CHAT_ID`와 `BOT_ALLOWED_CHAT_IDS`를 좁게 유지하세요.

## Reporting Issues / 이슈 제보

If this is published as a public repository, do not include:

공개 레포에 이슈를 올릴 때 포함하지 마세요.

- Telegram bot tokens
- Telegram 봇 토큰
- chat IDs if they identify private groups
- 비공개 그룹을 식별할 수 있는 chat ID
- message bodies
- 메시지 본문
- notification database dumps
- notification database dump

Use redacted logs when possible.

가능하면 redacted 로그를 사용하세요.
