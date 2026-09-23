from __future__ import annotations

import logging
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import FSInputFile, InputMediaPhoto, Message

from bot.config import BASE_DIR
from bot.database.db import Database
from bot.database.models import Address
from bot.texts import MENU_UNAVAILABLE, SENDING_MENU

logger = logging.getLogger(__name__)

LOCAL_MENU_DIR = BASE_DIR / "data" / "menu"

# Локальные фото меню по адресу кофейни — пока file_id не загружены через /setmenu
LOCAL_MENU_FILES = {
    "Ленинградский проспект, 36с11": "sok.jpeg",
    "Дмитровский проезд, 1": "d1.jpeg",
    "Пятницкая улица, 71/5с2": "pt.jpeg",
}


def _local_menu_path(address: Address) -> Path | None:
    name = LOCAL_MENU_FILES.get(address.full_name)
    if not name:
        return None
    path = LOCAL_MENU_DIR / name
    return path if path.is_file() else None


async def send_menu_for_address(
    bot: Bot,
    db: Database,
    chat_id: int,
    address: Address,
    *,
    caption: str | None = None,
) -> bool:
    """Отправляет гостю фото меню выбранной кофейни. Возвращает True, если отправилось."""
    caption = caption or SENDING_MENU.format(address=address.full_name)
    images = await db.get_menu_images(address.id)
    if not images:
        local = _local_menu_path(address)
        if local:
            try:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=FSInputFile(local),
                    caption=caption,
                    parse_mode="HTML",
                )
                return True
            except TelegramBadRequest:
                logger.exception("Failed to send local menu for address %s", address.id)
        await bot.send_message(chat_id=chat_id, text=MENU_UNAVAILABLE)
        return False
    file_ids = [item.file_id for item in images]

    if len(file_ids) == 1:
        try:
            await bot.send_photo(
                chat_id=chat_id,
                photo=file_ids[0],
                caption=caption,
                parse_mode="HTML",
            )
            return True
        except TelegramBadRequest:
            logger.exception("Failed to send single menu photo for address %s", address.id)
            await bot.send_message(chat_id=chat_id, text=MENU_UNAVAILABLE)
            return False

    sent_any = False
    for start in range(0, len(file_ids), 10):
        chunk = file_ids[start : start + 10]
        media = [
            InputMediaPhoto(
                media=file_id,
                caption=caption if start == 0 and index == 0 else None,
                parse_mode="HTML" if start == 0 and index == 0 else None,
            )
            for index, file_id in enumerate(chunk)
        ]
        try:
            await bot.send_media_group(chat_id=chat_id, media=media)
            sent_any = True
        except TelegramBadRequest:
            logger.exception("Failed to send menu album for address %s", address.id)
            for index, file_id in enumerate(chunk):
                try:
                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=file_id,
                        caption=caption if start == 0 and index == 0 else None,
                        parse_mode="HTML" if start == 0 and index == 0 else None,
                    )
                    sent_any = True
                except TelegramBadRequest:
                    logger.exception("Failed to send menu photo %s", file_id)

    if not sent_any:
        await bot.send_message(chat_id=chat_id, text=MENU_UNAVAILABLE)
    return sent_any


async def save_photo_file_id(message: Message) -> tuple[str, str | None] | None:
    if not message.photo:
        return None
    photo = message.photo[-1]
    return photo.file_id, photo.file_unique_id


async def send_local_menu_and_store(
    bot: Bot,
    db: Database,
    chat_id: int,
    address_id: int,
    path: str,
) -> None:
    """Вспомогательный метод: загрузить файл с диска и сохранить file_id."""
    sent: Message = await bot.send_photo(chat_id=chat_id, photo=FSInputFile(path))
    if not sent.photo:
        return
    photo = sent.photo[-1]
    count = await db.count_menu_images(address_id)
    await db.add_menu_image(address_id, photo.file_id, photo.file_unique_id, count)
