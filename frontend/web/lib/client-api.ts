"use client";

const userId = "demo-user";

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/backend${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `CardSense API returned ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export { userId };
