# Repository guidance for coding agents

## Scope

These instructions apply to the whole repository. More specific `AGENTS.md` files in
`server/`, `frontend/`, and `client/` add component-level rules.

## Product boundaries

- Treat activity records, machine metadata, IP addresses, and screenshots as sensitive.
- Do not add hidden collection, automatic screenshot capture, or a way around operator
  confirmation and authentication.
- Keep client HMAC credentials separate from the dashboard bearer credential.
- Do not commit secrets, certificates, private keys, databases, screenshots, build
  products, or dependency directories.
- Preserve protocol version compatibility unless the task explicitly includes a
  coordinated server and client migration.

## Architecture

- HTTP parsing and response concerns belong in `server/monitoring/routes/` or
  `server/monitoring/http.py`.
- Business rules belong in `server/monitoring/services.py` and must not depend on Flask.
- SQL and atomic state transitions belong in `server/monitoring/repositories.py`.
- Schema changes require a new ordered migration in `server/migrations/`; never rewrite
  an already released migration.
- Frontend network access goes through `frontend/src/api-client.js`. Render untrusted
  values with DOM nodes and `textContent`, never HTML string insertion.

## Required validation

Run the narrowest useful tests while editing and `make check` before handing off a
repository-wide change. On Linux, the native Windows client build is validated by CI.

Useful commands:

```bash
make help
make test
make lint
make security
make build
make check
```

## Change hygiene

- Keep changes scoped; preserve unrelated user edits in a dirty worktree.
- Add or update tests when behavior changes.
- Update `README.md` or `docs/` when commands, configuration, API contracts, security
  assumptions, or architecture change.
- Avoid introducing a dependency when the standard library or existing code is enough.
- Generated files are `frontend/dist/`, `client/build/`, `client/*.exe`, runtime data,
  and certificates. Do not hand-edit or commit them.
