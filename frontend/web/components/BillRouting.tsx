"use client";

import { useState } from "react";
import type { RoutableCategory } from "@/lib/types";
import { money } from "@/lib/format";

/**
 * Spending no card accepts, and what it costs to route anyway.
 *
 * The honest answer is almost always "don't". Showing the arithmetic rather
 * than the conclusion is the point: a user who can see $748 of fees buying
 * $516 of rewards does not need to be told, and will recognise the one case
 * where the numbers go the other way.
 */
export function BillRouting({ routable }: { routable: RoutableCategory[] }) {
  const [open, setOpen] = useState<string | null>(null);
  if (routable.length === 0) return null;

  const total = routable.reduce((sum, row) => sum + row.spend, 0);
  const worthAny = routable.some((row) => row.worthIt);

  return (
    <section className="section">
      <h2 className="section__label">Bills no card will take</h2>
      <p className="section__note">
        {money(total)} of your spending is with billers that do not accept cards
        at all, so it earns nothing and is left out of the comparison above. A
        payment service will charge one on your behalf for a percentage —{" "}
        {worthAny
          ? "and for at least one of these, that is worth doing."
          : "and for every category here, the fee costs more than the reward."}
      </p>

      <ul className="route">
        {routable.map((row) => {
          const expanded = open === row.category;
          return (
            <li key={row.category} className="route__row" data-worth={row.worthIt}>
              <div className="route__head">
                <div>
                  <p className="route__cat">{row.category}</p>
                  <p className="route__meta">
                    {money(row.spend)} over {row.transactions} payments ·{" "}
                    {row.bestCard ?? "no verified card"} pays{" "}
                    {(row.rewardRate * 100).toFixed(2)}%
                  </p>
                </div>

                <div className="route__sum">
                  <p className="route__net num" data-sign={row.net >= 0 ? "gain" : "loss"}>
                    {row.net >= 0 ? "+" : "−"}
                    {money(Math.abs(row.net))}
                  </p>
                  <p className="route__vs num">
                    {money(row.reward)} back − {money(row.fee)} fee
                  </p>
                </div>
              </div>

              <p className="route__verdict">{row.verdict}</p>

              <button
                type="button"
                className="route__toggle"
                aria-expanded={expanded}
                onClick={() => setOpen(expanded ? null : row.category)}
              >
                {expanded ? "Hide" : "Compare"} {row.alternatives.length} services
              </button>

              {expanded && (
                <table className="route__table">
                  <thead>
                    <tr>
                      <th scope="col">Service</th>
                      <th scope="col">Region</th>
                      <th scope="col" className="ftable__num">Fee</th>
                      <th scope="col" className="ftable__num">You pay</th>
                      <th scope="col" className="ftable__num">You earn</th>
                      <th scope="col" className="ftable__num">Net</th>
                    </tr>
                  </thead>
                  <tbody>
                    {row.alternatives.map((option) => (
                      <tr key={option.service} data-chosen={option.service === row.service}>
                        <th scope="row">
                          {option.name}
                          <span className="route__note">{option.note}</span>
                        </th>
                        <td>{option.region}</td>
                        <td className="ftable__num num">
                          {(option.feeRate * 100).toFixed(1)}%
                        </td>
                        <td className="ftable__num num">{money(option.fee)}</td>
                        <td className="ftable__num num">{money(option.reward)}</td>
                        <td
                          className="ftable__num num"
                          data-sign={option.net >= 0 ? "gain" : "loss"}
                        >
                          {option.net >= 0 ? "+" : "−"}
                          {money(Math.abs(option.net))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
