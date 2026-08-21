"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { AgentId, Recommendation, Snapshot } from "@/lib/types";
import { dayMonth, daysUntil, money, moneyWhole } from "@/lib/format";
import { api } from "@/lib/client-api";

const AGENT_LABEL: Record<AgentId, string> = {
  ingestion: "Ingestion agent",
  forecast: "Forecast agent",
  "card-intelligence": "Card intelligence agent",
  strategy: "Strategy agent",
  advisory: "Advisory agent",
};

const URGENCY_LABEL = {
  "act-now": "Act now",
  "this-week": "This week",
  informational: "For information",
} as const;

type Resolution = "done" | "dismissed";

/** How many recommendations show before the list needs a click to see more.
 *  A card edit can easily produce fifteen or twenty of these — mostly
 *  eligibility checks — and scrolling past all of them to reach the
 *  dashboard's other sections is the wrong default for a first look. */
const COLLAPSED_COUNT = 3;

export function Recommendations({
  items,
  now,
}: {
  items: Recommendation[];
  /** Reference date for deadline maths. Passed in so server and client agree. */
  now: string;
}) {
  const [resolved, setResolved] = useState<Record<string, Resolution>>({});
  const [pending, setPending] = useState<Record<string, boolean>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [expanded, setExpanded] = useState(false);
  const router = useRouter();

  const hidden = items.length - COLLAPSED_COUNT;
  const visible = expanded ? items : items.slice(0, COLLAPSED_COUNT);

  async function resolve(id: string, outcome: "open" | "acted" | "dismissed") {
    const previous = resolved[id];
    setResolved((current) => {
      const next = { ...current };
      if (outcome === "open") delete next[id];
      else next[id] = outcome === "acted" ? "done" : "dismissed";
      return next;
    });
    setPending((current) => ({ ...current, [id]: true }));
    setErrors((current) => ({ ...current, [id]: "" }));
    try {
      await api<Snapshot>(`/api/v1/advice/${encodeURIComponent(id)}/resolve`, {
        method: "POST", body: JSON.stringify({ outcome }),
      });
      router.refresh();
    } catch (error) {
      setResolved((current) => {
        const next = { ...current };
        if (previous) next[id] = previous;
        else delete next[id];
        return next;
      });
      setErrors((current) => ({
        ...current,
        [id]: error instanceof Error ? error.message : "Unable to update recommendation.",
      }));
    } finally {
      setPending((current) => ({ ...current, [id]: false }));
    }
  }

  return (
    <div>
      {visible.map((rec) => {
        const state = resolved[rec.id];

        // A resolved recommendation collapses rather than disappearing — the
        // advisory agent's response to being dismissed is part of the story.
        if (state) {
          return (
            <article key={rec.id} className="rec rec--resolved">
              <p className="rec__resolved-line">
                <span className="rec__resolved-mark" aria-hidden>
                  {state === "done" ? "✓" : "○"}
                </span>
                <span>
                  <strong>{rec.headline}</strong>
                  <br />
                  {state === "done"
                    ? `Marked done. The advisory agent will check it against your transactions and report back on your track record.`
                    : `Dismissed. Advice like this won't be pushed again.`}
                </span>
              </p>
              <button
                type="button"
                className="rec__undo"
                disabled={pending[rec.id]}
                onClick={() => resolve(rec.id, "open")}
              >
                {pending[rec.id] ? "Saving…" : "Undo"}
              </button>
              {errors[rec.id] && <p className="dialog__fine" role="alert">{errors[rec.id]}</p>}
            </article>
          );
        }

        return (
          <article key={rec.id} className="rec" data-urgency={rec.urgency}>
            <div className="rec__top">
              <span className={rec.urgency === "act-now" ? "tag" : "tag tag--calm"}>
                {URGENCY_LABEL[rec.urgency]}
              </span>
              {rec.deadline && (
                <span className="tag tag--deadline">
                  {daysUntil(rec.deadline, now)} days left · {dayMonth(rec.deadline)}
                </span>
              )}
            </div>

            <h3 className="rec__headline">{rec.headline}</h3>

            {rec.card && (
              <p className="rec__cards">
                <span>
                  {rec.card.name} ••{rec.card.last4}
                </span>
                {rec.tiedWith && (
                  <>
                    <span className="rec__tie">or, equally</span>
                    <span>
                      {rec.tiedWith.name} ••{rec.tiedWith.last4}
                    </span>
                  </>
                )}
              </p>
            )}

            <p className="rec__body">{rec.body}</p>

            <p className="rec__impact">
              <span className="rec__impact-value">
                {rec.impact >= 100 ? moneyWhole(rec.impact) : money(rec.impact)}
              </span>
              <span className="rec__impact-label">{rec.impactWindow}</span>
            </p>

            <div className="rec__actions">
              <button
                type="button"
                className="btn btn--small btn--quiet"
                disabled={pending[rec.id]}
                onClick={() => resolve(rec.id, "acted")}
              >
                {pending[rec.id] ? "Saving…" : "Mark as done"}
              </button>
              <button
                type="button"
                className="rec__dismiss"
                disabled={pending[rec.id]}
                onClick={() => resolve(rec.id, "dismissed")}
              >
                Not for me
              </button>
            </div>

            {errors[rec.id] && <p className="dialog__fine" role="alert">{errors[rec.id]}</p>}

            <details className="trace">
              <summary className="trace__toggle">
                <span className="trace__chevron" aria-hidden>
                  ›
                </span>
                How this was decided
              </summary>
              <ol className="trace__steps">
                {rec.trace.map((step, i) => (
                  <li key={i} className="trace__step">
                    <span className="trace__agent">{AGENT_LABEL[step.agent]}</span>
                    <span className="trace__detail">{step.detail}</span>
                  </li>
                ))}
              </ol>
            </details>
          </article>
        );
      })}

      {hidden > 0 && (
        <button
          type="button"
          className="rec__more"
          onClick={() => setExpanded((current) => !current)}
        >
          {expanded
            ? "Show fewer"
            : `Show ${hidden} more recommendation${hidden === 1 ? "" : "s"}`}
        </button>
      )}
    </div>
  );
}
