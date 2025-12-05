# Technical Architecture: Kisscam Bot

## Архитектура системы

```
┌─────────────────┐
│  Telegram User  │
└────────┬────────┘
         │
         │ Отправка фото
         ▼
┌─────────────────────────────────────┐
│      Telegram Bot API               │
│  (python-telegram-bot / aiogram)    │
└────────┬────────────────────────────┘
         │
         │ Обработка запроса
         ▼
┌─────────────────────────────────────┐
│      Bot Handlers                    │
│  - Command handlers (/start, /help) │
│  - Photo handlers                    │
│  - Error handlers                    │
└────────┬────────────────────────────┘
         │
         │ Валидация и подготовка
         ▼
┌─────────────────────────────────────┐
│      Image Service                   │
│  - Валидация формата                │
│  - Валидация размера                │
│  - Сохранение во временное хранилище│
└────────┬────────────────────────────┘
         │
         │ Добавление в очередь
         ▼
┌─────────────────────────────────────┐
│      Task Queue                      │
│  (Celery + Redis / asyncio)         │
└────────┬────────────────────────────┘
         │
         │ Асинхронная обработка
         ▼
┌─────────────────────────────────────┐
│      Grok Service                    │
│  - Отправка изображений в Grok API  │
│  - Получение видео                  │
│  - Retry логика                     │
└────────┬────────────────────────────┘
         │
         │ API запрос
         ▼
┌─────────────────────────────────────┐
│      Grok API (xAI)                 │
│  - Обработка изображений            │
│  - Генерация видео                  │
└────────┬────────────────────────────┘
         │
         │ Видео файл
         ▼
┌─────────────────────────────────────┐
│      Video Handler                   │
│  - Сохранение видео                 │
│  - Отправка пользователю            │
│  - Очистка временных файлов         │
└─────────────────────────────────────┘
```

## Технологический стек

### Backend
- **Python**: 3.10+
- **Framework**: 
  - `python-telegram-bot` (синхронный) или
  - `aiogram` (асинхронный) - рекомендуется для лучшей производительности
- **Task Queue**: 
  - `Celery` + `Redis` (для масштабирования) или
  - `asyncio` (для простоты на MVP)
- **HTTP Client**: 
  - `aiohttp` (асинхронный) или
  - `requests` (синхронный)

### Хранилище
- **Redis**: 
  - Очередь задач (если используется Celery)
  - Rate limiting счетчики
  - Кэширование
- **PostgreSQL/SQLite**: 
  - Метаданные запросов (опционально для MVP)
  - История пользователей (для будущих функций)
- **File Storage**: 
  - Локальная файловая система (для MVP)
  - S3/MinIO (для масштабирования)

### Мониторинг и логирование
- **Logging**: Python `logging` модуль
- **Monitoring**: 
  - Prometheus + Grafana (опционально)
  - Простой дашборд на Flask/FastAPI
- **Error Tracking**: Sentry (опционально)

### Инфраструктура
- **Server**: VPS (DigitalOcean, Hetzner, AWS EC2)
- **Process Manager**: systemd или supervisor
- **Reverse Proxy**: Nginx (опционально)
- **CI/CD**: GitHub Actions

## Структура проекта

```
kisscam/
├── bot/
│   ├── __init__.py
│   ├── main.py                 # Точка входа бота
│   ├── config.py               # Конфигурация
│   └── handlers/
│       ├── __init__.py
│       ├── commands.py         # Обработчики команд (/start, /help)
│       ├── photos.py           # Обработчики фотографий
│       └── errors.py           # Обработчики ошибок
├── services/
│   ├── __init__.py
│   ├── grok_service.py         # Сервис для работы с Grok API
│   ├── image_service.py        # Сервис для обработки изображений
│   └── video_service.py        # Сервис для обработки видео
├── utils/
│   ├── __init__.py
│   ├── validators.py           # Валидаторы
│   ├── storage.py              # Работа с хранилищем
│   └── logger.py               # Настройка логирования
├── tasks/
│   ├── __init__.py
│   └── process_photo.py        # Задачи для Celery (если используется)
├── tests/
│   ├── __init__.py
│   ├── test_handlers.py
│   ├── test_services.py
│   └── test_utils.py
├── storage/
│   ├── temp/                   # Временные файлы
│   └── videos/                 # Готовые видео (опционально)
├── .env                        # Переменные окружения
├── .env.example                # Пример конфигурации
├── requirements.txt            # Зависимости Python
├── README.md                   # Документация
├── PRD.md                      # Product Requirements Document
├── PRODUCT_ROADMAP.md          # Roadmap продукта
├── SPRINT_PLAN.md              # План спринтов
└── TECHNICAL_ARCHITECTURE.md   # Этот файл
```

## Компоненты системы

### 1. Bot Handlers (`bot/handlers/`)

#### commands.py
Обработчики команд Telegram:
- `/start` - приветствие и инструкция
- `/help` - справка по использованию
- `/stats` - статистика (будущая функция)

#### photos.py
Обработчики фотографий:
- Обработка одной фотографии
- Обработка двух фотографий (последовательно или в группе)
- Валидация входящих данных
- Отправка видео пользователю

#### errors.py
Обработка ошибок:
- Глобальный error handler
- Пользовательские сообщения об ошибках
- Логирование ошибок

### 2. Services (`services/`)

#### grok_service.py
```python
class GrokService:
    async def generate_kissing_video(
        self, 
        images: List[Image], 
        num_people: int
    ) -> Video:
        """
        Генерирует видео с целующимися людьми через Grok API
        
        Args:
            images: Список изображений (1 или 2)
            num_people: Количество людей на изображениях
            
        Returns:
            Video объект с готовым видео
            
        Raises:
            GrokAPIError: При ошибке API
        """
        pass
    
    async def detect_people(self, image: Image) -> int:
        """
        Определяет количество людей на изображении
        
        Returns:
            Количество людей
        """
        pass
```

#### image_service.py
```python
class ImageService:
    def validate_image(self, file: File) -> bool:
        """Валидация формата и размера изображения"""
        pass
    
    def save_temp(self, file: File) -> Path:
        """Сохранение изображения во временное хранилище"""
        pass
    
    def cleanup(self, path: Path):
        """Очистка временных файлов"""
        pass
```

#### video_service.py
```python
class VideoService:
    def save_video(self, video_data: bytes) -> Path:
        """Сохранение видео"""
        pass
    
    def send_to_user(self, user_id: int, video_path: Path):
        """Отправка видео пользователю"""
        pass
    
    def cleanup(self, path: Path):
        """Очистка временных файлов"""
        pass
```

### 3. Utils (`utils/`)

#### validators.py
- Валидация формата изображения
- Валидация размера файла
- Валидация количества людей

#### storage.py
- Работа с временным хранилищем
- Работа с постоянным хранилищем (если нужно)
- Очистка старых файлов

#### logger.py
- Настройка логирования
- Форматирование логов
- Ротация логов

## Конфигурация

### .env файл
```env
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token_here

# Grok API
GROK_API_KEY=your_grok_api_key_here
GROK_API_URL=https://api.x.ai/v1/...

# Redis (для очереди и rate limiting)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Database (опционально)
DATABASE_URL=postgresql://user:password@localhost/kisscam

# Storage
STORAGE_PATH=./storage
TEMP_STORAGE_PATH=./storage/temp

# Rate Limiting
RATE_LIMIT_REQUESTS=10
RATE_LIMIT_PERIOD=3600  # секунды

# Logging
LOG_LEVEL=INFO
LOG_FILE=./logs/bot.log

# Server
HOST=0.0.0.0
PORT=8000
```

## API Интеграция

### Grok API

#### Endpoint для генерации видео
```
POST https://api.x.ai/v1/generate-video
Headers:
  Authorization: Bearer {GROK_API_KEY}
  Content-Type: application/json

Body:
{
  "images": [
    {
      "url": "base64_encoded_image_or_url",
      "people_count": 2
    }
  ],
  "action": "kissing",
  "duration": 5,  # секунды
  "quality": "hd"
}

Response:
{
  "video_url": "https://...",
  "video_data": "base64_encoded_video",
  "duration": 5,
  "status": "success"
}
```

**Примечание**: Точный формат API нужно уточнить в документации Grok API, так как это может отличаться.

## Обработка ошибок

### Типы ошибок

1. **ValidationError**: Некорректный формат или размер файла
2. **GrokAPIError**: Ошибка при обращении к Grok API
   - Timeout
   - Rate limit exceeded
   - Invalid response
   - Service unavailable
3. **ProcessingError**: Ошибка при обработке изображения/видео
4. **StorageError**: Ошибка при сохранении файлов

### Стратегия обработки

```python
# Retry стратегия для Grok API
MAX_RETRIES = 3
RETRY_DELAY = 5  # секунды
BACKOFF_FACTOR = 2

# Exponential backoff
for attempt in range(MAX_RETRIES):
    try:
        result = await grok_service.generate_video(...)
        break
    except GrokAPIError as e:
        if attempt < MAX_RETRIES - 1:
            await asyncio.sleep(RETRY_DELAY * (BACKOFF_FACTOR ** attempt))
        else:
            raise
```

## Масштабирование

### Горизонтальное масштабирование

1. **Multiple Bot Instances**: Запуск нескольких экземпляров бота
2. **Load Balancer**: Распределение нагрузки между инстансами
3. **Shared Redis**: Общий Redis для очереди и rate limiting
4. **Shared Storage**: Общее хранилище файлов (S3)

### Вертикальное масштабирование

1. **Увеличение ресурсов сервера**: Больше CPU/RAM
2. **Оптимизация кода**: Асинхронная обработка, кэширование
3. **Оптимизация API**: Batch requests, connection pooling

## Безопасность

### Меры безопасности

1. **Валидация входных данных**: Формат, размер, содержимое
2. **Rate Limiting**: Защита от злоупотреблений
3. **Секреты**: Хранение токенов в переменных окружения
4. **Очистка файлов**: Автоматическое удаление временных файлов
5. **Логирование**: Отслеживание подозрительной активности
6. **Возрастные ограничения**: Предупреждения о контенте 18+

## Мониторинг

### Метрики для отслеживания

1. **Производительность**:
   - Время обработки запроса
   - Количество обработанных запросов в минуту
   - Размер очереди задач

2. **Надежность**:
   - Error rate
   - Success rate
   - Uptime

3. **Использование**:
   - Количество активных пользователей
   - Количество запросов на пользователя
   - Использование Grok API (количество запросов, стоимость)

4. **Ресурсы**:
   - Использование CPU/RAM
   - Использование дискового пространства
   - Использование Redis

## Деплой

### Production Setup

1. **Server Setup**:
   ```bash
   # Установка зависимостей
   sudo apt update
   sudo apt install python3.10 python3-pip redis-server postgresql
   
   # Настройка виртуального окружения
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Systemd Service**:
   ```ini
   [Unit]
   Description=Kisscam Telegram Bot
   After=network.target redis.service
   
   [Service]
   Type=simple
   User=bot
   WorkingDirectory=/opt/kisscam
   Environment="PATH=/opt/kisscam/venv/bin"
   ExecStart=/opt/kisscam/venv/bin/python bot/main.py
   Restart=always
   
   [Install]
   WantedBy=multi-user.target
   ```

3. **CI/CD Pipeline** (GitHub Actions):
   ```yaml
   name: Deploy
   on:
     push:
       branches: [main]
   jobs:
     deploy:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v2
         - name: Deploy to server
           run: |
             ssh user@server 'cd /opt/kisscam && git pull && systemctl restart kisscam'
   ```

## Будущие улучшения

1. **Кэширование**: Кэширование результатов для одинаковых запросов
2. **Batch Processing**: Обработка нескольких запросов одновременно
3. **Webhook вместо polling**: Использование webhook для Telegram Bot API
4. **GraphQL API**: Создание GraphQL API для будущего веб-интерфейса
5. **Machine Learning**: Локальная детекция лиц для уменьшения зависимости от API

