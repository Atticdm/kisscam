"""Middleware для rate limiting."""
from typing import Any, Awaitable, Callable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, Message, CallbackQuery
from services.rate_limiter import rate_limiter
from utils.logger import setup_logger

logger = setup_logger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    """Middleware для ограничения частоты запросов."""
    
    def __init__(self):
        # Команды, которые не требуют rate limiting
        self.excluded_commands = {'/start', '/help', '/terms'}
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any]
    ) -> Any:
        """Обработка события с проверкой rate limit."""
        
        # Получаем user_id и message/callback из события
        user_id = None
        message_obj = None
        callback_obj = None
        
        if isinstance(event, Update):
            if event.message:
                message_obj = event.message
                user_id = event.message.from_user.id if event.message.from_user else None
            elif event.callback_query:
                callback_obj = event.callback_query
                user_id = event.callback_query.from_user.id if event.callback_query.from_user else None
        elif isinstance(event, Message):
            message_obj = event
            user_id = event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            callback_obj = event
            user_id = event.from_user.id if event.from_user else None
        
        # Если не удалось получить user_id, пропускаем без ограничений
        if user_id is None:
            return await handler(event, data)
        
        # Проверяем, является ли это командой, которую нужно исключить
        message_to_check = message_obj or (callback_obj.message if callback_obj else None)
        if message_to_check and message_to_check.text:
            text = message_to_check.text.strip()
            if any(text.startswith(cmd) for cmd in self.excluded_commands):
                # Команды помощи не ограничиваем
                return await handler(event, data)
        
        # Проверяем rate limit
        allowed, remaining = await rate_limiter.check_rate_limit(user_id)
        
        if not allowed:
            # Лимит превышен - отправляем сообщение пользователю
            reset_time = await rate_limiter.get_reset_time(user_id)
            from datetime import datetime
            now = datetime.now()
            seconds_until_reset = int((reset_time - now).total_seconds())
            
            # Форматируем время до сброса
            if seconds_until_reset < 60:
                time_str = f"{seconds_until_reset} секунд"
            elif seconds_until_reset < 3600:
                minutes = seconds_until_reset // 60
                time_str = f"{minutes} минут"
            else:
                hours = seconds_until_reset // 3600
                minutes = (seconds_until_reset % 3600) // 60
                time_str = f"{hours} часов {minutes} минут"
            
            error_message = (
                "⏱️ Превышен лимит запросов!\n\n"
                f"Вы можете отправлять не более {rate_limiter.max_requests} запросов "
                f"в течение {rate_limiter.window_seconds // 60} минут.\n\n"
                f"Попробуйте снова через {time_str}."
            )
            
            # Отправляем сообщение пользователю
            if message_obj:
                await message_obj.answer(error_message)
            elif callback_obj:
                await callback_obj.answer(error_message, show_alert=True)
            elif isinstance(event, Update):
                if event.message:
                    await event.message.answer(error_message)
                elif event.callback_query:
                    await event.callback_query.answer(error_message, show_alert=True)
            
            # Не вызываем handler - блокируем обработку
            return None
        
        # Лимит не превышен - продолжаем обработку
        return await handler(event, data)

