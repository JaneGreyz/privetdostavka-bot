from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


@dataclass
class Settings:
    bot_token: str
    staff_chat_id: int
    admin_ids: frozenset[int]
    database_path: Path
    timezone: str
    delivery_start_hour: int = 10
    delivery_end_hour: int = 17

    def is_admin(self, user_id: int | None) -> bool:
        if user_id is None:
            return False
        if not self.admin_ids:
            return False
        return user_id in self.admin_ids

    def has_staff_chat(self) -> bool:
        return bool(self.staff_chat_id)


def _parse_int_list(raw: str) -> frozenset[int]:
    values: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part:
            values.add(int(part))
    return frozenset(values)


def load_settings() -> Settings:
    database_path = Path(os.getenv("DATABASE_PATH", "data/bot.db"))
    if not database_path.is_absolute():
        database_path = BASE_DIR / database_path

    staff_raw = os.getenv("STAFF_CHAT_ID", "").strip()
    staff_chat_id = int(staff_raw) if staff_raw else 0

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise KeyError("BOT_TOKEN")

    return Settings(
        bot_token=bot_token,
        staff_chat_id=staff_chat_id,
        admin_ids=_parse_int_list(os.getenv("ADMIN_IDS", "")),
        database_path=database_path,
        timezone=os.getenv("TIMEZONE", "Europe/Moscow"),
        delivery_start_hour=int(os.getenv("DELIVERY_START_HOUR", "10")),
        delivery_end_hour=int(os.getenv("DELIVERY_END_HOUR", "17")),
    )
