-- Инициализация базы данных для Kisscam Bot
-- Этот файл можно использовать для ручной инициализации БД

-- Создаем таблицу пользователей и токенов
CREATE TABLE IF NOT EXISTS user_tokens (
    user_id BIGINT PRIMARY KEY,
    tokens INTEGER NOT NULL DEFAULT 0,
    free_generations_used INTEGER NOT NULL DEFAULT 0,
    promo_generations INTEGER NOT NULL DEFAULT 0,
    terms_agreed_at TIMESTAMP WITH TIME ZONE,
    terms_version INTEGER,
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

-- Создаем таблицу для rate limiting (sliding window)
CREATE TABLE IF NOT EXISTS rate_limits (
    user_id BIGINT PRIMARY KEY,
    request_count INTEGER NOT NULL DEFAULT 0,
    window_start TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Индекс для очистки старых записей
CREATE INDEX IF NOT EXISTS idx_rate_limits_window_start 
ON rate_limits(window_start);

-- Создаем таблицу промокодов
CREATE TABLE IF NOT EXISTS promo_codes (
    code VARCHAR(50) PRIMARY KEY,
    generations INTEGER NOT NULL,
    max_uses_per_user INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Создаем таблицу использования промокодов
CREATE TABLE IF NOT EXISTS promo_code_usage (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    promo_code VARCHAR(50) NOT NULL,
    used_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES user_tokens(user_id) ON DELETE CASCADE,
    FOREIGN KEY (promo_code) REFERENCES promo_codes(code) ON DELETE CASCADE,
    UNIQUE(user_id, promo_code, used_at)
);

-- Индекс для быстрого поиска использований промокода пользователем
CREATE INDEX IF NOT EXISTS idx_promo_code_usage_user_code 
ON promo_code_usage(user_id, promo_code);

-- Вставляем промокод scam10
INSERT INTO promo_codes (code, generations, max_uses_per_user, is_active)
VALUES ('scam10', 10, 3, TRUE)
ON CONFLICT (code) DO NOTHING;

-- Комментарии к таблицам
COMMENT ON TABLE user_tokens IS 'Баланс токенов пользователей';
COMMENT ON TABLE token_transactions IS 'История транзакций токенов для аудита';
COMMENT ON TABLE rate_limits IS 'Rate limiting для защиты от спама запросов';
COMMENT ON TABLE promo_codes IS 'Промокоды для добавления генераций';
COMMENT ON TABLE promo_code_usage IS 'История использования промокодов пользователями';

