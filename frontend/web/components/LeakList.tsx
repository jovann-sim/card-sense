import type { CSSProperties } from "react";
import type { CategoryFlag, CategoryLeak } from "@/lib/types";
import { money } from "@/lib/format";
import { LedgerBar } from "./LedgerBar";

const FLAG_LABEL: Record<CategoryFlag, string> = {
  "multi-mcc": "Split across categories",
  "ambiguous-merchant": "Merchant unclear",
  "conditional-rate": "Eligibility unverified",
  "rules-unverified": "Rules unread",
};

export function LeakList({ categories }: { categories: CategoryLeak[] }) {
  // Sorted by what is unclaimed, not by what was spent: the page is about
  // opportunity, and the biggest category is rarely the biggest leak.
  const rows = [...categories].sort((a, b) => b.unclaimed - a.unclaimed);

  // Bar length is the total reward the category could return, scaled against
  // the richest category — so a long bar means a lot was on offer, and the
  // hatched share of it means a lot was missed.
  const maxReward = Math.max(
    0,
    ...rows.map((r) => r.captured + r.unclaimed),
  );

  return (
    <ol className="leak">
      {rows.map((row, i) => (
        <li key={row.category} className="leak__row">
          <div className="leak__head">
            <p className="leak__name">
              {row.category}
              <span className="leak__mcc">MCC {row.mcc}</span>
            </p>
            <p className="leak__amount">{money(row.unclaimed)}</p>
          </div>

          <div
            className="leak__track"
            style={
              {
                "--track": `${
                  maxReward > 0
                    ? ((row.captured + row.unclaimed) / maxReward) * 100
                    : 0
                }%`,
              } as CSSProperties
            }
          >
            <LedgerBar
              captured={row.captured}
              unclaimed={row.unclaimed}
              variant="row"
              delay={120 + i * 55}
              label={`${row.category}: ${money(row.captured)} banked, ${money(
                row.unclaimed,
              )} unclaimed on ${money(row.spend)} of spending`}
            />
          </div>

          <div className="leak__meta">
            <span className="leak__swap">
              {row.usedCard}
              {row.bestCard !== row.usedCard && ` → ${row.bestCard}`}
            </span>
            {row.flags?.map((flag) => (
              <span key={flag} className="flag" title={row.note}>
                {FLAG_LABEL[flag]}
              </span>
            ))}
          </div>

          {row.note && <p className="leak__note">{row.note}</p>}
        </li>
      ))}
    </ol>
  );
}
