"""
MacaroniOS — The Platform Layer for the Breakfast Hut of the Future
The restaurant is the interface. The company is the platform.

Run: uvicorn main:app --reload
"""

import json
import os
import uuid
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from bowl_graph import BowlGraph
from hut_os import HutOS
from intelligence import MacaroniIntelligence

app = FastAPI(
    title="MacaroniOS",
    description="The Breakfast Hut of the Future — Platform Layer v0.1",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

bowl_graph = BowlGraph("data/bowl_graph.db")
intelligence = MacaroniIntelligence(bowl_graph)
hut_os = HutOS(bowl_graph)


# ── Schemas ───────────────────────────────────────────────────────────────────

class PreferenceInput(BaseModel):
    hunger_level: str
    flavor_pref: str
    mood: str
    energy_goal: str
    timing: str
    group_type: str
    dietary: List[str] = []
    last_liked: Optional[str] = None


class OrderInput(BaseModel):
    customer_id: Optional[str] = None
    bowl_id: str
    modifications: List[str] = []
    quantity: int = 1
    group_size: int = 1


class FeedbackInput(BaseModel):
    order_id: str
    score: int
    notes: Optional[str] = ""


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def root():
    return FileResponse("static/index.html")


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    return FileResponse("static/dashboard.html")


@app.get("/api/menu")
def get_menu():
    with open("data/menu.json") as f:
        return json.load(f)


@app.post("/api/recommend")
def recommend(prefs: PreferenceInput):
    """
    Layer 3: Macaroni Intelligence
    Ask 7 lightweight questions, get one perfect bowl.
    """
    result = intelligence.recommend(prefs.dict())
    bowl_graph.record_taste_signal(prefs.dict(), result["recommended"]["id"])
    return result


@app.post("/api/orders")
def place_order(order: OrderInput):
    """Layer 1+4: Record an order through the Hut and Bowl Graph."""
    if not order.customer_id:
        order.customer_id = f"guest_{uuid.uuid4().hex[:8]}"

    order_id = bowl_graph.record_order({
        "customer_id": order.customer_id,
        "bowl_id": order.bowl_id,
        "modifications": order.modifications,
        "quantity": order.quantity,
        "group_size": order.group_size,
    })

    with open("data/menu.json") as f:
        menu = json.load(f)["bowls"]
    bowl = next((b for b in menu if b["id"] == order.bowl_id), None)
    eta = bowl["prep_minutes"] if bowl else 8

    return {"order_id": order_id, "status": "received", "eta_minutes": eta}


@app.post("/api/feedback")
def submit_feedback(feedback: FeedbackInput):
    """Capture satisfaction signals back into the Bowl Graph."""
    if not (1 <= feedback.score <= 5):
        raise HTTPException(status_code=400, detail="Score must be 1–5")
    bowl_graph.record_feedback(feedback.order_id, feedback.score, feedback.notes)
    return {"status": "recorded", "message": "Taste signal captured. The Bowl Graph grows."}


@app.get("/api/orders/recent")
def recent_orders(limit: int = 20):
    return bowl_graph.get_recent_orders(limit)


@app.get("/api/dashboard/data")
def dashboard_data():
    """Layer 4: Hut OS — full operations dashboard payload."""
    return hut_os.get_dashboard_data()


@app.get("/api/bowl-graph/insights")
def bowl_graph_insights():
    """Layer 2: Raw Bowl Graph analytics."""
    return bowl_graph.get_insights()


app.mount("/static", StaticFiles(directory="static"), name="static")
