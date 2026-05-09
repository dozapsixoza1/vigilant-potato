from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import SUBSCRIBE_LINK

def subscribe_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔔 Подписаться", url=SUBSCRIBE_LINK)],
        [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub")]
    ])

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👤 Выдать подписку", callback_data="admin_give_sub")],
        [InlineKeyboardButton(text="📁 Загрузить базу", callback_data="admin_upload")],
        [InlineKeyboardButton(text="🔙 Закрыть", callback_data="close")]
    ])

def plans_keyboard():
    buttons = [
        [InlineKeyboardButton(text="⚡ 7 дней (10 USDT)", callback_data="buy_7")],
        [InlineKeyboardButton(text="🔥 30 дней (25 USDT)", callback_data="buy_30")],
        [InlineKeyboardButton(text="💎 Навсегда (100 USDT)", callback_data="buy_9999")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def close_button():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="close")]
    ])
