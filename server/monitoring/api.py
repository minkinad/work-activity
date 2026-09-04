from __future__ import annotations

from flask import Flask, jsonify

from .config import Settings
from .database import Database
from .domain import PROTOCOL_VERSION, isoformat, utcnow
from .http import configure_http
from .repositories import MonitorRepository
from .routes.client import create_client_blueprint
from .routes.dashboard import create_dashboard_blueprint
from .security import ClientAuthenticator
from .services import ActivityService, CommandService


def create_app(settings: Settings) -> Flask:
    settings.validate()
    settings.ensure_runtime_directories()

    database = Database(settings.database_path)
    database.migrate()
    repository = MonitorRepository(database)
    activity_service = ActivityService(repository, settings.client_timeout_seconds)
    command_service = CommandService(repository, settings)
    client_authenticator = ClientAuthenticator(
        settings.client_shared_secret,
        settings.signature_tolerance_seconds,
        repository,
    )

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = int(settings.max_screenshot_bytes * 1.4) + 64 * 1024
    app.extensions["monitoring"] = {
        "database": database,
        "repository": repository,
        "activity_service": activity_service,
        "command_service": command_service,
    }
    configure_http(app, settings)
    app.register_blueprint(
        create_client_blueprint(client_authenticator, activity_service, command_service)
    )
    app.register_blueprint(
        create_dashboard_blueprint(
            settings.dashboard_token,
            activity_service,
            command_service,
        )
    )

    @app.get("/")
    def root():
        return jsonify(
            {
                "service": "work-activity-monitor-api",
                "protocol_version": PROTOCOL_VERSION,
            }
        )

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "time": isoformat(utcnow())})

    return app
