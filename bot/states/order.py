from aiogram.fsm.state import State, StatesGroup


class OrderStates(StatesGroup):
    choosing_address = State()
    confirm_saved_profile = State()
    address_clarification = State()
    phone = State()
    order_text = State()


class AdminStates(StatesGroup):
    choosing_menu_address = State()
    collecting_menu_photos = State()
    choosing_clear_menu_address = State()
