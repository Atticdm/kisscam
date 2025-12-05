# Тестирование Kisscam Bot

## Локальное тестирование

### 1. Установка зависимостей

```bash
# Активируйте виртуальное окружение
source venv/bin/activate  # macOS/Linux
# или
venv\Scripts\activate  # Windows

# Установите зависимости
pip install -r requirements.txt
```

### 2. Настройка переменных окружения

Создайте файл `.env` в корне проекта:

```env
TELEGRAM_BOT_TOKEN=ваш_токен_от_BotFather
GROK_API_KEY=ваш_ключ_Grok_API
GROK_API_URL=https://api.x.ai/v1
LOG_LEVEL=INFO
MAX_FILE_SIZE_MB=10
VIDEO_DURATION_SECONDS=5
```

### 3. Запуск бота

```bash
python bot/main.py
```

Вы должны увидеть:
```
INFO     kisscam Bot starting...
```

### 4. Тестирование в Telegram

1. Откройте Telegram
2. Найдите вашего бота (username из BotFather)
3. Отправьте команду `/start`
4. Проверьте ответ бота

### 5. Тестирование обработки фотографий

#### Тест 1: Одна фотография
1. Отправьте фотографию с парой людей
2. Дождитесь обработки
3. Проверьте получение видео

#### Тест 2: Две фотографии
1. Отправьте команду `/two` или текст "Две фотографии"
2. Отправьте первую фотографию
3. Отправьте вторую фотографию
4. Проверьте получение видео

#### Тест 3: Обработка ошибок
1. Отправьте файл неподдерживаемого формата
2. Отправьте файл больше 10 МБ
3. Проверьте сообщения об ошибках

## Тестирование Grok API

### Проверка доступности API

Создайте тестовый скрипт `test_grok_api.py`:

```python
import asyncio
import aiohttp
import os
from dotenv import load_dotenv

load_dotenv()

async def test_grok_api():
    api_key = os.getenv("GROK_API_KEY")
    api_url = "https://api.x.ai/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "grok-beta",
        "messages": [
            {
                "role": "user",
                "content": "Привет! Можешь ответить?"
            }
        ],
        "max_tokens": 100
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(api_url, json=data, headers=headers) as response:
            print(f"Status: {response.status}")
            print(f"Response: {await response.text()}")

if __name__ == "__main__":
    asyncio.run(test_grok_api())
```

Запустите:
```bash
python test_grok_api.py
```

## Проверка логов

Логи сохраняются в `logs/bot.log`. Проверьте их при ошибках:

```bash
tail -f logs/bot.log
```

## Типичные проблемы

### Бот не запускается
- Проверьте токен Telegram Bot в `.env`
- Убедитесь, что виртуальное окружение активировано
- Проверьте установку зависимостей: `pip list`

### Ошибка при обработке фотографий
- Проверьте логи: `logs/bot.log`
- Убедитесь, что Grok API доступен
- Проверьте формат фотографии (JPG, PNG)
- Проверьте размер файла (макс 10 МБ)

### Grok API ошибки
- Проверьте API ключ в `.env`
- Убедитесь, что у вас есть доступ к Grok API
- Проверьте лимиты API
- Проверьте формат запроса к API

## Автоматическое тестирование

Для будущего развития можно добавить:

1. **Unit тесты** (`tests/test_services.py`):
   - Тестирование ImageService
   - Тестирование GrokService (моки)
   - Тестирование валидации

2. **Integration тесты** (`tests/test_handlers.py`):
   - Тестирование обработчиков команд
   - Тестирование обработчиков фотографий

3. **E2E тесты**:
   - Тестирование полного потока обработки фотографий

## Перед деплоем на Railway

Убедитесь, что:
- ✅ Бот работает локально
- ✅ Все тесты проходят
- ✅ Логи не содержат ошибок
- ✅ Переменные окружения настроены правильно
- ✅ Код запушен в GitHub

