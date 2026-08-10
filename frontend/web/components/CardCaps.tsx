import type { CSSProperties } from "react";
import type { CapState, CardCap } from "@/lib/types";
import { money, pct } from "@/lib/format";

const STATE_LABEL: Record<CapState, string> = {
  healthy: "Room left",
  approaching: "Nearly capped",
  reached: "Cap reached",
  unverified: "Terms unread",
};

export function CardCaps({ cards }: { cards: CardCap[] }) {
  return (
    <ul className="caps">
      {cards.map((card) => {
        const filled = card.cap ? pct(card.cycleSpend, card.cap) : 0;
        // No cap and terms we could read: the limit is genuinely unbounded.
        // No cap because the terms never parsed is a different thing entirely.
        const uncapped = !card.cap && card.state !== "unverified";

        return (
          <li
            key={card.last4}
            className={card.state === "unverified" ? "cap cap--unverified" : "cap"}
            data-state={card.state}
          >
            <div>
              <p className="cap__name">
                {card.name} <span className="cap__digits">••{card.last4}</span>
              </p>
              <p className="cap__sub">
                {card.network} · {card.categoryLabel} · {card.rate}
              </p>
            </div>

            <div>
              {/* An uncapped card gets a full quiet band rather than an empty
                  meter, which would read as "nothing spent yet". */}
              <div
                className={uncapped ? "cap__meter cap__meter--uncapped" : "cap__meter"}
                role="img"
                aria-label={
                  card.cap
                    ? `${money(card.cycleSpend)} of a ${money(card.cap)} ${card.cycleLabel}`
                    : `${money(card.cycleSpend)} spent, ${card.cycleLabel}`
                }
              >
                {card.cap && (
                  <div
                    className="cap__fill"
                    style={{ "--w": `${filled}%` } as CSSProperties}
                  />
                )}
              </div>
              <p className="cap__figures">
                {money(card.cycleSpend)}
                {card.cap ? ` / ${money(card.cap)} ${card.cycleLabel}` : ` · ${card.cycleLabel}`}
              </p>
              {card.note && <p className="cap__sub">{card.note}</p>}
            </div>

            <span className="cap__state">{STATE_LABEL[card.state]}</span>
          </li>
        );
      })}
    </ul>
  );
}
