from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

INSECURE_SECRETS = {
    "",
    "change-me",
    "change-me-in-production",
    "secret",
    "password",
    "replace-with-a-random-client-secret-at-least-32-characters",
    "replace-with-a-different-random-dashboard-token-at-least-32-characters",
}


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _path_from_env(name: str, default: Path) -> Path:
    return Path(os.getenv(name, str(default))).expanduser().resolve()


@dataclass(frozen=True)
class Settings:
    database_path: Path
    screenshots_dir: Path
    api_host: str
    api_port: int
    client_timeout_seconds: int
    command_retry_seconds: int
    signature_tolerance_seconds: int
    client_shared_secret: str
    dashboard_token: str
    allowed_origins: tuple[str, ...]
    tls_cert_path: Path
    tls_key_path: Path
    max_screenshot_bytes: int = 10 * 1024 * 1024

    @classmethod
    def from_env(cls, server_dir: Path | None = None) -> Settings:
        root = (server_dir or Path(__file__).resolve().parent.parent).resolve()
        data_dir = root / "data"
        origins = tuple(
            origin.strip().rstrip("/")
            for origin in os.getenv(
                "MONITOR_FRONTEND_ORIGINS",
                "http://127.0.0.1:8081,http://localhost:8081",
            ).split(",")
            if origin.strip()
        )
        settings = cls(
            database_path=_path_from_env("MONITOR_DB_PATH", data_dir / "monitor.db"),
            screenshots_dir=_path_from_env("MONITOR_SCREENSHOTS_DIR", data_dir / "screenshots"),
            api_host=os.getenv("MONITOR_API_HOST", "127.0.0.1"),
            api_port=_positive_int("MONITOR_API_PORT", 5000),
            client_timeout_seconds=_positive_int("MONITOR_CLIENT_TIMEOUT", 180),
            command_retry_seconds=_positive_int("MONITOR_COMMAND_RETRY_SECONDS", 20),
            signature_tolerance_seconds=_positive_int("MONITOR_SIGNATURE_TOLERANCE_SECONDS", 300),
            client_shared_secret=os.getenv("MONITOR_SHARED_SECRET", ""),
            dashboard_token=os.getenv("MONITOR_DASHBOARD_TOKEN", ""),
            allowed_origins=origins,
            tls_cert_path=_path_from_env("MONITOR_TLS_CERT", root / "certs" / "server.crt"),
            tls_key_path=_path_from_env("MONITOR_TLS_KEY", root / "certs" / "server.key"),
            max_screenshot_bytes=_positive_int("MONITOR_MAX_SCREENSHOT_BYTES", 10 * 1024 * 1024),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        for name, value in (
            ("MONITOR_SHARED_SECRET", self.client_shared_secret),
            ("MONITOR_DASHBOARD_TOKEN", self.dashboard_token),
        ):
            if value.lower() in INSECURE_SECRETS or len(value) < 32:
                raise ValueError(f"{name} must contain at least 32 non-default characters")
        if self.client_shared_secret == self.dashboard_token:
            raise ValueError("Client and dashboard credentials must be different")
        if not self.allowed_origins:
            raise ValueError("MONITOR_FRONTEND_ORIGINS must contain at least one origin")
        if "*" in self.allowed_origins or "null" in self.allowed_origins:
            raise ValueError("Wildcard and null CORS origins are not allowed")
        if not 1 <= self.api_port <= 65535:
            raise ValueError("MONITOR_API_PORT must be between 1 and 65535")

    def ensure_runtime_directories(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

    def tls_context(self) -> tuple[str, str]:
        if not self.tls_cert_path.is_file() or not self.tls_key_path.is_file():
            raise FileNotFoundError(
                "TLS certificate or key is missing. Generate them or set "
                "MONITOR_TLS_CERT and MONITOR_TLS_KEY."
            )
        return str(self.tls_cert_path), str(self.tls_key_path)
