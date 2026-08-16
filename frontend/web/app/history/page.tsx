import type { Metadata } from "next";
import type { AdviceRecord } from "@/lib/types";
import { dayMonth, money, pct } from "@/lib/format";
import { getSnapshot } from "@/lib/api";

export const metadata: Metadata = {
  title: "CardSense — Track record",
};

function Row({ record }: { record: AdviceRecord }) {
  const closed = record.actual !== undefined;
  const beat = closed && (record.actual as number) >= record.predicted;
  const ratio = closed
    ? pct(Math.min(record.actual as number, record.predicted), record.predicted)
    : 0;

  return (
    <li className="rec-row" data-outcome={record.outcome}>
      <div className="rec-row__head">
        <p className="rec-row__headline">{record.headline}</p>
        <p className="rec-row__when num">
          {dayMonth(record.resolvedAt ?? record.pushedAt)}
        </p>
      </div>

      <p className="rec-row__meta">
        {record.card && (
          <span className="rec-row__card">
            {record.card.name} ••{record.card.last4}
          </span>
        )}
        <span className="rec-row__window">{record.window}</span>
      </p>

      {closed ? (
        <div className="claim">
          <div className="claim__bar" aria-hidden>
            <span className="claim__fill" style={{ width: `${ratio}%` }} />
          </div>
          <p className="claim__math">
            predicted <span className="num">{money(record.predicted)}</span>
            <span className="claim__arrow" aria-hidden>
              →
            </span>
            earned{" "}
            <span className="num claim__actual" data-beat={beat}>
              {money(record.actual as number)}
            </span>
          </p>
        </div>
      ) : (
        <p className="claim__open num">
          {money(record.predicted)} <span className="claim__pending">at stake</span>
        </p>
      )}

      {record.gapReason && <p className="rec-row__gap">{record.gapReason}</p>}
    </li>
  );
}

export default async function HistoryPage() {
  const snapshot = await getSnapshot();
  const { trackRecord } = snapshot;
  const open = trackRecord.records.filter(
    (r) => r.outcome === "open" && !r.invalidatedByRunId,
  );
  const closed = trackRecord.records.filter((r) => r.outcome === "acted");
  const notTaken = trackRecord.records.filter(
    (r) => !r.invalidatedByRunId &&
      (r.outcome === "expired" || r.outcome === "dismissed"),
  );
  const superseded = trackRecord.records.filter(
    (r) => Boolean(r.invalidatedByRunId),
  );

  return (
    <main>
      <section className="shell hero hero--sub">
        <p className="hero__eyebrow">Track record</p>

        <p className="hero__figure hero__figure--sub hero__figure--good num">
          {money(trackRecord.earned)}
        </p>

        <h1 className="hero__claim">
          Earned from advice you actually took. Every prediction below is checked
          against what the transactions returned.
        </h1>

        <p className="hero__sub">
          {open.length} open · {trackRecord.taken} taken · {superseded.length} superseded.{" "}
          {money(trackRecord.missed)} went unclaimed on the ones that did not.{" "}
          {trackRecord.accuracyNote}
        </p>
      </section>

      <div className="shell">
        <section className="section">
          <h2 className="section__label">Still open</h2>
          <ol className="rec-rows">
            {open.map((r) => (
              <Row key={r.id} record={r} />
            ))}
          </ol>
        </section>

        <section className="section">
          <h2 className="section__label">Taken, and what they returned</h2>
          <p className="section__note">
            The bar shows how close the prediction landed to reality. A short bar
            means the agent over-promised, and the reason is stated rather than
            quietly dropped.
          </p>
          <ol className="rec-rows" style={{ marginTop: "1.75rem" }}>
            {closed.map((r) => (
              <Row key={r.id} record={r} />
            ))}
          </ol>
        </section>

        <section className="section">
          <h2 className="section__label">Not taken</h2>
          <ol className="rec-rows">
            {notTaken.map((r) => (
              <Row key={r.id} record={r} />
            ))}
          </ol>
        </section>

        {superseded.length > 0 && (
          <section className="section">
            <h2 className="section__label">Superseded by later analysis</h2>
            <p className="section__note">
              These remain in the audit trail, but are not counted as advice you
              chose not to take.
            </p>
            <ol className="rec-rows" style={{ marginTop: "1.75rem" }}>
              {superseded.map((r) => (
                <Row key={r.id} record={r} />
              ))}
            </ol>
          </section>
        )}
      </div>
    </main>
  );
}
