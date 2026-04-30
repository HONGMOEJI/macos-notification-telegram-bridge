# Bot Commands / 봇 명령어

Commands are processed through Telegram `getUpdates`. Only the configured `TELEGRAM_CHAT_ID` and optional `BOT_ALLOWED_CHAT_IDS` can control the bridge.

명령어는 Telegram `getUpdates`로 처리합니다. 설정된 `TELEGRAM_CHAT_ID`와 선택적 `BOT_ALLOWED_CHAT_IDS`만 브리지를 제어할 수 있습니다.

## Enable / 활성화

```env
BOT_COMMANDS_ENABLED=1
BOT_ALLOWED_CHAT_IDS=
```

## Control / 제어

```text
/status
```

Show current runtime state.

현재 런타임 상태를 표시합니다.

```text
/pause
/resume
```

Pause or resume forwarding. While paused, new records are marked as seen so they will not flood later.

전달을 일시정지하거나 재개합니다. 일시정지 중 들어온 항목은 처리된 것으로 표시되어 나중에 몰아서 오지 않습니다.

```text
/mute 30m
/mute 2h
/unmute
```

Temporarily suppress forwarding. Like pause, muted records are skipped instead of queued.

일정 시간 전달을 조용히 합니다. pause와 마찬가지로 항목을 쌓아두지 않고 건너뜁니다.

```text
/messages on
/messages off
/noti on
/noti off
```

Toggle Messages or Notification Center forwarding at runtime.

Messages 또는 Notification Center 전달을 런타임에서 켜고 끕니다.

```text
/mode full
/mode redacted
/mode sender_only
/notimode full
/notimode redacted
/notimode app_only
```

Change privacy modes at runtime.

개인정보 모드를 런타임에서 바꿉니다.

## App Filters / 앱 필터

```text
/deny com.kakao.kakaotalkmac
/undeny com.kakao.kakaotalkmac
/denylist
```

Add or remove app bundle IDs from `NOTIFICATION_APP_DENYLIST`.

앱 번들 ID를 `NOTIFICATION_APP_DENYLIST`에 추가하거나 제거합니다.

Telegram bundle IDs are denied by default to avoid forwarding loops.

Telegram 알림 재귀 루프를 막기 위해 Telegram 번들 ID는 기본 제외됩니다.

## Notification Tables / 알림 표

```text
/notilist
/notilist all 20
/notilist com.kakao.kakaotalkmac 10
/notilist KakaoTalk 10
```

Show recent Notification Center records as a compact table. You can filter by bundle ID or mapped app name.

최근 Notification Center 항목을 간단한 표로 보여줍니다. 번들 ID 또는 매핑된 앱 이름으로 필터링할 수 있습니다.

```text
/apps
/apps 50
```

Show recently seen notification apps with bundle IDs, counts, and last seen time.

알림이 관측된 앱 목록, 번들 ID, 개수, 최근 시간을 표로 보여줍니다.

## App Name Mapping / 앱 이름 매핑

```text
/map
/map path
/map set com.kakao.kakaotalkmac KakaoTalk
/map unset com.kakao.kakaotalkmac
/unmap com.kakao.kakaotalkmac
```

Manage the editable bundle-ID-to-display-name table. The map is stored as JSON and can also be edited manually.

번들 ID를 사람이 읽기 쉬운 이름으로 바꾸는 매핑 테이블을 관리합니다. 매핑은 JSON 파일로 저장되어 직접 수정할 수도 있습니다.

Default path:

기본 경로:

```text
~/Library/Application Support/messages-to-telegram/app_map.json
```

Example:

예시:

```json
{
  "com.kakao.kakaotalkmac": "KakaoTalk",
  "com.google.chrome": "Chrome",
  "com.apple.mobilesms": "Messages"
}
```

## News / 뉴스

```text
/news
/news AI
/news 반도체 7
```

Uses Google News RSS. No API key is required. Results depend on `NEWS_LANGUAGE` and `NEWS_COUNTRY`.

Google News RSS를 사용합니다. API 키가 필요 없습니다. 결과는 `NEWS_LANGUAGE`, `NEWS_COUNTRY` 설정을 따릅니다.

```env
NEWS_LANGUAGE=ko
NEWS_COUNTRY=KR
```

## Stocks / 주식

```text
/stock AAPL
/stock AAPL NVDA 005930.KS
```

Uses Yahoo Finance chart data without an API key. This is convenient but unofficial, so it may change or break.

API 키 없이 Yahoo Finance chart 데이터를 사용합니다. 편하지만 비공식 엔드포인트라 언제든 바뀌거나 깨질 수 있습니다.

Korean tickers usually use Yahoo suffixes:

한국 종목은 보통 Yahoo suffix를 사용합니다.

```text
005930.KS  Samsung Electronics
035420.KS  NAVER
000660.KS  SK hynix
```

## Brief / 브리핑

```text
/brief
```

Returns top news plus the configured stock watchlist.

주요 뉴스와 설정된 관심 종목을 함께 보냅니다.

```env
STOCK_WATCHLIST=^GSPC,^IXIC,AAPL,NVDA,005930.KS
```

## Utility / 유틸

```text
/test
/help
```

Check that the bot command loop is alive, or show command help.

봇 명령 루프가 살아 있는지 확인하거나 도움말을 표시합니다.
