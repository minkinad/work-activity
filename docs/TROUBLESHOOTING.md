# Troubleshooting

## Server rejects configuration at startup

Both `MONITOR_SHARED_SECRET` and `MONITOR_DASHBOARD_TOKEN` must be different, non-default
values of at least 32 characters. `MONITOR_FRONTEND_ORIGINS` must contain exact origins and
cannot contain `*` or `null`.

## TLS certificate or key is missing

Run `server/tools/generate-dev-cert.sh` or the PowerShell equivalent. To use other paths,
set `MONITOR_TLS_CERT` and `MONITOR_TLS_KEY` to absolute files.

## Browser reports a network or CORS failure

- Trust the local API certificate in the browser.
- Verify the API URL uses HTTPS, except for an explicitly loopback-only HTTP setup.
- Add the frontend's exact scheme, host, and port to `MONITOR_FRONTEND_ORIGINS`.
- Restart the API after changing environment variables.
- Confirm `GET /health` is reachable independently of the dashboard.

## Dashboard returns 401

The value entered in the dashboard must exactly match `MONITOR_DASHBOARD_TOKEN`. Closing the
browser session removes the token from `sessionStorage`, so it must be entered again.

## Client requests return 401

Confirm that the client and server use the same `MONITOR_SHARED_SECRET`, system clocks are
synchronized, and every request uses a new nonce. Sign the exact UTF-8 bytes sent on the
wire; changing JSON whitespace after signing invalidates the signature.

## Screenshot command remains queued

The Windows client must be online and polling commands. Service mode can run in Windows
Session 0, where the interactive desktop is unavailable; use user-session mode when desktop
capture is required. Inspect the command history for a recorded client error.

## Frontend build is stale

Do not edit `frontend/dist`. Recreate it with:

```bash
make build-frontend
```

## Windows client does not build on Linux

The MSVC build is Windows-specific. Use the Windows GitHub Actions job, Visual Studio, or an
installed MinGW-w64 toolchain through `make build-client`.
