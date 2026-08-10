from __future__ import annotations

import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from ..plaid_taxonomy import classify


class IngestionAgent:
    """Turns raw transaction feeds into the shape every other agent reasons about.

    Deliberately deterministic. This is a fetch, a normalise and a group-by; a
    language model here would add latency and put non-determinism underneath
    every figure the dashboard shows.

    Its one real judgement is category: Plaid describes spending in its own
    taxonomy, card terms describe it in merchant category codes, and the join
    between them lives here.
    """

    id = "ingestion"

    # -- plaid -------------------------------------------------------------

    def normalise_plaid(self, tx: dict) -> dict:
        """One Plaid transaction, in our shape.

        MCC is taken from Plaid where it supplies one and inferred from the
        category where it does not — roughly two thirds of a sandbox pull carry
        a code, and a rule scoped to 5812 should still match the other third.
        """
        pfc = tx.get("personal_finance_category") or {}
        if not isinstance(pfc, dict):
            pfc = {}
        primary, detailed = pfc.get("primary"), pfc.get("detailed")

        inferred_mcc, label, is_purchase = classify(primary, detailed)
        stated_mcc = tx.get("merchant_category_code")
        mcc = str(stated_mcc) if stated_mcc else inferred_mcc

        return {
            "id": tx.get("transaction_id"),
            "source": "plaid",
            "accountId": tx.get("account_id"),
            "date": tx.get("date") or tx.get("authorized_date"),
            "merchant": tx.get("merchant_name") or tx.get("name") or "Unknown",
            "amount": abs(float(tx.get("amount") or 0)),
            "category": label,
            "mcc": mcc,
            "mccSource": "plaid" if stated_mcc else ("inferred" if inferred_mcc else None),
            "categorySource": primary or "uncategorized",
            "detailedCategory": detailed,
            # Money moving between your own accounts is not spending, and
            # counting it would inflate every reward figure downstream.
            "isPurchase": is_purchase,
            "categoryAmbiguous": mcc is None and is_purchase,
            "description": tx.get("name") or "",
            "pending": bool(tx.get("pending", False)),
            "currency": tx.get("iso_currency_code") or tx.get("unofficial_currency_code"),
            "paymentChannel": tx.get("payment_channel"),
            "location": tx.get("location") or {},
            "rawPlaid": tx,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }

    def summarise(self, transactions: list[dict]) -> dict:
        """What the run log reports, and what makes coverage gaps visible."""
        purchases = [t for t in transactions if t.get("isPurchase", True)]
        with_mcc = [t for t in purchases if t.get("mcc")]
        from_plaid = [t for t in purchases if t.get("mccSource") == "plaid"]
        unmapped = [t for t in purchases if not t.get("accountId")]
        return {
            "total": len(transactions),
            "purchases": len(purchases),
            "excluded": len(transactions) - len(purchases),
            "withMcc": len(with_mcc),
            "mccFromPlaid": len(from_plaid),
            "mccInferred": len(with_mcc) - len(from_plaid),
            "mccCoverage": round(len(with_mcc) / len(purchases), 3) if purchases else 0.0,
            "unlinkedToCard": len(unmapped),
            "accounts": sorted({t["accountId"] for t in purchases if t.get("accountId")}),
        }

    def degraded(self, summary: dict) -> list[str]:
        """Coverage problems worth surfacing rather than silently absorbing."""
        notes = []
        if summary["purchases"] and summary["mccCoverage"] < 0.9:
            missing = summary["purchases"] - summary["withMcc"]
            notes.append(
                f"{missing} of {summary['purchases']} purchases carry no merchant category code, "
                "so they can only be matched to card rules by category name."
            )
        return notes

    def run(self, uid: str, store) -> dict:
        """Re-read what has been persisted and report on its quality.

        The Plaid sync endpoint owns fetching, because it owns the cursor. This
        keeps the agent responsible for the shape and the reporting, which is
        what the rest of the pipeline depends on.
        """
        transactions = store.get_subcollection(uid, "transactions")
        return self.summarise(transactions)

    # -- csv ---------------------------------------------------------------

    def import_csv_dir(self, uid: str, store, statement_dir: str) -> list[dict]:
        """Fallback ingestion for a bank with no Plaid coverage."""
        directory = Path(statement_dir)
        if not directory.exists():
            return []

        rows = []
        for path in directory.glob("*.csv"):
            with path.open(encoding="utf-8-sig", newline="") as handle:
                for record in csv.DictReader(handle):
                    amount = self._amount(record)
                    if amount <= 0:
                        continue
                    rows.append({
                        "source": "csv",
                        "source_file": path.name,
                        "amount": amount,
                        "date": self._date(record),
                        "category": self._text(record, ["category", "type", "group"], "Uncategorised"),
                        "merchant": self._text(record, ["merchant", "payee", "name", "description"], "unknown"),
                        "description": self._text(record, ["description", "memo", "details"], ""),
                        "mcc": self._text(record, ["mcc", "merchant_category_code"], "") or None,
                        "isPurchase": True,
                    })

        for row in rows:
            # A statement row carries no upstream id, so a stable hash of its
            # identifying fields keeps re-imports idempotent.
            key = f"{row['source_file']}:{row['date']}:{row['merchant']}:{row['amount']}"
            store.set_subdoc(uid, "transactions", hashlib.sha256(key.encode()).hexdigest(), row)
        return rows

    def _amount(self, record):
        for key in ("amount", "transaction_amount", "debit", "withdrawal", "expense", "value"):
            if record.get(key):
                try:
                    return abs(float(str(record[key]).replace(",", "").replace("$", "")))
                except ValueError:
                    continue
        return 0.0

    def _date(self, record):
        for key in ("date", "posted_date", "transaction_date", "trans_date"):
            if record.get(key):
                return record[key]
        return None

    def _text(self, record, keys, default):
        for key in keys:
            if record.get(key):
                return str(record[key]).strip()
        return default
