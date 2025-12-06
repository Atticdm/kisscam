"""Сервис очереди задач для обработки фотографий."""
import asyncio
from dataclasses import dataclass
from typing import Optional, Callable, Awaitable, Any
from enum import Enum
from datetime import datetime
from bot.config import settings
from utils.logger import setup_logger

logger = setup_logger(__name__)


class TaskStatus(Enum):
    """Статус задачи."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class VideoGenerationTask:
    """Задача на генерацию видео."""
    task_id: str
    user_id: int
    message: Any  # Message объект от aiogram
    task_type: str  # "single" или "two"
    photo_data: dict  # Данные фотографий
    created_at: datetime
    status: TaskStatus = TaskStatus.PENDING
    position: int = 0
    status_message: Optional[Any] = None  # Сообщение со статусом для обновления
    processor: Optional[Callable[[Any], Awaitable[None]]] = None  # Функция-процессор


class TaskQueue:
    """Очередь задач для обработки фотографий."""
    
    def __init__(self, max_workers: int = 5):
        """
        Инициализирует очередь задач.
        
        Args:
            max_workers: Максимальное количество одновременных обработок
        """
        self.queue: asyncio.Queue = asyncio.Queue()
        self.max_workers = max_workers
        self.workers: list[asyncio.Task] = []
        self.active_tasks: dict[str, VideoGenerationTask] = {}
        self.task_counter = 0
        self._lock = asyncio.Lock()
        self._running = False
        
    async def start(self):
        """Запускает воркеры для обработки очереди."""
        if self._running:
            logger.warning("Task queue is already running")
            return
        
        self._running = True
        logger.info(f"Starting task queue with {self.max_workers} workers")
        
        # Запускаем воркеры
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker(f"worker-{i+1}"))
            self.workers.append(worker)
            logger.info(f"Started worker {i+1}/{self.max_workers}")
    
    async def stop(self):
        """Останавливает воркеры."""
        if not self._running:
            return
        
        logger.info("Stopping task queue...")
        self._running = False
        
        # Ждем завершения всех задач
        await self.queue.join()
        
        # Отменяем воркеры
        for worker in self.workers:
            worker.cancel()
        
        # Ждем завершения воркеров
        await asyncio.gather(*self.workers, return_exceptions=True)
        self.workers.clear()
        logger.info("Task queue stopped")
    
    async def add_task(
        self,
        user_id: int,
        message: Any,
        task_type: str,
        photo_data: dict,
        processor: Callable[[VideoGenerationTask], Awaitable[None]]
    ) -> VideoGenerationTask:
        """
        Добавляет задачу в очередь.
        
        Args:
            user_id: ID пользователя
            message: Объект сообщения от aiogram
            task_type: Тип задачи ("single" или "two")
            photo_data: Данные фотографий
            processor: Функция для обработки задачи
            
        Returns:
            VideoGenerationTask: Созданная задача
        """
        async with self._lock:
            self.task_counter += 1
            task_id = f"task-{self.task_counter}-{user_id}"
        
        task = VideoGenerationTask(
            task_id=task_id,
            user_id=user_id,
            message=message,
            task_type=task_type,
            photo_data=photo_data,
            created_at=datetime.now(),
            status=TaskStatus.PENDING,
            processor=processor
        )
        
        # Вычисляем позицию в очереди
        task.position = self.queue.qsize() + 1
        
        await self.queue.put(task)
        self.active_tasks[task_id] = task
        
        logger.info(
            f"Task {task_id} added to queue (user {user_id}, "
            f"position {task.position}, type {task_type})"
        )
        
        return task
    
    async def get_queue_position(self, task_id: str) -> int:
        """
        Получает позицию задачи в очереди.
        
        Args:
            task_id: ID задачи
            
        Returns:
            int: Позиция в очереди (0 если задача обрабатывается или не найдена)
        """
        if task_id not in self.active_tasks:
            return 0
        
        task = self.active_tasks[task_id]
        if task.status == TaskStatus.PROCESSING:
            return 0
        
        # Подсчитываем количество задач перед этой
        position = 1
        for queued_task in list(self.active_tasks.values()):
            if queued_task.task_id == task_id:
                break
            if queued_task.status == TaskStatus.PENDING:
                position += 1
        
        return position
    
    async def get_queue_size(self) -> int:
        """
        Получает размер очереди.
        
        Returns:
            int: Количество задач в очереди
        """
        return self.queue.qsize()
    
    async def _worker(self, worker_name: str):
        """Воркер для обработки задач из очереди."""
        logger.info(f"{worker_name} started")
        
        while self._running:
            try:
                # Получаем задачу из очереди (с таймаутом для проверки _running)
                try:
                    task = await asyncio.wait_for(
                        self.queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                task.status = TaskStatus.PROCESSING
                logger.info(f"{worker_name} processing task {task.task_id} (user {task.user_id})")
                
                try:
                    # Обрабатываем задачу
                    if task.processor:
                        await task.processor(task)
                    else:
                        logger.error(f"Task {task.task_id} has no processor")
                        task.status = TaskStatus.FAILED
                    
                    if task.status == TaskStatus.PROCESSING:
                        # Если статус не изменился, считаем успешным
                        task.status = TaskStatus.COMPLETED
                        logger.info(f"{worker_name} completed task {task.task_id}")
                    
                except Exception as e:
                    logger.error(
                        f"{worker_name} failed to process task {task.task_id}: {e}",
                        exc_info=True
                    )
                    task.status = TaskStatus.FAILED
                    
                    # Отправляем сообщение об ошибке пользователю
                    try:
                        await task.message.answer(
                            "❌ Произошла ошибка при обработке вашей задачи. "
                            "Попробуйте отправить фотографию заново."
                        )
                    except Exception as send_error:
                        logger.error(f"Failed to send error message: {send_error}")
                
                finally:
                    # Удаляем задачу из активных
                    self.active_tasks.pop(task.task_id, None)
                    # Помечаем задачу как выполненную
                    self.queue.task_done()
                    
            except asyncio.CancelledError:
                logger.info(f"{worker_name} cancelled")
                break
            except Exception as e:
                logger.error(f"{worker_name} error: {e}", exc_info=True)
                await asyncio.sleep(1)  # Небольшая задержка перед следующей попыткой
        
        logger.info(f"{worker_name} stopped")


# Глобальный экземпляр очереди задач
_task_queue: Optional[TaskQueue] = None


def get_task_queue() -> TaskQueue:
    """
    Получает глобальный экземпляр очереди задач.
    
    Returns:
        TaskQueue: Очередь задач
    """
    global _task_queue
    if _task_queue is None:
        # Настраиваем количество воркеров из конфига или используем значение по умолчанию
        max_workers = getattr(settings, 'task_queue_workers', 5)
        _task_queue = TaskQueue(max_workers=max_workers)
    return _task_queue

