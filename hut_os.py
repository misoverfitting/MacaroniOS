"""
Layer 4: Hut OS
Operating system for running Macaroni Hut locations and formats.
Powers ordering, prep, inventory, labor forecasting, and quality control.
This is where software becomes scale.
"""

import json
from datetime import datetime
from typing import List


class HutOS:
    def __init__(self, bowl_graph):
        self.bowl_graph = bowl_graph
        with open("data/menu.json") as f:
            data = json.load(f)
        self.menu: dict = {b["id"]: b for b in data["bowls"]}

    def get_dashboard_data(self) -> dict:
        insights = self.bowl_graph.get_insights()
        recent = self.bowl_graph.get_recent_orders(12)

        for order in recent:
            bowl = self.menu.get(order["bowl_id"], {})
            order["bowl_name"] = bowl.get("name", order["bowl_id"])

        bowl_perf = [
            {
                **stat,
                "bowl_name": self.menu.get(stat["bowl_id"], {}).get("name", stat["bowl_id"]),
                "price": self.menu.get(stat["bowl_id"], {}).get("price", 0),
                "avg_feedback": stat["avg_feedback"] or 0,
            }
            for stat in insights["bowl_stats"]
        ]

        revenue_est = sum(
            s["order_count"] * self.menu.get(s["bowl_id"], {}).get("price", 0)
            for s in insights["bowl_stats"]
        )

        return {
            "summary": {
                "total_orders": insights["total_orders"],
                "avg_satisfaction": insights["avg_satisfaction"],
                "peak_hour": insights["peak_hour"],
                "top_bowl": self.menu.get(insights["top_bowl"], {}).get("name", insights["top_bowl"]),
                "revenue_est": round(revenue_est, 2),
                "reorder_rate_pct": insights["reorder"]["reorder_rate_pct"],
            },
            "recent_orders": recent,
            "bowl_performance": bowl_perf,
            "hourly_volume": self._pad_hourly(insights["hourly_volume"]),
            "inventory_alerts": self._inventory_alerts(insights["bowl_stats"]),
            "demand_forecast": self._simple_forecast(insights["hourly_volume"]),
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _pad_hourly(self, hourly: list) -> list:
        by_hour = {row["hour"]: row["orders"] for row in hourly}
        return [{"hour": h, "orders": by_hour.get(h, 0)} for h in range(24)]

    def _inventory_alerts(self, bowl_stats: list) -> list:
        alerts = []
        for stat in bowl_stats:
            bowl = self.menu.get(stat["bowl_id"], {})
            if stat["order_count"] > 80:
                ingredient = bowl.get("ingredients", ["key ingredient"])[0]
                alerts.append({
                    "level": "warning",
                    "bowl": bowl.get("name", stat["bowl_id"]),
                    "message": f"High velocity — consider restocking {ingredient}.",
                })
            elif stat["order_count"] > 50:
                alerts.append({
                    "level": "info",
                    "bowl": bowl.get("name", stat["bowl_id"]),
                    "message": "Moderate demand. Monitor inventory.",
                })
        if not alerts:
            alerts.append({"level": "ok", "bowl": "All items", "message": "Inventory nominal."})
        return alerts

    def _simple_forecast(self, hourly: list) -> dict:
        if not hourly:
            return {"peak_window": "08:00–10:00", "expected_orders": 0}
        peak = max(hourly, key=lambda x: x["orders"])
        return {
            "peak_window": f"{peak['hour']:02d}:00–{peak['hour']+1:02d}:00",
            "expected_orders": peak["orders"],
            "note": "Based on 7-day rolling average.",
        }
