# Soft Limit — Telegram Mini App + мульти-бот платформа

Play-to-earn платформа: роле­вые «модели» (каждая со своим Telegram-ботом), у которых
подписчики крутят колесо фортуны и покупают эксклюзивные медиа за внутреннюю валюту
GEMS, за спины и напрямую за Telegram Stars.

## Структура

```
app/               FastAPI backend (API, платежи, спин-механики)
  api/             Роутеры: auth, spin, purchases, wheel, inventory, delivery, admin, webhook
  services/        Бизнес-логика: spin, wallet, delivery, analytics, payments, rate
  models/          SQLAlchemy-модели (users, models, spins, orders, media, ...)
  utils/           Общие хелперы
bot/               Telegram-боты
  admin_bot.py     Диспетчер админ-бота (polling, панель управления)
  model_bot.py     Диспетчер бота модели (webhook) + хендлеры платежей Stars
  manager.py       MultiBotManager — N ботов моделей маршрутизируются по webhook
alembic/           Миграции (схема изначально в first migration + изменения)
frontend/
  admin/           SPA админ-панели (vanilla JS)
  user/            SPA пользовательского Mini App (vanilla JS)
tests/             pytest + aiosqlite (тестовая БД test.db)
```

## Роли

- **Администратор** — владелец платформы: модерация моделей, контента, спин-пакетов,
  статистика (доход в Stars/GEMS/USD), распределение выручки.
- **Владелец модели** (роль `model` через админ-бота) — подключает персонального бота
  модели (токен), настраивает колесо, контент и тем Mini App.
- **Пользователь** — Mini App бота конкретной модели: спины, инвентарь, покупки.

## Валюты и платежи (Telegram Stars)

- Балансы хранятся в **GEMS** и **спинах**; реальные платежи — через **Telegram Stars**
  (currency `XTR`) от бота той модели, чей Mini App открыл пользователь.
- UI-прайсинг в Stars для покупки GEMS конвертируется в USD для аналитики фиксированным
  курсом Stars→TON (`STARS_TO_TON_RATE`) × живой курс TON→USD (CoinGecko, кэш 5 мин,
  fallback-константа в конфиге) — `app/services/rate.py`.
- **Серверная верификация платежей**:
  1. Любой Stars-инвойс создаёт запись `Order` (статус `created`) в БД;
     Telegram payload имеет формат `order:<order_id>:<idempotency_key>`.
  2. Хендлеры `pre_checkout_query` (подтверждение) и `successful_payment`
     (фиксация) живут в `bot/model_bot.py`: Order → `paid` + `PaymentAttempt`
     с `telegram_payment_charge_id` (ключ идемпотентности вебхука).
  3. Эндпоинты `*/complete` не доверяют клиенту: ищут подтверждённый
     `PaymentAttempt` по idempotency_key + user_id + сумме. Если вебхук ещё не
     дошёл (гонка), возвращают **409**; фронтенд автоматически повторяет запрос
     каждые 2 секунды до 5 раз.
- Идемпотентность пользователя:(idempotency_key возвращается при создании
  инвойса и принимается в complete) защищает от двойных начислений.

## Боты и маршрутизация

- Один процесс uvicorn обслуживает API **и** вебхуки всех ботов моделей:
  `POST /api/v1/webhook/model/{model_id}` (`bot/manager.py`).
- Админ-бот работает на **polling** (`bot/admin_bot.py`, запуск отдельно).
- Инвойсы всегда создаются от бота модели (`model.bot_token`), поэтому у
  пользователя должна быть выбрана модель (model_id в токене сессии).

## Запуск

```bash
pip install -e ".[dev]"
alembic upgrade head            # применяет миграции к БД из app/config.py → app.db
uvicorn app.main:app --reload   # API + вебхуки ботов моделей
python -m bot.admin_bot         # отдельно: админ-бот (polling)
```

Переменные окружения — см. `app/config.py` и `.env.example`:
`DATABASE_URL`, `BOT_TOKEN`, `INIT_DATA_TOKEN`, `APP_BASE_URL`, `HTTPS_PROXY` и др.

## Разработка

```bash
pytest -q                       # тесты (используют sqlite test.db)
flake8 app bot tests            # линтер (max-line-length 100, см. .flake8)
black app bot tests             # форматтер (конфиг в pyproject.toml)
alembic revision --autogenerate -m "..."   # новая миграция
```

Файлы миграций всегда применяются к БД из `app/config.py` (для тестов используется
отдельная схема через conftest, миграционные скрипты тестами не гоняются).
