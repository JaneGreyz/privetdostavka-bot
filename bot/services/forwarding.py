from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

logger = logging.getLogger(__name__)


async def copy_to_topic(
    bot: Bot,
    message: Message,
    chat_id: int,
    topic_id: int,
) -> bool:
    """Копирует любое сообщение гостя в тему сотрудников (текст, фото, QR, файлы)."""
    try:
        await bot.copy_message(
            chat_id=chat_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
            message_thread_id=topic_id,
        )
        return True
    except TelegramBadRequest as exc:
        logger.warning("copy_message to topic failed: %s", exc)
        try:
            await bot.forward_message(
                chat_id=chat_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
                message_thread_id=topic_id,
            )
            return True
        except TelegramBadRequest:
            logger.exception("forward_message to topic failed")
            return False


async def copy_to_user(bot: Bot, message: Message, user_id: int) -> bool:
    """Копирует ответ сотрудника гостю: текст, фото, QR, документы, голосовые."""
    try:
        await bot.copy_message(
            chat_id=user_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
        return True
    except TelegramBadRequest as exc:
        logger.warning("copy_message to user failed: %s", exc)
        try:
            await bot.forward_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
            return True
        except TelegramBadRequest:
            logger.exception("forward_message to user failed")
            return False
