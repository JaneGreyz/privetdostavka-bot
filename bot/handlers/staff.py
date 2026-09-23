from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.config import Settings
from bot.database.db import Database
from bot.keyboards import staff_order_card_markup
from bot.services.forwarding import copy_to_user
from bot.services.orders import change_order_status
from bot.services.topics import build_order_card_text
from bot.texts import STATUS_LABELS

logger = logging.getLogger(__name__)

STAFF_STATUS_ACTIONS = {
    "accepted": "accepted",
    "awaiting_payment": "awaiting_payment",
    "in_delivery": "in_delivery",
    "completed": "completed",
    "cancelled": "cancelled",
}


def create_staff_router(settings: Settings) -> Router:
    router = Router(name="staff")
    staff_chat = settings.staff_chat_id

    def _is_staff_chat(chat_id: int) -> bool:
        current = settings.staff_chat_id or staff_chat
        return bool(current) and chat_id == current

    @router.callback_query(F.data.startswith("staff:"))
    async def handle_staff_order_action(
        callback: CallbackQuery,
        db: Database,
    ) -> None:
        if not callback.data or not callback.message:
            return
        if not _is_staff_chat(callback.message.chat.id):
            await callback.answer()
            return

        parts = callback.data.split(":")
        if len(parts) != 3:
            await callback.answer("Ошибка", show_alert=True)
            return

        action = parts[1]
        order_id = int(parts[2])
        new_status = STAFF_STATUS_ACTIONS.get(action)
        if not new_status:
            await callback.answer("Неизвестное действие", show_alert=True)
            return

        order = await db.get_order(order_id)
        if not order:
            await callback.answer("Заказ не найден", show_alert=True)
            return

        if order.status in ("completed", "cancelled"):
            await callback.answer("Заказ уже закрыт", show_alert=True)
            return

        if order.status == new_status:
            await callback.answer(STATUS_LABELS.get(new_status, new_status))
            return

        order = await change_order_status(
            callback.bot, db, settings, order, new_status
        )

        await callback.answer(STATUS_LABELS.get(new_status, new_status))

        try:
            await callback.message.edit_text(
                build_order_card_text(order),
                parse_mode="HTML",
                reply_markup=staff_order_card_markup(order),
            )
        except Exception:
            logger.exception("Failed to update card after status change #%s", order.id)

    @router.message(F.message_thread_id.as_("topic_id"))
    async def handle_staff_topic_message(
        message: Message,
        db: Database,
        topic_id: int,
    ) -> None:
        if not _is_staff_chat(message.chat.id):
            return
        if message.from_user and message.from_user.is_bot:
            return
        if (
            message.forum_topic_created
            or message.forum_topic_edited
            or message.forum_topic_closed
            or message.forum_topic_reopened
        ):
            return

        order = await db.get_order_by_topic(topic_id)
        if order:
            if message.message_id == order.staff_message_id:
                return
            await copy_to_user(message.bot, message, order.guest_id)
            return

        support = await db.get_support_chat_by_topic(topic_id)
        if support:
            await copy_to_user(message.bot, message, support.user_id)

    return router
