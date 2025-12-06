"""Собственная реализация PostgreSQL хранилища для FSM в aiogram 3.x."""
import json
from typing import Any, Optional
from collections.abc import Mapping
import asyncpg
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.fsm.state import State
from utils.logger import setup_logger

logger = setup_logger(__name__)

StateType = str | State | None


class PostgreSQLStorage(BaseStorage):
    """PostgreSQL хранилище для FSM состояний в aiogram 3.x."""
    
    def __init__(self, pool: asyncpg.Pool):
        """
        Инициализирует PostgreSQL хранилище.
        
        Args:
            pool: Пул соединений asyncpg
        """
        self.pool = pool
        self._key_builder = None  # Можно добавить кастомный key builder если нужно
    
    def _build_key(self, key: StorageKey) -> str:
        """
        Строит ключ для хранения в БД.
        State и data хранятся в одной записи.
        
        Args:
            key: Ключ хранилища
            
        Returns:
            Строковый ключ
        """
        parts = [
            str(key.bot_id),
            str(key.chat_id),
            str(key.user_id),
        ]
        if key.thread_id:
            parts.append(str(key.thread_id))
        if key.business_connection_id:
            parts.append(str(key.business_connection_id))
        if key.destiny != "default":
            parts.append(key.destiny)
        
        return ":".join(parts)
    
    def _resolve_state(self, value: StateType) -> Optional[str]:
        """Преобразует StateType в строку."""
        if value is None:
            return None
        if isinstance(value, State):
            return value.state
        return str(value)
    
    async def create_schema(self):
        """Создает схему таблиц для FSM."""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS fsm_data (
                    key VARCHAR(255) PRIMARY KEY,
                    state VARCHAR(255),
                    data JSONB,
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                );
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_fsm_data_updated_at 
                ON fsm_data(updated_at);
            """)
            
            logger.info("FSM schema created")
    
    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        """Устанавливает состояние для ключа."""
        storage_key = self._build_key(key)
        state_str = self._resolve_state(state)
        
        async with self.pool.acquire() as conn:
            if state_str is None:
                # Удаляем состояние, но сохраняем данные если они есть
                await conn.execute("""
                    UPDATE fsm_data 
                    SET state = NULL, updated_at = NOW()
                    WHERE key = $1
                """, storage_key)
                # Если нет ни state ни data, удаляем запись
                row = await conn.fetchrow("""
                    SELECT state, data FROM fsm_data WHERE key = $1
                """, storage_key)
                if row and row['state'] is None and (not row['data'] or row['data'] == {}):
                    await conn.execute("""
                        DELETE FROM fsm_data WHERE key = $1
                    """, storage_key)
            else:
                # Обновляем или создаем запись
                await conn.execute("""
                    INSERT INTO fsm_data (key, state, updated_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (key) 
                    DO UPDATE SET state = $2, updated_at = NOW()
                """, storage_key, state_str)
    
    async def get_state(self, key: StorageKey) -> Optional[str]:
        """Получает состояние для ключа."""
        storage_key = self._build_key(key)
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT state FROM fsm_data WHERE key = $1
            """, storage_key)
            
            if row:
                return row['state']
            return None
    
    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        """Устанавливает данные для ключа."""
        storage_key = self._build_key(key)
        
        if not isinstance(data, dict):
            raise ValueError(f"Data must be a dict, got {type(data).__name__}")
        
        async with self.pool.acquire() as conn:
            if not data:
                # Удаляем данные, но сохраняем state если он есть
                await conn.execute("""
                    UPDATE fsm_data 
                    SET data = NULL, updated_at = NOW()
                    WHERE key = $1
                """, storage_key)
                # Если нет ни state ни data, удаляем запись
                row = await conn.fetchrow("""
                    SELECT state, data FROM fsm_data WHERE key = $1
                """, storage_key)
                if row and row['state'] is None and (not row['data'] or row['data'] == {}):
                    await conn.execute("""
                        DELETE FROM fsm_data WHERE key = $1
                    """, storage_key)
            else:
                # Обновляем или создаем запись
                await conn.execute("""
                    INSERT INTO fsm_data (key, data, updated_at)
                    VALUES ($1, $2::jsonb, NOW())
                    ON CONFLICT (key) 
                    DO UPDATE SET data = $2::jsonb, updated_at = NOW()
                """, storage_key, json.dumps(data))
    
    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        """Получает данные для ключа."""
        storage_key = self._build_key(key)
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT data FROM fsm_data WHERE key = $1
            """, storage_key)
            
            if row and row['data']:
                return dict(row['data'])
            return {}
    
    async def update_data(self, key: StorageKey, data: Mapping[str, Any]) -> dict[str, Any]:
        """Обновляет данные для ключа (как dict.update)."""
        current_data = await self.get_data(key)
        current_data.update(data)
        await self.set_data(key, current_data)
        return current_data.copy()
    
    async def close(self) -> None:
        """Закрывает хранилище."""
        # Пул соединений закрывается отдельно в close_database()
        pass

