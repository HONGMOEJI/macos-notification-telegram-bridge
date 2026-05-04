# Specification / 스펙

## Purpose / 목적

English:

Forward selected local macOS communication and notification events to a Telegram bot without running a custom Android app or remote backend.

한국어:

커스텀 Android 앱이나 별도 서버 없이, macOS 로컬에 도착한 메시지와 선택된 알림 이벤트를 Telegram 봇으로 전달합니다.

## Supported Sources / 지원 소스

### Messages Database / Messages 데이터베이스

- Default path: `~/Library/Messages/chat.db`
- 기본 경로: `~/Library/Messages/chat.db`
- SQLite database used by macOS Messages
- macOS Messages가 사용하는 SQLite 데이터베이스
- Polling key: `message.ROWID`
- 폴링 기준: `message.ROWID`
- Default behavior: forward incoming messages only
- 기본 동작: 수신 메시지만 전달
- Optional attachment-only note
- 첨부 전용 메시지는 설정에 따라 첨부 개수만 전달

Queried fields:

조회 필드:

- `message.ROWID`
- `message.guid`
- `message.text`
- `message.attributedBody`
- `message.date`
- `message.is_from_me`
- `message.service`
- `handle.id`
- `chat.display_name` or `chat.chat_identifier`
- attachment count

### Notification Center Database / Notification Center 데이터베이스

- Default Sequoia path: `~/Library/Group Containers/group.com.apple.usernoted/db2/db`
- Sequoia 기본 경로: `~/Library/Group Containers/group.com.apple.usernoted/db2/db`
- Older fallback: `$(getconf DARWIN_USER_DIR)/com.apple.notificationcenter/db2/db`
- 구버전 fallback: `$(getconf DARWIN_USER_DIR)/com.apple.notificationcenter/db2/db`
- SQLite database used internally by macOS Notification Center
- macOS Notification Center가 내부적으로 사용하는 SQLite 데이터베이스
- Polling key: `record.rec_id`
- 폴링 기준: `record.rec_id`
- Parsing method: property-list data in `record.data`
- 파싱 방식: `record.data`의 property-list 데이터

Queried fields:

조회 필드:

- `record.rec_id`
- `app.identifier`
- `record.data`
- `record.delivered_date`
- `record.presented`

Parsed notification keys:

파싱하는 알림 키:

- `req.titl` -> title
- `req.subt` -> subtitle
- `req.body` -> body
- `req.cate` -> category
- `req.iden` -> identifier
- `app` or app table identifier -> app identity

### Parcel Tracking / 택배 조회

- Provider: `naver_scrape`
- 제공자: `naver_scrape`
- Registered parcels are stored in `~/Library/Application Support/messages-to-telegram/parcels.json`
- 등록한 택배는 `~/Library/Application Support/messages-to-telegram/parcels.json`에 저장됩니다.
- Polling key: per-parcel `last_signature`
- 폴링 기준: 택배별 `last_signature`
- Default interval: `3600` seconds
- 기본 간격: `3600`초
- Request path: Naver search parcel tracking page plus `ts-proxy.naver.com` JSON response
- 요청 경로: 네이버 검색 택배조회 페이지와 `ts-proxy.naver.com` JSON 응답

## Timing Model / 타이밍 모델

Messages:

- When the Mac receives or syncs a message, `chat.db` is usually updated within a few seconds.
- Mac이 메시지를 받거나 동기화하면 보통 몇 초 안에 `chat.db`가 업데이트됩니다.
- The bridge reads committed SQLite rows.
- 브리지는 커밋된 SQLite row를 읽습니다.
- This is not a direct iPhone notification feed.
- iPhone 알림 피드를 직접 읽는 구조가 아닙니다.

Notification Center:

- macOS writes notification records when notifications are delivered or stored.
- macOS가 알림을 전달하거나 저장할 때 notification record를 씁니다.
- Timing and persistence are controlled by macOS and may vary across versions.
- 저장 시점과 보존 방식은 macOS 버전에 따라 달라질 수 있습니다.

Parcels:

- The bridge checks registered active parcels at most once per `PARCEL_POLL_INTERVAL_SECONDS`.
- 브리지는 등록된 활성 택배를 `PARCEL_POLL_INTERVAL_SECONDS`마다 최대 한 번 조회합니다.
- A Telegram message is sent only when the latest parcel signature changes after the initial registration/check.
- 최초 등록/조회 이후 택배 상태 signature가 바뀐 경우에만 Telegram 메시지를 보냅니다.

## State Model / 상태 모델

State file default:

기본 상태 파일:

```text
~/Library/Application Support/messages-to-telegram/state.json
```

State keys:

상태 키:

```json
{
  "messages_last_rowid": 123,
  "notifications_last_rec_id": 456,
  "initialized_at": "2026-04-29T04:00:00+00:00"
}
```

The state is advanced for skipped records as well as forwarded records. This prevents a denied or unparsable record from being retried forever.

전달하지 않은 항목도 상태를 전진시킵니다. 필터에 걸리거나 파싱되지 않은 항목이 무한 재시도되는 것을 막기 위함입니다.

## Delivery / 전송

- Protocol: HTTPS
- 프로토콜: HTTPS
- API: Telegram Bot API `sendMessage`
- API: Telegram Bot API `sendMessage`
- Payload: plain text
- payload: 일반 텍스트
- Maximum message size: Telegram text limit, trimmed by the bridge
- 최대 크기: Telegram 텍스트 제한에 맞춰 잘림

## Configuration Surface / 설정 범위

Required:

필수:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Core switches:

핵심 스위치:

- `WATCH_MESSAGES`
- `WATCH_NOTIFICATIONS`
- `POLL_INTERVAL_SECONDS`
- `BATCH_LIMIT`

Filtering:

필터:

- `SENDER_ALLOWLIST`
- `CHAT_ALLOWLIST`
- `SERVICE_ALLOWLIST`
- `NOTIFICATION_APP_ALLOWLIST`
- `NOTIFICATION_APP_DENYLIST`

Privacy modes:

개인정보 모드:

- `MESSAGE_TEXT_MODE`
- `NOTIFICATION_TEXT_MODE`
- `PROTECT_CONTENT`
- `DISABLE_NOTIFICATION`

Full reference: [CONFIGURATION.md](CONFIGURATION.md)

## Operational Constraints / 운영 제약

- The Mac must be powered on and logged into a user session for LaunchAgent operation.
- LaunchAgent 동작을 위해 Mac이 켜져 있고 사용자 세션이 있어야 합니다.
- macOS privacy permissions can block database access.
- macOS 개인정보 보호 권한이 데이터베이스 접근을 막을 수 있습니다.
- Notification Center parsing can break after macOS updates.
- macOS 업데이트 후 Notification Center 파싱이 깨질 수 있습니다.
- Naver parcel scraping can break if Naver changes its page, request key, or response format.
- 네이버 택배조회 스크래핑은 네이버가 페이지, 요청 키, 응답 형식을 바꾸면 깨질 수 있습니다.
- Telegram bot messages are visible to Telegram infrastructure and chat members.
- Telegram bot 메시지는 Telegram 인프라와 해당 채팅 구성원에게 보일 수 있습니다.

## Out of Scope / 범위 밖

- Reading notifications directly from iOS
- iOS에서 직접 알림 읽기
- Decrypting unavailable data
- 접근 불가능한 데이터 복호화
- Running a public relay server
- 공개 릴레이 서버 운영
- Guaranteed delivery semantics
- 보장형 전달 semantics
