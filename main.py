import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis
from config import BOT_TOKEN, REDIS_URL
from services import engine, Base
from handlers import router

async def main():
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    storage = RedisStorage(redis=redis)
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=storage)
    dp.include_router(router)

    # Создаём таблицы в базе
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await bot.delete_webhook(drop_pending_updates=True)
    print("Specter Search запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
