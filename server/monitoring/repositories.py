from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import timedelta
from typing import Any

from .database import Database
from .domain import ConflictError, NotFoundError, isoformat


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


class MonitorRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def consume_nonce(self, client_id: str, nonce: str, now, retention_seconds: int) -> None:
        threshold = isoformat(now - timedelta(seconds=retention_seconds))
        with self.database.write() as connection:
            connection.execute("DELETE FROM request_nonces WHERE created_at < ?", (threshold,))
            try:
                connection.execute(
                    "INSERT INTO request_nonces (client_id, nonce, created_at) VALUES (?, ?, ?)",
                    (client_id, nonce, isoformat(now)),
                )
            except sqlite3.IntegrityError as error:
                raise ConflictError("Signed request nonce has already been used") from error

    def upsert_client(self, heartbeat: dict[str, Any], source_ip: str, now) -> None:
        timestamp = isoformat(now)
        values = (
            heartbeat["client_id"],
            heartbeat["domain"],
            heartbeat["machine"],
            heartbeat["user"],
            heartbeat["ip_address"] or source_ip,
            heartbeat["activity_state"],
            heartbeat["idle_seconds"],
            heartbeat["last_active_at"],
            timestamp,
            heartbeat["app_mode"],
            heartbeat["service_name"],
            heartbeat["protocol_version"],
            timestamp,
            timestamp,
        )
        with self.database.write() as connection:
            connection.execute(
                """
                INSERT INTO clients (
                    client_id, domain_name, machine_name, user_name, ip_address,
                    activity_state, idle_seconds, last_active_at, last_seen_at,
                    app_mode, service_name, protocol_version, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(client_id) DO UPDATE SET
                    domain_name = excluded.domain_name,
                    machine_name = excluded.machine_name,
                    user_name = excluded.user_name,
                    ip_address = excluded.ip_address,
                    activity_state = excluded.activity_state,
                    idle_seconds = excluded.idle_seconds,
                    last_active_at = excluded.last_active_at,
                    last_seen_at = excluded.last_seen_at,
                    app_mode = excluded.app_mode,
                    service_name = excluded.service_name,
                    protocol_version = excluded.protocol_version,
                    updated_at = excluded.updated_at
                """,
                values,
            )
            connection.execute(
                """
                INSERT INTO activity_history (
                    client_id, activity_state, idle_seconds, last_active_at, received_at, source_ip
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    heartbeat["client_id"],
                    heartbeat["activity_state"],
                    heartbeat["idle_seconds"],
                    heartbeat["last_active_at"],
                    timestamp,
                    source_ip,
                ),
            )

    def get_client(self, client_id: str) -> sqlite3.Row:
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT * FROM clients WHERE client_id = ?", (client_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("Client not found")
        return row

    def list_clients_with_latest_screenshot(self) -> list[tuple[sqlite3.Row, sqlite3.Row | None]]:
        with self.database.read() as connection:
            clients = connection.execute(
                "SELECT * FROM clients ORDER BY last_seen_at DESC"
            ).fetchall()
            screenshot_rows = connection.execute(
                """
                SELECT s.* FROM screenshots s
                INNER JOIN (
                    SELECT client_id, MAX(id) AS latest_id
                    FROM screenshots GROUP BY client_id
                ) latest ON latest.latest_id = s.id
                """
            ).fetchall()
        screenshots = {row["client_id"]: row for row in screenshot_rows}
        return [(row, screenshots.get(row["client_id"])) for row in clients]

    def list_activity(self, client_id: str | None, limit: int) -> list[sqlite3.Row]:
        sql = "SELECT * FROM activity_history"
        params: list[Any] = []
        if client_id:
            sql += " WHERE client_id = ?"
            params.append(client_id)
        sql += " ORDER BY received_at DESC LIMIT ?"
        params.append(limit)
        with self.database.read() as connection:
            return connection.execute(sql, params).fetchall()

    def enqueue_screenshot(self, client_id: str, issued_by: str, now) -> sqlite3.Row:
        timestamp = isoformat(now)
        with self.database.write() as connection:
            existing = connection.execute(
                """
                SELECT id FROM commands
                WHERE client_id = ? AND command_type = 'capture_screenshot'
                  AND status IN ('queued', 'dispatched')
                LIMIT 1
                """,
                (client_id,),
            ).fetchone()
            if existing is not None:
                raise ConflictError("A screenshot command is already pending for this client")
            cursor = connection.execute(
                """
                INSERT INTO commands (
                    request_uuid, client_id, command_type, payload_json, status,
                    issued_by, created_at, updated_at
                ) VALUES (?, ?, 'capture_screenshot', ?, 'queued', ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex,
                    client_id,
                    _json({"reason": "dashboard_request"}),
                    issued_by,
                    timestamp,
                    timestamp,
                ),
            )
            return connection.execute(
                "SELECT * FROM commands WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()

    def claim_next_command(self, client_id: str, now, retry_seconds: int) -> sqlite3.Row | None:
        timestamp = isoformat(now)
        retry_threshold = isoformat(now - timedelta(seconds=retry_seconds))
        with self.database.write() as connection:
            row = connection.execute(
                """
                SELECT * FROM commands
                WHERE client_id = ?
                  AND (status = 'queued' OR (
                      status = 'dispatched' AND dispatched_at IS NOT NULL AND dispatched_at <= ?
                  ))
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """,
                (client_id, retry_threshold),
            ).fetchone()
            if row is None:
                return None
            updated = connection.execute(
                """
                UPDATE commands
                SET status = 'dispatched', dispatched_at = ?, updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (timestamp, timestamp, row["id"], row["status"]),
            )
            if updated.rowcount != 1:
                return None
            return connection.execute(
                "SELECT * FROM commands WHERE id = ?", (row["id"],)
            ).fetchone()

    def get_command_for_client(self, command_id: int, client_id: str) -> sqlite3.Row:
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT * FROM commands WHERE id = ? AND client_id = ?",
                (command_id, client_id),
            ).fetchone()
        if row is None:
            raise NotFoundError("Command not found for this client")
        return row

    def fail_command(self, command_id: int, error_text: str, now) -> sqlite3.Row:
        timestamp = isoformat(now)
        with self.database.write() as connection:
            updated = connection.execute(
                """
                UPDATE commands
                SET status = 'failed', completed_at = ?, updated_at = ?,
                    result_json = ?, error_text = ?
                WHERE id = ? AND status = 'dispatched'
                """,
                (timestamp, timestamp, _json({"status": "failed"}), error_text, command_id),
            )
            if updated.rowcount != 1:
                raise ConflictError("Only a dispatched command can be marked as failed")
            return connection.execute(
                "SELECT * FROM commands WHERE id = ?", (command_id,)
            ).fetchone()

    def complete_screenshot(
        self,
        command_id: int,
        client_id: str,
        file_name: str,
        file_path: str,
        captured_at: str,
        byte_size: int,
        sha256_hex: str,
        now,
    ) -> sqlite3.Row:
        timestamp = isoformat(now)
        result = _json({"screenshot_file_name": file_name, "sha256_hex": sha256_hex})
        with self.database.write() as connection:
            command = connection.execute(
                "SELECT * FROM commands WHERE id = ? AND client_id = ?",
                (command_id, client_id),
            ).fetchone()
            if command is None:
                raise NotFoundError("Command not found for this client")
            if command["command_type"] != "capture_screenshot" or command["status"] != "dispatched":
                raise ConflictError("Screenshot upload requires a dispatched screenshot command")
            cursor = connection.execute(
                """
                INSERT INTO screenshots (
                    command_id, client_id, file_name, file_path, captured_at,
                    uploaded_at, byte_size, sha256_hex
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    command_id,
                    client_id,
                    file_name,
                    file_path,
                    captured_at,
                    timestamp,
                    byte_size,
                    sha256_hex,
                ),
            )
            connection.execute(
                """
                UPDATE commands
                SET status = 'completed', completed_at = ?, updated_at = ?,
                    result_json = ?, error_text = NULL
                WHERE id = ?
                """,
                (timestamp, timestamp, result, command_id),
            )
            return connection.execute(
                "SELECT * FROM screenshots WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()

    def list_commands(self, client_id: str | None, limit: int) -> list[sqlite3.Row]:
        sql = "SELECT * FROM commands"
        params: list[Any] = []
        if client_id:
            sql += " WHERE client_id = ?"
            params.append(client_id)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(limit)
        with self.database.read() as connection:
            return connection.execute(sql, params).fetchall()

    def list_screenshots(self, client_id: str | None, limit: int) -> list[sqlite3.Row]:
        sql = "SELECT * FROM screenshots"
        params: list[Any] = []
        if client_id:
            sql += " WHERE client_id = ?"
            params.append(client_id)
        sql += " ORDER BY uploaded_at DESC, id DESC LIMIT ?"
        params.append(limit)
        with self.database.read() as connection:
            return connection.execute(sql, params).fetchall()

    def get_screenshot(self, screenshot_id: int) -> sqlite3.Row:
        with self.database.read() as connection:
            row = connection.execute(
                "SELECT * FROM screenshots WHERE id = ?", (screenshot_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError("Screenshot not found")
        return row


def serialize_command(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "request_uuid": row["request_uuid"],
        "client_id": row["client_id"],
        "command_type": row["command_type"],
        "payload": json.loads(row["payload_json"]),
        "status": row["status"],
        "issued_by": row["issued_by"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "dispatched_at": row["dispatched_at"],
        "completed_at": row["completed_at"],
        "result": json.loads(row["result_json"]) if row["result_json"] else None,
        "error_text": row["error_text"],
    }


def serialize_screenshot(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "command_id": row["command_id"],
        "client_id": row["client_id"],
        "file_name": row["file_name"],
        "captured_at": row["captured_at"],
        "uploaded_at": row["uploaded_at"],
        "byte_size": row["byte_size"],
        "sha256_hex": row["sha256_hex"],
        "url": f"/api/v1/dashboard/screenshots/{row['id']}/file",
    }
