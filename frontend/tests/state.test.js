import test from "node:test";
import assert from "node:assert/strict";

import { filterClients, scopedPath, summarizeClients } from "../src/state.js";

const clients = [
    { client_id: "one", user: "Alice", machine: "PC-01", status: "online", activity_state: "active" },
    { client_id: "two", user: "Bob", machine: "PC-02", status: "offline", activity_state: "idle" },
];

test("filters clients by status and searchable fields", () => {
    assert.deepEqual(filterClients(clients, "alice", "all"), [clients[0]]);
    assert.deepEqual(filterClients(clients, "pc-02", "offline"), [clients[1]]);
    assert.deepEqual(filterClients(clients, "", "online"), [clients[0]]);
});

test("summarizes operational state", () => {
    assert.deepEqual(
        summarizeClients(clients, [{ status: "queued" }, { status: "completed" }]),
        { total: 2, online: 1, active: 1, pending: 1 },
    );
});

test("builds encoded scoped dashboard paths", () => {
    assert.equal(
        scopedPath("activity", "office pc/1", 20),
        "/api/v1/dashboard/activity?limit=20&client_id=office+pc%2F1",
    );
});
