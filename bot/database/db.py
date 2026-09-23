from __future__ import annotations

import aiosqlite
from pathlib import Path

from bot.database.models import (
    ACTIVE_STATUSES,
    DEFAULT_ADDRESSES,
    Address,
    GuestProfile,
    MenuImage,
    Order,
    SupportChat,
)


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._connection: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self.path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA foreign_keys = ON")
        await self._create_tables()
        await self._seed_addresses()

    async def close(self) -> None:
        if self._connection:
            await self._connection.close()

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("Database is not connected")
        return self._connection

    async def _create_tables(self) -> None:
        await self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS addresses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL UNIQUE,
                short_name TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                sort_order INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guest_id INTEGER NOT NULL,
                guest_username TEXT,
                guest_name TEXT NOT NULL,
                address TEXT NOT NULL,
                address_short TEXT NOT NULL,
                address_clarification TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL,
                order_text TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'new',
                topic_id INTEGER,
                staff_message_id INTEGER,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );

            CREATE INDEX IF NOT EXISTS idx_orders_guest_id ON orders(guest_id);
            CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
            CREATE INDEX IF NOT EXISTS idx_orders_topic_id ON orders(topic_id);

            CREATE TABLE IF NOT EXISTS guest_profiles (
                guest_id INTEGER PRIMARY KEY,
                address_id INTEGER NOT NULL,
                address TEXT NOT NULL,
                address_short TEXT NOT NULL,
                address_clarification TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );

            CREATE TABLE IF NOT EXISTS menu_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address_id INTEGER,
                file_id TEXT NOT NULL,
                file_unique_id TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                FOREIGN KEY (address_id) REFERENCES addresses(id)
            );

            CREATE INDEX IF NOT EXISTS idx_menu_address ON menu_images(address_id, sort_order);

            CREATE TABLE IF NOT EXISTS support_chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                user_name TEXT NOT NULL,
                user_username TEXT,
                topic_id INTEGER NOT NULL UNIQUE,
                is_open INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );

            CREATE INDEX IF NOT EXISTS idx_support_user ON support_chats(user_id, is_open);

            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        await self.conn.commit()

    async def _seed_addresses(self) -> None:
        for index, (full_name, short_name) in enumerate(DEFAULT_ADDRESSES):
            await self.conn.execute(
                """
                INSERT INTO addresses (full_name, short_name, is_active, sort_order)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(full_name) DO UPDATE SET
                    short_name = excluded.short_name,
                    sort_order = excluded.sort_order
                """,
                (full_name, short_name, index),
            )
        await self.conn.commit()

    # --- Settings ---

    async def get_setting(self, key: str) -> str | None:
        cursor = await self.conn.execute(
            "SELECT value FROM bot_settings WHERE key = ?",
            (key,),
        )
        row = await cursor.fetchone()
        return row["value"] if row else None

    async def set_setting(self, key: str, value: str) -> None:
        await self.conn.execute(
            """
            INSERT INTO bot_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        await self.conn.commit()

    # --- Addresses ---

    async def get_active_addresses(self) -> list[Address]:
        return await self._fetch_addresses(active_only=True)

    async def get_all_addresses(self) -> list[Address]:
        return await self._fetch_addresses(active_only=False)

    async def _fetch_addresses(self, *, active_only: bool) -> list[Address]:
        sql = """
            SELECT id, full_name, short_name, is_active, sort_order
            FROM addresses
        """
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY sort_order, id"
        cursor = await self.conn.execute(sql)
        rows = await cursor.fetchall()
        return [
            Address(
                id=row["id"],
                full_name=row["full_name"],
                short_name=row["short_name"],
                is_active=bool(row["is_active"]),
                sort_order=row["sort_order"],
            )
            for row in rows
        ]

    async def get_address_by_id(self, address_id: int) -> Address | None:
        cursor = await self.conn.execute(
            """
            SELECT id, full_name, short_name, is_active, sort_order
            FROM addresses WHERE id = ?
            """,
            (address_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return Address(
            id=row["id"],
            full_name=row["full_name"],
            short_name=row["short_name"],
            is_active=bool(row["is_active"]),
            sort_order=row["sort_order"],
        )

    # --- Guest profiles ---

    async def get_guest_profile(self, guest_id: int) -> GuestProfile | None:
        cursor = await self.conn.execute(
            """
            SELECT guest_id, address_id, address, address_short,
                   address_clarification, phone
            FROM guest_profiles
            WHERE guest_id = ?
            """,
            (guest_id,),
        )
        row = await cursor.fetchone()
        return GuestProfile.from_row(row) if row else None

    async def save_guest_profile(
        self,
        guest_id: int,
        address_id: int,
        address: str,
        address_short: str,
        address_clarification: str,
        phone: str,
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO guest_profiles (
                guest_id, address_id, address, address_short,
                address_clarification, phone, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(guest_id) DO UPDATE SET
                address_id = excluded.address_id,
                address = excluded.address,
                address_short = excluded.address_short,
                address_clarification = excluded.address_clarification,
                phone = excluded.phone,
                updated_at = datetime('now', 'localtime')
            """,
            (
                guest_id,
                address_id,
                address,
                address_short,
                address_clarification,
                phone,
            ),
        )
        await self.conn.commit()

    # --- Orders ---

    async def create_order(
        self,
        guest_id: int,
        guest_username: str | None,
        guest_name: str,
        address: str,
        address_short: str,
        address_clarification: str,
        phone: str,
    ) -> Order:
        cursor = await self.conn.execute(
            """
            INSERT INTO orders (
                guest_id, guest_username, guest_name,
                address, address_short, address_clarification, phone
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guest_id,
                guest_username,
                guest_name,
                address,
                address_short,
                address_clarification,
                phone,
            ),
        )
        await self.conn.commit()
        order = await self.get_order(cursor.lastrowid)
        if order is None:
            raise RuntimeError("Failed to create order")
        return order

    async def get_order(self, order_id: int) -> Order | None:
        cursor = await self.conn.execute(
            "SELECT * FROM orders WHERE id = ?",
            (order_id,),
        )
        row = await cursor.fetchone()
        return Order.from_row(row) if row else None

    async def get_order_by_topic(self, topic_id: int) -> Order | None:
        cursor = await self.conn.execute(
            "SELECT * FROM orders WHERE topic_id = ?",
            (topic_id,),
        )
        row = await cursor.fetchone()
        return Order.from_row(row) if row else None

    async def get_active_order_for_guest(self, guest_id: int) -> Order | None:
        placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
        cursor = await self.conn.execute(
            f"""
            SELECT * FROM orders
            WHERE guest_id = ? AND status IN ({placeholders})
            ORDER BY id DESC LIMIT 1
            """,
            (guest_id, *ACTIVE_STATUSES),
        )
        row = await cursor.fetchone()
        return Order.from_row(row) if row else None

    async def get_pending_order_for_guest(self, guest_id: int) -> Order | None:
        placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
        cursor = await self.conn.execute(
            f"""
            SELECT * FROM orders
            WHERE guest_id = ? AND status IN ({placeholders}) AND topic_id IS NULL
            ORDER BY id DESC LIMIT 1
            """,
            (guest_id, *ACTIVE_STATUSES),
        )
        row = await cursor.fetchone()
        return Order.from_row(row) if row else None

    async def update_order_text(self, order_id: int, order_text: str) -> None:
        await self.conn.execute(
            """
            UPDATE orders
            SET order_text = ?, updated_at = datetime('now', 'localtime')
            WHERE id = ?
            """,
            (order_text, order_id),
        )
        await self.conn.commit()

    async def update_order_status(self, order_id: int, status: str) -> None:
        await self.conn.execute(
            """
            UPDATE orders
            SET status = ?, updated_at = datetime('now', 'localtime')
            WHERE id = ?
            """,
            (status, order_id),
        )
        await self.conn.commit()

    async def update_order_topic(
        self,
        order_id: int,
        topic_id: int,
        staff_message_id: int | None = None,
    ) -> None:
        if staff_message_id is None:
            await self.conn.execute(
                """
                UPDATE orders
                SET topic_id = ?, updated_at = datetime('now', 'localtime')
                WHERE id = ?
                """,
                (topic_id, order_id),
            )
        else:
            await self.conn.execute(
                """
                UPDATE orders
                SET topic_id = ?, staff_message_id = ?,
                    updated_at = datetime('now', 'localtime')
                WHERE id = ?
                """,
                (topic_id, order_id, staff_message_id),
            )
        await self.conn.commit()

    async def set_order_staff_message_id(
        self, order_id: int, staff_message_id: int
    ) -> None:
        await self.conn.execute(
            """
            UPDATE orders
            SET staff_message_id = ?, updated_at = datetime('now', 'localtime')
            WHERE id = ?
            """,
            (staff_message_id, order_id),
        )
        await self.conn.commit()

    # --- Menu ---

    async def get_menu_images(self, address_id: int) -> list[MenuImage]:
        cursor = await self.conn.execute(
            """
            SELECT id, address_id, file_id, file_unique_id, sort_order
            FROM menu_images
            WHERE address_id = ?
            ORDER BY sort_order, id
            """,
            (address_id,),
        )
        rows = await cursor.fetchall()
        if not rows:
            cursor = await self.conn.execute(
                """
                SELECT id, address_id, file_id, file_unique_id, sort_order
                FROM menu_images
                WHERE address_id IS NULL
                ORDER BY sort_order, id
                """
            )
            rows = await cursor.fetchall()
        return [_menu_from_row(row) for row in rows]

    async def add_menu_image(
        self,
        address_id: int | None,
        file_id: str,
        file_unique_id: str | None,
        sort_order: int,
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO menu_images (address_id, file_id, file_unique_id, sort_order)
            VALUES (?, ?, ?, ?)
            """,
            (address_id, file_id, file_unique_id, sort_order),
        )
        await self.conn.commit()

    async def clear_menu_images(self, address_id: int) -> int:
        cursor = await self.conn.execute(
            "DELETE FROM menu_images WHERE address_id = ?",
            (address_id,),
        )
        await self.conn.commit()
        return cursor.rowcount or 0

    async def count_menu_images(self, address_id: int) -> int:
        cursor = await self.conn.execute(
            "SELECT COUNT(*) FROM menu_images WHERE address_id = ?",
            (address_id,),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    # --- Support chats ---

    async def get_open_support_chat(self, user_id: int) -> SupportChat | None:
        cursor = await self.conn.execute(
            """
            SELECT * FROM support_chats
            WHERE user_id = ? AND is_open = 1
            ORDER BY id DESC LIMIT 1
            """,
            (user_id,),
        )
        row = await cursor.fetchone()
        return SupportChat.from_row(row) if row else None

    async def get_support_chat_by_topic(self, topic_id: int) -> SupportChat | None:
        cursor = await self.conn.execute(
            "SELECT * FROM support_chats WHERE topic_id = ?",
            (topic_id,),
        )
        row = await cursor.fetchone()
        return SupportChat.from_row(row) if row else None

    async def create_support_chat(
        self,
        user_id: int,
        user_name: str,
        user_username: str | None,
        topic_id: int,
    ) -> SupportChat:
        cursor = await self.conn.execute(
            """
            INSERT INTO support_chats (user_id, user_name, user_username, topic_id)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, user_name, user_username, topic_id),
        )
        await self.conn.commit()
        chat = await self.get_support_chat_by_topic(topic_id)
        if chat is None:
            raise RuntimeError("Failed to create support chat")
        _ = cursor.lastrowid
        return chat

    # --- Stats ---

    async def get_today_stats(self) -> dict:
        cursor = await self.conn.execute(
            """
            SELECT COUNT(*) as total FROM orders
            WHERE date(created_at) = date('now', 'localtime')
            """
        )
        total = (await cursor.fetchone())["total"]

        cursor = await self.conn.execute(
            """
            SELECT status, COUNT(*) as count FROM orders
            WHERE date(created_at) = date('now', 'localtime')
            GROUP BY status
            """
        )
        by_status = {row["status"]: row["count"] for row in await cursor.fetchall()}

        cursor = await self.conn.execute(
            """
            SELECT address_short, COUNT(*) as count FROM orders
            WHERE date(created_at) = date('now', 'localtime')
            GROUP BY address_short
            ORDER BY count DESC
            """
        )
        by_address = {
            row["address_short"]: row["count"] for row in await cursor.fetchall()
        }
        return {"total": total, "by_status": by_status, "by_address": by_address}


def _menu_from_row(row: aiosqlite.Row) -> MenuImage:
    return MenuImage(
        id=row["id"],
        address_id=row["address_id"],
        file_id=row["file_id"],
        file_unique_id=row["file_unique_id"],
        sort_order=row["sort_order"],
    )
