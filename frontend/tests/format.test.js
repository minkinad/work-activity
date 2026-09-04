import test from "node:test";
import assert from "node:assert/strict";

import { formatBytes, formatDuration } from "../src/format.js";

test("formats durations without fractional units", () => {
    assert.equal(formatDuration(42), "42 сек");
    assert.equal(formatDuration(125), "2 мин");
    assert.equal(formatDuration(3720), "1 ч 2 мин");
});

test("formats byte sizes", () => {
    assert.equal(formatBytes(512), "512 Б");
    assert.equal(formatBytes(2048), "2.0 КБ");
});
