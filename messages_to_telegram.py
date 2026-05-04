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
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable


APP_NAME = "messages-to-telegram"
DEFAULT_APP_DIR = Path.home() / "Library" / "Application Support" / APP_NAME
DEFAULT_CONFIG_PATH = DEFAULT_APP_DIR / "config.env"
DEFAULT_STATE_PATH = DEFAULT_APP_DIR / "state.json"
DEFAULT_APP_MAP_PATH = DEFAULT_APP_DIR / "app_map.json"
DEFAULT_PARCELS_PATH = DEFAULT_APP_DIR / "parcels.json"
DEFAULT_MESSAGES_DB = Path.home() / "Library" / "Messages" / "chat.db"
DEFAULT_NOTIFICATION_DB = (
    Path.home() / "Library" / "Group Containers" / "group.com.apple.usernoted" / "db2" / "db"
)
APPLE_EPOCH = dt.datetime(2001, 1, 1, tzinfo=dt.timezone.utc)
TELEGRAM_MAX_TEXT = 4096
HTTP_USER_AGENT = "messages-to-telegram/0.1"
DEFAULT_NEWS_LANGUAGE = "ko"
DEFAULT_NEWS_COUNTRY = "KR"
DEFAULT_STOCK_WATCHLIST = "^GSPC,^IXIC,AAPL,NVDA,005930.KS"
DEFAULT_PARCEL_PROVIDER = "naver_scrape"
DEFAULT_PARCEL_POLL_INTERVAL_SECONDS = 3600
DEFAULT_NAVER_PARCEL_SEARCH_URL = (
    "https://search.naver.com/search.naver?query=%ED%83%9D%EB%B0%B0%EC%A1%B0%ED%9A%8C"
)
NAVER_PARCEL_API_URL = "https://ts-proxy.naver.com/ocontent/util/headerjson.naver"
NAVER_PARCEL_CARRIERS = {
    "04": "CJ대한통운",
    "01": "우체국택배",
    "05": "한진택배",
    "08": "롯데택배",
    "06": "로젠택배",
    "54": "홈픽",
    "24": "GS25편의점택배",
    "46": "CU 편의점택배",
    "23": "경동택배",
    "22": "대신택배",
    "11": "일양로지스",
    "32": "합동택배",
    "18": "건영택배",
    "17": "천일택배",
    "20": "한진택배B2B",
    "16": "한의사랑택배",
    "12": "EMS",
    "25": "TNT Express",
    "14": "UPS",
    "21": "FedEx",
    "26": "USPS",
    "45": "우리택배(구호남택배)",
    "44": "SLX택배",
    "47": "우리한방택배",
    "53": "농협택배",
    "94": "카카오T당일배송",
    "92": "지니고 당일배송",
    "101": "한샘서비스 택배",
    "173": "물류대장(택배)",
    "189": "세븐일레븐 착한택배",
}
NAVER_PARCEL_CARRIER_ALIASES = {
    "cj": "04",
    "cj대한통운": "04",
    "대한통운": "04",
    "우체국": "01",
    "epost": "01",
    "한진": "05",
    "롯데": "08",
    "롯데글로벌로지스": "08",
    "로젠": "06",
    "logen": "06",
    "홈픽": "54",
    "gs25": "24",
    "cu": "46",
    "경동": "23",
    "대신": "22",
    "일양": "11",
    "합동": "32",
    "건영": "18",
    "천일": "17",
    "ems": "12",
    "tnt": "25",
    "ups": "14",
    "fedex": "21",
    "페덱스": "21",
    "usps": "26",
    "우리": "45",
    "slx": "44",
    "농협": "53",
    "카카오": "94",
}

ENV_KEYS = {
    "WATCH_MESSAGES",
    "WATCH_NOTIFICATIONS",
    "WATCH_PARCELS",
    "BOT_COMMANDS_ENABLED",
    "BOT_ALLOWED_CHAT_IDS",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "MESSAGES_DB_PATH",
    "NOTIFICATION_DB_PATH",
    "APP_MAP_PATH",
    "PARCELS_PATH",
    "STATE_PATH",
    "POLL_INTERVAL_SECONDS",
    "PARCEL_POLL_INTERVAL_SECONDS",
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
    "NEWS_LANGUAGE",
    "NEWS_COUNTRY",
    "STOCK_WATCHLIST",
    "PARCEL_PROVIDER",
    "NAVER_PARCEL_PASSPORT_KEY",
    "NAVER_PARCEL_SEARCH_URL",
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
    config_path: Path
    watch_messages: bool
    watch_notifications: bool
    watch_parcels: bool
    bot_commands_enabled: bool
    bot_allowed_chat_ids: tuple[str, ...]
    telegram_bot_token: str
    telegram_chat_id: str
    messages_db_path: Path
    notification_db_path: Path
    app_map_path: Path
    parcels_path: Path
    state_path: Path
    poll_interval_seconds: float
    parcel_poll_interval_seconds: float
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
    news_language: str
    news_country: str
    stock_watchlist: tuple[str, ...]
    parcel_provider: str
    naver_parcel_passport_key: str
    naver_parcel_search_url: str
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


@dataclass(frozen=True)
class ParcelTrackingEvent:
    time_text: str
    location: str
    status: str
    raw_time: int | float | None = None


@dataclass(frozen=True)
class ParcelTrackingResult:
    carrier_code: str
    carrier_name: str
    invoice: str
    status: str
    complete: bool
    events: tuple[ParcelTrackingEvent, ...]
    estimate: str | None
    checked_at: str
    raw: dict[str, Any]

    @property
    def latest_event(self) -> ParcelTrackingEvent | None:
        return self.events[-1] if self.events else None

    @property
    def signature(self) -> str:
        latest = self.latest_event
        return json.dumps(
            {
                "status": self.status,
                "complete": self.complete,
                "estimate": self.estimate or "",
                "event_count": len(self.events),
                "latest": {
                    "time": latest.time_text if latest else "",
                    "where": latest.location if latest else "",
                    "kind": latest.status if latest else "",
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        )


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
        config_path=config_path,
        watch_messages=parse_bool(raw.get("WATCH_MESSAGES"), True),
        watch_notifications=parse_bool(raw.get("WATCH_NOTIFICATIONS"), False),
        watch_parcels=parse_bool(raw.get("WATCH_PARCELS"), True),
        bot_commands_enabled=parse_bool(raw.get("BOT_COMMANDS_ENABLED"), True),
        bot_allowed_chat_ids=parse_csv(raw.get("BOT_ALLOWED_CHAT_IDS")),
        telegram_bot_token=token,
        telegram_chat_id=chat_id,
        messages_db_path=expand_path(raw.get("MESSAGES_DB_PATH", str(DEFAULT_MESSAGES_DB))),
        notification_db_path=expand_path(
            raw.get("NOTIFICATION_DB_PATH", str(detect_notification_db_path()))
        ),
        app_map_path=expand_path(raw.get("APP_MAP_PATH", str(DEFAULT_APP_MAP_PATH))),
        parcels_path=expand_path(raw.get("PARCELS_PATH", str(DEFAULT_PARCELS_PATH))),
        state_path=expand_path(raw.get("STATE_PATH", str(DEFAULT_STATE_PATH))),
        poll_interval_seconds=float(raw.get("POLL_INTERVAL_SECONDS", "5")),
        parcel_poll_interval_seconds=max(
            60.0,
            float(raw.get("PARCEL_POLL_INTERVAL_SECONDS", str(DEFAULT_PARCEL_POLL_INTERVAL_SECONDS))),
        ),
        batch_limit=max(1, int(raw.get("BATCH_LIMIT", "20"))),
        forward_incoming_only=parse_bool(raw.get("FORWARD_INCOMING_ONLY"), True),
        forward_empty_messages=parse_bool(raw.get("FORWARD_EMPTY_MESSAGES"), False),
        sender_allowlist=normalize_filter(parse_csv(raw.get("SENDER_ALLOWLIST"))),
        chat_allowlist=normalize_filter(parse_csv(raw.get("CHAT_ALLOWLIST"))),
        service_allowlist=normalize_filter(parse_csv(raw.get("SERVICE_ALLOWLIST"))),
        notification_app_allowlist=normalize_filter(parse_csv(raw.get("NOTIFICATION_APP_ALLOWLIST"))),
        notification_app_denylist=normalize_filter(
            parse_csv(
                raw.get(
                    "NOTIFICATION_APP_DENYLIST",
                    "com.apple.MobileSMS,com.apple.iChat,com.tdesktop.telegram,org.telegram.desktop,ru.keepcoder.Telegram",
                )
            )
        ),
        notification_presented_only=parse_bool(raw.get("NOTIFICATION_PRESENTED_ONLY"), False),
        notification_text_mode=raw.get("NOTIFICATION_TEXT_MODE", "full").strip().lower(),
        message_text_mode=raw.get("MESSAGE_TEXT_MODE", "full").strip().lower(),
        disable_notification=parse_bool(raw.get("DISABLE_NOTIFICATION"), False),
        protect_content=parse_bool(raw.get("PROTECT_CONTENT"), False),
        send_startup_message=parse_bool(raw.get("SEND_STARTUP_MESSAGE"), True),
        news_language=raw.get("NEWS_LANGUAGE", DEFAULT_NEWS_LANGUAGE).strip() or DEFAULT_NEWS_LANGUAGE,
        news_country=raw.get("NEWS_COUNTRY", DEFAULT_NEWS_COUNTRY).strip().upper() or DEFAULT_NEWS_COUNTRY,
        stock_watchlist=parse_csv(raw.get("STOCK_WATCHLIST", DEFAULT_STOCK_WATCHLIST)),
        parcel_provider=raw.get("PARCEL_PROVIDER", DEFAULT_PARCEL_PROVIDER).strip().lower()
        or DEFAULT_PARCEL_PROVIDER,
        naver_parcel_passport_key=raw.get("NAVER_PARCEL_PASSPORT_KEY", "").strip(),
        naver_parcel_search_url=raw.get(
            "NAVER_PARCEL_SEARCH_URL",
            DEFAULT_NAVER_PARCEL_SEARCH_URL,
        ).strip()
        or DEFAULT_NAVER_PARCEL_SEARCH_URL,
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


def load_app_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logging.warning("Invalid app map JSON: %s", path)
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        str(key).strip(): str(value).strip()
        for key, value in raw.items()
        if str(key).strip() and str(value).strip()
    }


def save_app_map(path: Path, app_map: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(dict(sorted(app_map.items())), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def load_parcels(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logging.warning("Invalid parcels JSON: %s", path)
        return []
    if isinstance(raw, dict):
        raw_parcels = raw.get("parcels", [])
    else:
        raw_parcels = raw
    if not isinstance(raw_parcels, list):
        return []
    return [item for item in raw_parcels if isinstance(item, dict)]


def save_parcels(path: Path, parcels: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps({"parcels": parcels}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def normalize_parcel_invoice(invoice: str) -> str:
    return re.sub(r"[\s-]+", "", invoice.strip())


def normalize_carrier_token(value: str) -> str:
    return re.sub(r"[\s_()（）/.-]+", "", value.strip().lower()).replace("택배", "")


def resolve_parcel_carrier(value: str) -> tuple[str, str] | None:
    raw = value.strip()
    if raw in NAVER_PARCEL_CARRIERS:
        return raw, NAVER_PARCEL_CARRIERS[raw]

    normalized = normalize_carrier_token(raw)
    alias_code = NAVER_PARCEL_CARRIER_ALIASES.get(normalized)
    if alias_code:
        return alias_code, NAVER_PARCEL_CARRIERS[alias_code]

    for code, name in NAVER_PARCEL_CARRIERS.items():
        if normalized in {normalize_carrier_token(name), normalize_carrier_token(code)}:
            return code, name
    for code, name in NAVER_PARCEL_CARRIERS.items():
        if normalized and normalized in normalize_carrier_token(name):
            return code, name
    return None


def parcel_record_id(carrier_code: str, invoice: str) -> str:
    return f"{carrier_code}:{normalize_parcel_invoice(invoice)}"


def select_parcel_records(parcels: list[dict[str, Any]], selector: str | None) -> list[dict[str, Any]]:
    if not selector or selector.lower() == "all":
        return parcels
    needle = selector.strip().lower()
    normalized_invoice = normalize_parcel_invoice(selector).lower()
    return [
        parcel
        for parcel in parcels
        if needle == str(parcel.get("id", "")).lower()
        or normalized_invoice == str(parcel.get("invoice", "")).lower()
        or needle in str(parcel.get("label", "")).lower()
        or needle in str(parcel.get("carrier_name", "")).lower()
    ]


def app_display_name(config: Config, bundle_id: str | None, app_map: dict[str, str] | None = None) -> str:
    bundle = bundle_id or "unknown app"
    app_map = app_map if app_map is not None else load_app_map(config.app_map_path)
    return app_map.get(bundle, bundle)


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


def fetch_recent_notifications(config: Config, limit: int, app_filter: str | None = None) -> list[NotificationRow]:
    limit = max(1, min(limit, 50))
    read_limit = limit if not app_filter else min(max(limit * 20, 100), 1000)
    query = """
        SELECT
            r.rec_id AS rec_id,
            a.identifier AS bundle_id,
            r.data AS data_blob,
            r.delivered_date AS delivered_date,
            r.presented AS presented
        FROM record r
        LEFT JOIN app a ON a.app_id = r.app_id
        ORDER BY r.rec_id DESC
        LIMIT ?
    """
    with connect_messages_db(config.notification_db_path) as conn:
        rows = conn.execute(query, (read_limit,)).fetchall()

    notifications = [row_to_notification(row) for row in rows]
    if app_filter:
        needle = app_filter.strip().lower()
        app_map = load_app_map(config.app_map_path)
        notifications = [
            notification
            for notification in notifications
            if needle in (notification.bundle_id or "").lower()
            or needle in app_display_name(config, notification.bundle_id, app_map).lower()
        ]
    return notifications[:limit]


def fetch_notification_by_rec_id(config: Config, rec_id: int) -> NotificationRow | None:
    query = """
        SELECT
            r.rec_id AS rec_id,
            a.identifier AS bundle_id,
            r.data AS data_blob,
            r.delivered_date AS delivered_date,
            r.presented AS presented
        FROM record r
        LEFT JOIN app a ON a.app_id = r.app_id
        WHERE r.rec_id = ?
        LIMIT 1
    """
    with connect_messages_db(config.notification_db_path) as conn:
        row = conn.execute(query, (rec_id,)).fetchone()
    return row_to_notification(row) if row else None


def fetch_notification_app_stats(config: Config, limit: int) -> list[dict[str, Any]]:
    query = """
        SELECT
            a.identifier AS bundle_id,
            COUNT(*) AS count,
            MAX(r.delivered_date) AS last_delivered_date,
            MAX(r.rec_id) AS last_rec_id
        FROM record r
        LEFT JOIN app a ON a.app_id = r.app_id
        GROUP BY a.identifier
        ORDER BY last_rec_id DESC
        LIMIT ?
    """
    with connect_messages_db(config.notification_db_path) as conn:
        rows = conn.execute(query, (max(1, min(limit, 100)),)).fetchall()
    return [dict(row) for row in rows]


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
    try:
        return telegram_request_urllib(config, method, payload)
    except RuntimeError as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
            raise
        logging.debug("Python TLS verification failed; retrying Telegram request with curl")
        return telegram_request_curl(config, method, payload)


def telegram_request_urllib(config: Config, method: str, payload: dict[str, Any] | None = None) -> Any:
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


def telegram_request_curl(config: Config, method: str, payload: dict[str, Any] | None = None) -> Any:
    curl_path = "/usr/bin/curl"
    if not Path(curl_path).exists():
        raise RuntimeError("Python TLS verification failed and /usr/bin/curl is not available")

    payload = payload or {}
    data = json.dumps(payload, ensure_ascii=False)
    curl_config = "\n".join(
        [
            f'url = "{curl_escape(telegram_api_url(config, method))}"',
            'request = "POST"',
            'header = "Content-Type: application/json"',
            f'data = "{curl_escape(data)}"',
            "silent",
            "show-error",
            'write-out = "\\n%{http_code}"',
            "",
        ]
    )
    proc = subprocess.run(
        [curl_path, "--config", "-"],
        input=curl_config,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Telegram curl request failed: {proc.stderr.strip()}")

    raw_body, _, status_code = proc.stdout.rpartition("\n")
    if not status_code.isdigit():
        raise RuntimeError(f"Telegram curl response missing HTTP status: {proc.stdout}")
    if int(status_code) >= 400:
        raise RuntimeError(f"Telegram HTTP {status_code}: {raw_body}")

    parsed = json.loads(raw_body)
    if not parsed.get("ok"):
        description = parsed.get("description", "unknown Telegram API error")
        raise RuntimeError(f"Telegram API error: {description}")
    return parsed.get("result")


def curl_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def http_get_bytes(url: str, timeout: int = 20, headers: dict[str, str] | None = None) -> bytes:
    request_headers = {"User-Agent": HTTP_USER_AGENT}
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(url, headers=request_headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read()
    except urllib.error.URLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
            raise RuntimeError(f"HTTP request failed: {exc}") from exc

    curl_path = "/usr/bin/curl"
    if not Path(curl_path).exists():
        raise RuntimeError("Python TLS verification failed and /usr/bin/curl is not available")
    proc = subprocess.run(
        build_curl_get_command(url, timeout, request_headers),
        text=False,
        capture_output=True,
        check=False,
        timeout=timeout + 5,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"curl request failed: {stderr}")
    return proc.stdout


def build_curl_get_command(url: str, timeout: int, headers: dict[str, str]) -> list[str]:
    command = ["/usr/bin/curl", "-fsSL", "--max-time", str(timeout)]
    for key, value in headers.items():
        command.extend(["-H", f"{key}: {value}"])
    command.append(url)
    return command


def http_get_json(url: str, timeout: int = 20, headers: dict[str, str] | None = None) -> Any:
    return json.loads(http_get_bytes(url, timeout=timeout, headers=headers).decode("utf-8"))


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


def send_telegram_to_chat(
    config: Config,
    chat_id: str | int,
    text: str,
    reply_markup: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "chat_id": str(chat_id),
        "text": trim_telegram_text(text),
        "disable_web_page_preview": True,
        "disable_notification": config.disable_notification,
        "protect_content": config.protect_content,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    telegram_request(config, "sendMessage", payload)


def answer_callback_query(config: Config, callback_query_id: str, text: str | None = None) -> None:
    payload: dict[str, Any] = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
        payload["show_alert"] = False
    telegram_request(config, "answerCallbackQuery", payload)


def authorized_chat_ids(config: Config) -> set[str]:
    ids = {config.telegram_chat_id.strip()} if config.telegram_chat_id.strip() else set()
    ids.update(item.strip() for item in config.bot_allowed_chat_ids if item.strip())
    return ids


def is_authorized_chat(config: Config, chat_id: Any) -> bool:
    return str(chat_id) in authorized_chat_ids(config)


def parse_duration_seconds(value: str) -> int | None:
    match = re.fullmatch(r"\s*(\d+)\s*([smhd]?)\s*", value.lower())
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2) or "m"
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return amount * multipliers[unit]


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def parse_iso_datetime(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def format_local_datetime(value: dt.datetime | None) -> str:
    if value is None:
        return "not set"
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def notification_short_time(date_raw: int | float | None) -> str:
    if not date_raw:
        return "unknown"
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
        return "unknown"
    return local_dt.strftime("%m-%d %H:%M")


def truncate_cell(value: str, width: int) -> str:
    value = " ".join(value.split())
    if len(value) <= width:
        return value
    if width <= 1:
        return value[:width]
    return value[: width - 1] + "…"


def notification_row_summary(config: Config, notification: NotificationRow) -> str:
    parsed = notification.parsed
    title = parsed.get("title") or ""
    subtitle = parsed.get("subtitle") or ""
    body = parsed.get("body") or ""
    if config.notification_text_mode == "app_only":
        return ""
    if config.notification_text_mode == "redacted":
        return title or "[본문 숨김]"
    parts = [part for part in [title, subtitle, body] if part]
    return " / ".join(parts)


def notification_card_summary(config: Config, notification: NotificationRow, app_map: dict[str, str]) -> str:
    parsed = notification.parsed
    title = parsed.get("title") or "(제목 없음)"
    subtitle = parsed.get("subtitle") or ""
    body = parsed.get("body") or ""
    app_name = app_display_name(config, notification.bundle_id, app_map)
    lines = [
        f"{notification_short_time(notification.delivered_date)} | {app_name}",
        truncate_cell(title, 80),
    ]
    if subtitle:
        lines.append(truncate_cell(subtitle, 80))
    if body and config.notification_text_mode == "full":
        lines.append(truncate_cell(body, 120))
    elif config.notification_text_mode == "redacted":
        lines.append("[본문 숨김]")
    return "\n".join(lines)


def notification_detail_text(config: Config, notification: NotificationRow) -> str:
    parsed = notification.parsed
    app_map = load_app_map(config.app_map_path)
    app_name = app_display_name(config, notification.bundle_id, app_map)
    bundle_id = notification.bundle_id or "unknown app"
    title = parsed.get("title") or ""
    subtitle = parsed.get("subtitle") or ""
    body = parsed.get("body") or ""

    if config.notification_text_mode == "redacted":
        body = "[본문 숨김]"
    elif config.notification_text_mode == "app_only":
        title = ""
        subtitle = ""
        body = ""

    lines = [
        "알림 상세",
        f"rec_id: {notification.rec_id}",
        f"시간: {apple_date_to_local(notification.delivered_date)}",
        f"앱: {app_name}",
        f"번들 ID: {bundle_id}",
    ]
    if title:
        lines.append(f"제목: {title}")
    if subtitle:
        lines.append(f"부제목: {subtitle}")
    if body:
        lines.extend(["", body])
    return trim_telegram_text("\n".join(lines))


def format_table(headers: list[str], rows: list[list[str]], widths: list[int]) -> str:
    def render(values: list[str]) -> str:
        cells = [truncate_cell(value, width).ljust(width) for value, width in zip(values, widths)]
        return " | ".join(cells).rstrip()

    separator = "-+-".join("-" * width for width in widths)
    lines = [render(headers), separator]
    lines.extend(render(row) for row in rows)
    return "\n".join(lines)


def forwarding_suppressed(state: dict[str, Any]) -> bool:
    if state.get("paused"):
        return True
    mute_until = parse_iso_datetime(state.get("mute_until"))
    return bool(mute_until and mute_until > dt.datetime.now(dt.timezone.utc))


def apply_runtime_state(config: Config, state: dict[str, Any]) -> Config:
    updates: dict[str, Any] = {}
    if "runtime_watch_messages" in state:
        updates["watch_messages"] = bool(state["runtime_watch_messages"])
    if "runtime_watch_notifications" in state:
        updates["watch_notifications"] = bool(state["runtime_watch_notifications"])
    if "runtime_watch_parcels" in state:
        updates["watch_parcels"] = bool(state["runtime_watch_parcels"])
    if state.get("runtime_message_text_mode"):
        updates["message_text_mode"] = str(state["runtime_message_text_mode"])
    if state.get("runtime_notification_text_mode"):
        updates["notification_text_mode"] = str(state["runtime_notification_text_mode"])
    return replace(config, **updates) if updates else config


def update_env_value(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    output: list[str] = []
    updated = False
    for line in lines:
        if line.startswith(f"{key}="):
            output.append(f"{key}={value}")
            updated = True
        else:
            output.append(line)
    if not updated:
        output.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


def update_csv_env_value(path: Path, key: str, item: str, add: bool) -> str:
    values = load_env_file(path)
    parts = [part.strip() for part in values.get(key, "").split(",") if part.strip()]
    lowered = {part.lower(): part for part in parts}
    normalized = item.strip()
    if add:
        lowered.setdefault(normalized.lower(), normalized)
    else:
        lowered.pop(normalized.lower(), None)
    result = ",".join(lowered.values())
    update_env_value(path, key, result)
    return result


def fetch_news_items(config: Config, query: str | None, limit: int = 5) -> list[dict[str, str]]:
    limit = max(1, min(limit, 10))
    language = config.news_language
    country = config.news_country
    ceid = f"{country}:{language}"
    params = {"hl": language, "gl": country, "ceid": ceid}
    if query:
        params["q"] = query
        base = "https://news.google.com/rss/search"
    else:
        base = "https://news.google.com/rss"
    url = base + "?" + urllib.parse.urlencode(params)
    root = ET.fromstring(http_get_bytes(url))
    items: list[dict[str, str]] = []
    for item in root.findall("./channel/item"):
        source = item.find("source")
        items.append(
            {
                "title": (item.findtext("title") or "").strip(),
                "link": (item.findtext("link") or "").strip(),
                "published": (item.findtext("pubDate") or "").strip(),
                "source": (source.text or "").strip() if source is not None else "",
            }
        )
        if len(items) >= limit:
            break
    return items


def format_news(config: Config, query: str | None, limit: int = 5) -> str:
    items = fetch_news_items(config, query=query, limit=limit)
    title = "주요 뉴스" if not query else f"뉴스 검색: {query}"
    if not items:
        return f"{title}\n\n결과가 없습니다."
    lines = [title]
    for index, item in enumerate(items, 1):
        source = f" ({item['source']})" if item.get("source") else ""
        lines.append(f"\n{index}. {item['title']}{source}")
        if item.get("link"):
            lines.append(item["link"])
    return trim_telegram_text("\n".join(lines))


def fetch_stock_quote(symbol: str) -> dict[str, Any]:
    encoded = urllib.parse.quote(symbol.strip(), safe="^.")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=1d&interval=1m"
    data = http_get_json(url)
    result = (data.get("chart", {}).get("result") or [None])[0]
    if not result:
        error = data.get("chart", {}).get("error")
        raise RuntimeError(error.get("description", "No quote data") if isinstance(error, dict) else "No quote data")
    meta = result.get("meta", {})
    price = meta.get("regularMarketPrice")
    previous = meta.get("chartPreviousClose") or meta.get("previousClose")
    change = price - previous if isinstance(price, (int, float)) and isinstance(previous, (int, float)) else None
    change_pct = (change / previous * 100) if change is not None and previous else None
    market_time = meta.get("regularMarketTime")
    return {
        "symbol": meta.get("symbol") or symbol.upper(),
        "name": meta.get("longName") or meta.get("shortName") or "",
        "currency": meta.get("currency") or "",
        "exchange": meta.get("exchangeName") or meta.get("fullExchangeName") or "",
        "price": price,
        "previous": previous,
        "change": change,
        "change_pct": change_pct,
        "market_time": market_time,
    }


def format_number(value: Any, decimals: int = 2) -> str:
    if not isinstance(value, (int, float)):
        return "n/a"
    return f"{value:,.{decimals}f}"


def format_stock_quotes(symbols: Iterable[str]) -> str:
    clean_symbols = [symbol.strip().upper() for symbol in symbols if symbol.strip()]
    clean_symbols = clean_symbols[:8]
    if not clean_symbols:
        return "사용법: /stock AAPL 또는 /stock 005930.KS"

    lines = ["주식/지수 조회"]
    for symbol in clean_symbols:
        try:
            quote = fetch_stock_quote(symbol)
        except Exception as exc:
            lines.append(f"\n{symbol}: 조회 실패 ({exc})")
            continue

        change = quote["change"]
        change_pct = quote["change_pct"]
        sign = "+" if isinstance(change, (int, float)) and change > 0 else ""
        market_time = quote.get("market_time")
        time_text = ""
        if isinstance(market_time, (int, float)):
            time_text = dt.datetime.fromtimestamp(market_time).astimezone().strftime("%Y-%m-%d %H:%M %Z")
        name = f" - {quote['name']}" if quote.get("name") else ""
        currency = f" {quote['currency']}" if quote.get("currency") else ""
        exchange = f" [{quote['exchange']}]" if quote.get("exchange") else ""
        lines.append(
            "\n"
            f"{quote['symbol']}{name}{exchange}\n"
            f"Price: {format_number(quote['price'])}{currency}\n"
            f"Change: {sign}{format_number(change)} ({sign}{format_number(change_pct)}%)"
        )
        if time_text:
            lines.append(f"Time: {time_text}")
    return trim_telegram_text("\n".join(lines))


def get_naver_parcel_passport_key(config: Config, state: dict[str, Any], force_refresh: bool = False) -> str:
    if config.naver_parcel_passport_key and not force_refresh:
        return urllib.parse.unquote(config.naver_parcel_passport_key)

    cached_key = str(state.get("naver_parcel_passport_key", ""))
    cached_until = parse_iso_datetime(state.get("naver_parcel_passport_key_expires_at"))
    if (
        cached_key
        and not force_refresh
        and cached_until
        and cached_until > dt.datetime.now(dt.timezone.utc)
    ):
        return cached_key

    html_text = http_get_bytes(
        config.naver_parcel_search_url,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.naver.com/",
        },
    ).decode("utf-8", errors="replace")
    match = re.search(r'"passportKey"\s*:\s*"([^"]+)"', html_text)
    if not match:
        raise RuntimeError("네이버 택배조회 passportKey를 찾지 못했습니다.")

    key = urllib.parse.unquote(match.group(1))
    state["naver_parcel_passport_key"] = key
    state["naver_parcel_passport_key_expires_at"] = (
        dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=6)
    ).isoformat()
    return key


def fetch_parcel_tracking(
    config: Config,
    state: dict[str, Any],
    carrier_code: str,
    invoice: str,
    force_key_refresh: bool = False,
) -> ParcelTrackingResult:
    if config.parcel_provider != DEFAULT_PARCEL_PROVIDER:
        raise RuntimeError(f"지원하지 않는 PARCEL_PROVIDER입니다: {config.parcel_provider}")

    normalized_invoice = normalize_parcel_invoice(invoice)
    passport_key = get_naver_parcel_passport_key(config, state, force_refresh=force_key_refresh)
    params = {
        "callapi": "parceltracking",
        "t_code": carrier_code,
        "t_invoice": normalized_invoice,
        "passportKey": passport_key,
    }
    url = NAVER_PARCEL_API_URL + "?" + urllib.parse.urlencode(params)
    data = http_get_json(
        url,
        headers={
            "Accept": "application/json,text/plain,*/*",
            "Referer": config.naver_parcel_search_url,
            "Origin": "https://search.naver.com",
        },
    )

    if isinstance(data, dict):
        message = data.get("message")
        if isinstance(message, dict) and "유효한 키" in str(message.get("error", "")) and not force_key_refresh:
            return fetch_parcel_tracking(config, state, carrier_code, normalized_invoice, force_key_refresh=True)

    return parse_naver_parcel_tracking(data, carrier_code, normalized_invoice)


def parse_naver_parcel_tracking(data: Any, carrier_code: str, invoice: str) -> ParcelTrackingResult:
    if not isinstance(data, dict):
        raise RuntimeError("네이버 택배조회 응답이 JSON 객체가 아닙니다.")

    message = data.get("message")
    if isinstance(message, dict) and message.get("error"):
        raise RuntimeError(str(message["error"]))

    tracking_info = data.get("tracking_info")
    if isinstance(tracking_info, dict) and tracking_info.get("ErrorMsg"):
        code = tracking_info.get("ErrorCode")
        detail = f" ({code})" if code else ""
        raise RuntimeError(f"{tracking_info['ErrorMsg']}{detail}")

    raw_events = data.get("trackingDetails") or []
    events = []
    if isinstance(raw_events, list):
        for item in raw_events:
            if not isinstance(item, dict):
                continue
            time_text = str(item.get("timeString") or item.get("date") or item.get("time") or "").strip()
            events.append(
                ParcelTrackingEvent(
                    time_text=time_text,
                    location=str(item.get("where") or "").strip(),
                    status=str(item.get("kind") or "").strip(),
                    raw_time=item.get("time") if isinstance(item.get("time"), (int, float)) else None,
                )
            )

    latest = events[-1] if events else None
    status = latest.status if latest and latest.status else ""
    if not status and parse_bool(data.get("complete")):
        status = "배송완료"
    if not status:
        status = "조회됨" if data.get("result") == "Y" else "조회 결과 없음"

    return ParcelTrackingResult(
        carrier_code=carrier_code,
        carrier_name=NAVER_PARCEL_CARRIERS.get(carrier_code, carrier_code),
        invoice=str(data.get("invoiceNo") or invoice),
        status=status,
        complete=parse_bool(data.get("complete")) or str(data.get("completeYN", "")).upper() == "Y",
        events=tuple(events),
        estimate=str(data.get("estimate")).strip() if data.get("estimate") else None,
        checked_at=iso_now(),
        raw=data,
    )


def apply_parcel_result(record: dict[str, Any], result: ParcelTrackingResult) -> bool:
    previous_signature = str(record.get("last_signature") or "")
    record["carrier_code"] = result.carrier_code
    record["carrier_name"] = result.carrier_name
    record["invoice"] = result.invoice
    record["last_checked_at"] = result.checked_at
    record["last_status"] = result.status
    record["last_signature"] = result.signature
    record["last_error"] = ""
    record["complete"] = result.complete
    latest = result.latest_event
    if latest:
        record["last_event_time"] = latest.time_text
        record["last_event_location"] = latest.location
    return bool(previous_signature and previous_signature != result.signature)


def format_parcel_tracking(
    record: dict[str, Any],
    result: ParcelTrackingResult,
    title: str = "택배 조회",
) -> str:
    label = str(record.get("label") or "").strip()
    latest = result.latest_event
    lines = [
        title,
        f"ID: {record.get('id') or parcel_record_id(result.carrier_code, result.invoice)}",
        f"택배사: {result.carrier_name} ({result.carrier_code})",
        f"운송장: {result.invoice}",
        f"상태: {result.status}",
    ]
    if label:
        lines.append(f"라벨: {label}")
    if latest:
        if latest.time_text:
            lines.append(f"시간: {latest.time_text}")
        if latest.location:
            lines.append(f"위치: {latest.location}")
    if result.estimate:
        lines.append(f"예상: {result.estimate}")
    lines.append(f"배송완료: {'yes' if result.complete else 'no'}")

    if result.events:
        lines.append("\n최근 이력")
        for event in result.events[-5:]:
            parts = [part for part in [event.time_text, event.location, event.status] if part]
            lines.append("- " + " | ".join(parts))
    return trim_telegram_text("\n".join(lines))


def format_parcels(config: Config) -> str:
    parcels = load_parcels(config.parcels_path)
    if not parcels:
        return f"등록된 택배가 없습니다.\n추가: /parceladd CJ대한통운 1234567890 책"
    lines = [f"등록 택배 목록\n파일: {config.parcels_path}"]
    for parcel in parcels:
        active = "on" if parcel.get("active", True) else "off"
        done = "done" if parcel.get("complete") else "open"
        label = f" / {parcel.get('label')}" if parcel.get("label") else ""
        status = parcel.get("last_status") or parcel.get("last_error") or "not checked"
        lines.append(
            "\n"
            f"{parcel.get('id')}\n"
            f"{parcel.get('carrier_name')} {parcel.get('invoice')}{label}\n"
            f"{active}, {done}, {status}"
        )
    return trim_telegram_text("\n".join(lines))


def format_parcel_carriers(query: str | None = None) -> str:
    items = sorted(NAVER_PARCEL_CARRIERS.items(), key=lambda item: int(item[0]) if item[0].isdigit() else 999)
    if query:
        needle = normalize_carrier_token(query)
        items = [
            item for item in items if needle in normalize_carrier_token(item[0]) or needle in normalize_carrier_token(item[1])
        ]
    if not items:
        return "택배사 검색 결과가 없습니다."
    lines = ["지원 택배사 코드"]
    for code, name in items[:60]:
        lines.append(f"{code}: {name}")
    return trim_telegram_text("\n".join(lines))


def format_notification_list(config: Config, app_filter: str | None, limit: int) -> str:
    notifications = fetch_recent_notifications(config, limit=limit, app_filter=app_filter)
    title = "최근 알림 목록" if not app_filter else f"최근 알림 목록: {app_filter}"
    if not notifications:
        return f"{title}\n\n결과가 없습니다."

    app_map = load_app_map(config.app_map_path)
    lines = [title]
    for index, notification in enumerate(notifications, 1):
        lines.append("")
        lines.append(f"{index}. {notification_card_summary(config, notification, app_map)}")
    return trim_telegram_text("\n".join(lines))


def build_notification_list_response(
    config: Config,
    app_filter: str | None,
    limit: int,
) -> tuple[str, dict[str, Any] | None]:
    notifications = fetch_recent_notifications(config, limit=limit, app_filter=app_filter)
    text = format_notification_list(config, app_filter=app_filter, limit=limit)
    if not notifications:
        return text, None
    keyboard = []
    row = []
    for index, notification in enumerate(notifications, 1):
        row.append(
            {
                "text": f"{index} 자세히 보기",
                "callback_data": f"notif:{notification.rec_id}",
            }
        )
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return text, {"inline_keyboard": keyboard}


def parse_notilist_args(args: list[str]) -> tuple[str | None, int]:
    limit = 10
    app_filter = None
    if args:
        if args[-1].isdigit():
            limit = int(args[-1])
            args = args[:-1]
        if args and args[0].lower() != "all":
            app_filter = " ".join(args)
    return app_filter, max(1, min(limit, 20))


def format_app_stats(config: Config, limit: int = 30) -> str:
    stats = fetch_notification_app_stats(config, limit=limit)
    if not stats:
        return "알림 앱 목록\n\n결과가 없습니다."
    app_map = load_app_map(config.app_map_path)
    rows = []
    for item in stats:
        bundle_id = item.get("bundle_id") or "unknown app"
        rows.append(
            [
                app_display_name(config, bundle_id, app_map),
                bundle_id,
                str(item.get("count") or 0),
                notification_short_time(item.get("last_delivered_date")),
            ]
        )
    table = format_table(["이름", "번들 ID", "수", "최근"], rows, [16, 32, 5, 11])
    return trim_telegram_text(f"알림 앱 목록\n\n{table}")


def format_app_map(config: Config) -> str:
    app_map = load_app_map(config.app_map_path)
    if not app_map:
        return f"앱 매핑 테이블이 비어 있습니다.\n파일: {config.app_map_path}"
    rows = [[bundle_id, name] for bundle_id, name in sorted(app_map.items())]
    table = format_table(["번들 ID", "표시 이름"], rows, [36, 24])
    return trim_telegram_text(f"앱 매핑 테이블\n파일: {config.app_map_path}\n\n{table}")


def format_brief(config: Config) -> str:
    sections = ["아침 브리핑", format_news(config, query=None, limit=5)]
    if config.stock_watchlist:
        sections.append(format_stock_quotes(config.stock_watchlist[:5]))
    return trim_telegram_text(("\n\n" + ("=" * 24) + "\n\n").join(sections))


def handle_parcel_add_command(config: Config, state: dict[str, Any], args: list[str]) -> str:
    if len(args) < 2:
        return "사용법: /parceladd <택배사|코드> <운송장번호> [라벨]\n예: /parceladd CJ대한통운 1234567890 키보드"

    resolved = resolve_parcel_carrier(args[0])
    if not resolved:
        return "택배사를 찾지 못했습니다. /parcelcarriers 로 코드를 확인해주세요."
    carrier_code, carrier_name = resolved
    invoice = normalize_parcel_invoice(args[1])
    if not invoice:
        return "운송장번호가 비어 있습니다."

    label = " ".join(args[2:]).strip()
    record_id = parcel_record_id(carrier_code, invoice)
    parcels = load_parcels(config.parcels_path)
    record = next((item for item in parcels if item.get("id") == record_id), None)
    if record is None:
        record = {
            "id": record_id,
            "carrier_code": carrier_code,
            "carrier_name": carrier_name,
            "invoice": invoice,
            "label": label,
            "active": True,
            "created_at": iso_now(),
        }
        parcels.append(record)
    else:
        record.update(
            {
                "carrier_code": carrier_code,
                "carrier_name": carrier_name,
                "invoice": invoice,
                "label": label or record.get("label", ""),
                "active": True,
            }
        )

    try:
        result = fetch_parcel_tracking(config, state, carrier_code, invoice)
        apply_parcel_result(record, result)
        response = format_parcel_tracking(record, result, title="택배 등록 완료")
    except Exception as exc:
        record["last_checked_at"] = iso_now()
        record["last_error"] = str(exc)
        response = (
            "택배를 등록했습니다.\n"
            f"ID: {record_id}\n"
            f"택배사: {carrier_name} ({carrier_code})\n"
            f"운송장: {invoice}\n"
            f"현재 조회 실패: {exc}\n\n"
            "아직 운송장이 등록 전이면 나중에 주기 조회에서 잡힐 수 있습니다."
        )

    save_parcels(config.parcels_path, parcels)
    return response


def handle_parcel_check_command(config: Config, state: dict[str, Any], args: list[str]) -> str:
    parcels = load_parcels(config.parcels_path)
    if not parcels:
        return "등록된 택배가 없습니다. /parceladd 로 먼저 추가해주세요."

    selector = args[0] if args else "all"
    selected = select_parcel_records(parcels, selector)
    if not selected:
        return f"해당 택배를 찾지 못했습니다: {selector}"

    responses = []
    for record in selected[:10]:
        try:
            result = fetch_parcel_tracking(
                config,
                state,
                str(record.get("carrier_code", "")),
                str(record.get("invoice", "")),
            )
            changed = apply_parcel_result(record, result)
            title = "택배 즉시조회" + (" - 변경됨" if changed else "")
            responses.append(format_parcel_tracking(record, result, title=title))
        except Exception as exc:
            record["last_checked_at"] = iso_now()
            record["last_error"] = str(exc)
            responses.append(f"택배 즉시조회 실패\nID: {record.get('id')}\n오류: {exc}")

    save_parcels(config.parcels_path, parcels)
    return trim_telegram_text(("\n\n" + ("-" * 24) + "\n\n").join(responses))


def handle_parcel_remove_command(config: Config, args: list[str]) -> str:
    if not args:
        return "사용법: /parcelremove <ID|운송장번호>"
    selector = args[0]
    parcels = load_parcels(config.parcels_path)
    selected = select_parcel_records(parcels, selector)
    if not selected:
        return f"해당 택배를 찾지 못했습니다: {selector}"
    selected_ids = {str(item.get("id")) for item in selected}
    remaining = [item for item in parcels if str(item.get("id")) not in selected_ids]
    save_parcels(config.parcels_path, remaining)
    return "택배 삭제 완료\n" + "\n".join(sorted(selected_ids))


def handle_parcel_active_command(config: Config, args: list[str], active: bool) -> str:
    if not args:
        return "사용법: /parcelpause <ID|운송장번호> 또는 /parcelresume <ID|운송장번호>"
    selector = args[0]
    parcels = load_parcels(config.parcels_path)
    selected = select_parcel_records(parcels, selector)
    if not selected:
        return f"해당 택배를 찾지 못했습니다: {selector}"
    for record in selected:
        record["active"] = active
    save_parcels(config.parcels_path, parcels)
    action = "재개" if active else "일시정지"
    return f"택배 {action} 완료\n" + "\n".join(str(item.get("id")) for item in selected)


def command_help() -> str:
    return """명령어
/status
현재 상태를 보여줍니다.

/pause
전달을 일시정지합니다.

/resume
전달을 다시 시작합니다.

/mute
일정 시간 조용히 합니다. 예: /mute 30m, /mute 2h

/unmute
mute를 해제합니다.

/messages
Messages 전달을 켜거나 끕니다. 예: /messages on, /messages off

/noti
다른 앱 알림 전달을 켜거나 끕니다. 예: /noti on, /noti off

/parcelon
택배 주기 조회를 켭니다.

/parceloff
택배 주기 조회를 끕니다.

/mode
Messages 본문 모드를 바꿉니다. 예: /mode full, /mode redacted, /mode sender_only

/notimode
알림 본문 모드를 바꿉니다. 예: /notimode full, /notimode redacted, /notimode app_only

/deny
앱 알림을 제외합니다. 예: /deny com.kakao.kakaotalkmac

/undeny
앱 알림 제외를 해제합니다. 예: /undeny com.kakao.kakaotalkmac

/denylist
제외 앱 목록을 보여줍니다.

/notilist
최근 알림 카드와 자세히 보기 버튼을 보여줍니다. 예: /notilist, /notilist all 20, /notilist KakaoTalk 10

/apps
알림 앱과 번들 ID 표를 보여줍니다. 예: /apps, /apps 50

/map
번들 ID 표시 이름 매핑을 관리합니다. 예: /map, /map path, /map set com.kakao.kakaotalkmac KakaoTalk

/unmap
번들 ID 표시 이름 매핑을 제거합니다. 예: /unmap com.kakao.kakaotalkmac

/news
주요 뉴스 또는 검색 뉴스를 보여줍니다. 예: /news, /news AI, /news 반도체 5

/stock
주식/지수를 조회합니다. 예: /stock AAPL, /stock AAPL NVDA 005930.KS

/brief
주요 뉴스와 관심 종목을 함께 보여줍니다.

/parceladd
택배를 등록하고 1시간마다 변경 여부를 확인합니다. 예: /parceladd CJ대한통운 1234567890 키보드

/parcels
등록된 택배 목록을 보여줍니다.

/parcelcheck
택배를 즉시 조회합니다. 예: /parcelcheck, /parcelcheck 04:1234567890

/parcelremove
등록된 택배를 삭제합니다. 예: /parcelremove 04:1234567890

/parcelpause
특정 택배 주기 조회를 멈춥니다. 예: /parcelpause 04:1234567890

/parcelresume
멈춘 택배 주기 조회를 다시 켭니다. 예: /parcelresume 04:1234567890

/parcelcarriers
네이버 택배사 코드를 보여줍니다. 예: /parcelcarriers, /parcelcarriers cj

/test
봇 명령 루프가 살아 있는지 확인합니다.

/help
도움말을 보여줍니다."""


def handle_command(config: Config, state: dict[str, Any], text: str) -> str:
    parts = text.strip().split()
    command = parts[0].split("@", 1)[0].lower()
    args = parts[1:]

    if command in {"/help", "/start"}:
        return command_help()

    if command == "/status":
        active = apply_runtime_state(config, state)
        mute_until = parse_iso_datetime(state.get("mute_until"))
        paused = bool(state.get("paused"))
        suppressed = forwarding_suppressed(state)
        return (
            "상태\n"
            f"Messages: {'on' if active.watch_messages else 'off'}\n"
            f"Notifications: {'on' if active.watch_notifications else 'off'}\n"
            f"Parcels: {'on' if active.watch_parcels else 'off'}\n"
            f"Parcel poll seconds: {int(active.parcel_poll_interval_seconds)}\n"
            f"Paused: {'yes' if paused else 'no'}\n"
            f"Muted until: {format_local_datetime(mute_until)}\n"
            f"Suppressed now: {'yes' if suppressed else 'no'}\n"
            f"Message mode: {active.message_text_mode}\n"
            f"Notification mode: {active.notification_text_mode}\n"
            f"Messages last ROWID: {state.get('messages_last_rowid', 'n/a')}\n"
            f"Notifications last rec_id: {state.get('notifications_last_rec_id', 'n/a')}"
        )

    if command == "/pause":
        state["paused"] = True
        return "전달을 일시정지했습니다. /resume 으로 다시 켤 수 있습니다."

    if command == "/resume":
        state["paused"] = False
        state.pop("mute_until", None)
        return "전달을 재개했습니다."

    if command == "/mute":
        duration = parse_duration_seconds(args[0]) if args else parse_duration_seconds("30m")
        if duration is None:
            return "사용법: /mute 30m 또는 /mute 2h"
        until = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=duration)
        state["mute_until"] = until.isoformat()
        return f"{format_local_datetime(until)}까지 전달을 조용히 합니다."

    if command == "/unmute":
        state.pop("mute_until", None)
        return "mute를 해제했습니다."

    if command in {"/messages", "/noti"}:
        if not args or args[0].lower() not in {"on", "off"}:
            return f"사용법: {command} on 또는 {command} off"
        enabled = args[0].lower() == "on"
        if command == "/messages":
            state["runtime_watch_messages"] = enabled
            return f"Messages 전달: {'on' if enabled else 'off'}"
        state["runtime_watch_notifications"] = enabled
        return f"다른 앱 알림 전달: {'on' if enabled else 'off'}"

    if command in {"/parcelon", "/parceloff"}:
        enabled = command == "/parcelon"
        state["runtime_watch_parcels"] = enabled
        return f"택배 주기 조회: {'on' if enabled else 'off'}"

    if command == "/mode":
        if not args or args[0].lower() not in {"full", "redacted", "sender_only"}:
            return "사용법: /mode full|redacted|sender_only"
        state["runtime_message_text_mode"] = args[0].lower()
        return f"메시지 모드: {args[0].lower()}"

    if command == "/notimode":
        if not args or args[0].lower() not in {"full", "redacted", "app_only"}:
            return "사용법: /notimode full|redacted|app_only"
        state["runtime_notification_text_mode"] = args[0].lower()
        return f"알림 모드: {args[0].lower()}"

    if command in {"/deny", "/undeny"}:
        if not args:
            return f"사용법: {command} com.example.App"
        add = command == "/deny"
        result = update_csv_env_value(config.config_path, "NOTIFICATION_APP_DENYLIST", args[0], add=add)
        return f"NOTIFICATION_APP_DENYLIST={result or '(empty)'}"

    if command == "/denylist":
        values = load_env_file(config.config_path).get("NOTIFICATION_APP_DENYLIST", "")
        return "제외 앱 목록\n" + (values or "(empty)")

    if command == "/notilist":
        app_filter, limit = parse_notilist_args(args)
        return format_notification_list(config, app_filter=app_filter, limit=limit)

    if command == "/apps":
        limit = int(args[0]) if args and args[0].isdigit() else 30
        return format_app_stats(config, limit=limit)

    if command == "/map":
        if not args:
            return format_app_map(config)
        action = args[0].lower()
        if action == "path":
            return f"앱 매핑 파일\n{config.app_map_path}"
        if action == "set":
            if len(args) < 3:
                return "사용법: /map set <bundle_id> <표시 이름>"
            bundle_id = args[1]
            name = " ".join(args[2:]).strip()
            app_map = load_app_map(config.app_map_path)
            app_map[bundle_id] = name
            save_app_map(config.app_map_path, app_map)
            return f"매핑 추가/수정: {bundle_id} -> {name}"
        if action in {"unset", "delete", "del"}:
            if len(args) < 2:
                return "사용법: /map unset <bundle_id>"
            bundle_id = args[1]
            app_map = load_app_map(config.app_map_path)
            removed = app_map.pop(bundle_id, None)
            save_app_map(config.app_map_path, app_map)
            return f"매핑 제거: {bundle_id}" if removed else f"매핑이 없습니다: {bundle_id}"
        return "사용법: /map, /map path, /map set <bundle_id> <표시 이름>, /map unset <bundle_id>"

    if command == "/unmap":
        if not args:
            return "사용법: /unmap <bundle_id>"
        app_map = load_app_map(config.app_map_path)
        removed = app_map.pop(args[0], None)
        save_app_map(config.app_map_path, app_map)
        return f"매핑 제거: {args[0]}" if removed else f"매핑이 없습니다: {args[0]}"

    if command == "/news":
        limit = 5
        query_parts = args
        if args and args[-1].isdigit():
            limit = int(args[-1])
            query_parts = args[:-1]
        query = " ".join(query_parts).strip() or None
        return format_news(config, query=query, limit=limit)

    if command == "/stock":
        return format_stock_quotes(args)

    if command == "/brief":
        return format_brief(config)

    if command == "/parceladd":
        return handle_parcel_add_command(config, state, args)

    if command == "/parcels":
        return format_parcels(config)

    if command == "/parcelcheck":
        return handle_parcel_check_command(config, state, args)

    if command == "/parcelremove":
        return handle_parcel_remove_command(config, args)

    if command == "/parcelpause":
        return handle_parcel_active_command(config, args, active=False)

    if command == "/parcelresume":
        return handle_parcel_active_command(config, args, active=True)

    if command == "/parcelcarriers":
        return format_parcel_carriers(" ".join(args).strip() or None)

    if command == "/test":
        return f"{APP_NAME} is alive on {socket.gethostname()}."

    return "알 수 없는 명령입니다. /help 를 보내보세요."


def process_telegram_commands(config: Config, state: dict[str, Any]) -> None:
    if not config.bot_commands_enabled:
        return
    updates = telegram_request(
        config,
        "getUpdates",
        {
            "offset": int(state.get("telegram_last_update_id", 0)) + 1,
            "limit": 25,
            "timeout": 0,
            "allowed_updates": ["message", "callback_query"],
        },
    )
    changed = False
    for update in updates:
        update_id = int(update.get("update_id", 0))
        state["telegram_last_update_id"] = max(int(state.get("telegram_last_update_id", 0)), update_id)
        changed = True
        callback_query = update.get("callback_query")
        if isinstance(callback_query, dict):
            handle_callback_query(config, callback_query)
            continue

        message = update.get("message")
        if not isinstance(message, dict):
            continue
        chat = message.get("chat")
        text = message.get("text")
        if not isinstance(chat, dict) or not isinstance(text, str) or not text.startswith("/"):
            continue
        chat_id = chat.get("id")
        if not is_authorized_chat(config, chat_id):
            logging.warning("Ignoring command from unauthorized chat_id=%s", chat_id)
            continue
        try:
            command = text.strip().split()[0].split("@", 1)[0].lower()
            if command == "/notilist":
                app_filter, limit = parse_notilist_args(text.strip().split()[1:])
                response, reply_markup = build_notification_list_response(config, app_filter, limit)
                send_telegram_to_chat(config, chat_id, response, reply_markup=reply_markup)
            else:
                response = handle_command(config, state, text)
                send_telegram_to_chat(config, chat_id, response)
        except Exception as exc:
            logging.exception("Command failed")
            send_telegram_to_chat(config, chat_id, f"명령 처리 실패: {exc}")
        changed = True
    if changed:
        save_state(config.state_path, state)


def handle_callback_query(config: Config, callback_query: dict[str, Any]) -> None:
    callback_id = str(callback_query.get("id", ""))
    data = str(callback_query.get("data", ""))
    message = callback_query.get("message")
    chat = message.get("chat") if isinstance(message, dict) else None
    chat_id = chat.get("id") if isinstance(chat, dict) else None

    if not callback_id:
        return
    if not is_authorized_chat(config, chat_id):
        answer_callback_query(config, callback_id, "권한이 없습니다.")
        logging.warning("Ignoring callback from unauthorized chat_id=%s", chat_id)
        return
    if not data.startswith("notif:"):
        answer_callback_query(config, callback_id)
        return
    try:
        rec_id = int(data.split(":", 1)[1])
    except ValueError:
        answer_callback_query(config, callback_id, "잘못된 알림 ID입니다.")
        return
    notification = fetch_notification_by_rec_id(config, rec_id)
    if not notification:
        answer_callback_query(config, callback_id, "알림을 찾을 수 없습니다.")
        return
    answer_callback_query(config, callback_id, "상세 내용을 보냅니다.")
    send_telegram_to_chat(config, chat_id, notification_detail_text(config, notification))


def initialize_command_state(config: Config, state: dict[str, Any]) -> None:
    if not config.bot_commands_enabled or "telegram_last_update_id" in state:
        return
    try:
        updates = telegram_request(config, "getUpdates", {"limit": 100, "timeout": 0})
    except Exception:
        logging.exception("Could not initialize Telegram command offset")
        return
    max_update_id = max((int(update.get("update_id", 0)) for update in updates), default=0)
    state["telegram_last_update_id"] = max_update_id
    save_state(config.state_path, state)


def mark_sources_seen(config: Config, state: dict[str, Any]) -> None:
    if config.watch_messages:
        state["messages_last_rowid"] = get_max_rowid(config)
    if config.watch_notifications:
        state["notifications_last_rec_id"] = get_max_notification_rec_id(config)
    save_state(config.state_path, state)


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


def parcel_is_due(config: Config, parcel: dict[str, Any], force: bool = False) -> bool:
    if force:
        return True
    if not parcel.get("active", True):
        return False
    if parcel.get("complete"):
        return False
    last_checked = parse_iso_datetime(parcel.get("last_checked_at"))
    if not last_checked:
        return True
    return (dt.datetime.now(dt.timezone.utc) - last_checked).total_seconds() >= config.parcel_poll_interval_seconds


def check_due_parcels(
    config: Config,
    state: dict[str, Any],
    dry_run: bool,
    notify: bool,
    force: bool = False,
) -> int:
    if not config.watch_parcels:
        return 0

    parcels = load_parcels(config.parcels_path)
    if not parcels:
        return 0

    checked = 0
    changed_count = 0
    for record in parcels:
        if not parcel_is_due(config, record, force=force):
            continue
        checked += 1
        try:
            result = fetch_parcel_tracking(
                config,
                state,
                str(record.get("carrier_code", "")),
                str(record.get("invoice", "")),
            )
            changed = apply_parcel_result(record, result)
            if changed:
                changed_count += 1
                message = format_parcel_tracking(record, result, title="택배 업데이트")
                if dry_run:
                    print(f"\n--- PARCEL {record.get('id')} ---\n{message}")
                elif notify:
                    send_telegram_message(config, message)
                    record["last_notified_at"] = iso_now()
        except Exception as exc:
            record["last_checked_at"] = iso_now()
            record["last_error"] = str(exc)
            logging.warning("Parcel check failed id=%s error=%s", record.get("id"), exc)

    if checked:
        save_parcels(config.parcels_path, parcels)
        save_state(config.state_path, state)
        logging.info("Checked %s parcel(s), %s changed", checked, changed_count)
    return changed_count


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
    initialize_command_state(config, state)
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
    if config.watch_parcels:
        logging.info("Watching parcels file: %s", config.parcels_path)

    while True:
        try:
            config = load_config(config.config_path)
            state = load_state(config.state_path) or state
            process_telegram_commands(config, state)
            state = load_state(config.state_path) or state
            active_config = apply_runtime_state(config, state)

            if forwarding_suppressed(state):
                mark_sources_seen(active_config, state)
                if active_config.watch_parcels:
                    check_due_parcels(active_config, state, dry_run=dry_run, notify=False)
                time.sleep(active_config.poll_interval_seconds)
                continue

            if active_config.watch_messages:
                rows = fetch_messages_after(active_config, int(state.get("messages_last_rowid", 0)))
                if rows:
                    forward_rows(active_config, rows, state, dry_run=dry_run)
            if active_config.watch_notifications:
                notifications = fetch_notifications_after(
                    active_config,
                    int(state.get("notifications_last_rec_id", 0)),
                )
                if notifications:
                    forward_notifications(active_config, notifications, state, dry_run=dry_run)
            if active_config.watch_parcels:
                check_due_parcels(active_config, state, dry_run=dry_run, notify=True)
            if (
                not active_config.watch_messages
                and not active_config.watch_notifications
                and not active_config.watch_parcels
            ):
                logging.warning("WATCH_MESSAGES, WATCH_NOTIFICATIONS, and WATCH_PARCELS are disabled")
            else:
                state = load_state(active_config.state_path) or state
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
    parcel_count = 0
    if config.watch_messages:
        rows = fetch_messages_after(config, int(state.get("messages_last_rowid", 0)))
        message_count = forward_rows(config, rows, state, dry_run=dry_run)
    if config.watch_notifications:
        notifications = fetch_notifications_after(config, int(state.get("notifications_last_rec_id", 0)))
        notification_count = forward_notifications(config, notifications, state, dry_run=dry_run)
    if config.watch_parcels:
        parcel_count = check_due_parcels(config, state, dry_run=dry_run, notify=True, force=True)
    logging.info(
        "Forwarded %s message(s), %s notification(s), %s parcel update(s)",
        message_count,
        notification_count,
        parcel_count,
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
