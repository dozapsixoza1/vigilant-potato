import re, os, json, tempfile, asyncio, patoolib, pandas as pd, aiofiles
from datetime import datetime
from pathlib import Path
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, ChatJoinRequest, ReplyKeyboardMarkup, KeyboardButton, ContentType
from aiogram.filters import Command
from sqlalchemy import text
from services import *
from keyboards import *
from config import OWNER_ID, SUBSCRIBE_CHAT_ID, PLANS
from main import bot  # импортируем глобальный bot

router = Router()

main_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🔍 Поиск"), KeyboardButton(text="💳 Подписка")],
              [KeyboardButton(text="ℹ️ Помощь")]],
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
            "🕵️ Specter Search — владелец.\nАдмин-панель: /admin или «админ».\nВыдача подписки: ID дни.\nЗагрузка баз: просто киньте файл.",
            reply_markup=main_kb
        )
    if not await is_subscribed_to_channel(bot, message.from_user.id, SUBSCRIBE_CHAT_ID):
        return await message.answer("🔒 Подпишитесь на канал.", reply_markup=subscribe_keyboard())
    await message.answer("🕵️ Specter Search. Примеры запросов...", reply_markup=main_kb)

# ---------- ПОМОЩЬ ----------
@router.message(Command("help"))
@router.message(F.text.lower() == "ℹ️ помощь")
async def cmd_help(message: Message):
    await message.answer("📖 Specter Search — поиск по открытым данным.", reply_markup=main_kb)

# ---------- АДМИНКА ----------
@router.message(Command("admin"))
@router.message(F.text.lower().in_(["админ", "admin", "🔒 админ-панель"]))
async def admin_panel(message: Message):
    if message.from_user.id != OWNER_ID:
        return await message.answer("⛔ Доступ запрещён.")
    await message.answer("🔒 Админ-панель", reply_markup=admin_menu())

# ---------- КНОПКИ АДМИНКИ ----------
@router.callback_query(F.data == "admin_stats")
async def admin_stats(call: CallbackQuery):
    async with async_session() as sess:
        from sqlalchemy import func
        total_users = await sess.scalar(select(func.count(User.id)))
        active_subs = await sess.scalar(select(func.count(User.id)).where(User.subscribed_until > datetime.utcnow()))
    await call.message.edit_text(f"📊 Всего: {total_users}, активных: {active_subs}", reply_markup=admin_menu())

@router.callback_query(F.data == "admin_subs")
async def admin_subs(call: CallbackQuery):
    await call.message.edit_text("Введите ID и дни (например, 7950038145 30)", reply_markup=admin_menu())

@router.callback_query(F.data == "admin_upload")
async def admin_upload_prompt(call: CallbackQuery):
    await call.message.edit_text("📁 Просто пришлите любой файл.", reply_markup=admin_menu())

@router.callback_query(F.data == "admin_add")
async def admin_add(call: CallbackQuery):
    await call.message.edit_text("👷 В разработке.", reply_markup=admin_menu())

@router.callback_query(F.data == "close")
async def close_callback(call: CallbackQuery):
    await call.message.delete()

# ---------- ВЫДАЧА ПОДПИСКИ ВЛАДЕЛЬЦЕМ ----------
@router.message(F.from_user.id == OWNER_ID, F.text.regexp(r'^\d+\s+\d+$'))
async def give_sub_by_text(message: Message):
    parts = message.text.split()
    await add_subscription(int(parts[0]), int(parts[1]))
    await message.answer(f"✅ Подписка на {parts[1]} дней выдана {parts[0]}.")

# ---------- ЗАГРУЗКА ФАЙЛОВ ----------
@router.message(F.from_user.id == OWNER_ID, F.content_type.in_({
    ContentType.DOCUMENT, ContentType.PHOTO, ContentType.VIDEO,
    ContentType.AUDIO, ContentType.ANIMATION, ContentType.STICKER,
    ContentType.VOICE, ContentType.VIDEO_NOTE
}))
async def handle_admin_files(message: Message, bot: Bot):
    if message.media_group_id:
        if not hasattr(router, '_mg_ids'):
            router._mg_ids = set()
        if message.media_group_id in router._mg_ids:
            return
        router._mg_ids.add(message.media_group_id)

    file_name = "unknown.file"
    file_id = None
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name or file_name
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_name = f"photo.jpg"
    # ... другие типы аналогично (кратко)
    if file_id:
        save_dir = Path(tempfile.gettempdir()) / "specter_uploads"
        save_dir.mkdir(exist_ok=True)
        save_path = save_dir / f"{message.message_id}_{file_name}"
        await bot.download(file_id, destination=save_path)
        asyncio.create_task(_process_and_notify(save_path, file_name, message.chat.id, bot))

async def _process_and_notify(file_path: Path, original_name: str, chat_id: int, bot: Bot):
    try:
        count = await _import_file(file_path)
        await bot.send_message(chat_id, f"✅ {original_name}: +{count} записей.")
    except Exception as e:
        await bot.send_message(chat_id, f"❌ Ошибка импорта {original_name}: {e}")

# ... здесь функции _import_file, _import_csv, _import_json как в предыдущем ответе ...

# ---------- ПЛАНЫ И ПОКУПКА ----------
@router.message(Command("plans"))
@router.message(F.text == "💳 Подписка")
async def show_plans(message: Message):
    await message.answer("💳 Тарифы:", reply_markup=plans_keyboard())

@router.callback_query(F.data.startswith("buy_"))
async def buy_subscription(call: CallbackQuery):
    days = int(call.data.split("_")[1])
    amount, desc = PLANS[days]
    user_id = call.from_user.id
    try:
        invoice_url = await create_crypto_invoice(amount, user_id)
        await call.message.answer(
            f"💸 Для оплаты **{desc}** переведите {amount} USDT:\n{invoice_url}\n\nОплата проверяется автоматически."
        )
    except Exception as e:
        await call.message.answer(f"⚠️ Ошибка создания счёта: {e}")
    await call.answer()

# ---------- ПОИСК ----------
@router.message(F.text)
async def handle_search(message: Message, bot: Bot):
    user_id = message.from_user.id
    # Владелец без ограничений (но не служебные слова)
    if user_id == OWNER_ID:
        q = message.text.strip()
        if q.lower() in ["админ", "admin", "🔒 админ-панель", "🔍 поиск", "💳 подписка", "ℹ️ помощь"]:
            return
        result = await process_search_query(q, user_id)
        return await message.answer(result or "ℹ️ Ничего не найдено.")

    user = await get_user(user_id)
    if not user:
        return await message.answer("❌ Нажмите /start")
    if not await is_subscribed_to_channel(bot, user_id, SUBSCRIBE_CHAT_ID):
        return await message.answer("🔒 Нужна подписка на канал.", reply_markup=subscribe_keyboard())
    if user.subscribed_until < datetime.utcnow():
        return await message.answer("💳 Подписка истекла. /plans", reply_markup=plans_keyboard())

    today = datetime.utcnow().date()
    if user.last_request_date.date() != today:
        user.daily_requests = 2
        user.last_request_date = datetime.utcnow()
        async with async_session() as sess:
            sess.add(user)
            await sess.commit()
    if user.daily_requests <= 0:
        return await message.answer("❌ Лимит на сегодня исчерпан.")

    query = message.text.strip()
    if query in ["🔍 Поиск", "💳 Подписка", "ℹ️ Помощь"]:
        return
    result = await process_search_query(query, user_id)
    user.daily_requests -= 1
    async with async_session() as sess:
        sess.add(user)
        await sess.commit()
    await message.answer(result or "ℹ️ Ничего не найдено.")

# Функции process_search_query, search_phone, search_username ... (как ранее)
