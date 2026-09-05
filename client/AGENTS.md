# Windows client agent guidance

## Design and security rules

- Keep wire-format changes coordinated with server routes and protocol tests.
- Sign the exact request bytes with the timestamp, nonce, client ID, and shared secret.
- Generate a unique cryptographically random nonce for every request.
- Keep TLS certificate verification enabled by default. Self-signed bypass is for isolated
  development only and must require explicit configuration.
- Never log the shared secret, signatures, screenshot bytes, or bearer credentials.
- Bound network payloads and release WinHTTP, GDI+, registry, service, and file handles on
  every return path.
- Do not add automatic screenshot capture. Screenshots are only responses to authenticated
  queued commands.

## Validation

Preferred build is Visual Studio `Release | x64`:

```powershell
msbuild Client.sln /m /p:Configuration=Release /p:Platform=x64
```

MinGW-w64 can be used from this directory with `make`. Changes to C++ code must also pass
the Windows CI build and CodeQL analysis.
