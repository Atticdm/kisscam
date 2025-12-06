"""Сервис для управления токенами пользователей через PostgreSQL."""
from typing import Dict, Optional
from services.database import get_pool
from utils.logger import setup_logger

logger = setup_logger(__name__)


class TokenService:
    """Сервис для управления токенами пользователей."""
    
    def __init__(self):
        # Инициализация происходит асинхронно через init_database()
        pass
    
    async def _ensure_user_exists(self, user_id: int):
        """
        Убеждается, что пользователь существует в базе данных.
        Создает запись если её нет.
        
        Args:
            user_id: ID пользователя
        """
        pool = await get_pool()
        
        async with pool.acquire() as conn:
            # Используем INSERT ... ON CONFLICT для атомарной операции
            await conn.execute("""
                INSERT INTO user_tokens (user_id, tokens, free_generation_used)
                VALUES ($1, 0, FALSE)
                ON CONFLICT (user_id) DO NOTHING
            """, user_id)
    
    def can_generate(self, user_id: int) -> bool:
        """
        Проверяет, может ли пользователь сгенерировать видео.
        
        Args:
            user_id: ID пользователя
            
        Returns:
            bool: True если может (есть бесплатная генерация или токены)
        """
        # Это синхронный метод, но нам нужен async
        # В реальности нужно вызывать async версию
        # Для совместимости оставляем, но лучше использовать async версию
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Если цикл уже запущен, создаем задачу
                return loop.run_until_complete(self._can_generate_async(user_id))
            else:
                return asyncio.run(self._can_generate_async(user_id))
        except RuntimeError:
            return asyncio.run(self._can_generate_async(user_id))
    
    async def _can_generate_async(self, user_id: int) -> bool:
        """Асинхронная версия can_generate."""
        await self._ensure_user_exists(user_id)
        
        pool = await get_pool()
        
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT tokens, free_generation_used
                FROM user_tokens
                WHERE user_id = $1
            """, user_id)
            
            if row is None:
                return True  # Новый пользователь имеет бесплатную генерацию
            
            tokens = row['tokens']
            free_used = row['free_generation_used']
            
            # Может генерировать если есть бесплатная генерация или токены
            return not free_used or tokens > 0
    
    async def use_generation(self, user_id: int) -> bool:
        """
        Использует одну генерацию (бесплатную или токен) (async версия).
        
        Args:
            user_id: ID пользователя
            
        Returns:
            bool: True если генерация использована успешно
        """
        return await self._use_generation_async(user_id)
    
    async def _use_generation_async(self, user_id: int) -> bool:
        """Асинхронная версия use_generation."""
        await self._ensure_user_exists(user_id)
        
        pool = await get_pool()
        
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Получаем текущее состояние
                row = await conn.fetchrow("""
                    SELECT tokens, free_generation_used
                    FROM user_tokens
                    WHERE user_id = $1
                    FOR UPDATE
                """, user_id)
                
                if row is None:
                    return False
                
                tokens = row['tokens']
                free_used = row['free_generation_used']
                
                # Используем бесплатную генерацию если доступна
                if not free_used:
                    await conn.execute("""
                        UPDATE user_tokens
                        SET free_generation_used = TRUE,
                            updated_at = NOW()
                        WHERE user_id = $1
                    """, user_id)
                    
                    # Записываем транзакцию
                    await conn.execute("""
                        INSERT INTO token_transactions (user_id, amount, transaction_type, description)
                        VALUES ($1, 0, 'free_generation', 'Used free generation')
                    """, user_id)
                    
                    logger.info(f"User {user_id} used free generation")
                    return True
                
                # Используем токен если есть
                if tokens > 0:
                    await conn.execute("""
                        UPDATE user_tokens
                        SET tokens = tokens - 1,
                            updated_at = NOW()
                        WHERE user_id = $1
                    """, user_id)
                    
                    # Записываем транзакцию
                    await conn.execute("""
                        INSERT INTO token_transactions (user_id, amount, transaction_type, description)
                        VALUES ($1, -1, 'token_used', 'Used token for video generation')
                    """, user_id)
                    
                    logger.info(f"User {user_id} used token, remaining: {tokens - 1}")
                    return True
                
                return False
    
    async def get_balance(self, user_id: int) -> Dict[str, int]:
        """
        Получает баланс пользователя (async версия).
        
        Args:
            user_id: ID пользователя
            
        Returns:
            dict: {"tokens": количество токенов, "free_available": есть ли бесплатная генерация}
        """
        return await self._get_balance_async(user_id)
    
    async def _get_balance_async(self, user_id: int) -> Dict[str, int]:
        """Асинхронная версия get_balance."""
        await self._ensure_user_exists(user_id)
        
        pool = await get_pool()
        
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT tokens, free_generation_used
                FROM user_tokens
                WHERE user_id = $1
            """, user_id)
            
            if row is None:
                return {"tokens": 0, "free_available": True}
            
            return {
                "tokens": row['tokens'],
                "free_available": not row['free_generation_used']
            }
    
    async def add_tokens(self, user_id: int, amount: int):
        """
        Добавляет токены пользователю (async версия).
        
        Args:
            user_id: ID пользователя
            amount: Количество токенов для добавления
        """
        await self._add_tokens_async(user_id, amount)
    
    async def _add_tokens_async(self, user_id: int, amount: int):
        """Асинхронная версия add_tokens."""
        await self._ensure_user_exists(user_id)
        
        pool = await get_pool()
        
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Добавляем токены
                await conn.execute("""
                    UPDATE user_tokens
                    SET tokens = tokens + $1,
                        updated_at = NOW()
                    WHERE user_id = $2
                """, amount, user_id)
                
                # Записываем транзакцию
                await conn.execute("""
                    INSERT INTO token_transactions (user_id, amount, transaction_type, description)
                    VALUES ($1, $2, 'purchase', 'Purchased tokens')
                """, user_id, amount)
                
                logger.info(f"Added {amount} tokens to user {user_id}")


# Тарифы для покупки токенов
TOKEN_PACKAGES = {
    "10": {"tokens": 10, "stars": 200, "name": "10 токенов"},
    "50": {"tokens": 50, "stars": 950, "name": "50 токенов"},
    "100": {"tokens": 100, "stars": 1800, "name": "100 токенов"}
}
