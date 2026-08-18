"use client";

import { Archivo, Public_Sans, IBM_Plex_Mono } from "next/font/google";
import "./globals.css";

/**
 * The one boundary Next.js requires for a crash in the root layout itself.
 *
 * `AgentRail` and `SiteFooter` need the snapshot on every page, so the fetch
 * lives in `layout.tsx` rather than a page — which means a failed fetch throws
 * above every page-level `error.tsx`, and none of them can catch it. Next.js's
 * rule for that specific case is this file: it must render its own `<html>`
 * and `<body>`, because it replaces the root layout entirely rather than
 * nesting inside it. Skipping it is what left the whole site behind Next's
 * bare "This page couldn't load" — no branding, no explanation, nothing
 * distinguishing a downed backend from a real bug.
 */

const archivo = Archivo({ subsets: ["latin"], axes: ["wdth"], variable: "--font-archivo", display: "swap" });
const publicSans = Public_Sans({ subsets: ["latin"], variable: "--font-public-sans", display: "swap" });
const plexMono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500"], variable: "--font-plex-mono", display: "swap" });

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  // Next.js redacts error messages in production and only exposes a digest,
  // which means sniffing the message never matches — the "generic error"
  // branch always won even for the failure this file exists to explain. So the
  // default is now the backend one, since a fresh deploy that lands here
  // almost always got here for exactly that reason. The generic branch
  // remains for local development, where the real message is available.
  const unreachable =
    process.env.NODE_ENV === "production" ||
    /snapshot|fetch|ECONNREFUSED|aborted|timeout/i.test(error.message);

  return (
    <html lang="en" className={`${archivo.variable} ${publicSans.variable} ${plexMono.variable}`}>
      <body>
        <main className="shell">
          <section className="section">
            <p className="hero__eyebrow">Nothing to show</p>

            <h1 className="hero__claim" style={{ marginTop: "1rem", maxWidth: "22ch" }}>
              {unreachable
                ? "The analysis service is not answering."
                : "Something went wrong loading CardSense."}
            </h1>

            <p className="hero__sub" style={{ marginTop: "1rem", maxWidth: "58ch" }}>
              {unreachable ? (
                <>
                  Every figure here comes from agents running against your own
                  transactions, so there is nothing to show until they are
                  reachable. If this is a fresh deployment, check that{" "}
                  <code>CARDSENSE_API_URL</code> is set and points at a running
                  backend, then redeploy — environment variable changes only
                  take effect on the next build.
                </>
              ) : (
                "This is a fault in the page rather than in your data. Nothing has been changed."
              )}
            </p>

            <button
              type="button"
              className="section__action"
              style={{ marginTop: "1.5rem" }}
              onClick={reset}
            >
              Try again
            </button>

            {error.digest && (
              <p className="addcard__fine" style={{ marginTop: "1rem" }}>
                Reference {error.digest}
              </p>
            )}
          </section>
        </main>
      </body>
    </html>
  );
}
