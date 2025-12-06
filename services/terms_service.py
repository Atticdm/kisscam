"""Сервис для управления согласием пользователей с правилами."""
from typing import Optional
from datetime import datetime
from services.database import get_pool
from bot.terms import TERMS_VERSION
from utils.logger import setup_logger

logger = setup_logger(__name__)


class TermsService:
    """Сервис для управления согласием пользователей с правилами."""
    
    async def has_agreed_to_current_terms(self, user_id: int) -> bool:
        """
        Проверяет, согласился ли пользователь с текущей версией правил.
        
        Args:
            user_id: ID пользователя
            
        Returns:
            bool: True если пользователь согласился с текущей версией правил
        """
        pool = await get_pool()
        
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT terms_agreed_at, terms_version
                FROM user_tokens
                WHERE user_id = $1
            """, user_id)
            
            if row is None:
                return False
            
            # Проверяем, что пользователь согласился и версия правил совпадает
            return (
                row['terms_agreed_at'] is not None and
                row['terms_version'] == TERMS_VERSION
            )
    
    async def agree_to_terms(self, user_id: int) -> bool:
        """
        Сохраняет согласие пользователя с текущей версией правил.
        
        Args:
            user_id: ID пользователя
            
        Returns:
            bool: True если согласие успешно сохранено
        """
        pool = await get_pool()
        
        async with pool.acquire() as conn:
            # Убеждаемся, что пользователь существует
            await conn.execute("""
                INSERT INTO user_tokens (user_id, tokens, free_generations_used, terms_agreed_at, terms_version)
                VALUES ($1, 0, 0, NOW(), $2)
                ON CONFLICT (user_id) 
                DO UPDATE SET 
                    terms_agreed_at = NOW(),
                    terms_version = $2,
                    updated_at = NOW()
            """, user_id, TERMS_VERSION)
            
            logger.info(f"User {user_id} agreed to terms version {TERMS_VERSION}")
            return True
    
    async def get_terms_info(self, user_id: int) -> dict:
        """
        Получает информацию о согласии пользователя с правилами.
        
        Args:
            user_id: ID пользователя
            
        Returns:
            dict: {
                "agreed": bool,
                "agreed_at": Optional[datetime],
                "terms_version": Optional[int],
                "current_version": int,
                "needs_agreement": bool
            }
        """
        pool = await get_pool()
        
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT terms_agreed_at, terms_version
                FROM user_tokens
                WHERE user_id = $1
            """, user_id)
            
            if row is None:
                return {
                    "agreed": False,
                    "agreed_at": None,
                    "terms_version": None,
                    "current_version": TERMS_VERSION,
                    "needs_agreement": True
                }
            
            agreed_at = row['terms_agreed_at']
            user_version = row['terms_version']
            agreed = agreed_at is not None and user_version == TERMS_VERSION
            
            return {
                "agreed": agreed,
                "agreed_at": agreed_at,
                "terms_version": user_version,
                "current_version": TERMS_VERSION,
                "needs_agreement": not agreed
            }

