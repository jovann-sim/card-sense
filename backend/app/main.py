from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import csv
import io
import re
import uuid
import logging
from time import perf_counter

from fastapi import BackgroundTasks, FastAPI, HTTPException, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from .agents.terms import document_from_upload
from .agents.card_intelligence import with_rule_ids
from .valuations import BASE_CURRENCY
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
    Snapshot,
    RunResponse,
    CardResponse,
)
from .orchestrator import AGENTS, Orchestrator, READ_MODEL_VERSION, project_catalog
from .plaid_client import get_plaid_client

app = FastAPI(title="CardSense Backend", version="0.2.0")
logger = logging.getLogger("cardsense")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in settings.cors_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
orch = Orchestrator(store)
UID = "demo-user"

# The durable production version may override these with global mcc_map docs;
# this small explicit baseline keeps Plaid's taxonomy out of reward matching.
PLAID_CATEGORY_MAP = {
    "FOOD_AND_DRINK": "Dining & restaurants", "GROCERIES": "Groceries",
    "TRAVEL": "Air travel", "TRANSPORTATION": "Transit & rideshare",
    "GAS_STATIONS": "Fuel", "ENTERTAINMENT": "Streaming & digital",
    "GENERAL_MERCHANDISE": "Online retail", "HOME_IMPROVEMENT": "Online retail",
    "RENT_AND_UTILITIES": "Utilities & bills",
}


def _uid(user_id: str | None = None) -> str:
    # Authentication is intentionally outside this hackathon backend.
    # Keep the current demo-user convention, while allowing Plaid records to
    # remain associated with the client_user_id supplied to Plaid Link.
    return user_id or UID


def _plaid_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=502, detail=f"Plaid request failed: {exc}")


def _plaid_transactions_sync_request(access_token: str, cursor: str | None):
    """Plaid requires an absent initial cursor, not an explicit null value."""
    from plaid.model.transactions_sync_request import TransactionsSyncRequest

    values = {"access_token": access_token}
    if cursor is not None:
        values["cursor"] = cursor
    return TransactionsSyncRequest(**values)


@app.on_event("startup")
def validate_runtime_configuration():
    errors = settings.real_mode_errors()
    if errors:
        raise RuntimeError("CardSense configuration error: " + "; ".join(errors))
    if not settings.demo_mode:
        try:
            import google.auth
            google.auth.default()
            store.connect()
        except Exception as exc:
            raise RuntimeError(
                "CardSense requires Application Default Credentials when DEMO_MODE=false. "
                "Run `gcloud auth application-default login` locally."
            ) from exc


def _firestore_safe_plaid_value(value):
    """Convert Plaid SDK values that Firestore cannot encode recursively."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _firestore_safe_plaid_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_firestore_safe_plaid_value(item) for item in value]
    return value


def _normalise_plaid_transaction(tx: dict) -> dict:
    """Delegates to the ingestion agent, which owns the transaction shape."""
    return _firestore_safe_plaid_value(orch.ingestion.normalise_plaid(tx))


def _store_plaid_accounts(uid: str, client, access_token: str, item_id: str) -> list[dict]:
    """Persist the accounts behind a Plaid Item so cards can be linked to them."""
    from plaid.model.accounts_get_request import AccountsGetRequest

    accounts = client.accounts_get(AccountsGetRequest(access_token=access_token)).to_dict()["accounts"]
    stored = []
    for account in accounts:
        record = _firestore_safe_plaid_value({
            "id": account["account_id"],
            "itemId": item_id,
            "mask": account.get("mask"),
            "name": account.get("name"),
            "officialName": account.get("official_name"),
            "type": str(account.get("type") or ""),
            "subtype": str(account.get("subtype") or ""),
        })
        store.set_subdoc(uid, "plaid_accounts", account["account_id"], record)
        stored.append(record)
    return stored


def link_accounts_to_cards(uid: str) -> list[dict]:
    """Attach Plaid accounts to wallet cards by matching the last four digits.

    Without this, strategy cannot attribute any transaction to a card, so every
    category reports zero captured reward and flags itself unverified. Plaid
    exposes the account mask, which is exactly the last4 the user typed when
    adding the card, so the common case needs no interaction at all.
    """
    accounts = store.get_subcollection(uid, "plaid_accounts")
    linked = []
    claimed = {card["accountId"] for card in store.get_wallet(uid) if card.get("accountId")}
    for card in store.get_wallet(uid):
        if card.get("accountId"):
            continue
        matches = [
            account for account in accounts
            if account.get("mask") and card.get("last4")
            and str(account["mask"]) == str(card["last4"])
            and "credit" in f"{account.get('type')} {account.get('subtype')}".lower()
            and account["id"] not in claimed
        ]
        # A guessed link is worse than asking. Only automate a unique match.
        if len(matches) != 1:
            continue
        match = matches[0]
        store.set_subdoc(uid, "wallet", card["cardId"], {"accountId": match["id"]})
        claimed.add(match["id"])
        linked.append({"cardId": card["cardId"], "accountId": match["id"], "mask": match["mask"]})
    return linked


def _remove_plaid_item_remote(item: dict) -> bool:
    """Revoke one Plaid Item when credentials are available."""
    if not settings.use_plaid:
        return False
    from plaid.model.item_remove_request import ItemRemoveRequest

    client = get_plaid_client()
    client.item_remove(ItemRemoveRequest(access_token=item["accessToken"]))
    return True


def _delete_plaid_item_data(uid: str, item: dict) -> dict:
    """Remove one Item's local accounts, transactions and wallet links."""
    item_id = item.get("id") or item.get("itemId")
    accounts = [
        account for account in store.get_subcollection(uid, "plaid_accounts")
        if account.get("itemId") == item_id
    ]
    account_ids = {account["id"] for account in accounts}
    transactions = [
        transaction for transaction in store.get_subcollection(uid, "transactions")
        if transaction.get("source") == "plaid" and transaction.get("accountId") in account_ids
    ]
    advice = store.get_subcollection(uid, "advice")
    upserts = [
        ("wallet", card["cardId"], {"accountId": None})
        for card in store.get_wallet(uid)
        if card.get("accountId") in account_ids
    ]
    deletes = [
        ("plaid_accounts", account["id"])
        for account in accounts
    ] + [
        ("transactions", transaction["id"])
        for transaction in transactions
    ] + [
        ("advice", recommendation["id"])
        for recommendation in advice
    ] + [("plaid_items", item_id)]
    store.apply_subdoc_changes(uid, upserts=upserts, deletes=deletes)
    return {
        "accountsRemoved": len(accounts),
        "transactionsRemoved": len(transactions),
        "cardsUnlinked": len(upserts),
        "adviceCleared": len(advice),
    }


def _rebuild_ingestion_from_store(uid: str) -> list[dict]:
    """Transactions are authoritative in their subcollection; never mirror them on users/{uid}."""
    transactions = store.get_subcollection(uid, "transactions")
    transactions.sort(key=lambda x: (x.get("date") or "", x.get("id") or ""))
    return transactions


def _same_wallet_card(left: dict, right: dict) -> bool:
    """Match a snapshot card to its authoritative wallet document."""
    if left.get("accountId") and right.get("accountId"):
        return left["accountId"] == right["accountId"]
    return bool(
        left.get("name")
        and left.get("last4")
        and left.get("name") == right.get("name")
        and left.get("last4") == right.get("last4")
    )


def _normalise_snapshot_wallet(snapshot: dict, uid: str = UID) -> dict:
    """Attach authoritative wallet document IDs to older persisted snapshots."""
    wallet = snapshot.get("wallet")
    if isinstance(wallet, list):
        persisted_wallet = store.get_wallet(uid)
        snapshot["wallet"] = [
            {
                **card,
                "walletId": next(
                    (
                        persisted.get("walletId")
                        for persisted in persisted_wallet
                        if persisted.get("cardId") == card.get("cardId")
                        or _same_wallet_card(persisted, card)
                    ),
                    card.get("walletId") or card.get("id") or card.get("cardId"),
                ),
                "cardId": card.get("cardId") or card.get("id"),
            }
            for card in wallet
            if card.get("cardId") or card.get("id")
        ]
        # Refresh this derived view too, so snapshots persisted by an older
        # release immediately show user-added cards after deployment.
        snapshot["catalog"] = project_catalog(store, uid, persisted_wallet)
        snapshot["readModelVersion"] = READ_MODEL_VERSION
    return snapshot


@app.get("/health")
def health():
    return {
        "status": "ok",
        "demoMode": settings.demo_mode,
        "model": settings.finance_agent_model,
        "plaidEnv": settings.plaid_env if settings.use_plaid else "not configured",
        "realModeErrors": settings.real_mode_errors(),
    }


@app.get("/api/v1/snapshot", response_model=Snapshot)
def snapshot():
    started = perf_counter()
    snap = store.get_snapshot(UID)
    persisted = snap is not None
    if not snap:
        snap = orch.empty_snapshot(UID)
    elif snap.get("readModelVersion") != READ_MODEL_VERSION:
        # Recompute deterministic forecast fields and refresh the authoritative
        # wallet projection without invoking Gemini or a full agent run.
        migration_orchestrator = orch if orch.store is store else Orchestrator(store)
        snap = migration_orchestrator.refresh_forecast_projection(UID, snap)
    logger.info("snapshot uid=%s duration_ms=%d persisted=%s", UID, round((perf_counter() - started) * 1000), persisted)
    return snap


def _run_via_adk(uid: str, request: str) -> tuple[str, dict]:
    """Execute the pipeline as an ADK graph and project the result.

    The graph's nodes persist to the same collections the orchestrator writes,
    so the projection assembles a snapshot without knowing which engine ran —
    which is the property that makes swapping engines safe.
    """
    from adk_agents.pipeline.runner import run_pipeline

    run_id, _state = run_pipeline(uid, request)
    snapshot = orch.project(uid, run_id)
    store.set_snapshot(uid, snapshot)
    store.set_user(uid, {"lastRunId": run_id, "lastRunAt": snapshot["generatedAt"]})
    return run_id, snapshot


@app.post("/api/v1/runs", response_model=RunResponse)
def run_agents(body: RunIn):
    engine = body.engine or settings.pipeline_engine
    if engine == "adk":
        run_id, snap = _run_via_adk(UID, body.request)
    else:
        run_id, snap = orch.run(UID, body.request)
    return {"runId": run_id, "snapshot": snap}


def _execute_background_run(active_orchestrator: Orchestrator, run_id: str, request: str):
    try:
        active_orchestrator.run(UID, request, run_id=run_id)
    except Exception as exc:
        logger.exception("background agent run failed run_id=%s", run_id)
        entries = [
            entry for entry in store.get_subcollection(UID, "agent_runs")
            if entry.get("runId") == run_id
        ]
        failed = next((entry for entry in entries if entry.get("status") == "running"), None)
        failed = failed or next((entry for entry in entries if entry.get("status") == "queued"), None)
        if failed:
            store.write_agent_run(UID, failed["id"], {
                "status": "failed",
                "summary": f"{failed.get('label') or failed.get('agent')} failed.",
                "detail": str(exc)[:300],
                "retryable": True,
            })


@app.post("/api/v1/runs/async", status_code=202)
def start_agent_run(body: RunIn, background_tasks: BackgroundTasks):
    """Queue a real run and return its ID before agent work starts."""
    run_id = uuid.uuid4().hex
    active_orchestrator = orch if orch.store is store else Orchestrator(store)
    active_orchestrator.queue_run(UID, run_id)
    background_tasks.add_task(_execute_background_run, active_orchestrator, run_id, body.request)
    return {"runId": run_id, "status": "queued"}


@app.get("/api/v1/runs/{run_id}")
def run_status(run_id: str):
    data = [
        entry for entry in store.get_subcollection(UID, "agent_runs")
        if entry.get("runId") == run_id
    ]
    if not data:
        raise HTTPException(404, "Run not found")
    order = {agent: index for index, (agent, _label) in enumerate(AGENTS)}
    labels = dict(AGENTS)
    data.sort(key=lambda entry: order.get(entry.get("agent"), len(order)))
    statuses = {entry.get("status") for entry in data}
    if "failed" in statuses:
        status = "failed"
    elif len(data) == len(AGENTS) and statuses <= {"ok", "degraded"}:
        status = "complete"
    elif "running" in statuses:
        status = "running"
    else:
        status = "queued"
    return {
        "runId": run_id,
        "status": status,
        "agents": [{
            "id": entry["agent"],
            "label": entry.get("label") or labels.get(entry["agent"], entry["agent"]),
            "status": entry.get("status", "queued"),
            "summary": entry.get("summary"),
            "detail": entry.get("detail"),
            "durationMs": entry.get("durationMs", 0),
        } for entry in data],
    }


@app.post("/api/v1/planned", response_model=Snapshot)
def add_planned(body: PlannedItemIn):
    item = {"id": uuid.uuid4().hex, **body.model_dump(mode="json")}
    store.add_subdoc(UID, "planned", item, item["id"])
    return orch.project_planned_change(UID, added=item)


@app.delete("/api/v1/planned/{planned_id}", response_model=Snapshot)
def delete_planned(planned_id: str):
    store.delete_subdoc(UID, "planned", planned_id)
    return orch.project_planned_change(UID, removed_id=planned_id)


@app.post("/api/v1/goals", response_model=Snapshot)
def set_goal(body: GoalIn):
    goal = body.model_dump(mode="json")
    store.set_user(UID, {"goal": goal})
    return orch.project_goal_change(UID, goal)


@app.delete("/api/v1/goals", response_model=Snapshot)
def clear_goal():
    store.set_user(UID, {"goal": None})
    return orch.project_goal_change(UID, None)


@app.post("/api/v1/advice/{advice_id}/resolve", response_model=Snapshot)
def resolve_advice(advice_id: str, body: AdviceResolveIn):
    advice = store.get_subdoc(UID, "advice", advice_id)
    if not advice:
        raise HTTPException(404, "Advice not found")
    resolution = {
        "outcome": body.outcome,
        "resolvedAt": None if body.outcome == "open" else datetime.now(timezone.utc).isoformat(),
    }
    store.set_subdoc(UID, "advice", advice_id, resolution)
    return orch.project_advice_resolution(
        UID,
        {**advice, **resolution, "id": advice_id},
    )


def _card_id(name: str, network: str) -> str:
    """A URL-safe, stable id. Spaces here end up in route paths and break them."""
    slug = re.sub(r"[^a-z0-9]+", "-", f"{network} {name}".lower()).strip("-")
    return slug or "card"


def _apply_parse(card: dict, card_id: str, parsed: dict) -> dict:
    """Fold an extraction result into the wallet document and the global rules.

    Provenance, cadence and the failure reason all come from the agent now — the
    API no longer invents a source label or a recheck date the agent never set.
    """
    rules = with_rule_ids(parsed.get("rules", []))
    card_detail = {
        "name": card["name"],
        "last4": card["last4"],
        "network": card["network"],
        "annualFee": parsed.get("annualFee") if parsed.get("annualFee") is not None else card.get("annualFee", 0),
        "track": card["track"],
        "cardId": card_id,
        "accountId": card.get("accountId"),
        "rules": rules,
        "characteristics": parsed.get("characteristics", {}),
        # The card's own billing currency. Rendered rather than converted.
        "currency": parsed.get("currency", BASE_CURRENCY),
        "source": parsed["source"],
        "recheckCadence": parsed.get("recheckCadence", "weekly"),
        "nextRecheckAt": parsed.get("nextRecheckAt", str(datetime.now(timezone.utc).date())),
        "parseStatus": parsed.get("status", "failed"),
        "parseNote": parsed.get("note"),
        "parseConfidence": parsed.get("confidence", 0.0),
        "failureReason": parsed.get("failureReason"),
        "termsUrl": card.get("termsUrl"),
    }
    if parsed.get("documentSummary"):
        card_detail["documentSummary"] = parsed["documentSummary"]

    store.set_global_doc("card_rules", card_id, {
        "rules": rules,
        "characteristics": parsed.get("characteristics", {}),
        "source": parsed["source"],
        "status": card_detail["parseStatus"],
        "confidence": card_detail["parseConfidence"],
    })
    store.set_subdoc(UID, "wallet", card_id, card_detail)
    return card_detail


@app.post("/api/v1/cards", response_model=CardResponse)
def add_card(body: CardIn):
    card = body.model_dump(mode="json")
    card_id = _card_id(card["name"], card["network"])

    if card.get("rules"):
        # Rates the user typed or corrected by hand are authoritative.
        today = datetime.now(timezone.utc).date()
        parsed = {
            "rules": card["rules"], "characteristics": {}, "status": "parsed",
            "confidence": 1.0, "note": None, "failureReason": None,
            "source": {"label": "Entered by you", "locator": card.get("termsUrl") or "entered by hand", "retrievedAt": today.isoformat()},
            "recheckCadence": "not rechecked", "nextRecheckAt": str(today + timedelta(days=3650)),
        }
    else:
        previous = store.get_global_doc("card_rules", card_id)
        parsed = orch.cardintel.parse(card, previous)

    card_detail = _apply_parse(card, card_id, parsed)
    _, snap = orch.run(UID, "Recalculate after card added")
    return {"card": card_detail, "snapshot": snap}


@app.post("/api/v1/cards/{card_id}/recheck", response_model=CardResponse)
def recheck_card(card_id: str):
    """Re-read a card's terms on demand — what the 'recheck now' control calls."""
    card = store.get_subdoc(UID, "wallet", card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    if not card.get("termsUrl"):
        raise HTTPException(status_code=400, detail="This card has no terms link to reread.")

    previous = store.get_global_doc("card_rules", card_id)
    parsed = orch.cardintel.parse({**card, "rules": None}, previous)
    card_detail = _apply_parse({**card, "termsUrl": card.get("termsUrl")}, card_id, parsed)
    _, snap = orch.run(UID, "Recalculate after terms recheck")
    return {"card": card_detail, "snapshot": snap}


@app.post("/api/v1/cards/{card_id}/terms", response_model=CardResponse)
async def upload_terms(card_id: str, file: UploadFile = File(...)):
    """Read a terms document the user has on disk rather than one we can fetch."""
    card = store.get_subdoc(UID, "wallet", card_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="The uploaded file was empty.")

    document = document_from_upload(payload, file.filename or "uploaded terms")
    parsed = orch.cardintel.parse_document(document, card)
    card_detail = _apply_parse(card, card_id, parsed)
    _, snap = orch.run(UID, "Recalculate after terms upload")
    return {"card": card_detail, "snapshot": snap}


@app.post("/api/v1/cards/{card_id}/link-account", response_model=CardResponse)
def link_card_account(card_id: str, body: dict):
    """Attach a Plaid account to a card by hand when the mask does not match."""
    card = store.get_subdoc(UID, "wallet", card_id)
    if not card:
        raise HTTPException(404, "Card not found")
    account_id = (body or {}).get("accountId")
    if not account_id:
        raise HTTPException(400, "accountId is required")
    account = store.get_subdoc(UID, "plaid_accounts", account_id)
    if not account:
        raise HTTPException(404, "No such Plaid account for this user")
    if "credit" not in f"{account.get('type')} {account.get('subtype')}".lower():
        raise HTTPException(400, "Only a Plaid credit account can be linked to a card")
    linked_elsewhere = next(
        (item for item in store.get_wallet(UID)
         if item.get("accountId") == account_id and item.get("cardId") != card_id),
        None,
    )
    if linked_elsewhere:
        raise HTTPException(409, f"That account is already linked to {linked_elsewhere['name']}")

    store.set_subdoc(UID, "wallet", card_id, {"accountId": account_id})
    _, snap = orch.run(UID, "Recalculate after linking an account", refresh_advice=False)
    return {"card": store.get_subdoc(UID, "wallet", card_id), "snapshot": snap}


@app.get("/api/v1/plaid/accounts")
def plaid_accounts():
    """Accounts we know about, and which card each is linked to."""
    wallet = store.get_wallet(UID)
    by_account = {c["accountId"]: c for c in wallet if c.get("accountId")}
    return [
        {**account, "linkedCard": (by_account.get(account["id"]) or {}).get("name")}
        for account in store.get_subcollection(UID, "plaid_accounts")
    ]


@app.get("/api/v1/plaid/items")
def plaid_items():
    """Connected Items safe to show in an account-management interface."""
    accounts = store.get_subcollection(UID, "plaid_accounts")
    account_counts: dict[str, int] = {}
    for account in accounts:
        item_id = account.get("itemId")
        if item_id:
            account_counts[item_id] = account_counts.get(item_id, 0) + 1
    return [
        {
            "itemId": item.get("id") or item.get("itemId"),
            "institutionId": item.get("institutionId"),
            "institutionName": item.get("institutionName"),
            "createdAt": item.get("createdAt"),
            "lastSyncedAt": item.get("lastSyncedAt"),
            "accounts": account_counts.get(item.get("id") or item.get("itemId"), 0),
        }
        for item in store.get_subcollection(UID, "plaid_items")
    ]


@app.get("/api/v1/cards")
def cards():
    return store.get_wallet(UID)


@app.delete("/api/v1/cards/{wallet_or_card_id}", response_model=Snapshot)
def delete_card(wallet_or_card_id: str):
    card = store.get_subdoc(UID, "wallet", wallet_or_card_id)
    if not card:
        wallet = store.get_wallet(UID)
        card = next(
            (item for item in wallet if item.get("cardId") == wallet_or_card_id),
            None,
        )
    if not card:
        # Persisted snapshots created before walletId was introduced can contain
        # only a derived cardId. Correlate that record back to the live wallet.
        snapshot_card = next(
            (
                item
                for item in (store.get_snapshot(UID) or {}).get("wallet", [])
                if wallet_or_card_id in {
                    item.get("walletId"), item.get("id"), item.get("cardId")
                }
            ),
            None,
        )
        if snapshot_card:
            card = next((item for item in wallet if _same_wallet_card(item, snapshot_card)), None)
    if not card:
        raise HTTPException(404, "Card not found in wallet")
    # Rules are global card knowledge; only remove this user's wallet reference.
    store.delete_subdoc(UID, "wallet", card.get("walletId") or card.get("id") or wallet_or_card_id)
    _, snap = orch.run(
        UID,
        "Recalculate after card removed",
        refresh_advice=False,
    )
    return snap


@app.post("/api/v1/plaid/link-token")
def plaid_link_token(body: LinkTokenIn):
    if not settings.use_plaid:
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


@app.post("/api/v1/plaid/sandbox/seed")
def plaid_sandbox_seed(body: LinkTokenIn):
    """Create a sandbox Item and exchange it in one call.

    Plaid Link exists so a human can type bank credentials somewhere we never
    see. In sandbox there are no real credentials, so this shortcut mints the
    public token directly — which means ingestion can be built and tested
    before any of the Link UI exists. Sandbox only, by construction.
    """
    if not settings.use_plaid:
        raise HTTPException(400, "Plaid is not configured; set PLAID_CLIENT_ID and PLAID_SECRET.")
    if (settings.plaid_env or "sandbox").lower() != "sandbox":
        raise HTTPException(400, "This endpoint only exists for the sandbox environment.")

    # Each seed mints a NEW Item with new account and transaction ids, so the
    # same synthetic purchases arrive again under different identities and
    # nothing dedupes them. Seeding four times quadrupled reported spend.
    # Clearing first makes reseeding idempotent, which is what a test loop needs.
    uid_to_clear = _uid(body.userId)
    for collection in ("plaid_items", "plaid_accounts", "transactions"):
        for row in store.get_subcollection(uid_to_clear, collection):
            if row.get("id"):
                store.delete_subdoc(uid_to_clear, collection, row["id"])
    for card in store.get_wallet(uid_to_clear):
        if card.get("accountId"):
            store.set_subdoc(uid_to_clear, "wallet", card["cardId"], {"accountId": None})

    from plaid.model.products import Products
    from plaid.model.sandbox_public_token_create_request import SandboxPublicTokenCreateRequest

    uid = _uid(body.userId)
    client = get_plaid_client()
    try:
        created = client.sandbox_public_token_create(SandboxPublicTokenCreateRequest(
            institution_id="ins_109508",  # First Platypus Bank, the standard sandbox institution
            initial_products=[Products("transactions")],
        )).to_dict()
        from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest

        exchanged = client.item_public_token_exchange(
            ItemPublicTokenExchangeRequest(public_token=created["public_token"])
        ).to_dict()
    except Exception as exc:
        raise _plaid_error(exc)

    item_id = exchanged["item_id"]
    store.set_subdoc(uid, "plaid_items", item_id, {
        "id": item_id,
        "accessToken": exchanged["access_token"],
        "cursor": None,
        "institutionId": "ins_109508",
        "createdAt": datetime.now(timezone.utc).isoformat(),
    })
    accounts = _store_plaid_accounts(uid, client, exchanged["access_token"], item_id)
    return {"ok": True, "itemId": item_id, "userId": uid, "accounts": len(accounts),
            "linked": link_accounts_to_cards(uid),
            "next": "POST /api/v1/plaid/sync to pull transactions"}


@app.post("/api/v1/plaid/exchange-token")
def plaid_exchange(body: ExchangeTokenIn):
    if not settings.use_plaid:
        return {"ok": True, "demo": True, "message": "Plaid is not configured; set PLAID_CLIENT_ID and PLAID_SECRET."}

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
                "institutionId": body.institutionId,
                "institutionName": body.institutionName,
                "createdAt": datetime.now(timezone.utc).isoformat(),
            },
        )
        accounts = _store_plaid_accounts(uid, client, access_token, item_id)
        linked = link_accounts_to_cards(uid)

        return {"ok": True, "itemId": item_id, "accounts": len(accounts), "linked": linked}
    except Exception as exc:
        raise _plaid_error(exc)


@app.post("/api/v1/plaid/webhook")
def plaid_webhook(body: dict):
    """Plaid tells us a transaction landed; we pull it immediately.

    This is what makes the feed current rather than a thing the user refreshes.
    Plaid posts SYNC_UPDATES_AVAILABLE when a bank reports new activity, and the
    handler runs the same cursor-based sync as the manual endpoint — so there is
    one code path, whether the pull was scheduled, manual or pushed.

    Note that "immediately" means when the bank posts the transaction, typically
    minutes to a day after the card is used, because that is when Plaid learns
    of it. Detecting the moment of purchase is the extension's job: it sees the
    checkout page before the transaction exists anywhere.

    Deliberately tolerant: a webhook that errors gets retried by Plaid, so an
    unrecognised type is acknowledged rather than failed.
    """
    webhook_type = (body or {}).get("webhook_type")
    webhook_code = (body or {}).get("webhook_code")
    item_id = (body or {}).get("item_id")
    logger.info("Plaid webhook %s/%s for item %s", webhook_type, webhook_code, item_id)

    if webhook_type != "TRANSACTIONS":
        return {"ok": True, "handled": False, "reason": f"Ignoring {webhook_type}"}

    # SYNC_UPDATES_AVAILABLE is the modern signal; the older per-count codes
    # mean the same thing for a cursor-based puller.
    if webhook_code not in {"SYNC_UPDATES_AVAILABLE", "DEFAULT_UPDATE", "INITIAL_UPDATE",
                            "HISTORICAL_UPDATE", "TRANSACTIONS_REMOVED"}:
        return {"ok": True, "handled": False, "reason": f"Ignoring {webhook_code}"}

    if not settings.use_plaid:
        return {"ok": True, "handled": False, "reason": "Plaid is not configured"}

    try:
        result = plaid_sync(SyncIn(userId=UID, itemId=item_id))
    except HTTPException as exc:
        # Returning 200 stops Plaid retrying something that will never succeed,
        # such as an Item we no longer hold.
        logger.warning("Webhook sync failed: %s", exc.detail)
        return {"ok": False, "handled": False, "reason": str(exc.detail)}

    return {"ok": True, "handled": True,
            "added": result.get("added"), "modified": result.get("modified"),
            "removed": result.get("removed")}


@app.post("/api/v1/plaid/sync")
def plaid_sync(body: SyncIn):
    started = perf_counter()
    if not settings.use_plaid:
        return {"ok": True, "demo": True, "message": "Plaid is not configured; set PLAID_CLIENT_ID and PLAID_SECRET."}

    uid = _uid(body.userId)
    item_id = body.itemId

    try:
        # If the frontend omits itemId, sync all Plaid Items connected to this user.
        items = [store.get_subdoc(uid, "plaid_items", item_id)] if item_id else store.get_subcollection(uid, "plaid_items")
        items = [x for x in items if x]
        if not items:
            raise HTTPException(404, "No Plaid Item connected for this user")

        client = get_plaid_client()
        totals = {"added": 0, "modified": 0, "removed": 0}
        cursors = []
        upserts: list[tuple[str, str, dict]] = []
        deletes: list[tuple[str, str]] = []

        for item in items:
            # Backfill accounts for Items created before account persistence was
            # added, and refresh masks/names when Plaid changes them.
            _store_plaid_accounts(uid, client, item["accessToken"], item["id"])
            current_cursor = body.cursor if body.cursor is not None else item.get("cursor")
            has_more = True
            item_added = item_modified = item_removed = 0

            while has_more:
                request = _plaid_transactions_sync_request(
                    item["accessToken"],
                    current_cursor,
                )
                response = client.transactions_sync(request)
                data = response.to_dict()

                for tx in data.get("added", []):
                    tx_id = tx.get("transaction_id")
                    if not tx_id:
                        continue
                    upserts.append(("transactions", tx_id, _normalise_plaid_transaction(tx)))
                    item_added += 1

                for tx in data.get("modified", []):
                    tx_id = tx.get("transaction_id")
                    if not tx_id:
                        continue
                    upserts.append(("transactions", tx_id, _normalise_plaid_transaction(tx)))
                    item_modified += 1

                for tx in data.get("removed", []):
                    tx_id = tx.get("transaction_id")
                    if tx_id:
                        deletes.append(("transactions", tx_id))
                        item_removed += 1

                current_cursor = data.get("next_cursor") or current_cursor
                has_more = bool(data.get("has_more", False))

            upserts.append((
                "plaid_items",
                item["id"],
                {
                    "cursor": current_cursor,
                    "lastSyncedAt": datetime.now(timezone.utc).isoformat(),
                },
            ))
            cursors.append({"itemId": item["id"], "cursor": current_cursor})
            totals["added"] += item_added
            totals["modified"] += item_modified
            totals["removed"] += item_removed

        store.apply_subdoc_changes(uid, upserts=upserts, deletes=deletes)
        # A card added after the bank was connected still needs attaching.
        link_accounts_to_cards(uid)
        transactions = _rebuild_ingestion_from_store(uid)
        # Plaid connection should not wait for a Gemini advisory call. Existing
        # advice remains valid while deterministic totals and strategy refresh.
        # Skipping the model keeps a bank connection fast, but that is only
        # safe when there is advice to retain. On a first sync there is none,
        # so the dashboard would show nothing to do and a track record of
        # "0 of 0", which reads as broken rather than as an optimisation.
        run_id, snap = orch.run(
            uid,
            "Analyse newly synced Plaid transactions",
            refresh_advice=not store.get_subcollection(uid, "advice"),
        )
        logger.info("plaid_sync uid=%s duration_ms=%d added=%d modified=%d removed=%d", uid, round((perf_counter() - started) * 1000), totals["added"], totals["modified"], totals["removed"])

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


@app.delete("/api/v1/plaid/items/{item_id}")
def disconnect_plaid_item(item_id: str):
    """Revoke one bank connection and remove only the data it supplied."""
    item = store.get_subdoc(UID, "plaid_items", item_id)
    if not item:
        raise HTTPException(404, "No such Plaid Item for this user")
    if not settings.use_plaid:
        raise HTTPException(503, "Plaid credentials are required to revoke this Item safely")
    try:
        plaid_removed = _remove_plaid_item_remote(item)
        removed = _delete_plaid_item_data(UID, item)
        active_orchestrator = orch if orch.store is store else Orchestrator(store)
        run_id, snapshot = active_orchestrator.run(
            UID,
            "Recalculate after disconnecting a Plaid Item",
            refresh_advice=False,
            refresh_card_intelligence=False,
        )
        return {
            "ok": True,
            "itemId": item_id,
            "plaidRemoved": plaid_removed,
            **removed,
            "runId": run_id,
            "snapshot": snapshot,
        }
    except HTTPException:
        raise
    except Exception as exc:
        # Keep the token and local records when remote revocation fails so the
        # user can retry instead of being left with an unreachable active Item.
        raise _plaid_error(exc)


@app.post("/api/v1/demo/reset")
def reset_demo(x_internal_secret: str | None = Header(default=None)):
    """Return the single-user sandbox demo to a fresh zero-value snapshot."""
    if x_internal_secret != settings.internal_run_secret:
        raise HTTPException(401, "Unauthorized")
    if not settings.demo_mode or settings.plaid_env.lower() != "sandbox":
        raise HTTPException(403, "Demo reset is available only in DEMO_MODE with Plaid Sandbox")

    items = store.get_subcollection(UID, "plaid_items")
    removed_items, disconnect_errors = 0, []
    for item in items:
        try:
            if _remove_plaid_item_remote(item):
                removed_items += 1
        except Exception as exc:
            item_id = item.get("id") or item.get("itemId")
            logger.warning("demo_reset Plaid removal failed item_id=%s error=%s", item_id, exc)
            disconnect_errors.append({
                "itemId": item_id,
                "error": "Plaid Item removal failed; local demo state was still cleared.",
            })

    # Reset must remain useful if Sandbox is unavailable. Remote errors are
    # returned visibly, while all local user state is still cleared.
    store.clear_user(UID, preserve_collections={"catalog"})
    active_orchestrator = orch if orch.store is store else Orchestrator(store)
    snapshot = active_orchestrator.empty_snapshot(UID)
    store.set_snapshot(UID, snapshot)
    return {
        "ok": True,
        "itemsFound": len(items),
        "plaidItemsRemoved": removed_items,
        "disconnectErrors": disconnect_errors,
        "snapshot": snapshot,
    }


@app.post("/api/v1/scheduler/run")
def scheduled_run(x_internal_secret: str | None = Header(default=None)):
    if x_internal_secret != settings.internal_run_secret:
        raise HTTPException(401, "Unauthorized")
    if settings.use_plaid and store.get_subcollection(UID, "plaid_items"):
        synced = plaid_sync(SyncIn(userId=UID))
        return {"runId": synced["runId"], "generatedAt": synced["snapshot"]["generatedAt"],
                "plaid": {key: synced[key] for key in ("added", "modified", "removed")}}
    run_id, snap = orch.run(UID, "Scheduled autonomous CardSense run")
    return {"runId": run_id, "generatedAt": snap["generatedAt"]}


@app.post("/api/v1/import/csv")
async def import_csv(file: UploadFile = File(...)):
    content = (await file.read()).decode("utf-8-sig")
    rows = orch.ingestion.import_csv_records(
        UID, store, csv.DictReader(io.StringIO(content)), file.filename or "statement.csv"
    )
    run_id, snap = orch.run(UID, "Analyse imported bank statement")
    return {"imported": len(rows), "runId": run_id, "snapshot": snap}
