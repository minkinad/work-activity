from __future__ import annotations

import json
from typing import Any

from flask import Flask, Response, jsonify, request
from werkzeug.exceptions import HTTPException

from .config import Settings
from .domain import DomainError


def request_object() -> tuple[dict[str, Any], bytes]:
    body = request.get_data(cache=True)
    if not body:
        raise DomainError("Request body is required")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DomainError("Request body must contain valid UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise DomainError("JSON body must be an object")
    return payload, body


def configure_http(app: Flask, settings: Settings) -> None:
    @app.before_request
    def enforce_dashboard_origin():
        origin = request.headers.get("Origin", "").rstrip("/")
        is_dashboard = request.path.startswith("/api/v1/dashboard")
        if is_dashboard and origin and origin not in settings.allowed_origins:
            return Response(status=403)
        if request.method == "OPTIONS" and request.path.startswith("/api/"):
            return Response(status=204 if origin in settings.allowed_origins else 403)
        return None

    @app.errorhandler(DomainError)
    def domain_error(error: DomainError):
        return jsonify({"error": {"code": error.code, "message": error.message}}), error.status_code

    @app.errorhandler(HTTPException)
    def http_error(error: HTTPException):
        return (
            jsonify(
                {
                    "error": {
                        "code": error.name.lower().replace(" ", "_"),
                        "message": error.description,
                    }
                }
            ),
            error.code,
        )

    @app.after_request
    def response_security(response: Response) -> Response:
        origin = request.headers.get("Origin", "").rstrip("/")
        if origin and origin in settings.allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers.add("Vary", "Origin")
            response.headers["Access-Control-Allow-Headers"] = (
                "Authorization, Content-Type, X-Monitor-Signature, "
                "X-Monitor-Timestamp, X-Monitor-Nonce, X-Monitor-Client-Id"
            )
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
            response.headers["Access-Control-Max-Age"] = "600"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        if request.path.startswith("/api/v1/dashboard"):
            response.headers["Cache-Control"] = "no-store, private"
        return response
