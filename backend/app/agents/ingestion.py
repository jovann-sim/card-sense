from __future__ import annotations

import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from ..plaid_taxonomy import classify, is_redirectable


def is_eligible_purchase(transaction: dict) -> bool:
    """A posted purchase that should contribute to spend and reward figures."""
    return transaction.get("isPurchase", True) is not False and not transaction.get("pending", False)


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

        amount = float(tx.get("amount") or 0)
        return {
            "id": tx.get("transaction_id"),
            "source": "plaid",
            "accountId": tx.get("account_id"),
            "date": tx.get("date") or tx.get("authorized_date"),
            "merchant": tx.get("merchant_name") or tx.get("name") or "Unknown",
            # Plaid uses positive values for outflows and negative values for
            # credits. Preserve the sign so a refund reduces spend instead of
            # becoming a second purchase.
            "amount": amount,
            "isRefund": amount < 0,
            "category": label,
            "mcc": mcc,
            "mccSource": "plaid" if stated_mcc else ("inferred" if inferred_mcc else None),
            "categorySource": primary or "uncategorized",
            "detailedCategory": detailed,
            # Money moving between your own accounts is not spending, and
            # counting it would inflate every reward figure downstream.
            "isPurchase": is_purchase,
            "categoryAmbiguous": mcc is None and is_purchase,
            # Earns nothing on a card today because the biller will not take
            # one, but a payment service could route it. Recorded now so the
            # optimiser can weigh the fee against the reward later.
            "isRedirectable": is_redirectable(label, is_purchase),
            "description": tx.get("name") or "",
            "pending": bool(tx.get("pending", False)),
            "currency": tx.get("iso_currency_code") or tx.get("unofficial_currency_code"),
            "paymentChannel": tx.get("payment_channel"),
            "location": tx.get("location") or {},
            "rawPlaid": tx,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }

    def summarise(
        self,
        transactions: list[dict],
        linked_account_ids: set[str] | None = None,
    ) -> dict:
        """What the run log reports, and what makes coverage gaps visible."""
        purchases = [t for t in transactions if is_eligible_purchase(t)]
        pending = [t for t in transactions if t.get("pending", False)]
        excluded = [
            t for t in transactions
            if t.get("isPurchase", True) is False and not t.get("pending", False)
        ]
        with_mcc = [t for t in purchases if t.get("mcc")]
        from_plaid = [t for t in purchases if t.get("mccSource") == "plaid"]
        if linked_account_ids is None:
            unmapped = [t for t in purchases if not t.get("accountId")]
        else:
            unmapped = [t for t in purchases if t.get("accountId") not in linked_account_ids]
        return {
            "total": len(transactions),
            "purchases": len(purchases),
            "excluded": len(excluded),
            "pending": len(pending),
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
        if summary["unlinkedToCard"]:
            notes.append(
                f"{summary['unlinkedToCard']} purchases belong to Plaid accounts that are not linked "
                "to a wallet card, so actual rewards cannot be attributed."
            )
        return notes

    def run(self, uid: str, store) -> dict:
        """Re-read what has been persisted and report on its quality.

        The Plaid sync endpoint owns fetching, because it owns the cursor. This
        keeps the agent responsible for the shape and the reporting, which is
        what the rest of the pipeline depends on.
        """
        transactions = store.get_subcollection(uid, "transactions")
        linked = {card["accountId"] for card in store.get_wallet(uid) if card.get("accountId")}
        return self.summarise(transactions, linked_account_ids=linked)

    # -- csv ---------------------------------------------------------------

    def import_csv_dir(self, uid: str, store, statement_dir: str) -> list[dict]:
        """Fallback ingestion for a bank with no Plaid coverage."""
        directory = Path(statement_dir)
        if not directory.exists():
            return []

        rows = []
        for path in directory.glob("*.csv"):
            with path.open(encoding="utf-8-sig", newline="") as handle:
                rows.extend(self.import_csv_records(uid, store, csv.DictReader(handle), path.name))
        return rows

    def import_csv_records(self, uid: str, store, records, filename: str) -> list[dict]:
        """Normalise uploaded CSV records through the same canonical shape."""
        rows = []
        for record in records:
            amount = self._amount(record)
            if amount <= 0:
                continue
            row = {
                "source": "csv",
                "source_file": filename,
                "amount": amount,
                "date": self._date(record),
                "category": self._text(record, ["category", "type", "group"], "Uncategorised"),
                "merchant": self._text(record, ["merchant", "payee", "name", "description"], "unknown"),
                "description": self._text(record, ["description", "memo", "details"], ""),
                "mcc": self._text(record, ["mcc", "merchant_category_code"], "") or None,
                "isPurchase": True,
                "pending": False,
            }
            key = f"{filename}:{row['date']}:{row['merchant']}:{row['amount']}"
            row["id"] = hashlib.sha256(key.encode()).hexdigest()
            store.set_subdoc(uid, "transactions", row["id"], row)
            rows.append(row)
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
