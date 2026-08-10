import { CardCaps } from "@/components/CardCaps";
import { ConnectFlow } from "@/components/ConnectFlow";
import { LeakList } from "@/components/LeakList";
import { LedgerBar, LedgerLegend } from "@/components/LedgerBar";
import { Recommendations } from "@/components/Recommendations";
import { TrackPanel } from "@/components/TrackPanel";
import { ExcludedStrip } from "@/components/ExcludedStrip";
import { TrackRecordStrip } from "@/components/TrackRecordStrip";
import { dayMonth, money } from "@/lib/format";
import { getSnapshot } from "@/lib/api";

export default async function SpendingAnalytics() {
  const snapshot = await getSnapshot();
  const { period, totals, generatedAt } = snapshot;
  const optimal = totals.captured + totals.unclaimed;

  return (
    <main>
      <section className="shell hero">
        <p className="hero__eyebrow">
          Unclaimed rewards · {period.label} · {dayMonth(period.start)} –{" "}
          {dayMonth(period.end)}
        </p>

        <p className="hero__figure num">{money(totals.unclaimed)}</p>

        <h1 className="hero__claim">
          More than half of what your spending could have earned went to the
          wrong card.
        </h1>

        <p className="hero__sub">
          You banked {money(totals.captured)} on {money(totals.spend)} of
          spending. {totals.refunds > 0 && (
            <>
              Refunds and credits total {money(totals.refunds)}. {totals.netSpend < 0 ? (
                <>
                  That is {money(Math.abs(totals.netSpend))} more in credits
                  than purchases. {" "}
                </>
              ) : (
                <>Net spending is {money(totals.netSpend)}. {" "}</>
              )}
            </>
          )}
          The same purchases, routed to the best card you already
          hold, would have returned {money(optimal)}. Nothing here asks you to
          open a new account.
        </p>

        <LedgerBar
          captured={totals.captured}
          unclaimed={totals.unclaimed}
          variant="hero"
          label={`${money(totals.captured)} of rewards banked against ${money(
            totals.unclaimed,
          )} unclaimed, out of ${money(optimal)} available`}
        />
        <LedgerLegend captured={totals.captured} unclaimed={totals.unclaimed} />
      </section>

      <div className="shell">
        <ExcludedStrip totals={totals} />

        <TrackRecordStrip record={snapshot.trackRecord} />

        <section className="section split">
          <div>
            <h2 className="section__label">What to do next</h2>
            <Recommendations
              items={snapshot.recommendations}
              now={generatedAt}
            />
          </div>

          <div>
            <h2 className="section__label">Where it&rsquo;s leaking</h2>
            <p className="section__note" style={{ marginBottom: "1.75rem" }}>
              Bar length is the total reward each category could return; the
              hatched part is what went to the wrong card. Ordered by what was
              missed, not by what was spent.
            </p>
            <LeakList categories={snapshot.categories} />
          </div>
        </section>

        <section className="section">
          <h2 className="section__label">Cards &amp; caps</h2>
          <p className="section__note">
            A card stops being the best choice the moment it hits its cap. These
            are the limits currently shaping every recommendation above.
          </p>
          <div style={{ marginTop: "1.5rem" }}>
            <CardCaps cards={snapshot.cards} />
          </div>
        </section>

        <section className="section">
          <h2 className="section__label">Reward track</h2>
          <p className="section__note">
            Points, cash back, and miles are not comparable until they are all
            priced in dollars. Below is this quarter&rsquo;s balance in each,
            converted at the rates stated on each card.
          </p>
          <div style={{ marginTop: "1.5rem" }}>
            <TrackPanel
              tracks={snapshot.tracks}
              recommended={snapshot.recommendedTrack}
              rationale={snapshot.trackRationale}
              hasPreference={snapshot.trackPreference !== null}
            />
          </div>
        </section>
      </div>

      <ConnectFlow agents={snapshot.agents} />
    </main>
  );
}
