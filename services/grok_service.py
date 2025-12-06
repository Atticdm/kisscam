"""Сервис для работы с Grok API."""
import aiohttp
import asyncio
from pathlib import Path
from typing import List, Optional, Dict
from bot.config import settings
from utils.logger import setup_logger

logger = setup_logger(__name__)


class GrokAPIError(Exception):
    """Ошибка при работе с Grok API."""
    pass


class GrokService:
    """Сервис для взаимодействия с Grok API (xAI) и Kie.ai API."""
    
    # Глобальный семафор для ограничения одновременных API вызовов
    _api_semaphore: Optional[asyncio.Semaphore] = None
    
    # Глобальные HTTP сессии с connection pooling
    _grok_session: Optional[aiohttp.ClientSession] = None
    _kie_session: Optional[aiohttp.ClientSession] = None
    _download_session: Optional[aiohttp.ClientSession] = None
    
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
        
        # Инициализируем семафор если еще не создан
        if GrokService._api_semaphore is None:
            max_concurrent = getattr(settings, 'max_concurrent_api_calls', 10)
            GrokService._api_semaphore = asyncio.Semaphore(max_concurrent)
            logger.info(f"Initialized API semaphore with limit: {max_concurrent}")
    
    @property
    def api_semaphore(self) -> asyncio.Semaphore:
        """Получает семафор для ограничения одновременных API вызовов."""
        if GrokService._api_semaphore is None:
            max_concurrent = getattr(settings, 'max_concurrent_api_calls', 10)
            GrokService._api_semaphore = asyncio.Semaphore(max_concurrent)
        return GrokService._api_semaphore
    
    async def _get_grok_session(self) -> aiohttp.ClientSession:
        """Получает глобальную сессию для Grok API с connection pooling."""
        if GrokService._grok_session is None or GrokService._grok_session.closed:
            # Настраиваем connection pool для Grok API
            connector = aiohttp.TCPConnector(
                limit=50,  # Максимальное количество соединений
                limit_per_host=20,  # Максимальное количество соединений на хост
                ttl_dns_cache=300,  # Кэш DNS на 5 минут
                keepalive_timeout=30,  # Keep-alive соединений 30 секунд
                enable_cleanup_closed=True  # Автоматическая очистка закрытых соединений
            )
            timeout = aiohttp.ClientTimeout(total=120, connect=10)
            GrokService._grok_session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            )
            logger.info("Created Grok API session with connection pooling")
        return GrokService._grok_session
    
    async def _get_kie_session(self) -> aiohttp.ClientSession:
        """Получает глобальную сессию для Kie.ai API с connection pooling."""
        if GrokService._kie_session is None or GrokService._kie_session.closed:
            # Настраиваем connection pool для Kie.ai API
            connector = aiohttp.TCPConnector(
                limit=50,
                limit_per_host=20,
                ttl_dns_cache=300,
                keepalive_timeout=30,
                enable_cleanup_closed=True
            )
            timeout = aiohttp.ClientTimeout(total=120, connect=10)
            GrokService._kie_session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            )
            logger.info("Created Kie.ai API session with connection pooling")
        return GrokService._kie_session
    
    async def _get_download_session(self) -> aiohttp.ClientSession:
        """Получает глобальную сессию для скачивания файлов с connection pooling."""
        if GrokService._download_session is None or GrokService._download_session.closed:
            # Настраиваем connection pool для скачивания файлов
            connector = aiohttp.TCPConnector(
                limit=30,
                limit_per_host=10,
                ttl_dns_cache=300,
                keepalive_timeout=60,  # Дольше для больших файлов
                enable_cleanup_closed=True
            )
            timeout = aiohttp.ClientTimeout(total=300, connect=10)  # Больше времени для скачивания
            GrokService._download_session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout
            )
            logger.info("Created download session with connection pooling")
        return GrokService._download_session
    
    @classmethod
    async def close_sessions(cls):
        """Закрывает все HTTP сессии."""
        if cls._grok_session and not cls._grok_session.closed:
            await cls._grok_session.close()
            logger.info("Closed Grok API session")
        
        if cls._kie_session and not cls._kie_session.closed:
            await cls._kie_session.close()
            logger.info("Closed Kie.ai API session")
        
        if cls._download_session and not cls._download_session.closed:
            await cls._download_session.close()
            logger.info("Closed download session")
    
    async def _make_grok_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict] = None,
        headers: Optional[dict] = None
    ) -> dict:
        """Выполняет HTTP запрос к Grok API (xAI) с retry логикой и семафором."""
        if headers is None:
            headers = {
                "Authorization": f"Bearer {self.grok_api_key}",
                "Content-Type": "application/json"
            }
        
        url = f"{self.grok_api_url}/{endpoint}"
        
        # Используем семафор для ограничения одновременных запросов
        async with self.api_semaphore:
            session = await self._get_grok_session()
            for attempt in range(self.max_retries):
                try:
                    async with session.request(
                        method=method,
                        url=url,
                        json=data,
                        headers=headers
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
                    "Keep the exact same people from the original photo, do not create or add any new characters. "
                    "STRICTLY FORBIDDEN: Do NOT generate video if the photo contains children (people under 18) or military personnel. "
                    "If you detect children or military personnel in the image, do not proceed with generation."
                )
            else:
                prompt = (
                    "Combine ONLY the people from these two photos. "
                    "Do NOT add any new people or characters that are not in the original images. "
                    "Animate them moving towards each other and kissing smoothly and realistically. "
                    "Use only the people that exist in the provided photos, do not create or add any additional characters. "
                    "STRICTLY FORBIDDEN: Do NOT generate video if any photo contains children (people under 18) or military personnel. "
                    "If you detect children or military personnel in any image, do not proceed with generation."
                )
            
            # Запрос к Kie.ai Grok Imagine API
            # Правильный формат согласно документации: /api/v1/jobs/createTask
            # Используем только первое изображение, так как API поддерживает только одно изображение
            # ВАЖНО: Spicy режим работает только с изображениями, сгенерированными через Grok на Kie.ai
            # Для внешних изображений (image_urls) spicy автоматически переключается на normal
            
            # Проверяем доступность URL перед отправкой в Kie.ai
            image_url = image_urls[0]
            logger.info(f"Checking accessibility of Telegram file URL: {image_url}")
            
            # Проверяем, что URL доступен (делаем HEAD запрос)
            try:
                download_session = await self._get_download_session()
                async with download_session.head(
                    image_url,
                    allow_redirects=True
                ) as check_response:
                    if check_response.status != 200:
                        logger.warning(f"Telegram URL returned status {check_response.status}, but proceeding anyway")
                    else:
                        logger.info(f"Telegram URL is accessible (status {check_response.status})")
            except Exception as e:
                logger.warning(f"Could not verify URL accessibility: {e}, but proceeding anyway")
            
            # Формируем запрос согласно документации Kie.ai API
            # Используем публичные URL от Telegram
            request_data = {
                "model": "grok-imagine/image-to-video",
                "input": {
                    "image_urls": [image_url],  # Публичный URL от Telegram
                    "prompt": prompt,
                    "mode": "spicy"  # spicy режим (для внешних изображений автоматически переключится на normal)
                }
            }
            
            logger.info("Using spicy mode for video generation (will auto-switch to normal for external images)")
            logger.info(f"Requesting video generation for {len(image_urls)} image(s) using Kie.ai API")
            logger.info(f"Using Telegram file URL: {image_url}")
            logger.debug(f"Request data structure: {request_data}")
            
            # Выполняем запрос к Kie.ai API
            headers = {
                "Authorization": f"Bearer {self.kie_api_key}",
                "Content-Type": "application/json"
            }
            
            # Создаем задачу с использованием семафора
            task_id = None
            async with self.api_semaphore:
                session = await self._get_kie_session()
                for attempt in range(self.max_retries):
                    try:
                        async with session.post(
                            self.kie_create_task_endpoint,
                            json=request_data,
                            headers=headers
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
                
                # Используем семафор для запросов статуса (более мягкий лимит)
                async with self.api_semaphore:
                    try:
                        session = await self._get_kie_session()
                        async with session.get(
                            f"{self.kie_record_info_endpoint}?taskId={task_id}",
                            headers=headers
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
                                    
                                    # Скачиваем видео используя глобальную сессию
                                    download_session = await self._get_download_session()
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
    
    async def check_prohibited_content(self, image_path: Path) -> Dict[str, bool]:
        """
        Проверяет изображение на наличие запрещенного контента (дети, военные).
        
        Args:
            image_path: Путь к изображению
            
        Returns:
            dict: {
                "has_children": bool - обнаружены ли дети,
                "has_military": bool - обнаружены ли военные,
                "is_prohibited": bool - запрещен ли контент
            }
            
        Raises:
            GrokAPIError: При ошибке API
        """
        try:
            # Читаем изображение
            with open(image_path, 'rb') as f:
                import base64
                img_data = base64.b64encode(f.read()).decode('utf-8')
            
            prompt = (
                "Analyze this image and determine if it contains:\n"
                "1. Children (people under 18 years old, minors, kids)\n"
                "2. Military personnel (soldiers, people in military uniforms, armed forces)\n\n"
                "Respond ONLY with a JSON object in this exact format:\n"
                '{"has_children": true/false, "has_military": true/false}\n\n'
                "Be strict: if you see any indication of children or military, mark it as true."
            )
            
            request_data = {
                "model": "grok-2-vision-1212",
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
                "max_tokens": 100
            }
            
            response = await self._make_grok_request("POST", "chat/completions", data=request_data)
            
            if "choices" in response and len(response["choices"]) > 0:
                content = response["choices"][0].get("message", {}).get("content", "").strip()
                
                # Пытаемся извлечь JSON из ответа
                import json
                import re
                
                # Ищем JSON объект в ответе
                json_match = re.search(r'\{[^}]+\}', content)
                if json_match:
                    try:
                        result = json.loads(json_match.group())
                        has_children = result.get("has_children", False)
                        has_military = result.get("has_military", False)
                        is_prohibited = has_children or has_military
                        
                        logger.info(
                            f"Content check result: children={has_children}, "
                            f"military={has_military}, prohibited={is_prohibited}"
                        )
                        
                        return {
                            "has_children": has_children,
                            "has_military": has_military,
                            "is_prohibited": is_prohibited
                        }
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse JSON from response: {content}")
                
                # Если JSON не найден, проверяем текстовый ответ
                content_lower = content.lower()
                has_children = any(word in content_lower for word in ["true", "yes", "child", "kid", "minor"])
                has_military = any(word in content_lower for word in ["true", "yes", "military", "soldier", "uniform"])
                
                # Более строгая проверка: если в ответе есть упоминание детей или военных
                if "has_children" in content_lower and "true" in content_lower:
                    has_children = True
                if "has_military" in content_lower and "true" in content_lower:
                    has_military = True
                
                is_prohibited = has_children or has_military
                
                logger.info(
                    f"Content check result (text parsing): children={has_children}, "
                    f"military={has_military}, prohibited={is_prohibited}"
                )
                
                return {
                    "has_children": has_children,
                    "has_military": has_military,
                    "is_prohibited": is_prohibited
                }
            
            # Если не удалось определить, считаем что контент разрешен (но логируем)
            logger.warning("Could not determine prohibited content, allowing by default")
            return {
                "has_children": False,
                "has_military": False,
                "is_prohibited": False
            }
            
        except Exception as e:
            logger.error(f"Error checking prohibited content: {e}", exc_info=True)
            # При ошибке считаем что контент разрешен (но логируем)
            # Это безопаснее чем блокировать всех пользователей при сбое API
            return {
                "has_children": False,
                "has_military": False,
                "is_prohibited": False
            }
