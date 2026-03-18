import base64
import hashlib
import hmac
import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from flask import Flask, Response, abort, jsonify, request, send_from_directory


# The server stores all operational state on disk so that command history and
# activity history survive restarts.
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
DATA_DIR.mkdir(exist_ok=True)
SCREENSHOTS_DIR.mkdir(exist_ok=True)

DB_PATH = Path(os.getenv("MONITOR_DB_PATH", str(DATA_DIR / "monitor.db")))
API_HOST = os.getenv("MONITOR_API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("MONITOR_API_PORT", "5000"))
CLIENT_TIMEOUT_SECONDS = int(os.getenv("MONITOR_CLIENT_TIMEOUT", "180"))
COMMAND_RETRY_SECONDS = int(os.getenv("MONITOR_COMMAND_RETRY_SECONDS", "20"))
SIGNATURE_TOLERANCE_SECONDS = int(os.getenv("MONITOR_SIGNATURE_TOLERANCE_SECONDS", "300"))
SHARED_SECRET = os.getenv("MONITOR_SHARED_SECRET", "change-me-in-production")
TLS_CERT_PATH = os.getenv("MONITOR_TLS_CERT", str(BASE_DIR / "certs" / "server.crt"))
TLS_KEY_PATH = os.getenv("MONITOR_TLS_KEY", str(BASE_DIR / "certs" / "server.key"))
FRONTEND_ORIGIN = os.getenv("MONITOR_FRONTEND_ORIGIN", "*")

PROTOCOL_VERSION = 2

app = Flask(__name__)
db_lock = threading.RLock()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def serialize_json(value: Any) -> str:
    # Canonical JSON keeps signatures and persisted payloads deterministic.
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def compute_signature(client_id: str, timestamp: str, nonce: str, body: bytes) -> str:
    mac = hmac.new(SHARED_SECRET.encode("utf-8"), digestmod=hashlib.sha256)
    mac.update(timestamp.encode("utf-8"))
    mac.update(b"\n")
    mac.update(nonce.encode("utf-8"))
    mac.update(b"\n")
    mac.update(client_id.encode("utf-8"))
    mac.update(b"\n")
    mac.update(body)
    return base64.b64encode(mac.digest()).decode("ascii")


def sanitize_client_id(client_id: str) -> str:
    return "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in client_id)


@contextmanager
def db_connection() -> Iterable[sqlite3.Connection]:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def initialize_database() -> None:
    with db_lock, db_connection() as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS clients (
                client_id TEXT PRIMARY KEY,
                domain_name TEXT NOT NULL,
                machine_name TEXT NOT NULL,
                user_name TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                activity_state TEXT NOT NULL,
                idle_seconds INTEGER NOT NULL,
                last_active_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                app_mode TEXT NOT NULL,
                service_name TEXT NOT NULL,
                protocol_version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT NOT NULL,
                activity_state TEXT NOT NULL,
                idle_seconds INTEGER NOT NULL,
                last_active_at TEXT NOT NULL,
                received_at TEXT NOT NULL,
                source_ip TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_uuid TEXT NOT NULL UNIQUE,
                client_id TEXT NOT NULL,
                command_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                issued_by TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                dispatched_at TEXT,
                completed_at TEXT,
                result_json TEXT,
                error_text TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS screenshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command_id INTEGER NOT NULL,
                client_id TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                uploaded_at TEXT NOT NULL,
                byte_size INTEGER NOT NULL,
                sha256_hex TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS request_nonces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT NOT NULL,
                nonce TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(client_id, nonce)
            )
            """
        )


def cleanup_expired_nonces(connection: sqlite3.Connection) -> None:
    threshold = isoformat(utcnow() - timedelta(seconds=SIGNATURE_TOLERANCE_SECONDS * 2))
    connection.execute("DELETE FROM request_nonces WHERE created_at < ?", (threshold,))


def parse_client_request_json() -> tuple[dict[str, Any], bytes]:
    body = request.get_data(cache=False)
    if not body:
        abort(400, description="Request body is required")

    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as error:
        abort(400, description=f"Invalid JSON body: {error}")

    if not isinstance(payload, dict):
        abort(400, description="JSON body must be an object")

    return payload, body


def verify_signed_client_request(expected_client_id: str, body: bytes) -> None:
    signature = request.headers.get("X-Monitor-Signature", "")
    timestamp = request.headers.get("X-Monitor-Timestamp", "")
    nonce = request.headers.get("X-Monitor-Nonce", "")
    header_client_id = request.headers.get("X-Monitor-Client-Id", "")

    if not signature or not timestamp or not nonce or not header_client_id:
        abort(401, description="Missing signature headers")

    if header_client_id != expected_client_id:
        abort(401, description="Client ID header does not match request body")

    try:
        sent_at = parse_timestamp(timestamp)
    except ValueError:
        abort(401, description="Invalid signature timestamp")

    age = abs((utcnow() - sent_at).total_seconds())
    if age > SIGNATURE_TOLERANCE_SECONDS:
        abort(401, description="Signed request timestamp is outside the allowed window")

    expected_signature = compute_signature(expected_client_id, timestamp, nonce, body)
    if not hmac.compare_digest(signature, expected_signature):
        abort(401, description="Invalid request signature")

    with db_lock, db_connection() as connection:
        cleanup_expired_nonces(connection)
        try:
            connection.execute(
                "INSERT INTO request_nonces (client_id, nonce, created_at) VALUES (?, ?, ?)",
                (expected_client_id, nonce, isoformat(utcnow())),
            )
        except sqlite3.IntegrityError:
            abort(409, description="Duplicate signed request nonce")


def fetch_client_row(client_id: str) -> sqlite3.Row:
    with db_lock, db_connection() as connection:
        row = connection.execute("SELECT * FROM clients WHERE client_id = ?", (client_id,)).fetchone()
    if row is None:
        abort(404, description="Client not found")
    return row


def fetch_command_row(command_id: int, client_id: str) -> sqlite3.Row:
    with db_lock, db_connection() as connection:
        row = connection.execute(
            "SELECT * FROM commands WHERE id = ? AND client_id = ?",
            (command_id, client_id),
        ).fetchone()
    if row is None:
        abort(404, description="Command not found for this client")
    return row


def compute_client_status(last_seen_at: str) -> str:
    last_seen = parse_timestamp(last_seen_at)
    return "online" if (utcnow() - last_seen).total_seconds() <= CLIENT_TIMEOUT_SECONDS else "offline"


def serialize_client(row: sqlite3.Row, latest_screenshot: Optional[sqlite3.Row]) -> dict[str, Any]:
    return {
        "client_id": row["client_id"],
        "domain": row["domain_name"],
        "machine": row["machine_name"],
        "user": row["user_name"],
        "ip_address": row["ip_address"],
        "activity_state": row["activity_state"],
        "idle_seconds": row["idle_seconds"],
        "last_active_at": row["last_active_at"],
        "last_seen_at": row["last_seen_at"],
        "status": compute_client_status(row["last_seen_at"]),
        "app_mode": row["app_mode"],
        "service_name": row["service_name"],
        "protocol_version": row["protocol_version"],
        "latest_screenshot": serialize_screenshot(latest_screenshot) if latest_screenshot else None,
    }


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


def upsert_client(payload: dict[str, Any], source_ip: str) -> None:
    now = isoformat(utcnow())
    values = (
        payload["client_id"],
        payload.get("domain", ""),
        payload.get("machine", ""),
        payload.get("user", ""),
        payload.get("ip_address") or source_ip,
        payload.get("activity_state", "unknown"),
        int(payload.get("idle_seconds", 0)),
        payload.get("last_active_at", now),
        now,
        payload.get("app_mode", "background"),
        payload.get("service_name", ""),
        int(payload.get("protocol_version", PROTOCOL_VERSION)),
        now,
        now,
    )

    with db_lock, db_connection() as connection:
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
                payload["client_id"],
                payload.get("activity_state", "unknown"),
                int(payload.get("idle_seconds", 0)),
                payload.get("last_active_at", now),
                now,
                source_ip,
            ),
        )


def enqueue_command(client_id: str, command_type: str, payload: dict[str, Any], issued_by: str) -> dict[str, Any]:
    now = isoformat(utcnow())
    request_uuid = uuid.uuid4().hex

    with db_lock, db_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO commands (
                request_uuid, client_id, command_type, payload_json, status,
                issued_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'queued', ?, ?, ?)
            """,
            (request_uuid, client_id, command_type, serialize_json(payload), issued_by, now, now),
        )
        command_id = cursor.lastrowid
        row = connection.execute("SELECT * FROM commands WHERE id = ?", (command_id,)).fetchone()

    return serialize_command(row)


def claim_next_command(client_id: str) -> Optional[dict[str, Any]]:
    now = isoformat(utcnow())
    retry_threshold = isoformat(utcnow() - timedelta(seconds=COMMAND_RETRY_SECONDS))

    with db_lock, db_connection() as connection:
        row = connection.execute(
            """
            SELECT * FROM commands
            WHERE client_id = ?
              AND (
                    status = 'queued'
                    OR (status = 'dispatched' AND dispatched_at IS NOT NULL AND dispatched_at <= ?)
                  )
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (client_id, retry_threshold),
        ).fetchone()

        if row is None:
            return None

        connection.execute(
            """
            UPDATE commands
            SET status = 'dispatched', dispatched_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, now, row["id"]),
        )
        claimed = connection.execute("SELECT * FROM commands WHERE id = ?", (row["id"],)).fetchone()

    return serialize_command(claimed)


def store_screenshot(command_id: int, client_id: str, image_bytes: bytes, captured_at: str) -> dict[str, Any]:
    client_slug = sanitize_client_id(client_id)
    sha256_hex = hashlib.sha256(image_bytes).hexdigest()
    file_name = f"{client_slug}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.png"
    file_path = SCREENSHOTS_DIR / file_name
    file_path.write_bytes(image_bytes)

    now = isoformat(utcnow())
    result_json = serialize_json({"screenshot_file_name": file_name, "sha256_hex": sha256_hex})

    with db_lock, db_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO screenshots (
                command_id, client_id, file_name, file_path, captured_at, uploaded_at, byte_size, sha256_hex
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (command_id, client_id, file_name, str(file_path), captured_at, now, len(image_bytes), sha256_hex),
        )
        screenshot_id = cursor.lastrowid
        connection.execute(
            """
            UPDATE commands
            SET status = 'completed', completed_at = ?, updated_at = ?, result_json = ?, error_text = NULL
            WHERE id = ?
            """,
            (now, now, result_json, command_id),
        )
        row = connection.execute("SELECT * FROM screenshots WHERE id = ?", (screenshot_id,)).fetchone()

    return serialize_screenshot(row)


def fail_command(command_id: int, error_text: str) -> dict[str, Any]:
    now = isoformat(utcnow())
    result_json = serialize_json({"status": "failed"})

    with db_lock, db_connection() as connection:
        connection.execute(
            """
            UPDATE commands
            SET status = 'failed', completed_at = ?, updated_at = ?, result_json = ?, error_text = ?
            WHERE id = ?
            """,
            (now, now, result_json, error_text, command_id),
        )
        row = connection.execute("SELECT * FROM commands WHERE id = ?", (command_id,)).fetchone()

    return serialize_command(row)


def get_latest_screenshot_map(connection: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    rows = connection.execute(
        """
        SELECT s.*
        FROM screenshots s
        INNER JOIN (
            SELECT client_id, MAX(id) AS latest_id
            FROM screenshots
            GROUP BY client_id
        ) latest
        ON latest.latest_id = s.id
        """
    ).fetchall()
    return {row["client_id"]: row for row in rows}


@app.after_request
def apply_cors_headers(response: Response) -> Response:
    # The dashboard is a standalone frontend, so API responses must be consumable
    # from a different origin during development and deployment.
    response.headers["Access-Control-Allow-Origin"] = FRONTEND_ORIGIN
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Monitor-Signature, X-Monitor-Timestamp, X-Monitor-Nonce, X-Monitor-Client-Id"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


@app.route("/api/<path:_path>", methods=["OPTIONS"])
def api_options(_path: str) -> Response:
    return Response(status=204)


@app.route("/")
def root() -> Response:
    return jsonify(
        {
            "service": "work-activity-monitor-api",
            "protocol_version": PROTOCOL_VERSION,
            "frontend_hint": "Run the standalone frontend from ./frontend and point it to this API server.",
        }
    )


@app.route("/health")
def health() -> Response:
    return jsonify({"status": "ok", "time": isoformat(utcnow())})


@app.route("/api/v1/client/heartbeat", methods=["POST"])
def client_heartbeat() -> Response:
    payload, body = parse_client_request_json()
    client_id = payload.get("client_id", "")
    if not client_id:
        abort(400, description="client_id is required")

    verify_signed_client_request(client_id, body)
    upsert_client(payload, request.remote_addr or "")
    return jsonify({"status": "ok", "received_at": isoformat(utcnow())})


@app.route("/api/v1/client/commands/poll", methods=["POST"])
def client_poll_commands() -> Response:
    payload, body = parse_client_request_json()
    client_id = payload.get("client_id", "")
    if not client_id:
        abort(400, description="client_id is required")

    verify_signed_client_request(client_id, body)
    command = claim_next_command(client_id)
    return jsonify({"command": command, "server_time": isoformat(utcnow())})


@app.route("/api/v1/client/commands/<int:command_id>/complete", methods=["POST"])
def client_complete_command(command_id: int) -> Response:
    payload, body = parse_client_request_json()
    client_id = payload.get("client_id", "")
    if not client_id:
        abort(400, description="client_id is required")

    verify_signed_client_request(client_id, body)
    fetch_command_row(command_id, client_id)
    error_text = payload.get("error", "Client reported a command failure")
    command = fail_command(command_id, error_text)
    return jsonify({"status": "recorded", "command": command})


@app.route("/api/v1/client/commands/<int:command_id>/screenshot", methods=["POST"])
def client_upload_screenshot(command_id: int) -> Response:
    payload, body = parse_client_request_json()
    client_id = payload.get("client_id", "")
    image_base64 = payload.get("image_base64", "")
    captured_at = payload.get("captured_at", isoformat(utcnow()))

    if not client_id or not image_base64:
        abort(400, description="client_id and image_base64 are required")

    verify_signed_client_request(client_id, body)
    command = fetch_command_row(command_id, client_id)
    if command["command_type"] != "capture_screenshot":
        abort(409, description="Command type does not accept screenshot uploads")

    try:
        image_bytes = base64.b64decode(image_base64)
    except ValueError:
        abort(400, description="image_base64 is not valid base64")

    screenshot = store_screenshot(command_id, client_id, image_bytes, captured_at)
    return jsonify({"status": "completed", "screenshot": screenshot})


@app.route("/api/v1/dashboard/clients", methods=["GET"])
def dashboard_clients() -> Response:
    with db_lock, db_connection() as connection:
        client_rows = connection.execute("SELECT * FROM clients ORDER BY last_seen_at DESC").fetchall()
        latest_screenshot_map = get_latest_screenshot_map(connection)

    clients = [serialize_client(row, latest_screenshot_map.get(row["client_id"])) for row in client_rows]
    return jsonify({"clients": clients, "generated_at": isoformat(utcnow())})


@app.route("/api/v1/dashboard/activity", methods=["GET"])
def dashboard_activity() -> Response:
    client_id = request.args.get("client_id")
    limit = min(int(request.args.get("limit", "50")), 200)

    query = """
        SELECT * FROM activity_history
        {where_clause}
        ORDER BY received_at DESC
        LIMIT ?
    """
    params: list[Any] = [limit]
    where_clause = ""
    if client_id:
        where_clause = "WHERE client_id = ?"
        params.insert(0, client_id)

    with db_lock, db_connection() as connection:
        rows = connection.execute(query.format(where_clause=where_clause), params).fetchall()

    return jsonify(
        {
            "items": [
                {
                    "id": row["id"],
                    "client_id": row["client_id"],
                    "activity_state": row["activity_state"],
                    "idle_seconds": row["idle_seconds"],
                    "last_active_at": row["last_active_at"],
                    "received_at": row["received_at"],
                    "source_ip": row["source_ip"],
                }
                for row in rows
            ]
        }
    )


@app.route("/api/v1/dashboard/commands", methods=["GET"])
def dashboard_commands() -> Response:
    client_id = request.args.get("client_id")
    limit = min(int(request.args.get("limit", "50")), 200)

    query = """
        SELECT * FROM commands
        {where_clause}
        ORDER BY created_at DESC
        LIMIT ?
    """
    params: list[Any] = [limit]
    where_clause = ""
    if client_id:
        where_clause = "WHERE client_id = ?"
        params.insert(0, client_id)

    with db_lock, db_connection() as connection:
        rows = connection.execute(query.format(where_clause=where_clause), params).fetchall()

    return jsonify({"items": [serialize_command(row) for row in rows]})


@app.route("/api/v1/dashboard/screenshots", methods=["GET"])
def dashboard_screenshots() -> Response:
    client_id = request.args.get("client_id")
    limit = min(int(request.args.get("limit", "20")), 100)

    query = """
        SELECT * FROM screenshots
        {where_clause}
        ORDER BY uploaded_at DESC
        LIMIT ?
    """
    params: list[Any] = [limit]
    where_clause = ""
    if client_id:
        where_clause = "WHERE client_id = ?"
        params.insert(0, client_id)

    with db_lock, db_connection() as connection:
        rows = connection.execute(query.format(where_clause=where_clause), params).fetchall()

    return jsonify({"items": [serialize_screenshot(row) for row in rows]})


@app.route("/api/v1/dashboard/screenshots/<int:screenshot_id>/file", methods=["GET"])
def dashboard_screenshot_file(screenshot_id: int) -> Response:
    with db_lock, db_connection() as connection:
        row = connection.execute("SELECT * FROM screenshots WHERE id = ?", (screenshot_id,)).fetchone()

    if row is None:
        abort(404, description="Screenshot not found")

    return send_from_directory(SCREENSHOTS_DIR, row["file_name"])


@app.route("/api/v1/dashboard/clients/<client_id>/commands/screenshot", methods=["POST"])
def dashboard_queue_screenshot(client_id: str) -> Response:
    fetch_client_row(client_id)
    command = enqueue_command(
        client_id=client_id,
        command_type="capture_screenshot",
        payload={"reason": "dashboard_request"},
        issued_by="dashboard",
    )
    return jsonify({"status": "queued", "command": command}), 202


@dataclass
class TlsConfig:
    cert_path: str
    key_path: str


def resolve_tls_config() -> TlsConfig:
    cert_path = Path(TLS_CERT_PATH)
    key_path = Path(TLS_KEY_PATH)
    if not cert_path.exists() or not key_path.exists():
        raise FileNotFoundError(
            "TLS certificate or key is missing. Generate them first or set MONITOR_TLS_CERT and MONITOR_TLS_KEY."
        )
    return TlsConfig(cert_path=str(cert_path), key_path=str(key_path))


if __name__ == "__main__":
    initialize_database()
    tls = resolve_tls_config()
    app.run(host=API_HOST, port=API_PORT, debug=False, ssl_context=(tls.cert_path, tls.key_path))
