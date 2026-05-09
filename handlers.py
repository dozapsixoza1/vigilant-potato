import re
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, ChatJoinRequest, ReplyKeyboardMarkup, KeyboardButton, ContentType
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
    if message.from_user.id == OWNER_ID:
        return await message.answer(
            "🕵️ **Specter Search** — владелец.\n"
            "Админ-панель: /admin или слово «админ».\n"
            "Выдача подписки: просто напишите `ID дни`.\n"
            "Загрузка базы: просто пришлите любой файл.",
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
        "💳 Тарифы: /plans или кнопка «Подписка»",
        reply_markup=main_kb
    )

# ---------- ПОМОЩЬ ----------
@router.message(Command("help"))
@router.message(F.text.lower() == "ℹ️ помощь")
async def cmd_help(message: Message):
    await message.answer(
        "📖 **Specter Search** — поиск по открытым данным.\n\n"
        "Отправьте номер, @username, email, госномер, VIN или другие данные.\n"
        "Для подписки: /plans или кнопка «💳 Подписка».\n"
        "Постоянная клавиатура внизу экрана.",
        reply_markup=main_kb
    )

# ---------- АДМИНКА ----------
@router.message(Command("admin"))
@router.message(F.text.lower().in_(["админ", "admin", "🔒 админ-панель"]))
async def admin_panel(message: Message):
    if message.from_user.id != OWNER_ID:
        return await message.answer("⛔ Доступ запрещён.")
    await message.answer("🔒 Админ-панель Specter Search", reply_markup=admin_menu())

# ---------- ОБРАБОТЧИКИ КНОПОК АДМИНКИ ----------
@router.callback_query(F.data == "admin_stats")
async def admin_stats(call: CallbackQuery):
    async with async_session() as sess:
        from sqlalchemy import func
        total_users = await sess.scalar(select(func.count(User.id)))
        active_subs = await sess.scalar(select(func.count(User.id)).where(User.subscribed_until > datetime.utcnow()))
    await call.message.edit_text(
        f"📊 Статистика:\n👥 Всего пользователей: {total_users}\n✅ Активных подписок: {active_subs}",
        reply_markup=admin_menu()
    )

@router.callback_query(F.data == "admin_subs")
async def admin_subs(call: CallbackQuery):
    await call.message.edit_text(
        "Введите Telegram ID пользователя и количество дней через пробел.\n"
        "Пример: `7950038145 30`\n"
        "Или просто напишите это сообщением, если вы владелец.",
        reply_markup=admin_menu()
    )

@router.callback_query(F.data == "admin_upload")
async def admin_upload_prompt(call: CallbackQuery):
    await call.message.edit_text(
        "📁 Просто перешлите любой файл (базу) сюда.\n"
        "Поддерживаются все форматы: .csv, .json, .7z, .rar, .zip, .001 и т.д.\n"
        "Бот примет и запустит импорт.",
        reply_markup=admin_menu()
    )

@router.callback_query(F.data == "admin_add")
async def admin_add(call: CallbackQuery):
    await call.message.edit_text(
        "Чтобы добавить админа, отправьте его Telegram ID.\nПока команда в разработке.",
        reply_markup=admin_menu()
    )

@router.callback_query(F.data == "close")
async def close_callback(call: CallbackQuery):
    await call.message.delete()

# ---------- ВЫДАЧА ПОДПИСКИ ВЛАДЕЛЬЦУ (просто ID дни) ----------
@router.message(F.from_user.id == OWNER_ID, F.text.regexp(r'^\d+\s+\d+$'))
async def give_subscription_by_text(message: Message):
    parts = message.text.strip().split()
    target_id = int(parts[0])
    days = int(parts[1])
    await add_subscription(target_id, days)
    await message.answer(f"✅ Подписка на {days} дней выдана пользователю {target_id}.")

# ---------- ЗАГРУЗКА ЛЮБЫХ ФАЙЛОВ (владелец) – ЛОВИТ ВСЁ НЕТЕКСТОВОЕ ----------
@router.message(F.from_user.id == OWNER_ID, ~F.text)
async def handle_admin_any_file(message: Message, bot: Bot):
    # Определяем тип контента и сохраняем
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name or "документ"
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_name = "фото.jpg"
    elif message.video:
        file_id = message.video.file_id
        file_name = message.video.file_name or "видео.mp4"
    elif message.audio:
        file_id = message.audio.file_id
        file_name = message.audio.file_name or "аудио.mp3"
    elif message.animation:
        file_id = message.animation.file_id
        file_name = message.animation.file_name or "анимация.gif"
    elif message.sticker:
        file_id = message.sticker.file_id
        file_name = "стикер.webp"
    elif message.voice:
        file_id = message.voice.file_id
        file_name = "голосовое.ogg"
    elif message.video_note:
        file_id = message.video_note.file_id
        file_name = "видеокружок.mp4"
    else:
        return await message.answer("❌ Неподдерживаемый тип вложения.")
    
    await bot.download(file_id, destination=f"/tmp/{file_name}")
    await message.answer(f"✅ Файл «{file_name}» получен. Импорт запущен (заглушка).")

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

# ---------- ПОИСК ----------
@router.message(F.text)
async def handle_search(message: Message, bot: Bot):
    user_id = message.from_user.id
    # Владелец без ограничений
    if user_id == OWNER_ID:
        query = message.text.strip()
        if query.lower() in ["админ", "admin", "🔒 админ-панель", "🔍 поиск", "💳 подписка", "ℹ️ помощь"]:
            return
        result = await process_search_query(query, user_id)
        return await message.answer(result or "ℹ️ Ничего не найдено.")

    # Обычный пользователь
    user = await get_user(user_id)
    if not user:
        return await message.answer("❌ Сначала нажмите /start")

    if not await is_subscribed_to_channel(bot, user_id, SUBSCRIBE_CHAT_ID):
        return await message.answer("🔒 Необходима подписка на канал.", reply_markup=subscribe_keyboard())

    if user.subscribed_until < datetime.utcnow():
        return await message.answer("💳 Подписка истекла. Продлите: /plans", reply_markup=plans_keyboard())

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
    if query in ["🔍 Поиск", "💳 Подписка", "ℹ️ Помощь"]:
        return

    result = await process_search_query(query, user_id)
    user.daily_requests -= 1
    async with async_session() as sess:
        sess.add(user)
        await sess.commit()
    await message.answer(result or "ℹ️ Ничего не найдено. Проверьте формат.")

# ---------- ФУНКЦИИ ПОИСКА ----------
async def process_search_query(query: str, user_id: int):
    if re.fullmatch(r"\+?\d{11}", query):
        return await search_phone(query)
    elif re.fullmatch(r"@\w+", query):
        return await search_username(query.lstrip("@"))
    elif re.fullmatch(r"[\w\.-]+@[\w\.-]+", query):
        return await search_email(query)
    elif re.fullmatch(r"^[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+", query):
        return await search_fio(query)
    elif re.fullmatch(r"^[A-ZА-Я]\d{3}[A-ZА-Я]{2}\d{2,3}$", query.upper()):
        return await search_car_plate(query.upper())
    return None

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
