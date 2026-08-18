const test = require("node:test");
const assert = require("node:assert/strict");

const Core = require("../core.js");

test("a known merchant renders confidence and remaining cap", () => {
  const state = Core.popupState({
    merchant: "instacart.com",
    card: { name: "Blue Cash", last4: "1111" },
    recommendationConfidence: "high",
    cap: { status: "verified", remaining: 4750 },
  });
  assert.deepEqual(state, {
    kind: "verdict",
    confidence: "High confidence",
    cap: "$4,750 cap remaining",
  });
});

test("an unknown merchant declines without inventing a card", () => {
  const state = Core.popupState({
    merchant: "unknown.example",
    card: null,
    reason: "No known merchant category could be resolved.",
  });
  assert.equal(state.kind, "empty");
  assert.equal(state.headline, "unknown.example");
  assert.match(state.message, /No known merchant/);
});

test("unreadable wallet rules preserve the backend explanation", () => {
  const state = Core.popupState({
    merchant: "doordash.com",
    card: null,
    reason: "None of your cards has a readable rule covering this category.",
  });
  assert.equal(state.kind, "empty");
  assert.match(state.message, /readable rule/);
});

test("backend failures name the configured origin and settings recovery", () => {
  const state = Core.backendFailure("https://cardsense-api.example/path");
  assert.equal(state.headline, "Could not reach CardSense");
  assert.match(state.message, /https:\/\/cardsense-api\.example/);
  assert.match(state.message, /Settings/);
});

test("backend origins are normalized and unsafe schemes are rejected", () => {
  assert.equal(Core.normalizeApiOrigin("https://api.example/path"), "https://api.example");
  assert.equal(Core.permissionPattern("http://localhost:8080"), "http://localhost:8080/*");
  assert.throws(() => Core.normalizeApiOrigin("file:///tmp/api"), /http/);
});
