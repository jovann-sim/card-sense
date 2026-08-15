import type { WelcomeCandidate, WelcomeProgress } from "@/lib/types";
import { money, moneyWhole } from "@/lib/format";

const STATE_LABEL: Record<WelcomeProgress["state"], string> = {
  met: "Earned",
  "on-track": "On track",
  "at-risk": "At risk",
  missed: "Window closed",
};

/**
 * The only deadline in the product that costs money if it passes.
 *
 * Everything else here is an optimisation that can be taken tomorrow. A
 * welcome bonus expires, and missing one by a couple of hundred dollars of
 * spending loses several hundred — so it leads, and it shows the gap in the
 * terms the user can act on: dollars per day, against the dollars per day they
 * are actually managing.
 */
export function WelcomeBonuses({
  welcome,
  candidates,
}: {
  welcome: WelcomeProgress[];
  candidates: WelcomeCandidate[];
}) {
  if (welcome.length === 0 && candidates.length === 0) return null;

  return (
    <>
      {welcome.length > 0 && (
        <section className="section">
          <h2 className="section__label">Bonus windows</h2>
          <p className="section__note">
            Measured against spending the issuer would actually count —
            transfers excluded, refunds subtracted, this card only.
          </p>

          <ul className="wb">
            {welcome.map((row) => {
              const pct = Math.min(100, (row.qualifyingSpend / row.minSpend) * 100);
              return (
                <li key={row.card} className="wb__row" data-state={row.state}>
                  <div className="wb__head">
                    <div>
                      <p className="wb__card">{row.card}</p>
                      <p className="wb__meta">
                        {row.award.toLocaleString()} {row.unit} ·{" "}
                        {moneyWhole(row.valueUsd)} · closes {row.deadline}
                      </p>
                    </div>
                    <span className="wb__state">{STATE_LABEL[row.state]}</span>
                  </div>

                  <div
                    className="wb__track"
                    role="img"
                    aria-label={`${money(row.qualifyingSpend)} of ${money(row.minSpend)} qualifying spend`}
                  >
                    <span className="wb__fill" style={{ width: `${pct}%` }} />
                  </div>

                  <p className="wb__figures num">
                    {money(row.qualifyingSpend)}{" "}
                    <span className="wb__of">of {money(row.minSpend)}</span>
                    {row.gap > 0 && (
                      <span className="wb__gap">
                        {" "}
                        · {money(row.gap)} to go in {row.daysLeft} days
                      </span>
                    )}
                  </p>

                  {row.gap > 0 && row.daysLeft > 0 && (
                    <p className="wb__pace">
                      Needs {money(row.perDayNeeded)}/day. You are averaging{" "}
                      {money(row.perDayCurrent)}.
                    </p>
                  )}

                  {row.rescue?.worthIt && (
                    <p className="wb__rescue">
                      <strong>The fee is worth it here.</strong> Routing{" "}
                      {money(row.rescue.spendToRoute)} of bills through{" "}
                      {row.rescue.serviceName} costs {money(row.rescue.fee)} and
                      closes the gap — still {money(row.rescue.net)} ahead. This
                      is the one case where paying to put a bill on a card wins.
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {candidates.length > 0 && (
        <section className="section">
          <h2 className="section__label">Bonuses you would clear</h2>
          <p className="section__note">
            Not what these cards advertise — whether your own spending of{" "}
            {money(candidates[0].monthlySpend)} a month would actually reach the
            minimum inside the window.
          </p>

          <table className="ftable">
            <thead>
              <tr>
                <th scope="col">Card</th>
                <th scope="col" className="ftable__num">Bonus</th>
                <th scope="col" className="ftable__num">Minimum</th>
                <th scope="col" className="ftable__num">You&rsquo;d spend</th>
                <th scope="col" className="ftable__num">Verdict</th>
              </tr>
            </thead>
            <tbody>
              {candidates.map((row) => (
                <tr key={row.card} data-qualifies={row.qualifies}>
                  <th scope="row">
                    {row.card}
                    <span className="ftable__tag">
                      {row.award.toLocaleString()} {row.unit}
                    </span>
                  </th>
                  <td className="ftable__num num">{moneyWhole(row.valueUsd)}</td>
                  <td className="ftable__num num">
                    {moneyWhole(row.minSpend)}
                    <span className="ftable__tag">in {row.monthsAllowed} mo</span>
                  </td>
                  <td className="ftable__num num">
                    {moneyWhole(row.projectedSpend)}
                  </td>
                  <td className="ftable__num">
                    {row.qualifies ? (
                      <span className="wb__yes">Clears it</span>
                    ) : (
                      <span className="wb__no">
                        {moneyWhole(row.shortfall)} short
                        {row.monthsToMinimum !== null && (
                          <span className="ftable__tag">
                            needs {row.monthsToMinimum} mo
                          </span>
                        )}
                      </span>
                    )}
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
