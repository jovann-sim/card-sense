import type { Metadata } from "next";
import type { AgentId, AgentLogEntry } from "@/lib/types";
import { longDay, timeOfDay } from "@/lib/format";
import { snapshot } from "@/lib/mock";

export const metadata: Metadata = {
  title: "CardSense — Agent activity",
};

const AGENT_LABEL: Record<AgentId, string> = {
  ingestion: "Ingestion",
  forecast: "Forecast",
  "card-intelligence": "Card intelligence",
  strategy: "Simulation & strategy",
  advisory: "Advisory",
};

function groupByDay(entries: AgentLogEntry[]) {
  const days = new Map<string, AgentLogEntry[]>();
  for (const entry of entries) {
    const key = longDay(entry.startedAt);
    days.set(key, [...(days.get(key) ?? []), entry]);
  }
  return [...days.entries()];
}

export default function ActivityPage() {
  const days = groupByDay(snapshot.activity);
  const degraded = snapshot.activity.filter((e) => e.status === "degraded");

  return (
    <main>
      <section className="shell hero hero--sub">
        <p className="hero__eyebrow">Agent activity</p>

        <h1 className="hero__claim hero__claim--lead">
          Five agents, running on their own schedule, writing to a shared store.
        </h1>

        <p className="hero__sub">
          No agent calls another. Each one reads the collections it needs and
          writes its own, so a failure degrades the output instead of breaking
          the chain — as {degraded.length === 1 ? "the run" : "the runs"} below
          {degraded.length === 1 ? " shows" : " show"}.
        </p>
      </section>

      <div className="shell">
        {days.map(([day, entries]) => (
          <section key={day} className="section">
            <h2 className="section__label">{day}</h2>

            <ol className="log">
              {entries.map((entry) => (
                <li key={entry.id} className="log__row" data-status={entry.status}>
                  <div className="log__when">
                    <p className="log__time num">{timeOfDay(entry.startedAt)}</p>
                    <p className="log__dur num">
                      {(entry.durationMs / 1000).toFixed(1)}s
                    </p>
                  </div>

                  <div className="log__body">
                    <p className="log__agent">
                      {AGENT_LABEL[entry.agent]}
                      <span className="log__status">{entry.status}</span>
                    </p>
                    <p className="log__summary">{entry.summary}</p>
                    {entry.detail && <p className="log__detail">{entry.detail}</p>}

                    <p className="log__io">
                      {entry.reads && entry.reads.length > 0 && (
                        <>
                          <span className="log__io-label">reads</span>
                          {entry.reads.map((c) => (
                            <code key={c} className="coll">
                              {c}
                            </code>
                          ))}
                        </>
                      )}
                      <span className="log__io-label">writes</span>
                      <code className="coll coll--write">{entry.writes}</code>
                    </p>

                    {entry.retryable && (
                      <button type="button" className="btn btn--small">
                        Retry this run
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          </section>
        ))}

        <section className="section">
          <h2 className="section__label">How the agents share state</h2>
          <p className="section__note">
            Firestore collections, and who touches each one. This is the whole
            coordination mechanism — there are no direct calls between agents.
          </p>

          <ul className="wiring">
            {snapshot.collections.map((link) => (
              <li key={link.collection} className="wiring__row">
                <code className="coll coll--write">{link.collection}</code>
                <span className="wiring__from">{AGENT_LABEL[link.writtenBy]}</span>
                <span className="wiring__arrow" aria-hidden>
                  →
                </span>
                <span className="wiring__to">
                  {link.readBy.length > 0
                    ? link.readBy.map((a) => AGENT_LABEL[a]).join(", ")
                    : "Dashboard and extension"}
                </span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </main>
  );
}
