from __future__ import annotations

import re
from datetime import datetime

PHONE_DIGITS = re.compile(r"\D")


def normalize_phone(phone: str) -> str:
    digits = PHONE_DIGITS.sub("", phone)
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    if digits.startswith("7") and len(digits) == 11:
        return (
            f"+{digits[0]} ({digits[1:4]}) {digits[4:7]}-"
            f"{digits[7:9]}-{digits[9:11]}"
        )
    return phone.strip()


def is_valid_phone(phone: str) -> bool:
    digits = PHONE_DIGITS.sub("", phone)
    return len(digits) >= 10


def guest_display_name(user) -> str:
    if user is None:
        return "Гость"
    parts = [user.first_name or "", user.last_name or ""]
    name = " ".join(part for part in parts if part).strip()
    return name or (user.username or "Гость")


def is_working_hours(moment: datetime, start_hour: int, end_hour: int) -> bool:
    return start_hour <= moment.hour < end_hour
