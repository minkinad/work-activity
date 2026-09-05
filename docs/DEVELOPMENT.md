# Development guide

## Prerequisites

- Python 3.12 or newer;
- Node.js 22 and npm;
- GNU Make for the shortcut commands;
- `uv` is optional but lets setup work on minimal Python installations without
  `ensurepip`; otherwise install the platform's Python venv package;
- OpenSSL for generating a local TLS certificate;
- Visual Studio Build Tools or MinGW-w64 for the Windows client.

## First-time setup

From the repository root:

```bash
make setup
cp .env.example .env
```

`.env` is a reference file for your shell or process manager; Flask does not load it
automatically. Generate two different secrets and export the variables before launch:

```bash
export MONITOR_SHARED_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
export MONITOR_DASHBOARD_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
```

Generate the development certificate:

```bash
server/tools/generate-dev-cert.sh
```

Copy `MONITOR_SHARED_SECRET` into `client/config.ini` only in your uncommitted local copy.

## Running locally

Terminal 1:

```bash
server/.venv/bin/python server/server.py
```

Terminal 2:

```bash
make build-frontend
python3 -m http.server 8081 --directory frontend/dist
```

Open `http://127.0.0.1:8081`, then enter `https://127.0.0.1:5000` and the dashboard
token. A self-signed certificate must be trusted locally before the browser can call the
API.

## Quality commands

```bash
make help       # list commands
make test       # server and frontend tests
make lint       # Ruff and frontend static policy
make security   # Bandit, installed Python environment audit, npm audit
make build      # static frontend artifact
make check      # complete local gate
```

The Windows client is built separately with Visual Studio or `make build-client` when a
MinGW-w64 toolchain is installed. GitHub Actions performs the authoritative MSBuild x64
Release build.

## Database changes

Add the next zero-padded SQL file to `server/migrations/`. Migrations run in filename order
and are recorded by the database adapter. Never edit a migration that may already have run;
add a new migration that moves the existing schema forward.

## Debugging

Keep production security rules enabled while debugging. Prefer temporary test settings and
fixtures instead of weakening authentication, TLS validation, CORS, or request bounds.
Common failures are documented in [`TROUBLESHOOTING.md`](./TROUBLESHOOTING.md).
