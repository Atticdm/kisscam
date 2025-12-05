# Чеклист деплоя на Railway

## Перед деплоем

- [ ] Код запушен в GitHub репозиторий
- [ ] Бот протестирован локально
- [ ] Все зависимости указаны в `requirements.txt`
- [ ] `.env` файл не содержит секретов в коде (только в Railway)
- [ ] `Procfile` или `railway.json` настроены

## Деплой на Railway

### Шаг 1: Создание проекта
- [ ] Зайти на https://railway.app
- [ ] Войти через GitHub
- [ ] Создать новый проект
- [ ] Выбрать "Deploy from GitHub repo"
- [ ] Выбрать репозиторий `Atticdm/kisscam`

### Шаг 2: Настройка переменных окружения
Добавить в Railway Variables:

- [ ] `TELEGRAM_BOT_TOKEN` = ваш токен от BotFather
- [ ] `GROK_API_KEY` = ваш ключ Grok API
- [ ] `GROK_API_URL` = `https://api.x.ai/v1`
- [ ] `LOG_LEVEL` = `INFO`
- [ ] `MAX_FILE_SIZE_MB` = `10`
- [ ] `VIDEO_DURATION_SECONDS` = `5`

### Шаг 3: Проверка деплоя
- [ ] Дождаться завершения build
- [ ] Проверить логи на ошибки
- [ ] Убедиться, что бот запустился

### Шаг 4: Тестирование
- [ ] Открыть Telegram
- [ ] Найти бота
- [ ] Отправить `/start`
- [ ] Отправить тестовую фотографию
- [ ] Проверить получение видео

## После деплоя

- [ ] Настроить мониторинг (опционально)
- [ ] Проверить использование ресурсов
- [ ] Настроить алерты (опционально)
- [ ] Обновить документацию с URL бота

## Troubleshooting

### Build failed
- Проверьте `requirements.txt`
- Проверьте логи build в Railway
- Убедитесь, что Python версия совместима

### Bot не запускается
- Проверьте логи в Railway
- Убедитесь, что все переменные окружения установлены
- Проверьте формат токенов

### Ошибки при обработке
- Проверьте логи бота
- Убедитесь, что Grok API доступен
- Проверьте лимиты API

## Полезные ссылки

- Railway Dashboard: https://railway.app/dashboard
- Railway Docs: https://docs.railway.app
- Telegram Bot API: https://core.telegram.org/bots/api
- Grok API Docs: https://docs.x.ai (если доступны)

