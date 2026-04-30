# macOS Notification Telegram Bridge

macOS에서 수신한 Messages 및 일부 Notification Center 알림을 읽어 Telegram Bot으로 전달하는 작은 브리지입니다.

A small local bridge that forwards macOS Messages and selected Notification Center records to a Telegram bot.

```text
iPhone / macOS events
  -> Messages.app and/or macOS Notification Center
  -> local Python LaunchAgent
  -> Telegram Bot API
  -> Telegram on Android, iOS, desktop, or web
```

## Status / 상태

This is an MVP for personal automation. It is designed to be simple, inspectable, and dependency-free.

개인 자동화용 MVP입니다. 외부 Python 패키지 없이 동작하고, 코드와 동작을 쉽게 검토할 수 있도록 작게 만들었습니다.

## Features / 기능

- Forward new incoming Messages rows from `~/Library/Messages/chat.db`
- macOS Messages의 `chat.db`에 추가되는 새 수신 메시지를 Telegram으로 전달
- Optional best-effort forwarding from macOS Notification Center storage
- 선택적으로 macOS Notification Center 저장소의 다른 앱 알림도 전달
- Telegram Bot API `sendMessage` based delivery
- Telegram Bot API `sendMessage` 기반 전송
- LaunchAgent installer for background operation
- LaunchAgent 설치 스크립트 제공
- Sender, chat, service, and app bundle allowlist or denylist filters
- 발신자, 채팅방, 서비스, 앱 번들 ID 기반 필터
- Privacy modes: full text, redacted body, sender/app-only metadata
- 개인정보 모드: 본문 전체, 본문 숨김, 메타데이터만 전송
- No third-party Python dependencies
- 서드파티 Python 의존성 없음

## Non-goals / 하지 않는 것

- This does not directly read iPhone notification internals.
- iPhone 내부 알림 스트림을 직접 읽지 않습니다.
- This does not bypass macOS privacy controls.
- macOS 개인정보 보호 권한을 우회하지 않습니다.
- This is not a hosted relay service.
- 호스팅 서버형 릴레이가 아닙니다.
- Notification Center parsing is not a stable public Apple API.
- Notification Center 파싱은 Apple의 안정적인 공개 API가 아닙니다.

## Requirements / 요구 사항

- macOS with Messages.app enabled
- Messages.app 사용이 가능한 macOS
- Python 3 available as `python3`
- `python3` 실행 가능
- Telegram account and a bot created through `@BotFather`
- `@BotFather`로 만든 Telegram 봇
- Full Disk Access for the runner, depending on macOS privacy settings
- macOS 설정에 따라 실행 주체에 Full Disk Access 필요

Details: [docs/SPECIFICATION.md](docs/SPECIFICATION.md)

## Quick Start / 빠른 시작

1. Create a Telegram bot with `@BotFather` and copy the bot token.
2. 새 Telegram 봇을 `@BotFather`로 만들고 토큰을 복사합니다.
3. Send any message to the bot from the Telegram account or group that should receive forwarded events.
4. 전달을 받을 개인 계정 또는 그룹에서 봇에게 아무 메시지나 보냅니다.
5. Run the installer once. The first run creates the config and stops.
6. 설치 스크립트를 한 번 실행합니다. 첫 실행은 설정 파일만 만들고 종료합니다.

```bash
./install_launch_agent.sh
```

7. Edit the generated config.
8. 생성된 설정 파일을 편집합니다.

```bash
open -e "$HOME/Library/Application Support/messages-to-telegram/config.env"
```

9. Set `TELEGRAM_BOT_TOKEN`.
10. `TELEGRAM_BOT_TOKEN`을 입력합니다.
11. Get the chat ID.
12. chat ID를 확인합니다.

```bash
python3 "$HOME/Library/Application Support/messages-to-telegram/messages_to_telegram.py" \
  --config "$HOME/Library/Application Support/messages-to-telegram/config.env" \
  chat-id
```

13. Put the printed value in `TELEGRAM_CHAT_ID`.
14. 출력된 값을 `TELEGRAM_CHAT_ID`에 넣습니다.
15. Test Telegram delivery.
16. Telegram 전송을 테스트합니다.

```bash
python3 "$HOME/Library/Application Support/messages-to-telegram/messages_to_telegram.py" \
  --config "$HOME/Library/Application Support/messages-to-telegram/config.env" \
  test-telegram
```

17. Run the installer again to install and start the LaunchAgent.
18. 설치 스크립트를 다시 실행해서 LaunchAgent를 설치하고 시작합니다.

```bash
./install_launch_agent.sh
```

Full setup guide: [docs/INSTALLATION.md](docs/INSTALLATION.md)

## Enable Other Notifications / 다른 앱 알림 켜기

Messages forwarding is enabled by default. Other app notifications are opt-in.

Messages 전달은 기본 활성화입니다. 다른 앱 알림 전달은 명시적으로 켜야 합니다.

```env
WATCH_MESSAGES=1
WATCH_NOTIFICATIONS=1
```

To avoid duplicate iMessage/SMS forwarding, Messages bundle IDs are denied by default in the Notification Center path.

iMessage/SMS 중복 전달을 피하려고 Notification Center 쪽에서는 Messages 관련 번들 ID를 기본 제외합니다.

```env
NOTIFICATION_APP_DENYLIST=com.apple.MobileSMS,com.apple.iChat,com.tdesktop.telegram,org.telegram.desktop,ru.keepcoder.Telegram
```

Notification Center support is best-effort because Apple does not provide a public API for subscribing to all app notifications.

Notification Center 지원은 best-effort입니다. Apple이 모든 앱 알림을 구독하는 공개 API를 제공하지 않기 때문입니다.

## Useful Commands / 유용한 명령

Preview Messages parsing without sending:

메시지 파싱 결과만 미리 보기:

```bash
python3 messages_to_telegram.py sample --limit 5
```

Preview Notification Center parsing without sending:

Notification Center 파싱 결과만 미리 보기:

```bash
python3 messages_to_telegram.py notification-sample --limit 5
```

Mark current rows as already seen:

현재까지의 항목을 이미 처리한 것으로 표시:

```bash
python3 messages_to_telegram.py init-state
```

Run once:

한 번만 실행:

```bash
python3 messages_to_telegram.py once
```

Run in foreground:

포그라운드에서 계속 실행:

```bash
python3 messages_to_telegram.py run
```

Uninstall the LaunchAgent:

LaunchAgent 제거:

```bash
./uninstall_launch_agent.sh
```

## How Fresh Is `chat.db`? / `chat.db`는 얼마나 빨리 업데이트되나요?

`chat.db` is the local SQLite database used by Messages on macOS. When the Mac receives or syncs a message, a committed row is usually visible within a few seconds.

`chat.db`는 macOS Messages가 사용하는 로컬 SQLite 데이터베이스입니다. Mac이 메시지를 받거나 동기화하면 보통 몇 초 안에 커밋된 row가 보입니다.

It is not a direct iPhone notification stream. If the Mac has not received the message yet, the row does not exist yet.

단, 이것은 iPhone 알림 스트림이 아니라 Mac의 Messages 저장소입니다. Mac이 아직 메시지를 받지 못했다면 row도 존재하지 않습니다.

More details: [docs/SPECIFICATION.md](docs/SPECIFICATION.md)

## Privacy and Security / 개인정보와 보안

This bridge can move private message or notification content from Apple's local storage into Telegram. Use allowlists and redaction modes for sensitive setups.

이 브리지는 Apple 로컬 저장소의 메시지나 알림 내용을 Telegram으로 옮길 수 있습니다. 민감한 환경에서는 allowlist와 redaction 모드를 사용하세요.

Recommended privacy-oriented settings:

개인정보 보호 중심 추천 설정:

```env
MESSAGE_TEXT_MODE=redacted
NOTIFICATION_TEXT_MODE=redacted
SENDER_ALLOWLIST=+15551234567,person@example.com
NOTIFICATION_APP_ALLOWLIST=com.apple.mail,com.tinyspeck.slackmacgap
PROTECT_CONTENT=1
```

Threat model and permissions: [docs/SECURITY.md](docs/SECURITY.md)

## Documentation / 문서

- [Installation / 설치](docs/INSTALLATION.md)
- [Specification / 스펙](docs/SPECIFICATION.md)
- [Architecture / 아키텍처](docs/ARCHITECTURE.md)
- [Configuration / 설정](docs/CONFIGURATION.md)
- [Security / 보안](docs/SECURITY.md)
- [Troubleshooting / 문제 해결](docs/TROUBLESHOOTING.md)

## License / 라이선스

MIT License. See [LICENSE](LICENSE).
