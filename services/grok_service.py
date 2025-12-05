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
            
            # Формируем промпт для Grok Imagine (генерация видео)
            if len(image_paths) == 1:
                prompt = (
                    "Create an animated video (3-5 seconds) where the people in this photo are kissing each other. "
                    "Animate the photo to show people moving towards each other and kissing. "
                    "Make it realistic and smooth. If there are multiple people, show them all kissing each other."
                )
            else:
                prompt = (
                    "Create an animated video (3-5 seconds) where the people from these two photos are kissing each other. "
                    "Combine the people from both photos into one scene and animate them moving towards each other and kissing. "
                    "Make it realistic and seamless."
                )
            
            # Запрос к Grok API через chat completions
            # Пробуем использовать grok-2-image-1212 для генерации видео (Grok Imagine)
            # или grok-2-vision-1212 если первая не работает
            request_data = {
                "model": "grok-2-image-1212",  # Image model может генерировать видео через Imagine
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            *images_data
                        ]
                    }
                ],
                "max_tokens": 2000  # Увеличиваем для видео
            }
            
            logger.info(f"Requesting video generation for {len(image_paths)} image(s) using grok-2-image-1212")
            logger.debug(f"Request data: {request_data}")
            
            try:
                response = await self._make_request("POST", "chat/completions", data=request_data)
            except GrokAPIError as e:
                # Если grok-2-image-1212 не поддерживает видео, пробуем grok-2-vision-1212
                logger.warning(f"grok-2-image-1212 failed, trying grok-2-vision-1212: {e}")
                request_data["model"] = "grok-2-vision-1212"
                response = await self._make_request("POST", "chat/completions", data=request_data)
            
            logger.debug(f"Grok API response: {response}")
            
            # Обработка ответа
            # Примечание: Точный формат ответа нужно уточнить по документации Grok API
            # Возможно, API возвращает URL видео или base64 данные
            if "choices" in response and len(response["choices"]) > 0:
                content = response["choices"][0].get("message", {}).get("content", "")
                logger.info(f"Received content from Grok API (length: {len(content)})")
                
                # Если API возвращает URL видео
                if "http" in content or "https://" in content:
                    # Извлекаем URL
                    import re
                    url_match = re.search(r'https?://[^\s<>"{}|\\^`\[\]]+', content)
                    if url_match:
                        video_url = url_match.group(0)
                        logger.info(f"Found video URL: {video_url}")
                        # Скачиваем видео по URL
                        async with aiohttp.ClientSession() as session:
                            async with session.get(video_url) as resp:
                                if resp.status == 200:
                                    video_bytes = await resp.read()
                                    logger.info(f"Downloaded video: {len(video_bytes)} bytes")
                                    return video_bytes
                                else:
                                    logger.error(f"Failed to download video: HTTP {resp.status}")
                
                # Если API возвращает base64 видео
                if "data:video" in content or "base64" in content.lower():
                    import base64
                    # Ищем base64 данные
                    base64_match = re.search(r'data:video/[^;]+;base64,([A-Za-z0-9+/=]+)', content)
                    if base64_match:
                        video_data = base64.b64decode(base64_match.group(1))
                        logger.info(f"Decoded base64 video: {len(video_data)} bytes")
                        return video_data
                
                # Проверяем, может быть API вернул структурированные данные с видео
                # Grok Imagine может возвращать видео в специальном формате
                if isinstance(content, dict):
                    # Если content - это словарь, ищем видео данные
                    if "video_url" in content:
                        video_url = content["video_url"]
                        logger.info(f"Found video URL in response: {video_url}")
                        async with aiohttp.ClientSession() as session:
                            async with session.get(video_url) as resp:
                                if resp.status == 200:
                                    video_bytes = await resp.read()
                                    logger.info(f"Downloaded video: {len(video_bytes)} bytes")
                                    return video_bytes
                    
                    if "video" in content:
                        video_data = content["video"]
                        if isinstance(video_data, str) and video_data.startswith("http"):
                            # Это URL
                            async with aiohttp.ClientSession() as session:
                                async with session.get(video_data) as resp:
                                    if resp.status == 200:
                                        return await resp.read()
                        elif isinstance(video_data, str):
                            # Это base64
                            import base64
                            return base64.b64decode(video_data)
                
                # Если контент - это просто текст с описанием
                logger.warning(f"Grok API returned text instead of video: {content[:200]}")
                logger.info(f"Full response content type: {type(content)}")
                logger.info(f"Full response: {str(content)[:1000]}")
                raise GrokAPIError(
                    f"Grok API returned text response instead of video. "
                    f"Response: {str(content)[:500]}"
                )
            
            logger.error(f"Unexpected response format: {response}")
            raise GrokAPIError(f"Unexpected response format from API: {str(response)[:500]}")
                    
        except GrokAPIError:
            # Пробрасываем GrokAPIError как есть
            raise
            except Exception as e:
            logger.error(f"Error generating video: {e}", exc_info=True)
            logger.error(f"Error type: {type(e).__name__}")
            logger.error(f"Error details: {str(e)}")
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
                "model": "grok-2-vision-1212",  # Vision model для анализа изображений
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
