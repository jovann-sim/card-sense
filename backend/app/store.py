from __future__ import annotations
import json
import logging
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any
from .config import settings

log = logging.getLogger(__name__)

class Store:
    USER_COLLECTIONS = {
        "transactions", "planned", "wallet", "catalog", "plaid_items",
        "plaid_accounts", "forecasts", "strategy_runs", "advice",
        "agent_runs", "model_calls", "quality_reports", "snapshots",
    }

    def __init__(self, persist: bool = False):
        """`persist` is opt-in so a bare Store() is always empty and isolated.

        Only the module-level singleton reads and writes the local file; tests
        constructing their own Store must not inherit yesterday's cards.
        """
        self.db = None
        self.memory: dict[str, Any] = {"users": {}, "card_rules": {}, "mcc_map": {}}
        self._snapshot_cache: dict[str, tuple[float, dict]] = {}
        self._persist_enabled = persist
        self._load()

    def connect(self):
        """Initialise Firestore only after real-mode readiness has been checked."""
        if settings.demo_mode or self.db:
            return
        from google.cloud import firestore
        self.db = firestore.Client(project=settings.google_cloud_project, database=settings.firestore_database)

    # -- local persistence ---------------------------------------------------
    # Without this the in-memory store loses every card on restart, which makes
    # working on extraction miserable. Firestore, when enabled, takes over
    # entirely and these become no-ops.

    @property
    def _path(self) -> Path:
        return Path(settings.local_store_path)

    @property
    def _persisting(self) -> bool:
        return self._persist_enabled and settings.persist_local_store and not self.db

    def _load(self):
        if not (self._persisting and self._path.exists()):
            return
        try:
            self.memory = json.loads(self._path.read_text())
        except Exception as exc:
            log.warning("Could not read local store, starting empty: %s", exc)

    def _persist(self):
        if not self._persisting:
            return
        try:
            self._path.write_text(json.dumps(self.memory, indent=2, default=str))
        except Exception as exc:
            log.warning("Could not write local store: %s", exc)

    def reset(self):
        """Drop everything. Used by tests and by starting a demo from scratch."""
        self.memory = {"users": {}, "card_rules": {}, "mcc_map": {}}
        self._snapshot_cache.clear()
        self._persist()

    def clear_user(self, uid: str, *, preserve_collections: set[str] | None = None):
        """Clear one user's operational state without deleting global rules."""
        preserve = preserve_collections or set()
        if self.db:
            for collection in self.USER_COLLECTIONS - preserve:
                documents = list(self._user_ref(uid).collection(collection).stream())
                for offset in range(0, len(documents), 450):
                    batch = self.db.batch()
                    for document in documents[offset:offset + 450]:
                        batch.delete(document.reference)
                    batch.commit()
            # User fields such as goal and lastRunAt live on the parent doc.
            self._user_ref(uid).delete()
        else:
            existing = self.memory["users"].get(uid, {})
            kept = {
                collection: deepcopy(existing[collection])
                for collection in preserve
                if collection in existing
            }
            if kept:
                self.memory["users"][uid] = kept
            else:
                self.memory["users"].pop(uid, None)
            self._persist()
        self._snapshot_cache.pop(uid, None)

    def _user_ref(self, uid: str):
        return self.db.collection("users").document(uid)

    def _global_ref(self, collection: str):
        return self.db.collection(collection)

    def get_user(self, uid: str) -> dict:
        if self.db:
            snap = self._user_ref(uid).get()
            return snap.to_dict() if snap.exists else {}
        return deepcopy(self.memory["users"].get(uid, {}))

    def set_user(self, uid: str, data: dict):
        if self.db:
            self._user_ref(uid).set(data, merge=True)
        else:
            self.memory["users"].setdefault(uid, {}).update(deepcopy(data))
            self._persist()

    def get_subcollection(self, uid: str, collection: str) -> list[dict]:
        if self.db:
            return [dict(s.to_dict() or {}, id=s.id) for s in self._user_ref(uid).collection(collection).stream()]
        return deepcopy(self.memory["users"].get(uid, {}).get(collection, []))

    def get_wallet(self, uid: str) -> list[dict]:
        """Expose a stable cardId for both current and legacy wallet documents."""
        wallet = self.get_subcollection(uid, "wallet")
        return [
            {
                **card,
                "walletId": card.get("walletId") or card.get("id") or card.get("cardId"),
                "cardId": card.get("cardId") or card.get("id"),
            }
            for card in wallet
            if card.get("cardId") or card.get("id")
        ]

    def add_subdoc(self, uid: str, collection: str, data: dict, doc_id: str | None = None) -> str:
        if self.db:
            ref = self._user_ref(uid).collection(collection).document(doc_id) if doc_id else self._user_ref(uid).collection(collection).document()
            ref.set(data)
            return ref.id
        import uuid
        doc_id = doc_id or uuid.uuid4().hex
        user = self.memory["users"].setdefault(uid, {})
        user.setdefault(collection, []).append(deepcopy({"id": doc_id, **data}))
        self._persist()
        return doc_id

    def set_subdoc(self, uid: str, collection: str, doc_id: str, data: dict):
        if self.db:
            self._user_ref(uid).collection(collection).document(doc_id).set(data, merge=True)
            return
        rows = self.memory["users"].setdefault(uid, {}).setdefault(collection, [])
        for row in rows:
            if row.get("id") == doc_id:
                row.update(deepcopy(data)); self._persist(); return
        rows.append(deepcopy({"id": doc_id, **data}))
        self._persist()

    def get_subdoc(self, uid: str, collection: str, doc_id: str) -> dict | None:
        if self.db:
            snap = self._user_ref(uid).collection(collection).document(doc_id).get()
            return dict(snap.to_dict() or {}, id=snap.id) if snap.exists else None
        rows = self.memory["users"].get(uid, {}).get(collection, [])
        return deepcopy(next((r for r in rows if r.get("id") == doc_id), None))

    def delete_subdoc(self, uid: str, collection: str, doc_id: str):
        if self.db:
            self._user_ref(uid).collection(collection).document(doc_id).delete()
            return
        rows = self.memory["users"].setdefault(uid, {}).setdefault(collection, [])
        self.memory["users"][uid][collection] = [r for r in rows if r.get("id") != doc_id]
        self._persist()

    def apply_subdoc_changes(
        self,
        uid: str,
        *,
        upserts: list[tuple[str, str, dict]],
        deletes: list[tuple[str, str]],
    ):
        """Apply a group of user subcollection changes with few Firestore round trips."""
        if self.db:
            operations = [
                ("set", collection, doc_id, data)
                for collection, doc_id, data in upserts
            ] + [
                ("delete", collection, doc_id, None)
                for collection, doc_id in deletes
            ]
            # Stay below Firestore's 500-write batch limit.
            for offset in range(0, len(operations), 450):
                batch = self.db.batch()
                for operation, collection, doc_id, data in operations[offset:offset + 450]:
                    ref = self._user_ref(uid).collection(collection).document(doc_id)
                    if operation == "set":
                        batch.set(ref, data, merge=True)
                    else:
                        batch.delete(ref)
                batch.commit()
            return

        user = self.memory["users"].setdefault(uid, {})
        for collection, doc_id, data in upserts:
            rows = user.setdefault(collection, [])
            row = next((item for item in rows if item.get("id") == doc_id), None)
            if row is None:
                rows.append(deepcopy({"id": doc_id, **data}))
            else:
                row.update(deepcopy(data))
        for collection, doc_id in deletes:
            rows = user.setdefault(collection, [])
            user[collection] = [item for item in rows if item.get("id") != doc_id]
        self._persist()

    def set_snapshot(self, uid: str, snapshot: dict):
        self.set_subdoc(uid, "snapshots", "current", snapshot)
        self._snapshot_cache[uid] = (
            monotonic() + settings.snapshot_cache_ttl_seconds,
            deepcopy(snapshot),
        )

    def get_snapshot(self, uid: str) -> dict | None:
        cached = self._snapshot_cache.get(uid)
        if cached and cached[0] > monotonic():
            return deepcopy(cached[1])

        snapshot = self.get_subdoc(uid, "snapshots", "current")
        if snapshot is not None:
            self._snapshot_cache[uid] = (
                monotonic() + settings.snapshot_cache_ttl_seconds,
                deepcopy(snapshot),
            )
        else:
            self._snapshot_cache.pop(uid, None)
        return snapshot

    def write_agent_run(self, uid: str, run_id: str, data: dict):
        self.set_subdoc(uid, "agent_runs", run_id, data)

    def set_global_doc(self, collection: str, doc_id: str, data: dict):
        if self.db:
            self._global_ref(collection).document(doc_id).set(data, merge=True)
            return
        self.memory.setdefault(collection, {})[doc_id] = deepcopy({"id": doc_id, **data})
        self._persist()

    def get_global_doc(self, collection: str, doc_id: str) -> dict | None:
        if self.db:
            snap = self._global_ref(collection).document(doc_id).get()
            return dict(snap.to_dict() or {}, id=snap.id) if snap.exists else None
        return deepcopy(self.memory.get(collection, {}).get(doc_id))

store = Store(persist=True)
