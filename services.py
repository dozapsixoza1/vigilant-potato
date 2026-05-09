from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Boolean, JSON, Text, select
from datetime import datetime, timedelta
import aiohttp
from config import DB_URL, CRYPTO_BOT_API

engine = create_async_engine(DB_URL)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

# ---------- МОДЕЛИ ----------
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)                    # автоинкремент
    user_id = Column(BigInteger, unique=True, index=True)     # Telegram ID
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
    data = Column(JSON)       # любые дополнительные данные

# ---------- ФУНКЦИИ РАБОТЫ С ПОЛЬЗОВАТЕЛЯМИ ----------
async def get_user(telegram_user_id: int):
    """Ищет пользователя по Telegram user_id"""
    async with async_session() as sess:
        stmt = select(User).where(User.user_id == telegram_user_id)
        result = await sess.execute(stmt)
        return result.scalar()

async def create_user_if_not(telegram_user_id: int, username: str):
    """Создаёт пользователя, если его ещё нет в базе"""
    async with async_session() as sess:
        stmt = select(User).where(User.user_id == telegram_user_id)
        result = await sess.execute(stmt)
        user = result.scalar()
        if not user:
            user = User(user_id=telegram_user_id, username=username)
            sess.add(user)
            await sess.commit()
        return user

async def add_subscription(telegram_user_id: int, days: int):
    async with async_session() as sess:
        stmt = select(User).where(User.user_id == telegram_user_id)
        result = await sess.execute(stmt)
        user = result.scalar()
        if not user:
            return
        now = datetime.utcnow()
        if user.subscribed_until < now:
            user.subscribed_until = now + timedelta(days=days)
        else:
            user.subscribed_until += timedelta(days=days)
        await sess.commit()

# ---------- ПРОВЕРКА ПОДПИСКИ НА КАНАЛ ----------
async def is_subscribed_to_channel(bot, user_id, chat_id):
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status not in ("left", "kicked")
    except:
        return False

# ---------- ИНТЕГРАЦИЯ CRYPTO BOT (исправлено) ----------
async def create_crypto_invoice(amount_usdt: float, telegram_user_id: int):
    url = "https://pay.crypt.bot/api/createInvoice"
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_API}
    payload = {
        "asset": "USDT",
        "amount": str(amount_usdt),
        "description": f"Подписка Specter Search для user {telegram_user_id}",
        "payload": str({"user_id": telegram_user_id}),   # обязательно строка!
        "allow_comments": False
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=payload) as resp:
            data = await resp.json()
            if data.get("ok"):
                return data["result"]["bot_invoice_url"]
            else:
                raise Exception(f"Crypto Bot: {data.get('error', 'неизвестная ошибка')}")
