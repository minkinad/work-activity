from __future__ import annotations

import base64
import binascii
import hashlib
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .config import Settings
from .domain import (
    ACTIVITY_STATES,
    APP_MODES,
    PROTOCOL_VERSION,
    ConflictError,
    DomainError,
    bounded_int,
    isoformat,
    optional_string,
    parse_timestamp,
    require_string,
    utcnow,
    validate_client_id,
)
from .repositories import MonitorRepository, serialize_command, serialize_screenshot

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class ActivityService:
    def __init__(
        self,
        repository: MonitorRepository,
        client_timeout_seconds: int,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self.repository = repository
        self.client_timeout_seconds = client_timeout_seconds
        self.clock = clock

    def record_heartbeat(self, payload: dict[str, Any], source_ip: str) -> None:
        client_id = validate_client_id(payload.get("client_id"))
        state = require_string(payload, "activity_state", 16)
        if state not in ACTIVITY_STATES:
            raise DomainError("activity_state must be active or idle")
        app_mode = optional_string(payload, "app_mode", 32, "background") or "background"
        if app_mode not in APP_MODES:
            raise DomainError("app_mode must be background or service")
        protocol_version = bounded_int(
            payload.get("protocol_version", PROTOCOL_VERSION),
            "protocol_version",
            1,
            100,
        )
        if protocol_version != PROTOCOL_VERSION:
            raise ConflictError(
                f"Unsupported protocol version {protocol_version}; expected {PROTOCOL_VERSION}"
            )

        now = self.clock()
        last_active = parse_timestamp(
            payload.get("last_active_at", isoformat(now)), "last_active_at"
        )
        if last_active > now + timedelta(minutes=5):
            raise DomainError("last_active_at must not be more than five minutes in the future")

        heartbeat = {
            "client_id": client_id,
            "domain": optional_string(payload, "domain", 255),
            "machine": optional_string(payload, "machine", 255),
            "user": optional_string(payload, "user", 255),
            "ip_address": optional_string(payload, "ip_address", 64),
            "activity_state": state,
            "idle_seconds": bounded_int(payload.get("idle_seconds", 0), "idle_seconds", 0, 86400 * 30),
            "last_active_at": isoformat(last_active),
            "app_mode": app_mode,
            "service_name": optional_string(payload, "service_name", 255),
            "protocol_version": protocol_version,
        }
        self.repository.upsert_client(heartbeat, source_ip, now)

    def list_clients(self) -> list[dict[str, Any]]:
        now = self.clock()
        clients = []
        for row, latest_screenshot in self.repository.list_clients_with_latest_screenshot():
            last_seen = parse_timestamp(row["last_seen_at"], "last_seen_at")
            clients.append(
                {
                    "client_id": row["client_id"],
                    "domain": row["domain_name"],
                    "machine": row["machine_name"],
                    "user": row["user_name"],
                    "ip_address": row["ip_address"],
                    "activity_state": row["activity_state"],
                    "idle_seconds": row["idle_seconds"],
                    "last_active_at": row["last_active_at"],
                    "last_seen_at": row["last_seen_at"],
                    "status": "online"
                    if (now - last_seen).total_seconds() <= self.client_timeout_seconds
                    else "offline",
                    "app_mode": row["app_mode"],
                    "service_name": row["service_name"],
                    "protocol_version": row["protocol_version"],
                    "latest_screenshot": serialize_screenshot(latest_screenshot)
                    if latest_screenshot
                    else None,
                }
            )
        return clients

    def list_activity(self, client_id: str | None, limit: int) -> list[dict[str, Any]]:
        if client_id:
            validate_client_id(client_id)
        return [
            {
                "id": row["id"],
                "client_id": row["client_id"],
                "activity_state": row["activity_state"],
                "idle_seconds": row["idle_seconds"],
                "last_active_at": row["last_active_at"],
                "received_at": row["received_at"],
                "source_ip": row["source_ip"],
            }
            for row in self.repository.list_activity(client_id, limit)
        ]


class CommandService:
    def __init__(
        self,
        repository: MonitorRepository,
        settings: Settings,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.clock = clock

    def enqueue_screenshot(self, client_id: str, issued_by: str = "dashboard") -> dict[str, Any]:
        client_id = validate_client_id(client_id)
        self.repository.get_client(client_id)
        return serialize_command(
            self.repository.enqueue_screenshot(client_id, issued_by, self.clock())
        )

    def poll(self, client_id: str) -> dict[str, Any] | None:
        client_id = validate_client_id(client_id)
        self.repository.get_client(client_id)
        row = self.repository.claim_next_command(
            client_id, self.clock(), self.settings.command_retry_seconds
        )
        return serialize_command(row) if row else None

    def report_failure(self, command_id: int, client_id: str, error: Any) -> dict[str, Any]:
        client_id = validate_client_id(client_id)
        self.repository.get_command_for_client(command_id, client_id)
        if not isinstance(error, str) or not error.strip():
            error = "Client reported a command failure"
        error = error.strip()[:2000]
        return serialize_command(
            self.repository.fail_command(command_id, error, self.clock())
        )

    def upload_screenshot(
        self,
        command_id: int,
        client_id: str,
        image_base64: Any,
        captured_at: Any,
    ) -> dict[str, Any]:
        client_id = validate_client_id(client_id)
        captured = parse_timestamp(captured_at, "captured_at")
        now = self.clock()
        if captured > now + timedelta(minutes=5):
            raise DomainError("captured_at must not be more than five minutes in the future")
        image = self._decode_png(image_base64)
        digest = hashlib.sha256(image).hexdigest()
        file_name = f"{client_id}_{uuid.uuid4().hex}.png"
        file_path = self.settings.screenshots_dir / file_name
        file_path.write_bytes(image)
        try:
            row = self.repository.complete_screenshot(
                command_id,
                client_id,
                file_name,
                str(file_path),
                isoformat(captured),
                len(image),
                digest,
                now,
            )
        except Exception:
            file_path.unlink(missing_ok=True)
            raise
        return serialize_screenshot(row)

    def _decode_png(self, image_base64: Any) -> bytes:
        if not isinstance(image_base64, str) or not image_base64:
            raise DomainError("image_base64 is required")
        maximum_encoded_size = ((self.settings.max_screenshot_bytes + 2) // 3) * 4
        if len(image_base64) > maximum_encoded_size + 4:
            raise DomainError("Screenshot exceeds the configured size limit")
        try:
            image = base64.b64decode(image_base64, validate=True)
        except (ValueError, binascii.Error) as error:
            raise DomainError("image_base64 must contain valid base64") from error
        if not image.startswith(PNG_SIGNATURE):
            raise DomainError("Only PNG screenshots are accepted")
        if len(image) > self.settings.max_screenshot_bytes:
            raise DomainError("Screenshot exceeds the configured size limit")
        return image

    def list_commands(self, client_id: str | None, limit: int) -> list[dict[str, Any]]:
        if client_id:
            validate_client_id(client_id)
        return [serialize_command(row) for row in self.repository.list_commands(client_id, limit)]

    def list_screenshots(self, client_id: str | None, limit: int) -> list[dict[str, Any]]:
        if client_id:
            validate_client_id(client_id)
        return [
            serialize_screenshot(row)
            for row in self.repository.list_screenshots(client_id, limit)
        ]

    def screenshot_path(self, screenshot_id: int) -> Path:
        row = self.repository.get_screenshot(screenshot_id)
        path = Path(row["file_path"]).resolve()
        screenshots_dir = self.settings.screenshots_dir.resolve()
        if path.parent != screenshots_dir or not path.is_file():
            raise DomainError("Screenshot file is unavailable")
        return path
