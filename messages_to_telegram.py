#!/usr/bin/env python3
"""Forward new macOS Messages and Notification Center rows to a Telegram bot.

This is intentionally small and dependency-free so it can run as a LaunchAgent
on a stock-ish macOS machine. It reads local SQLite databases, keeps last-seen
state, and sends new rows through the Telegram Bot API.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import logging
import os
import plistlib
import re
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


APP_NAME = "messages-to-telegram"
DEFAULT_APP_DIR = Path.home() / "Library" / "Application Support" / APP_NAME
DEFAULT_CONFIG_PATH = DEFAULT_APP_DIR / "config.env"
DEFAULT_STATE_PATH = DEFAULT_APP_DIR / "state.json"
DEFAULT_MESSAGES_DB = Path.home() / "Library" / "Messages" / "chat.db"
DEFAULT_NOTIFICATION_DB = (
    Path.home() / "Library" / "Group Containers" / "group.com.apple.usernoted" / "db2" / "db"
)
APPLE_EPOCH = dt.datetime(2001, 1, 1, tzinfo=dt.timezone.utc)
TELEGRAM_MAX_TEXT = 4096

ENV_KEYS = {
    "WATCH_MESSAGES",
    "WATCH_NOTIFICATIONS",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "MESSAGES_DB_PATH",
    "NOTIFICATION_DB_PATH",
    "STATE_PATH",
    "POLL_INTERVAL_SECONDS",
    "BATCH_LIMIT",
    "FORWARD_INCOMING_ONLY",
    "FORWARD_EMPTY_MESSAGES",
    "SENDER_ALLOWLIST",
    "CHAT_ALLOWLIST",
    "SERVICE_ALLOWLIST",
    "NOTIFICATION_APP_ALLOWLIST",
    "NOTIFICATION_APP_DENYLIST",
    "NOTIFICATION_PRESENTED_ONLY",
    "NOTIFICATION_TEXT_MODE",
    "MESSAGE_TEXT_MODE",
    "DISABLE_NOTIFICATION",
    "PROTECT_CONTENT",
    "SEND_STARTUP_MESSAGE",
    "LOG_LEVEL",
}


IGNORED_ARCHIVE_STRINGS = {
    "",
    "$archiver",
    "$objects",
    "$top",
    "$version",
    "NS.attributes",
    "NS.keys",
    "NS.objects",
    "NS.string",
    "NSColor",
    "NSDictionary",
    "NSMutableAttributedString",
    "NSMutableString",
    "NSObject",
    "NSOriginalFont",
    "NSParagraphStyle",
    "NSString",
    "NSValue",
    "root",
}


@dataclass(frozen=True)
class Config:
    watch_messages: bool
    watch_notifications: bool
    telegram_bot_token: str
    telegram_chat_id: str
    messages_db_path: Path
    notification_db_path: Path
    state_path: Path
    poll_interval_seconds: float
    batch_limit: int
    forward_incoming_only: bool
    forward_empty_messages: bool
    sender_allowlist: tuple[str, ...]
    chat_allowlist: tuple[str, ...]
    service_allowlist: tuple[str, ...]
    notification_app_allowlist: tuple[str, ...]
    notification_app_denylist: tuple[str, ...]
    notification_presented_only: bool
    notification_text_mode: str
    message_text_mode: str
    disable_notification: bool
    protect_content: bool
    send_startup_message: bool
    log_level: str


@dataclass(frozen=True)
class MessageRow:
    rowid: int
    guid: str | None
    text: str | None
    attributed_body: bytes | None
    date_raw: int | None
    is_from_me: bool
    service: str | None
    sender: str | None
    chat_name: str | None
    attachment_count: int

    @property
    def body(self) -> str:
        if self.text:
            return self.text
        decoded = decode_attributed_body(self.attributed_body)
        if decoded:
            return decoded
        if self.attachment_count:
            return f"[{self.attachment_count} attachment(s)]"
        return ""


@dataclass(frozen=True)
class NotificationRow:
    rec_id: int
    bundle_id: str | None
    data_blob: bytes | None
    delivered_date: float | None
    presented: bool

    @property
    def parsed(self) -> dict[str, Any]:
        return parse_notification_blob(self.data_blob)


def expand_path(value: str | Path) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(value))))


def parse_bool(value: str | bool | int | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"{path}:{line_number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError(f"{path}:{line_number}: empty key")
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]
        values[key] = value
    return values


def load_config(config_path: Path) -> Config:
    raw = load_env_file(config_path)
    for key in ENV_KEYS:
        if key in os.environ:
            raw[key] = os.environ[key]

    token = raw.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = raw.get("TELEGRAM_CHAT_ID", "").strip()

    return Config(
        watch_messages=parse_bool(raw.get("WATCH_MESSAGES"), True),
        watch_notifications=parse_bool(raw.get("WATCH_NOTIFICATIONS"), False),
        telegram_bot_token=token,
        telegram_chat_id=chat_id,
        messages_db_path=expand_path(raw.get("MESSAGES_DB_PATH", str(DEFAULT_MESSAGES_DB))),
        notification_db_path=expand_path(
            raw.get("NOTIFICATION_DB_PATH", str(detect_notification_db_path()))
        ),
        state_path=expand_path(raw.get("STATE_PATH", str(DEFAULT_STATE_PATH))),
        poll_interval_seconds=float(raw.get("POLL_INTERVAL_SECONDS", "5")),
        batch_limit=max(1, int(raw.get("BATCH_LIMIT", "20"))),
        forward_incoming_only=parse_bool(raw.get("FORWARD_INCOMING_ONLY"), True),
        forward_empty_messages=parse_bool(raw.get("FORWARD_EMPTY_MESSAGES"), False),
        sender_allowlist=normalize_filter(parse_csv(raw.get("SENDER_ALLOWLIST"))),
        chat_allowlist=normalize_filter(parse_csv(raw.get("CHAT_ALLOWLIST"))),
        service_allowlist=normalize_filter(parse_csv(raw.get("SERVICE_ALLOWLIST"))),
        notification_app_allowlist=normalize_filter(parse_csv(raw.get("NOTIFICATION_APP_ALLOWLIST"))),
        notification_app_denylist=normalize_filter(
            parse_csv(raw.get("NOTIFICATION_APP_DENYLIST", "com.apple.MobileSMS,com.apple.iChat"))
        ),
        notification_presented_only=parse_bool(raw.get("NOTIFICATION_PRESENTED_ONLY"), False),
        notification_text_mode=raw.get("NOTIFICATION_TEXT_MODE", "full").strip().lower(),
        message_text_mode=raw.get("MESSAGE_TEXT_MODE", "full").strip().lower(),
        disable_notification=parse_bool(raw.get("DISABLE_NOTIFICATION"), False),
        protect_content=parse_bool(raw.get("PROTECT_CONTENT"), False),
        send_startup_message=parse_bool(raw.get("SEND_STARTUP_MESSAGE"), True),
        log_level=raw.get("LOG_LEVEL", "INFO").strip().upper(),
    )


def normalize_filter(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(value.lower() for value in values if value)


def require_telegram_config(config: Config) -> None:
    missing = []
    if not config.telegram_bot_token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not config.telegram_chat_id:
        missing.append("TELEGRAM_CHAT_ID")
    if missing:
        raise SystemExit(
            "Missing required config: "
            + ", ".join(missing)
            + f"\nEdit {DEFAULT_CONFIG_PATH} or pass --config PATH."
        )


def configure_logging(level_name: str) -> None:
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def path_is_probably_present(path: Path) -> bool:
    try:
        path.stat()
        return True
    except PermissionError:
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def darwin_user_dir() -> Path | None:
    try:
        result = subprocess.run(
            ["getconf", "DARWIN_USER_DIR"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = result.stdout.strip()
    return Path(value) if value else None


def notification_db_candidates() -> list[Path]:
    candidates = [DEFAULT_NOTIFICATION_DB]

    darwin_dir = darwin_user_dir()
    if darwin_dir:
        candidates.extend(
            [
                darwin_dir / "com.apple.notificationcenter" / "db2" / "db",
                darwin_dir / "com.apple.notificationcenter" / "db" / "db",
            ]
        )

    legacy_dir = Path.home() / "Library" / "Application Support" / "NotificationCenter"
    try:
        candidates.extend(sorted(legacy_dir.glob("*.db")))
    except OSError:
        pass

    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            deduped.append(candidate)
    return deduped


def detect_notification_db_path() -> Path:
    for candidate in notification_db_candidates():
        if path_is_probably_present(candidate):
            return candidate
    return DEFAULT_NOTIFICATION_DB


def sqlite_uri(path: Path) -> str:
    return "file:" + urllib.parse.quote(str(path), safe="/:") + "?mode=ro"


def connect_messages_db(path: Path) -> sqlite3.Connection:
    if not path_is_probably_present(path):
        raise FileNotFoundError(f"Messages database not found: {path}")
    conn = sqlite3.connect(sqlite_uri(path), uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def get_max_rowid(config: Config) -> int:
    with connect_messages_db(config.messages_db_path) as conn:
        row = conn.execute("SELECT COALESCE(MAX(ROWID), 0) AS max_rowid FROM message").fetchone()
    return int(row["max_rowid"])


def get_max_notification_rec_id(config: Config) -> int:
    with connect_messages_db(config.notification_db_path) as conn:
        row = conn.execute("SELECT COALESCE(MAX(rec_id), 0) AS max_rec_id FROM record").fetchone()
    return int(row["max_rec_id"])


def fetch_messages_after(config: Config, last_rowid: int) -> list[MessageRow]:
    query = """
        SELECT
            m.ROWID AS rowid,
            m.guid AS guid,
            m.text AS text,
            m.attributedBody AS attributed_body,
            m.date AS date_raw,
            m.is_from_me AS is_from_me,
            m.service AS service,
            h.id AS sender,
            COALESCE(NULLIF(c.display_name, ''), c.chat_identifier) AS chat_name,
            COUNT(a.ROWID) AS attachment_count
        FROM message m
        LEFT JOIN handle h ON h.ROWID = m.handle_id
        LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        LEFT JOIN chat c ON c.ROWID = cmj.chat_id
        LEFT JOIN message_attachment_join maj ON maj.message_id = m.ROWID
        LEFT JOIN attachment a ON a.ROWID = maj.attachment_id
        WHERE m.ROWID > ?
          AND (? = 0 OR m.is_from_me = 0)
        GROUP BY m.ROWID
        ORDER BY m.ROWID ASC
        LIMIT ?
    """
    with connect_messages_db(config.messages_db_path) as conn:
        rows = conn.execute(
            query,
            (
                last_rowid,
                1 if config.forward_incoming_only else 0,
                config.batch_limit,
            ),
        ).fetchall()
    return [row_to_message(row) for row in rows]


def fetch_notifications_after(config: Config, last_rec_id: int) -> list[NotificationRow]:
    query = """
        SELECT
            r.rec_id AS rec_id,
            a.identifier AS bundle_id,
            r.data AS data_blob,
            r.delivered_date AS delivered_date,
            r.presented AS presented
        FROM record r
        LEFT JOIN app a ON a.app_id = r.app_id
        WHERE r.rec_id > ?
          AND (? = 0 OR r.presented = 1)
        ORDER BY r.rec_id ASC
        LIMIT ?
    """
    with connect_messages_db(config.notification_db_path) as conn:
        rows = conn.execute(
            query,
            (
                last_rec_id,
                1 if config.notification_presented_only else 0,
                config.batch_limit,
            ),
        ).fetchall()
    return [row_to_notification(row) for row in rows]


def fetch_latest_messages(config: Config, limit: int) -> list[MessageRow]:
    query = """
        SELECT
            m.ROWID AS rowid,
            m.guid AS guid,
            m.text AS text,
            m.attributedBody AS attributed_body,
            m.date AS date_raw,
            m.is_from_me AS is_from_me,
            m.service AS service,
            h.id AS sender,
            COALESCE(NULLIF(c.display_name, ''), c.chat_identifier) AS chat_name,
            COUNT(a.ROWID) AS attachment_count
        FROM message m
        LEFT JOIN handle h ON h.ROWID = m.handle_id
        LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        LEFT JOIN chat c ON c.ROWID = cmj.chat_id
        LEFT JOIN message_attachment_join maj ON maj.message_id = m.ROWID
        LEFT JOIN attachment a ON a.ROWID = maj.attachment_id
        WHERE (? = 0 OR m.is_from_me = 0)
        GROUP BY m.ROWID
        ORDER BY m.ROWID DESC
        LIMIT ?
    """
    with connect_messages_db(config.messages_db_path) as conn:
        rows = conn.execute(
            query,
            (
                1 if config.forward_incoming_only else 0,
                max(1, limit),
            ),
        ).fetchall()
    return [row_to_message(row) for row in reversed(rows)]


def fetch_latest_notifications(config: Config, limit: int) -> list[NotificationRow]:
    query = """
        SELECT
            r.rec_id AS rec_id,
            a.identifier AS bundle_id,
            r.data AS data_blob,
            r.delivered_date AS delivered_date,
            r.presented AS presented
        FROM record r
        LEFT JOIN app a ON a.app_id = r.app_id
        WHERE (? = 0 OR r.presented = 1)
        ORDER BY r.rec_id DESC
        LIMIT ?
    """
    with connect_messages_db(config.notification_db_path) as conn:
        rows = conn.execute(
            query,
            (
                1 if config.notification_presented_only else 0,
                max(1, limit),
            ),
        ).fetchall()
    return [row_to_notification(row) for row in reversed(rows)]


def row_to_message(row: sqlite3.Row) -> MessageRow:
    return MessageRow(
        rowid=int(row["rowid"]),
        guid=row["guid"],
        text=row["text"],
        attributed_body=row["attributed_body"],
        date_raw=row["date_raw"],
        is_from_me=bool(row["is_from_me"]),
        service=row["service"],
        sender=row["sender"],
        chat_name=row["chat_name"],
        attachment_count=int(row["attachment_count"] or 0),
    )


def row_to_notification(row: sqlite3.Row) -> NotificationRow:
    return NotificationRow(
        rec_id=int(row["rec_id"]),
        bundle_id=row["bundle_id"],
        data_blob=row["data_blob"],
        delivered_date=row["delivered_date"],
        presented=bool(row["presented"]),
    )


def decode_attributed_body(blob: bytes | None) -> str | None:
    if not blob:
        return None

    from_archive = decode_nskeyed_archiver_string(blob)
    if from_archive:
        return from_archive

    return decode_attributed_body_fallback(blob)


def decode_nskeyed_archiver_string(blob: bytes) -> str | None:
    try:
        archive = plistlib.loads(blob)
    except Exception:
        return None

    objects = archive.get("$objects")
    if not isinstance(objects, list):
        return None

    def resolve(value: Any) -> Any:
        if isinstance(value, plistlib.UID):
            index = value.data
            if 0 <= index < len(objects):
                return objects[index]
            return None
        return value

    def walk(value: Any, depth: int = 0) -> str | None:
        if depth > 25:
            return None
        value = resolve(value)

        if isinstance(value, str) and is_probable_message_string(value):
            return value

        if isinstance(value, dict):
            preferred = value.get("NS.string") or value.get("NSString")
            if preferred is not None:
                found = walk(preferred, depth + 1)
                if found:
                    return found
            for child in value.values():
                found = walk(child, depth + 1)
                if found:
                    return found

        if isinstance(value, list):
            for child in value:
                found = walk(child, depth + 1)
                if found:
                    return found

        return None

    top = archive.get("$top", {})
    if isinstance(top, dict) and "root" in top:
        found = walk(top["root"])
        if found:
            return clean_message_text(found)

    candidates = [item for item in objects if isinstance(item, str) and is_probable_message_string(item)]
    if not candidates:
        return None
    return clean_message_text(max(candidates, key=len))


def is_probable_message_string(value: str) -> bool:
    stripped = clean_message_text(value)
    if not stripped:
        return False
    if stripped in IGNORED_ARCHIVE_STRINGS:
        return False
    if stripped.startswith("NS") and len(stripped) < 40:
        return False
    if stripped.startswith("__kIM") or stripped.startswith("IM"):
        return False
    return True


def decode_attributed_body_fallback(blob: bytes) -> str | None:
    text = blob.decode("utf-8", errors="ignore")
    if not text:
        return None

    if "NSString" in text:
        text = text.split("NSString", 1)[1]
    if "NSDictionary" in text:
        text = text.split("NSDictionary", 1)[0]

    runs = re.findall(r"[^\x00-\x08\x0b\x0c\x0e-\x1f\x7f]{1,}", text)
    candidates = [clean_message_text(run) for run in runs]
    candidates = [candidate for candidate in candidates if is_probable_message_string(candidate)]
    if not candidates:
        return None
    return max(candidates, key=len)


def clean_message_text(value: str) -> str:
    return value.replace("\ufffc", "").strip()


def parse_notification_blob(blob: bytes | None) -> dict[str, Any]:
    if not blob:
        return {}
    try:
        parsed = plistlib.loads(blob)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}

    req = parsed.get("req")
    if not isinstance(req, dict):
        req = {}

    return {
        "title": plist_text(req.get("titl")),
        "subtitle": plist_text(req.get("subt")),
        "body": plist_text(req.get("body")),
        "category": plist_text(req.get("cate")),
        "identifier": plist_text(req.get("iden")),
        "source": plist_text(parsed.get("srce") or req.get("srce")),
        "app": plist_text(parsed.get("app")),
    }


def plist_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return clean_message_text(value)
    if isinstance(value, bytes):
        return clean_message_text(value.decode("utf-8", errors="replace"))
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        parts = [plist_text(item) for item in value]
        parts = [part for part in parts if part]
        return ", ".join(parts) if parts else None
    if isinstance(value, dict):
        return None
    return clean_message_text(str(value))


def apple_date_to_local(date_raw: int | float | None) -> str:
    if not date_raw:
        return "unknown time"

    raw = float(date_raw)
    if raw > 100_000_000_000_000:
        seconds = raw / 1_000_000_000
    elif raw > 100_000_000_000:
        seconds = raw / 1_000_000
    else:
        seconds = raw

    try:
        local_dt = (APPLE_EPOCH + dt.timedelta(seconds=seconds)).astimezone()
    except OverflowError:
        return "unknown time"
    return local_dt.strftime("%Y-%m-%d %H:%M:%S %Z")


def matches_filter(value: str | None, allowed: tuple[str, ...]) -> bool:
    if not allowed:
        return True
    normalized = (value or "").lower()
    return any(item in normalized for item in allowed)


def should_forward(config: Config, message: MessageRow) -> bool:
    if not config.forward_empty_messages and not message.body:
        return False
    if not matches_filter(message.sender, config.sender_allowlist):
        return False
    if not matches_filter(message.chat_name, config.chat_allowlist):
        return False
    if not matches_filter(message.service, config.service_allowlist):
        return False
    return True


def should_forward_notification(config: Config, notification: NotificationRow) -> bool:
    parsed = notification.parsed
    text_parts = [
        parsed.get("title"),
        parsed.get("subtitle"),
        parsed.get("body"),
    ]
    if not any(text_parts):
        return False
    bundle_id = notification.bundle_id or parsed.get("app")
    if not matches_filter(bundle_id, config.notification_app_allowlist):
        return False
    normalized_bundle = (bundle_id or "").lower()
    if any(item in normalized_bundle for item in config.notification_app_denylist):
        return False
    return True


def format_message(config: Config, message: MessageRow) -> str:
    sender = message.sender or "unknown sender"
    chat = message.chat_name or sender
    service = message.service or "Messages"
    direction = "sent from this Mac" if message.is_from_me else "incoming"

    body = message.body
    if config.message_text_mode == "redacted":
        body = "[message body hidden]"
    elif config.message_text_mode == "sender_only":
        body = ""

    lines = [
        f"[{service}] {direction}",
        f"Time: {apple_date_to_local(message.date_raw)}",
        f"From: {sender}",
    ]
    if chat and chat != sender:
        lines.append(f"Chat: {chat}")
    if body:
        lines.extend(["", body])
    if message.attachment_count and "[attachment" not in body.lower():
        lines.append(f"\nAttachments: {message.attachment_count}")

    return trim_telegram_text("\n".join(lines))


def format_notification(config: Config, notification: NotificationRow) -> str:
    parsed = notification.parsed
    bundle_id = notification.bundle_id or parsed.get("app") or "unknown app"
    title = parsed.get("title") or ""
    subtitle = parsed.get("subtitle") or ""
    body = parsed.get("body") or ""

    if config.notification_text_mode == "redacted":
        title = title or "[notification]"
        subtitle = ""
        body = "[notification body hidden]"
    elif config.notification_text_mode == "app_only":
        title = ""
        subtitle = ""
        body = ""

    lines = [
        "[Notification]",
        f"Time: {apple_date_to_local(notification.delivered_date)}",
        f"App: {bundle_id}",
    ]
    if title:
        lines.append(f"Title: {title}")
    if subtitle:
        lines.append(f"Subtitle: {subtitle}")
    if body:
        lines.extend(["", body])

    if parsed.get("category"):
        lines.append(f"\nCategory: {parsed['category']}")

    return trim_telegram_text("\n".join(lines))


def trim_telegram_text(text: str) -> str:
    if len(text) <= TELEGRAM_MAX_TEXT:
        return text
    suffix = "\n\n[truncated]"
    return text[: TELEGRAM_MAX_TEXT - len(suffix)] + suffix


def telegram_api_url(config: Config, method: str) -> str:
    token = urllib.parse.quote(config.telegram_bot_token, safe=":")
    return f"https://api.telegram.org/bot{token}/{method}"


def telegram_request(config: Config, method: str, payload: dict[str, Any] | None = None) -> Any:
    payload = payload or {}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        telegram_api_url(config, method),
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Telegram HTTP {exc.code}: {raw}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Telegram request failed: {exc}") from exc

    parsed = json.loads(raw)
    if not parsed.get("ok"):
        description = parsed.get("description", "unknown Telegram API error")
        raise RuntimeError(f"Telegram API error: {description}")
    return parsed.get("result")


def send_telegram_message(config: Config, text: str) -> None:
    telegram_request(
        config,
        "sendMessage",
        {
            "chat_id": config.telegram_chat_id,
            "text": trim_telegram_text(text),
            "disable_notification": config.disable_notification,
            "protect_content": config.protect_content,
        },
    )


def forward_rows(config: Config, rows: list[MessageRow], state: dict[str, Any], dry_run: bool) -> int:
    forwarded = 0
    for message in rows:
        state["messages_last_rowid"] = max(int(state.get("messages_last_rowid", 0)), message.rowid)

        if not should_forward(config, message):
            logging.debug("Skipping message ROWID=%s due to filters", message.rowid)
            save_state(config.state_path, state)
            continue

        formatted = format_message(config, message)
        if dry_run:
            print(f"\n--- ROWID {message.rowid} ---\n{formatted}")
        else:
            send_telegram_message(config, formatted)
            logging.info("Forwarded message ROWID=%s sender=%s", message.rowid, message.sender)

        forwarded += 1
        save_state(config.state_path, state)

    return forwarded


def forward_notifications(
    config: Config,
    rows: list[NotificationRow],
    state: dict[str, Any],
    dry_run: bool,
) -> int:
    forwarded = 0
    for notification in rows:
        state["notifications_last_rec_id"] = max(
            int(state.get("notifications_last_rec_id", 0)),
            notification.rec_id,
        )

        if not should_forward_notification(config, notification):
            logging.debug("Skipping notification rec_id=%s due to filters", notification.rec_id)
            save_state(config.state_path, state)
            continue

        formatted = format_notification(config, notification)
        if dry_run:
            print(f"\n--- NOTIFICATION rec_id {notification.rec_id} ---\n{formatted}")
        else:
            send_telegram_message(config, formatted)
            logging.info(
                "Forwarded notification rec_id=%s bundle=%s",
                notification.rec_id,
                notification.bundle_id,
            )

        forwarded += 1
        save_state(config.state_path, state)

    return forwarded


def initialize_state(
    config: Config,
    message_backfill: int,
    notification_backfill: int,
    dry_run: bool,
) -> dict[str, Any]:
    state = load_state(config.state_path)

    if "last_rowid" in state and "messages_last_rowid" not in state:
        state["messages_last_rowid"] = state.pop("last_rowid")

    if config.watch_messages and "messages_last_rowid" not in state:
        if message_backfill > 0:
            rows = fetch_latest_messages(config, message_backfill)
            if rows:
                state["messages_last_rowid"] = rows[0].rowid - 1
                save_state(config.state_path, state)
                forward_rows(config, rows, state, dry_run=dry_run)
            else:
                state["messages_last_rowid"] = get_max_rowid(config)
        else:
            state["messages_last_rowid"] = get_max_rowid(config)
        logging.info("Initialized Messages state at ROWID=%s", state["messages_last_rowid"])

    if config.watch_notifications and "notifications_last_rec_id" not in state:
        if notification_backfill > 0:
            rows = fetch_latest_notifications(config, notification_backfill)
            if rows:
                state["notifications_last_rec_id"] = rows[0].rec_id - 1
                save_state(config.state_path, state)
                forward_notifications(config, rows, state, dry_run=dry_run)
            else:
                state["notifications_last_rec_id"] = get_max_notification_rec_id(config)
        else:
            state["notifications_last_rec_id"] = get_max_notification_rec_id(config)
        logging.info(
            "Initialized Notification Center state at rec_id=%s",
            state["notifications_last_rec_id"],
        )

    state["initialized_at"] = state.get("initialized_at") or dt.datetime.now(dt.timezone.utc).isoformat()
    save_state(config.state_path, state)
    return state


def run_loop(config: Config, message_backfill: int, notification_backfill: int, dry_run: bool) -> None:
    require_telegram_config(config)
    state = initialize_state(
        config,
        message_backfill=message_backfill,
        notification_backfill=notification_backfill,
        dry_run=dry_run,
    )

    if config.send_startup_message and not dry_run:
        hostname = socket.gethostname()
        send_telegram_message(config, f"{APP_NAME} started on {hostname}.")

    if config.watch_messages:
        logging.info("Watching Messages DB: %s", config.messages_db_path)
    if config.watch_notifications:
        logging.info("Watching Notification Center DB: %s", config.notification_db_path)

    while True:
        try:
            if config.watch_messages:
                rows = fetch_messages_after(config, int(state.get("messages_last_rowid", 0)))
                if rows:
                    forward_rows(config, rows, state, dry_run=dry_run)
            if config.watch_notifications:
                notifications = fetch_notifications_after(
                    config,
                    int(state.get("notifications_last_rec_id", 0)),
                )
                if notifications:
                    forward_notifications(config, notifications, state, dry_run=dry_run)
            if not config.watch_messages and not config.watch_notifications:
                logging.warning("Both WATCH_MESSAGES and WATCH_NOTIFICATIONS are disabled")
            else:
                state = load_state(config.state_path) or state
        except KeyboardInterrupt:
            raise
        except Exception:
            logging.exception("Polling failed")
        time.sleep(config.poll_interval_seconds)


def run_once(config: Config, message_backfill: int, notification_backfill: int, dry_run: bool) -> None:
    require_telegram_config(config)
    state = initialize_state(
        config,
        message_backfill=message_backfill,
        notification_backfill=notification_backfill,
        dry_run=dry_run,
    )
    message_count = 0
    notification_count = 0
    if config.watch_messages:
        rows = fetch_messages_after(config, int(state.get("messages_last_rowid", 0)))
        message_count = forward_rows(config, rows, state, dry_run=dry_run)
    if config.watch_notifications:
        notifications = fetch_notifications_after(config, int(state.get("notifications_last_rec_id", 0)))
        notification_count = forward_notifications(config, notifications, state, dry_run=dry_run)
    logging.info(
        "Forwarded %s message(s), %s notification(s)",
        message_count,
        notification_count,
    )


def init_state(config: Config) -> None:
    state: dict[str, Any] = {"initialized_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    if config.watch_messages:
        state["messages_last_rowid"] = get_max_rowid(config)
    if config.watch_notifications:
        state["notifications_last_rec_id"] = get_max_notification_rec_id(config)
    save_state(config.state_path, state)
    print(f"Initialized {config.state_path}: {json.dumps(state, ensure_ascii=False)}")


def test_telegram(config: Config) -> None:
    require_telegram_config(config)
    hostname = socket.gethostname()
    now = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    send_telegram_message(config, f"{APP_NAME} test from {hostname} at {now}.")
    print("Sent Telegram test message.")


def print_chat_ids(config: Config) -> None:
    if not config.telegram_bot_token:
        raise SystemExit(f"Missing TELEGRAM_BOT_TOKEN. Edit {DEFAULT_CONFIG_PATH} or pass --config PATH.")
    result = telegram_request(config, "getUpdates", {"limit": 100, "timeout": 0})
    seen: set[int] = set()
    for update in result:
        message = (
            update.get("message")
            or update.get("edited_message")
            or update.get("channel_post")
            or update.get("my_chat_member")
        )
        if not isinstance(message, dict):
            continue
        chat = message.get("chat")
        if not isinstance(chat, dict):
            continue
        chat_id = chat.get("id")
        if chat_id in seen:
            continue
        seen.add(chat_id)
        label = chat.get("title") or " ".join(
            part for part in [chat.get("first_name"), chat.get("last_name")] if part
        )
        print(f"{chat_id}\t{chat.get('type', 'unknown')}\t{label or '(no label)'}")

    if not seen:
        print("No chats found. Send any message to your bot in Telegram, then run this again.")


def render_sample(config: Config, limit: int) -> None:
    rows = fetch_latest_messages(config, limit)
    for message in rows:
        print(f"\n--- ROWID {message.rowid} ---")
        print(format_message(config, message))


def render_notification_sample(config: Config, limit: int) -> None:
    rows = fetch_latest_notifications(config, limit)
    for notification in rows:
        print(f"\n--- NOTIFICATION rec_id {notification.rec_id} ---")
        print(format_notification(config, notification))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Path to KEY=VALUE config file.")

    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="Watch enabled sources forever and forward new rows.")
    run_parser.add_argument("--backfill", type=int, default=0, help="On first run, forward newest N messages.")
    run_parser.add_argument(
        "--notification-backfill",
        type=int,
        default=0,
        help="On first run, forward newest N Notification Center records.",
    )
    run_parser.add_argument("--dry-run", action="store_true", help="Print forwarded messages instead of sending.")

    once_parser = subparsers.add_parser("once", help="Forward currently pending rows and exit.")
    once_parser.add_argument("--backfill", type=int, default=0, help="On first run, forward newest N messages.")
    once_parser.add_argument(
        "--notification-backfill",
        type=int,
        default=0,
        help="On first run, forward newest N Notification Center records.",
    )
    once_parser.add_argument("--dry-run", action="store_true", help="Print forwarded messages instead of sending.")

    subparsers.add_parser("init-state", help="Mark all current Messages rows as already seen.")
    subparsers.add_parser("test-telegram", help="Send a test Telegram message.")
    subparsers.add_parser("chat-id", help="Print Telegram chat IDs found via getUpdates.")

    sample_parser = subparsers.add_parser("sample", help="Print newest parsed Messages rows without Telegram.")
    sample_parser.add_argument("--limit", type=int, default=5)

    notification_sample_parser = subparsers.add_parser(
        "notification-sample",
        help="Print newest parsed Notification Center rows without Telegram.",
    )
    notification_sample_parser.add_argument("--limit", type=int, default=5)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = load_config(expand_path(args.config))
    configure_logging(config.log_level)

    command = args.command or "run"
    try:
        if command == "run":
            run_loop(
                config,
                message_backfill=getattr(args, "backfill", 0),
                notification_backfill=getattr(args, "notification_backfill", 0),
                dry_run=getattr(args, "dry_run", False),
            )
        elif command == "once":
            run_once(
                config,
                message_backfill=args.backfill,
                notification_backfill=args.notification_backfill,
                dry_run=args.dry_run,
            )
        elif command == "init-state":
            init_state(config)
        elif command == "test-telegram":
            test_telegram(config)
        elif command == "chat-id":
            print_chat_ids(config)
        elif command == "sample":
            render_sample(config, limit=args.limit)
        elif command == "notification-sample":
            render_notification_sample(config, limit=args.limit)
        else:
            parser.error(f"Unknown command: {html.escape(command)}")
    except KeyboardInterrupt:
        print("Stopped.")
        return 130
    except PermissionError as exc:
        print(f"Permission error: {exc}", file=sys.stderr)
        print("Grant Full Disk Access to Terminal, Python, or the launchd service runner.", file=sys.stderr)
        return 2
    except sqlite3.OperationalError as exc:
        print(f"SQLite error: {exc}", file=sys.stderr)
        print("If this is an access error, grant Full Disk Access and retry.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
