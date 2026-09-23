from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.database.db import Database
from bot.states.order import OrderStates
from bot.texts import (
    BUTTON_ADMIN,
    BUTTON_CANCEL,
    BUTTON_CANCEL_ORDER,
    BUTTON_CONTACT_MANAGER,
    BUTTON_FAQ,
    BUTTON_MAKE_ORDER,
    BUTTON_MENU_DONE,
    BUTTON_START,
)

MENU_BUTTONS = frozenset(
    {
        BUTTON_START,
        BUTTON_ADMIN,
        BUTTON_MAKE_ORDER,
        BUTTON_CANCEL_ORDER,
        BUTTON_CONTACT_MANAGER,
        BUTTON_FAQ,
        BUTTON_CANCEL,
        BUTTON_MENU_DONE,
    }
)

IN_PROGRESS_STATES = frozenset(
    {
        OrderStates.choosing_address.state,
        OrderStates.confirm_saved_profile.state,
        OrderStates.address_clarification.state,
        OrderStates.phone.state,
    }
)


class NotMenuButtonFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        if not message.text:
            return True
        return message.text not in MENU_BUTTONS


class PendingOrderFilter(BaseFilter):
    async def __call__(
        self,
        message: Message,
        db: Database,
        state: FSMContext,
    ) -> bool:
        if not message.from_user:
            return False
        current = await state.get_state()
        if current in IN_PROGRESS_STATES:
            return False
        order = await db.get_pending_order_for_guest(message.from_user.id)
        return order is not None


class ActiveConversationFilter(BaseFilter):
    """Гость уже общается с сотрудником — заказ или обращение."""

    async def __call__(self, message: Message, db: Database) -> bool:
        if not message.from_user:
            return False
        order = await db.get_active_order_for_guest(message.from_user.id)
        if order and order.topic_id:
            return True
        support = await db.get_open_support_chat(message.from_user.id)
        return support is not None
