# Client-Server Application Monitoring Work Activity

[![Client](https://img.shields.io/badge/client-C%2B%2B%20%2F%20WinHTTP%20%2B%20WinAPI-00599c)](./client)
[![Server](https://img.shields.io/badge/server-Python%20Flask%20%2B%20SQLite-1f6feb)](./server)
[![Frontend](https://img.shields.io/badge/frontend-HTML%20%2F%20CSS%20%2F%20JS-0f7b6c)](./frontend)
[![Security](https://img.shields.io/badge/security-TLS%20%2B%20HMAC-orange)](./server/certs/README.md)
[![License](https://img.shields.io/badge/license-MIT-black)](./LICENSE)

Клиент-серверное приложение для мониторинга рабочей активности сотрудников.

Текущая версия проекта состоит из:

- Windows-клиента на C++;
- HTTPS API на Python/Flask;
- отдельного frontend без build-step;
- SQLite-хранилища истории и очереди команд.

## Что есть в проекте

- HTTPS API с TLS-сертификатом;
- HMAC-SHA256 подпись клиентских запросов;
- защита от replay через nonce;
- хранение текущего состояния клиентов в SQLite;
- история активности в SQLite;
- очередь команд в SQLite;
- история скриншотов и история команд;
- отдельный frontend в папке [`frontend`](./frontend);
- Windows Service-режим клиента;
- PowerShell-скрипты установки и удаления сервиса;
- Inno Setup-скрипт для сборки установщика;
- Visual Studio solution/project files;
- комментарии в ключевых местах кода.

## Архитектура

Проект разбит на три приложения, а сервер — на отдельные архитектурные слои.

- `client`
  Windows-агент на C++, который собирает активность, отправляет heartbeat, опрашивает очередь команд и загружает скриншоты по HTTPS.
- `server`
  Flask API с application factory. HTTP-адаптеры, бизнес-сервисы, безопасность,
  репозитории и SQLite-миграции разделены по модулям.
- `frontend`
  статическое приложение на HTML/CSS/JS, которое живёт отдельно от сервера и обращается к API по CORS.

Подробное описание границ и зависимостей: [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md).

Руководства для разработчиков и инструментов:

- [`CONTRIBUTING.md`](./CONTRIBUTING.md) — правила внесения изменений;
- [`docs/DEVELOPMENT.md`](./docs/DEVELOPMENT.md) — подготовка окружения и команды;
- [`docs/API.md`](./docs/API.md) — краткий контракт API;
- [`docs/TROUBLESHOOTING.md`](./docs/TROUBLESHOOTING.md) — частые проблемы;
- [`AGENTS.md`](./AGENTS.md) — архитектурные и security-ограничения для coding agents.

### Реальный поток данных

1. Клиент отправляет heartbeat на `POST /api/v1/client/heartbeat`.
2. Сервер проверяет подпись и обновляет таблицы `clients` и `activity_history`.
3. Клиент опрашивает `POST /api/v1/client/commands/poll`.
4. Оператор проходит bearer-аутентификацию, после чего frontend создаёт команду на
   скриншот через `POST /api/v1/dashboard/clients/<client_id>/commands/screenshot`.
5. Сервер сохраняет команду в `commands` со статусом `queued`.
6. Клиент получает команду `capture_screenshot`, делает PNG-скриншот и загружает его на `POST /api/v1/client/commands/<id>/screenshot`.
7. Сервер сохраняет файл и метаданные в `screenshots`, а команду переводит в `completed`.

## Безопасность

### TLS

Сервер запускается с TLS-контекстом и требует сертификат и ключ.

Ожидаемые пути по умолчанию:

- [`server/certs/server.crt`](./server/certs/README.md)
- [`server/certs/server.key`](./server/certs/README.md)

В репозитории сами ключ и сертификат не хранятся. Для локальной разработки есть скрипты:

- [`server/tools/generate-dev-cert.sh`](./server/tools/generate-dev-cert.sh)
- [`server/tools/generate-dev-cert.ps1`](./server/tools/generate-dev-cert.ps1)

### Подпись клиентских сообщений

Каждый клиентский запрос подписывается по формуле:

```text
timestamp + "\n" + nonce + "\n" + client_id + "\n" + raw_body
```

Используемые заголовки:

- `X-Monitor-Client-Id`
- `X-Monitor-Timestamp`
- `X-Monitor-Nonce`
- `X-Monitor-Signature`

На сервере подпись проверяется через HMAC-SHA256, а `nonce` сохраняется в БД, чтобы не допустить повторную отправку того же подписанного запроса.

### Доступ оператора

Все `dashboard` endpoints, включая файлы скриншотов, требуют отдельный bearer token из
`MONITOR_DASHBOARD_TOKEN`. CORS работает только для точного списка origin из
`MONITOR_FRONTEND_ORIGINS`. Сервер не запускается с пустыми, короткими или стандартными
секретами. Полная модель угроз и ограничения описаны в [`docs/SECURITY.md`](./docs/SECURITY.md).

## База данных

Используется SQLite. Версионируемые SQL-миграции находятся в [`server/migrations`](./server/migrations).

Полное описание схемы в отдельном документе:

- [`docs/DATABASE_SCHEMA.md`](./docs/DATABASE_SCHEMA.md)

Основные таблицы:

- `clients`
- `activity_history`
- `commands`
- `screenshots`
- `request_nonces`

Runtime-файлы создаются автоматически и не лежат в репозитории:

- `server/data/monitor.db`
- `server/data/screenshots/*.png`

## Структура репозитория

```text
Client-Server-application-monitoring-work-activity/
|-- client/
|   |-- Client.cpp
|   |-- activity_monitor.cpp
|   |-- screenshot.cpp
|   |-- client.h
|   |-- config.ini
|   |-- Makefile
|   |-- Client.sln
|   |-- Client.vcxproj
|   |-- Client.vcxproj.filters
|   |-- install_service.ps1
|   |-- uninstall_service.ps1
|   `-- installer/
|       `-- ClientSetup.iss
|-- docs/
|   |-- API.md
|   |-- ARCHITECTURE.md
|   |-- DATABASE_SCHEMA.md
|   |-- DEVELOPMENT.md
|   |-- SECURITY.md
|   `-- TROUBLESHOOTING.md
|-- frontend/
|   |-- index.html
|   |-- package.json
|   |-- scripts/
|   |-- src/
|   |-- styles.css
|   `-- tests/
|-- server/
|   |-- migrations/
|   |-- monitoring/
|   |-- tests/
|   |-- server.py
|   |-- requirements.txt
|   |-- certs/
|   |   `-- README.md
|   `-- tools/
|       |-- generate-dev-cert.sh
|       `-- generate-dev-cert.ps1
|-- .gitignore
|-- AGENTS.md
|-- CONTRIBUTING.md
|-- LICENSE
|-- Makefile
|-- SECURITY.md
`-- README.md
```

## Ключевые файлы

### Клиент

- [`client/Client.cpp`](./client/Client.cpp)
  Основная логика клиента: конфиг, WinHTTP, HMAC, polling очереди команд, service mode.
- [`client/activity_monitor.cpp`](./client/activity_monitor.cpp)
  Определение `idle_seconds` через `GetLastInputInfo`.
- [`client/screenshot.cpp`](./client/screenshot.cpp)
  Получение PNG-скриншота в память через GDI+.
- [`client/config.ini`](./client/config.ini)
  Настройки подключения, TLS и service metadata.

### Сервер

- [`server/server.py`](./server/server.py)
  Минимальная точка сборки и запуска HTTPS-сервера.
- [`server/monitoring`](./server/monitoring)
  Конфигурация, HTTP API, бизнес-сервисы, безопасность и слой хранения.
- [`server/requirements.txt`](./server/requirements.txt)
  Единственная внешняя Python-зависимость: Flask.

### Frontend

- [`frontend/index.html`](./frontend/index.html)
  Разметка dashboard.
- [`frontend/src/app.js`](./frontend/src/app.js)
  Контроллер интерфейса и orchestration пользовательских сценариев.
- [`frontend/src/api-client.js`](./frontend/src/api-client.js)
  Изолированный API-клиент с bearer-аутентификацией и timeout.
- [`frontend/src/renderers.js`](./frontend/src/renderers.js)
  Безопасный DOM-rendering без вставки непроверенного HTML.
- [`frontend/styles.css`](./frontend/styles.css)
  Стили интерфейса.

## Конфигурация клиента

Файл [`client/config.ini`](./client/config.ini):

```ini
[client]
server_host = 127.0.0.1
server_port = 5000
api_base_path = /api/v1
heartbeat_interval_seconds = 15
command_poll_interval_seconds = 5
idle_threshold_seconds = 300
use_tls = true
allow_self_signed_tls = false
enable_autostart = false
registry_value_name = WorkActivityMonitor
shared_secret = replace-with-the-same-32-character-or-longer-secret-as-the-server
service_name = WorkActivityMonitorSvc
service_display_name = Work Activity Monitor Service
service_description = Uploads activity telemetry and executes queued screenshot commands.
```

Параметры:

- `server_host` - host API;
- `server_port` - порт API;
- `api_base_path` - базовый путь API;
- `heartbeat_interval_seconds` - период отправки heartbeat;
- `command_poll_interval_seconds` - период опроса очереди команд;
- `idle_threshold_seconds` - порог idle в секундах;
- `use_tls` - использовать HTTPS;
- `allow_self_signed_tls` - разрешить self-signed сертификат только в изолированной разработке;
- `enable_autostart` - добавить приложение в автозапуск текущего пользователя;
- `registry_value_name` - имя значения в ветке `Run`;
- `shared_secret` - общий секрет для HMAC;
- `service_name`, `service_display_name`, `service_description` - параметры Windows Service.

## Запуск сервера

### 1. Сгенерировать dev-сертификат

Linux/macOS:

```bash
cd server/tools
./generate-dev-cert.sh
```

Windows PowerShell:

```powershell
cd server\tools
.\generate-dev-cert.ps1
```

### 2. Установить зависимости

```bash
cd server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Windows PowerShell:

```powershell
cd server
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

### 3. Настроить секреты и запустить API

```bash
cd server
export MONITOR_SHARED_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export MONITOR_DASHBOARD_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
python server.py
```

Скопируйте `MONITOR_SHARED_SECRET` в `client/config.ini`. Значения должны быть разными и
содержать минимум 32 символа. Полный шаблон конфигурации находится в [`.env.example`](./.env.example).

Поддерживаемые переменные окружения:

- `MONITOR_API_HOST`
- `MONITOR_API_PORT`
- `MONITOR_DB_PATH`
- `MONITOR_SCREENSHOTS_DIR`
- `MONITOR_CLIENT_TIMEOUT`
- `MONITOR_COMMAND_RETRY_SECONDS`
- `MONITOR_SIGNATURE_TOLERANCE_SECONDS`
- `MONITOR_SHARED_SECRET`
- `MONITOR_DASHBOARD_TOKEN`
- `MONITOR_TLS_CERT`
- `MONITOR_TLS_KEY`
- `MONITOR_FRONTEND_ORIGINS`
- `MONITOR_MAX_SCREENSHOT_BYTES`

### Что отдаёт сервер

- `GET /`
  краткая JSON-информация о сервисе;
- `GET /health`
  healthcheck;
- `GET /api/v1/dashboard/*`
  dashboard API для frontend;
- `POST /api/v1/client/*`
  клиентские endpoints.

## Запуск frontend

Frontend остаётся статическим приложением, но теперь имеет unit-тесты, security-проверку и
воспроизводимую сборку.

Пример:

```bash
cd frontend
npm ci
npm run ci
python -m http.server 8081 --directory dist
```

Дальше:

1. открыть `http://127.0.0.1:8081`;
2. указать `API Base URL`, например `https://127.0.0.1:5000`;
3. указать значение `MONITOR_DASHBOARD_TOKEN`;
4. применить настройки;
5. смотреть клиентов, историю активности, команды и скриншоты.

## Сборка клиента

### Visual Studio

1. открыть [`client/Client.sln`](./client/Client.sln);
2. выбрать `Release | x64`;
3. собрать проект;
4. положить [`client/config.ini`](./client/config.ini) рядом с `Client.exe`;
5. убедиться, что `shared_secret` совпадает со значением `MONITOR_SHARED_SECRET` на сервере.

### MinGW-w64

```bash
cd client
make
```

## Режимы запуска клиента

### Фоновый пользовательский режим

```powershell
Client.exe
```

Этот режим лучше подходит для интерактивного пользователя и снятия скриншотов рабочего стола.

### Установка как Windows Service

Через PowerShell:

```powershell
cd client
.\install_service.ps1 -ExecutablePath .\Client.exe
```

Или напрямую:

```powershell
Client.exe --install-service
```

Удаление:

```powershell
Client.exe --uninstall-service
```

### Installer

Для упаковки клиента добавлен Inno Setup-скрипт:

- [`client/installer/ClientSetup.iss`](./client/installer/ClientSetup.iss)

## API

### Клиентские endpoints

- `POST /api/v1/client/heartbeat`
- `POST /api/v1/client/commands/poll`
- `POST /api/v1/client/commands/<id>/fail`
- `POST /api/v1/client/commands/<id>/screenshot`

Старый endpoint `/complete` временно сохранён как совместимый alias для отчёта об ошибке.

### Dashboard endpoints

- `GET /api/v1/dashboard/clients`
- `GET /api/v1/dashboard/activity`
- `GET /api/v1/dashboard/commands`
- `GET /api/v1/dashboard/screenshots`
- `GET /api/v1/dashboard/screenshots/<id>/file`
- `POST /api/v1/dashboard/clients/<client_id>/commands/screenshot`

## Что показывает frontend

- список клиентов;
- `online/offline` статус;
- домен, машина, пользователь, IP;
- `activity_state`, `idle_seconds`, `last_active_at`, `last_seen_at`;
- историю активности;
- очередь и историю команд;
- историю скриншотов;
- превью последнего скриншота.

## Проверка

Из корня репозитория полный набор локальных проверок запускается одной командой:

```bash
make check
```

Список доступных вспомогательных команд:

```bash
make help
```

Эквивалентный ручной запуск:

```bash
cd server
python -m unittest discover -s tests -v
ruff check monitoring tests server.py
bandit --quiet --recursive monitoring
pip-audit --requirement requirements.txt
cd ..
cd frontend
npm ci
npm run ci
```

GitHub Actions запускает серверные и frontend-тесты, Ruff, Bandit, `pip-audit`, `npm audit`,
статическую сборку dashboard и Release-сборку Windows-клиента. Собранные frontend и
`Client.exe` публикуются как CI artifacts. Отдельный CodeQL workflow анализирует Python,
JavaScript и C++.

## Ограничения

- Windows Service работает в Session 0, поэтому доступ к интерактивному desktop и скриншотам может быть ограничен. Для надёжного захвата пользовательского экрана практичнее user-session режим.
- Один dashboard bearer token пока представляет всех операторов; для нескольких ролей нужен SSO/RBAC.
- Глобальный HMAC-секрет клиентов следует заменить per-device credential перед большим развёртыванием.
- Политика хранения скриншотов и юридически значимое согласие сотрудников остаются ответственностью оператора системы.

## Лицензия

MIT. Подробности: [`LICENSE`](./LICENSE).
