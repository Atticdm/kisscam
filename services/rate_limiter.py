"""Сервис для rate limiting запросов пользователей."""
from datetime import datetime, timedelta
from typing import Tuple
from services.database import get_pool
from bot.config import settings
from utils.logger import setup_logger

logger = setup_logger(__name__)


class RateLimiter:
    """Сервис для ограничения частоты запросов пользователей."""
    
    def __init__(self):
        self.max_requests = settings.rate_limit_requests
        self.window_seconds = settings.rate_limit_period
    
    async def check_rate_limit(self, user_id: int) -> Tuple[bool, int]:
        """
        Проверяет, не превышен ли лимит запросов для пользователя.
        Использует sliding window алгоритм.
        
        Args:
            user_id: ID пользователя Telegram
            
        Returns:
            Tuple[bool, int]: (разрешено ли, оставшееся количество запросов)
            - True если запрос разрешен, False если лимит превышен
            - Количество оставшихся запросов (может быть отрицательным если лимит превышен)
        """
        pool = await get_pool()
        now = datetime.now()
        window_start = now - timedelta(seconds=self.window_seconds)
        
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Получаем текущее состояние rate limit для пользователя
                row = await conn.fetchrow("""
                    SELECT request_count, window_start
                    FROM rate_limits
                    WHERE user_id = $1
                    FOR UPDATE
                """, user_id)
                
                if row is None:
                    # Первый запрос от пользователя - создаем запись
                    await conn.execute("""
                        INSERT INTO rate_limits (user_id, request_count, window_start, updated_at)
                        VALUES ($1, 1, NOW(), NOW())
                    """, user_id)
                    remaining = self.max_requests - 1
                    logger.debug(f"Rate limit: user {user_id}, first request, remaining: {remaining}")
                    return True, remaining
                
                current_count = row['request_count']
                stored_window_start = row['window_start']
                
                # Проверяем, не истекло ли окно
                if stored_window_start < window_start:
                    # Окно истекло - сбрасываем счетчик
                    await conn.execute("""
                        UPDATE rate_limits
                        SET request_count = 1,
                            window_start = NOW(),
                            updated_at = NOW()
                        WHERE user_id = $1
                    """, user_id)
                    remaining = self.max_requests - 1
                    logger.debug(f"Rate limit: user {user_id}, window reset, remaining: {remaining}")
                    return True, remaining
                
                # Окно еще активно - проверяем лимит
                if current_count >= self.max_requests:
                    # Лимит превышен
                    # Вычисляем время до сброса окна
                    reset_time = stored_window_start + timedelta(seconds=self.window_seconds)
                    seconds_until_reset = int((reset_time - now).total_seconds())
                    remaining = 0
                    logger.warning(
                        f"Rate limit exceeded: user {user_id}, "
                        f"count: {current_count}/{self.max_requests}, "
                        f"reset in {seconds_until_reset}s"
                    )
                    return False, remaining
                
                # Увеличиваем счетчик
                await conn.execute("""
                    UPDATE rate_limits
                    SET request_count = request_count + 1,
                        updated_at = NOW()
                    WHERE user_id = $1
                """, user_id)
                
                remaining = self.max_requests - (current_count + 1)
                logger.debug(
                    f"Rate limit: user {user_id}, "
                    f"count: {current_count + 1}/{self.max_requests}, "
                    f"remaining: {remaining}"
                )
                return True, remaining
    
    async def get_remaining_requests(self, user_id: int) -> int:
        """
        Получает количество оставшихся запросов для пользователя.
        
        Args:
            user_id: ID пользователя Telegram
            
        Returns:
            int: Количество оставшихся запросов
        """
        pool = await get_pool()
        now = datetime.now()
        window_start = now - timedelta(seconds=self.window_seconds)
        
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT request_count, window_start
                FROM rate_limits
                WHERE user_id = $1
            """, user_id)
            
            if row is None:
                return self.max_requests
            
            current_count = row['request_count']
            stored_window_start = row['window_start']
            
            # Если окно истекло, возвращаем полный лимит
            if stored_window_start < window_start:
                return self.max_requests
            
            # Возвращаем оставшиеся запросы
            return max(0, self.max_requests - current_count)
    
    async def get_reset_time(self, user_id: int) -> datetime:
        """
        Получает время сброса лимита для пользователя.
        
        Args:
            user_id: ID пользователя Telegram
            
        Returns:
            datetime: Время сброса лимита
        """
        pool = await get_pool()
        
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT window_start
                FROM rate_limits
                WHERE user_id = $1
            """, user_id)
            
            if row is None:
                return datetime.now()
            
            window_start = row['window_start']
            return window_start + timedelta(seconds=self.window_seconds)
    
    async def cleanup_old_records(self, days: int = 7):
        """
        Удаляет старые записи rate limiting (старше указанного количества дней).
        Полезно для очистки базы данных от неактивных пользователей.
        
        Args:
            days: Количество дней для хранения записей (по умолчанию 7)
        """
        pool = await get_pool()
        cutoff_date = datetime.now() - timedelta(days=days)
        
        async with pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM rate_limits
                WHERE updated_at < $1
            """, cutoff_date)
            
            deleted_count = int(result.split()[-1])
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} old rate limit records")


# Глобальный экземпляр rate limiter
rate_limiter = RateLimiter()

