"""Конфигурация бота."""
from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    """Настройки приложения."""
    
    # Telegram Bot
    telegram_bot_token: str = Field(..., env="TELEGRAM_BOT_TOKEN")
    
    # Grok API
    grok_api_key: str = Field(..., env="GROK_API_KEY")
    grok_api_url: str = Field(default="https://api.x.ai/v1", env="GROK_API_URL")
    
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


# Глобальный экземпляр настроек
settings = Settings()
