-- Инициализация базы данных для Kisscam Bot
-- Этот файл можно использовать для ручной инициализации БД

-- Создаем таблицу пользователей и токенов
CREATE TABLE IF NOT EXISTS user_tokens (
    user_id BIGINT PRIMARY KEY,
    tokens INTEGER NOT NULL DEFAULT 0,
    free_generation_used BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Индекс для быстрого поиска по updated_at (для аналитики)
CREATE INDEX IF NOT EXISTS idx_user_tokens_updated_at 
ON user_tokens(updated_at);

-- Создаем таблицу истории транзакций (для аудита и аналитики)
CREATE TABLE IF NOT EXISTS token_transactions (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    amount INTEGER NOT NULL,
    transaction_type VARCHAR(50) NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES user_tokens(user_id) ON DELETE CASCADE
);

-- Индекс для быстрого поиска транзакций пользователя
CREATE INDEX IF NOT EXISTS idx_token_transactions_user_id 
ON token_transactions(user_id, created_at DESC);

-- Комментарии к таблицам
COMMENT ON TABLE user_tokens IS 'Баланс токенов пользователей';
COMMENT ON TABLE token_transactions IS 'История транзакций токенов для аудита';

