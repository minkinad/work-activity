# Server agent guidance

## Design rules

- Keep `server.py` and `monitoring/api.py` as composition roots.
- Routes authenticate and translate HTTP; services enforce use cases; repositories own
  SQL. Do not let services import Flask or issue SQL directly.
- Raise typed domain errors for expected failures so the shared HTTP error handler keeps
  responses consistent.
- Use timezone-aware UTC timestamps and the helpers from `monitoring/domain.py`.
- Validate all external strings, integers, timestamps, identifiers, and file sizes before
  persistence or filesystem access.
- Make multi-step command transitions atomic with SQLite transactions.

## Security rules

- All `/api/v1/client/*` requests must remain HMAC authenticated and replay protected.
- All `/api/v1/dashboard/*` routes, including files, must remain bearer authenticated.
- Never weaken secret length, CORS, TLS, PNG validation, path containment, or request-size
  controls to simplify tests or local development.
- Use constant-time comparisons for credentials and signatures.

## Validation

From `server/` run:

```bash
python -m unittest discover -s tests -v
ruff check monitoring tests server.py
bandit --quiet --recursive monitoring
pip-audit --requirement requirements.txt
python -m compileall -q monitoring server.py
```

Every fixed defect should receive a regression test in `tests/`.
