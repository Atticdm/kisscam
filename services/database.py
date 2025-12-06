"""Модуль для работы с PostgreSQL базой данных."""
import asyncpg
from typing import Optional
from bot.config import settings
from utils.logger import setup_logger

logger = setup_logger(__name__)

# Глобальный пул соединений
_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """
    Получает пул соединений с базой данных.
    Создает пул при первом вызове.
    
    Returns:
        asyncpg.Pool: Пул соединений
    """
    global _pool
    
    if _pool is None:
        try:
            _pool = await asyncpg.create_pool(
                settings.database_url,
                min_size=5,  # Минимальное количество соединений
                max_size=20,  # Максимальное количество соединений для масштабирования
                command_timeout=60,  # Таймаут для команд
                server_settings={
                    'application_name': 'kisscam_bot',
                }
            )
            logger.info("Database connection pool created")
        except Exception as e:
            logger.error(f"Failed to create database pool: {e}", exc_info=True)
            raise
    
    return _pool


async def init_database():
    """
    Инициализирует базу данных: создает таблицы если их нет.
    """
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        try:
            # Создаем таблицу пользователей и токенов
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_tokens (
                    user_id BIGINT PRIMARY KEY,
                    tokens INTEGER NOT NULL DEFAULT 0,
                    free_generation_used BOOLEAN NOT NULL DEFAULT FALSE,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                );
            """)
            
            # Создаем индекс для быстрого поиска по user_id (хотя PRIMARY KEY уже индекс)
            # Но создадим индекс для updated_at для аналитики
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_tokens_updated_at 
                ON user_tokens(updated_at);
            """)
            
            # Создаем таблицу истории транзакций (для аудита и аналитики)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS token_transactions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    amount INTEGER NOT NULL,
                    transaction_type VARCHAR(50) NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    FOREIGN KEY (user_id) REFERENCES user_tokens(user_id) ON DELETE CASCADE
                );
            """)
            
            # Индекс для быстрого поиска транзакций пользователя
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_token_transactions_user_id 
                ON token_transactions(user_id, created_at DESC);
            """)
            
            logger.info("Database tables initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing database: {e}", exc_info=True)
            raise


async def close_database():
    """Закрывает пул соединений с базой данных."""
    global _pool
    
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database connection pool closed")

