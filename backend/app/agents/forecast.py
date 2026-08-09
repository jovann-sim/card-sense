from __future__ import annotations
from datetime import date, timedelta

class ForecastAgent:
    id="forecast"
    def run(self, summary, planned):
        monthly=list(summary["monthly"].values())
        avg=sum(monthly)/len(monthly) if monthly else summary["spend"]
        projected=round(avg*1.05,2)
        today=date.today()
        timeline=[]
        for p in planned:
            timeline.append({"date":str(p["startDate"]),"kind":p["kind"],"title":p["label"],"detail":p.get("note"),"amount":p["amount"]})
        return {"horizonDays":30,"projectedSpend":projected,"confidence":round(projected*.12,2),"basis":"Recent transaction history plus user-declared planned spending. Not seasonality.","timeline":sorted(timeline,key=lambda x:x["date"]),"doNothingCost":round(projected*.03,2),"doNothingWindow":"over the next 30 days"}
