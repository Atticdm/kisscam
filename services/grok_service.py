"""Сервис для работы с Grok API."""
import aiohttp
import asyncio
from pathlib import Path
from typing import List, Optional
from bot.config import settings
from utils.logger import setup_logger

logger = setup_logger(__name__)


class GrokAPIError(Exception):
    """Ошибка при работе с Grok API."""
    pass


class GrokService:
    """Сервис для взаимодействия с Grok API."""
    
    def __init__(self):
        self.api_key = settings.grok_api_key
        self.api_url = settings.grok_api_url
        self.base_url = f"{self.api_url}/chat/completions"
        self.max_retries = 3
        self.retry_delay = 5
        
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict] = None,
        files: Optional[dict] = None,
        headers: Optional[dict] = None
    ) -> dict:
        """Выполняет HTTP запрос к Grok API с retry логикой."""
        if headers is None:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
        
        url = f"{self.api_url}/{endpoint}"
        
        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.request(
                        method=method,
                        url=url,
                        json=data,
                        data=files,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=120)
                    ) as response:
                        if response.status == 200:
                            return await response.json()
                        elif response.status == 429:
                            # Rate limit
                            wait_time = self.retry_delay * (2 ** attempt)
                            logger.warning(f"Rate limit exceeded. Waiting {wait_time}s")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            error_text = await response.text()
                            logger.error(f"API error {response.status}: {error_text}")
                            raise GrokAPIError(f"API returned status {response.status}: {error_text}")
                            
            except asyncio.TimeoutError:
                logger.warning(f"Request timeout, attempt {attempt + 1}/{self.max_retries}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))
                else:
                    raise GrokAPIError("Request timeout after retries")
            except aiohttp.ClientError as e:
                logger.error(f"Client error: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(self.retry_delay * (2 ** attempt))
                else:
                    raise GrokAPIError(f"Client error: {e}")
        
        raise GrokAPIError("Max retries exceeded")
    
    async def generate_kissing_video(
        self,
        image_paths: List[Path],
        num_people: Optional[int] = None
    ) -> bytes:
        """
        Генерирует видео с целующимися людьми через Grok API.
        
        Args:
            image_paths: Список путей к изображениям (1 или 2)
            num_people: Количество людей на изображениях (опционально)
            
        Returns:
            bytes: Видео файл в формате MP4
            
        Raises:
            GrokAPIError: При ошибке API
        """
        try:
            # Читаем изображения
            images_data = []
            for img_path in image_paths:
                with open(img_path, 'rb') as f:
                    import base64
                    img_data = base64.b64encode(f.read()).decode('utf-8')
                    images_data.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_data}"
                        }
                    })
            
            # Формируем промпт для Grok
            if len(image_paths) == 1:
                prompt = (
                    "Create a short video (3-5 seconds) where the people in this photo "
                    "are kissing each other. Make it realistic and smooth."
                )
            else:
                prompt = (
                    "Create a short video (3-5 seconds) where the people from these two photos "
                    "are kissing each other. Combine them naturally and make the animation smooth."
                )
            
            # Запрос к Grok API через chat completions
            request_data = {
                "model": "grok-beta",  # Может потребоваться уточнение модели
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            *images_data
                        ]
                    }
                ],
                "max_tokens": 1000
            }
            
            logger.info(f"Requesting video generation for {len(image_paths)} image(s)")
            response = await self._make_request("POST", "chat/completions", data=request_data)
            
            # Обработка ответа
            # Примечание: Точный формат ответа нужно уточнить по документации Grok API
            # Возможно, API возвращает URL видео или base64 данные
            if "choices" in response and len(response["choices"]) > 0:
                content = response["choices"][0].get("message", {}).get("content", "")
                
                # Если API возвращает URL видео
                if "http" in content:
                    # Скачиваем видео по URL
                    async with aiohttp.ClientSession() as session:
                        async with session.get(content) as resp:
                            if resp.status == 200:
                                return await resp.read()
                
                # Если API возвращает base64 видео
                if "data:video" in content:
                    import base64
                    video_data = content.split(",")[1]
                    return base64.b64decode(video_data)
            
            raise GrokAPIError("Unexpected response format from API")
                    
        except Exception as e:
            logger.error(f"Error generating video: {e}")
            raise GrokAPIError(f"Failed to generate video: {str(e)}")
    
    async def detect_people(self, image_path: Path) -> int:
        """
        Определяет количество людей на изображении.
        
        Args:
            image_path: Путь к изображению
            
        Returns:
            int: Количество людей
        """
        try:
            # Читаем изображение
            with open(image_path, 'rb') as f:
                import base64
                img_data = base64.b64encode(f.read()).decode('utf-8')
            
            prompt = (
                "Count how many people are in this photo. "
                "Return only the number, nothing else."
            )
            
            request_data = {
                "model": "grok-beta",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{img_data}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 10
            }
            
            response = await self._make_request("POST", "chat/completions", data=request_data)
            
            if "choices" in response and len(response["choices"]) > 0:
                content = response["choices"][0].get("message", {}).get("content", "")
                # Пытаемся извлечь число
                import re
                numbers = re.findall(r'\d+', content)
                if numbers:
                    return int(numbers[0])
            
            # Если не удалось определить, возвращаем 2 по умолчанию
            logger.warning("Could not detect number of people, defaulting to 2")
            return 2
            
        except Exception as e:
            logger.error(f"Error detecting people: {e}")
            # Возвращаем 2 по умолчанию
            return 2
