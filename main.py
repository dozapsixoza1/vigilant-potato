import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN
from services import engine, Base
from handlers import router
from sqlalchemy import text

async def main():
    storage = MemoryStorage()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=storage)
    dp.include_router(router)

    # Сбрасываем старые сессии Telegram
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.session.close()

    # Исправление типа user_id: удаляем старую таблицу, если она с ошибкой
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE IF EXISTS users CASCADE"))
        await conn.run_sync(Base.metadata.create_all)

    bot = Bot(token=BOT_TOKEN)  # свежая сессия

    print("Specter Search запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
