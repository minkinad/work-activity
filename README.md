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

Проект разбит на 3 слоя.

- `client`
  Windows-агент на C++, который собирает активность, отправляет heartbeat, опрашивает очередь команд и загружает скриншоты по HTTPS.
- `server`
  Flask API, которое проверяет HMAC-подпись, пишет данные в SQLite и отдаёт dashboard API.
- `frontend`
  статическое приложение на HTML/CSS/JS, которое живёт отдельно от сервера и обращается к API по CORS.

### Реальный поток данных

1. Клиент отправляет heartbeat на `POST /api/v1/client/heartbeat`.
2. Сервер проверяет подпись и обновляет таблицы `clients` и `activity_history`.
3. Клиент опрашивает `POST /api/v1/client/commands/poll`.
4. Frontend создаёт команду на скриншот через `POST /api/v1/dashboard/clients/<client_id>/commands/screenshot`.
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

## База данных

Используется SQLite. Схема создаётся программно в [`server/server.py`](./server/server.py).

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
|   `-- DATABASE_SCHEMA.md
|-- frontend/
|   |-- index.html
|   |-- styles.css
|   `-- app.js
|-- server/
|   |-- server.py
|   |-- requirements.txt
|   |-- certs/
|   |   `-- README.md
|   `-- tools/
|       |-- generate-dev-cert.sh
|       `-- generate-dev-cert.ps1
|-- .gitignore
|-- LICENSE
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
  Flask API, SQLite, проверка подписи, история активности, очередь команд, история скриншотов.
- [`server/requirements.txt`](./server/requirements.txt)
  Единственная внешняя Python-зависимость: Flask.

### Frontend

- [`frontend/index.html`](./frontend/index.html)
  Разметка dashboard.
- [`frontend/app.js`](./frontend/app.js)
  Работа с API и обновление экранов.
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
allow_self_signed_tls = true
enable_autostart = false
registry_value_name = WorkActivityMonitor
shared_secret = change-me-in-production
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
- `allow_self_signed_tls` - игнорировать ошибки self-signed сертификата;
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
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
cd server
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Запустить API

```bash
cd server
MONITOR_SHARED_SECRET=change-me-in-production python server.py
```

Поддерживаемые переменные окружения:

- `MONITOR_API_HOST`
- `MONITOR_API_PORT`
- `MONITOR_DB_PATH`
- `MONITOR_CLIENT_TIMEOUT`
- `MONITOR_COMMAND_RETRY_SECONDS`
- `MONITOR_SIGNATURE_TOLERANCE_SECONDS`
- `MONITOR_SHARED_SECRET`
- `MONITOR_TLS_CERT`
- `MONITOR_TLS_KEY`
- `MONITOR_FRONTEND_ORIGIN`

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

Frontend не требует npm/yarn и может быть поднят любым статическим сервером.

Пример:

```bash
cd frontend
python -m http.server 8081
```

Дальше:

1. открыть `http://127.0.0.1:8081`;
2. указать `API Base URL`, например `https://127.0.0.1:5000`;
3. сохранить URL;
4. смотреть клиентов, историю активности, команды и скриншоты.

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
- `POST /api/v1/client/commands/<id>/complete`
- `POST /api/v1/client/commands/<id>/screenshot`

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

## Ограничения

- Windows Service работает в Session 0, поэтому доступ к интерактивному desktop и скриншотам может быть ограничен. Для надёжного захвата пользовательского экрана практичнее user-session режим.
- В проекте нет аутентификации операторов dashboard API.
- `allow_self_signed_tls = true` удобно для разработки, но не подходит для production.
- Схема БД создаётся программно, а не через систему миграций.

## Лицензия

MIT. Подробности: [`LICENSE`](./LICENSE).
