# Architecture / 아키텍처

## High-level Flow / 전체 흐름

```text
Messages.app / Notification Center
        |
        v
SQLite databases on macOS
        |
        v
messages_to_telegram.py
        |
        v
Telegram Bot API sendMessage
        |
        v
Telegram client on Android or any device
```

```text
Messages.app / Notification Center
        |
        v
macOS 로컬 SQLite 데이터베이스
        |
        v
messages_to_telegram.py
        |
        v
Telegram Bot API sendMessage
        |
        v
Android 등 Telegram 클라이언트
```

## Runtime Components / 런타임 구성요소

### `messages_to_telegram.py`

English:

Main executable. It loads config, polls enabled sources, formats records, sends Telegram messages, and persists state.

한국어:

메인 실행 파일입니다. 설정을 읽고, 활성화된 소스를 폴링하고, 항목을 포맷하고, Telegram으로 전송하고, 상태를 저장합니다.

### `config.env`

English:

User-local configuration file. It contains Telegram credentials and privacy controls. It must not be committed.

한국어:

사용자 로컬 설정 파일입니다. Telegram 인증 정보와 개인정보 설정을 포함합니다. 커밋하면 안 됩니다.

### `state.json`

English:

User-local state file. It stores the last seen Messages `ROWID`, Notification Center `rec_id`, Telegram command offset, and cached Naver parcel request key.

한국어:

사용자 로컬 상태 파일입니다. 마지막으로 본 Messages `ROWID`, Notification Center `rec_id`, Telegram 명령 offset, 캐시된 네이버 택배조회 요청 키를 저장합니다.

### `parcels.json`

English:

User-editable parcel registry. Each record stores carrier code, invoice number, label, active flag, and the last observed delivery signature.

한국어:

사용자가 수정할 수 있는 택배 등록 파일입니다. 각 항목은 택배사 코드, 운송장 번호, 라벨, 활성 여부, 마지막으로 관측한 배송 signature를 저장합니다.

### LaunchAgent

English:

Runs the Python script in the user session and restarts it if it exits.

한국어:

사용자 세션 안에서 Python 스크립트를 실행하고 종료되면 재시작합니다.

## Polling Strategy / 폴링 전략

The bridge uses simple polling instead of filesystem watchers.

브리지는 파일시스템 watcher 대신 단순 폴링을 사용합니다.

Reasons:

이유:

- SQLite and WAL updates can be noisy.
- SQLite와 WAL 업데이트는 이벤트가 많을 수 있습니다.
- Polling is easier to inspect and debug.
- 폴링은 검토와 디버깅이 쉽습니다.
- The workload is tiny for personal use.
- 개인 사용량에서는 부하가 작습니다.
- Parcel tracking is rate-limited separately by `PARCEL_POLL_INTERVAL_SECONDS`, defaulting to one hour.
- 택배 조회는 `PARCEL_POLL_INTERVAL_SECONDS`로 별도 제한하며 기본값은 1시간입니다.

## Failure Handling / 실패 처리

- Telegram request failures are logged and retried on the next loop only for records whose state was not saved yet.
- Telegram 요청 실패는 로그에 남고, 아직 상태 저장이 되지 않은 항목은 다음 루프에서 다시 시도됩니다.
- Records skipped by filters still advance state.
- 필터로 제외된 항목도 상태를 전진시킵니다.
- Database access errors are logged repeatedly until permissions or paths are fixed.
- 데이터베이스 접근 오류는 권한이나 경로가 고쳐질 때까지 로그에 반복 기록됩니다.

## Why Telegram / Telegram을 쓰는 이유

English:

Telegram removes the need for a custom Android app. The receiving phone only needs the standard Telegram client.

한국어:

Telegram을 쓰면 커스텀 Android 앱이 필요 없습니다. 수신 폰에는 일반 Telegram 클라이언트만 있으면 됩니다.

## Why Not a macOS Notification API / 왜 macOS Notification API가 아닌가

English:

macOS does not provide a stable public API that lets an arbitrary process subscribe to all notifications from other apps. Notification Center support therefore reads private local storage on a best-effort basis.

한국어:

macOS는 임의 프로세스가 다른 모든 앱의 알림을 구독할 수 있는 안정적인 공개 API를 제공하지 않습니다. 그래서 Notification Center 지원은 사설 로컬 저장소를 best-effort로 읽는 방식입니다.
