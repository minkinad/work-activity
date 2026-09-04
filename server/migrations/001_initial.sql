CREATE TABLE IF NOT EXISTS clients (
    client_id TEXT PRIMARY KEY,
    domain_name TEXT NOT NULL,
    machine_name TEXT NOT NULL,
    user_name TEXT NOT NULL,
    ip_address TEXT NOT NULL,
    activity_state TEXT NOT NULL CHECK (activity_state IN ('active', 'idle')),
    idle_seconds INTEGER NOT NULL CHECK (idle_seconds >= 0),
    last_active_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    app_mode TEXT NOT NULL CHECK (app_mode IN ('background', 'service')),
    service_name TEXT NOT NULL,
    protocol_version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activity_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    activity_state TEXT NOT NULL CHECK (activity_state IN ('active', 'idle')),
    idle_seconds INTEGER NOT NULL CHECK (idle_seconds >= 0),
    last_active_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    source_ip TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_uuid TEXT NOT NULL UNIQUE,
    client_id TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    command_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'dispatched', 'completed', 'failed')),
    issued_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    dispatched_at TEXT,
    completed_at TEXT,
    result_json TEXT,
    error_text TEXT
);

CREATE TABLE IF NOT EXISTS screenshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    command_id INTEGER NOT NULL UNIQUE REFERENCES commands(id) ON DELETE CASCADE,
    client_id TEXT NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    file_name TEXT NOT NULL UNIQUE,
    file_path TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    byte_size INTEGER NOT NULL CHECK (byte_size > 0),
    sha256_hex TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS request_nonces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id TEXT NOT NULL,
    nonce TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(client_id, nonce)
);

CREATE INDEX IF NOT EXISTS idx_activity_client_received
    ON activity_history(client_id, received_at DESC);
CREATE INDEX IF NOT EXISTS idx_commands_client_status_created
    ON commands(client_id, status, created_at);
CREATE INDEX IF NOT EXISTS idx_screenshots_client_uploaded
    ON screenshots(client_id, uploaded_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_screenshots_command
    ON screenshots(command_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_screenshots_file_name
    ON screenshots(file_name);
CREATE INDEX IF NOT EXISTS idx_nonces_created
    ON request_nonces(created_at);
