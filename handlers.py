import re
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, ChatJoinRequest, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command
from sqlalchemy import text
from services import *
from keyboards import *
from config import OWNER_ID, SUBSCRIBE_CHAT_ID, PLANS

router = Router()

# ---------- ПОСТОЯННАЯ КЛАВИАТУРА ----------
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔍 Поиск"), KeyboardButton(text="💳 Подписка")],
        [KeyboardButton(text="ℹ️ Помощь")]
    ],
    resize_keyboard=True
)

# ---------- АВТООДОБРЕНИЕ ЗАЯВОК ----------
@router.chat_join_request(F.chat.id == SUBSCRIBE_CHAT_ID)
async def handle_join_request(update: ChatJoinRequest):
    await update.approve()

# ---------- СТАРТ ----------
@router.message(Command("start"))
async def cmd_start(message: Message, bot: Bot):
    user = await create_user_if_not(message.from_user.id, message.from_user.username)
    # Владельцу сразу доступ без проверок
    if message.from_user.id == OWNER_ID:
        return await message.answer(
            "🕵️ **Specter Search** — владелец.\nАдмин-панель: /admin",
            reply_markup=main_kb
        )
    if not await is_subscribed_to_channel(bot, message.from_user.id, SUBSCRIBE_CHAT_ID):
        return await message.answer(
            "🔒 Для доступа необходимо подписаться на наш канал.",
            reply_markup=subscribe_keyboard()
        )
    await message.answer(
        "🕵️ **Specter Search** приветствует.\n\n"
        "📞 79999688666\n"
        "👤 @username\n"
        "✉️ name@mail.ru\n"
        "🚘 В395ОК199\n\n"
        "💳 Тарифы: /plans",
        reply_markup=main_kb
    )

# ---------- ПОМОЩЬ ----------
@router.message(Command("help"))
@router.message(F.text.lower() == "ℹ️ помощь")
async def cmd_help(message: Message):
    await message.answer(
        "📖 **Specter Search** — поиск по открытым данным.\n\n"
        "Отправьте номер, @username, email, госномер, VIN или другие данные.\n"
        "Для подписки: /plans\n"
        "Постоянная клавиатура внизу экрана.",
        reply_markup=main_kb
    )

# ---------- АДМИНКА (только владелец, без проверок) ----------
@router.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    await message.answer("🔒 Админ-панель Specter Search", reply_markup=admin_menu())

# ---------- ПЛАНЫ И ПОКУПКА ----------
@router.message(Command("plans"))
@router.message(F.text == "💳 Подписка")
async def show_plans(message: Message):
    await message.answer("💳 Выберите тарифный план:", reply_markup=plans_keyboard())

@router.callback_query(F.data.startswith("buy_"))
async def buy_subscription(call: CallbackQuery):
    days = int(call.data.split("_")[1])
    amount, desc = PLANS[days]
    user_id = call.from_user.id
    try:
        invoice_url = await create_crypto_invoice(amount, user_id)
        await call.message.answer(
            f"💸 Для оплаты **{desc}** переведите {amount} USDT:\n{invoice_url}\n\n"
            "Оплата проверяется автоматически."
        )
    except Exception as e:
        await call.message.answer(f"⚠️ Ошибка создания счёта: {e}")
    await call.answer()

# ---------- ПОИСК (проверки есть, кроме админа) ----------
@router.message(F.text)
@router.message(F.text == "🔍 Поиск")
async def handle_search(message: Message, bot: Bot):
    user_id = message.from_user.id

    # Владелец — без ограничений
    if user_id == OWNER_ID:
        query = message.text.strip()
        if query == "🔍 Поиск":
            return await message.answer("Введите данные для поиска (номер, @username и т.д.)")
        result = await process_search_query(query, user_id)
        return await message.answer(result or "ℹ️ Ничего не найдено.")

    # Обычный пользователь
    user = await get_user(user_id)
    if not user:
        return await message.answer("❌ Сначала нажмите /start")

    # Проверка подписки на канал
    if not await is_subscribed_to_channel(bot, user_id, SUBSCRIBE_CHAT_ID):
        return await message.answer("🔒 Необходима подписка на канал.", reply_markup=subscribe_keyboard())

    # Проверка платной подписки
    if user.subscribed_until < datetime.utcnow():
        return await message.answer("💳 Подписка истекла. Продлите: /plans", reply_markup=plans_keyboard())

    # Дневной лимит
    today = datetime.utcnow().date()
    if user.last_request_date.date() != today:
        user.daily_requests = 2
        user.last_request_date = datetime.utcnow()
        async with async_session() as sess:
            sess.add(user)
            await sess.commit()
    if user.daily_requests <= 0:
        return await message.answer("❌ Дневной лимит запросов исчерпан (2 в день).")

    query = message.text.strip()
    if query == "🔍 Поиск":
        return await message.answer("Введите данные для поиска (номер, @username и т.д.)")

    result = await process_search_query(query, user_id)

    # Списание запроса
    user.daily_requests -= 1
    async with async_session() as sess:
        sess.add(user)
        await sess.commit()

    await message.answer(result or "ℹ️ Ничего не найдено. Проверьте формат.")

# ---------- ОБРАБОТЧИК САМОГО ПОИСКА (без проверок) ----------
async def process_search_query(query: str, user_id: int):
    if re.fullmatch(r"\+?\d{11}", query):               # телефон
        return await search_phone(query)
    elif re.fullmatch(r"@\w+", query):                  # юзернейм
        return await search_username(query.lstrip("@"))
    elif re.fullmatch(r"[\w\.-]+@[\w\.-]+", query):     # email
        return await search_email(query)
    elif re.fullmatch(r"^[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+", query):  # ФИО
        return await search_fio(query)
    elif re.fullmatch(r"^[A-ZА-Я]\d{3}[A-ZА-Я]{2}\d{2,3}$", query.upper()):  # госномер
        return await search_car_plate(query.upper())
    # сюда можно добавить остальные типы
    return None

# ---------- ФУНКЦИИ ПОИСКА (как были) ----------
async def search_phone(phone: str):
    async with async_session() as sess:
        q = text("SELECT fio, email, username, data FROM leaks WHERE phone = :phone LIMIT 3")
        res = await sess.execute(q, {"phone": phone})
        rows = res.fetchall()
    if rows:
        out = "<b>📞 Результат по телефону:</b>\n"
        for r in rows:
            out += f"• ФИО: {r[0]}\n• Email: {r[1]}\n• Логин: @{r[2]}\n• Детали: {r[3]}\n\n"
        return out
    return None

async def search_username(username: str):
    async with async_session() as sess:
        q = text("SELECT phone, email, fio, data FROM leaks WHERE username = :uname LIMIT 3")
        res = await sess.execute(q, {"uname": username})
        rows = res.fetchall()
    if rows:
        out = "<b>🔎 Результат по @username:</b>\n"
        for r in rows:
            out += f"• Телефон: {r[0]}\n• Email: {r[1]}\n• ФИО: {r[2]}\n• Детали: {r[3]}\n\n"
        return out
    return None

async def search_email(email: str):
    async with async_session() as sess:
        q = text("SELECT phone, fio, username, data FROM leaks WHERE email = :email LIMIT 3")
        res = await sess.execute(q, {"email": email})
        rows = res.fetchall()
    if rows:
        out = "<b>✉️ Результат по email:</b>\n"
        for r in rows:
            out += f"• Телефон: {r[0]}\n• ФИО: {r[1]}\n• Логин: @{r[2]}\n• Детали: {r[3]}\n\n"
        return out
    return None

async def search_fio(fio: str):
    return "🔍 Поиск по ФИО пока в разработке"

async def search_car_plate(plate: str):
    return "🚘 Поиск по госномеру пока в разработке"

# ---------- ЗАКРЫТИЕ СООБЩЕНИЙ ----------
@router.callback_query(F.data == "close")
async def close_callback(call: CallbackQuery):
    await call.message.delete()
