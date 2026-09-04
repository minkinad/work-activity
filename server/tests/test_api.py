import base64
import json
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from monitoring import Settings, create_app
from monitoring.security import compute_client_signature

CLIENT_SECRET = "client-secret-" + "c" * 32
DASHBOARD_TOKEN = "dashboard-token-" + "d" * 32
CLIENT_ID = "office-pc-01"


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.settings = Settings(
            database_path=root / "monitor.db",
            screenshots_dir=root / "screenshots",
            api_host="127.0.0.1",
            api_port=5000,
            client_timeout_seconds=180,
            command_retry_seconds=20,
            signature_tolerance_seconds=300,
            client_shared_secret=CLIENT_SECRET,
            dashboard_token=DASHBOARD_TOKEN,
            allowed_origins=("http://127.0.0.1:8081",),
            tls_cert_path=root / "server.crt",
            tls_key_path=root / "server.key",
            max_screenshot_bytes=1024,
        )
        self.app = create_app(self.settings)
        self.app.testing = True
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    @property
    def dashboard_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {DASHBOARD_TOKEN}"}

    def signed_post(
        self,
        path: str,
        payload: dict,
        nonce: str | None = None,
        timestamp: str | None = None,
    ):
        body = json.dumps(payload, separators=(",", ":")).encode()
        timestamp = timestamp or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        nonce = nonce or uuid.uuid4().hex
        signature = compute_client_signature(
            CLIENT_SECRET, payload["client_id"], timestamp, nonce, body
        )
        return self.client.post(
            path,
            data=body,
            content_type="application/json",
            headers={
                "X-Monitor-Client-Id": payload["client_id"],
                "X-Monitor-Timestamp": timestamp,
                "X-Monitor-Nonce": nonce,
                "X-Monitor-Signature": signature,
            },
        )

    def heartbeat_payload(self) -> dict:
        return {
            "client_id": CLIENT_ID,
            "domain": "EXAMPLE",
            "machine": "OFFICE-PC-01",
            "user": "alice",
            "ip_address": "10.0.0.10",
            "activity_state": "active",
            "idle_seconds": 2,
            "last_active_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "app_mode": "background",
            "service_name": "WorkActivityMonitorSvc",
            "protocol_version": 2,
        }

    def register_client(self) -> None:
        response = self.signed_post("/api/v1/client/heartbeat", self.heartbeat_payload())
        self.assertEqual(response.status_code, 200, response.get_json())

    def test_dashboard_requires_bearer_token(self) -> None:
        routes = (
            "/api/v1/dashboard/clients",
            "/api/v1/dashboard/activity",
            "/api/v1/dashboard/commands",
            "/api/v1/dashboard/screenshots",
            f"/api/v1/dashboard/clients/{CLIENT_ID}/commands/screenshot",
        )
        for route in routes:
            with self.subTest(route=route):
                response = self.client.open(route, method="POST" if "commands/screenshot" in route else "GET")
                self.assertEqual(response.status_code, 401)
                self.assertEqual(
                    response.get_json()["error"]["code"], "authentication_required"
                )

        invalid = self.client.get(
            "/api/v1/dashboard/clients",
            headers={"Authorization": "Bearer " + "x" * 32},
        )
        self.assertEqual(invalid.status_code, 401)

        response = self.client.get(
            "/api/v1/dashboard/clients", headers=self.dashboard_headers
        )
        self.assertEqual(response.status_code, 200)

    def test_signed_heartbeat_is_validated_and_replay_is_rejected(self) -> None:
        payload = self.heartbeat_payload()
        nonce = uuid.uuid4().hex
        first = self.signed_post("/api/v1/client/heartbeat", payload, nonce)
        second = self.signed_post("/api/v1/client/heartbeat", payload, nonce)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 409)

        invalid_payload = self.heartbeat_payload()
        invalid_payload["idle_seconds"] = -1
        invalid = self.signed_post("/api/v1/client/heartbeat", invalid_payload)
        self.assertEqual(invalid.status_code, 400)

    def test_stale_client_signature_is_rejected(self) -> None:
        stale = "2020-01-01T00:00:00Z"
        response = self.signed_post(
            "/api/v1/client/heartbeat",
            self.heartbeat_payload(),
            timestamp=stale,
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["error"]["code"], "authentication_required")

    def test_unsupported_protocol_version_is_rejected(self) -> None:
        payload = self.heartbeat_payload()
        payload["protocol_version"] = 1
        response = self.signed_post("/api/v1/client/heartbeat", payload)
        self.assertEqual(response.status_code, 409)

    def test_screenshot_command_lifecycle(self) -> None:
        self.register_client()
        command_response = self.client.post(
            f"/api/v1/dashboard/clients/{CLIENT_ID}/commands/screenshot",
            headers=self.dashboard_headers,
        )
        self.assertEqual(command_response.status_code, 202)
        command_id = command_response.get_json()["command"]["id"]

        duplicate = self.client.post(
            f"/api/v1/dashboard/clients/{CLIENT_ID}/commands/screenshot",
            headers=self.dashboard_headers,
        )
        self.assertEqual(duplicate.status_code, 409)

        poll = self.signed_post(
            "/api/v1/client/commands/poll", {"client_id": CLIENT_ID}
        )
        self.assertEqual(poll.status_code, 200)
        self.assertEqual(poll.get_json()["command"]["id"], command_id)
        self.assertEqual(poll.get_json()["command"]["status"], "dispatched")

        invalid_upload = self.signed_post(
            f"/api/v1/client/commands/{command_id}/screenshot",
            {
                "client_id": CLIENT_ID,
                "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "image_base64": base64.b64encode(b"not a png").decode(),
            },
        )
        self.assertEqual(invalid_upload.status_code, 400)

        png = b"\x89PNG\r\n\x1a\n" + b"test-image-data"
        upload = self.signed_post(
            f"/api/v1/client/commands/{command_id}/screenshot",
            {
                "client_id": CLIENT_ID,
                "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "image_base64": base64.b64encode(png).decode(),
            },
        )
        self.assertEqual(upload.status_code, 200, upload.get_json())
        screenshot_id = upload.get_json()["screenshot"]["id"]

        repeated_upload = self.signed_post(
            f"/api/v1/client/commands/{command_id}/screenshot",
            {
                "client_id": CLIENT_ID,
                "captured_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "image_base64": base64.b64encode(png).decode(),
            },
        )
        self.assertEqual(repeated_upload.status_code, 409)

        denied = self.client.get(
            f"/api/v1/dashboard/screenshots/{screenshot_id}/file"
        )
        allowed = self.client.get(
            f"/api/v1/dashboard/screenshots/{screenshot_id}/file",
            headers=self.dashboard_headers,
        )
        self.assertEqual(denied.status_code, 401)
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.data, png)
        allowed.close()

    def test_cors_is_limited_to_configured_origins(self) -> None:
        allowed = self.client.get(
            "/health", headers={"Origin": "http://127.0.0.1:8081"}
        )
        denied = self.client.get(
            "/health", headers={"Origin": "https://attacker.example"}
        )
        self.assertEqual(
            allowed.headers.get("Access-Control-Allow-Origin"),
            "http://127.0.0.1:8081",
        )
        self.assertIsNone(denied.headers.get("Access-Control-Allow-Origin"))

        denied_preflight = self.client.options(
            "/api/v1/dashboard/clients",
            headers={
                "Origin": "https://attacker.example",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
        self.assertEqual(denied_preflight.status_code, 403)

    def test_security_headers_are_present(self) -> None:
        response = self.client.get(
            "/api/v1/dashboard/clients",
            headers=self.dashboard_headers,
            base_url="https://monitor.example",
        )
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["Cache-Control"], "no-store, private")
        self.assertIn("max-age=31536000", response.headers["Strict-Transport-Security"])
        self.assertIn("camera=()", response.headers["Permissions-Policy"])


if __name__ == "__main__":
    unittest.main()
