from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

PROTOCOL_VERSION = 2
CLIENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
ACTIVITY_STATES = {"active", "idle"}
APP_MODES = {"background", "service"}


class DomainError(Exception):
    status_code = 400
    code = "invalid_request"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AuthenticationError(DomainError):
    status_code = 401
    code = "authentication_required"


class ConflictError(DomainError):
    status_code = 409
    code = "conflict"


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise DomainError(f"{field} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise DomainError(f"{field} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise DomainError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def require_string(payload: dict[str, Any], field: str, max_length: int) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise DomainError(f"{field} is required")
    value = value.strip()
    if len(value) > max_length:
        raise DomainError(f"{field} must not exceed {max_length} characters")
    return value


def optional_string(payload: dict[str, Any], field: str, max_length: int, default: str = "") -> str:
    value = payload.get(field, default)
    if not isinstance(value, str):
        raise DomainError(f"{field} must be a string")
    value = value.strip()
    if len(value) > max_length:
        raise DomainError(f"{field} must not exceed {max_length} characters")
    return value


def bounded_int(value: Any, field: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise DomainError(f"{field} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise DomainError(f"{field} must be an integer") from error
    if not minimum <= parsed <= maximum:
        raise DomainError(f"{field} must be between {minimum} and {maximum}")
    return parsed


def validate_client_id(value: Any) -> str:
    if not isinstance(value, str) or not CLIENT_ID_PATTERN.fullmatch(value):
        raise DomainError("client_id must use 1-128 letters, digits, dots, underscores, or hyphens")
    return value


def parse_limit(value: str | None, default: int, maximum: int) -> int:
    return bounded_int(default if value is None else value, "limit", 1, maximum)
