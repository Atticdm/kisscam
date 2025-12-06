"""Процессоры для обработки фотографий в очереди задач."""
import asyncio
import aiofiles
from pathlib import Path
from aiogram.types import FSInputFile
from bot.config import settings
from services.image_service import ImageService, ImageValidationError
from services.grok_service import GrokService, GrokAPIError
from services.token_service import TokenService
from services.task_queue import VideoGenerationTask, TaskStatus
from utils.logger import setup_logger

logger = setup_logger(__name__)


async def process_single_photo_task(task: VideoGenerationTask):
    """Обрабатывает задачу генерации видео из одной фотографии."""
    user_id = task.user_id
    message = task.message
    photo_data = task.photo_data
    
    image_service = ImageService()
    grok_service = GrokService()
    token_service = TokenService()
    temp_path = None
    
    try:
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
            task.status = TaskStatus.FAILED
            return
        
        # Обновляем статус - начинаем обработку
        if task.status_message:
            await task.status_message.edit_text("⏳ Обрабатываю фотографию...")
        
        # Получаем данные фотографии
        photo = photo_data.get('photo')
        file_path = photo_data.get('file_path')
        file_bytes = photo_data.get('file_bytes')
        
        if not photo or not file_path:
            await message.answer("❌ Ошибка: данные фотографии не найдены")
            task.status = TaskStatus.FAILED
            return
        
        # Валидация
        try:
            temp_path = await image_service.save_temp(file_bytes, file_path)
            image_service.validate_image(temp_path, len(file_bytes))
        except ImageValidationError as e:
            if task.status_message:
                await task.status_message.edit_text(f"❌ {str(e)}")
            else:
                await message.answer(f"❌ {str(e)}")
            task.status = TaskStatus.FAILED
            return
        
        # Получаем публичный URL от Telegram
        import urllib.parse
        encoded_file_path = urllib.parse.quote(file_path, safe='/')
        telegram_file_url = f"https://api.telegram.org/file/bot{settings.telegram_bot_token}/{encoded_file_path}"
        logger.info(f"Using Telegram file URL: {telegram_file_url}")
        
        # Проверяем на запрещенный контент (дети, военные)
        if task.status_message:
            await task.status_message.edit_text("🔍 Проверяю изображение на запрещенный контент...")
        content_check = await grok_service.check_prohibited_content(temp_path)
        
        if content_check["is_prohibited"]:
            error_reasons = []
            if content_check["has_children"]:
                error_reasons.append("детей")
            if content_check["has_military"]:
                error_reasons.append("военных")
            
            error_msg = (
                f"❌ Генерация видео запрещена.\n\n"
                f"На изображении обнаружен запрещенный контент: {', '.join(error_reasons)}.\n\n"
                f"Мы не генерируем видео с участием детей или военных."
            )
            
            if task.status_message:
                await task.status_message.edit_text(error_msg)
            else:
                await message.answer(error_msg)
            
            task.status = TaskStatus.FAILED
            return
        
        # Определяем количество людей
        if task.status_message:
            await task.status_message.edit_text("🔍 Определяю количество людей на фото...")
        num_people = await grok_service.detect_people(temp_path)
        logger.info(f"Detected {num_people} people in photo")
        
        # Генерируем видео используя публичный URL Telegram
        if task.status_message:
            await task.status_message.edit_text("🎬 Генерирую видео...")
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
        if task.status_message:
            await task.status_message.edit_text("✅ Видео готово! Отправляю...")
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
        image_service.cleanup(temp_path)
        image_service.cleanup(video_path)
        if task.status_message:
            await task.status_message.delete()
        
        task.status = TaskStatus.COMPLETED
        
    except GrokAPIError as e:
        logger.error(f"Grok API error: {e}", exc_info=True)
        error_msg = (
            "❌ Ошибка при генерации видео через Grok API.\n\n"
            f"Детали: {str(e)[:200]}\n\n"
            "Попробуйте позже или отправьте другую фотографию."
        )
        if task.status_message:
            await task.status_message.edit_text(error_msg)
        else:
            await message.answer(error_msg)
        task.status = TaskStatus.FAILED
    except Exception as e:
        logger.error(f"Error processing single photo task: {e}", exc_info=True)
        await message.answer(
            f"❌ Произошла ошибка при обработке.\n"
            f"Тип ошибки: {type(e).__name__}\n"
            f"Сообщение: {str(e)[:200]}"
        )
        task.status = TaskStatus.FAILED
    finally:
        if temp_path and temp_path.exists():
            image_service.cleanup(temp_path)


async def process_two_photos_task(task: VideoGenerationTask):
    """Обрабатывает задачу генерации видео из двух фотографий."""
    user_id = task.user_id
    message = task.message
    photo_data = task.photo_data
    
    image_service = ImageService()
    grok_service = GrokService()
    token_service = TokenService()
    
    try:
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
            task.status = TaskStatus.FAILED
            return
        
        # Получаем данные фотографий
        first_telegram_url = photo_data.get('first_telegram_url')
        second_telegram_url = photo_data.get('second_telegram_url')
        second_photo_path = photo_data.get('second_photo_path')
        
        if not first_telegram_url or not second_telegram_url:
            await message.answer("❌ Ошибка: данные фотографий не найдены")
            task.status = TaskStatus.FAILED
            return
        
        # Обновляем статус
        if task.status_message:
            await task.status_message.edit_text("⏳ Обрабатываю две фотографии...")
        
        temp_paths = []
        
        # Валидация второй фотографии
        if second_photo_path:
            try:
                with open(second_photo_path, 'rb') as f:
                    file_size = len(f.read())
                image_service.validate_image(second_photo_path, file_size)
                temp_paths.append(second_photo_path)
            except ImageValidationError as e:
                if task.status_message:
                    await task.status_message.edit_text(f"❌ Ошибка во второй фотографии: {str(e)}")
                else:
                    await message.answer(f"❌ Ошибка во второй фотографии: {str(e)}")
                task.status = TaskStatus.FAILED
                return
        
        # Проверяем обе фотографии на запрещенный контент
        if task.status_message:
            await task.status_message.edit_text("🔍 Проверяю изображения на запрещенный контент...")
        
        # Проверяем первую фотографию (скачиваем её для проверки)
        first_temp_path = None
        try:
            download_session = await grok_service._get_download_session()
            async with download_session.get(first_telegram_url) as resp:
                if resp.status == 200:
                    first_file_bytes = await resp.read()
                    first_temp_path = Path(settings.storage_path) / "temp" / f"first_{user_id}_{int(asyncio.get_event_loop().time())}.jpg"
                    first_temp_path.parent.mkdir(parents=True, exist_ok=True)
                    async with aiofiles.open(first_temp_path, 'wb') as f:
                        await f.write(first_file_bytes)
                    temp_paths.append(first_temp_path)
                    
                    # Проверяем первую фотографию
                    first_check = await grok_service.check_prohibited_content(first_temp_path)
                    if first_check["is_prohibited"]:
                        error_reasons = []
                        if first_check["has_children"]:
                            error_reasons.append("детей")
                        if first_check["has_military"]:
                            error_reasons.append("военных")
                        
                        error_msg = (
                            f"❌ Генерация видео запрещена.\n\n"
                            f"На первой фотографии обнаружен запрещенный контент: {', '.join(error_reasons)}.\n\n"
                            f"Мы не генерируем видео с участием детей или военных."
                        )
                        
                        if task.status_message:
                            await task.status_message.edit_text(error_msg)
                        else:
                            await message.answer(error_msg)
                        
                        task.status = TaskStatus.FAILED
                        return
        except Exception as e:
            logger.warning(f"Could not check first photo for prohibited content: {e}")
            # Продолжаем, если не удалось проверить первую фотографию
        
        # Проверяем вторую фотографию
        if temp_paths:
            second_check = await grok_service.check_prohibited_content(temp_paths[0])
            
            if second_check["is_prohibited"]:
                error_reasons = []
                if second_check["has_children"]:
                    error_reasons.append("детей")
                if second_check["has_military"]:
                    error_reasons.append("военных")
                
                error_msg = (
                    f"❌ Генерация видео запрещена.\n\n"
                    f"На второй фотографии обнаружен запрещенный контент: {', '.join(error_reasons)}.\n\n"
                    f"Мы не генерируем видео с участием детей или военных."
                )
                
                if task.status_message:
                    await task.status_message.edit_text(error_msg)
                else:
                    await message.answer(error_msg)
                
                task.status = TaskStatus.FAILED
                return
        
        logger.info(f"Using Telegram file URLs - First: {first_telegram_url}, Second: {second_telegram_url}")
        
        # Генерируем видео используя публичный URL Telegram
        if task.status_message:
            await task.status_message.edit_text("🎬 Генерирую видео из двух фотографий...")
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
        if task.status_message:
            await task.status_message.edit_text("✅ Видео готово! Отправляю...")
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
        if task.status_message:
            await task.status_message.delete()
        
        task.status = TaskStatus.COMPLETED
        
    except GrokAPIError as e:
        logger.error(f"Grok API error: {e}")
        error_msg = (
            "❌ Ошибка при генерации видео. "
            "Попробуйте позже или отправьте другие фотографии."
        )
        if task.status_message:
            await task.status_message.edit_text(error_msg)
        else:
            await message.answer(error_msg)
        task.status = TaskStatus.FAILED
    except Exception as e:
        logger.error(f"Error processing two photos task: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка при обработке. Попробуйте еще раз.")
        task.status = TaskStatus.FAILED
    finally:
        for path in temp_paths:
            if path and path.exists():
                image_service.cleanup(path)

