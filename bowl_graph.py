"""
Layer 2: The Bowl Graph
Structured intelligence layer — maps orders, customers, recipes, and taste signals
into a proprietary data asset. Every transaction becomes a data point.
"""

import json
import random
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional


class BowlGraph:
    def __init__(self, db_path: str = "data/bowl_graph.db"):
        self.db_path = db_path
        self._init_schema()
        self._seed_demo_data()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id     TEXT PRIMARY KEY,
                    customer_id  TEXT NOT NULL,
                    bowl_id      TEXT NOT NULL,
                    modifications TEXT DEFAULT '[]',
                    quantity     INTEGER DEFAULT 1,
                    group_size   INTEGER DEFAULT 1,
                    status       TEXT DEFAULT 'received',
                    feedback_score INTEGER,
                    feedback_notes TEXT,
                    created_at   TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS taste_signals (
                    signal_id    TEXT PRIMARY KEY,
                    customer_id  TEXT NOT NULL,
                    hunger_level TEXT,
                    flavor_pref  TEXT,
                    mood         TEXT,
                    energy_goal  TEXT,
                    timing       TEXT,
                    group_type   TEXT,
                    dietary      TEXT DEFAULT '[]',
                    recommended_bowl TEXT,
                    ordered_bowl TEXT,
                    created_at   TEXT NOT NULL
                );
            """)

    def _seed_demo_data(self):
        with self._conn() as conn:
            if conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] > 0:
                return

        bowls = ["classic-hut", "green-machine", "sweet-kugel", "protein-power", "the-adventurer", "office-bundle"]
        weights = [0.35, 0.20, 0.15, 0.18, 0.08, 0.04]
        random.seed(42)
        now = datetime.utcnow()

        for _ in range(240):
            bowl_id = random.choices(bowls, weights=weights)[0]
            hours_ago = random.uniform(0, 168)  # last 7 days
            ts = (now - timedelta(hours=hours_ago)).isoformat()
            score = random.choices([None, 3, 4, 4, 5, 5], weights=[0.25, 0.05, 0.15, 0.15, 0.2, 0.2])[0]
            customer_id = f"cust_{random.randint(1, 100):04d}"

            with self._conn() as conn:
                conn.execute(
                    "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        f"ord_{uuid.uuid4().hex[:12]}",
                        customer_id, bowl_id, "[]",
                        1, random.randint(1, 4),
                        "completed", score, None, ts,
                    ),
                )

    # ── Write ─────────────────────────────────────────────────────────────────

    def record_order(self, data: dict) -> str:
        order_id = f"ord_{uuid.uuid4().hex[:12]}"
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    order_id,
                    data["customer_id"],
                    data["bowl_id"],
                    json.dumps(data.get("modifications", [])),
                    data.get("quantity", 1),
                    data.get("group_size", 1),
                    "received",
                    None, None,
                    datetime.utcnow().isoformat(),
                ),
            )
        return order_id

    def record_taste_signal(self, prefs: dict, recommended: str, ordered: Optional[str] = None):
        signal_id = f"sig_{uuid.uuid4().hex[:12]}"
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO taste_signals VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    signal_id,
                    prefs.get("customer_id", "anonymous"),
                    prefs.get("hunger_level"),
                    prefs.get("flavor_pref"),
                    prefs.get("mood"),
                    prefs.get("energy_goal"),
                    prefs.get("timing"),
                    prefs.get("group_type"),
                    json.dumps(prefs.get("dietary", [])),
                    recommended,
                    ordered,
                    datetime.utcnow().isoformat(),
                ),
            )

    def record_feedback(self, order_id: str, score: int, notes: str = ""):
        with self._conn() as conn:
            conn.execute(
                "UPDATE orders SET feedback_score=?, feedback_notes=? WHERE order_id=?",
                (score, notes, order_id),
            )

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_recent_orders(self, limit: int = 20) -> List[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_bowl_stats(self) -> List[dict]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT
                    bowl_id,
                    COUNT(*) AS order_count,
                    ROUND(AVG(CASE WHEN feedback_score IS NOT NULL THEN CAST(feedback_score AS REAL) END), 1) AS avg_feedback,
                    SUM(group_size) AS total_servings
                FROM orders
                GROUP BY bowl_id
                ORDER BY order_count DESC
            """).fetchall()
        return [dict(r) for r in rows]

    def get_hourly_volume(self) -> List[dict]:
        with self._conn() as conn:
            rows = conn.execute("""
                SELECT
                    CAST(strftime('%H', created_at) AS INTEGER) AS hour,
                    COUNT(*) AS orders
                FROM orders
                WHERE created_at >= datetime('now', '-7 days')
                GROUP BY hour
                ORDER BY hour
            """).fetchall()
        return [dict(r) for r in rows]

    def get_reorder_rate(self) -> dict:
        with self._conn() as conn:
            multi = conn.execute("""
                SELECT COUNT(*) FROM (
                    SELECT customer_id FROM orders
                    GROUP BY customer_id HAVING COUNT(*) > 1
                )
            """).fetchone()[0]
            total_customers = conn.execute(
                "SELECT COUNT(DISTINCT customer_id) FROM orders"
            ).fetchone()[0]
        rate = (multi / total_customers * 100) if total_customers else 0
        return {"repeat_customers": multi, "total_customers": total_customers, "reorder_rate_pct": round(rate, 1)}

    def get_network_data(self) -> dict:
        """Build the Bowl Graph network: nodes and edges for visualization."""
        with open("data/menu.json") as f:
            bowls = json.load(f)["bowls"]

        stats = self.get_bowl_stats()
        order_counts = {s["bowl_id"]: s["order_count"] for s in stats}
        feedback_avgs = {s["bowl_id"]: (s["avg_feedback"] or 0) for s in stats}

        nodes: list = []
        edges: list = []
        seen: set = set()

        def add_node(n):
            if n["id"] not in seen:
                nodes.append(n)
                seen.add(n["id"])

        # ── Bowl nodes (central, heaviest) ──────────────────────────────────
        for bowl in bowls:
            add_node({
                "id": f"bowl:{bowl['id']}",
                "type": "bowl",
                "label": bowl["name"],
                "sublabel": bowl["tagline"],
                "weight": max(order_counts.get(bowl["id"], 1), 1),
                "meta": {
                    "price": bowl["price"],
                    "calories": bowl["calories"],
                    "protein_g": bowl["protein_g"],
                    "feedback": round(feedback_avgs.get(bowl["id"], 0), 1),
                    "ingredients": bowl["ingredients"],
                    "tags": bowl.get("tags", []),
                    "prep_minutes": bowl["prep_minutes"],
                },
            })

        # ── Ingredient + tag nodes with edges ────────────────────────────────
        ing_bowls: dict = {}   # ing_id -> list of bowl_ids
        tag_weight: dict = {}  # tag_id -> total order weight

        for bowl in bowls:
            vol = order_counts.get(bowl["id"], 1)
            bid = f"bowl:{bowl['id']}"

            for ing in bowl["ingredients"]:
                iid = "ing:" + ing.replace(" ", "_")
                ing_bowls.setdefault(iid, {"label": ing, "bowls": []})["bowls"].append(bowl["id"])
                edges.append({"source": bid, "target": iid, "type": "contains", "weight": vol})

            for tag in bowl.get("tags", []):
                tid = f"tag:{tag}"
                tag_weight[tid] = tag_weight.get(tid, 0) + vol
                edges.append({"source": bid, "target": tid, "type": "tag", "weight": vol})

        for iid, data in ing_bowls.items():
            add_node({
                "id": iid, "type": "ingredient",
                "label": data["label"],
                "sublabel": f"in {len(data['bowls'])} bowl(s)",
                "weight": len(data["bowls"]),
                "meta": {"bowls": data["bowls"]},
            })

        for tid, w in tag_weight.items():
            add_node({
                "id": tid, "type": "tag",
                "label": tid.replace("tag:", "").replace("-", " "),
                "sublabel": f"{w} orders",
                "weight": w,
                "meta": {},
            })

        # ── Preference segment nodes (from taste_signals) ────────────────────
        with self._conn() as conn:
            segs = conn.execute("""
                SELECT flavor_pref, COUNT(*) AS cnt,
                       GROUP_CONCAT(DISTINCT recommended_bowl) AS bowls
                FROM taste_signals
                WHERE flavor_pref IS NOT NULL AND flavor_pref != ''
                GROUP BY flavor_pref
            """).fetchall()

        for row in [dict(r) for r in segs]:
            sid = f"seg:{row['flavor_pref']}"
            add_node({
                "id": sid, "type": "segment",
                "label": f"{row['flavor_pref']} seekers",
                "sublabel": f"{row['cnt']} signals",
                "weight": row["cnt"],
                "meta": {},
            })
            for bowl_id in (row["bowls"] or "").split(",")[:3]:
                if f"bowl:{bowl_id}" in seen:
                    edges.append({"source": sid, "target": f"bowl:{bowl_id}",
                                  "type": "prefers", "weight": row["cnt"]})

        total_orders = sum(order_counts.values())
        return {
            "nodes": nodes,
            "edges": edges,
            "meta": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "total_orders": total_orders,
            },
        }

    def get_insights(self) -> dict:
        stats = self.get_bowl_stats()
        hourly = self.get_hourly_volume()
        reorder = self.get_reorder_rate()

        total_orders = sum(s["order_count"] for s in stats)
        rated = [s["avg_feedback"] for s in stats if s["avg_feedback"]]
        avg_sat = round(sum(rated) / len(rated), 2) if rated else 0
        peak_hour = max(hourly, key=lambda x: x["orders"])["hour"] if hourly else 8

        return {
            "total_orders": total_orders,
            "top_bowl": stats[0]["bowl_id"] if stats else "classic-hut",
            "avg_satisfaction": avg_sat,
            "peak_hour": f"{peak_hour:02d}:00",
            "reorder": reorder,
            "bowl_stats": stats,
            "hourly_volume": hourly,
        }
