# API quick reference

All request and response bodies use JSON unless the endpoint returns a PNG. Timestamps are
timezone-aware ISO 8601 values. Expected API failures use:

```json
{"error":{"code":"invalid_request","message":"Human-readable explanation"}}
```

## Health

- `GET /` returns the service and protocol version.
- `GET /health` returns process health and server time.

## Client authentication

All `/api/v1/client/*` endpoints require `X-Monitor-Client-Id`,
`X-Monitor-Timestamp`, `X-Monitor-Nonce`, and `X-Monitor-Signature`. The HMAC-SHA256 input
is:

```text
timestamp + "\n" + nonce + "\n" + client_id + "\n" + raw_body
```

Client endpoints:

- `POST /api/v1/client/heartbeat` records current activity and client metadata.
- `POST /api/v1/client/commands/poll` atomically claims the next command.
- `POST /api/v1/client/commands/<id>/fail` records a command error.
- `POST /api/v1/client/commands/<id>/screenshot` uploads a base64 PNG and completes the
  command.

Protocol version `2` is required. Nonces are single-use and timestamps outside the allowed
tolerance are rejected.

## Dashboard authentication

All `/api/v1/dashboard/*` endpoints require:

```text
Authorization: Bearer <MONITOR_DASHBOARD_TOKEN>
```

Endpoints:

- `GET /api/v1/dashboard/clients`
- `GET /api/v1/dashboard/activity?client_id=<id>&limit=<1..200>`
- `GET /api/v1/dashboard/commands?client_id=<id>&limit=<1..200>`
- `GET /api/v1/dashboard/screenshots?client_id=<id>&limit=<1..100>`
- `GET /api/v1/dashboard/screenshots/<id>/file`
- `POST /api/v1/dashboard/clients/<client_id>/commands/screenshot`

`client_id` is optional on list endpoints. Screenshot command creation returns HTTP 202;
a conflicting pending command returns HTTP 409.
