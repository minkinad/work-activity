from __future__ import annotations

from flask import Blueprint, jsonify, request, send_file

from ..domain import isoformat, parse_limit, utcnow
from ..security import dashboard_auth_required
from ..services import ActivityService, CommandService


def create_dashboard_blueprint(
    dashboard_token: str,
    activity_service: ActivityService,
    command_service: CommandService,
) -> Blueprint:
    blueprint = Blueprint("dashboard_api", __name__, url_prefix="/api/v1/dashboard")
    require_auth = dashboard_auth_required(dashboard_token)

    @blueprint.get("/clients")
    @require_auth
    def clients():
        return jsonify(
            {
                "clients": activity_service.list_clients(),
                "generated_at": isoformat(utcnow()),
            }
        )

    @blueprint.get("/activity")
    @require_auth
    def activity():
        items = activity_service.list_activity(
            request.args.get("client_id"),
            parse_limit(request.args.get("limit"), 50, 200),
        )
        return jsonify({"items": items})

    @blueprint.get("/commands")
    @require_auth
    def commands():
        items = command_service.list_commands(
            request.args.get("client_id"),
            parse_limit(request.args.get("limit"), 50, 200),
        )
        return jsonify({"items": items})

    @blueprint.get("/screenshots")
    @require_auth
    def screenshots():
        items = command_service.list_screenshots(
            request.args.get("client_id"),
            parse_limit(request.args.get("limit"), 20, 100),
        )
        return jsonify({"items": items})

    @blueprint.get("/screenshots/<int:screenshot_id>/file")
    @require_auth
    def screenshot_file(screenshot_id: int):
        return send_file(
            command_service.screenshot_path(screenshot_id),
            mimetype="image/png",
            as_attachment=False,
            conditional=True,
        )

    @blueprint.post("/clients/<client_id>/commands/screenshot")
    @require_auth
    def queue_screenshot(client_id: str):
        command = command_service.enqueue_screenshot(client_id)
        return jsonify({"status": "queued", "command": command}), 202

    return blueprint
