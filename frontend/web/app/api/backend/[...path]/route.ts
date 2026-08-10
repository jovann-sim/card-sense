import { NextRequest } from "next/server";
import { revalidateTag } from "next/cache";
import { SNAPSHOT_CACHE_TAG } from "@/lib/cache-tags";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type Context = { params: Promise<{ path: string[] }> };

async function forward(request: NextRequest, { params }: Context) {
  const { path } = await params;
  const baseUrl = process.env.CARDSENSE_API_URL ?? "http://localhost:8080";
  const url = new URL(`${baseUrl.replace(/\/$/, "")}/${path.join("/")}`);
  url.search = request.nextUrl.search;

  try {
    const upstream = await fetch(url, {
      method: request.method,
      headers: {
        Accept: request.headers.get("accept") ?? "application/json",
        ...(request.headers.get("content-type")
          ? { "Content-Type": request.headers.get("content-type")! }
          : {}),
      },
      body: ["GET", "HEAD"].includes(request.method)
        ? undefined
        : await request.arrayBuffer(),
      cache: "no-store",
    });
    const responseBody = await upstream.arrayBuffer();
    if (upstream.ok && !["GET", "HEAD", "OPTIONS"].includes(request.method)) {
      // Route handlers cannot use updateTag, so expire immediately to preserve
      // read-after-write behavior for the router.refresh() that follows.
      revalidateTag(SNAPSHOT_CACHE_TAG, { expire: 0 });
    }
    return new Response(responseBody, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return Response.json(
      { detail: "CardSense backend is unavailable. Start the backend and try again." },
      { status: 502 },
    );
  }
}

export const GET = forward;
export const POST = forward;
export const DELETE = forward;
