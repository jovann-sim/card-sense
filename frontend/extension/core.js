(function expose(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.CardSenseExtension = api;
})(typeof globalThis === "undefined" ? this : globalThis, function buildCore() {
  const DEFAULT_API_ORIGIN = "http://localhost:8080";

  function normalizeApiOrigin(value) {
    const raw = String(value || DEFAULT_API_ORIGIN).trim();
    let parsed;
    try {
      parsed = new URL(raw);
    } catch {
      throw new Error("Enter a complete http:// or https:// address.");
    }
    if (!/^https?:$/.test(parsed.protocol)) {
      throw new Error("The backend must use http:// or https://.");
    }
    if (parsed.username || parsed.password || parsed.search || parsed.hash) {
      throw new Error("Use only the backend origin, without credentials, query text, or a fragment.");
    }
    return parsed.origin;
  }

  function permissionPattern(origin) {
    return `${normalizeApiOrigin(origin)}/*`;
  }

  function confidenceLabel(value) {
    return value === "high" ? "High confidence" : value === "medium" ? "Medium confidence" : "Low confidence";
  }

  function capLabel(cap) {
    if (!cap || cap.status === "uncapped") return "No reward cap";
    if (cap.status === "unverified") return "Cap remaining unknown";
    const remaining = new Intl.NumberFormat("en-US", {
      style: "currency", currency: "USD", maximumFractionDigits: 0,
    }).format(cap.remaining || 0);
    return cap.status === "reached" ? "Reward cap reached" : `${remaining} cap remaining`;
  }

  function popupState(verdict) {
    if (!verdict) {
      return { kind: "empty", headline: "No page to read", message: "Open a shop and try again." };
    }
    if (!verdict.card) {
      return {
        kind: "empty",
        headline: verdict.merchant || "Unknown merchant",
        message: verdict.reason || "No verified card recommendation is available.",
      };
    }
    return {
      kind: "verdict",
      confidence: confidenceLabel(verdict.recommendationConfidence || verdict.confidence),
      cap: capLabel(verdict.cap),
    };
  }

  function backendFailure(origin) {
    return {
      kind: "empty",
      headline: "Could not reach CardSense",
      message: `No recommendation could be loaded from ${normalizeApiOrigin(origin)}. Check the backend address in Settings.`,
    };
  }

  return {
    DEFAULT_API_ORIGIN,
    normalizeApiOrigin,
    permissionPattern,
    confidenceLabel,
    capLabel,
    popupState,
    backendFailure,
  };
});
