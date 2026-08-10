from __future__ import annotations

class ForecastAgent:
    id="forecast"
    def timeline(self, planned):
        return sorted(
            [
                {
                    "date": str(item["startDate"]),
                    "kind": item["kind"],
                    "title": item["label"],
                    "detail": item.get("note"),
                    "amount": item["amount"],
                }
                for item in planned
            ],
            key=lambda item: item["date"],
        )

    def run(self, summary, planned):
        monthly=list(summary["monthly"].values())
        avg=sum(monthly)/len(monthly) if monthly else summary["spend"]
        projected=round(avg*1.05,2)
        return {"horizonDays":30,"projectedSpend":projected,"confidence":round(projected*.12,2),"basis":"Recent transaction history plus user-declared planned spending. Not seasonality.","timeline":self.timeline(planned),"doNothingCost":round(projected*.03,2),"doNothingWindow":"over the next 30 days"}
