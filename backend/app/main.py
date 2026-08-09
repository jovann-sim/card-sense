from __future__ import annotations

from datetime import datetime, timezone
import csv
import io
import uuid

from fastapi import FastAPI, HTTPException, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .store import store
from .models import (
    PlannedItemIn,
    GoalIn,
    AdviceResolveIn,
    CardIn,
    RunIn,
    LinkTokenIn,
    ExchangeTokenIn,
    SyncIn,
)
from .orchestrator import Orchestrator
from .plaid_client import get_plaid_client

app = FastAPI(title="CardSense Backend", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
orch = Orchestrator(store)
UID = "demo-user"


def _uid(user_id: str | None = None) -> str:
    # Authentication is intentionally outside this hackathon backend.
    # Keep the current demo-user convention, while allowing Plaid records to
    # remain associated with the client_user_id supplied to Plaid Link.
    return user_id or UID


def _plaid_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=502, detail=f"Plaid request failed: {exc}")


def _normalise_plaid_transaction(tx: dict) -> dict:
    pfc = tx.get("personal_finance_category") or {}
    if isinstance(pfc, dict):
        category = pfc.get("primary") or "uncategorized"
        detailed_category = pfc.get("detailed")
    else:
        category = "uncategorized"
        detailed_category = None

    return {
        "id": tx.get("transaction_id"),
        "source": "plaid",
        "accountId": tx.get("account_id"),
        "date": tx.get("date") or tx.get("authorized_date"),
        "merchant": tx.get("merchant_name") or tx.get("name") or "Unknown",
        "amount": abs(float(tx.get("amount") or 0)),
        "category": category,
        "detailedCategory": detailed_category,
        "description": tx.get("name") or "",
        "pending": bool(tx.get("pending", False)),
        "currency": tx.get("iso_currency_code") or tx.get("unofficial_currency_code"),
        "paymentChannel": tx.get("payment_channel"),
        "location": tx.get("location") or {},
        "rawPlaid": tx,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


def _rebuild_ingestion_from_store(uid: str) -> list[dict]:
    """Keep the existing agent contract: ingestion.transactions is the source read by Orchestrator."""
    transactions = store.get_subcollection(uid, "transactions")
    transactions.sort(key=lambda x: (x.get("date") or "", x.get("id") or ""))
    store.set_user(uid, {"ingestion": {"transactions": transactions}})
    return transactions


@app.get("/health")
def health():
    return {
        "status": "ok",
        "demoMode": settings.demo_mode,
        "model": settings.finance_agent_model,
        "plaidEnv": settings.plaid_env if not settings.demo_mode else "demo",
    }


@app.get("/api/v1/snapshot")
def snapshot():
    snap = store.get_snapshot(UID)
    if not snap:
        _, snap = orch.run(UID)
    return snap


@app.post("/api/v1/runs")
def run_agents(body: RunIn):
    run_id, snap = orch.run(UID, body.request)
    return {"runId": run_id, "snapshot": snap}


@app.get("/api/v1/runs/{run_id}")
def run_status(run_id: str):
    data = store.get_subcollection(UID, "agent_runs")
    row = next((x for x in data if x.get("id") == run_id), None)
    if not row:
        raise HTTPException(404, "Run not found")
    return row


@app.post("/api/v1/planned")
def add_planned(body: PlannedItemIn):
    item = {"id": uuid.uuid4().hex, **body.model_dump(mode="json")}
    store.add_subdoc(UID, "planned", item, item["id"])
    user = store.get_user(UID)
    planned = user.get("planned", [])
    planned.append(item)
    store.set_user(UID, {"planned": planned})
    _, snap = orch.run(UID, "Recalculate after planned spending change")
    return snap


@app.delete("/api/v1/planned/{planned_id}")
def delete_planned(planned_id: str):
    store.delete_subdoc(UID, "planned", planned_id)
    user = store.get_user(UID)
    store.set_user(UID, {"planned": [x for x in user.get("planned", []) if x.get("id") != planned_id]})
    _, snap = orch.run(UID, "Recalculate after planned spending removal")
    return snap


@app.post("/api/v1/goals")
def set_goal(body: GoalIn):
    goal = body.model_dump(mode="json")
    store.set_user(UID, {"goal": goal})
    _, snap = orch.run(UID, "Recalculate after goal change")
    return snap


@app.post("/api/v1/advice/{advice_id}/resolve")
def resolve_advice(advice_id: str, body: AdviceResolveIn):
    user = store.get_user(UID)
    records = user.get("trackRecord", {}).get("records", [])
    found = False
    for r in records:
        if r.get("id") == advice_id:
            r.update({"outcome": body.outcome, "resolvedAt": datetime.now(timezone.utc).isoformat()})
            found = True
    if not found:
        raise HTTPException(404, "Advice not found")
    tr = user.get("trackRecord", {})
    tr["records"] = records
    store.set_user(UID, {"trackRecord": tr})
    _, snap = orch.run(UID, "Recalculate after advice resolution")
    return snap


@app.post("/api/v1/cards")
def add_card(body: CardIn):
    card = body.model_dump(mode="json")
    parsed = {"rules": card.get("rules") or [], "status": "parsed" if card.get("rules") else "failed", "note": None}
    if not parsed["rules"]:
        parsed = orch.cardintel.parse(card)
    wallet = store.get_user(UID).get("wallet", [])
    card_detail = {
        "name": card["name"],
        "last4": card["last4"],
        "network": card["network"],
        "annualFee": card["annualFee"],
        "track": card["track"],
        "rules": parsed.get("rules", []),
        "source": {
            "label": "User supplied terms",
            "locator": card.get("termsUrl") or "uploaded terms",
            "retrievedAt": datetime.now(timezone.utc).date().isoformat(),
        },
        "recheckCadence": "weekly",
        "nextRecheckAt": str(datetime.now(timezone.utc).date()),
        "parseStatus": parsed.get("status", "failed"),
        "parseNote": parsed.get("note"),
    }
    wallet = [x for x in wallet if x.get("name") != card["name"]] + [card_detail]
    rule_map = store.get_user(UID).get("card_rules", {})
    rule_map[card["name"]] = parsed.get("rules", [])
    store.set_user(UID, {"wallet": wallet, "card_rules": rule_map})
    _, snap = orch.run(UID, "Recalculate after card added")
    return {"card": card_detail, "snapshot": snap}


@app.get("/api/v1/cards")
def cards():
    return store.get_user(UID).get("wallet", [])


@app.post("/api/v1/plaid/link-token")
def plaid_link_token(body: LinkTokenIn):
    if settings.demo_mode:
        return {"demo": True, "link_token": "demo-link-token"}

    try:
        from plaid.model.link_token_create_request import LinkTokenCreateRequest
        from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
        from plaid.model.products import Products
        from plaid.model.country_code import CountryCode

        client = get_plaid_client()
        country_codes = [CountryCode(code.strip()) for code in settings.plaid_country_codes.split(",") if code.strip()]
        request = LinkTokenCreateRequest(
            user=LinkTokenCreateRequestUser(client_user_id=body.userId),
            client_name="CardSense",
            products=[Products("transactions")],
            country_codes=country_codes,
            language="en",
        )
        response = client.link_token_create(request)
        return response.to_dict()
    except Exception as exc:
        raise _plaid_error(exc)


@app.post("/api/v1/plaid/exchange-token")
def plaid_exchange(body: ExchangeTokenIn):
    if settings.demo_mode:
        return {"ok": True, "demo": True, "message": "Demo mode: no Plaid token stored."}

    try:
        from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest

        client = get_plaid_client()
        response = client.item_public_token_exchange(
            ItemPublicTokenExchangeRequest(public_token=body.publicToken)
        )
        data = response.to_dict()
        item_id = data["item_id"]
        access_token = data["access_token"]
        uid = _uid(body.userId)

        # access_token is a server credential. It is persisted but NEVER returned to the browser.
        store.set_subdoc(
            uid,
            "plaid_items",
            item_id,
            {
                "itemId": item_id,
                "accessToken": access_token,
                "cursor": None,
                "createdAt": datetime.now(timezone.utc).isoformat(),
            },
        )

        return {"ok": True, "itemId": item_id}
    except Exception as exc:
        raise _plaid_error(exc)


@app.post("/api/v1/plaid/sync")
def plaid_sync(body: SyncIn):
    if settings.demo_mode:
        return {"ok": True, "demo": True, "message": "Demo mode: use CSV ingestion or seeded transactions."}

    uid = _uid(body.userId)
    item_id = body.itemId

    try:
        # If the frontend omits itemId, sync all Plaid Items connected to this user.
        items = [store.get_subdoc(uid, "plaid_items", item_id)] if item_id else store.get_subcollection(uid, "plaid_items")
        items = [x for x in items if x]
        if not items:
            raise HTTPException(404, "No Plaid Item connected for this user")

        from plaid.model.transactions_sync_request import TransactionsSyncRequest

        client = get_plaid_client()
        totals = {"added": 0, "modified": 0, "removed": 0}
        cursors = []

        for item in items:
            current_cursor = body.cursor if body.cursor is not None else item.get("cursor")
            has_more = True
            item_added = item_modified = item_removed = 0

            while has_more:
                request = TransactionsSyncRequest(
                    access_token=item["accessToken"],
                    cursor=current_cursor,
                )
                response = client.transactions_sync(request)
                data = response.to_dict()

                for tx in data.get("added", []):
                    tx_id = tx.get("transaction_id")
                    if not tx_id:
                        continue
                    store.set_subdoc(uid, "transactions", tx_id, _normalise_plaid_transaction(tx))
                    item_added += 1

                for tx in data.get("modified", []):
                    tx_id = tx.get("transaction_id")
                    if not tx_id:
                        continue
                    store.set_subdoc(uid, "transactions", tx_id, _normalise_plaid_transaction(tx))
                    item_modified += 1

                for tx in data.get("removed", []):
                    tx_id = tx.get("transaction_id")
                    if tx_id:
                        store.delete_subdoc(uid, "transactions", tx_id)
                        item_removed += 1

                current_cursor = data.get("next_cursor") or current_cursor
                has_more = bool(data.get("has_more", False))

            store.set_subdoc(
                uid,
                "plaid_items",
                item["id"],
                {
                    "cursor": current_cursor,
                    "lastSyncedAt": datetime.now(timezone.utc).isoformat(),
                },
            )
            cursors.append({"itemId": item["id"], "cursor": current_cursor})
            totals["added"] += item_added
            totals["modified"] += item_modified
            totals["removed"] += item_removed

        transactions = _rebuild_ingestion_from_store(uid)
        run_id, snap = orch.run(uid, "Analyse newly synced Plaid transactions")

        return {
            "ok": True,
            **totals,
            "transactionCount": len(transactions),
            "items": cursors,
            "runId": run_id,
            "snapshot": snap,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise _plaid_error(exc)


@app.post("/api/v1/scheduler/run")
def scheduled_run(x_internal_secret: str | None = Header(default=None)):
    if x_internal_secret != settings.internal_run_secret:
        raise HTTPException(401, "Unauthorized")
    run_id, snap = orch.run(UID, "Scheduled autonomous CardSense run")
    return {"runId": run_id, "generatedAt": snap["generatedAt"]}


@app.post("/api/v1/import/csv")
async def import_csv(file: UploadFile = File(...)):
    content = (await file.read()).decode("utf-8-sig")
    rows = []
    for r in csv.DictReader(io.StringIO(content)):
        amount = 0
        for key in ["amount", "transaction_amount", "debit", "withdrawal", "expense", "value"]:
            if r.get(key):
                try:
                    amount = abs(float(str(r[key]).replace(",", "").replace("$", "")))
                    break
                except Exception:
                    pass
        if amount > 0:
            rows.append({
                "source_file": file.filename,
                "source": "csv",
                "amount": amount,
                "date": r.get("date") or r.get("posted_date"),
                "category": r.get("category") or r.get("type") or "uncategorized",
                "merchant": r.get("merchant") or r.get("payee") or r.get("name") or "unknown",
                "description": r.get("description") or "",
            })

    store.set_user(UID, {"ingestion": {"transactions": rows}})
    run_id, snap = orch.run(UID, "Analyse imported bank statement")
    return {"imported": len(rows), "runId": run_id, "snapshot": snap}
