BOT_TOKEN = "8665761164:AAGNz-2uXVXi59Cya-A0B48gOI1jAQpZ46M"
CRYPTO_BOT_API = "579759:AABlv5LTi5FE60Yqql1CgwgMooW9sxHYj50"
OWNER_ID = 7950038145

# ID приватного канала с заявками (узнай через @getmyid_bot, переслав пригласительную ссылку)
SUBSCRIBE_CHAT_ID = -1003844270710  # !!! СЮДА ВСТАВИТЬ РЕАЛЬНЫЙ ID !!!
SUBSCRIBE_LINK = "https://t.me/+6x1CHb3JxP5kZjU6"

# База данных Neon (вставил твою)
DB_URL = "postgresql+asyncpg://neondb_owner:npg_Wpbx9jtKPl6y@ep-lucky-butterfly-apy8s59f-pooler.c-7.us-east-1.aws.neon.tech/neondb"

# Подключение к Redis (локальный)
REDIS_URL = "redis://localhost:6379"

# Тарифы: ключ – days, значение: (цена USDT, description)
PLANS = {
    7: (10, "7 дней"),
    30: (25, "30 дней"),
    9999: (100, "Навсегда")   # 9999 условно
}
