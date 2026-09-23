from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from bot.database.models import ACTIVE_STATUSES, Address, Order
from bot.texts import (
    BUTTON_ADMIN,
    BUTTON_BACK,
    BUTTON_CANCEL,
    BUTTON_CANCEL_ORDER,
    BUTTON_CHANGE_ADDRESS,
    BUTTON_CONTACT_MANAGER,
    BUTTON_FAQ,
    BUTTON_MAKE_ORDER,
    BUTTON_MENU_DONE,
    BUTTON_START,
    BUTTON_STATUS_ACCEPTED,
    BUTTON_STATUS_AWAITING_PAYMENT,
    BUTTON_STATUS_CANCELLED,
    BUTTON_STATUS_COMPLETED,
    BUTTON_STATUS_IN_DELIVERY,
    BUTTON_USE_SAVED_PROFILE,
)


def guest_main_keyboard(*, show_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=BUTTON_START)],
        [KeyboardButton(text=BUTTON_MAKE_ORDER)],
        [KeyboardButton(text=BUTTON_CONTACT_MANAGER)],
        [KeyboardButton(text=BUTTON_FAQ)],
    ]
    if show_admin:
        rows.append([KeyboardButton(text=BUTTON_ADMIN)])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
    )


def guest_order_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BUTTON_CANCEL_ORDER)],
            [KeyboardButton(text=BUTTON_CONTACT_MANAGER)],
            [KeyboardButton(text=BUTTON_FAQ)],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def admin_menu_collect_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BUTTON_MENU_DONE)],
            [KeyboardButton(text=BUTTON_CANCEL)],
        ],
        resize_keyboard=True,
    )


def remove_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def saved_profile_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=BUTTON_USE_SAVED_PROFILE,
                    callback_data="profile:use",
                )
            ],
            [
                InlineKeyboardButton(
                    text=BUTTON_CHANGE_ADDRESS,
                    callback_data="profile:change",
                )
            ],
            [
                InlineKeyboardButton(
                    text=BUTTON_CANCEL,
                    callback_data="order:cancel",
                )
            ],
        ]
    )


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=BUTTON_CANCEL, callback_data="order:cancel")]
        ]
    )


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Статистика за сегодня",
                    callback_data="admin:stats",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🍽 Загрузить меню",
                    callback_data="admin:setmenu",
                ),
                InlineKeyboardButton(
                    text="🗑 Удалить меню",
                    callback_data="admin:clearmenu",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🆔 Мой ID",
                    callback_data="admin:id",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💬 Привязать группу",
                    callback_data="admin:bind",
                )
            ],
        ]
    )


def admin_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=BUTTON_BACK, callback_data="admin:back")]
        ]
    )


def addresses_keyboard(
    addresses: list[Address],
    *,
    prefix: str = "addr",
) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=addr.full_name, callback_data=f"{prefix}:{addr.id}")]
        for addr in addresses
    ]
    buttons.append(
        [InlineKeyboardButton(text=BUTTON_CANCEL, callback_data="order:cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def admin_addresses_keyboard(
    addresses: list[Address],
    *,
    prefix: str,
) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=addr.full_name, callback_data=f"{prefix}:{addr.id}")]
        for addr in addresses
    ]
    buttons.append(
        [InlineKeyboardButton(text=BUTTON_CANCEL, callback_data="admin:cancel")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cancel_active_order_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=BUTTON_CANCEL,
                    callback_data="guest:cancel_active",
                )
            ]
        ]
    )


def staff_order_keyboard(order: Order) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=BUTTON_STATUS_ACCEPTED,
                    callback_data=f"staff:accepted:{order.id}",
                ),
                InlineKeyboardButton(
                    text=BUTTON_STATUS_AWAITING_PAYMENT,
                    callback_data=f"staff:awaiting_payment:{order.id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=BUTTON_STATUS_IN_DELIVERY,
                    callback_data=f"staff:in_delivery:{order.id}",
                ),
                InlineKeyboardButton(
                    text=BUTTON_STATUS_COMPLETED,
                    callback_data=f"staff:completed:{order.id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=BUTTON_STATUS_CANCELLED,
                    callback_data=f"staff:cancelled:{order.id}",
                )
            ],
        ]
    )


def staff_order_card_markup(order: Order) -> InlineKeyboardMarkup | None:
    if order.status in ACTIVE_STATUSES:
        return staff_order_keyboard(order)
    return None
