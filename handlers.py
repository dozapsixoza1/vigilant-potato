import asyncio
import tempfile
from pathlib import Path
from aiogram.types import ContentType
from sqlalchemy import insert
import pandas as pd
import json
import patoolib
import aiofiles

# ------------- ГЛОБАЛЬНЫЙ ТРЕКЕР АЛЬБОМОВ -------------
_media_group_lock = asyncio.Lock()
_media_group_tracker = set()

# ------------- ХЕНДЛЕР ФАЙЛОВ -------------
@router.message(F.from_user.id == OWNER_ID, F.content_type.in_({
    ContentType.DOCUMENT, ContentType.PHOTO, ContentType.VIDEO,
    ContentType.AUDIO, ContentType.ANIMATION, ContentType.STICKER,
    ContentType.VOICE, ContentType.VIDEO_NOTE
}))
async def handle_admin_files(message: Message, bot: Bot):
    if message.media_group_id:
        async with _media_group_lock:
            if message.media_group_id in _media_group_tracker:
                return
            _media_group_tracker.add(message.media_group_id)
            # Не удаляем из трекера, чтобы повторно не обрабатывать эту группу никогда (память не утечёт)

    # Определяем имя и скачиваем
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
    else:
        return

    save_dir = Path(tempfile.gettempdir()) / "specter_uploads"
    save_dir.mkdir(exist_ok=True)
    save_path = save_dir / f"{message.message_id}_{file_name}"
    await bot.download(file_id, destination=save_path)

    # Запуск обработки в фоне
    asyncio.create_task(_process_and_notify(save_path, file_name, message.chat.id, bot))

# ------------- ФОН ВЫЗОВ ОБРАБОТКИ -------------
async def _process_and_notify(file_path: Path, original_name: str, chat_id: int, bot: Bot):
    try:
        count = await _import_file(file_path)
        await bot.send_message(chat_id, f"✅ Импорт завершён: {original_name} → +{count} записей в базу.")
    except Exception as e:
        await bot.send_message(chat_id, f"❌ Ошибка импорта {original_name}: {e}")

# ------------- РЕАЛЬНЫЙ ИМПОРТЕР -------------
async def _import_file(file_path: Path) -> int:
    """Обрабатывает файл (csv, json, архив) и возвращает количество добавленных записей."""
    ext = file_path.suffix.lower()
    total = 0

    # Если текстовый CSV/JSON
    if ext == ".csv":
        total = await _import_csv(file_path)
    elif ext == ".json":
        total = await _import_json(file_path)
    elif ext in (".zip", ".rar", ".7z", ".gz", ".bz2", ".tar", ".tgz", ".xz", ".001"):
        # Это архив, распаковываем и обрабатываем содержимое
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                patoolib.extract_archive(str(file_path), outdir=tmpdir, interactive=False)
            except Exception as e:
                raise RuntimeError(f"Ошибка распаковки: {e}")
            # Проходим по всем файлам внутри
            for root, dirs, files in os.walk(tmpdir):
                for f in files:
                    inner_path = Path(root) / f
                    inner_ext = inner_path.suffix.lower()
                    if inner_ext == ".csv":
                        total += await _import_csv(inner_path)
                    elif inner_ext == ".json":
                        total += await _import_json(inner_path)
                    # остальные пропускаем
    else:
        # Пробуем всё равно как CSV/JSON на всякий случай
        total = await _import_csv(file_path) or await _import_json(file_path)
        if total == 0:
            raise RuntimeError("Неподдерживаемый формат или пустой файл")
    return total

async def _import_csv(path: Path) -> int:
    """Асинхронный импорт CSV в таблицу leaks"""
    try:
        async with aiofiles.open(path, mode='r', encoding='utf-8') as f:
            content = await f.read()
    except UnicodeDecodeError:
        # Пробуем другую кодировку
        async with aiofiles.open(path, mode='r', encoding='cp1251') as f:
            content = await f.read()
    import io
    df = pd.read_csv(io.StringIO(content), dtype=str).fillna("")
    return await _insert_dataframe(df)

async def _import_json(path: Path) -> int:
    async with aiofiles.open(path, mode='r', encoding='utf-8') as f:
        content = await f.read()
    data = json.loads(content)
    if isinstance(data, list):
        df = pd.DataFrame(data).fillna("")
    elif isinstance(data, dict):
        # если это словарь ключ-значение, можно конвертировать в одну строку
        df = pd.DataFrame([data]).fillna("")
    else:
        return 0
    return await _insert_dataframe(df)

async def _insert_dataframe(df: pd.DataFrame) -> int:
    # Приводим колонки к стандартным, если есть
    col_map = {
        'phone': 'phone', 'email': 'email', 'fio': 'fio',
        'username': 'username', 'car_plate': 'car_plate', 'vin': 'vin',
        'data': 'data'
    }
    # оставляем только нужные колонки
    available_cols = [c for c in col_map.keys() if c in df.columns]
    df = df[available_cols].copy()
    # Преобразуем data в JSON, если есть другие колонки
    if 'data' not in df.columns:
        extra_cols = [c for c in df.columns if c not in col_map.values()]
        if extra_cols:
            df['data'] = df[extra_cols].to_dict(orient='records')
            df = df[col_map.keys()].copy()
    # Если нет нужных колонок, добавляем пустые
    for col in col_map:
        if col not in df.columns:
            df[col] = None

    records = df.to_dict(orient='records')
    async with async_session() as sess:
        for rec in records:
            # Убираем все None, преобразуем data в JSON строку
            rec = {k: (json.dumps(v) if k == 'data' and isinstance(v, (dict, list)) else v) for k, v in rec.items()}
            sess.add(Leak(**rec))
        await sess.commit()
    return len(records)
