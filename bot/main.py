"""Главный файл бота."""
import asyncio
import sys
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from bot.config import settings
from bot.handlers import commands, photos
from utils.logger import setup_logger

logger = setup_logger(__name__)


async def main():
    """Запуск бота."""
    # Инициализация базы данных
    from services.database import init_database, close_database
    try:
        await init_database()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)
        raise
    
    # Инициализация бота и диспетчера
    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher(storage=MemoryStorage())
    
    # Регистрация роутеров
    from bot.handlers import errors, payments
    dp.include_router(commands.router)
    dp.include_router(payments.router)
    dp.include_router(photos.router)
    dp.include_router(errors.router)
    
    logger.info("Bot starting...")
    
    try:
        # Запуск polling
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error running bot: {e}", exc_info=True)
    finally:
        await close_database()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
        sys.exit(0)
