"""Обработчики ошибок."""
from aiogram import Router
from aiogram.types import ErrorEvent
from utils.logger import setup_logger

logger = setup_logger(__name__)

router = Router()


@router.error()
async def error_handler(event: ErrorEvent):
    """Глобальный обработчик ошибок."""
    logger.error(f"Update {event.update} caused error: {event.exception}", exc_info=True)
    
    # Отправляем сообщение пользователю, если это возможно
    if event.update.message:
        await event.update.message.answer(
            "❌ Произошла непредвиденная ошибка. "
            "Попробуйте отправить запрос заново."
        )
