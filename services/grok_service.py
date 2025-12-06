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
        self.kie_create_task_endpoint = f"{self.kie_api_url}/api/v1/jobs/createTask"
        self.kie_record_info_endpoint = f"{self.kie_api_url}/api/v1/jobs/recordInfo"
        
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
        image_urls: List[str],
        num_people: Optional[int] = None
    ) -> bytes:
        """
        Генерирует видео с целующимися людьми через Kie.ai Grok Imagine API.
        
        Args:
            image_urls: Список публичных URL изображений (1 или 2)
            num_people: Количество людей на изображениях (опционально)
            
        Returns:
            bytes: Видео файл в формате MP4
            
        Raises:
            GrokAPIError: При ошибке API
        """
        try:
            # Используем публичные URL изображений напрямую
            # Kie.ai API требует внешние URL, а не base64 данные
            
            # Формируем промпт для генерации видео
            if len(image_urls) == 1:
                prompt = (
                    "Animate ONLY the people that are already in this photo. "
                    "Do NOT add any new people or characters that are not in the original image. "
                    "If there are multiple people in the photo, show them moving towards each other and kissing smoothly. "
                    "If there is only one person in the photo, show them miming a kiss with the air - "
                    "they should move as if kissing someone, but no other person should appear in the video. "
                    "Keep the exact same people from the original photo, do not create or add any new characters."
                )
            else:
                prompt = (
                    "Combine ONLY the people from these two photos. "
                    "Do NOT add any new people or characters that are not in the original images. "
                    "Animate them moving towards each other and kissing smoothly and realistically. "
                    "Use only the people that exist in the provided photos, do not create or add any additional characters."
                )
            
            # Запрос к Kie.ai Grok Imagine API
            # Правильный формат согласно документации: /api/v1/jobs/createTask
            # Используем только первое изображение, так как API поддерживает только одно изображение
            # ВАЖНО: Spicy режим работает только с изображениями, сгенерированными через Grok на Kie.ai
            # Для внешних изображений (image_urls) spicy автоматически переключается на normal
            
            # Формируем запрос согласно документации Kie.ai API
            # Используем публичные URL от Telegram
            request_data = {
                "model": "grok-imagine/image-to-video",
                "input": {
                    "image_urls": [image_urls[0]],  # Публичный URL от Telegram
                    "prompt": prompt,
                    "mode": "spicy"  # spicy режим (для внешних изображений автоматически переключится на normal)
                }
            }
            
            logger.info("Using spicy mode for video generation (will auto-switch to normal for external images)")
            logger.info(f"Requesting video generation for {len(image_urls)} image(s) using Kie.ai API")
            logger.info(f"Using Telegram file URL: {image_urls[0]}")
            logger.debug(f"Request data structure: model and input keys")
            
            # Выполняем запрос к Kie.ai API
            headers = {
                "Authorization": f"Bearer {self.kie_api_key}",
                "Content-Type": "application/json"
            }
            
            # Создаем задачу
            task_id = None
            for attempt in range(self.max_retries):
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            self.kie_create_task_endpoint,
                            json=request_data,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=120)
                        ) as response:
                            if response.status == 200:
                                result = await response.json()
                                logger.debug(f"Kie.ai createTask response: {result}")
                                
                                # Получаем task_id из ответа
                                # API возвращает taskId внутри объекта data
                                task_id = None
                                if isinstance(result, dict):
                                    # Проверяем вложенный объект data
                                    data = result.get("data", {})
                                    if isinstance(data, dict):
                                        task_id = data.get("taskId") or data.get("task_id") or data.get("id")
                                    # Также проверяем корневой уровень на случай другого формата
                                    if not task_id:
                                        task_id = result.get("task_id") or result.get("taskId") or result.get("id")
                                
                                if not task_id:
                                    logger.error(f"No task_id in response: {result}")
                                    raise GrokAPIError(f"Kie.ai API did not return task_id: {str(result)[:500]}")
                                
                                logger.info(f"Task created with ID: {task_id}")
                                break
                            
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
            
            if not task_id:
                raise GrokAPIError("Failed to create task after retries")
            
            # Опрашиваем статус задачи до завершения
            max_polls = 60  # Максимум 60 попыток (5 минут при интервале 5 секунд)
            poll_interval = 5  # Проверяем каждые 5 секунд
            
            for poll_attempt in range(max_polls):
                await asyncio.sleep(poll_interval)
                
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            f"{self.kie_record_info_endpoint}?taskId={task_id}",
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=30)
                        ) as response:
                            if response.status == 200:
                                result = await response.json()
                                logger.debug(f"Kie.ai recordInfo response: {result}")
                                
                                # Проверяем статус задачи согласно документации
                                # Статус находится в data.state: waiting, success, fail
                                data = result.get("data", {})
                                if not isinstance(data, dict):
                                    logger.error(f"Invalid data format in response: {result}")
                                    if poll_attempt < max_polls - 1:
                                        continue
                                    else:
                                        raise GrokAPIError("Invalid response format from Kie.ai API")
                                
                                state = data.get("state")
                                
                                if state == "success":
                                    # Задача завершена успешно, получаем видео из resultJson
                                    result_json_str = data.get("resultJson")
                                    if not result_json_str:
                                        logger.error(f"No resultJson in response: {result}")
                                        raise GrokAPIError("Task completed but no resultJson found")
                                    
                                    # Парсим JSON строку из resultJson
                                    import json
                                    try:
                                        result_json = json.loads(result_json_str)
                                    except json.JSONDecodeError as e:
                                        logger.error(f"Failed to parse resultJson: {result_json_str}")
                                        raise GrokAPIError(f"Invalid JSON in resultJson: {str(e)}")
                                    
                                    # Извлекаем URL видео из resultUrls
                                    result_urls = result_json.get("resultUrls", [])
                                    if not result_urls or len(result_urls) == 0:
                                        logger.error(f"No resultUrls in resultJson: {result_json}")
                                        raise GrokAPIError("Task completed but no video URLs found")
                                    
                                    video_url = result_urls[0]  # Берем первый URL
                                    logger.info(f"Task completed, found video URL: {video_url}")
                                    
                                    # Скачиваем видео
                                    async with aiohttp.ClientSession() as download_session:
                                        async with download_session.get(video_url) as video_resp:
                                            if video_resp.status == 200:
                                                video_bytes = await video_resp.read()
                                                logger.info(f"Downloaded video: {len(video_bytes)} bytes")
                                                return video_bytes
                                            else:
                                                logger.error(f"Failed to download video: HTTP {video_resp.status}")
                                                raise GrokAPIError(f"Failed to download video: HTTP {video_resp.status}")
                                
                                elif state == "fail":
                                    # Задача завершилась с ошибкой
                                    fail_msg = data.get("failMsg") or data.get("failCode") or "Unknown error"
                                    logger.error(f"Task failed: {fail_msg}")
                                    raise GrokAPIError(f"Task failed: {fail_msg}")
                                
                                elif state == "waiting":
                                    # Задача еще обрабатывается
                                    logger.info(f"Task {task_id} is still waiting/processing (attempt {poll_attempt + 1}/{max_polls})")
                                    continue
                                
                                else:
                                    logger.warning(f"Unknown task state: {state}")
                                    continue
                            
                            else:
                                error_text = await response.text()
                                logger.error(f"Kie.ai recordInfo error {response.status}: {error_text}")
                                if poll_attempt < max_polls - 1:
                                    continue
                                else:
                                    raise GrokAPIError(f"Failed to query task status: {response.status}")
                
                except asyncio.TimeoutError:
                    logger.warning(f"Query timeout, attempt {poll_attempt + 1}/{max_polls}")
                    if poll_attempt < max_polls - 1:
                        continue
                    else:
                        raise GrokAPIError("Task query timeout")
                except GrokAPIError:
                    raise
                except Exception as e:
                    logger.error(f"Error querying task: {e}")
                    if poll_attempt < max_polls - 1:
                        continue
                    else:
                        raise GrokAPIError(f"Failed to query task: {str(e)}")
            
            raise GrokAPIError("Task did not complete within timeout period")
                    
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
