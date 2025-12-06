"""Сервис для управления токенами пользователей."""
import json
from pathlib import Path
from typing import Dict, Optional
from bot.config import settings
from utils.logger import setup_logger

logger = setup_logger(__name__)


class TokenService:
    """Сервис для управления токенами пользователей."""
    
    def __init__(self):
        self.storage_path = Path(settings.storage_path) / "tokens.json"
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._tokens: Dict[int, int] = {}  # user_id -> token_count
        self._free_used: Dict[int, bool] = {}  # user_id -> has_used_free
        self._load_tokens()
    
    def _load_tokens(self):
        """Загружает токены из файла."""
        try:
            if self.storage_path.exists():
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._tokens = {int(k): v for k, v in data.get("tokens", {}).items()}
                    self._free_used = {int(k): v for k, v in data.get("free_used", {}).items()}
                logger.info(f"Loaded tokens for {len(self._tokens)} users")
        except Exception as e:
            logger.error(f"Error loading tokens: {e}")
            self._tokens = {}
            self._free_used = {}
    
    def _save_tokens(self):
        """Сохраняет токены в файл."""
        try:
            data = {
                "tokens": self._tokens,
                "free_used": self._free_used
            }
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving tokens: {e}")
    
    def can_generate(self, user_id: int) -> bool:
        """
        Проверяет, может ли пользователь сгенерировать видео.
        
        Args:
            user_id: ID пользователя
            
        Returns:
            bool: True если может (есть бесплатная генерация или токены)
        """
        # Проверяем бесплатную генерацию
        if not self._free_used.get(user_id, False):
            return True
        
        # Проверяем токены
        return self._tokens.get(user_id, 0) > 0
    
    def use_generation(self, user_id: int) -> bool:
        """
        Использует одну генерацию (бесплатную или токен).
        
        Args:
            user_id: ID пользователя
            
        Returns:
            bool: True если генерация использована успешно
        """
        # Используем бесплатную генерацию если доступна
        if not self._free_used.get(user_id, False):
            self._free_used[user_id] = True
            self._save_tokens()
            logger.info(f"User {user_id} used free generation")
            return True
        
        # Используем токен
        tokens = self._tokens.get(user_id, 0)
        if tokens > 0:
            self._tokens[user_id] = tokens - 1
            self._save_tokens()
            logger.info(f"User {user_id} used token, remaining: {self._tokens[user_id]}")
            return True
        
        return False
    
    def get_balance(self, user_id: int) -> Dict[str, int]:
        """
        Получает баланс пользователя.
        
        Args:
            user_id: ID пользователя
            
        Returns:
            dict: {"tokens": количество токенов, "free_available": есть ли бесплатная генерация}
        """
        return {
            "tokens": self._tokens.get(user_id, 0),
            "free_available": not self._free_used.get(user_id, False)
        }
    
    def add_tokens(self, user_id: int, amount: int):
        """
        Добавляет токены пользователю.
        
        Args:
            user_id: ID пользователя
            amount: Количество токенов для добавления
        """
        current = self._tokens.get(user_id, 0)
        self._tokens[user_id] = current + amount
        self._save_tokens()
        logger.info(f"Added {amount} tokens to user {user_id}, total: {self._tokens[user_id]}")


# Тарифы для покупки токенов
TOKEN_PACKAGES = {
    "10": {"tokens": 10, "stars": 200, "name": "10 токенов"},
    "50": {"tokens": 50, "stars": 950, "name": "50 токенов"},
    "100": {"tokens": 100, "stars": 1800, "name": "100 токенов"}
}

