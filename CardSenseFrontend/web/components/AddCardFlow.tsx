"use client";

import { useEffect, useState } from "react";
import type { CardDetail, ParsedRule } from "@/lib/types";

/** Paced for the camera, like the connect flow. Real reads take longer. */
const READ_MS = 1_200;

const READ_STEPS = [
  "Fetching the document",
  "Reading it with document understanding",
  "Matching rules to spending categories",
];

/** What a successful extraction looks like coming back from the agent. */
const EXTRACTED: ParsedRule[] = [
  { categoryLabel: "Dining", rate: "4% cash back", cap: null, cycleLabel: "no cap" },
  { categoryLabel: "Groceries", rate: "1% cash back", cap: null, cycleLabel: "no cap" },
  {
    categoryLabel: "Everything else",
    rate: "1% cash back",
    cap: null,
    cycleLabel: "no cap",
  },
];

const BLANK_RULE: ParsedRule = {
  categoryLabel: "",
  rate: "",
  cap: null,
  cycleLabel: "no cap",
};

type Phase = "form" | "reading" | "review" | "manual";

export function AddCardFlow({
  onAdd,
  onCancel,
  /** Starts straight in manual entry, for a card whose document never parsed. */
  manualFor,
}: {
  onAdd: (card: CardDetail) => void;
  onCancel: () => void;
  manualFor?: CardDetail;
}) {
  const [phase, setPhase] = useState<Phase>(manualFor ? "manual" : "form");
  const [step, setStep] = useState(0);

  const [name, setName] = useState(manualFor?.name ?? "");
  const [last4, setLast4] = useState(manualFor?.last4 ?? "");
  const [source, setSource] = useState(manualFor?.source.locator ?? "");
  const [rules, setRules] = useState<ParsedRule[]>(
    manualFor ? [BLANK_RULE] : EXTRACTED,
  );

  useEffect(() => {
    if (phase !== "reading") return;

    if (step >= READ_STEPS.length) {
      const t = setTimeout(() => setPhase("review"), 400);
      return () => clearTimeout(t);
    }

    const t = setTimeout(() => setStep((s) => s + 1), READ_MS);
    return () => clearTimeout(t);
  }, [phase, step]);

  function startRead(e: React.FormEvent) {
    e.preventDefault();
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setStep(READ_STEPS.length);
      setPhase("review");
      return;
    }
    setStep(0);
    setPhase("reading");
  }

  function updateRule(index: number, patch: Partial<ParsedRule>) {
    setRules((list) =>
      list.map((r, i) => (i === index ? { ...r, ...patch } : r)),
    );
  }

  function commit() {
    const usable = rules.filter(
      (r) => r.categoryLabel.trim() !== "" && r.rate.trim() !== "",
    );
    if (usable.length === 0) return;

    onAdd({
      name: name.trim() || "Untitled card",
      last4: last4.trim() || "0000",
      network: manualFor?.network ?? "Added by you",
      annualFee: manualFor?.annualFee ?? 0,
      track: manualFor?.track ?? "cashback",
      rules: usable,
      source: {
        label: phase === "manual" ? "Entered by you" : "Terms document you supplied",
        locator: source.trim() || "entered by hand",
        retrievedAt: new Date().toISOString().slice(0, 10),
      },
      recheckCadence: phase === "manual" ? "Not rechecked" : "Weekly",
      nextRecheckAt: new Date().toISOString().slice(0, 10),
      parseStatus: "parsed",
      parseNote:
        phase === "manual"
          ? "Rates entered by hand. The agent will not overwrite these until you point it at a document it can read."
          : undefined,
    });
  }

  return (
    <div className="addcard">
      {phase === "form" && (
        <form onSubmit={startRead}>
          <p className="addcard__title">Add a card</p>
          <p className="addcard__lede">
            Give the agent a link to the issuer&rsquo;s terms, or a PDF. It reads
            the rates itself and shows you what it found before anything is
            saved.
          </p>

          <div className="pform__grid">
            <label className="field">
              <span className="field__label">Card name</span>
              <input
                className="field__input"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Aurora Dining Card"
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

            <label className="field field--wide">
              <span className="field__label">Terms link or PDF</span>
              <input
                className="field__input"
                value={source}
                onChange={(e) => setSource(e.target.value)}
                placeholder="https://issuer.com/rates  ·  or  ·  terms.pdf"
                required
              />
            </label>
          </div>

          <p className="addcard__fine">
            Only the terms document is read. CardSense never asks for a card
            number.
          </p>

          <div className="pform__actions">
            <button type="submit" className="btn">
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
          <ol className="stages">
            {READ_STEPS.map((label, i) => {
              const state = i < step ? "done" : i === step ? "running" : "queued";
              return (
                <li key={label} className="stage" data-state={state}>
                  <span className="stage__dot" aria-hidden />
                  <span className="stage__name">{label}</span>
                  <span className="stage__status">
                    {state === "done"
                      ? "done"
                      : state === "running"
                        ? "working…"
                        : "queued"}
                  </span>
                </li>
              );
            })}
          </ol>
        </>
      )}

      {(phase === "review" || phase === "manual") && (
        <>
          <p className="addcard__title">
            {phase === "manual"
              ? `Enter the rates for ${manualFor?.name ?? name}`
              : `Found ${rules.length} rules — check them`}
          </p>
          <p className="addcard__lede">
            {phase === "manual"
              ? "The document could not be read, so these have to come from you. Copy them from your statement or the issuer's site."
              : "Extraction is not perfect. Correct anything that is wrong before it starts driving recommendations."}
          </p>

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
                  aria-label="Cap"
                  placeholder="no cap"
                  onChange={(e) =>
                    updateRule(i, {
                      cap: e.target.value === "" ? null : Number(e.target.value),
                      cycleLabel:
                        e.target.value === "" ? "no cap" : "per quarter",
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
            <button type="button" className="btn" onClick={commit}>
              {phase === "manual" ? "Save these rates" : "Looks right, add it"}
            </button>
            <button type="button" className="btn btn--quiet" onClick={onCancel}>
              Cancel
            </button>
          </div>

          {phase === "review" && (
            <button
              type="button"
              className="addcard__switch"
              onClick={() => setPhase("manual")}
            >
              It read this wrong — let me enter the rates myself
            </button>
          )}
        </>
      )}
    </div>
  );
}
