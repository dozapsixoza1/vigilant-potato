import asyncio
import os
import tempfile
import aiofiles
from collections import defaultdict
from pathlib import Path
from aiogram.types import ContentType
from sqlalchemy import insert

# Глобальные переменные для контроля групп медиа
_media_group_tracker = {}
_media_group_lock = asyncio.Lock()
_processing_tasks = set()

# -------------------------------------------------------------
# УНИВЕРСАЛЬНЫЙ ПРИЁМ ФАЙЛОВ (владелец)
# -------------------------------------------------------------
@router.message(F.from_user.id == OWNER_ID, F.content_type.in_({
    ContentType.DOCUMENT, ContentType.PHOTO, ContentType.VIDEO,
    ContentType.AUDIO, ContentType.ANIMATION, ContentType.STICKER,
    ContentType.VOICE, ContentType.VIDEO_NOTE
}))
async def handle_admin_files(message: Message, bot: Bot):
    # Альбомы: обрабатываем только первый файл, чтобы не дублировать ответы
    if message.media_group_id:
        async with _media_group_lock:
            if message.media_group_id in _media_group_tracker:
                return
            _media_group_tracker[message.media_group_id] = True
            asyncio.create_task(_release_media_group(message.media_group_id))

    # Определяем реальное имя файла
    file_name = "unknown.file"
    file_id = None
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name or file_name
    elif message.photo:
        file_id = message.photo[-1].file_id
        file_name = f"photo_{message.photo[-1].file_unique_id}.jpg"
    elif message.video:
        file_id = message.video.file_id
        file_name = message.video.file_name or f"video_{message.video.file_unique_id}.mp4"
    elif message.audio:
        file_id = message.audio.file_id
        file_name = message.audio.file_name or f"audio_{message.audio.file_unique_id}.mp3"
    elif message.animation:
        file_id = message.animation.file_id
        file_name = message.animation.file_name or f"animation_{message.animation.file_unique_id}.gif"
    elif message.sticker:
        file_id = message.sticker.file_id
        file_name = f"sticker_{message.sticker.file_unique_id}.webp"
    elif message.voice:
        file_id = message.voice.file_id
        file_name = f"voice_{message.voice.file_unique_id}.ogg"
    elif message.video_note:
        file_id = message.video_note.file_id
        file_name = f"video_note_{message.video_note.file_unique_id}.mp4"

    if not file_id:
        return

    # Создаём временную папку для всей группы (если ещё не создана)
    if message.media_group_id:
        group_dir = Path(tempfile.gettempdir()) / f"specter_{message.media_group_id}"
        group_dir.mkdir(exist_ok=True)
        save_path = group_dir / file_name
    else:
        save_path = Path(tempfile.gettempdir()) / f"specter_{message.message_id}_{file_name}"

    await message.answer(f"📥 Загрузка файла: {file_name} ...")
    await bot.download(file_id, destination=save_path)
    await message.answer(f"✅ Файл «{file_name}» сохранён, начинаю импорт.")

    # Запускаем фоновую обработку
    task = asyncio.create_task(process_file(str(save_path), message.chat.id, message.media_group_id))
    _processing_tasks.add(task)
    task.add_done_callback(lambda t: _processing_tasks.discard(t))

# -------------------------------------------------------------
# ОБРАБОТКА ОДНОГО ФАЙЛА (рекурсивная распаковка + импорт)
# -------------------------------------------------------------
async def process_file(file_path: str, chat_id: int, media_group_id: str | None):
    from bot_instance import bot   # нужно передать объект бота; проще сохранить в global или импортировать
    # (мы можем сохранить bot глобально при старте, либо передать чат_id и бота через аргумент)
    # Упростим: бот доступен глобально как router.parent_router... сложно. Просто передадим bot через partial.
    # Поэтому сейчас сделаем заглушку, а реальный импорт выполним в той же таске с прямым обращением к engine.
    # Но нам нужен bot для отправки сообщений. Решение: сохраним bot в global в main.py.
    # Для этого примера я оставлю отправку сообщений через asyncio.get_event_loop() и обращение к bot по имени.
    pass
