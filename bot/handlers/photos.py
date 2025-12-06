"""Обработчики фотографий."""
import asyncio
import aiofiles
from pathlib import Path
from typing import Dict, Optional
from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.config import settings
from services.image_service import ImageService, ImageValidationError
from services.grok_service import GrokService, GrokAPIError
from services.token_service import TokenService
from services.terms_service import TermsService
from services.task_queue import get_task_queue, VideoGenerationTask, TaskStatus
from utils.logger import setup_logger

logger = setup_logger(__name__)

router = Router()
terms_service = TermsService()
task_queue = get_task_queue()


class PhotoProcessing(StatesGroup):
    """Состояния обработки фотографий."""
    waiting_second_photo = State()


@router.message(F.photo, PhotoProcessing.waiting_second_photo)
async def handle_second_photo(message: Message, state: FSMContext):
    """Обработчик второй фотографии."""
    # Проверяем согласие с правилами через БД
    user_id = message.from_user.id
    agreed = await terms_service.has_agreed_to_current_terms(user_id)
    
    if not agreed:
        await message.answer(
            "❌ Для использования бота необходимо согласиться с правилами.\n\n"
            "Используйте команду /start для просмотра и принятия правил."
        )
        await state.clear()
        return
    
    image_service = ImageService()
    temp_path = None
    
    try:
        data = await state.get_data()
        first_photo_path_str = data.get("first_photo_path")
        
        first_photo_file_path = data.get("first_photo_file_path")
        
        if not first_photo_file_path:
            await message.answer("❌ Первая фотография не найдена. Начните заново.")
            await state.clear()
            return
        
        # Сохраняем вторую фотографию для валидации
        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        file_data = await message.bot.download_file(file.file_path)
        file_bytes = file_data.read()
        
        temp_path = await image_service.save_temp(file_bytes, file.file_path)
        
        # Формируем публичные URL для обеих фотографий
        # Важно: URL должен быть правильно сформирован и доступен для внешних сервисов
        import urllib.parse
        encoded_first_path = urllib.parse.quote(first_photo_file_path, safe='/')
        encoded_second_path = urllib.parse.quote(file.file_path, safe='/')
        first_telegram_url = f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{encoded_first_path}"
        second_telegram_url = f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{encoded_second_path}"
        logger.info(f"First photo URL: {first_telegram_url}")
        logger.info(f"Second photo URL: {second_telegram_url}")
        
        await add_two_photos_to_queue(message, first_telegram_url, second_telegram_url, temp_path)
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error handling second photo: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при обработке второй фотографии. "
            "Попробуйте отправить фотографии заново."
        )
        await state.clear()
    finally:
        if temp_path and temp_path.exists():
            image_service.cleanup(temp_path)


@router.message(F.photo)
async def handle_photo(message: Message, state: FSMContext):
    """Обработчик входящих фотографий (первая или единственная)."""
    # Проверяем согласие с правилами через БД
    user_id = message.from_user.id
    agreed = await terms_service.has_agreed_to_current_terms(user_id)
    
    if not agreed:
        await message.answer(
            "❌ Для использования бота необходимо согласиться с правилами.\n\n"
            "Используйте команду /start для просмотра и принятия правил."
        )
        return
    
    image_service = ImageService()
    temp_path = None
    
    try:
        photo = message.photo[-1]  # Берем фото наибольшего размера
        
        # Проверяем состояние
        current_state = await state.get_state()
        if current_state == PhotoProcessing.waiting_second_photo.state:
            # Сохраняем первую фотографию для ожидания второй
            file = await message.bot.get_file(photo.file_id)
            file_data = await message.bot.download_file(file.file_path)
            file_bytes = file_data.read()
            
            temp_path = await image_service.save_temp(file_bytes, file.file_path)
            await state.update_data(
                first_photo_path=str(temp_path),
                first_photo_file_path=file.file_path  # Сохраняем file_path для формирования URL
            )
            
            await message.answer(
                "✅ Первая фотография получена!\n"
                "📸 Теперь отправьте вторую фотографию."
            )
            return
        
        # Добавляем задачу в очередь вместо прямой обработки
        await add_single_photo_to_queue(message, photo)
            
    except Exception as e:
        logger.error(f"Error handling photo: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при обработке фотографии. "
            "Попробуйте отправить фотографию заново."
        )
    finally:
        # Не очищаем temp_path здесь, если ждем вторую фотографию
        current_state = await state.get_state()
        if current_state != PhotoProcessing.waiting_second_photo.state:
            if temp_path and temp_path.exists():
                image_service.cleanup(temp_path)


async def add_single_photo_to_queue(message: Message, photo):
    """Добавляет задачу обработки одной фотографии в очередь."""
    user_id = message.from_user.id
    token_service = TokenService()
    image_service = ImageService()
    
    # Проверяем доступность генерации
    if not await token_service.can_generate(user_id):
        balance = await token_service.get_balance(user_id)
        error_msg = (
            f"❌ У вас недостаточно ресурсов для генерации видео.\n\n"
            f"💰 Токенов: {balance['tokens']}\n"
        )
        promo_generations = balance.get('promo_generations', 0) or 0
        if promo_generations > 0:
            error_msg += f"🎁 Промокодных генераций: {promo_generations}\n"
        if balance['free_remaining'] > 0:
            error_msg += f"✅ Осталось бесплатных генераций: {balance['free_remaining']}\n\n"
        else:
            error_msg += f"❌ Бесплатные генерации использованы ({balance['free_used']}/{token_service.FREE_GENERATIONS_LIMIT})\n\n"
        error_msg += (
            f"💳 Купить токены: /buy\n"
            f"📊 Проверить баланс: /tokens"
        )
        await message.answer(error_msg)
        return
    
    try:
        # Скачиваем фото заранее (до добавления в очередь)
        file = await message.bot.get_file(photo.file_id)
        file_data = await message.bot.download_file(file.file_path)
        file_bytes = file_data.read()
        
        # Валидация перед добавлением в очередь
        temp_path = await image_service.save_temp(file_bytes, file.file_path)
        image_service.validate_image(temp_path, len(file_bytes))
        
        # Получаем позицию в очереди
        queue_size = await task_queue.get_queue_size()
        position = queue_size + 1
        
        # Отправляем сообщение о добавлении в очередь
        if position > task_queue.max_workers:
            status_msg = await message.answer(
                f"📋 Задача добавлена в очередь\n\n"
                f"⏳ Ваша позиция: {position}\n"
                f"🔄 Обрабатывается: {task_queue.max_workers} задач одновременно\n\n"
                f"Ожидайте, обработка начнется автоматически..."
            )
        else:
            status_msg = await message.answer("⏳ Обрабатываю фотографию...")
        
        # Импортируем процессор
        from bot.handlers.photo_processors import process_single_photo_task
        
        # Добавляем задачу в очередь
        task = await task_queue.add_task(
            user_id=user_id,
            message=message,
            task_type="single",
            photo_data={
                'photo': photo,
                'file_path': file.file_path,
                'file_bytes': file_bytes,
                'temp_path': temp_path
            },
            processor=process_single_photo_task
        )
        
        # Сохраняем ссылку на сообщение статуса в задаче
        task.status_message = status_msg
        
        # Запускаем задачу обновления позиции в очереди
        asyncio.create_task(update_queue_position(task, status_msg))
        
    except ImageValidationError as e:
        await message.answer(f"❌ {str(e)}")
    except Exception as e:
        logger.error(f"Error adding single photo to queue: {e}", exc_info=True)
        await message.answer(
            f"❌ Произошла ошибка при добавлении задачи в очередь.\n"
            f"Сообщение: {str(e)[:200]}"
        )


async def update_queue_position(task: VideoGenerationTask, status_msg):
    """Обновляет позицию задачи в очереди до начала обработки."""
    from services.task_queue import TaskStatus
    
    while task.status == TaskStatus.PENDING:
        try:
            position = await task_queue.get_queue_position(task.task_id)
            
            if position > 0:
                await status_msg.edit_text(
                    f"📋 Задача в очереди\n\n"
                    f"⏳ Ваша позиция: {position}\n"
                    f"🔄 Обрабатывается: {task_queue.max_workers} задач одновременно\n\n"
                    f"Ожидайте, обработка начнется автоматически..."
                )
            
            # Проверяем каждые 3 секунды
            await asyncio.sleep(3)
            
        except Exception as e:
            logger.error(f"Error updating queue position: {e}")
            break


async def add_two_photos_to_queue(message: Message, first_telegram_url: str, second_telegram_url: str, second_photo_path: Path):
    """Добавляет задачу обработки двух фотографий в очередь."""
    user_id = message.from_user.id
    token_service = TokenService()
    image_service = ImageService()
    
    # Проверяем доступность генерации
    if not await token_service.can_generate(user_id):
        balance = await token_service.get_balance(user_id)
        error_msg = (
            f"❌ У вас недостаточно ресурсов для генерации видео.\n\n"
            f"💰 Токенов: {balance['tokens']}\n"
        )
        promo_generations = balance.get('promo_generations', 0) or 0
        if promo_generations > 0:
            error_msg += f"🎁 Промокодных генераций: {promo_generations}\n"
        if balance['free_remaining'] > 0:
            error_msg += f"✅ Осталось бесплатных генераций: {balance['free_remaining']}\n\n"
        else:
            error_msg += f"❌ Бесплатные генерации использованы ({balance['free_used']}/{token_service.FREE_GENERATIONS_LIMIT})\n\n"
        error_msg += (
            f"💳 Купить токены: /buy\n"
            f"📊 Проверить баланс: /tokens"
        )
        await message.answer(error_msg)
        return
    
    try:
        # Получаем позицию в очереди
        queue_size = await task_queue.get_queue_size()
        position = queue_size + 1
        
        # Отправляем сообщение о добавлении в очередь
        if position > task_queue.max_workers:
            status_msg = await message.answer(
                f"📋 Задача добавлена в очередь\n\n"
                f"⏳ Ваша позиция: {position}\n"
                f"🔄 Обрабатывается: {task_queue.max_workers} задач одновременно\n\n"
                f"Ожидайте, обработка начнется автоматически..."
            )
        else:
            status_msg = await message.answer("⏳ Обрабатываю две фотографии...")
        
        # Импортируем процессор
        from bot.handlers.photo_processors import process_two_photos_task
        
        # Добавляем задачу в очередь
        task = await task_queue.add_task(
            user_id=user_id,
            message=message,
            task_type="two",
            photo_data={
                'first_telegram_url': first_telegram_url,
                'second_telegram_url': second_telegram_url,
                'second_photo_path': second_photo_path
            },
            processor=process_two_photos_task
        )
        
        # Сохраняем ссылку на сообщение статуса в задаче
        task.status_message = status_msg
        
        # Запускаем задачу обновления позиции в очереди
        asyncio.create_task(update_queue_position(task, status_msg))
        
    except Exception as e:
        logger.error(f"Error adding two photos to queue: {e}", exc_info=True)
        await message.answer(
            f"❌ Произошла ошибка при добавлении задачи в очередь.\n"
            f"Сообщение: {str(e)[:200]}"
        )


async def process_two_photos(message: Message, first_telegram_url: str, second_telegram_url: str, second_photo_path: Path):
    """Обрабатывает две фотографии."""
    user_id = message.from_user.id
    image_service = ImageService()
    grok_service = GrokService()
    token_service = TokenService()
    
    # Проверяем доступность генерации
    if not await token_service.can_generate(user_id):
        balance = await token_service.get_balance(user_id)
        error_msg = (
            f"❌ У вас недостаточно ресурсов для генерации видео.\n\n"
            f"💰 Токенов: {balance['tokens']}\n"
        )
        promo_generations = balance.get('promo_generations', 0) or 0
        if promo_generations > 0:
            error_msg += f"🎁 Промокодных генераций: {promo_generations}\n"
        if balance['free_remaining'] > 0:
            error_msg += f"✅ Осталось бесплатных генераций: {balance['free_remaining']}\n\n"
        else:
            error_msg += f"❌ Бесплатные генерации использованы ({balance['free_used']}/{token_service.FREE_GENERATIONS_LIMIT})\n\n"
        error_msg += (
            f"💳 Купить токены: /buy\n"
            f"📊 Проверить баланс: /tokens"
        )
        await message.answer(error_msg)
        return
    
    temp_paths = []
    
    try:
        # Отправляем сообщение о начале обработки
        status_msg = await message.answer("⏳ Обрабатываю две фотографии...")
        
        # Валидация второй фотографии
        try:
            with open(second_photo_path, 'rb') as f:
                file_size = len(f.read())
            image_service.validate_image(second_photo_path, file_size)
            temp_paths.append(second_photo_path)
        except ImageValidationError as e:
            await status_msg.edit_text(f"❌ Ошибка во второй фотографии: {str(e)}")
            return
        
        # Получаем публичные URL от Telegram для обеих фотографий
        logger.info(f"Using Telegram file URLs - First: {first_telegram_url}, Second: {second_telegram_url}")
        
        # Генерируем видео используя публичный URL Telegram
        # Используем только вторую фотографию, так как API поддерживает только одно изображение
        # В промпте упоминаем обе фотографии для контекста
        await status_msg.edit_text("🎬 Генерирую видео из двух фотографий...")
        video_data = await grok_service.generate_kissing_video([second_telegram_url])
        
        # Сохраняем видео
        video_path = Path(settings.storage_path) / "videos" / f"{user_id}_{int(asyncio.get_event_loop().time())}.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(video_path, 'wb') as f:
            await f.write(video_data)
        
        # Списываем токен или бесплатную генерацию
        await token_service.use_generation(user_id)
        balance = await token_service.get_balance(user_id)
        
        # Отправляем видео
        await status_msg.edit_text("✅ Видео готово! Отправляю...")
        video_file = FSInputFile(video_path)
        
        # Добавляем информацию о балансе в подпись
        caption = "🎬 Ваше видео готово!"
        if balance['tokens'] > 0:
            caption += f"\n💰 Осталось токенов: {balance['tokens']}"
        elif balance.get('promo_generations', 0) > 0:
            caption += f"\n🎁 Промокодных генераций: {balance['promo_generations']}"
        elif balance['free_remaining'] > 0:
            caption += f"\n✅ Осталось бесплатных генераций: {balance['free_remaining']}"
        else:
            caption += "\n💳 Купить токены: /buy"
        
        await message.answer_video(video_file, caption=caption)
        
        # Очистка
        for path in temp_paths:
            image_service.cleanup(path)
        image_service.cleanup(video_path)
        await status_msg.delete()
        
    except GrokAPIError as e:
        logger.error(f"Grok API error: {e}")
        if 'status_msg' in locals():
            await status_msg.edit_text(
                "❌ Ошибка при генерации видео. "
                "Попробуйте позже или отправьте другие фотографии."
            )
        else:
            await message.answer(
                "❌ Ошибка при генерации видео. "
                "Попробуйте позже или отправьте другие фотографии."
            )
    except Exception as e:
        logger.error(f"Error processing two photos: {e}", exc_info=True)
        await message.answer(
            "❌ Произошла ошибка при обработке. Попробуйте еще раз."
        )
    finally:
        for path in temp_paths:
            if path and path.exists():
                image_service.cleanup(path)


@router.message(F.text.in_(["Две фотографии", "2 фото", "/two"]))
async def cmd_two_photos(message: Message, state: FSMContext):
    """Команда для обработки двух фотографий."""
    await message.answer(
        "📸 Режим обработки двух фотографий активирован.\n\n"
        "Отправьте первую фотографию, затем вторую.\n"
        "У вас есть 5 минут на отправку второй фотографии."
    )
    await state.set_state(PhotoProcessing.waiting_second_photo)
