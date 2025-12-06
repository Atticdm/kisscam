"""Сервис для управления токенами пользователей через PostgreSQL."""
from typing import Dict, Optional
from services.database import get_pool
from utils.logger import setup_logger

logger = setup_logger(__name__)


class TokenService:
    """Сервис для управления токенами пользователей."""
    
    # Количество бесплатных генераций для новых пользователей
    FREE_GENERATIONS_LIMIT = 3
    
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
                INSERT INTO user_tokens (user_id, tokens, free_generations_used, promo_generations)
                VALUES ($1, 0, 0, 0)
                ON CONFLICT (user_id) DO NOTHING
            """, user_id)
    
    async def can_generate(self, user_id: int) -> bool:
        """
        Проверяет, может ли пользователь сгенерировать видео.
        
        Args:
            user_id: ID пользователя
            
        Returns:
            bool: True если может (есть бесплатная генерация или токены)
        """
        await self._ensure_user_exists(user_id)
        
        pool = await get_pool()
        
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT tokens, free_generations_used, promo_generations
                FROM user_tokens
                WHERE user_id = $1
            """, user_id)
            
            if row is None:
                return True  # Новый пользователь имеет бесплатные генерации
            
            tokens = row['tokens']
            free_generations_used = row['free_generations_used']
            promo_generations = row.get('promo_generations', 0) or 0
            
            # Может генерировать если есть бесплатные генерации (меньше лимита), промокодные генерации или токены
            free_available = free_generations_used < self.FREE_GENERATIONS_LIMIT
            promo_available = promo_generations > 0
            return free_available or promo_available or tokens > 0
    
    async def use_generation(self, user_id: int) -> bool:
        """
        Использует одну генерацию (бесплатную или токен).
        
        Args:
            user_id: ID пользователя
            
        Returns:
            bool: True если генерация использована успешно
        """
        await self._ensure_user_exists(user_id)
        
        pool = await get_pool()
        
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Получаем текущее состояние
                row = await conn.fetchrow("""
                    SELECT tokens, free_generations_used
                    FROM user_tokens
                    WHERE user_id = $1
                    FOR UPDATE
                """, user_id)
                
                if row is None:
                    return False
                
                tokens = row['tokens']
                free_generations_used = row['free_generations_used']
                
                # Используем бесплатную генерацию если доступна (меньше лимита)
                if free_generations_used < self.FREE_GENERATIONS_LIMIT:
                    new_count = free_generations_used + 1
                    await conn.execute("""
                        UPDATE user_tokens
                        SET free_generations_used = $1,
                            updated_at = NOW()
                        WHERE user_id = $2
                    """, new_count, user_id)
                    
                    # Записываем транзакцию
                    await conn.execute("""
                        INSERT INTO token_transactions (user_id, amount, transaction_type, description)
                        VALUES ($1, 0, 'free_generation', 'Used free generation')
                    """, user_id)
                    
                    remaining_free = self.FREE_GENERATIONS_LIMIT - new_count
                    logger.info(
                        f"User {user_id} used free generation "
                        f"({new_count}/{self.FREE_GENERATIONS_LIMIT}), "
                        f"remaining free: {remaining_free}"
                    )
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
        Получает баланс пользователя.
        
        Args:
            user_id: ID пользователя
            
        Returns:
            dict: {
                "tokens": количество токенов,
                "free_available": есть ли бесплатные генерации (bool),
                "free_remaining": количество оставшихся бесплатных генераций (int),
                "free_used": количество использованных бесплатных генераций (int)
            }
        """
        await self._ensure_user_exists(user_id)
        
        pool = await get_pool()
        
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT tokens, free_generations_used, promo_generations
                FROM user_tokens
                WHERE user_id = $1
            """, user_id)
            
            if row is None:
                return {
                    "tokens": 0,
                    "free_available": True,
                    "free_remaining": self.FREE_GENERATIONS_LIMIT,
                    "free_used": 0,
                    "promo_generations": 0
                }
            
            free_generations_used = row['free_generations_used']
            promo_generations = row.get('promo_generations', 0) or 0
            free_remaining = max(0, self.FREE_GENERATIONS_LIMIT - free_generations_used)
            
            return {
                "tokens": row['tokens'],
                "free_available": free_remaining > 0,
                "free_remaining": free_remaining,
                "free_used": free_generations_used,
                "promo_generations": promo_generations
            }
    
    async def add_tokens(self, user_id: int, amount: int):
        """
        Добавляет токены пользователю.
        
        Args:
            user_id: ID пользователя
            amount: Количество токенов для добавления
        """
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
