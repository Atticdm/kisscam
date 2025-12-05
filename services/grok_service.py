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
            
            # Формируем детальный промпт для Grok
            if len(image_paths) == 1:
                prompt = (
                    "You are a video generation AI. Your task is to create a short animated video (3-5 seconds) "
                    "where the people in the provided photo are kissing each other.\n\n"
                    "Requirements:\n"
                    "- The video should be realistic and smooth\n"
                    "- People should naturally move towards each other and kiss\n"
                    "- If there are multiple people, they should all kiss each other\n"
                    "- The animation should be seamless and natural\n"
                    "- Output format: MP4 video file\n\n"
                    "Generate the video now and return it as a video file or provide a download URL."
                )
            else:
                prompt = (
                    "You are a video generation AI. Your task is to create a short animated video (3-5 seconds) "
                    "where the people from the two provided photos are kissing each other.\n\n"
                    "Requirements:\n"
                    "- Combine people from both photos naturally in one scene\n"
                    "- People should move towards each other and kiss\n"
                    "- The animation should be seamless and realistic\n"
                    "- Output format: MP4 video file\n\n"
                    "Generate the video now and return it as a video file or provide a download URL."
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
            logger.debug(f"Request data: {request_data}")
            
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
                
                # Если контент - это просто текст с описанием
                logger.warning(f"Grok API returned text instead of video: {content[:200]}")
                raise GrokAPIError(
                    f"Grok API returned text response instead of video. "
                    f"Response: {content[:500]}"
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
