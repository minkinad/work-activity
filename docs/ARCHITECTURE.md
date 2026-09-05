# Architecture

## Design goals

The server is organized around explicit boundaries so HTTP, business rules, persistence,
and authentication can evolve independently. The Windows protocol remains small: signed
heartbeats, command polling, and command results.

```text
Windows client
  -> client HMAC authentication
  -> Flask API adapters
  -> activity / command services
  -> repository
  -> SQLite + screenshot storage

Dashboard
  -> dashboard bearer authentication
  -> Flask API adapters
  -> activity / command services
```

## Server modules

- `monitoring/config.py` parses and validates runtime configuration. The process fails
  closed when secrets are absent, weak, or default-valued.
- `monitoring/api.py` is the composition root for the Flask application and blueprints.
- `monitoring/routes/` separates client protocol routes from operator dashboard routes.
- `monitoring/http.py` owns JSON parsing, errors, CORS, and HTTP security headers.
- `monitoring/security.py` verifies client HMAC signatures, timestamp freshness, replay
  nonces, and dashboard bearer tokens.
- `monitoring/services.py` contains application use cases and business invariants.
- `monitoring/repositories.py` owns SQL and atomic state transitions.
- `monitoring/database.py` owns connections and ordered SQL migrations.
- `migrations/` contains the durable schema and indexes.
- `server.py` is only the composition root and HTTPS process entry point.

Dependencies point inward: API code may call services, services may call repositories,
and repositories may call the database adapter. Services do not import Flask.

## Business invariants

- A client identifier has a bounded, filesystem-safe format.
- Only protocol version 2 is accepted.
- Activity state is either `active` or `idle`; numeric and timestamp fields are bounded.
- At most one pending screenshot command exists for a client.
- A client can complete or fail only a command that was dispatched to that client.
- A screenshot is a bounded base64-encoded PNG and is stored once per command.
- Command claiming and state transitions run inside immediate SQLite transactions.

## Trust boundaries

Client and operator traffic use separate credentials. Client requests use an HMAC shared
secret plus timestamp and one-time nonce. Dashboard requests use an independent bearer
token. CORS is an allowlist and does not grant authentication.

For a larger deployment, the next architectural step is replacing the global client
secret with per-device credentials and replacing the dashboard token with an identity
provider and role-based authorization.

## Frontend modules

- `src/app.js` coordinates UI state and operator flows.
- `src/api-client.js` owns authenticated, time-bounded HTTP access.
- `src/renderers.js` renders API data using DOM nodes and `textContent` only.
- `src/config.js`, `src/state.js`, and `src/format.js` contain testable pure helpers.
- `scripts/check.mjs` rejects inline handlers and unsafe HTML insertion APIs.
- `scripts/build.mjs` produces the dependency-free static artifact in `dist/`.
