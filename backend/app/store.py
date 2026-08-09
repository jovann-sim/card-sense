from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from .config import settings

class Store:
    def __init__(self):
        self.db = None
        self.memory: dict[str, Any] = {"users": {}, "card_rules": {}, "mcc_map": {}}

    def connect(self):
        """Initialise Firestore only after real-mode readiness has been checked."""
        if settings.demo_mode or self.db:
            return
        from google.cloud import firestore
        self.db = firestore.Client(project=settings.google_cloud_project, database=settings.firestore_database)

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
        return doc_id

    def set_subdoc(self, uid: str, collection: str, doc_id: str, data: dict):
        if self.db:
            self._user_ref(uid).collection(collection).document(doc_id).set(data, merge=True)
            return
        rows = self.memory["users"].setdefault(uid, {}).setdefault(collection, [])
        for row in rows:
            if row.get("id") == doc_id:
                row.update(deepcopy(data)); return
        rows.append(deepcopy({"id": doc_id, **data}))

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

    def set_snapshot(self, uid: str, snapshot: dict):
        self.set_subdoc(uid, "snapshots", "current", snapshot)

    def get_snapshot(self, uid: str) -> dict | None:
        return self.get_subdoc(uid, "snapshots", "current")

    def write_agent_run(self, uid: str, run_id: str, data: dict):
        self.set_subdoc(uid, "agent_runs", run_id, data)

    def set_global_doc(self, collection: str, doc_id: str, data: dict):
        if self.db:
            self._global_ref(collection).document(doc_id).set(data, merge=True)
            return
        self.memory.setdefault(collection, {})[doc_id] = deepcopy({"id": doc_id, **data})

    def get_global_doc(self, collection: str, doc_id: str) -> dict | None:
        if self.db:
            snap = self._global_ref(collection).document(doc_id).get()
            return dict(snap.to_dict() or {}, id=snap.id) if snap.exists else None
        return deepcopy(self.memory.get(collection, {}).get(doc_id))

store = Store()
