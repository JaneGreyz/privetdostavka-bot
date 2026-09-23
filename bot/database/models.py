from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

OrderStatus = str

STATUS_NEW = "new"
STATUS_ACCEPTED = "accepted"
STATUS_AWAITING_PAYMENT = "awaiting_payment"
STATUS_IN_DELIVERY = "in_delivery"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"

ACTIVE_STATUSES = (
    STATUS_NEW,
    STATUS_ACCEPTED,
    STATUS_AWAITING_PAYMENT,
    STATUS_IN_DELIVERY,
)

DEFAULT_ADDRESSES: list[tuple[str, str]] = [
    ("Ленинградский проспект, 36с11", "СОК"),
    ("Дмитровский проезд, 1", "Д1"),
    ("Пятницкая улица, 71/5с2", "ПТ"),
]


@dataclass
class Address:
    id: int
    full_name: str
    short_name: str
    is_active: bool
    sort_order: int


@dataclass
class GuestProfile:
    guest_id: int
    address_id: int
    address: str
    address_short: str
    address_clarification: str
    phone: str

    @classmethod
    def from_row(cls, row: Any) -> "GuestProfile":
        return cls(
            guest_id=row["guest_id"],
            address_id=row["address_id"],
            address=row["address"],
            address_short=row["address_short"],
            address_clarification=row["address_clarification"],
            phone=row["phone"],
        )


@dataclass
class MenuImage:
    id: int
    address_id: int | None
    file_id: str
    file_unique_id: str | None
    sort_order: int


@dataclass
class Order:
    id: int
    guest_id: int
    guest_username: str | None
    guest_name: str
    address: str
    address_short: str
    address_clarification: str
    phone: str
    order_text: str
    status: OrderStatus
    topic_id: int | None
    staff_message_id: int | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: Any) -> "Order":
        return cls(
            id=row["id"],
            guest_id=row["guest_id"],
            guest_username=row["guest_username"],
            guest_name=row["guest_name"],
            address=row["address"],
            address_short=row["address_short"],
            address_clarification=row["address_clarification"],
            phone=row["phone"],
            order_text=row["order_text"],
            status=row["status"],
            topic_id=row["topic_id"],
            staff_message_id=row["staff_message_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )


@dataclass
class SupportChat:
    id: int
    user_id: int
    user_name: str
    user_username: str | None
    topic_id: int
    is_open: bool

    @classmethod
    def from_row(cls, row: Any) -> "SupportChat":
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            user_name=row["user_name"],
            user_username=row["user_username"],
            topic_id=row["topic_id"],
            is_open=bool(row["is_open"]),
        )
