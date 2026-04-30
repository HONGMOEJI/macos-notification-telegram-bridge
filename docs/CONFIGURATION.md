# Configuration / 설정

The config file is a simple `KEY=VALUE` file.

설정 파일은 단순한 `KEY=VALUE` 형식입니다.

Default path:

기본 경로:

```text
~/Library/Application Support/messages-to-telegram/config.env
```

## Required / 필수

### `TELEGRAM_BOT_TOKEN`

Telegram bot token from `@BotFather`.

`@BotFather`에서 받은 Telegram 봇 토큰입니다.

### `TELEGRAM_CHAT_ID`

Destination chat ID.

전송 대상 chat ID입니다.

Get it with:

확인:

```bash
python3 messages_to_telegram.py --config config.env chat-id
```

## Source Switches / 소스 스위치

### `WATCH_MESSAGES`

Default: `1`

기본값: `1`

Enable Messages database polling.

Messages 데이터베이스 폴링을 켭니다.

### `WATCH_NOTIFICATIONS`

Default: `0`

기본값: `0`

Enable Notification Center polling.

Notification Center 폴링을 켭니다.

## Paths / 경로

### `MESSAGES_DB_PATH`

Default:

기본값:

```text
~/Library/Messages/chat.db
```

### `NOTIFICATION_DB_PATH`

Default detection order:

기본 탐색 순서:

```text
~/Library/Group Containers/group.com.apple.usernoted/db2/db
$(getconf DARWIN_USER_DIR)/com.apple.notificationcenter/db2/db
$(getconf DARWIN_USER_DIR)/com.apple.notificationcenter/db/db
~/Library/Application Support/NotificationCenter/*.db
```

### `STATE_PATH`

Default:

기본값:

```text
~/Library/Application Support/messages-to-telegram/state.json
```

## Polling / 폴링

### `POLL_INTERVAL_SECONDS`

Default: `5`

기본값: `5`

Seconds between polling loops.

폴링 루프 간격입니다.

### `BATCH_LIMIT`

Default: `20`

기본값: `20`

Maximum records read per source per loop.

각 루프에서 소스별로 읽을 최대 항목 수입니다.

## Messages Filters / Messages 필터

### `FORWARD_INCOMING_ONLY`

Default: `1`

기본값: `1`

Forward only messages not sent by this Mac account.

이 Mac 계정이 보낸 메시지를 제외하고 수신 메시지만 전달합니다.

### `FORWARD_EMPTY_MESSAGES`

Default: `0`

기본값: `0`

Forward messages without readable text, usually as attachment count notes.

읽을 수 있는 텍스트가 없는 메시지도 전달합니다. 보통 첨부 개수 메모로 전달됩니다.

### `SENDER_ALLOWLIST`

Comma-separated, case-insensitive substring matching.

쉼표 구분, 대소문자 무시 부분 문자열 매칭입니다.

```env
SENDER_ALLOWLIST=+15551234567,person@example.com
```

### `CHAT_ALLOWLIST`

```env
CHAT_ALLOWLIST=Family,Project
```

### `SERVICE_ALLOWLIST`

```env
SERVICE_ALLOWLIST=iMessage,SMS
```

## Notification Filters / 알림 필터

### `NOTIFICATION_APP_ALLOWLIST`

Forward only matching bundle IDs.

일치하는 번들 ID만 전달합니다.

```env
NOTIFICATION_APP_ALLOWLIST=com.apple.mail,com.tinyspeck.slackmacgap
```

### `NOTIFICATION_APP_DENYLIST`

Default:

기본값:

```env
NOTIFICATION_APP_DENYLIST=com.apple.MobileSMS,com.apple.iChat,com.tdesktop.telegram,org.telegram.desktop,ru.keepcoder.Telegram
```

Skip matching bundle IDs.

일치하는 번들 ID를 제외합니다.

Telegram bundle IDs are included by default to avoid forwarding loops.

Telegram으로 보낸 메시지가 다시 Telegram 알림으로 들어와 재전송되는 루프를 막기 위해 Telegram 번들 ID를 기본 제외합니다.

### `NOTIFICATION_PRESENTED_ONLY`

Default: `0`

기본값: `0`

If `1`, forward only records marked as presented by macOS.

`1`이면 macOS가 presented로 표시한 항목만 전달합니다.

## Privacy Modes / 개인정보 모드

### `MESSAGE_TEXT_MODE`

Values:

값:

- `full`: include body
- `full`: 본문 포함
- `redacted`: hide body but include metadata
- `redacted`: 본문 숨김, 메타데이터 포함
- `sender_only`: include sender, chat, and time only
- `sender_only`: 발신자, 채팅방, 시간만 포함

### `NOTIFICATION_TEXT_MODE`

Values:

값:

- `full`: include title, subtitle, and body
- `full`: 제목, 부제목, 본문 포함
- `redacted`: hide body but include app, time, and title
- `redacted`: 본문 숨김, 앱, 시간, 제목 포함
- `app_only`: include app and time only
- `app_only`: 앱과 시간만 포함

### `PROTECT_CONTENT`

Default: `0`

기본값: `0`

Ask Telegram to protect bot messages from forwarding and saving where supported.

Telegram에 메시지 전달 및 저장 제한을 요청합니다. 지원되는 범위에서만 적용됩니다.

### `DISABLE_NOTIFICATION`

Default: `0`

기본값: `0`

Send Telegram messages silently.

Telegram 메시지를 무음으로 보냅니다.

## Logging / 로깅

### `SEND_STARTUP_MESSAGE`

Default: `1`

기본값: `1`

Send a Telegram message when the bridge starts.

브리지가 시작될 때 Telegram 메시지를 보냅니다.

### `LOG_LEVEL`

Default: `INFO`

기본값: `INFO`

Common values: `DEBUG`, `INFO`, `WARNING`, `ERROR`.

일반적인 값: `DEBUG`, `INFO`, `WARNING`, `ERROR`.
