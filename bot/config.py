"""Конфигурация бота."""
import os
from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    """Настройки приложения."""
    
    # Telegram Bot
    telegram_bot_token: str = Field(..., env="TELEGRAM_BOT_TOKEN")
    
    # Grok API (xAI) - для анализа изображений
    grok_api_key: str = Field(..., env="GROK_API_KEY")
    grok_api_url: str = Field(default="https://api.x.ai/v1", env="GROK_API_URL")
    
    # Kie.ai API - для генерации видео через Grok Imagine
    kie_ai_api_key: str = Field(..., env="KIE_AI_API_KEY")
    kie_ai_api_url: str = Field(default="https://api.kie.ai", env="KIE_AI_API_URL")
    
    # PostgreSQL Database
    database_url: str = Field(..., env="DATABASE_URL")
    
    # Redis (optional)
    redis_host: str = Field(default="localhost", env="REDIS_HOST")
    redis_port: int = Field(default=6379, env="REDIS_PORT")
    redis_db: int = Field(default=0, env="REDIS_DB")
    
    # Storage
    storage_path: Path = Field(default=Path("./storage"), env="STORAGE_PATH")
    temp_storage_path: Path = Field(default=Path("./storage/temp"), env="TEMP_STORAGE_PATH")
    
    # Rate Limiting
    rate_limit_requests: int = Field(default=10, env="RATE_LIMIT_REQUESTS")
    rate_limit_period: int = Field(default=3600, env="RATE_LIMIT_PERIOD")
    
    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_file: Path = Field(default=Path("./logs/bot.log"), env="LOG_FILE")
    
    # Bot Settings
    max_file_size_mb: int = Field(default=10, env="MAX_FILE_SIZE_MB")
    video_duration_seconds: int = Field(default=5, env="VIDEO_DURATION_SECONDS")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        # Читать переменные окружения напрямую
        env_file_required = False


# Глобальный экземпляр настроек
try:
    settings = Settings()
except Exception as e:
    # Полезное сообщение об ошибке, если переменные не найдены
    missing_vars = []
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        missing_vars.append("TELEGRAM_BOT_TOKEN")
    if not os.getenv("GROK_API_KEY"):
        missing_vars.append("GROK_API_KEY")
    if not os.getenv("KIE_AI_API_KEY"):
        missing_vars.append("KIE_AI_API_KEY")
    
    if missing_vars:
        raise ValueError(
            f"Отсутствуют обязательные переменные окружения: {', '.join(missing_vars)}\n"
            f"Убедитесь, что они установлены в Railway Variables."
        ) from e
    raise
