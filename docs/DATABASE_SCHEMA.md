# Database Schema

Сервер использует SQLite и создаёт схему программно в [`server/server.py`](../server/server.py).
Ниже та же схема в явном SQL-виде, чтобы её было удобно читать, обсуждать и переносить.

## Назначение таблиц

- `clients` - последнее известное состояние клиента;
- `activity_history` - история heartbeat и активности;
- `commands` - очередь команд и история выполнения;
- `screenshots` - метаданные загруженных скриншотов;
- `request_nonces` - защита от повторного воспроизведения подписанных запросов.

## SQL

```sql
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS clients (
    client_id TEXT PRIMARY KEY,
    domain_name TEXT NOT NULL,
    machine_name TEXT NOT NULL,
    user_name TEXT NOT NULL,
    ip_address TEXT NOT NULL,
    activity_state TEXT NOT NULL,
    idle_seconds INTEGER NOT NULL,
    last_active_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    app_mode TEXT NOT NULL,
    service_name TEXT NOT NULL,
    protocol_version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activity_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT NOT NULL,
    activity_state TEXT NOT NULL,
    idle_seconds INTEGER NOT NULL,
    last_active_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    source_ip TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_uuid TEXT NOT NULL UNIQUE,
    client_id TEXT NOT NULL,
    command_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL,
    issued_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    dispatched_at TEXT,
    completed_at TEXT,
    result_json TEXT,
    error_text TEXT
);

CREATE TABLE IF NOT EXISTS screenshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command_id INTEGER NOT NULL,
    client_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    byte_size INTEGER NOT NULL,
    sha256_hex TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS request_nonces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT NOT NULL,
    nonce TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(client_id, nonce)
);
```

## Логические связи

- одна запись в `clients` соответствует одному `client_id`;
- одному `client_id` соответствует много записей в `activity_history`;
- одному `client_id` соответствует много записей в `commands`;
- одной команде `capture_screenshot` может соответствовать одна запись в `screenshots`;
- в `request_nonces` хранится история использованных `nonce` для каждого клиента.

## Замечания

- В текущей реализации внешние ключи не включены на уровне SQLite, потому что сервер работает с простой прикладной моделью и сам контролирует порядок записи.
- Все времена сохраняются в ISO 8601 UTC-формате.
- Поля `payload_json` и `result_json` позволяют хранить расширяемые данные без миграции схемы под каждый новый тип команды.
