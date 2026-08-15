import type { StrategyPlan as Plan } from "@/lib/types";
import { money, moneyWhole } from "@/lib/format";

const KIND_LABEL: Record<string, string> = {
  reassign: "Move spending",
  acquire: "New card",
  "route-welcome": "Pay a fee, on purpose",
  "route-ongoing": "Route a bill",
};

/**
 * The whole simulation, as an instruction list.
 *
 * Everything else on the dashboard reports a condition. This says what to do
 * about it, in the order that pays best, with the arithmetic visible so the
 * ordering can be argued with rather than trusted.
 */
export function StrategyPlan({ plan }: { plan: Plan | Record<string, never> }) {
  const steps = "steps" in plan ? plan.steps : [];
  const additions = "additions" in plan ? plan.additions : [];
  if (steps.length === 0 && additions.length === 0) return null;

  const captured = "capturedNow" in plan ? plan.capturedNow : 0;
  const best = "bestWithWallet" in plan ? plan.bestWithWallet : 0;
  const days = "observedDays" in plan ? plan.observedDays : 0;

  return (
    <>
      {steps.length > 0 && (
        <section className="section">
          <h2 className="section__label">What to do</h2>
          <p className="section__note">
            Every card you hold and every card you don&rsquo;t, priced against{" "}
            {days} days of your own spending. You earned {money(captured)}; the
            cards in your wallet could have earned {money(best)}. These are the
            moves, best first.
          </p>

          <ol className="plan">
            {steps.map((step) => (
              <li key={`${step.rank}-${step.kind}`} className="plan__row" data-kind={step.kind}>
                <p className="plan__rank num">{step.rank}</p>

                <div className="plan__body">
                  <p className="plan__kind">{KIND_LABEL[step.kind] ?? step.kind}</p>
                  <p className="plan__title">{step.title}</p>
                  <p className="plan__detail">{step.detail}</p>
                  {step.categories && step.categories.length > 0 && (
                    <p className="plan__cats">{step.categories.join(" · ")}</p>
                  )}
                </div>

                <div className="plan__worth">
                  <p className="plan__value num">+{money(step.value)}</p>
                  <p className="plan__window">{step.valueWindow}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      {additions.length > 0 && (
        <section className="section">
          <h2 className="section__label">Cards you don&rsquo;t hold</h2>
          <p className="section__note">
            Priced by re-running your whole history with each card added, not by
            what it advertises — a card that duplicates one you already hold adds
            nothing. The first year carries the welcome bonus; every year after
            does not, which is the column that decides whether to keep it.
          </p>

          <table className="ftable">
            <thead>
              <tr>
                <th scope="col">Card</th>
                <th scope="col" className="ftable__num">Adds/yr</th>
                <th scope="col" className="ftable__num">Fee</th>
                <th scope="col" className="ftable__num">First year</th>
                <th scope="col" className="ftable__num">Every year after</th>
              </tr>
            </thead>
            <tbody>
              {additions.map((row) => (
                <tr key={row.id} data-worth={row.worthIt}>
                  <th scope="row">
                    {row.card}
                    {row.headlineRate && (
                      <span className="ftable__tag">{row.headlineRate}</span>
                    )}
                  </th>
                  <td className="ftable__num num">{money(row.rewardPerYear)}</td>
                  <td className="ftable__num num">
                    {row.annualFee ? moneyWhole(row.annualFee) : "—"}
                  </td>
                  <td className="ftable__num num">
                    {moneyWhole(row.netFirstYear)}
                    {row.welcomeValue > 0 && (
                      <span className="ftable__tag">
                        incl. {moneyWhole(row.welcomeValue)} bonus
                      </span>
                    )}
                  </td>
                  <td
                    className="ftable__num num"
                    data-sign={row.netOngoing >= 0 ? "gain" : "loss"}
                  >
                    {row.netOngoing >= 0 ? "+" : "−"}
                    {moneyWhole(Math.abs(row.netOngoing))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </>
  );
}
