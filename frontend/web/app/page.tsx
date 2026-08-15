import { CardCaps } from "@/components/CardCaps";
import { ConnectFlow } from "@/components/ConnectFlow";
import { LeakList } from "@/components/LeakList";
import { BillRouting } from "@/components/BillRouting";
import { WelcomeBonuses } from "@/components/WelcomeBonuses";
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
  const hasEligibleData = totals.spend > 0 || totals.refunds > 0;
  const hasConnectedData =
    hasEligibleData ||
    (totals.excludedCount ?? 0) > 0 ||
    (totals.uncategorisedCount ?? 0) > 0;
  const hasCompletedRun = snapshot.agents.some(
    (agent) => agent.status === "ok" || agent.status === "degraded",
  );
  const hasOnlyExcludedData = hasConnectedData && !hasEligibleData;
  const awaitingAnalysis = hasEligibleData && !hasCompletedRun;
  const noVerifiedRewards =
    hasEligibleData && hasCompletedRun && optimal <= 0.005;
  const allCaptured =
    hasEligibleData &&
    hasCompletedRun &&
    optimal > 0.005 &&
    totals.unclaimed <= 0.005;
  const leakShare = optimal > 0 ? totals.unclaimed / optimal : 0;

  const emptyRecommendation = !hasConnectedData
    ? "Connect a Plaid account or import a CSV, then run the agents to get recommendations."
    : hasOnlyExcludedData
      ? "No eligible purchases were found. Card payments, transfers, and other excluded rows cannot produce card-routing advice."
    : awaitingAnalysis
      ? "Your transactions are ready. Run the agents to calculate card recommendations."
      : noVerifiedRewards
        ? "No card recommendation can be made until at least one wallet reward rule is verified."
      : allCaptured
        ? "All identified rewards were captured. There is no card swap to recommend for this period."
        : "No additional action is currently recommended.";

  return (
    <main>
      <section className="shell hero">
        <p className="hero__eyebrow">
          {!hasConnectedData
            ? "Ready to analyse"
            : hasOnlyExcludedData
              ? "No eligible purchases"
            : awaitingAnalysis
              ? "Analysis not run"
              : noVerifiedRewards
                ? "No verified reward estimate"
              : allCaptured
                ? "All identified rewards captured"
                : "Unclaimed rewards"}{" "}
          · {period.label} · {dayMonth(period.start)} –{" "}
          {dayMonth(period.end)}
        </p>

        <p className="hero__figure num">{money(totals.unclaimed)}</p>

        <h1 className="hero__claim">
          {!hasConnectedData
            ? "Connect spending data to see what your cards actually earned."
            : hasOnlyExcludedData
              ? "Connected activity was excluded from the rewards comparison."
            : awaitingAnalysis
              ? "Your transactions are connected and waiting for an agent run."
              : noVerifiedRewards
                ? "CardSense could not verify a reward return for these purchases."
              : allCaptured
                ? "Your current routing captured every reward CardSense could verify."
                : leakShare > 0.5
                  ? "More than half of what your spending could have earned went to the wrong card."
                  : `CardSense found ${money(totals.unclaimed)} in rewards left unclaimed.`}
        </h1>

        <p className="hero__sub">
          {!hasConnectedData ? (
            <>
              No eligible transaction history is available yet. Connect Plaid
              or import a CSV, then run the agents to build the comparison.
            </>
          ) : hasOnlyExcludedData ? (
            <>
              CardSense found connected rows, but none were eligible purchases.
              Card payments, transfers, and other non-purchase activity are
              excluded so they cannot create false rewards or leakage.
            </>
          ) : awaitingAnalysis ? (
            <>
              CardSense found {money(totals.spend)} of eligible spending, but
              no completed agent run exists yet. The $0 result is a pending
              analysis, not a claim that no rewards were missed.
            </>
          ) : noVerifiedRewards ? (
            <>
              CardSense analysed {money(totals.spend)} of eligible spending,
              but no readable wallet reward rule could price the return. Add or
              verify card terms before treating $0 as a result.
            </>
          ) : (
            <>
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
              {allCaptured
                ? "No verified wallet card would have returned more on these purchases. Conditional or unreadable rates remain excluded."
                : `The same purchases, routed to the best card you already hold, would have returned ${money(optimal)}. Nothing here asks you to open a new account.`}
            </>
          )}
        </p>

        {hasEligibleData && hasCompletedRun && !noVerifiedRewards && (
          <>
            <LedgerBar
              captured={totals.captured}
              unclaimed={totals.unclaimed}
              variant="hero"
              label={`${money(totals.captured)} of rewards banked against ${money(
                totals.unclaimed,
              )} unclaimed, out of ${money(optimal)} available`}
            />
            <LedgerLegend captured={totals.captured} unclaimed={totals.unclaimed} />
          </>
        )}
      </section>

      <div className="shell">
        <ExcludedStrip totals={totals} />

        <TrackRecordStrip record={snapshot.trackRecord} />

        <WelcomeBonuses
          welcome={snapshot.welcome ?? []}
          candidates={snapshot.welcomeCandidates ?? []}
        />

        <section className="section split">
          <div>
            <h2 className="section__label">What to do next</h2>
            {snapshot.recommendations.length > 0 ? (
              <Recommendations
                items={snapshot.recommendations}
                now={generatedAt}
              />
            ) : (
              <p className="empty-state">{emptyRecommendation}</p>
            )}
          </div>

          <div>
            <h2 className="section__label">
              {allCaptured ? "Where rewards landed" : "Where it’s leaking"}
            </h2>
            <p className="section__note" style={{ marginBottom: "1.75rem" }}>
              {allCaptured
                ? "No verified category leaked rewards. Bars show what each category returned."
                : "Bar length is the total reward each category could return; the hatched part is what went to the wrong card. Ordered by what was missed, not by what was spent."}
            </p>
            {snapshot.categories.length > 0 ? (
              <LeakList categories={snapshot.categories} />
            ) : (
              <p className="empty-state">
                {hasConnectedData
                  ? "No analysed reward categories are available yet."
                  : "Categories will appear after transaction data is connected and analysed."}
              </p>
            )}
          </div>
        </section>

        <BillRouting routable={snapshot.routable ?? []} />

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

      <ConnectFlow agents={snapshot.agents} wallet={snapshot.wallet} />
    </main>
  );
}
