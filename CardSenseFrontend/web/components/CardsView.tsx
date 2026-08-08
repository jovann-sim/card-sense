"use client";

import { useMemo, useState } from "react";
import type { CardDetail, CatalogCard, ParseStatus } from "@/lib/types";
import { dayMonth, money } from "@/lib/format";
import { AddCardFlow } from "./AddCardFlow";

const PARSE_LABEL: Record<ParseStatus, string> = {
  parsed: "Rules read",
  stale: "Rules stale",
  failed: "Rules unread",
};

function Wallet({
  wallet,
  rechecking,
  onRecheck,
  onManual,
}: {
  wallet: CardDetail[];
  rechecking: string | null;
  onRecheck: (last4: string) => void;
  onManual: (card: CardDetail) => void;
}) {
  return (
    <div className="wallet">
      {wallet.map((card) => (
        <article key={card.last4} className="wcard" data-parse={card.parseStatus}>
          <header className="wcard__head">
            <div>
              <p className="wcard__name">{card.name}</p>
              <p className="wcard__meta">
                {card.network} · ••{card.last4} ·{" "}
                {card.annualFee === 0
                  ? "no annual fee"
                  : `${money(card.annualFee)} a year`}
              </p>
            </div>
            <span className="wcard__parse">{PARSE_LABEL[card.parseStatus]}</span>
          </header>

          {card.rules.length > 0 ? (
            <ul className="rules">
              {card.rules.map((rule) => (
                <li key={rule.categoryLabel} className="rules__row">
                  <span className="rules__cat">{rule.categoryLabel}</span>
                  <span className="rules__rate num">{rule.rate}</span>
                  <span className="rules__cap num">
                    {rule.cap
                      ? `${money(rule.cap)} ${rule.cycleLabel}`
                      : rule.cycleLabel}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="rules__empty">
              No rules extracted. This card is left out of every comparison.
            </p>
          )}

          {card.parseNote && <p className="wcard__note">{card.parseNote}</p>}

          {/* No state is a dead end: every card that isn't working offers
              the one action that would fix it. */}
          {card.parseStatus === "failed" && (
            <button
              type="button"
              className="btn btn--small"
              onClick={() => onManual(card)}
            >
              Enter the rates yourself
            </button>
          )}

          {card.parseStatus === "stale" && (
            <button
              type="button"
              className="btn btn--small btn--quiet"
              disabled={rechecking === card.last4}
              onClick={() => onRecheck(card.last4)}
            >
              {rechecking === card.last4 ? "Rechecking…" : "Recheck now"}
            </button>
          )}

          <dl className="prov">
            <div className="prov__pair">
              <dt>Source</dt>
              <dd>{card.source.label}</dd>
            </div>
            <div className="prov__pair">
              <dt>Located at</dt>
              <dd className="num">{card.source.locator}</dd>
            </div>
            <div className="prov__pair">
              <dt>Last read</dt>
              <dd className="num">{dayMonth(card.source.retrievedAt)}</dd>
            </div>
            <div className="prov__pair">
              <dt>Rechecks</dt>
              <dd>
                {card.recheckCadence.toLowerCase()}
                {card.recheckCadence !== "Not rechecked" && (
                  <>
                    {" "}
                    · next <span className="num">{dayMonth(card.nextRecheckAt)}</span>
                  </>
                )}
              </dd>
            </div>
          </dl>
        </article>
      ))}
    </div>
  );
}

function Catalog({
  catalog,
  onAddRequest,
}: {
  catalog: CatalogCard[];
  onAddRequest: () => void;
}) {
  const [query, setQuery] = useState("");

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const matched = q
      ? catalog.filter(
          (c) =>
            c.name.toLowerCase().includes(q) ||
            c.headlineRate.toLowerCase().includes(q) ||
            c.tags.some((t) => t.includes(q)),
        )
      : catalog;

    // Cards that would beat the current wallet come first, biggest gain down.
    return [...matched].sort((a, b) => b.deltaVsWallet - a.deltaVsWallet);
  }, [catalog, query]);

  return (
    <div>
      <label className="search">
        <span className="search__label">Search cards</span>
        <input
          className="search__input"
          type="search"
          value={query}
          placeholder="dining, no annual fee, miles…"
          onChange={(e) => setQuery(e.target.value)}
        />
      </label>

      <p className="section__note" style={{ marginBottom: "1.5rem" }}>
        Every card is priced against your actual spending this quarter, net of
        its annual fee. A card only looks good here if it would have beaten what
        you already hold.
      </p>

      {rows.length === 0 ? (
        // The moment a user discovers their card isn't in the database is
        // exactly the moment to offer adding it.
        <div className="catalog__empty">
          <p>Nothing here matches &ldquo;{query}&rdquo;.</p>
          <p className="catalog__empty-sub">
            If it&rsquo;s a card you hold, point the agent at its terms and it
            will read the rates itself.
          </p>
          <button type="button" className="btn" onClick={onAddRequest}>
            Add this card
          </button>
        </div>
      ) : (
        <ul className="catalog">
          {rows.map((card) => (
            <li key={card.name} className="crow" data-held={card.held}>
              <div className="crow__main">
                <p className="crow__name">
                  {card.name}
                  {card.held && <span className="crow__held">in your wallet</span>}
                </p>
                <p className="crow__rate">{card.headlineRate}</p>
                <p className="crow__meta">
                  {card.network} ·{" "}
                  {card.annualFee === 0
                    ? "no annual fee"
                    : `${money(card.annualFee)} a year`}
                </p>
                {card.deltaNote && <p className="crow__note">{card.deltaNote}</p>}
              </div>

              <div className="crow__delta">
                {card.held ? (
                  <span className="crow__dash" aria-hidden>
                    —
                  </span>
                ) : (
                  <>
                    <p
                      className="crow__value num"
                      data-sign={card.deltaVsWallet >= 0 ? "gain" : "loss"}
                    >
                      {card.deltaVsWallet >= 0 ? "+" : "−"}
                      {money(Math.abs(card.deltaVsWallet))}
                    </p>
                    <p className="crow__vs">vs. your wallet, per quarter</p>
                  </>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function CardsView({
  wallet: initialWallet,
  catalog,
}: {
  wallet: CardDetail[];
  catalog: CatalogCard[];
}) {
  const [tab, setTab] = useState<"wallet" | "catalog">("wallet");
  const [wallet, setWallet] = useState(initialWallet);
  const [adding, setAdding] = useState(false);
  const [manualFor, setManualFor] = useState<CardDetail | null>(null);
  const [rechecking, setRechecking] = useState<string | null>(null);

  function openAdd() {
    setManualFor(null);
    setAdding(true);
    setTab("wallet");
  }

  function recheck(last4: string) {
    setRechecking(last4);
    window.setTimeout(() => {
      const today = new Date().toISOString().slice(0, 10);
      setWallet((list) =>
        list.map((c) =>
          c.last4 === last4
            ? {
                ...c,
                parseStatus: "parsed",
                parseNote: undefined,
                source: { ...c.source, retrievedAt: today },
              }
            : c,
        ),
      );
      setRechecking(null);
    }, 1_200);
  }

  function saveCard(card: CardDetail) {
    setWallet((list) => {
      const existing = list.findIndex((c) => c.last4 === card.last4);
      if (existing === -1) return [...list, card];
      return list.map((c, i) => (i === existing ? card : c));
    });
    setAdding(false);
    setManualFor(null);
  }

  const showFlow = adding || manualFor !== null;

  return (
    <>
      <div className="tabs" role="tablist" aria-label="Cards">
        <button
          type="button"
          role="tab"
          className="tabs__tab"
          aria-selected={tab === "wallet"}
          onClick={() => setTab("wallet")}
        >
          Your wallet
          <span className="tabs__count">{wallet.length}</span>
        </button>
        <button
          type="button"
          role="tab"
          className="tabs__tab"
          aria-selected={tab === "catalog"}
          onClick={() => setTab("catalog")}
        >
          All cards
          <span className="tabs__count">{catalog.length}</span>
        </button>

        {!showFlow && (
          <button type="button" className="tabs__action" onClick={openAdd}>
            + Add a card
          </button>
        )}
      </div>

      {showFlow && (
        <AddCardFlow
          manualFor={manualFor ?? undefined}
          onAdd={saveCard}
          onCancel={() => {
            setAdding(false);
            setManualFor(null);
          }}
        />
      )}

      {tab === "wallet" ? (
        <Wallet
          wallet={wallet}
          rechecking={rechecking}
          onRecheck={recheck}
          onManual={(card) => {
            setAdding(false);
            setManualFor(card);
          }}
        />
      ) : (
        <Catalog catalog={catalog} onAddRequest={openAdd} />
      )}
    </>
  );
}
