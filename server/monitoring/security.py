from __future__ import annotations

import base64
import hashlib
import hmac
from collections.abc import Callable
from datetime import datetime
from functools import wraps
from typing import TypeVar

from flask import Request, request

from .domain import (
    AuthenticationError,
    DomainError,
    parse_timestamp,
    utcnow,
    validate_client_id,
)
from .repositories import MonitorRepository

F = TypeVar("F", bound=Callable)


def compute_client_signature(
    secret: str,
    client_id: str,
    timestamp: str,
    nonce: str,
    body: bytes,
) -> str:
    material = b"\n".join(
        (timestamp.encode(), nonce.encode(), client_id.encode(), body)
    )
    return base64.b64encode(
        hmac.new(secret.encode(), material, hashlib.sha256).digest()
    ).decode("ascii")


class ClientAuthenticator:
    def __init__(
        self,
        secret: str,
        tolerance_seconds: int,
        repository: MonitorRepository,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self.secret = secret
        self.tolerance_seconds = tolerance_seconds
        self.repository = repository
        self.clock = clock

    def verify(self, http_request: Request, expected_client_id: str, body: bytes) -> None:
        client_id = validate_client_id(expected_client_id)
        signature = http_request.headers.get("X-Monitor-Signature", "")
        timestamp = http_request.headers.get("X-Monitor-Timestamp", "")
        nonce = http_request.headers.get("X-Monitor-Nonce", "")
        header_client_id = http_request.headers.get("X-Monitor-Client-Id", "")
        if not signature or not timestamp or not nonce or not header_client_id:
            raise AuthenticationError("Missing client signature headers")
        if len(nonce) > 128:
            raise AuthenticationError("Invalid request nonce")
        if not hmac.compare_digest(header_client_id, client_id):
            raise AuthenticationError("Client ID header does not match request body")
        try:
            sent_at = parse_timestamp(timestamp, "X-Monitor-Timestamp")
        except DomainError as error:
            raise AuthenticationError(error.message) from error
        now = self.clock()
        if abs((now - sent_at).total_seconds()) > self.tolerance_seconds:
            raise AuthenticationError("Signed request timestamp is outside the allowed window")
        expected = compute_client_signature(self.secret, client_id, timestamp, nonce, body)
        if not hmac.compare_digest(signature, expected):
            raise AuthenticationError("Invalid client request signature")
        self.repository.consume_nonce(
            client_id,
            nonce,
            now,
            retention_seconds=self.tolerance_seconds * 2,
        )


def dashboard_auth_required(token: str) -> Callable[[F], F]:
    def decorator(handler: F) -> F:
        @wraps(handler)
        def wrapped(*args, **kwargs):
            authorization = request.headers.get("Authorization", "")
            scheme, separator, supplied = authorization.partition(" ")
            if separator != " " or scheme.lower() != "bearer" or not supplied:
                raise AuthenticationError("Dashboard bearer token is required")
            if not hmac.compare_digest(supplied, token):
                raise AuthenticationError("Dashboard bearer token is invalid")
            return handler(*args, **kwargs)

        return wrapped  # type: ignore[return-value]

    return decorator
