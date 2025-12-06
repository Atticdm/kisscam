"""Сервис для работы с промокодами."""
from typing import Optional, Dict
from services.database import get_pool
from utils.logger import setup_logger

logger = setup_logger(__name__)


class PromoCodeError(Exception):
    """Ошибка при работе с промокодами."""
    pass


class PromoService:
    """Сервис для управления промокодами."""
    
    def __init__(self):
        pass
    
    async def apply_promo_code(self, user_id: int, code: str) -> Dict[str, int]:
        """
        Применяет промокод для пользователя.
        
        Args:
            user_id: ID пользователя
            code: Код промокода
            
        Returns:
            dict: {
                "generations_added": количество добавленных генераций,
                "total_promo_generations": общее количество промокодных генераций
            }
            
        Raises:
            PromoCodeError: Если промокод недействителен или уже использован максимальное количество раз
        """
        code = code.strip().lower()
        
        pool = await get_pool()
        
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Проверяем существование и активность промокода
                promo_row = await conn.fetchrow("""
                    SELECT code, generations, max_uses_per_user, is_active
                    FROM promo_codes
                    WHERE code = $1
                """, code)
                
                if not promo_row:
                    raise PromoCodeError("Промокод не найден")
                
                if not promo_row['is_active']:
                    raise PromoCodeError("Промокод неактивен")
                
                generations = promo_row['generations']
                max_uses = promo_row['max_uses_per_user']
                
                # Проверяем, сколько раз пользователь уже использовал этот промокод
                usage_count = await conn.fetchval("""
                    SELECT COUNT(*)
                    FROM promo_code_usage
                    WHERE user_id = $1 AND promo_code = $2
                """, user_id, code)
                
                if usage_count >= max_uses:
                    raise PromoCodeError(
                        f"Вы уже использовали этот промокод максимальное количество раз ({max_uses})"
                    )
                
                # Убеждаемся, что пользователь существует
                await conn.execute("""
                    INSERT INTO user_tokens (user_id, tokens, free_generations_used, promo_generations)
                    VALUES ($1, 0, 0, 0)
                    ON CONFLICT (user_id) DO NOTHING
                """, user_id)
                
                # Добавляем промокодные генерации
                await conn.execute("""
                    UPDATE user_tokens
                    SET promo_generations = promo_generations + $1,
                        updated_at = NOW()
                    WHERE user_id = $2
                """, generations, user_id)
                
                # Записываем использование промокода
                await conn.execute("""
                    INSERT INTO promo_code_usage (user_id, promo_code)
                    VALUES ($1, $2)
                """, user_id, code)
                
                # Получаем общее количество промокодных генераций
                total_promo = await conn.fetchval("""
                    SELECT promo_generations
                    FROM user_tokens
                    WHERE user_id = $1
                """, user_id)
                
                logger.info(
                    f"User {user_id} applied promo code {code}, "
                    f"added {generations} generations, total promo: {total_promo}"
                )
                
                return {
                    "generations_added": generations,
                    "total_promo_generations": total_promo
                }
    
    async def get_promo_info(self, user_id: int, code: str) -> Optional[Dict]:
        """
        Получает информацию о промокоде для пользователя.
        
        Args:
            user_id: ID пользователя
            code: Код промокода
            
        Returns:
            dict или None: {
                "code": код промокода,
                "generations": количество генераций,
                "max_uses": максимальное количество использований,
                "used_count": сколько раз использовал пользователь,
                "remaining_uses": сколько раз еще можно использовать,
                "is_active": активен ли промокод
            }
        """
        code = code.strip().lower()
        
        pool = await get_pool()
        
        async with pool.acquire() as conn:
            promo_row = await conn.fetchrow("""
                SELECT code, generations, max_uses_per_user, is_active
                FROM promo_codes
                WHERE code = $1
            """, code)
            
            if not promo_row:
                return None
            
            usage_count = await conn.fetchval("""
                SELECT COUNT(*)
                FROM promo_code_usage
                WHERE user_id = $1 AND promo_code = $2
            """, user_id, code) or 0
            
            return {
                "code": promo_row['code'],
                "generations": promo_row['generations'],
                "max_uses": promo_row['max_uses_per_user'],
                "used_count": usage_count,
                "remaining_uses": max(0, promo_row['max_uses_per_user'] - usage_count),
                "is_active": promo_row['is_active']
            }

