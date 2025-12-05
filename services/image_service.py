"""Сервис для обработки изображений."""
import aiofiles
from pathlib import Path
from typing import Optional
from bot.config import settings
from utils.logger import setup_logger

logger = setup_logger(__name__)


class ImageValidationError(Exception):
    """Ошибка валидации изображения."""
    pass


class ImageService:
    """Сервис для работы с изображениями."""
    
    def __init__(self):
        self.max_size_mb = settings.max_file_size_mb
        self.max_size_bytes = self.max_size_mb * 1024 * 1024
        self.allowed_extensions = {'.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG'}
        self.temp_storage = Path(settings.temp_storage_path)
        self.temp_storage.mkdir(parents=True, exist_ok=True)
    
    def validate_image(self, file_path: Path, file_size: int) -> bool:
        """
        Валидирует изображение.
        
        Args:
            file_path: Путь к файлу
            file_size: Размер файла в байтах
            
        Returns:
            bool: True если валидно
            
        Raises:
            ImageValidationError: Если изображение невалидно
        """
        # Проверка расширения
        if file_path.suffix not in self.allowed_extensions:
            raise ImageValidationError(
                f"Неподдерживаемый формат файла. "
                f"Поддерживаются: {', '.join(self.allowed_extensions)}"
            )
        
        # Проверка размера
        if file_size > self.max_size_bytes:
            raise ImageValidationError(
                f"Файл слишком большой. "
                f"Максимальный размер: {self.max_size_mb} МБ"
            )
        
        return True
    
    async def save_temp(self, file_data: bytes, filename: str) -> Path:
        """
        Сохраняет изображение во временное хранилище.
        
        Args:
            file_data: Данные файла
            filename: Имя файла
            
        Returns:
            Path: Путь к сохраненному файлу
        """
        # Генерируем уникальное имя файла
        import uuid
        file_id = uuid.uuid4().hex
        extension = Path(filename).suffix
        temp_filename = f"{file_id}{extension}"
        temp_path = self.temp_storage / temp_filename
        
        # Сохраняем файл
        async with aiofiles.open(temp_path, 'wb') as f:
            await f.write(file_data)
        
        logger.debug(f"Saved temp image: {temp_path}")
        return temp_path
    
    def cleanup(self, file_path: Path):
        """
        Удаляет временный файл.
        
        Args:
            file_path: Путь к файлу для удаления
        """
        try:
            if file_path.exists():
                file_path.unlink()
                logger.debug(f"Cleaned up temp file: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup file {file_path}: {e}")
