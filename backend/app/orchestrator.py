from __future__ import annotations
from datetime import date, datetime, timezone
import uuid
from .agents.ingestion import IngestionAgent
from .agents.forecast import ForecastAgent
from .agents.card_intelligence import CardIntelligenceAgent
from .agents.strategy import StrategyAgent
from .agents.advisory import AdvisoryAgent
from .agents.runtime import GeminiRuntime

class Orchestrator:
    def __init__(self,store):
        self.store=store
        rt=GeminiRuntime()
        self.ingestion=IngestionAgent(); self.forecast=ForecastAgent(); self.cardintel=CardIntelligenceAgent(rt); self.strategy=StrategyAgent(); self.advisory=AdvisoryAgent(rt)
    def run(self,uid,request="Run CardSense"):
        started=datetime.now(timezone.utc).isoformat(); run_id=uuid.uuid4().hex
        user=self.store.get_user(uid)
        transactions=user.get("ingestion",{}).get("transactions",[])
        # In production, IngestionAgent is called by the Plaid sync worker first.
        cats={}
        months={}
        for t in transactions:
            cats[t.get("category","uncategorized")]=cats.get(t.get("category","uncategorized"),0)+float(t.get("amount",0))
            if t.get("date"):
                months[str(t["date"])[:7]]=months.get(str(t["date"])[:7],0)+float(t.get("amount",0))
        summary={"spend":sum(cats.values()),"categories":cats,"monthly":months}
        planned=user.get("planned",[])
        forecast=self.forecast.run(summary,planned)
        wallet=user.get("wallet",[])
        rules=user.get("card_rules",{})
        strategy=self.strategy.run(summary,wallet,rules,user.get("goal"))
        advice=self.advisory.run(strategy,forecast,wallet)
        now=datetime.now(timezone.utc).isoformat()
        snapshot=self._snapshot(user,summary,forecast,strategy,advice,now)
        self.store.set_snapshot(uid,snapshot)
        self.store.set_user(uid,{"lastRunId":run_id,"lastRunAt":now})
        self.store.write_agent_run(uid,run_id,{"id":run_id,"request":request,"startedAt":started,"completedAt":now,"status":"ok"})
        return run_id,snapshot
    def _snapshot(self,user,summary,forecast,strategy,advice,now):
        wallet=user.get("wallet",[])
        rules=user.get("card_rules",{})
        cards=[]
        for c in wallet:
            crules=rules.get(c.get("name"),[])
            first=crules[0] if crules else {}
            cap=first.get("cap")
            spend=sum(x.get("spend",0) for x in strategy.get("categories",[]) if x.get("bestCard")==c.get("name"))
            state="unverified" if c.get("parseStatus")=="failed" else ("reached" if cap and spend >= cap else ("approaching" if cap and spend >= cap*0.8 else "healthy"))
            cards.append({"name":c.get("name",""),"last4":c.get("last4",""),"network":c.get("network",""),"categoryLabel":first.get("categoryLabel",""),"rate":first.get("rate",""),"cycleSpend":round(spend,2),"cap":cap,"cycleLabel":first.get("cycleLabel","no cap"),"state":state})
        captured=strategy.get("captured",0)
        tracks=[
            {"track":"cashback","rawUnits":round(captured,2),"unitLabel":"dollars","rate":1,"nominal":round(captured,2),"source":"Cashback: 1:1 placeholder assumption."},
            {"track":"points","rawUnits":round(captured/0.01,0),"unitLabel":"points","rate":0.01,"nominal":round(captured,2),"source":"Points: $0.01/point placeholder assumption."},
            {"track":"miles","rawUnits":round(captured/0.013,0),"unitLabel":"miles","rate":0.013,"nominal":round(captured,2),"source":"Miles: $0.013/mile placeholder assumption."},
        ]
        agent_runs=[{"id":a,"label":label,"status":"ok","lastRunAt":now} for a,label in [("ingestion","Ingestion"),("forecast","Forecast"),("card-intelligence","Card intelligence"),("strategy","Simulation & strategy"),("advisory","Advisory")]]
        activity=list(user.get("activity",[]))
        for a,label in [("ingestion","Ingestion"),("forecast","Forecast"),("card-intelligence","Card intelligence"),("strategy","Simulation & strategy"),("advisory","Advisory")]:
            activity.append({"id":f"{a}-{now}","agent":a,"status":"ok","startedAt":now,"durationMs":0,"summary":f"{label} completed the latest autonomous run.","writes":"snapshots/current","reads":[],"retryable":False})
        return {
            "generatedAt":now,
            "period":{"label":"Current period","start":str(date.today().replace(day=1)),"end":str(date.today())},
            "totals":{"spend":round(summary["spend"],2),"captured":strategy["captured"],"unclaimed":strategy["unclaimed"]},
            "agents":agent_runs,"recommendations":advice,"categories":strategy["categories"],"cards":cards,"tracks":tracks,
            "trackPreference":user.get("goal",{}).get("track") if user.get("goal") else None,"recommendedTrack":"cashback",
            "trackRationale":"Cash back is the current nominal-value baseline. Set a goal to make the optimisation preference explicit.",
            "forecast":forecast,"goal":user.get("goal"),"planned":user.get("planned",[]),
            "trackRecord":user.get("trackRecord",{"taken":0,"offered":len(advice),"earned":0,"missed":0,"accuracyNote":"No closed recommendations yet.","records":[]}),
            "wallet":wallet,"catalog":user.get("catalog",[]),"activity":activity[-50:],
            "collections":[
                {"collection":"ingestion","writtenBy":"ingestion","readBy":["forecast","strategy"]},
                {"collection":"card_rules","writtenBy":"card-intelligence","readBy":["strategy"]},
                {"collection":"snapshots/current","writtenBy":"strategy","readBy":["advisory"]},
                {"collection":"advice","writtenBy":"advisory","readBy":[]},
            ],
        }
