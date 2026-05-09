import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN
from services import engine, Base
from handlers import router

bot = Bot(token=BOT_TOKEN)  # глобальный объект

async def main():
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    dp.include_router(router)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await bot.delete_webhook(drop_pending_updates=True)
    print("Specter Search запущен")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
