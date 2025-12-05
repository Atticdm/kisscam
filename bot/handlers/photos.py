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
from utils.logger import setup_logger

logger = setup_logger(__name__)

router = Router()


class PhotoProcessing(StatesGroup):
    """Состояния обработки фотографий."""
    waiting_second_photo = State()


@router.message(F.photo, PhotoProcessing.waiting_second_photo)
async def handle_second_photo(message: Message, state: FSMContext):
    """Обработчик второй фотографии."""
    image_service = ImageService()
    temp_path = None
    
    try:
        data = await state.get_data()
        first_photo_path_str = data.get("first_photo_path")
        
        if not first_photo_path_str:
            await message.answer("❌ Первая фотография не найдена. Начните заново.")
            await state.clear()
            return
        
        first_photo_path = Path(first_photo_path_str)
        
        if not first_photo_path.exists():
            await message.answer("❌ Первая фотография устарела. Начните заново.")
            await state.clear()
            return
        
            # Сохраняем вторую фотографию
            photo = message.photo[-1]
            file = await message.bot.get_file(photo.file_id)
            file_data = await message.bot.download_file(file.file_path)
            file_bytes = file_data.read()
        
        temp_path = await image_service.save_temp(file_bytes, file.file_path)
        
        await process_two_photos(message, first_photo_path, photo)
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
            await state.update_data(first_photo_path=str(temp_path))
            
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
    temp_path = None
    
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
        
        # Определяем количество людей
        await status_msg.edit_text("🔍 Определяю количество людей на фото...")
        num_people = await grok_service.detect_people(temp_path)
        logger.info(f"Detected {num_people} people in photo")
        
        # Генерируем видео
        await status_msg.edit_text("🎬 Генерирую видео...")
        video_data = await grok_service.generate_kissing_video([temp_path], num_people)
        
        # Сохраняем видео
        video_path = Path(settings.storage_path) / "videos" / f"{user_id}_{int(asyncio.get_event_loop().time())}.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(video_path, 'wb') as f:
            await f.write(video_data)
        
        # Отправляем видео
        await status_msg.edit_text("✅ Видео готово! Отправляю...")
        video_file = FSInputFile(video_path)
        await message.answer_video(video_file, caption="🎬 Ваше видео готово!")
        
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


async def process_two_photos(message: Message, first_photo_path: Path, second_photo):
    """Обрабатывает две фотографии."""
    user_id = message.from_user.id
    image_service = ImageService()
    grok_service = GrokService()
    
    temp_paths = []
    second_photo_path = None
    
    try:
        # Отправляем сообщение о начале обработки
        status_msg = await message.answer("⏳ Обрабатываю две фотографии...")
        
        # Скачиваем вторую фотографию
        file = await message.bot.get_file(second_photo.file_id)
        file_data = await message.bot.download_file(file.file_path)
        file_bytes = file_data.read()
        
        # Валидация второй фотографии
        try:
            second_photo_path = await image_service.save_temp(file_bytes, file.file_path)
            image_service.validate_image(second_photo_path, len(file_bytes))
            temp_paths.append(second_photo_path)
        except ImageValidationError as e:
            await status_msg.edit_text(f"❌ Ошибка во второй фотографии: {str(e)}")
            image_service.cleanup(first_photo_path)
            return
        
        temp_paths.append(first_photo_path)
        
        # Генерируем видео
        await status_msg.edit_text("🎬 Генерирую видео из двух фотографий...")
        video_data = await grok_service.generate_kissing_video(temp_paths)
        
        # Сохраняем видео
        video_path = Path(settings.storage_path) / "videos" / f"{user_id}_{int(asyncio.get_event_loop().time())}.mp4"
        video_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(video_path, 'wb') as f:
            await f.write(video_data)
        
        # Отправляем видео
        await status_msg.edit_text("✅ Видео готово! Отправляю...")
        video_file = FSInputFile(video_path)
        await message.answer_video(video_file, caption="🎬 Ваше видео готово!")
        
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
        if first_photo_path.exists():
            image_service.cleanup(first_photo_path)


@router.message(F.text.in_(["Две фотографии", "2 фото", "/two"]))
async def cmd_two_photos(message: Message, state: FSMContext):
    """Команда для обработки двух фотографий."""
    await message.answer(
        "📸 Режим обработки двух фотографий активирован.\n\n"
        "Отправьте первую фотографию, затем вторую.\n"
        "У вас есть 5 минут на отправку второй фотографии."
    )
    await state.set_state(PhotoProcessing.waiting_second_photo)
