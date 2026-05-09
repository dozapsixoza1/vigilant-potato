import re
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, ChatJoinRequest
from aiogram.filters import Command
from sqlalchemy import text
from services import *
from keyboards import *
from config import OWNER_ID, SUBSCRIBE_CHAT_ID, PLANS

router = Router()

# ---------- АВТООДОБРЕНИЕ ЗАЯВОК ----------
@router.chat_join_request(F.chat.id == SUBSCRIBE_CHAT_ID)
async def handle_join_request(update: ChatJoinRequest):
    await update.approve()

# ---------- СТАРТ ----------
@router.message(Command("start"))
async def cmd_start(message: Message, bot: Bot):
    user = await create_user_if_not(message.from_user.id, message.from_user.username)
    # проверка подписки на канал
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
        "🚘 В395ОК199\n"
        "📟 /vu 1234567890\n"
        "🌐 1.1.1.1\n\n"
        "💳 Тарифы: /plans\n"
        "ℹ️ Примеры запросов — просто введите данные."
    )

# проверка подписки по кнопке
@router.callback_query(F.data == "check_sub")
async def check_subscription_callback(call: CallbackQuery, bot: Bot):
    if await is_subscribed_to_channel(bot, call.from_user.id, SUBSCRIBE_CHAT_ID):
        await call.message.edit_text("✅ Подписка активна. Используйте /start")
    else:
        await call.answer("❌ Вы всё ещё не подписаны!", show_alert=True)

# ---------- ПЛАНЫ И ПОКУПКА ----------
@router.message(Command("plans"))
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
            "После оплаты подписка активируется автоматически."
        )
    except Exception as e:
        await call.message.answer("⚠️ Не удалось создать счёт. Попробуйте позже.")
    await call.answer()

# Здесь нужно добавить обработчик webhook'а от Crypto Bot (упрощённо: при получении уведомления вызывается process_payment)
# В рамках этого примера предполагаем, что ты настроил приём webhook отдельно (через Flask или aiohttp)
# и он вызывает функцию activate_subscription(user_id, days)

async def activate_subscription(user_id, days):
    await add_subscription(user_id, days)
    # Отправка уведомления пользователю (бот должен быть запущен)
    # Можно сохранить bot instance глобально
    try:
        await bot.send_message(user_id, f"✅ Подписка активирована на {days} дней!")
    except:
        pass

# ---------- ПОИСК ----------
@router.message(F.text)
async def handle_search(message: Message, bot: Bot):
    user_id = message.from_user.id
    user = await get_user(user_id)
    if not user:
        return await message.answer("❌ Ошибка. Используйте /start")
    if not await is_subscribed_to_channel(bot, user_id, SUBSCRIBE_CHAT_ID):
        return await message.answer("🔒 Необходима подписка на канал.", reply_markup=subscribe_keyboard())

    # Проверка платной подписки
    if user.subscribed_until < datetime.utcnow():
        return await message.answer("💳 Подписка истекла. Продлите: /plans")

    # Проверка дневного лимита
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
    result = None

    # Определяем тип запроса
    if re.fullmatch(r"\+?\d{11}", query):               # телефон
        result = await search_phone(query)
    elif re.fullmatch(r"@\w+", query):                  # юзернейм
        result = await search_username(query.lstrip("@"))
    elif re.fullmatch(r"[\w\.-]+@[\w\.-]+", query):     # email
        result = await search_email(query)
    elif re.fullmatch(r"^[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+", query):  # ФИО
        result = await search_fio(query)
    elif re.fullmatch(r"^[A-ZА-Я]\d{3}[A-ZА-Я]{2}\d{2,3}$", query.upper()):  # госномер
        result = await search_car_plate(query.upper())
    # Можно добавить остальные типы (VIN, VK, IP и т.д.)

    # Списание запроса
    user.daily_requests -= 1
    async with async_session() as sess:
        sess.add(user)
        await sess.commit()

    if result:
        await message.answer(result, parse_mode="HTML")
    else:
        await message.answer("ℹ️ Ничего не найдено. Проверьте формат запроса.")

# ---------- ФУНКЦИИ ПОИСКА ----------
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

# Остальные функции по аналогии
async def search_fio(fio: str):
    return "🔍 Поиск по ФИО пока в разработке"

async def search_car_plate(plate: str):
    return "🚘 Поиск по госномеру пока в разработке"

# ---------- АДМИНКА ----------
@router.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    await message.answer("🔒 Админ-панель Specter Search", reply_markup=admin_menu())

@router.callback_query(F.data == "admin_upload")
async def admin_upload_prompt(call: CallbackQuery):
    await call.message.answer("📁 Перешлите CSV или JSON файл с данными. Бот обработает его в фоне.")

@router.message(F.from_user.id == OWNER_ID, F.document)
async def handle_admin_document(message: Message, bot: Bot):
    file_id = message.document.file_id
    file_path = f"temp_{message.document.file_name}"
    await bot.download(file_id, destination=file_path)
    # В реальности: парсинг и вставка в БД. Здесь просто уведомление.
    await message.answer(f"✅ Файл получен ({message.document.file_size} байт). Запущен импорт.")
    # os.remove(file_path)  # потом удалить

@router.callback_query(F.data == "admin_give_sub")
async def admin_give_sub(call: CallbackQuery):
    await call.message.answer("Введите ID пользователя и количество дней через пробел.\nПример: 123456 30")
    # можно сделать FSM для ожидания ввода

# Закрытие сообщений
@router.callback_query(F.data == "close")
async def close_callback(call: CallbackQuery):
    await call.message.delete()
