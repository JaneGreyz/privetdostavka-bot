from __future__ import annotations

import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ChatMemberUpdated, Message

from bot.config import Settings
from bot.database.db import Database
from bot.keyboards import (
    admin_addresses_keyboard,
    admin_back_keyboard,
    admin_menu_collect_keyboard,
    admin_panel_keyboard,
    guest_main_keyboard,
)
from bot.services.menu import save_photo_file_id
from bot.states.order import AdminStates
from bot.texts import (
    ADMIN_BIND_HINT,
    ADMIN_CHOOSE_CLEAR_ADDRESS,
    ADMIN_CHOOSE_MENU_ADDRESS,
    ADMIN_MENU_CLEARED,
    ADMIN_MENU_EMPTY,
    ADMIN_MENU_PHOTO_SAVED,
    ADMIN_MENU_SAVED,
    ADMIN_NEED_FORUM,
    ADMIN_NO_ACCESS,
    ADMIN_NO_ORDERS,
    ADMIN_PANEL,
    ADMIN_SEND_MENU_PHOTOS,
    ADMIN_STAFF_BOUND,
    ADMIN_STATS_BY_ADDRESS,
    ADMIN_STATS_BY_STATUS,
    ADMIN_STATS_HEADER,
    ADMIN_STATS_TOTAL,
    ADMIN_YOUR_ID,
    BUTTON_ADMIN,
    BUTTON_CANCEL,
    BUTTON_MENU_DONE,
    STATUS_LABELS,
)

logger = logging.getLogger(__name__)


def create_admin_router(settings: Settings) -> Router:
    router = Router(name="admin")

    def can_admin(user_id: int | None) -> bool:
        if user_id is None:
            return False
        if not settings.admin_ids:
            return True
        return settings.is_admin(user_id)

    async def deny(message: Message) -> bool:
        if message.from_user and can_admin(message.from_user.id):
            return False
        if message.chat.type == ChatType.PRIVATE:
            await message.answer(ADMIN_NO_ACCESS)
        return True

    def _panel_text() -> str:
        staff = settings.staff_chat_id or "не задан"
        return ADMIN_PANEL.format(staff_chat_id=staff)

    def _stats_text(stats: dict) -> str:
        today = datetime.now().strftime("%d.%m.%Y")
        if not stats["total"]:
            return ADMIN_NO_ORDERS
        lines = [
            ADMIN_STATS_HEADER.format(date=today),
            ADMIN_STATS_TOTAL.format(total=stats["total"]),
            ADMIN_STATS_BY_STATUS,
        ]
        for status, count in stats["by_status"].items():
            label = STATUS_LABELS.get(status, status)
            lines.append(f"  • {label}: {count}")
        if stats["by_address"]:
            lines.append(ADMIN_STATS_BY_ADDRESS)
            for address, count in stats["by_address"].items():
                lines.append(f"  • {address}: {count}")
        return "\n".join(lines)

    async def _edit_or_send(
        callback: CallbackQuery,
        text: str,
        reply_markup,
    ) -> None:
        if not isinstance(callback.message, Message):
            return
        try:
            await callback.message.edit_text(text, reply_markup=reply_markup)
        except TelegramBadRequest:
            await callback.message.answer(text, reply_markup=reply_markup)

    @router.message(F.chat.type == "private", F.text == BUTTON_ADMIN)
    async def open_admin_panel(message: Message) -> None:
        if await deny(message):
            return
        await message.answer(
            _panel_text(),
            parse_mode="HTML",
            reply_markup=admin_panel_keyboard(),
        )

    @router.callback_query(F.data == "admin:back")
    async def admin_back(callback: CallbackQuery) -> None:
        if not callback.from_user or not can_admin(callback.from_user.id):
            await callback.answer(ADMIN_NO_ACCESS, show_alert=True)
            return
        await _edit_or_send(
            callback, _panel_text(), admin_panel_keyboard()
        )
        await callback.answer()

    @router.callback_query(F.data == "admin:stats")
    async def admin_stats(callback: CallbackQuery, db: Database) -> None:
        if not callback.from_user or not can_admin(callback.from_user.id):
            await callback.answer(ADMIN_NO_ACCESS, show_alert=True)
            return
        stats = await db.get_today_stats()
        await _edit_or_send(callback, _stats_text(stats), admin_back_keyboard())
        await callback.answer()

    @router.callback_query(F.data == "admin:id")
    async def admin_show_id(callback: CallbackQuery) -> None:
        if not callback.from_user:
            return
        if not can_admin(callback.from_user.id):
            await callback.answer(ADMIN_NO_ACCESS, show_alert=True)
            return
        chat_id = callback.message.chat.id if isinstance(callback.message, Message) else 0
        await _edit_or_send(
            callback,
            ADMIN_YOUR_ID.format(
                user_id=callback.from_user.id, chat_id=chat_id
            ),
            admin_back_keyboard(),
        )
        await callback.answer()

    @router.callback_query(F.data == "admin:bind")
    async def admin_bind_hint(callback: CallbackQuery) -> None:
        if not callback.from_user or not can_admin(callback.from_user.id):
            await callback.answer(ADMIN_NO_ACCESS, show_alert=True)
            return
        staff = settings.staff_chat_id or "не задан"
        await _edit_or_send(
            callback,
            ADMIN_BIND_HINT.format(staff_chat_id=staff),
            admin_back_keyboard(),
        )
        await callback.answer()

    @router.callback_query(F.data == "admin:setmenu")
    async def admin_start_setmenu(callback: CallbackQuery, db: Database) -> None:
        if not callback.from_user or not can_admin(callback.from_user.id):
            await callback.answer(ADMIN_NO_ACCESS, show_alert=True)
            return
        addresses = await db.get_all_addresses()
        await _edit_or_send(
            callback,
            ADMIN_CHOOSE_MENU_ADDRESS,
            admin_addresses_keyboard(addresses, prefix="setmenu"),
        )
        await callback.answer()

    @router.callback_query(F.data == "admin:clearmenu")
    async def admin_start_clearmenu(callback: CallbackQuery, db: Database) -> None:
        if not callback.from_user or not can_admin(callback.from_user.id):
            await callback.answer(ADMIN_NO_ACCESS, show_alert=True)
            return
        addresses = await db.get_all_addresses()
        await _edit_or_send(
            callback,
            ADMIN_CHOOSE_CLEAR_ADDRESS,
            admin_addresses_keyboard(addresses, prefix="clearmenu"),
        )
        await callback.answer()

    @router.message(Command("id"))
    async def cmd_id(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else 0
        await message.answer(
            ADMIN_YOUR_ID.format(user_id=user_id, chat_id=message.chat.id),
            parse_mode="HTML",
        )

    @router.message(Command("admin"))
    async def cmd_admin(message: Message) -> None:
        if await deny(message):
            return
        await message.answer(
            _panel_text(),
            parse_mode="HTML",
            reply_markup=admin_panel_keyboard(),
        )

    @router.message(Command("bindstaff"))
    async def cmd_bindstaff(message: Message, db: Database) -> None:
        if await deny(message):
            return

        chat = message.chat
        is_forum = bool(getattr(chat, "is_forum", False))
        if chat.type not in (ChatType.SUPERGROUP, ChatType.GROUP) or not is_forum:
            await message.answer(ADMIN_NEED_FORUM)
            return

        settings.staff_chat_id = chat.id
        await db.set_setting("staff_chat_id", str(chat.id))
        logger.info("Staff chat bound to %s", chat.id)
        await message.answer(
            ADMIN_STAFF_BOUND.format(chat_id=chat.id),
            parse_mode="HTML",
        )

    @router.my_chat_member()
    async def on_added_to_chat(
        event: ChatMemberUpdated,
        db: Database,
    ) -> None:
        new = event.new_chat_member
        if not new.user.is_bot:
            return
        if new.status not in {"administrator", "member"}:
            return
        chat = event.chat
        if not getattr(chat, "is_forum", False):
            return
        if settings.staff_chat_id:
            return
        settings.staff_chat_id = chat.id
        await db.set_setting("staff_chat_id", str(chat.id))
        logger.info("Auto-bound staff forum chat %s", chat.id)
        try:
            await event.bot.send_message(
                chat_id=chat.id,
                text=ADMIN_STAFF_BOUND.format(chat_id=chat.id),
                parse_mode="HTML",
            )
        except Exception:
            logger.warning("Could not confirm staff chat bind in %s", chat.id)

    @router.message(Command("stats"))
    async def cmd_stats(message: Message, db: Database) -> None:
        if await deny(message):
            return

        stats = await db.get_today_stats()
        await message.answer(_stats_text(stats), parse_mode="HTML")

    @router.message(Command("setmenu"))
    async def cmd_setmenu(
        message: Message,
        state: FSMContext,
        db: Database,
    ) -> None:
        if await deny(message):
            return
        addresses = await db.get_all_addresses()
        await state.set_state(AdminStates.choosing_menu_address)
        await message.answer(
            ADMIN_CHOOSE_MENU_ADDRESS,
            reply_markup=admin_addresses_keyboard(addresses, prefix="setmenu"),
        )

    @router.message(Command("clearmenu"))
    async def cmd_clearmenu(
        message: Message,
        state: FSMContext,
        db: Database,
    ) -> None:
        if await deny(message):
            return
        addresses = await db.get_all_addresses()
        await state.set_state(AdminStates.choosing_clear_menu_address)
        await message.answer(
            ADMIN_CHOOSE_CLEAR_ADDRESS,
            reply_markup=admin_addresses_keyboard(addresses, prefix="clearmenu"),
        )

    @router.callback_query(F.data.startswith("setmenu:"))
    async def choose_menu_address(
        callback: CallbackQuery,
        state: FSMContext,
        db: Database,
    ) -> None:
        if not callback.from_user or not can_admin(callback.from_user.id):
            await callback.answer(ADMIN_NO_ACCESS, show_alert=True)
            return
        if not callback.data or not isinstance(callback.message, Message):
            return

        address_id = int(callback.data.split(":")[1])
        address = await db.get_address_by_id(address_id)
        if not address:
            await callback.answer("Адрес не найден", show_alert=True)
            return

        await db.clear_menu_images(address_id)
        await state.set_state(AdminStates.collecting_menu_photos)
        await state.update_data(menu_address_id=address_id, menu_count=0)
        await callback.message.edit_text(
            ADMIN_SEND_MENU_PHOTOS.format(address=address.full_name),
            parse_mode="HTML",
        )
        await callback.message.answer(
            "Присылайте фото меню.",
            reply_markup=admin_menu_collect_keyboard(),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("clearmenu:"))
    async def clear_menu_address(
        callback: CallbackQuery,
        state: FSMContext,
        db: Database,
    ) -> None:
        if not callback.from_user or not can_admin(callback.from_user.id):
            await callback.answer(ADMIN_NO_ACCESS, show_alert=True)
            return
        if not callback.data or not isinstance(callback.message, Message):
            return

        address_id = int(callback.data.split(":")[1])
        address = await db.get_address_by_id(address_id)
        if not address:
            await callback.answer("Адрес не найден", show_alert=True)
            return

        await db.clear_menu_images(address_id)
        await state.clear()
        await callback.message.edit_text(
            ADMIN_MENU_CLEARED.format(address=address.full_name)
        )
        await callback.answer()

    @router.callback_query(F.data == "admin:cancel")
    async def admin_cancel(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await _edit_or_send(callback, _panel_text(), admin_panel_keyboard())
        await callback.answer()

    @router.message(AdminStates.collecting_menu_photos, F.photo)
    async def collect_menu_photo(
        message: Message,
        state: FSMContext,
        db: Database,
    ) -> None:
        if not message.from_user or not can_admin(message.from_user.id):
            return
        data = await state.get_data()
        address_id = data.get("menu_address_id")
        if not address_id:
            await state.clear()
            return

        saved = await save_photo_file_id(message)
        if not saved:
            return
        file_id, unique_id = saved
        count = int(data.get("menu_count", 0))
        await db.add_menu_image(address_id, file_id, unique_id, count)
        count += 1
        await state.update_data(menu_count=count)
        await message.answer(ADMIN_MENU_PHOTO_SAVED.format(count=count))

    @router.message(AdminStates.collecting_menu_photos, F.text == BUTTON_MENU_DONE)
    async def finish_menu_upload(
        message: Message,
        state: FSMContext,
        db: Database,
    ) -> None:
        data = await state.get_data()
        address_id = data.get("menu_address_id")
        count = int(data.get("menu_count", 0))
        await state.clear()

        kb = guest_main_keyboard(show_admin=True)
        if not address_id or count == 0:
            await message.answer(ADMIN_MENU_EMPTY, reply_markup=kb)
            return

        address = await db.get_address_by_id(address_id)
        name = address.full_name if address else str(address_id)
        await message.answer(
            ADMIN_MENU_SAVED.format(address=name, count=count),
            reply_markup=kb,
        )

    @router.message(AdminStates.collecting_menu_photos, F.text == BUTTON_CANCEL)
    async def cancel_menu_upload(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer(
            "Загрузка меню отменена.",
            reply_markup=guest_main_keyboard(show_admin=True),
        )

    return router
