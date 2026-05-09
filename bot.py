import asyncio, re, os, json, tempfile, time
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp, aiofiles, pandas as pd, patoolib
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (Message, CallbackQuery, ChatJoinRequest,
                           ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup,
                           InlineKeyboardButton, ContentType)
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import (Column, Integer, BigInteger, String, DateTime,
                        Boolean, JSON, select, text, func)

# ---------- КОНФИГ ----------
BOT_TOKEN = "8665761164:AAGNz-2uXVXi59Cya-A0B48gOI1jAQpZ46M"
CRYPTO_BOT_API = "579759:AABlv5LTi5FE60Yqql1CgwgMooW9sxHYj50"
OWNER_ID = 7950038145
SUBSCRIBE_CHAT_ID = -1003844270710  # замени на реальный ID канала!!
SUBSCRIBE_LINK = "https://t.me/+6x1CHb3JxP5kZjU6"
DB_URL = "postgresql+asyncpg://neondb_owner:npg_Wpbx9jtKPl6y@ep-lucky-butterfly-apy8s59f-pooler.c-7.us-east-1.aws.neon.tech/neondb"

PLANS = {
    7: (10, "7 дней"),
    30: (25, "30 дней"),
    9999: (100, "Навсегда")
}

# ---------- БАЗА ДАННЫХ ----------
engine = create_async_engine(DB_URL)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, unique=True, index=True)
    username = Column(String)
    subscribed_until = Column(DateTime, default=datetime.utcnow)
    daily_requests = Column(Integer, default=2)
    last_request_date = Column(DateTime, default=datetime.utcnow)
    is_admin = Column(Boolean, default=False)

class Leak(Base):
    __tablename__ = "leaks"
    id = Column(Integer, primary_key=True)
    phone = Column(String, index=True)
    email = Column(String, index=True)
    fio = Column(String, index=True)
    username = Column(String, index=True)
    car_plate = Column(String, index=True)
    vin = Column(String, index=True)
    data = Column(JSON)

async def get_user(uid: int):
    async with async_session() as sess:
        return (await sess.execute(select(User).where(User.user_id == uid))).scalar()

async def create_user_if_not(uid: int, uname: str):
    async with async_session() as sess:
        user = await get_user(uid)
        if not user:
            user = User(user_id=uid, username=uname)
            sess.add(user)
            await sess.commit()
        return user

async def add_subscription(uid: int, days: int):
    async with async_session() as sess:
        user = (await sess.execute(select(User).where(User.user_id == uid))).scalar()
        if not user:
            return
        now = datetime.utcnow()
        if user.subscribed_until < now:
            user.subscribed_until = now + timedelta(days=days)
        else:
            user.subscribed_until += timedelta(days=days)
        await sess.commit()

async def is_subscribed_to_channel(bot, uid, chat_id):
    try:
        member = await bot.get_chat_member(chat_id, uid)
        return member.status not in ("left", "kicked")
    except:
        return False

async def create_crypto_invoice(amount_usdt: float, uid: int):
    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_API}
    payload = {
        "asset": "USDT",
        "amount": str(amount_usdt),
        "description": f"Подписка Specter Search для user {uid}",
        "payload": str({"user_id": uid}),
        "allow_comments": False
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            data = await resp.json()
            if data.get("ok"):
                return data["result"]["bot_invoice_url"]
            else:
                raise Exception(f"Crypto Bot error: {data.get('error', 'unknown')}")

# ---------- КЛАВИАТУРЫ ----------
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔍 Поиск"), KeyboardButton(text="💳 Подписка")],
        [KeyboardButton(text="ℹ️ Помощь")]
    ],
    resize_keyboard=True
)

def subscribe_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔔 Подписаться", url=SUBSCRIBE_LINK)],
        [InlineKeyboardButton(text="✅ Проверить", callback_data="check_sub")]
    ])

def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👤 Управление подписками", callback_data="admin_subs")],
        [InlineKeyboardButton(text="📁 Загрузить базу", callback_data="admin_upload")],
        [InlineKeyboardButton(text="➕ Добавить админа", callback_data="admin_add")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="close")]
    ])

def plans_keyboard():
    buttons = [
        [InlineKeyboardButton(text="⚡ 7 дней (10 USDT)", callback_data="buy_7")],
        [InlineKeyboardButton(text="🔥 30 дней (25 USDT)", callback_data="buy_30")],
        [InlineKeyboardButton(text="💎 Навсегда (100 USDT)", callback_data="buy_9999")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ---------- БОТ ----------
router = Router()
bot = Bot(token=BOT_TOKEN)

# Автоодобрение заявок
@router.chat_join_request(F.chat.id == SUBSCRIBE_CHAT_ID)
async def handle_join_request(update: ChatJoinRequest):
    await update.approve()

@router.message(Command("start"))
async def cmd_start(message: Message):
    uid = message.from_user.id
    await create_user_if_not(uid, message.from_user.username)
    if uid == OWNER_ID:
        return await message.answer(
            "🕵️ Specter Search | Администратор\n"
            "/admin — панель управления\n"
            "Выдача подписки: ID дни (например, 7950038145 30)\n"
            "Загрузка баз: просто киньте файл.",
            reply_markup=main_kb
        )
    if not await is_subscribed_to_channel(bot, uid, SUBSCRIBE_CHAT_ID):
        return await message.answer("🔒 Подпишитесь на канал.", reply_markup=subscribe_keyboard())
    await message.answer(
        "🕵️ Specter Search\n"
        "📞 79991234567\n"
        "👤 @username\n"
        "✉️ mail@example.com\n"
        "🚘 А123БВ177\n\n"
        "💳 Тарифы: /plans или кнопка «Подписка»",
        reply_markup=main_kb
    )

@router.message(Command("help"))
@router.message(F.text.lower() == "ℹ️ помощь")
async def cmd_help(message: Message):
    await message.answer("ℹ️ Specter Search — поиск по открытым данным.", reply_markup=main_kb)

# Админка
@router.message(Command("admin"))
@router.message(F.text.lower().in_(["админ", "admin", "🔒 админ-панель"]))
async def admin_panel(message: Message):
    if message.from_user.id != OWNER_ID:
        return await message.answer("⛔ Доступ запрещён.")
    await message.answer("🔒 Админ-панель", reply_markup=admin_menu())

@router.callback_query(F.data == "admin_stats")
async def admin_stats(call: CallbackQuery):
    async with async_session() as sess:
        total = await sess.scalar(select(func.count(User.id)))
        active = await sess.scalar(select(func.count(User.id)).where(User.subscribed_until > datetime.utcnow()))
    await call.message.edit_text(f"📊 Пользователей: {total}\n✅ Активных подписок: {active}", reply_markup=admin_menu())

@router.callback_query(F.data == "admin_subs")
async def admin_subs(call: CallbackQuery):
    await call.message.edit_text("Введите ID и дни (например, 7950038145 30)", reply_markup=admin_menu())

@router.callback_query(F.data == "admin_upload")
async def admin_upload_prompt(call: CallbackQuery):
    await call.message.edit_text("📁 Пришлите любой файл (csv, json, архив). Бот импортирует.", reply_markup=admin_menu())

@router.callback_query(F.data == "admin_add")
async def admin_add(call: CallbackQuery):
    await call.message.edit_text("👷 Добавление админов — заглушка.", reply_markup=admin_menu())

@router.callback_query(F.data == "close")
async def close_callback(call: CallbackQuery):
    await call.message.delete()

@router.callback_query(F.data == "check_sub")
async def check_sub(call: CallbackQuery):
    if await is_subscribed_to_channel(bot, call.from_user.id, SUBSCRIBE_CHAT_ID):
        await call.message.edit_text("✅ Подписка активна!")
    else:
        await call.answer("❌ Вы не подписаны.", show_alert=True)

# Выдача подписки владельцем
@router.message(F.from_user.id == OWNER_ID, F.text.regexp(r'^\d+\s+\d+$'))
async def give_sub(message: Message):
    parts = message.text.split()
    await add_subscription(int(parts[0]), int(parts[1]))
    await message.answer(f"✅ Подписка на {parts[1]} дн. выдана {parts[0]}.")

# Загрузка любых файлов
@router.message(F.from_user.id == OWNER_ID, F.content_type.in_({
    ContentType.DOCUMENT, ContentType.PHOTO, ContentType.VIDEO,
    ContentType.AUDIO, ContentType.ANIMATION, ContentType.STICKER,
    ContentType.VOICE, ContentType.VIDEO_NOTE
}))
async def handle_admin_files(message: Message):
    # защита от альбомов
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
        file_name = "photo.jpg"
    elif message.video:
        file_id = message.video.file_id
        file_name = message.video.file_name or "video.mp4"
    elif message.audio:
        file_id = message.audio.file_id
        file_name = message.audio.file_name or "audio.mp3"
    elif message.animation:
        file_id = message.animation.file_id
        file_name = message.animation.file_name or "animation.gif"
    else:
        return

    save_dir = Path(tempfile.gettempdir()) / "specter_uploads"
    save_dir.mkdir(exist_ok=True)
    save_path = save_dir / f"{message.message_id}_{file_name}"
    await bot.download(file_id, destination=save_path)

    asyncio.create_task(_process_file(save_path, file_name, message.chat.id))

async def _process_file(file_path: Path, original_name: str, chat_id: int):
    try:
        count = await _import_file(file_path)
        await bot.send_message(chat_id, f"✅ {original_name}: +{count} записей")
    except Exception as e:
        await bot.send_message(chat_id, f"❌ Ошибка в {original_name}: {e}")

async def _import_file(file_path: Path) -> int:
    ext = file_path.suffix.lower()
    total = 0
    if ext == ".csv":
        return await _import_csv(file_path)
    elif ext == ".json":
        return await _import_json(file_path)
    elif ext in (".zip", ".rar", ".7z", ".gz", ".tar", ".tgz", ".xz", ".001"):
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                patoolib.extract_archive(str(file_path), outdir=tmpdir, interactive=False)
            except Exception as e:
                raise RuntimeError(f"Ошибка распаковки: {e}")
            for root, dirs, files in os.walk(tmpdir):
                for f in files:
                    inner = Path(root) / f
                    if inner.suffix == ".csv":
                        total += await _import_csv(inner)
                    elif inner.suffix == ".json":
                        total += await _import_json(inner)
    else:
        # пробуем как csv
        total = await _import_csv(file_path)
        if total == 0:
            total = await _import_json(file_path)
        if total == 0:
            raise RuntimeError("Неподдерживаемый формат")
    return total

async def _import_csv(path: Path) -> int:
    try:
        async with aiofiles.open(path, encoding='utf-8') as f:
            content = await f.read()
    except UnicodeDecodeError:
        async with aiofiles.open(path, encoding='cp1251') as f:
            content = await f.read()
    import io
    df = pd.read_csv(io.StringIO(content), dtype=str).fillna("")
    return await _insert_df(df)

async def _import_json(path: Path) -> int:
    async with aiofiles.open(path, encoding='utf-8') as f:
        content = await f.read()
    data = json.loads(content)
    if isinstance(data, list):
        df = pd.DataFrame(data).fillna("")
    elif isinstance(data, dict):
        df = pd.DataFrame([data]).fillna("")
    else:
        return 0
    return await _insert_df(df)

async def _insert_df(df: pd.DataFrame) -> int:
    # маппинг полей
    cols = ['phone','email','fio','username','car_plate','vin']
    for c in cols:
        if c not in df.columns:
            df[c] = None
    # дополнительные поля кладём в data
    extra_cols = [c for c in df.columns if c not in cols]
    if extra_cols:
        df['data'] = df[extra_cols].to_dict(orient='records')
    else:
        df['data'] = None
    records = df[cols + ['data']].to_dict(orient='records')
    async with async_session() as sess:
        for rec in records:
            rec['data'] = json.dumps(rec['data']) if rec['data'] else None
            sess.add(Leak(**rec))
        await sess.commit()
    return len(records)

# Планы и покупка
@router.message(Command("plans"))
@router.message(F.text == "💳 Подписка")
async def show_plans(message: Message):
    await message.answer("💳 Тарифы:", reply_markup=plans_keyboard())

@router.callback_query(F.data.startswith("buy_"))
async def buy_subscription(call: CallbackQuery):
    days = int(call.data.split("_")[1])
    amount, desc = PLANS[days]
    uid = call.from_user.id
    try:
        invoice_url = await create_crypto_invoice(amount, uid)
        await call.message.answer(
            f"💸 Оплатите {amount} USDT за **{desc}**:\n{invoice_url}"
        )
    except Exception as e:
        await call.message.answer(f"⚠️ Ошибка создания счёта: {e}")
    await call.answer()

# Поиск
@router.message(F.text)
async def handle_search(message: Message):
    uid = message.from_user.id
    # владелец без ограничений
    if uid == OWNER_ID:
        q = message.text.strip()
        if q.lower() in ["админ", "admin", "🔒 админ-панель", "🔍 поиск", "💳 подписка", "ℹ️ помощь"]:
            return
        result = await process_search(q, uid)
        return await message.answer(result or "ℹ️ Ничего не найдено.")

    user = await get_user(uid)
    if not user:
        return await message.answer("❌ Нажмите /start")
    if not await is_subscribed_to_channel(bot, uid, SUBSCRIBE_CHAT_ID):
        return await message.answer("🔒 Подпишитесь на канал.", reply_markup=subscribe_keyboard())
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

    q = message.text.strip()
    if q in ["🔍 Поиск", "💳 Подписка", "ℹ️ Помощь"]:
        return
    result = await process_search(q, uid)
    user.daily_requests -= 1
    async with async_session() as sess:
        sess.add(user)
        await sess.commit()
    await message.answer(result or "ℹ️ Ничего не найдено.")

async def process_search(query: str, uid: int) -> str | None:
    if re.fullmatch(r"\+?\d{11}", query):
        async with async_session() as sess:
            res = await sess.execute(
                text("SELECT fio, email, username FROM leaks WHERE phone = :p LIMIT 3"), {"p": query}
            )
            rows = res.fetchall()
            if rows:
                return "📞 Результаты:\n" + "\n".join(
                    f"• {r[0]} | {r[1]} | @{r[2]}" for r in rows
                )
    elif re.fullmatch(r"@\w+", query):
        uname = query.lstrip("@")
        async with async_session() as sess:
            res = await sess.execute(
                text("SELECT phone, email, fio FROM leaks WHERE username = :u LIMIT 3"), {"u": uname}
            )
            rows = res.fetchall()
            if rows:
                return "👤 @" + uname + ":\n" + "\n".join(
                    f"• {r[0]} | {r[1]} | {r[2]}" for r in rows
                )
    return None

async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await bot.delete_webhook(drop_pending_updates=True)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    print("Specter Search готов")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
