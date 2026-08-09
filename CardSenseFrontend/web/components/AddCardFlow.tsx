"use client";

import { useState } from "react";
import { api } from "@/lib/client-api";
import type { CardDetail, ParsedRule } from "@/lib/types";

const BLANK_RULE: ParsedRule = {
  categoryLabel: "",
  rate: "",
  cap: null,
  cycleLabel: "no cap",
};

type Phase = "form" | "reading" | "review" | "manual";

type CardResponse = { card: CardDetail; snapshot: { wallet: CardDetail[] } };

/** Extra fields the card intelligence agent returns alongside the rules. */
type Extraction = CardDetail & {
  parseConfidence?: number;
  failureReason?: string | null;
  characteristics?: Record<string, number | string>;
  termsUrl?: string | null;
};

const FAILURE_HINT: Record<string, string> = {
  fetch_failed: "Check the link opens in a browser, or paste the terms text instead.",
  rate_limited: "The issuer is refusing automated requests. Try the PDF, or paste the text.",
  unsupported_content: "That link is not a terms document.",
  no_rules_found:
    "The page carried no reward rates — most issuer pages load them with JavaScript. Use the terms PDF, or enter the rates yourself.",
  low_confidence: "The rates were too ambiguous to trust. Enter them yourself below.",
  model_unavailable: "The reader is unavailable right now. Try again, or enter the rates yourself.",
  no_source: "Give the agent a terms link, or enter the rates yourself.",
};

export function AddCardFlow({
  onSaved,
  onCancel,
  /** Starts straight in manual entry, for a card whose document never parsed. */
  manualFor,
}: {
  onSaved: (wallet: CardDetail[]) => void;
  onCancel: () => void;
  manualFor?: Extraction;
}) {
  const [phase, setPhase] = useState<Phase>(manualFor ? "manual" : "form");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Extraction | null>(null);

  const [name, setName] = useState(manualFor?.name ?? "");
  const [last4, setLast4] = useState(manualFor?.last4 ?? "");
  const [source, setSource] = useState(manualFor?.termsUrl ?? "");
  const [network, setNetwork] = useState(manualFor?.network ?? "Visa");
  const [track, setTrack] = useState<string>(manualFor?.track ?? "cashback");
  const [rules, setRules] = useState<ParsedRule[]>(manualFor ? [BLANK_RULE] : []);

  const payload = () => ({
    name: name.trim() || "Untitled card",
    last4: last4.trim() || "0000",
    network,
    annualFee: manualFor?.annualFee ?? 0,
    track,
    termsUrl: source.trim() || null,
  });

  /** Hand the link to the agent and show back whatever it actually read. */
  async function readTerms(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setPhase("reading");
    try {
      const response = await api<CardResponse>("/api/v1/cards", {
        method: "POST",
        body: JSON.stringify(payload()),
      });
      const card = response.card as Extraction;
      setResult(card);
      setRules(card.rules?.length ? card.rules : [BLANK_RULE]);
      onSaved(response.snapshot.wallet);
      setPhase(card.parseStatus === "parsed" ? "review" : "manual");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reach the reader.");
      setPhase("form");
    } finally {
      setBusy(false);
    }
  }

  /** Rates the user typed or corrected are authoritative and overwrite the read. */
  async function saveCorrected() {
    const usable = rules.filter((r) => r.categoryLabel.trim() && String(r.rate).trim());
    if (!usable.length) return;
    setBusy(true);
    setError(null);
    try {
      const response = await api<CardResponse>("/api/v1/cards", {
        method: "POST",
        body: JSON.stringify({ ...payload(), rules: usable }),
      });
      onSaved(response.snapshot.wallet);
      onCancel();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save those rates.");
    } finally {
      setBusy(false);
    }
  }

  function updateRule(index: number, patch: Partial<ParsedRule>) {
    setRules((list) => list.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  return (
    <div className="addcard">
      {error && (
        <p className="addcard__fine" role="alert" style={{ color: "var(--ember)" }}>
          {error}
        </p>
      )}

      {phase === "form" && (
        <form onSubmit={readTerms}>
          <p className="addcard__title">Add a card</p>
          <p className="addcard__lede">
            Give the agent a link to the issuer&rsquo;s terms, or a PDF. It reads
            the rates itself and shows you what it found before they drive
            anything.
          </p>

          <div className="pform__grid">
            <label className="field">
              <span className="field__label">Card name</span>
              <input
                className="field__input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="HSBC Revolution"
                required
              />
            </label>

            <label className="field">
              <span className="field__label">Last 4 digits</span>
              <input
                className="field__input"
                value={last4}
                onChange={(e) => setLast4(e.target.value.replace(/\D/g, "").slice(0, 4))}
                placeholder="0000"
                inputMode="numeric"
              />
            </label>

            <label className="field">
              <span className="field__label">Network</span>
              <select
                className="field__input"
                value={network}
                onChange={(e) => setNetwork(e.target.value)}
              >
                {["Visa", "Mastercard", "Amex", "UnionPay", "JCB"].map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </label>

            <label className="field">
              <span className="field__label">Earns</span>
              <select
                className="field__input"
                value={track}
                onChange={(e) => setTrack(e.target.value)}
              >
                <option value="cashback">Cash back</option>
                <option value="miles">Air miles</option>
                <option value="points">Points</option>
              </select>
            </label>

            <label className="field field--wide">
              <span className="field__label">Terms link or PDF</span>
              <input
                className="field__input"
                value={source}
                onChange={(e) => setSource(e.target.value)}
                placeholder="https://issuer.com/terms.pdf"
                required
              />
            </label>
          </div>

          <p className="addcard__fine">
            Only the terms document is read. CardSense never asks for a card
            number.
          </p>

          <div className="pform__actions">
            <button type="submit" className="btn" disabled={busy}>
              Read the terms
            </button>
            <button type="button" className="btn btn--quiet" onClick={onCancel}>
              Cancel
            </button>
          </div>
        </form>
      )}

      {phase === "reading" && (
        <>
          <p className="addcard__title">Reading {name || "the document"}</p>
          <p className="addcard__lede">
            Fetching the document and extracting its reward rules. A PDF takes a
            little longer than a page.
          </p>
          <ol className="stages">
            <li className="stage" data-state="running">
              <span className="stage__dot" aria-hidden />
              <span className="stage__name">Card intelligence agent</span>
              <span className="stage__status">working…</span>
            </li>
          </ol>
        </>
      )}

      {(phase === "review" || phase === "manual") && (
        <>
          <p className="addcard__title">
            {phase === "manual"
              ? `Enter the rates for ${name || manualFor?.name || "this card"}`
              : `Found ${rules.length} rule${rules.length === 1 ? "" : "s"} — check them`}
          </p>
          <p className="addcard__lede">
            {phase === "manual"
              ? result?.failureReason
                ? `${result.parseNote ?? ""} ${FAILURE_HINT[result.failureReason] ?? ""}`.trim()
                : "The document could not be read, so these have to come from you."
              : "Extraction is not perfect. Correct anything wrong before it starts driving recommendations."}
          </p>

          {phase === "review" && result?.parseConfidence !== undefined && (
            <p className="addcard__fine">
              Read from {result.source?.label?.toLowerCase()} ·{" "}
              {Math.round((result.parseConfidence ?? 0) * 100)}% confidence · rechecks{" "}
              {result.recheckCadence}
            </p>
          )}

          {phase === "review" && result?.characteristics && Object.keys(result.characteristics).length > 0 && (
            <dl className="prov">
              {Object.entries(result.characteristics).map(([key, value]) => (
                <div className="prov__pair" key={key}>
                  <dt>{key.replace(/([A-Z])/g, " $1").toLowerCase()}</dt>
                  <dd className="num">{String(value)}</dd>
                </div>
              ))}
            </dl>
          )}

          <ul className="ruleedit">
            {rules.map((rule, i) => (
              <li key={i} className="ruleedit__row">
                <input
                  className="field__input"
                  value={rule.categoryLabel}
                  aria-label="Category"
                  placeholder="Dining"
                  onChange={(e) => updateRule(i, { categoryLabel: e.target.value })}
                />
                <input
                  className="field__input"
                  value={rule.rate}
                  aria-label="Rate"
                  placeholder="4% cash back"
                  onChange={(e) => updateRule(i, { rate: e.target.value })}
                />
                <input
                  className="field__input"
                  type="number"
                  min="0"
                  value={rule.cap ?? ""}
                  aria-label="Spend cap"
                  placeholder="no cap"
                  onChange={(e) =>
                    updateRule(i, {
                      cap: e.target.value === "" ? null : Number(e.target.value),
                      cycleLabel: e.target.value === "" ? "no cap" : "per month",
                    })
                  }
                />
                <button
                  type="button"
                  className="ruleedit__remove"
                  aria-label={`Remove ${rule.categoryLabel || "rule"}`}
                  onClick={() => setRules((l) => l.filter((_, j) => j !== i))}
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>

          <button
            type="button"
            className="btn btn--quiet btn--small"
            onClick={() => setRules((l) => [...l, { ...BLANK_RULE }])}
          >
            Add a rule
          </button>

          <div className="pform__actions">
            {phase === "review" && (
              <button type="button" className="btn" onClick={onCancel} disabled={busy}>
                Looks right, keep it
              </button>
            )}
            <button
              type="button"
              className={phase === "review" ? "btn btn--quiet" : "btn"}
              onClick={saveCorrected}
              disabled={busy}
            >
              {phase === "manual" ? "Save these rates" : "Save my corrections"}
            </button>
            <button type="button" className="btn btn--quiet" onClick={onCancel}>
              Cancel
            </button>
          </div>
        </>
      )}
    </div>
  );
}
