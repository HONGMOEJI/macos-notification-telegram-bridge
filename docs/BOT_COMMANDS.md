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

Show recent Notification Center records as a card-style list with detail buttons. You can filter by bundle ID or mapped app name.

최근 Notification Center 항목을 카드형 목록으로 보여주고 각 항목에 자세히 보기 버튼을 붙입니다. 번들 ID 또는 매핑된 앱 이름으로 필터링할 수 있습니다.

When you tap a detail button, the bot reads the selected `rec_id` again from the local Notification Center database and sends a full detail message.

자세히 보기 버튼을 누르면 봇이 선택된 `rec_id`를 로컬 Notification Center 데이터베이스에서 다시 읽어 상세 메시지를 보냅니다.

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

## Parcels / 택배

```text
/parcelon
/parceloff
```

Enable or disable hourly parcel polling at runtime.

택배 주기 조회를 런타임에서 켜고 끕니다. 등록된 택배가 없으면 네트워크 조회도 하지 않습니다.

```text
/parceladd
```

Register a parcel by carrier name or Naver carrier code, invoice number, and optional label. Example usage: `/parceladd CJ대한통운 1234567890 키보드`.

택배사 이름 또는 네이버 택배사 코드, 운송장 번호, 선택 라벨로 택배를 등록합니다. 사용 예시는 `/parceladd CJ대한통운 1234567890 키보드`입니다.

```text
/parcels
```

Show registered parcels, their IDs, current state, and last status.

등록된 택배의 ID, 활성 상태, 마지막 조회 상태를 보여줍니다.

```text
/parcelcheck
```

Immediately check all parcels or one selected parcel. Example usage: `/parcelcheck`, `/parcelcheck 04:1234567890`.

모든 택배 또는 선택한 택배를 즉시 조회합니다. 사용 예시는 `/parcelcheck`, `/parcelcheck 04:1234567890`입니다.

```text
/parcelremove
```

Remove a registered parcel. Example usage: `/parcelremove 04:1234567890`.

등록한 택배를 삭제합니다. 사용 예시는 `/parcelremove 04:1234567890`입니다.

```text
/parcelpause
/parcelresume
```

Pause or resume polling for one registered parcel. Example usage: `/parcelpause 04:1234567890`.

특정 택배의 주기 조회만 멈추거나 다시 켭니다. 사용 예시는 `/parcelpause 04:1234567890`입니다.

```text
/parcelcarriers
```

Show Naver carrier codes. Example usage: `/parcelcarriers`, `/parcelcarriers cj`.

네이버 택배사 코드를 보여줍니다. 사용 예시는 `/parcelcarriers`, `/parcelcarriers cj`입니다.

Parcel tracking uses Naver search's parcel tracking web path and an internal JSON response. It is convenient and keyless, but it may break if Naver changes the page, request key, or response shape.

택배 조회는 네이버 검색의 택배조회 웹 경로와 내부 JSON 응답을 사용합니다. 별도 키 없이 편하지만, 네이버가 페이지, 요청 키, 응답 형식을 바꾸면 깨질 수 있습니다.

## Utility / 유틸

```text
/test
/help
```

Check that the bot command loop is alive, or show command help.

봇 명령 루프가 살아 있는지 확인하거나 도움말을 표시합니다.
