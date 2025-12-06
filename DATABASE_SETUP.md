# Настройка PostgreSQL базы данных

## Для Railway

1. **Создайте PostgreSQL сервис в Railway:**
   - Зайдите в ваш проект на Railway
   - Нажмите "New" → "Database" → "Add PostgreSQL"
   - Railway автоматически создаст базу данных

2. **Получите DATABASE_URL:**
   - Railway автоматически создаст переменную окружения `DATABASE_URL`
   - Она будет содержать строку подключения вида:
     ```
     postgresql://user:password@host:port/database
     ```
   - Эта переменная уже будет доступна в вашем приложении

3. **База данных инициализируется автоматически:**
   - При запуске бота автоматически создаются необходимые таблицы
   - Никаких дополнительных действий не требуется

## Для локальной разработки

1. **Установите PostgreSQL:**
   ```bash
   # macOS
   brew install postgresql
   brew services start postgresql
   
   # Linux
   sudo apt-get install postgresql
   sudo systemctl start postgresql
   ```

2. **Создайте базу данных:**
   ```bash
   createdb kisscam
   ```

3. **Установите переменную окружения:**
   ```bash
   export DATABASE_URL="postgresql://username:password@localhost:5432/kisscam"
   ```
   
   Или добавьте в `.env` файл:
   ```
   DATABASE_URL=postgresql://username:password@localhost:5432/kisscam
   ```

4. **Запустите бота:**
   - Таблицы создадутся автоматически при первом запуске

## Ручная инициализация (опционально)

Если хотите создать таблицы вручную:

```bash
psql $DATABASE_URL -f database/init.sql
```

## Проверка подключения

После запуска бота проверьте логи:
- Должно быть сообщение: "Database connection pool created"
- Должно быть сообщение: "Database tables initialized successfully"

## Масштабирование

База данных настроена для работы с 100,000+ пользователей:
- Используется connection pooling (5-20 соединений)
- Созданы индексы для быстрых запросов
- Транзакции обеспечивают целостность данных
- История транзакций для аудита и аналитики

