"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type {
  Forecast,
  PlannedItemDraft,
  Snapshot,
  TimelineKind,
} from "@/lib/types";
import { dayMonth, daysUntil, money, moneyWhole } from "@/lib/format";
import { PlannedForm } from "./PlannedForm";
import { api } from "@/lib/client-api";

const KIND_LABEL: Record<TimelineKind, string> = {
  event: "Your calendar",
  purchase: "Planned purchase",
  cap: "Cap crossing",
  deadline: "Deadline",
  agent: "Agent run",
  reset: "Cycle reset",
};

/** What declaring one item changed, held so it can be shown back to the user. */
type Change = {
  label: string;
  spendDelta: number;
  collision: string | null;
};

export function ForecastView({
  forecast,
  today,
}: {
  forecast: Forecast;
  today: string;
}) {
  const [currentForecast, setCurrentForecast] = useState(forecast);
  const [adding, setAdding] = useState(false);
  const [change, setChange] = useState<Change | null>(null);
  const [saving, setSaving] = useState(false);
  const [requestError, setRequestError] = useState<string | null>(null);
  const router = useRouter();

  const projected = currentForecast.projectedSpend;
  const low = Math.max(0, projected - currentForecast.confidence);
  const high = projected + currentForecast.confidence;
  const actionable = currentForecast.timeline.filter((e) => e.action).length;

  async function addItem(item: PlannedItemDraft) {
    setSaving(true);
    setRequestError(null);
    try {
      const snapshot = await api<Snapshot>("/api/v1/planned", {
        method: "POST",
        body: JSON.stringify(item),
      });
      const previousProjection = currentForecast.projectedSpend;
      const cap = snapshot.forecast.timeline.find(
        (entry) => entry.kind === "cap" && entry.date === item.startDate &&
          entry.title.startsWith(`${item.categories[0]} passes `),
      );
      setCurrentForecast(snapshot.forecast);
      setAdding(false);
      setChange({
        label: item.label,
        spendDelta: Math.max(0, snapshot.forecast.projectedSpend - previousProjection),
        collision: cap ? `${cap.title} on ${dayMonth(cap.date)}.` : null,
      });
      router.refresh();
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "Unable to save planned spending.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <section className="shell hero hero--sub">
        <p className="hero__eyebrow">
          What&rsquo;s coming · next {currentForecast.horizonDays} days
        </p>

        <p className="hero__figure hero__figure--sub num">
          {moneyWhole(projected)}
        </p>

        <h1 className="hero__claim">
          Projected spending, and the {actionable} dates where it changes which
          card you should be holding.
        </h1>

        <p className="hero__sub">
          Somewhere between {moneyWhole(low)} and {moneyWhole(high)}.{" "}
          {currentForecast.basis}
        </p>
      </section>

      <div className="shell">
        <section className="section">
          <div className="section__label">
            Timeline
            {!adding && (
              <button
                type="button"
                className="section__action"
                onClick={() => setAdding(true)}
                disabled={saving}
              >
                + Add something planned
              </button>
            )}
          </div>

          {adding && (
            <PlannedForm
              defaultDate={today.slice(0, 10)}
              onCancel={() => setAdding(false)}
              onAdd={addItem}
            />
          )}

          {change && (
            <div className="changed" role="status">
              <p className="changed__label">Forecast updated</p>
              <p className="changed__text">
                <strong>{change.label}</strong> added.
                {change.spendDelta > 0 && (
                  <> Projection rose by {money(change.spendDelta)}.</>
                )}{" "}
                {change.collision ?? "No cap collisions from this one."}
              </p>
              <button
                type="button"
                className="changed__dismiss"
                onClick={() => setChange(null)}
              >
                Dismiss
              </button>
            </div>
          )}

          {requestError && <p className="addcard__fine" role="alert">{requestError}</p>}
          {saving && <p className="addcard__fine" role="status">Saving planned spending…</p>}

          <ol className="tl">
            {currentForecast.timeline.map((entry, i) => {
              const days = daysUntil(entry.date, today);

              return (
                <li key={`${entry.date}-${entry.title}-${i}`} className="tl__row" data-kind={entry.kind}>
                  <div className="tl__when">
                    <p className="tl__date num">{dayMonth(entry.date)}</p>
                    <p className="tl__rel">
                      {days === 0 ? "today" : `in ${days} days`}
                    </p>
                  </div>

                  <div className="tl__marker" aria-hidden>
                    <span className="tl__dot" />
                  </div>

                  <div className="tl__body">
                    <p className="tl__kind">{KIND_LABEL[entry.kind]}</p>
                    <p className="tl__title">{entry.title}</p>
                    {entry.detail && <p className="tl__detail">{entry.detail}</p>}

                    {entry.amount !== undefined && (
                      <p className="tl__amount num">{money(entry.amount)}</p>
                    )}

                    {entry.action && (
                      <p className="tl__action">
                        <span className="tl__action-label">Do this</span>
                        {entry.action}
                      </p>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        </section>
      </div>
    </>
  );
}
