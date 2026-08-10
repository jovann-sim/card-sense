import { money } from "@/lib/format";
import type { Totals } from "@/lib/types";

/**
 * What is deliberately not in the figures above.
 *
 * The dashboard reports less than a bank statement would, because salary,
 * transfers and card bill payments are not spending, and because a purchase we
 * could not categorise cannot be claimed by any card rule. A user who cannot
 * see why is entitled to assume the number is simply wrong.
 */
export function ExcludedStrip({ totals }: { totals: Totals }) {
  const excluded = totals.excludedSpend ?? 0;
  const uncategorised = totals.uncategorisedSpend ?? 0;
  const redirectable = totals.redirectableSpend ?? 0;
  if (excluded + uncategorised + redirectable === 0) return null;

  const share =
    totals.spend > 0 ? Math.round((uncategorised / totals.spend) * 100) : 0;

  return (
    <section className="excluded">
      <p className="excluded__label">Not counted above</p>

      <ul className="excluded__items">
        {excluded > 0 && (
          <li className="excluded__item">
            <span className="excluded__value num">{money(excluded)}</span>
            <span className="excluded__what">
              moved rather than spent — salary, transfers and card bill payments
              across {totals.excludedCount ?? 0} transactions. No card earns on these.
            </span>
          </li>
        )}

        {uncategorised > 0 && (
          <li className="excluded__item" data-weight={share >= 25 ? "high" : undefined}>
            <span className="excluded__value num">{money(uncategorised)}</span>
            <span className="excluded__what">
              could not be placed in a category{share > 0 && ` — ${share}% of your spending`}.
              No card rule can claim it, so it is left out of the comparison rather
              than credited at a rate that would flatter every card equally.
            </span>
          </li>
        )}

        {redirectable > 0 && (
          <li className="excluded__item" data-kind="opportunity">
            <span className="excluded__value num">{money(redirectable)}</span>
            <span className="excluded__what">
              in bills that take no card today — rent, utilities, insurance.
              A payment service could route these onto a card for a fee, which
              is worth doing only when the reward beats the fee.
            </span>
          </li>
        )}
      </ul>
    </section>
  );
}
