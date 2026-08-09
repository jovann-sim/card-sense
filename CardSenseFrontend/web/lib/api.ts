import "server-only";
import { cache } from "react";

import { snapshot as mockSnapshot } from "@/lib/mock";
import type { Snapshot } from "@/lib/types";

const requiredSnapshotKeys = [
  "generatedAt", "period", "totals", "agents", "recommendations", "categories",
  "cards", "tracks", "trackPreference", "recommendedTrack", "trackRationale",
  "forecast", "goal", "planned", "trackRecord", "wallet", "catalog", "activity",
  "collections",
] as const satisfies readonly (keyof Snapshot)[];

function isSnapshot(value: unknown): value is Snapshot {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const candidate = value as Record<string, unknown>;
  return requiredSnapshotKeys.every((key) => key in candidate) &&
    typeof candidate.generatedAt === "string" &&
    typeof candidate.recommendedTrack === "string" &&
    Array.isArray(candidate.agents) &&
    Array.isArray(candidate.recommendations) &&
    Array.isArray(candidate.categories) &&
    Array.isArray(candidate.planned);
}

/** Fetch the single backend read model. This is server-only by design. */
const SNAPSHOT_TIMEOUT_MS = 8_000;

export const getSnapshot = cache(async (): Promise<Snapshot> => {
  const baseUrl = process.env.CARDSENSE_API_URL ?? "http://localhost:8080";
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), SNAPSHOT_TIMEOUT_MS);
  try {
    const response = await fetch(`${baseUrl}/api/v1/snapshot`, {
      cache: "no-store",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(`CardSense API returned ${response.status}`);
    const payload: unknown = await response.json();
    if (!isSnapshot(payload)) throw new Error("CardSense API returned an invalid Snapshot");
    return payload;
  } catch (error) {
    if (process.env.NODE_ENV !== "production" && process.env.CARDSENSE_REAL_DATA !== "true") return mockSnapshot;
    const message = error instanceof Error ? error.message : "Unknown error";
    throw new Error(`Unable to load CardSense backend snapshot: ${message}`);
  } finally {
    clearTimeout(timeout);
  }
});
