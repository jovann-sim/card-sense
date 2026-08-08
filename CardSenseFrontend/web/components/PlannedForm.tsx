"use client";

import { useState } from "react";
import type { PlannedItem, PlannedKind } from "@/lib/types";

export const CATEGORIES = [
  "Dining & restaurants",
  "Groceries",
  "Air travel",
  "Online retail",
  "Transit & rideshare",
  "Streaming & digital",
  "Fuel",
  "Utilities & bills",
];

/**
 * Declaring something the agent could not have inferred. Kept deliberately
 * short — four fields — because anything longer stops being worth the user's
 * time for a forecast they are only estimating anyway.
 */
export function PlannedForm({
  onAdd,
  onCancel,
  defaultDate,
}: {
  onAdd: (item: PlannedItem) => void;
  onCancel: () => void;
  defaultDate: string;
}) {
  const [kind, setKind] = useState<PlannedKind>("event");
  const [label, setLabel] = useState("");
  const [startDate, setStartDate] = useState(defaultDate);
  const [endDate, setEndDate] = useState("");
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState(CATEGORIES[0]);

  const amountValue = Number(amount);
  const valid = label.trim() !== "" && amountValue > 0 && startDate !== "";

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!valid) return;

    onAdd({
      id: `plan-${Date.now()}`,
      kind,
      label: label.trim(),
      startDate,
      endDate: kind === "event" && endDate ? endDate : undefined,
      amount: amountValue,
      categories: [category],
    });
  }

  return (
    <form className="pform" onSubmit={submit}>
      <div className="pform__kinds" role="group" aria-label="What kind of spending">
        <button
          type="button"
          className="chip"
          aria-pressed={kind === "event"}
          onClick={() => setKind("event")}
        >
          A trip or event
        </button>
        <button
          type="button"
          className="chip"
          aria-pressed={kind === "purchase"}
          onClick={() => setKind("purchase")}
        >
          A big purchase
        </button>
      </div>

      <div className="pform__grid">
        <label className="field">
          <span className="field__label">What</span>
          <input
            className="field__input"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder={kind === "event" ? "Tokyo trip" : "Replacement laptop"}
            required
          />
        </label>

        <label className="field">
          <span className="field__label">
            {kind === "event" ? "Starts" : "When"}
          </span>
          <input
            className="field__input"
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            required
          />
        </label>

        {kind === "event" && (
          <label className="field">
            <span className="field__label">Ends</span>
            <input
              className="field__input"
              type="date"
              value={endDate}
              min={startDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </label>
        )}

        <label className="field">
          <span className="field__label">Roughly how much</span>
          <input
            className="field__input"
            type="number"
            inputMode="decimal"
            min="1"
            step="1"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="2400"
            required
          />
        </label>

        <label className="field">
          <span className="field__label">Mostly spent on</span>
          <select
            className="field__input"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
      </div>

      <p className="pform__hint">
        An estimate is enough. The forecast agent treats this as a range, not a
        commitment.
      </p>

      <div className="pform__actions">
        <button type="submit" className="btn" disabled={!valid}>
          Add to forecast
        </button>
        <button type="button" className="btn btn--quiet" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
