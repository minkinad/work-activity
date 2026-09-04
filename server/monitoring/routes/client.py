from __future__ import annotations

from flask import Blueprint, jsonify, request

from ..domain import isoformat, utcnow
from ..http import request_object
from ..security import ClientAuthenticator
from ..services import ActivityService, CommandService


def create_client_blueprint(
    authenticator: ClientAuthenticator,
    activity_service: ActivityService,
    command_service: CommandService,
) -> Blueprint:
    blueprint = Blueprint("client_api", __name__, url_prefix="/api/v1/client")

    @blueprint.post("/heartbeat")
    def heartbeat():
        payload, body = request_object()
        client_id = payload.get("client_id", "")
        authenticator.verify(request, client_id, body)
        activity_service.record_heartbeat(payload, request.remote_addr or "")
        return jsonify({"status": "ok", "received_at": isoformat(utcnow())})

    @blueprint.post("/commands/poll")
    def poll_commands():
        payload, body = request_object()
        client_id = payload.get("client_id", "")
        authenticator.verify(request, client_id, body)
        command = command_service.poll(client_id)
        return jsonify({"command": command, "server_time": isoformat(utcnow())})

    def record_failure(command_id: int):
        payload, body = request_object()
        client_id = payload.get("client_id", "")
        authenticator.verify(request, client_id, body)
        command = command_service.report_failure(command_id, client_id, payload.get("error"))
        return jsonify({"status": "recorded", "command": command})

    blueprint.add_url_rule(
        "/commands/<int:command_id>/fail",
        "fail_command",
        record_failure,
        methods=["POST"],
    )
    blueprint.add_url_rule(
        "/commands/<int:command_id>/complete",
        "complete_command_legacy",
        record_failure,
        methods=["POST"],
    )

    @blueprint.post("/commands/<int:command_id>/screenshot")
    def upload_screenshot(command_id: int):
        payload, body = request_object()
        client_id = payload.get("client_id", "")
        authenticator.verify(request, client_id, body)
        screenshot = command_service.upload_screenshot(
            command_id,
            client_id,
            payload.get("image_base64"),
            payload.get("captured_at"),
        )
        return jsonify({"status": "completed", "screenshot": screenshot})

    return blueprint
