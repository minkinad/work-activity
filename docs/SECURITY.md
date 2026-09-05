# Security model

Инструкция по приватному сообщению об уязвимостях находится в корневом
[`SECURITY.md`](../SECURITY.md).

## Required controls

- Run the API only over TLS.
- Generate different random values for `MONITOR_SHARED_SECRET` and
  `MONITOR_DASHBOARD_TOKEN`; both must be at least 32 characters.
- Keep `allow_self_signed_tls = false` outside isolated local development.
- Set `MONITOR_FRONTEND_ORIGINS` to the exact dashboard origins.
- Bind to `127.0.0.1` unless a firewall or private network explicitly protects the API.

Generate suitable development values with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Generate the two values separately. Do not put either value in Git.

## Authentication

Windows clients sign the exact request body with HMAC-SHA256. The signature covers the
timestamp, nonce, client identifier, and body. The server rejects stale timestamps and
reused nonces.

Every dashboard endpoint, including screenshot files, requires:

```text
Authorization: Bearer <MONITOR_DASHBOARD_TOKEN>
```

The browser dashboard keeps this token in `sessionStorage`, so closing the tab session
removes it. The API returns `Cache-Control: no-store` for dashboard data.

## Current scope

The bearer token represents one operator role. It is appropriate for a single-operator
demo or a private environment, not for a multi-tenant deployment. Production evolution
should add SSO, named operators, RBAC, audit events, credential rotation, retention rules,
and explicit employee consent/policy controls.

## Automated checks

- Bandit scans Python code for common security mistakes.
- `pip-audit` checks production Python dependencies against vulnerability advisories.
- `npm audit` verifies the dependency-free frontend package metadata.
- The frontend checker rejects inline event handlers, `innerHTML`, `outerHTML`,
  `insertAdjacentHTML`, `document.write`, and `eval`.
- CodeQL analyzes Python, JavaScript, and the Windows C++ client.
