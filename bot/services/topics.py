from __future__ import annotations

from html import escape
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from bot.config import Settings
from bot.database.db import Database
from bot.database.models import Order
from bot.keyboards import staff_order_card_markup, staff_order_keyboard
from bot.texts import STAFF_ORDER_CARD, STAFF_SUPPORT_TOPIC_CARD, STATUS_LABELS
from bot.utils import guest_display_name

logger = logging.getLogger(__name__)


def build_order_card_text(order: Order) -> str:
    username_line = ""
    if order.guest_username:
        username_line = f"🔗 <b>Username:</b> @{escape(order.guest_username)}\n"

    status_line = ""
    if order.status != "new":
        label = STATUS_LABELS.get(order.status, order.status)
        status_line = f"\n📌 <b>Статус:</b> {label}\n"

    return STAFF_ORDER_CARD.format(
        order_id=order.id,
        address=escape(order.address),
        clarification=escape(order.address_clarification or "—"),
        phone=escape(order.phone),
        guest_name=escape(order.guest_name),
        guest_id=order.guest_id,
        username_line=username_line,
        order_text=escape(order.order_text or "—"),
        status_line=status_line,
    )


async def _send_order_card(
    bot: Bot,
    settings: Settings,
    order: Order,
    topic_id: int,
) -> int | None:
    card_text = build_order_card_text(order)
    markups = (staff_order_keyboard(order), None)

    for markup in markups:
        try:
            card_message = await bot.send_message(
                chat_id=settings.staff_chat_id,
                message_thread_id=topic_id,
                text=card_text,
                parse_mode="HTML",
                reply_markup=markup,
            )
            return card_message.message_id
        except TelegramBadRequest as exc:
            logger.warning(
                "Order card send failed for #%s (markup=%s): %s",
                order.id,
                markup is not None,
                exc,
            )

    try:
        plain = (
            f"🆕 Заказ #{order.id}\n"
            f"📍 {order.address}\n"
            f"👤 {order.guest_name}\n"
            f"📞 {order.phone}\n\n"
            f"📝 {order.order_text or '—'}"
        )
        card_message = await bot.send_message(
            chat_id=settings.staff_chat_id,
            message_thread_id=topic_id,
            text=plain,
            reply_markup=staff_order_keyboard(order),
        )
        return card_message.message_id
    except TelegramBadRequest as exc:
        logger.error("Plain order card send failed for #%s: %s", order.id, exc)
        return None


async def create_order_topic(
    bot: Bot,
    db: Database,
    settings: Settings,
    order: Order,
) -> Order:
    topic_name = f"#{order.id} | {order.address_short}"
    forum_topic = await bot.create_forum_topic(
        chat_id=settings.staff_chat_id,
        name=topic_name[:128],
    )
    topic_id = forum_topic.message_thread_id

    await db.update_order_topic(order.id, topic_id)

    staff_message_id = await _send_order_card(bot, settings, order, topic_id)
    if staff_message_id:
        await db.set_order_staff_message_id(order.id, staff_message_id)

    updated = await db.get_order(order.id)
    if updated is None:
        raise RuntimeError("Order not found after topic creation")
    if updated.topic_id is None:
        raise RuntimeError("Topic id was not saved")
    return updated


async def update_order_card(
    bot: Bot,
    settings: Settings,
    order: Order,
) -> None:
    if not order.topic_id or not order.staff_message_id:
        return

    try:
        await bot.edit_message_text(
            chat_id=settings.staff_chat_id,
            message_id=order.staff_message_id,
            text=build_order_card_text(order),
            parse_mode="HTML",
            reply_markup=staff_order_card_markup(order),
        )
    except TelegramBadRequest as exc:
        err = str(exc).lower()
        if "message is not modified" not in err:
            logger.warning("Could not edit order card #%s: %s", order.id, exc)


async def create_support_topic(
    bot: Bot,
    db: Database,
    settings: Settings,
    user,
) -> int:
    """Создаёт тему для обращения без заказа и возвращает topic_id."""
    name = guest_display_name(user)
    topic_name = f"Обращение | {name}"[:128]
    forum_topic = await bot.create_forum_topic(
        chat_id=settings.staff_chat_id,
        name=topic_name,
    )
    topic_id = forum_topic.message_thread_id

    username_line = ""
    if user.username:
        username_line = f"🔗 <b>Username:</b> @{escape(user.username)}\n"

    await bot.send_message(
        chat_id=settings.staff_chat_id,
        message_thread_id=topic_id,
        text=STAFF_SUPPORT_TOPIC_CARD.format(
            guest_name=escape(name),
            guest_id=user.id,
            username_line=username_line,
        ),
        parse_mode="HTML",
    )

    await db.create_support_chat(
        user_id=user.id,
        user_name=name,
        user_username=user.username,
        topic_id=topic_id,
    )
    return topic_id
