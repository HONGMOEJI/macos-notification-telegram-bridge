# Installation / 설치

This guide assumes the repository has been cloned or downloaded on the Mac that will act as the bridge.

이 문서는 브리지 역할을 할 Mac에 레포가 clone 또는 다운로드되어 있다고 가정합니다.

## 1. Telegram Bot / Telegram 봇 준비

English:

1. Open Telegram.
2. Talk to `@BotFather`.
3. Create a new bot.
4. Copy the bot token.
5. Send any message to your bot from the target receiving account or group.

한국어:

1. Telegram을 엽니다.
2. `@BotFather`에게 말을 겁니다.
3. 새 봇을 만듭니다.
4. 봇 토큰을 복사합니다.
5. 알림을 받을 계정 또는 그룹에서 봇에게 아무 메시지나 보냅니다.

## 2. Install Files / 파일 설치

Run:

실행:

```bash
./install_launch_agent.sh
```

On the first run, the installer creates:

첫 실행 시 다음 파일이 생성됩니다.

```text
~/Library/Application Support/messages-to-telegram/config.env
~/Library/Application Support/messages-to-telegram/messages_to_telegram.py
```

The installer stops after creating the config so you can add secrets manually.

설정 파일에 비밀값을 직접 넣을 수 있도록 첫 실행은 여기서 멈춥니다.

## 3. Configure / 설정

Open the config:

설정 파일 열기:

```bash
open -e "$HOME/Library/Application Support/messages-to-telegram/config.env"
```

Set:

설정:

```env
TELEGRAM_BOT_TOKEN=<token-from-botfather>
TELEGRAM_CHAT_ID=
WATCH_MESSAGES=1
WATCH_NOTIFICATIONS=0
```

Then get the chat ID:

그 다음 chat ID 확인:

```bash
python3 "$HOME/Library/Application Support/messages-to-telegram/messages_to_telegram.py" \
  --config "$HOME/Library/Application Support/messages-to-telegram/config.env" \
  chat-id
```

Copy the printed numeric ID into `TELEGRAM_CHAT_ID`.

출력된 숫자 ID를 `TELEGRAM_CHAT_ID`에 넣습니다.

## 4. Test / 테스트

```bash
python3 "$HOME/Library/Application Support/messages-to-telegram/messages_to_telegram.py" \
  --config "$HOME/Library/Application Support/messages-to-telegram/config.env" \
  test-telegram
```

You should receive a Telegram test message.

Telegram 테스트 메시지를 받아야 합니다.

## 5. Start Background Service / 백그라운드 서비스 시작

Run the installer again:

설치 스크립트 재실행:

```bash
./install_launch_agent.sh
```

This installs:

다음 LaunchAgent를 설치합니다.

```text
~/Library/LaunchAgents/com.codex.messages-to-telegram.plist
```

## 6. Full Disk Access / 전체 디스크 접근 권한

macOS may block access to Messages or Notification Center storage.

macOS가 Messages 또는 Notification Center 저장소 접근을 막을 수 있습니다.

Grant Full Disk Access to the runner:

실행 주체에 Full Disk Access를 부여합니다.

- Terminal, iTerm, or the terminal app used for manual runs
- 수동 실행에 쓰는 Terminal, iTerm 등
- The Python executable used by LaunchAgent, depending on macOS version
- macOS 버전에 따라 LaunchAgent가 사용하는 Python 실행 파일

Settings path:

설정 경로:

```text
System Settings -> Privacy & Security -> Full Disk Access
```

## 7. Logs / 로그

```bash
tail -f "$HOME/Library/Logs/messages-to-telegram.out.log"
tail -f "$HOME/Library/Logs/messages-to-telegram.err.log"
```

## 8. Uninstall / 제거

```bash
./uninstall_launch_agent.sh
```

This removes only the LaunchAgent plist. App files and config remain for inspection or reinstall.

LaunchAgent plist만 제거합니다. 앱 파일과 설정은 재설치나 확인을 위해 남겨둡니다.
