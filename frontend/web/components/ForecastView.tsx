"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type {
  Cadence,
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

const HORIZONS = [1, 3, 6, 12] as const;

const CADENCE_LABEL: Record<Cadence, string> = {
  weekly: "every week",
  fortnightly: "every fortnight",
  monthly: "every month",
  quarterly: "every quarter",
  yearly: "every year",
};

/** Two charges is one interval — enough to notice, not enough to be sure. */
const CONFIDENCE_LABEL: Record<string, string> = {
  high: "confirmed",
  medium: "likely",
  low: "seen twice",
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
  const months = currentForecast.horizonMonths;
  const peak = Math.max(1, ...currentForecast.months.map((m) => m.total));
  const commitment = currentForecast.recurring.reduce(
    (total, stream) => total + stream.monthlyAmount,
    0,
  );

  async function addItem(item: PlannedItemDraft) {
    setSaving(true);
    setRequestError(null);
    try {
      const snapshot = await api<Snapshot>("/api/v1/planned", {
        method: "POST",
        body: JSON.stringify(item),
      });
      const previousProjection = currentForecast.projectedSpend;
      // The snapshot always carries the one-month projection. Re-project at the
      // horizon actually on screen, or declaring an item would silently reset it.
      const updated =
        months === 1
          ? snapshot.forecast
          : (await api<Forecast>(`/api/v1/forecast?months=${months}`)) ??
            snapshot.forecast;
      const cap = updated.timeline.find(
        (entry) => entry.kind === "cap" && entry.date === item.startDate &&
          entry.title.startsWith(`${item.categories[0]} passes `),
      );
      setCurrentForecast(updated);
      setAdding(false);
      setChange({
        label: item.label,
        spendDelta: Math.max(0, updated.projectedSpend - previousProjection),
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

        <nav className="horizon" aria-label="Projection horizon">
          {HORIZONS.map((option) => (
            <Link
              key={option}
              href={option === 1 ? "/forecast" : `/forecast?months=${option}`}
              scroll={false}
              className="horizon__option"
              aria-current={option === months ? "page" : undefined}
              data-beyond={option > currentForecast.reliableMonths || undefined}
            >
              {option} {option === 1 ? "month" : "months"}
            </Link>
          ))}
        </nav>

        {currentForecast.extrapolated && (
          <p className="horizon__warn" role="note">
            <strong>This is an extrapolation.</strong>{" "}
            {currentForecast.historyDays} days of history supports about{" "}
            {currentForecast.reliableMonths}{" "}
            {currentForecast.reliableMonths === 1 ? "month" : "months"} of
            projection. Past that the range widens faster than the figure does —
            which is the honest answer, not a hedge.
          </p>
        )}
      </section>

      <div className="shell">
        {currentForecast.months.length > 1 && (
          <section className="section">
            <h2 className="section__label">Month by month</h2>
            <p className="section__note">
              Committed spending is projected by billing date. Everything else is
              a rate measured on what is left once those are removed — counting
              both would double the rent.
            </p>

            <ol className="mbar">
              {currentForecast.months.map((bucket) => (
                <li key={bucket.month} className="mbar__row">
                  <p className="mbar__label">{bucket.label}</p>

                  <div
                    className="mbar__track"
                    role="img"
                    aria-label={`${bucket.label}: ${money(bucket.total)} projected`}
                  >
                    <span
                      className="mbar__seg mbar__seg--recurring"
                      style={{ width: `${(bucket.recurring / peak) * 100}%` }}
                    />
                    <span
                      className="mbar__seg mbar__seg--variable"
                      style={{ width: `${(bucket.variable / peak) * 100}%` }}
                    />
                    <span
                      className="mbar__seg mbar__seg--planned"
                      style={{ width: `${(bucket.planned / peak) * 100}%` }}
                    />
                  </div>

                  <p className="mbar__figure num">{moneyWhole(bucket.total)}</p>
                  <p className="mbar__cum num">
                    {moneyWhole(bucket.cumulative)}
                    <span className="mbar__band">
                      {" "}
                      ± {moneyWhole(bucket.cumulativeConfidence)}
                    </span>
                  </p>
                </li>
              ))}
            </ol>

            <p className="mbar__key">
              <span className="mbar__swatch mbar__swatch--recurring" /> Committed
              <span className="mbar__swatch mbar__swatch--variable" /> Variable
              <span className="mbar__swatch mbar__swatch--planned" /> Declared
              <span className="mbar__keynote">
                Right-hand figure is the running total, with its range.
              </span>
            </p>
          </section>
        )}

        {currentForecast.recurring.length > 0 && (
          <section className="section">
            <h2 className="section__label">What repeats</h2>
            <p className="section__note">
              {money(commitment)} a month is already spoken for. These are
              projected on their own schedule rather than averaged, so a
              quarterly bill lands in the quarter it is due.
            </p>

            <ul className="streams">
              {currentForecast.recurring.map((stream) => (
                <li key={`${stream.merchant}-${stream.cadence}`} className="streams__row">
                  <div className="streams__who">
                    <p className="streams__merchant">{stream.merchant}</p>
                    <p className="streams__meta">
                      {stream.category ?? "Uncategorised"} ·{" "}
                      {CADENCE_LABEL[stream.cadence]} · next {dayMonth(stream.nextDue)}
                    </p>
                  </div>
                  <p className="streams__amount num">{money(stream.amount)}</p>
                  <p className="streams__monthly num">
                    {money(stream.monthlyAmount)}/mo
                  </p>
                  <span className="streams__conf" data-level={stream.confidence}>
                    {CONFIDENCE_LABEL[stream.confidence]}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}

        {currentForecast.categories.length > 0 && (
          <section className="section">
            <h2 className="section__label">Where it goes</h2>
            <p className="section__note">
              A total says how much you will spend. This says which card should
              be carrying it.
            </p>

            <table className="ftable">
              <thead>
                <tr>
                  <th scope="col">Category</th>
                  <th scope="col" className="ftable__num">MCC</th>
                  <th scope="col" className="ftable__num">Per month</th>
                  <th scope="col" className="ftable__num">
                    Over {months === 1 ? "the month" : `${months} months`}
                  </th>
                  <th scope="col" className="ftable__num">Share</th>
                </tr>
              </thead>
              <tbody>
                {currentForecast.categories.map((row) => (
                  <tr key={row.category}>
                    <th scope="row">
                      {row.category}
                      {row.recurring > 0 && (
                        <span className="ftable__tag">
                          {money(row.recurring)} committed
                        </span>
                      )}
                    </th>
                    <td className="ftable__num num">{row.mcc}</td>
                    <td className="ftable__num num">{money(row.monthly)}</td>
                    <td className="ftable__num num">{money(row.projected)}</td>
                    <td className="ftable__num num">
                      {(row.share * 100).toFixed(1)}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}

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
