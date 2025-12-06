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
from utils.logger import setup_logger

logger = setup_logger(__name__)

router = Router()


class PhotoProcessing(StatesGroup):
    """Состояния обработки фотографий."""
    waiting_second_photo = State()


@router.message(F.photo, PhotoProcessing.waiting_second_photo)
async def handle_second_photo(message: Message, state: FSMContext):
    """Обработчик второй фотографии."""
    # Проверяем согласие с правилами
    user_data = await state.get_data()
    agreed = user_data.get("terms_agreed", False)
    
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
        first_telegram_url = f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{first_photo_file_path}"
        second_telegram_url = f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file.file_path}"
        
        await process_two_photos(message, first_telegram_url, second_telegram_url, temp_path)
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
    # Проверяем согласие с правилами
    user_data = await state.get_data()
    agreed = user_data.get("terms_agreed", False)
    
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
        
        # Обрабатываем одну фотографию
        await process_single_photo(message, photo)
            
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


async def process_single_photo(message: Message, photo):
    """Обрабатывает одну фотографию."""
    user_id = message.from_user.id
    image_service = ImageService()
    grok_service = GrokService()
    token_service = TokenService()
    temp_path = None
    
    # Проверяем доступность генерации
    if not await token_service.can_generate(user_id):
        balance = await token_service.get_balance(user_id)
        await message.answer(
            f"❌ У вас недостаточно токенов для генерации видео.\n\n"
            f"💰 Ваш баланс: {balance['tokens']} токенов\n\n"
            f"💳 Купить токены: /buy\n"
            f"📊 Проверить баланс: /tokens"
        )
        return
    
    try:
        # Отправляем сообщение о начале обработки
        status_msg = await message.answer("⏳ Обрабатываю фотографию...")
        
        # Скачиваем фото
        file = await message.bot.get_file(photo.file_id)
        file_data = await message.bot.download_file(file.file_path)
        file_bytes = file_data.read()
        
        # Валидация
        try:
            temp_path = await image_service.save_temp(file_bytes, file.file_path)
            image_service.validate_image(temp_path, len(file_bytes))
        except ImageValidationError as e:
            await status_msg.edit_text(f"❌ {str(e)}")
            return
        
        # Получаем публичный URL от Telegram
        telegram_file_url = f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{file.file_path}"
        logger.info(f"Using Telegram file URL: {telegram_file_url}")
        
        # Определяем количество людей
        await status_msg.edit_text("🔍 Определяю количество людей на фото...")
        num_people = await grok_service.detect_people(temp_path)
        logger.info(f"Detected {num_people} people in photo")
        
        # Генерируем видео используя публичный URL Telegram
        await status_msg.edit_text("🎬 Генерирую видео...")
        video_data = await grok_service.generate_kissing_video([telegram_file_url], num_people)
        
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
        elif balance['free_available']:
            caption += "\n✅ У вас есть бесплатная генерация"
        else:
            caption += "\n💳 Купить токены: /buy"
        
        await message.answer_video(video_file, caption=caption)
        
        # Очистка
        image_service.cleanup(temp_path)
        image_service.cleanup(video_path)
        await status_msg.delete()
        
    except GrokAPIError as e:
        logger.error(f"Grok API error: {e}", exc_info=True)
        error_msg = (
            "❌ Ошибка при генерации видео через Grok API.\n\n"
            f"Детали: {str(e)[:200]}\n\n"
            "Попробуйте позже или отправьте другую фотографию."
        )
        if 'status_msg' in locals():
            await status_msg.edit_text(error_msg)
        else:
            await message.answer(error_msg)
    except Exception as e:
        logger.error(f"Error processing single photo: {e}", exc_info=True)
        logger.error(f"Error type: {type(e).__name__}")
        await message.answer(
            f"❌ Произошла ошибка при обработке.\n"
            f"Тип ошибки: {type(e).__name__}\n"
            f"Сообщение: {str(e)[:200]}"
        )
    finally:
        if temp_path and temp_path.exists():
            image_service.cleanup(temp_path)


async def process_two_photos(message: Message, first_telegram_url: str, second_telegram_url: str, second_photo_path: Path):
    """Обрабатывает две фотографии."""
    user_id = message.from_user.id
    image_service = ImageService()
    grok_service = GrokService()
    token_service = TokenService()
    
    # Проверяем доступность генерации
    if not await token_service.can_generate(user_id):
        balance = await token_service.get_balance(user_id)
        await message.answer(
            f"❌ У вас недостаточно токенов для генерации видео.\n\n"
            f"💰 Ваш баланс: {balance['tokens']} токенов\n\n"
            f"💳 Купить токены: /buy\n"
            f"📊 Проверить баланс: /tokens"
        )
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
        elif balance['free_available']:
            caption += "\n✅ У вас есть бесплатная генерация"
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
