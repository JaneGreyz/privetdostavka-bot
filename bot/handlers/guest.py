from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import CommandStart, StateFilter, or_f
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import Settings
from bot.database.db import Database
from bot.database.models import Order
from bot.filters import ActiveConversationFilter, NotMenuButtonFilter, PendingOrderFilter
from bot.keyboards import (
    addresses_keyboard,
    cancel_active_order_keyboard,
    cancel_keyboard,
    guest_main_keyboard,
    guest_order_keyboard,
    saved_profile_keyboard,
)
from bot.services.forwarding import copy_to_topic
from bot.services.menu import send_menu_for_address
from bot.services.orders import cancel_guest_active_order, finalize_order
from bot.services.topics import create_support_topic
from bot.states.order import OrderStates
from bot.texts import (
    ADDRESS_SELECTED,
    BUTTON_CANCEL_ORDER,
    BUTTON_CONTACT_MANAGER,
    BUTTON_FAQ,
    BUTTON_MAKE_ORDER,
    BUTTON_START,
    CHOOSE_ADDRESS,
    CONTACT_MANAGER,
    CONTACT_MANAGER_FAILED,
    CONTACT_MANAGER_PROMPT,
    ENTER_ADDRESS_CLARIFICATION,
    ENTER_ORDER_TEXT,
    ENTER_PHONE,
    FAQ,
    INVALID_PHONE,
    NO_ADDRESSES,
    OFF_HOURS_MENU_CAPTION,
    OFF_HOURS_START,
    ORDER_ACCEPTED,
    ORDER_CANCELLED_ACTIVE,
    ORDER_CANCELLED_BY_GUEST,
    ORDER_ERROR_RETRY,
    ORDER_FINALIZE_FAILED,
    ORDER_IN_PROGRESS,
    ORDER_NO_ACTIVE,
    ORDER_NO_STAFF_CHAT,
    ORDER_TOPIC_RIGHTS,
    SAVED_PROFILE_CLARIFICATION,
    SAVED_PROFILE_CONFIRM,
    STAFF_GUEST_WANTS_CONTACT,
    STAFF_SUPPORT_GUEST_MESSAGE,
    WELCOME,
    WELCOME_OFF_HOURS,
)
from bot.utils import (
    guest_display_name,
    is_valid_phone,
    is_working_hours,
    normalize_phone,
)

logger = logging.getLogger(__name__)
router = Router(name="guest")


def _is_off_hours(settings: Settings) -> bool:
    now = datetime.now(ZoneInfo(settings.timezone))
    return not is_working_hours(
        now, settings.delivery_start_hour, settings.delivery_end_hour
    )


def _main_kb(message: Message, settings: Settings):
    user_id = message.from_user.id if message.from_user else None
    return guest_main_keyboard(show_admin=settings.is_admin(user_id))


def _format_saved_profile(profile) -> str:
    clarification_line = ""
    if profile.address_clarification.strip():
        clarification_line = SAVED_PROFILE_CLARIFICATION.format(
            clarification=profile.address_clarification.strip()
        )
    return SAVED_PROFILE_CONFIRM.format(
        address=profile.address,
        clarification_line=clarification_line,
        phone=profile.phone,
    )


async def _start_address_selection(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
) -> None:
    addresses = await db.get_active_addresses()
    if not addresses:
        await message.answer(NO_ADDRESSES, reply_markup=_main_kb(message, settings))
        return

    await state.set_state(OrderStates.choosing_address)
    await message.answer(
        CHOOSE_ADDRESS,
        reply_markup=addresses_keyboard(addresses),
    )


async def _proceed_to_menu(
    message: Message,
    state: FSMContext,
    db: Database,
    order: Order,
    address_id: int,
) -> None:
    await state.update_data(order_id=order.id, address_id=address_id)
    await state.set_state(OrderStates.order_text)

    address = await db.get_address_by_id(address_id)
    if address:
        await send_menu_for_address(message.bot, db, message.chat.id, address)

    await message.answer(ENTER_ORDER_TEXT, reply_markup=guest_order_keyboard())


async def show_welcome(
    message: Message,
    state: FSMContext,
    settings: Settings,
) -> None:
    await state.clear()
    logger.info("Start from user %s", message.from_user.id if message.from_user else "?")
    text = WELCOME
    if _is_off_hours(settings):
        text += WELCOME_OFF_HOURS
    await message.answer(text, reply_markup=_main_kb(message, settings))


@router.message(CommandStart(), F.chat.type == "private")
async def cmd_start(
    message: Message,
    state: FSMContext,
    settings: Settings,
) -> None:
    await show_welcome(message, state, settings)


@router.message(F.chat.type == "private", F.text == BUTTON_START)
async def press_start(
    message: Message,
    state: FSMContext,
    settings: Settings,
) -> None:
    await show_welcome(message, state, settings)


@router.message(F.chat.type == "private", F.text == BUTTON_MAKE_ORDER)
async def start_order(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
) -> None:
    if not message.from_user:
        return

    active = await db.get_active_order_for_guest(message.from_user.id)
    if active:
        if active.topic_id:
            await message.answer(
                ORDER_IN_PROGRESS.format(order_id=active.id),
                reply_markup=cancel_active_order_keyboard(),
            )
            return
        await db.update_order_status(active.id, "cancelled")

    if _is_off_hours(settings):
        addresses = await db.get_active_addresses()
        if not addresses:
            await message.answer(NO_ADDRESSES, reply_markup=_main_kb(message, settings))
            return
        await state.clear()
        await state.set_state(OrderStates.choosing_address)
        await state.update_data(off_hours=True)
        await message.answer(
            OFF_HOURS_START,
            reply_markup=addresses_keyboard(addresses),
        )
        return

    profile = await db.get_guest_profile(message.from_user.id)
    if profile:
        address = await db.get_address_by_id(profile.address_id)
        if address and address.is_active:
            await state.set_state(OrderStates.confirm_saved_profile)
            await message.answer(
                _format_saved_profile(profile),
                reply_markup=saved_profile_keyboard(),
                parse_mode="HTML",
            )
            return

    await _start_address_selection(message, state, db, settings)


@router.message(F.chat.type == "private", F.text == BUTTON_FAQ)
async def show_faq(message: Message) -> None:
    await message.answer(FAQ, disable_web_page_preview=True)


@router.message(F.chat.type == "private", F.text == BUTTON_CONTACT_MANAGER)
async def contact_manager(
    message: Message,
    db: Database,
    settings: Settings,
) -> None:
    if not message.from_user:
        return

    if not settings.has_staff_chat():
        await message.answer(
            CONTACT_MANAGER_FAILED, reply_markup=_main_kb(message, settings)
        )
        return

    order = await db.get_active_order_for_guest(message.from_user.id)
    if order and order.topic_id:
        try:
            await message.bot.send_message(
                chat_id=settings.staff_chat_id,
                message_thread_id=order.topic_id,
                text=STAFF_GUEST_WANTS_CONTACT.format(order_id=order.id),
            )
        except Exception:
            logger.exception("Failed to ping staff for order #%s", order.id)
            await message.answer(
                CONTACT_MANAGER_FAILED, reply_markup=_main_kb(message, settings)
            )
            return
        await message.answer(CONTACT_MANAGER, reply_markup=_main_kb(message, settings))
        return

    support = await db.get_open_support_chat(message.from_user.id)
    if support:
        try:
            await message.bot.send_message(
                chat_id=settings.staff_chat_id,
                message_thread_id=support.topic_id,
                text=STAFF_GUEST_WANTS_CONTACT.format(order_id="—"),
            )
        except Exception:
            logger.exception("Failed to ping support topic for user %s", message.from_user.id)
        await message.answer(
            CONTACT_MANAGER_PROMPT, reply_markup=_main_kb(message, settings)
        )
        return

    try:
        await create_support_topic(message.bot, db, settings, message.from_user)
    except Exception:
        logger.exception("Failed to create support topic")
        await message.answer(
            CONTACT_MANAGER_FAILED, reply_markup=_main_kb(message, settings)
        )
        return

    await message.answer(
        CONTACT_MANAGER_PROMPT, reply_markup=_main_kb(message, settings)
    )


@router.message(F.chat.type == "private", F.text == BUTTON_CANCEL_ORDER)
async def cancel_my_order(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
) -> None:
    if not message.from_user:
        return

    current = await state.get_state()
    order = await cancel_guest_active_order(
        message.bot, db, settings, message.from_user.id, state
    )

    if order:
        await message.answer(
            ORDER_CANCELLED_ACTIVE.format(order_id=order.id),
            reply_markup=_main_kb(message, settings),
        )
        return

    if current:
        await state.clear()
        await message.answer(
            ORDER_CANCELLED_BY_GUEST, reply_markup=_main_kb(message, settings)
        )
        return

    await message.answer(ORDER_NO_ACTIVE, reply_markup=_main_kb(message, settings))


@router.callback_query(F.data == "profile:use")
async def use_saved_profile(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    settings: Settings,
) -> None:
    if not callback.from_user or not isinstance(callback.message, Message):
        return

    profile = await db.get_guest_profile(callback.from_user.id)
    if not profile:
        await callback.answer("Данные не найдены", show_alert=True)
        await _start_address_selection(callback.message, state, db, settings)
        return

    address = await db.get_address_by_id(profile.address_id)
    if not address or not address.is_active:
        await callback.answer("Сохранённый адрес недоступен", show_alert=True)
        await _start_address_selection(callback.message, state, db, settings)
        return

    order = await db.create_order(
        guest_id=callback.from_user.id,
        guest_username=callback.from_user.username,
        guest_name=guest_display_name(callback.from_user),
        address=profile.address,
        address_short=profile.address_short,
        address_clarification=profile.address_clarification,
        phone=profile.phone,
    )
    await _proceed_to_menu(
        callback.message, state, db, order, profile.address_id
    )
    await callback.answer()


@router.callback_query(F.data == "profile:change")
async def change_saved_profile(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    settings: Settings,
) -> None:
    if not isinstance(callback.message, Message):
        return
    await _start_address_selection(callback.message, state, db, settings)
    await callback.answer()


@router.callback_query(F.data.startswith("addr:"))
async def choose_address(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
) -> None:
    if not callback.data or not isinstance(callback.message, Message):
        return

    address_id = int(callback.data.split(":")[1])
    address = await db.get_address_by_id(address_id)
    if not address or not address.is_active:
        await callback.answer("Адрес недоступен", show_alert=True)
        return

    data = await state.get_data()
    if data.get("off_hours"):
        await send_menu_for_address(
            callback.message.bot,
            db,
            callback.message.chat.id,
            address,
            caption=OFF_HOURS_MENU_CAPTION.format(address=address.full_name),
        )
        await callback.answer()
        return

    await state.update_data(
        address_id=address.id,
        address=address.full_name,
        address_short=address.short_name,
    )
    await state.set_state(OrderStates.address_clarification)
    await callback.message.edit_text(
        ADDRESS_SELECTED.format(
            address=address.full_name,
            prompt=ENTER_ADDRESS_CLARIFICATION,
        ),
        reply_markup=cancel_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(OrderStates.address_clarification, F.text, NotMenuButtonFilter())
async def process_clarification(message: Message, state: FSMContext) -> None:
    await state.update_data(address_clarification=(message.text or "").strip())
    await state.set_state(OrderStates.phone)
    await message.answer(ENTER_PHONE, reply_markup=guest_order_keyboard())


@router.message(OrderStates.phone, F.text, NotMenuButtonFilter())
async def process_phone(
    message: Message,
    state: FSMContext,
    db: Database,
) -> None:
    if not message.from_user or not message.text:
        return

    if not is_valid_phone(message.text):
        await message.answer(INVALID_PHONE, reply_markup=guest_order_keyboard())
        return

    phone = normalize_phone(message.text)
    data = await state.get_data()

    order = await db.create_order(
        guest_id=message.from_user.id,
        guest_username=message.from_user.username,
        guest_name=guest_display_name(message.from_user),
        address=data["address"],
        address_short=data["address_short"],
        address_clarification=data.get("address_clarification", ""),
        phone=phone,
    )

    await db.save_guest_profile(
        guest_id=message.from_user.id,
        address_id=data["address_id"],
        address=data["address"],
        address_short=data["address_short"],
        address_clarification=data.get("address_clarification", ""),
        phone=phone,
    )

    await _proceed_to_menu(message, state, db, order, data["address_id"])


async def _resolve_pending_order(
    message: Message,
    state: FSMContext,
    db: Database,
) -> Order | None:
    if not message.from_user:
        return None

    data = await state.get_data()
    order_id = data.get("order_id")
    if order_id:
        order = await db.get_order(order_id)
        if order and order.topic_id is None:
            return order

    order = await db.get_pending_order_for_guest(message.from_user.id)
    if order:
        await state.update_data(order_id=order.id)
        await state.set_state(OrderStates.order_text)
    return order


@router.message(
    F.chat.type == "private",
    NotMenuButtonFilter(),
    ~F.text.startswith("/"),
    or_f(StateFilter(OrderStates.order_text), PendingOrderFilter()),
)
async def process_order_message(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
) -> None:
    if not message.from_user:
        return

    order = await _resolve_pending_order(message, state, db)
    if not order:
        await state.clear()
        await message.answer(
            ORDER_ERROR_RETRY, reply_markup=_main_kb(message, settings)
        )
        return

    order_text = (message.text or message.caption or "").strip()
    if not order_text:
        await message.answer(ENTER_ORDER_TEXT, reply_markup=guest_order_keyboard())
        return

    try:
        order = await finalize_order(message.bot, db, settings, order, order_text)
    except Exception as exc:
        logger.exception("Failed to finalize order %s", order.id)
        hint = ORDER_FINALIZE_FAILED
        err = str(exc).lower()
        if "not enough rights" in err or "manage topics" in err:
            hint = ORDER_TOPIC_RIGHTS
        await message.answer(hint, reply_markup=guest_order_keyboard())
        return

    if order.topic_id:
        await copy_to_topic(
            message.bot, message, settings.staff_chat_id, order.topic_id
        )
    elif not settings.has_staff_chat():
        await state.clear()
        await message.answer(
            ORDER_NO_STAFF_CHAT, reply_markup=_main_kb(message, settings)
        )
        return
    else:
        logger.error("Order %s finalized without topic_id", order.id)
        await message.answer(ORDER_NO_STAFF_CHAT, reply_markup=guest_order_keyboard())
        return

    data = await state.get_data()
    address_id = data.get("address_id")
    if address_id:
        await db.save_guest_profile(
            guest_id=message.from_user.id,
            address_id=address_id,
            address=order.address,
            address_short=order.address_short,
            address_clarification=order.address_clarification,
            phone=order.phone,
        )

    await state.clear()
    await message.answer(
        ORDER_ACCEPTED.format(order_id=order.id),
        reply_markup=_main_kb(message, settings),
    )


@router.callback_query(F.data == "guest:cancel_active")
async def cancel_active_order(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    settings: Settings,
) -> None:
    if not callback.from_user:
        return

    order = await cancel_guest_active_order(
        callback.bot, db, settings, callback.from_user.id, state
    )
    if not order:
        if isinstance(callback.message, Message):
            await callback.message.edit_text(ORDER_NO_ACTIVE)
        await callback.answer()
        return

    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            ORDER_CANCELLED_ACTIVE.format(order_id=order.id)
        )
        await callback.bot.send_message(
            chat_id=callback.message.chat.id,
            text="Нажмите «Сделать заказ», чтобы оформить новый.",
            reply_markup=guest_main_keyboard(
                show_admin=settings.is_admin(callback.from_user.id)
            ),
        )
    await callback.answer()


@router.callback_query(F.data == "order:cancel")
async def cancel_order(
    callback: CallbackQuery,
    state: FSMContext,
    db: Database,
    settings: Settings,
) -> None:
    if not callback.from_user:
        return

    current = await state.get_state()
    order = await cancel_guest_active_order(
        callback.bot, db, settings, callback.from_user.id, state
    )
    if not order and current:
        await state.clear()

    if isinstance(callback.message, Message):
        if order:
            await callback.message.edit_text(
                ORDER_CANCELLED_ACTIVE.format(order_id=order.id)
            )
        elif current:
            await callback.message.edit_text(ORDER_CANCELLED_BY_GUEST)
        await callback.bot.send_message(
            chat_id=callback.message.chat.id,
            text="Вы на главном экране.",
            reply_markup=guest_main_keyboard(
                show_admin=settings.is_admin(callback.from_user.id)
            ),
        )
    await callback.answer()


@router.message(
    F.chat.type == "private",
    StateFilter(None),
    NotMenuButtonFilter(),
    ActiveConversationFilter(),
)
async def forward_guest_message(
    message: Message,
    db: Database,
    settings: Settings,
) -> None:
    if not message.from_user or not settings.has_staff_chat():
        return

    order = await db.get_active_order_for_guest(message.from_user.id)
    if order and order.topic_id:
        await copy_to_topic(
            message.bot, message, settings.staff_chat_id, order.topic_id
        )
        return

    support = await db.get_open_support_chat(message.from_user.id)
    if not support:
        return

    try:
        await message.bot.send_message(
            chat_id=settings.staff_chat_id,
            message_thread_id=support.topic_id,
            text=STAFF_SUPPORT_GUEST_MESSAGE,
        )
    except Exception:
        pass
    await copy_to_topic(
        message.bot, message, settings.staff_chat_id, support.topic_id
    )
