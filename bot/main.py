"""Главный файл бота."""
import asyncio
import sys
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from bot.config import settings
from bot.handlers import commands, photos
from services.database import init_database, close_database, get_fsm_storage
from utils.logger import setup_logger

logger = setup_logger(__name__)


async def main():
    """Запуск бота."""
    # Инициализация базы данных
    try:
        await init_database()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}", exc_info=True)
        raise
    
    # Инициализация FSM хранилища (PostgreSQL)
    try:
        fsm_storage = await get_fsm_storage()
        logger.info("FSM storage initialized")
    except Exception as e:
        logger.error(f"Failed to initialize FSM storage: {e}", exc_info=True)
        raise
    
    # Инициализация бота и диспетчера
    bot = Bot(token=settings.telegram_bot_token)
    dp = Dispatcher(storage=fsm_storage)
    
    # Устанавливаем меню команд
    commands_list = [
        BotCommand(command="start", description="🚀 Запустить бота"),
        BotCommand(command="help", description="❓ Помощь по использованию"),
        BotCommand(command="menu", description="📋 Показать меню команд"),
        BotCommand(command="tokens", description="💰 Проверить баланс токенов"),
        BotCommand(command="buy", description="💳 Купить токены"),
        BotCommand(command="promo", description="🎁 Использовать промокод"),
        BotCommand(command="terms", description="📋 Правила использования"),
    ]
    
    try:
        await bot.set_my_commands(commands_list)
        logger.info("Bot commands menu set")
    except Exception as e:
        logger.warning(f"Failed to set bot commands: {e}", exc_info=True)
    
    # Регистрация middleware для rate limiting
    from bot.middlewares.rate_limit import RateLimitMiddleware
    dp.update.middleware(RateLimitMiddleware())
    logger.info("Rate limit middleware registered")
    
    # Инициализация очереди задач
    from services.task_queue import get_task_queue
    task_queue = get_task_queue()
    try:
        await task_queue.start()
        logger.info("Task queue started")
    except Exception as e:
        logger.error(f"Failed to start task queue: {e}", exc_info=True)
        raise
    
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
        # Останавливаем очередь задач
        try:
            await task_queue.stop()
            logger.info("Task queue stopped")
        except Exception as e:
            logger.error(f"Error stopping task queue: {e}", exc_info=True)
        
        # Закрываем HTTP сессии с connection pooling
        try:
            from services.grok_service import GrokService
            await GrokService.close_sessions()
            logger.info("HTTP sessions closed")
        except Exception as e:
            logger.error(f"Error closing HTTP sessions: {e}", exc_info=True)
        
        await close_database()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
        sys.exit(0)
