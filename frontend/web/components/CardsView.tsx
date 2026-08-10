"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import type { CardDetail, CatalogCard, ParseStatus, Snapshot } from "@/lib/types";
import { dayMonth, money, moneyIn, timeOfDay } from "@/lib/format";
import { api, userId } from "@/lib/client-api";
import { AddCardFlow } from "./AddCardFlow";

const PARSE_LABEL: Record<ParseStatus, string> = {
  parsed: "Rules read",
  stale: "Rules stale",
  failed: "Rules unread",
};

type PlaidAccount = {
  id: string;
  itemId: string;
  mask?: string | null;
  name?: string | null;
  officialName?: string | null;
  type?: string;
  subtype?: string;
  linkedCard?: string | null;
};

type PlaidItem = {
  itemId: string;
  institutionId?: string | null;
  institutionName?: string | null;
  createdAt?: string | null;
  lastSyncedAt?: string | null;
  accounts: number;
};

function PlaidConnections({
  items,
  accounts,
  loading,
  syncing,
  disconnecting,
  status,
  onSync,
  onDisconnect,
}: {
  items: PlaidItem[];
  accounts: PlaidAccount[];
  loading: boolean;
  syncing: string | null;
  disconnecting: string | null;
  status: string | null;
  onSync: (item: PlaidItem) => void;
  onDisconnect: (item: PlaidItem) => void;
}) {
  if (loading) {
    return <p className="connections__status" role="status">Loading Plaid connections…</p>;
  }

  if (items.length === 0) {
    return (
      <div className="connections__empty">
        <p>No Plaid institution is connected.</p>
        <p>Connect a credit account before assigning its transactions to a wallet card.</p>
        <Link className="btn btn--small" href="/">Connect an account</Link>
      </div>
    );
  }

  return (
    <div className="connections">
      <div className="connections__intro">
        <div>
          <h2 className="section__label">Plaid connections</h2>
          <p className="section__note">
            Plaid supplies accounts and transactions. Wallet cards supply the reward rules used to price them.
          </p>
        </div>
        <div className="connections__tools">
          {status && <p className="connections__status" role="status">{status}</p>}
          <Link className="btn btn--small btn--quiet" href="/">Connect another account</Link>
        </div>
      </div>

      {items.map((item) => {
        const itemAccounts = accounts.filter((account) => account.itemId === item.itemId);
        const displayName = item.institutionName || itemAccounts[0]?.officialName ||
          itemAccounts[0]?.name || "Plaid institution";
        const busy = syncing === item.itemId || disconnecting === item.itemId;
        return (
          <article className="connection" key={item.itemId}>
            <header className="connection__head">
              <div>
                <p className="connection__name">{displayName}</p>
                <p className="connection__meta num">
                  Item {item.itemId.slice(0, 8)}… · {item.accounts} account{item.accounts === 1 ? "" : "s"}
                </p>
              </div>
              <span className="connection__state">Connected</span>
            </header>

            <dl className="connection__facts">
              <div>
                <dt>Last synced</dt>
                <dd>
                  {item.lastSyncedAt
                    ? `${dayMonth(item.lastSyncedAt)} at ${timeOfDay(item.lastSyncedAt)}`
                    : "Not synced yet"}
                </dd>
              </div>
              {item.institutionId && (
                <div>
                  <dt>Institution ID</dt>
                  <dd className="num">{item.institutionId}</dd>
                </div>
              )}
            </dl>

            <ul className="connection__accounts">
              {itemAccounts.map((account) => {
                const credit = `${account.type ?? ""} ${account.subtype ?? ""}`
                  .toLowerCase().includes("credit");
                const state = account.linkedCard ? "linked" : credit ? "unmatched" : "ineligible";
                return (
                  <li className="connection__account" data-state={state} key={account.id}>
                    <div>
                      <p className="connection__account-name">
                        {account.officialName || account.name || "Plaid account"}
                      </p>
                      <p className="connection__account-meta">
                        {account.subtype || account.type || "account"}
                        {account.mask ? ` · ••${account.mask}` : ""}
                      </p>
                    </div>
                    <span className="connection__account-state">
                      {account.linkedCard
                        ? `Linked to ${account.linkedCard}`
                        : credit
                          ? "Needs a wallet card"
                          : "Not a credit card"}
                    </span>
                  </li>
                );
              })}
              {itemAccounts.length === 0 && (
                <li className="connection__account connection__account--empty">
                  No accounts were returned for this Item.
                </li>
              )}
            </ul>

            <div className="connection__actions">
              <button
                type="button"
                className="btn btn--small"
                disabled={busy}
                onClick={() => onSync(item)}
              >
                {syncing === item.itemId ? "Syncing…" : "Sync now"}
              </button>
              <button
                type="button"
                className="btn btn--small btn--quiet connection__disconnect"
                disabled={busy}
                onClick={() => onDisconnect(item)}
              >
                {disconnecting === item.itemId ? "Disconnecting…" : "Disconnect"}
              </button>
            </div>
          </article>
        );
      })}
    </div>
  );
}

function Wallet({
  wallet,
  rechecking,
  removing,
  accounts,
  linking,
  onRecheck,
  onLinkAccount,
  onManual,
  onRemove,
}: {
  wallet: CardDetail[];
  rechecking: string | null;
  removing: boolean;
  accounts: PlaidAccount[];
  linking: string | null;
  onRecheck: (card: CardDetail) => void;
  onLinkAccount: (card: CardDetail, accountId: string) => void;
  onManual: (card: CardDetail) => void;
  onRemove: (card: CardDetail) => void;
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
                  : `${moneyIn(card.annualFee, card.characteristics?.currency)} a year`}
              </p>
            </div>
            <span className="wcard__parse">{PARSE_LABEL[card.parseStatus]}</span>
          </header>

          {card.rules.length > 0 ? (
            <ul className="rules">
              {card.rules.map((rule, index) => (
                <li key={rule.id ?? `legacy-rule-${index}`} className="rules__row">
                  <span className="rules__cat">{rule.categoryLabel}</span>
                  <span className="rules__rate num">{rule.rate}</span>
                  <span className="rules__cap num">
                    {rule.cap
                      ? `${moneyIn(rule.cap, card.characteristics?.currency)} ${rule.cycleLabel}`
                      : rule.cycleLabel}
                    {rule.mccCodes && rule.mccCodes.length > 0 && (
                      <span className="rules__mcc">
                        {" "}MCC {rule.mccCodes.slice(0, 4).join(", ")}
                        {rule.mccCodes.length > 4 && ` +${rule.mccCodes.length - 4}`}
                      </span>
                    )}
                  </span>
                  {/* The caveats that decide whether a headline rate is real. */}
                  {rule.restrictions && rule.restrictions.length > 0 && (
                    <span className="rules__limits">
                      {rule.restrictions.map((limit) => (
                        <span key={limit} className="limit">{limit}</span>
                      ))}
                    </span>
                  )}
                  {rule.hasRewardChoice && rule.alternativeRewards?.length ? (
                    <span className="rules__alt">
                      or {rule.alternativeRewards
                        .map((alt) => `${alt.rateValue}${alt.rateUnit === "percent" ? "%" : "×"} ${alt.rewardCurrency ?? alt.rewardType}`)
                        .join(", ")}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : (
            <p className="rules__empty">
              No rules extracted. This card is left out of every comparison.
            </p>
          )}

          {card.parseNote && <p className="wcard__note">{card.parseNote}</p>}

          {accounts.length > 0 && (
            <label className="field" style={{ marginTop: "1rem", maxWidth: "24rem" }}>
              <span className="field__label">Transactions paid with</span>
              <select
                className="field__input"
                value={card.accountId ?? ""}
                disabled={linking === (card.cardId ?? card.walletId)}
                onChange={(event) => onLinkAccount(card, event.target.value)}
              >
                <option value="">Choose a Plaid credit account</option>
                {accounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name || account.officialName || "Credit account"}
                    {account.mask ? ` ••${account.mask}` : ""}
                    {account.linkedCard && account.linkedCard !== card.name
                      ? ` — linked to ${account.linkedCard}`
                      : ""}
                  </option>
                ))}
              </select>
            </label>
          )}

          {card.unresolved && card.unresolved.length > 0 && (
            <details className="unresolved">
              <summary className="unresolved__toggle">
                {card.unresolved.length} thing{card.unresolved.length === 1 ? "" : "s"} the agent could not model
              </summary>
              <ul className="unresolved__list">
                {card.unresolved.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </details>
          )}

          <button
            type="button"
            className="btn btn--small btn--quiet"
            onClick={() => onRemove(card)}
            disabled={removing}
          >
            Remove card
          </button>

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
              disabled={rechecking === (card.cardId ?? card.walletId ?? card.last4)}
              onClick={() => onRecheck(card)}
            >
              {rechecking === (card.cardId ?? card.walletId ?? card.last4) ? "Rechecking…" : "Recheck now"}
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
  const [tab, setTab] = useState<"wallet" | "catalog" | "connections">("wallet");
  const [wallet, setWallet] = useState(initialWallet);
  const [adding, setAdding] = useState(false);
  const [manualFor, setManualFor] = useState<CardDetail | null>(null);
  const [rechecking, setRechecking] = useState<string | null>(null);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [accounts, setAccounts] = useState<PlaidAccount[]>([]);
  const [plaidItems, setPlaidItems] = useState<PlaidItem[]>([]);
  const [connectionsLoading, setConnectionsLoading] = useState(true);
  const [syncingItem, setSyncingItem] = useState<string | null>(null);
  const [disconnectingItem, setDisconnectingItem] = useState<string | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<string | null>(null);
  const [linkingId, setLinkingId] = useState<string | null>(null);
  const router = useRouter();

  const loadConnections = useCallback(async () => {
    const [nextItems, nextAccounts] = await Promise.all([
      api<PlaidItem[]>("/api/v1/plaid/items"),
      api<PlaidAccount[]>("/api/v1/plaid/accounts"),
    ]);
    setPlaidItems(nextItems);
    setAccounts(nextAccounts);
  }, []);

  useEffect(() => {
    let active = true;
    Promise.all([
      api<PlaidItem[]>("/api/v1/plaid/items"),
      api<PlaidAccount[]>("/api/v1/plaid/accounts"),
    ])
      .then(([nextItems, nextAccounts]) => {
        if (!active) return;
        setPlaidItems(nextItems);
        setAccounts(nextAccounts);
      })
      .catch(() => {
        if (active) setRequestError("Unable to load Plaid connections.");
      })
      .finally(() => {
        if (active) setConnectionsLoading(false);
      })
    return () => { active = false; };
  }, [loadConnections]);

  const creditAccounts = useMemo(() => accounts.filter((account) =>
    `${account.type ?? ""} ${account.subtype ?? ""}`.toLowerCase().includes("credit"),
  ), [accounts]);

  const visibleCatalog = useMemo(() => {
    const heldNames = new Set(wallet.map((card) => card.name.toLowerCase()));
    const rows = catalog.map((card) => ({
      ...card,
      held: heldNames.has(card.name.toLowerCase()),
    }));
    const catalogNames = new Set(rows.map((card) => card.name.toLowerCase()));

    for (const card of wallet) {
      if (catalogNames.has(card.name.toLowerCase())) continue;
      const headlineRate = card.rules
        .slice(0, 2)
        .map((rule) => `${rule.rate} ${rule.categoryLabel.toLowerCase()}`)
        .join(", ") || "Rules not yet readable";
      const tags = [
        ...card.rules.map((rule) => rule.categoryLabel.toLowerCase()),
        card.track,
        ...(card.annualFee === 0 ? ["no annual fee"] : []),
      ];
      rows.push({
        name: card.name,
        network: card.network,
        headlineRate,
        annualFee: card.annualFee,
        track: card.track,
        held: true,
        deltaVsWallet: 0,
        ...(card.parseNote ? { deltaNote: card.parseNote } : {}),
        tags: [...new Set(tags)],
      });
    }
    return rows;
  }, [catalog, wallet]);

  function openAdd() {
    setManualFor(null);
    setAdding(true);
    setTab("wallet");
  }

  async function recheck(card: CardDetail) {
    const cardId = card.cardId ?? card.walletId ?? card.id;
    if (!cardId) return;
    setRequestError(null);
    setRechecking(cardId);
    try {
      const response = await api<{ card: CardDetail; snapshot: Snapshot }>(
        `/api/v1/cards/${encodeURIComponent(cardId)}/recheck`,
        { method: "POST" },
      );
      setWallet(response.snapshot.wallet);
      router.refresh();
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "Unable to recheck that card.");
    } finally {
      setRechecking(null);
    }
  }

  async function removeCard(card: CardDetail) {
    const walletId = card.walletId ?? card.id ?? card.cardId;
    if (!walletId) {
      setRequestError("This card has no persisted ID. Reload the page and try again.");
      return;
    }
    if (!window.confirm(`Remove ${card.name} ••${card.last4} from your wallet?`)) return;
    setRequestError(null);
    const previous = wallet;
    setRemovingId(walletId);
    setWallet((list) =>
      list.filter((item) => (item.walletId ?? item.id ?? item.cardId) !== walletId),
    );
    try {
      const snapshot = await api<Snapshot>(
        `/api/v1/cards/${encodeURIComponent(walletId)}`,
        { method: "DELETE" },
      );
      setWallet(snapshot.wallet);
      router.refresh();
    } catch (error) {
      setWallet(previous);
      setRequestError(error instanceof Error ? error.message : "Unable to remove card.");
    } finally {
      setRemovingId(null);
    }
  }

  async function linkAccount(card: CardDetail, accountId: string) {
    const cardId = card.cardId ?? card.walletId ?? card.id;
    if (!cardId || !accountId) return;
    setRequestError(null);
    setLinkingId(cardId);
    try {
      const response = await api<{ card: CardDetail; snapshot: Snapshot }>(
        `/api/v1/cards/${encodeURIComponent(cardId)}/link-account`,
        { method: "POST", body: JSON.stringify({ accountId }) },
      );
      setWallet(response.snapshot.wallet);
      setAccounts((current) => current.map((account) => ({
        ...account,
        linkedCard: account.id === accountId ? card.name :
          account.linkedCard === card.name ? null : account.linkedCard,
      })));
      router.refresh();
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "Unable to link that account.");
    } finally {
      setLinkingId(null);
    }
  }

  async function syncItem(item: PlaidItem) {
    setRequestError(null);
    setConnectionStatus(null);
    setSyncingItem(item.itemId);
    try {
      const response = await api<{
        added: number;
        modified: number;
        removed: number;
        snapshot: Snapshot;
      }>("/api/v1/plaid/sync", {
        method: "POST",
        body: JSON.stringify({ userId, itemId: item.itemId }),
      });
      setWallet(response.snapshot.wallet);
      await loadConnections();
      setConnectionStatus(
        `Sync complete: ${response.added} added, ${response.modified} updated, ${response.removed} removed.`,
      );
      router.refresh();
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "Unable to sync that Plaid connection.");
    } finally {
      setSyncingItem(null);
    }
  }

  async function disconnectItem(item: PlaidItem) {
    const itemAccounts = accounts.filter((account) => account.itemId === item.itemId);
    const linkedCards = itemAccounts
      .map((account) => account.linkedCard)
      .filter((name): name is string => Boolean(name));
    const consequence = linkedCards.length
      ? ` This will unlink ${linkedCards.join(", ")} and remove this institution's transactions.`
      : " This will remove this institution's imported transactions.";
    if (!window.confirm(`Disconnect ${item.institutionName || "this Plaid institution"}?${consequence}`)) return;

    setRequestError(null);
    setConnectionStatus(null);
    setDisconnectingItem(item.itemId);
    try {
      const response = await api<{ transactionsRemoved: number; snapshot: Snapshot }>(
        `/api/v1/plaid/items/${encodeURIComponent(item.itemId)}`,
        { method: "DELETE" },
      );
      setWallet(response.snapshot.wallet);
      await loadConnections();
      setConnectionStatus(
        `Disconnected successfully. ${response.transactionsRemoved} transaction${response.transactionsRemoved === 1 ? "" : "s"} removed.`,
      );
      router.refresh();
    } catch (error) {
      setRequestError(error instanceof Error ? error.message : "Unable to disconnect that Plaid connection.");
    } finally {
      setDisconnectingItem(null);
    }
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
          <span className="tabs__count">{visibleCatalog.length}</span>
        </button>
        <button
          type="button"
          role="tab"
          className="tabs__tab"
          aria-selected={tab === "connections"}
          onClick={() => setTab("connections")}
        >
          Connections
          <span className="tabs__count">{plaidItems.length}</span>
        </button>

        {!showFlow && tab !== "connections" && (
          <button type="button" className="tabs__action" onClick={openAdd}>
            + Add a card
          </button>
        )}
      </div>

      {showFlow && (
        <AddCardFlow
          manualFor={manualFor ?? undefined}
          onSaved={(nextWallet) => {
            // Deliberately no router.refresh() here: refreshing remounts this
            // component and would throw away the review step before the user
            // has seen what the agent actually read.
            setWallet(nextWallet);
          }}
          onCancel={() => {
            setAdding(false);
            setManualFor(null);
            router.refresh();
          }}
        />
      )}

      {requestError && <p className="addcard__fine" role="alert">{requestError}</p>}
      {removingId && <p className="addcard__fine" role="status">Removing card…</p>}

      {tab === "wallet" ? (
        <Wallet
          wallet={wallet}
          rechecking={rechecking}
          removing={removingId !== null}
          accounts={creditAccounts}
          linking={linkingId}
          onRecheck={recheck}
          onLinkAccount={linkAccount}
          onManual={(card) => {
            setAdding(false);
            setManualFor(card);
          }}
          onRemove={removeCard}
        />
      ) : tab === "catalog" ? (
        <Catalog catalog={visibleCatalog} onAddRequest={openAdd} />
      ) : (
        <PlaidConnections
          items={plaidItems}
          accounts={accounts}
          loading={connectionsLoading}
          syncing={syncingItem}
          disconnecting={disconnectingItem}
          status={connectionStatus}
          onSync={syncItem}
          onDisconnect={disconnectItem}
        />
      )}
    </>
  );
}
