from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault, ErrorEvent

from bot.config import load_settings
from bot.database.db import Database
from bot.handlers.admin import create_admin_router
from bot.handlers.guest import router as guest_router
from bot.handlers.staff import create_staff_router
from bot.middlewares.dependencies import DependencyMiddleware
from bot.middlewares.errors import ErrorHandlerMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
# В Docker stdout часто буферизуется — принудительно сбрасываем, чтобы логи
# появлялись на хостинге сразу, а не после завершения процесса
for _handler in logging.getLogger().handlers:
    if hasattr(_handler, "reconfigure"):
        try:
            _handler.reconfigure(line_buffering=True)
        except Exception:
            pass
logging.getLogger().setLevel(logging.INFO)
print("Logging configured", flush=True)
logger = logging.getLogger(__name__)


async def _restore_staff_chat(settings, db: Database) -> None:
    if settings.staff_chat_id:
        return
    saved = await db.get_setting("staff_chat_id")
    if saved:
        settings.staff_chat_id = int(saved)
        logger.info("Restored STAFF_CHAT_ID from database: %s", saved)


async def _setup_commands(bot: Bot, settings) -> None:
    await bot.set_my_commands(
        [BotCommand(command="start", description="Начать / главное меню")],
        scope=BotCommandScopeDefault(),
    )
    admin_commands = [
        BotCommand(command="start", description="Главное меню"),
        BotCommand(command="admin", description="Панель администратора"),
        BotCommand(command="setmenu", description="Загрузить меню кофейни"),
        BotCommand(command="clearmenu", description="Удалить меню кофейни"),
        BotCommand(command="bindstaff", description="Привязать группу сотрудников"),
        BotCommand(command="stats", description="Статистика за сегодня"),
        BotCommand(command="id", description="Показать ID чата"),
    ]
    for admin_id in settings.admin_ids:
        try:
            await bot.set_my_commands(
                admin_commands,
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except Exception:
            logger.warning("Could not set admin commands for %s", admin_id)


async def main() -> None:
    settings = load_settings()

    # Диагностика старта: сразу видно, что подхватилось из окружения
    token_tail = settings.bot_token[-5:] if settings.bot_token else ""
    logger.info(
        "Config: token=...%s staff_chat=%s admins=%s db=%s tz=%s hours=%s-%s",
        token_tail,
        settings.staff_chat_id or "NOT SET",
        sorted(settings.admin_ids) or "NOT SET",
        settings.database_path,
        settings.timezone,
        settings.delivery_start_hour,
        settings.delivery_end_hour,
    )
    if not settings.staff_chat_id:
        logger.warning("STAFF_CHAT_ID is not set — заказы не смогут уходить в группу")
    if not settings.admin_ids:
        logger.warning("ADMIN_IDS is not set — админ-панель недоступна")

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    logger.info("Starting Привет delivery bot...")
    dp = Dispatcher(storage=MemoryStorage())
    db = Database(settings.database_path)
    await db.connect()
    await _restore_staff_chat(settings, db)

    logger.info("Staff chat: %s", settings.staff_chat_id or "not set")
    logger.info("Admins: %s", ", ".join(map(str, settings.admin_ids)) or "none (bootstrap)")

    @dp.errors()
    async def on_error(event: ErrorEvent) -> None:
        logger.exception("Update error: %s", event.exception)

    dp.message.middleware(ErrorHandlerMiddleware())
    dp.callback_query.middleware(ErrorHandlerMiddleware())
    dp.my_chat_member.middleware(ErrorHandlerMiddleware())
    dp.message.middleware(DependencyMiddleware(db, settings))
    dp.callback_query.middleware(DependencyMiddleware(db, settings))
    dp.my_chat_member.middleware(DependencyMiddleware(db, settings))

    dp.include_router(create_admin_router(settings))
    dp.include_router(guest_router)
    dp.include_router(create_staff_router(settings))

    try:
        await _setup_commands(bot, settings)
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook cleared, polling started")
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
    except KeyError as exc:
        logger.error(
            "Missing required environment variable: %s. "
            "Проверьте, что переменная задана в настройках хостинга.",
            exc,
        )
        raise SystemExit(1) from exc
    except ValueError as exc:
        logger.error("Invalid environment variable format: %s", exc)
        raise SystemExit(1) from exc
    except Exception:
        logger.exception("Bot failed to start")
        raise SystemExit(1)
