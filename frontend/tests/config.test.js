import test from "node:test";
import assert from "node:assert/strict";

import { normalizeApiBaseUrl, validateDashboardToken } from "../src/config.js";

test("normalizes API URL and removes a trailing slash", () => {
    assert.equal(normalizeApiBaseUrl("https://monitor.example/api/"), "https://monitor.example/api");
});

test("allows plain HTTP only for loopback development", () => {
    assert.equal(normalizeApiBaseUrl("http://127.0.0.1:5000/"), "http://127.0.0.1:5000");
    assert.throws(() => normalizeApiBaseUrl("http://monitor.example"), /HTTPS/);
});

test("rejects credentials, query parameters, and short dashboard tokens", () => {
    assert.throws(() => normalizeApiBaseUrl("https://user:pass@monitor.example"), /credentials/);
    assert.throws(() => normalizeApiBaseUrl("https://monitor.example?token=secret"), /query/);
    assert.throws(() => validateDashboardToken("too-short"), /32/);
    assert.equal(validateDashboardToken("x".repeat(32)), "x".repeat(32));
});
