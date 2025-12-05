# Деплой на Railway

## Подготовка

1. Убедитесь, что код запушен в GitHub репозиторий: https://github.com/Atticdm/kisscam

## Шаги деплоя

### 1. Создание проекта на Railway

1. Перейдите на https://railway.app
2. Войдите через GitHub
3. Нажмите "New Project"
4. Выберите "Deploy from GitHub repo"
5. Выберите репозиторий `Atticdm/kisscam`

### 2. Настройка переменных окружения

В настройках проекта Railway добавьте следующие переменные окружения:

```
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
GROK_API_KEY=your_grok_api_key_here
GROK_API_URL=https://api.x.ai/v1
LOG_LEVEL=INFO
MAX_FILE_SIZE_MB=10
VIDEO_DURATION_SECONDS=5
```

**Как добавить переменные:**
1. В проекте Railway нажмите на сервис
2. Перейдите в раздел "Variables"
3. Добавьте каждую переменную через "New Variable"

### 3. Настройка деплоя

Railway автоматически определит Python проект и установит зависимости из `requirements.txt`.

Если нужно настроить вручную:
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `python bot/main.py`

### 4. Запуск деплоя

Railway автоматически запустит деплой после подключения репозитория.

Вы можете:
- Посмотреть логи в разделе "Deployments"
- Проверить статус деплоя
- Перезапустить сервис при необходимости

### 5. Проверка работы

После успешного деплоя:
1. Откройте Telegram
2. Найдите вашего бота
3. Отправьте команду `/start`
4. Протестируйте отправку фотографий

## Мониторинг

### Логи
- Логи доступны в разделе "Deployments" → выберите деплой → "View Logs"
- Или в разделе "Metrics" → "Logs"

### Метрики
- Railway показывает использование CPU, RAM, Network
- Можно настроить алерты при превышении лимитов

## Обновление бота

После каждого push в main ветку Railway автоматически:
1. Обнаружит изменения
2. Запустит новый build
3. Задеплоит новую версию
4. Перезапустит сервис

## Troubleshooting

### Бот не запускается
1. Проверьте логи в Railway
2. Убедитесь, что все переменные окружения установлены
3. Проверьте формат токенов

### Ошибки при обработке фотографий
1. Проверьте логи бота
2. Убедитесь, что Grok API доступен
3. Проверьте лимиты API

### Railway не определяет Python
- Убедитесь, что `requirements.txt` присутствует в корне проекта
- Проверьте, что `Procfile` или `railway.json` настроены правильно

## Стоимость

Railway предоставляет:
- **Free tier**: $5 кредитов в месяц
- Для Telegram бота этого обычно достаточно
- При превышении лимита можно перейти на платный план

## Альтернативные платформы

Если Railway не подходит, можно использовать:
- **Render**: https://render.com
- **Fly.io**: https://fly.io
- **Heroku**: https://heroku.com (платный)
- **DigitalOcean App Platform**: https://www.digitalocean.com/products/app-platform

