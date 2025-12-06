"""Модуль для работы с PostgreSQL базой данных."""
import asyncpg
from typing import Optional
from bot.config import settings
from utils.logger import setup_logger

logger = setup_logger(__name__)

# Глобальный пул соединений
_pool: Optional[asyncpg.Pool] = None

# Глобальное хранилище FSM
_fsm_storage = None


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
                    free_generations_used INTEGER NOT NULL DEFAULT 0,
                    promo_generations INTEGER NOT NULL DEFAULT 0,
                    terms_agreed_at TIMESTAMP WITH TIME ZONE,
                    terms_version INTEGER,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                );
            """)
            
            # Миграция: добавляем поле promo_generations если его нет
            try:
                await conn.execute("""
                    ALTER TABLE user_tokens 
                    ADD COLUMN IF NOT EXISTS promo_generations INTEGER NOT NULL DEFAULT 0;
                """)
            except Exception as e:
                logger.debug(f"Column promo_generations may already exist: {e}")
            
            # Миграция: изменяем free_generation_used (BOOLEAN) на free_generations_used (INTEGER)
            try:
                # Проверяем, существует ли старое поле free_generation_used
                column_check = await conn.fetchval("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'user_tokens' 
                    AND column_name = 'free_generation_used'
                """)
                
                if column_check:
                    # Мигрируем данные: TRUE -> 1, FALSE -> 0
                    await conn.execute("""
                        ALTER TABLE user_tokens 
                        ADD COLUMN IF NOT EXISTS free_generations_used INTEGER NOT NULL DEFAULT 0;
                    """)
                    
                    # Переносим данные из старого поля в новое
                    await conn.execute("""
                        UPDATE user_tokens 
                        SET free_generations_used = CASE 
                            WHEN free_generation_used = TRUE THEN 1 
                            ELSE 0 
                        END
                        WHERE free_generations_used = 0;
                    """)
                    
                    # Удаляем старое поле
                    await conn.execute("""
                        ALTER TABLE user_tokens 
                        DROP COLUMN IF EXISTS free_generation_used;
                    """)
                    
                    logger.info("Migrated free_generation_used to free_generations_used")
            except Exception as e:
                logger.debug(f"Migration might already be done or error: {e}")
            
            # Добавляем колонки для согласия с правилами, если их еще нет (миграция)
            try:
                await conn.execute("""
                    ALTER TABLE user_tokens 
                    ADD COLUMN IF NOT EXISTS terms_agreed_at TIMESTAMP WITH TIME ZONE;
                """)
                await conn.execute("""
                    ALTER TABLE user_tokens 
                    ADD COLUMN IF NOT EXISTS terms_version INTEGER;
                """)
            except Exception as e:
                # Колонки уже существуют или другая ошибка - игнорируем
                logger.debug(f"Columns might already exist: {e}")
            
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
            
            # Создаем таблицу для rate limiting (sliding window)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS rate_limits (
                    user_id BIGINT PRIMARY KEY,
                    request_count INTEGER NOT NULL DEFAULT 0,
                    window_start TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                );
            """)
            
            # Создаем таблицу промокодов
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS promo_codes (
                    code VARCHAR(50) PRIMARY KEY,
                    generations INTEGER NOT NULL,
                    max_uses_per_user INTEGER NOT NULL DEFAULT 1,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                );
            """)
            
            # Создаем таблицу использования промокодов
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS promo_code_usage (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    promo_code VARCHAR(50) NOT NULL,
                    used_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    FOREIGN KEY (user_id) REFERENCES user_tokens(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (promo_code) REFERENCES promo_codes(code) ON DELETE CASCADE,
                    UNIQUE(user_id, promo_code, used_at)
                );
            """)
            
            # Индекс для быстрого поиска использований промокода пользователем
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_promo_code_usage_user_code 
                ON promo_code_usage(user_id, promo_code);
            """)
            
            # Вставляем промокод scam10 если его еще нет
            await conn.execute("""
                INSERT INTO promo_codes (code, generations, max_uses_per_user, is_active)
                VALUES ('scam10', 10, 3, TRUE)
                ON CONFLICT (code) DO NOTHING;
            """)
            
            logger.info("Promo codes tables created")
            
            # Индекс для очистки старых записей
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_rate_limits_window_start 
                ON rate_limits(window_start);
            """)
            
            logger.info("Database tables initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing database: {e}", exc_info=True)
            raise


async def get_fsm_storage():
    """
    Получает хранилище FSM состояний на основе PostgreSQL.
    Создает хранилище при первом вызове.
    
    Returns:
        Хранилище FSM состояний (PostgreSQLStorage)
    """
    global _fsm_storage
    
    if _fsm_storage is None:
        try:
            # Импортируем PostgreSQLStorage (пробуем разные варианты импорта)
            try:
                from aiogram.fsm.storage.postgresql import PostgreSQLStorage
            except ImportError:
                # Альтернативный путь импорта
                from aiogram.fsm.storage.postgres import PostgreSQLStorage
            
            # Получаем пул соединений
            pool = await get_pool()
            
            # Создаем хранилище с использованием пула
            _fsm_storage = PostgreSQLStorage(pool=pool)
            
            # Создаем схему таблиц для FSM (если метод доступен)
            if hasattr(_fsm_storage, 'create_schema'):
                await _fsm_storage.create_schema()
            
            logger.info("FSM PostgreSQL storage initialized")
        except ImportError as e:
            logger.error(
                f"Failed to import PostgreSQLStorage. "
                f"Make sure aiogram[postgres] is installed: {e}",
                exc_info=True
            )
            raise
        except Exception as e:
            logger.error(f"Failed to create FSM storage: {e}", exc_info=True)
            raise
    
    return _fsm_storage


async def close_database():
    """Закрывает пул соединений с базой данных и FSM хранилище."""
    global _pool, _fsm_storage
    
    if _fsm_storage is not None:
        await _fsm_storage.close()
        _fsm_storage = None
        logger.info("FSM storage closed")
    
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database connection pool closed")

