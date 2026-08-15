"use client";

/**
 * What a visitor sees when the backend cannot be reached.
 *
 * A deployed frontend outlives its backend: Cloud Run scales to zero, a deploy
 * restarts, an environment variable is wrong. Failing to a stack trace makes
 * that look like a broken product rather than a service that is briefly down,
 * so this says which of the two it is and what to do about it.
 *
 * It deliberately does not fall back to sample data. A page of invented figures
 * that looks live is worse than an honest empty one.
 */
export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const unreachable = /snapshot|fetch|ECONNREFUSED|aborted|timeout/i.test(error.message);

  return (
    <main className="shell">
      <section className="section">
        <p className="hero__eyebrow">Nothing to show</p>

        <h1 className="hero__claim" style={{ marginTop: "1rem", maxWidth: "22ch" }}>
          {unreachable
            ? "The analysis service is not answering."
            : "Something went wrong rendering this page."}
        </h1>

        <p className="hero__sub" style={{ marginTop: "1rem", maxWidth: "58ch" }}>
          {unreachable ? (
            <>
              Every figure in CardSense comes from agents running against your
              own transactions, so there is nothing to show until they are
              reachable. If this is a fresh deployment, check that{" "}
              <code>CARDSENSE_API_URL</code> points at a running backend.
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
  );
}
