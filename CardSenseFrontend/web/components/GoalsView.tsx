"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { Goal, PlannedItem, RewardTrack, TrackValuation } from "@/lib/types";
import { count, dayMonth, money } from "@/lib/format";
import { daysBetween, projectArrival, weeksBetween } from "@/lib/goal";
import { PlannedForm } from "./PlannedForm";
import { api } from "@/lib/client-api";

/**
 * Balance and earning rate per track, as the strategy agent last reported
 * them. Switching track re-bases the goal against that track's numbers.
 */
const TRACK_LABEL: Record<RewardTrack, string> = {
  points: "Points",
  cashback: "Cash back",
  miles: "Air miles",
};

function units(n: number, track: RewardTrack) {
  return track === "cashback" ? money(n) : count(n);
}

export function GoalsView({
  goal: initialGoal,
  planned: initialPlanned,
  tracks,
  today,
}: {
  goal: Goal | null;
  planned: PlannedItem[];
  tracks: TrackValuation[];
  today: string;
}) {
  const [track, setTrack] = useState<RewardTrack>(initialGoal?.track ?? "miles");
  const [hasTarget, setHasTarget] = useState(initialGoal?.target !== null);
  const [target, setTarget] = useState(String(initialGoal?.target ?? 60_000));
  const [deadline, setDeadline] = useState(initialGoal?.deadline ?? "");
  const [purpose, setPurpose] = useState(initialGoal?.purpose ?? "");

  const [planned, setPlanned] = useState(initialPlanned);
  const [adding, setAdding] = useState(false);
  const [saving, setSaving] = useState(false);
  const [requestError, setRequestError] = useState<string | null>(null);
  const router = useRouter();

  const valuation = tracks.find((value) => value.track === track);
  const basis = {
    unitLabel: track === "cashback" ? "dollars" : track,
    current: initialGoal?.track === track ? initialGoal.current : (valuation?.rawUnits ?? 0),
    pacePerMonth: initialGoal?.track === track ? initialGoal.pacePerMonth : 0,
  };
  const targetValue = hasTarget && Number(target) > 0 ? Number(target) : null;
  const progress =
    targetValue === null ? 0 : Math.min(100, (basis.current / targetValue) * 100);

  const projected = projectArrival(
    basis.current,
    targetValue,
    basis.pacePerMonth,
    today,
  );

  // Negative means the target is reached before the deadline.
  const slipDays =
    projected && deadline ? daysBetween(deadline, projected) : null;
  const late = slipDays !== null && slipDays > 0;

  const fix = initialGoal?.fix;
  const fixProjected = fix
    ? projectArrival(basis.current, targetValue, fix.pacePerMonth, today)
    : null;

  async function saveGoal() {
    setSaving(true);
    setRequestError(null);
    try {
      await api("/api/v1/goals", {
        method: "POST",
        body: JSON.stringify({ track, target: targetValue, unitLabel: basis.unitLabel, current: basis.current, deadline: deadline || null, purpose }),
      });
      router.refresh();
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "Unable to save goal.");
    } finally {
      setSaving(false);
    }
  }

  async function addPlan(item: PlannedItem) {
    setSaving(true);
    setRequestError(null);
    try {
      await api("/api/v1/planned", { method: "POST", body: JSON.stringify(item) });
      setPlanned((list) => [...list, item].sort((a, b) => a.startDate.localeCompare(b.startDate)));
      setAdding(false);
      router.refresh();
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "Unable to save planned spending.");
    } finally {
      setSaving(false);
    }
  }

  async function removePlan(id: string) {
    setSaving(true);
    setRequestError(null);
    try {
      await api(`/api/v1/planned/${id}`, { method: "DELETE" });
      setPlanned((list) => list.filter((item) => item.id !== id));
      router.refresh();
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "Unable to remove planned spending.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <section className="section">
        <h2 className="section__label">What you&rsquo;re working toward</h2>

        <div className="goal">
          <div className="goal__form">
            <div className="field">
              <span className="field__label">I want</span>
              <div className="pform__kinds">
                {(Object.keys(TRACK_LABEL) as RewardTrack[]).map((t) => (
                  <button
                    key={t}
                    type="button"
                    className="chip"
                    aria-pressed={track === t}
                    onClick={() => setTrack(t)}
                  >
                    {TRACK_LABEL[t]}
                  </button>
                ))}
              </div>
            </div>

            <div className="pform__grid">
              <label className="field">
                <span className="field__label">Target</span>
                <input
                  className="field__input"
                  type="number"
                  min="1"
                  value={target}
                  disabled={!hasTarget}
                  onChange={(e) => setTarget(e.target.value)}
                />
              </label>

              <label className="field">
                <span className="field__label">By</span>
                <input
                  className="field__input"
                  type="date"
                  value={deadline}
                  disabled={!hasTarget}
                  onChange={(e) => setDeadline(e.target.value)}
                />
              </label>

              <label className="field field--wide">
                <span className="field__label">What it&rsquo;s for</span>
                <input
                  className="field__input"
                  value={purpose}
                  placeholder="Two business-class seats to Tokyo"
                  onChange={(e) => setPurpose(e.target.value)}
                />
              </label>
            </div>

            <label className="check">
              <input
                type="checkbox"
                checked={!hasTarget}
                onChange={(e) => setHasTarget(!e.target.checked)}
              />
              <span>
                No finish line — just earn as much {TRACK_LABEL[track].toLowerCase()} as
                possible
              </span>
            </label>
            <div className="pform__actions">
              <button type="button" className="btn" onClick={saveGoal} disabled={saving}>
                {saving ? "Saving…" : "Save goal"}
              </button>
            </div>
          </div>

          <div className="goal__state" data-late={late}>
            {targetValue === null ? (
              <>
                <p className="goal__verdict">Maximising, with no deadline.</p>
                <p className="goal__detail">
                  Every recommendation will be ranked by nominal dollar value in{" "}
                  {TRACK_LABEL[track].toLowerCase()}. You currently hold{" "}
                  {units(basis.current, track)} {basis.unitLabel}, earning about{" "}
                  {units(basis.pacePerMonth, track)} a month.
                </p>
              </>
            ) : (
              <>
                <p className="goal__progress-figure num">
                  {units(basis.current, track)}{" "}
                  <span className="goal__of">
                    / {units(targetValue, track)} {basis.unitLabel}
                  </span>
                </p>

                <div className="goal__bar" aria-hidden>
                  <span
                    className="goal__fill"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                <p className="goal__pct num">{Math.round(progress)}%</p>

                {projected && (
                  <p className="goal__verdict">
                    {deadline === "" ? (
                      <>You get there around {dayMonth(projected)}.</>
                    ) : late ? (
                      <>
                        You miss this by {weeksBetween(deadline, projected)} weeks
                        — arriving {dayMonth(projected)}, not{" "}
                        {dayMonth(deadline)}.
                      </>
                    ) : (
                      <>
                        On track — you arrive {dayMonth(projected)}, {-slipDays!}{" "}
                        days early.
                      </>
                    )}
                  </p>
                )}

                <p className="goal__detail">
                  At your current rate of about{" "}
                  {units(basis.pacePerMonth, track)} {basis.unitLabel} a month.
                </p>
              </>
            )}
          </div>
        </div>

        {late && fix && fixProjected && (
          <div className="fix">
            <p className="fix__label">One change closes it</p>
            <p className="fix__action">{fix.action}</p>
            <p className="fix__detail">
              Raises you to about {units(fix.pacePerMonth, track)}{" "}
              {basis.unitLabel} a month, which brings the date to{" "}
              <strong>{dayMonth(fixProjected)}</strong> —{" "}
              {deadline
                ? `${Math.abs(daysBetween(deadline, fixProjected))} days ${
                    daysBetween(deadline, fixProjected) <= 0 ? "early" : "late"
                  }`
                : "sooner"}
              .
            </p>
          </div>
        )}
      </section>

      <section className="section">
        <h2 className="section__label">What you have planned</h2>
        <p className="section__note">
          Spending the agent could not have inferred from your history. Each one
          feeds the forecast and can change which card you should be holding on
          the day.
        </p>

        <ul className="plans">
          {planned.map((item) => (
            <li key={item.id} className="plan">
              <div className="plan__main">
                <p className="plan__label">
                  {item.label}
                  <span className="plan__kind">
                    {item.kind === "event" ? "trip or event" : "purchase"}
                  </span>
                </p>
                <p className="plan__meta num">
                  {dayMonth(item.startDate)}
                  {item.endDate && ` – ${dayMonth(item.endDate)}`} ·{" "}
                  {money(item.amount)} · {item.categories.join(", ")}
                </p>
                {item.note && <p className="plan__note">{item.note}</p>}
              </div>
              <button
                type="button"
                className="plan__remove"
                onClick={() => removePlan(item.id)}
              >
                Remove
              </button>
            </li>
        ))}
        </ul>

        {requestError && <p className="addcard__fine" role="alert">{requestError}</p>}

        {adding ? (
          <PlannedForm
            defaultDate={today.slice(0, 10)}
            onCancel={() => setAdding(false)}
            onAdd={addPlan}
          />
        ) : (
          <button type="button" className="btn" onClick={() => setAdding(true)}>
            Add something planned
          </button>
        )}
      </section>
    </>
  );
}
