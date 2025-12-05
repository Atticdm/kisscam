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
    """Сервис для взаимодействия с Grok API (xAI) и Kie.ai API."""
    
    def __init__(self):
        # Grok API (xAI) - для анализа изображений
        self.grok_api_key = settings.grok_api_key
        self.grok_api_url = settings.grok_api_url
        self.grok_base_url = f"{self.grok_api_url}/chat/completions"
        
        # Kie.ai API - для генерации видео
        self.kie_api_key = settings.kie_ai_api_key
        self.kie_api_url = settings.kie_ai_api_url
        self.kie_video_endpoint = f"{self.kie_api_url}/grok-imagine/image-to-video"
        
        self.max_retries = 3
        self.retry_delay = 5
        
    async def _make_grok_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict] = None,
        headers: Optional[dict] = None
    ) -> dict:
        """Выполняет HTTP запрос к Grok API (xAI) с retry логикой."""
        if headers is None:
            headers = {
                "Authorization": f"Bearer {self.grok_api_key}",
                "Content-Type": "application/json"
            }
        
        url = f"{self.grok_api_url}/{endpoint}"
        
        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.request(
                        method=method,
                        url=url,
                        json=data,
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
        Генерирует видео с целующимися людьми через Kie.ai Grok Imagine API.
        
        Args:
            image_paths: Список путей к изображениям (1 или 2)
            num_people: Количество людей на изображениях (опционально)
            
        Returns:
            bytes: Видео файл в формате MP4
            
        Raises:
            GrokAPIError: При ошибке API
        """
        try:
            # Загружаем изображения и конвертируем в base64 для загрузки
            import base64
            image_data_list = []
            
            for img_path in image_paths:
                with open(img_path, 'rb') as f:
                    img_bytes = f.read()
                    # Конвертируем в base64 data URL
                    img_base64 = base64.b64encode(img_bytes).decode('utf-8')
                    # Определяем MIME type по расширению
                    ext = img_path.suffix.lower()
                    mime_type = "image/jpeg" if ext in ['.jpg', '.jpeg'] else "image/png"
                    image_data_list.append(f"data:{mime_type};base64,{img_base64}")
            
            # Формируем промпт для генерации видео
            if len(image_paths) == 1:
                prompt = (
                    "Animate the people in this photo to kiss each other. "
                    "Show them moving towards each other and kissing smoothly. "
                    "If there are multiple people, show them all kissing each other."
                )
            else:
                prompt = (
                    "Combine the people from both photos and animate them kissing each other. "
                    "Show them moving towards each other and kissing smoothly and realistically."
                )
            
            # Запрос к Kie.ai Grok Imagine API
            # Используем только первое изображение, так как API поддерживает только одно изображение
            request_data = {
                "image_urls": [image_data_list[0]],  # Kie.ai принимает data URL или внешний URL
                "prompt": prompt,
                "mode": "normal"  # normal, fun, или spicy
            }
            
            logger.info(f"Requesting video generation for {len(image_paths)} image(s) using Kie.ai API")
            logger.debug(f"Request data keys: {list(request_data.keys())}")
            
            # Выполняем запрос к Kie.ai API
            headers = {
                "Authorization": f"Bearer {self.kie_api_key}",
                "Content-Type": "application/json"
            }
            
            for attempt in range(self.max_retries):
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            self.kie_video_endpoint,
                            json=request_data,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=120)
                        ) as response:
                            if response.status == 200:
                                result = await response.json()
                                logger.debug(f"Kie.ai API response: {result}")
                                
                                # Обработка ответа от Kie.ai
                                # Формат ответа может быть разным, проверяем несколько вариантов
                                video_url = None
                                
                                if isinstance(result, dict):
                                    # Ищем URL видео в разных возможных полях
                                    video_url = (
                                        result.get("video_url") or
                                        result.get("video") or
                                        result.get("output") or
                                        result.get("url")
                                    )
                                    
                                    # Если это словарь с вложенными данными
                                    if isinstance(video_url, dict):
                                        video_url = video_url.get("url") or video_url.get("video_url")
                                
                                if video_url:
                                    logger.info(f"Found video URL: {video_url}")
                                    # Скачиваем видео
                                    async with aiohttp.ClientSession() as download_session:
                                        async with download_session.get(video_url) as video_resp:
                                            if video_resp.status == 200:
                                                video_bytes = await video_resp.read()
                                                logger.info(f"Downloaded video: {len(video_bytes)} bytes")
                                                return video_bytes
                                            else:
                                                logger.error(f"Failed to download video: HTTP {video_resp.status}")
                                
                                # Если URL не найден, возможно видео в base64
                                if isinstance(result, dict):
                                    video_data = result.get("video_data") or result.get("data")
                                    if video_data and isinstance(video_data, str):
                                        if video_data.startswith("data:video"):
                                            # Извлекаем base64 данные
                                            base64_data = video_data.split(",")[1]
                                            video_bytes = base64.b64decode(base64_data)
                                            logger.info(f"Decoded base64 video: {len(video_bytes)} bytes")
                                            return video_bytes
                                
                                logger.error(f"Unexpected response format from Kie.ai: {result}")
                                raise GrokAPIError(f"Kie.ai API returned unexpected format: {str(result)[:500]}")
                            
                            elif response.status == 429:
                                # Rate limit
                                wait_time = self.retry_delay * (2 ** attempt)
                                logger.warning(f"Rate limit exceeded. Waiting {wait_time}s")
                                await asyncio.sleep(wait_time)
                                continue
                            else:
                                error_text = await response.text()
                                logger.error(f"Kie.ai API error {response.status}: {error_text}")
                                raise GrokAPIError(f"Kie.ai API returned status {response.status}: {error_text}")
                
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
            
            response = await self._make_grok_request("POST", "chat/completions", data=request_data)
            
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
