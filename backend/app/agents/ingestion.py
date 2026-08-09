from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import csv, re

class IngestionAgent:
    id = "ingestion"
    def run(self, uid: str, store, statement_dir: str | None = None):
        rows=[]
        if statement_dir and Path(statement_dir).exists():
            for path in Path(statement_dir).glob("*.csv"):
                with path.open(encoding="utf-8-sig", newline="") as f:
                    reader=csv.DictReader(f)
                    for r in reader:
                        amount=self._amount(r)
                        if amount > 0:
                            rows.append({"source_file":path.name,"amount":amount,"date":self._date(r),"category":self._text(r,["category","type","group"],"uncategorized"),"merchant":self._text(r,["merchant","payee","name","description"],"unknown"),"description":self._text(r,["description","memo","details"],"")})
        for row in rows:
            # CSV rows do not contain an upstream ID, so use a stable enough
            # import key to keep the subcollection contract intact.
            key = f"{row.get('source_file', '')}:{row.get('date', '')}:{row.get('merchant', '')}:{row.get('amount', 0)}"
            import hashlib
            store.set_subdoc(uid, "transactions", hashlib.sha256(key.encode()).hexdigest(), row)
        return rows
    def _amount(self,r):
        for k in ["amount","transaction_amount","debit","withdrawal","expense","value"]:
            if r.get(k):
                try:return abs(float(str(r[k]).replace(",","").replace("$","")))
                except: pass
        return 0.0
    def _date(self,r):
        for k in ["date","posted_date","transaction_date","trans_date"]:
            if r.get(k): return r[k]
        return None
    def _text(self,r,keys,default):
        for k in keys:
            if r.get(k): return str(r[k]).strip()
        return default
