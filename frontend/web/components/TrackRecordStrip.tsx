import Link from "next/link";
import type { TrackRecord } from "@/lib/types";
import { dayMonth, money } from "@/lib/format";

/**
 * The accountability loop, on the front page: what the agent promised against
 * what the spending actually returned. It is the one claim on this dashboard
 * that can be checked, so it gets stated before anything is asked of the user.
 */
export function TrackRecordStrip({ record }: { record: TrackRecord }) {
  const open = record.open ?? record.records.filter(
    (r) => r.outcome === "open" && !r.invalidatedByRunId,
  ).length;
  const superseded = record.superseded ?? record.records.filter(
    (r) => Boolean(r.invalidatedByRunId),
  ).length;
  const lastClosed = record.records.find(
    (r) => r.outcome === "acted" && r.actual !== undefined,
  );

  return (
    <section className="record">
      <div className="record__figures">
        <p className="record__label">Track record</p>
        <p className="record__line">
          <span className="record__value">
            {open} open
          </span>{" "}
          · <span className="record__value">{record.taken} taken</span>{" "}
          · <span className="record__value">{superseded} superseded</span>{" "}
          ·{" "}
          <span className="record__value record__value--good">
            {money(record.earned)}
          </span>{" "}
          earned ·{" "}
          <span className="record__value record__value--miss">
            {money(record.missed)}
          </span>{" "}
          missed
        </p>
        <p className="record__note">{record.accuracyNote}</p>
      </div>

      {lastClosed && (
        <div className="record__last">
          <p className="record__label">
            Last closed · {dayMonth(lastClosed.resolvedAt ?? lastClosed.pushedAt)}
          </p>
          <p className="record__headline">{lastClosed.headline}</p>
          <p className="record__math">
            predicted <span className="num">{money(lastClosed.predicted)}</span>{" "}
            <span className="record__arrow" aria-hidden>
              →
            </span>{" "}
            earned{" "}
            <span
              className="num record__actual"
              data-beat={(lastClosed.actual ?? 0) >= lastClosed.predicted}
            >
              {money(lastClosed.actual ?? 0)}
            </span>
          </p>
        </div>
      )}

      <Link href="/history" className="record__link">
        Every recommendation →
      </Link>
    </section>
  );
}
