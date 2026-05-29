"""
Layer 3: Macaroni Intelligence
AI system that learns from the Bowl Graph. Powers recommendations, personalization,
and eventually nutrition-aware meal design. Falls back to rule-based logic when
ANTHROPIC_API_KEY is not set — still works, still smart.
"""

import json
import os
from typing import List, Optional

CLAUDE_AVAILABLE = False
try:
    import anthropic
    CLAUDE_AVAILABLE = bool(os.getenv("ANTHROPIC_API_KEY"))
except ImportError:
    pass

BOWL_REASONS = {
    "classic-hut": "The crowd-pleaser. Warm, cheesy, protein-forward — built for every morning.",
    "green-machine": "Light but nourishing. High-protein, plant-forward, ready to carry you forward.",
    "sweet-kugel": "Comfort in a bowl. Sweet, nostalgic, surprisingly filling. The morning reset.",
    "protein-power": "Built to carry you. Dense macros, clean fuel, holds until dinner.",
    "the-adventurer": "For when breakfast should feel earned. Bold flavors, no apologies.",
    "office-bundle": "Scale the experience. Same quality, four bowls, one smart move.",
}


class MacaroniIntelligence:
    def __init__(self, bowl_graph):
        self.bowl_graph = bowl_graph
        with open("data/menu.json") as f:
            self.menu: List[dict] = json.load(f)["bowls"]

        if CLAUDE_AVAILABLE:
            self.client = anthropic.Anthropic()

    def recommend(self, prefs: dict) -> dict:
        try:
            if CLAUDE_AVAILABLE:
                return self._claude_recommend(prefs)
        except Exception:
            pass
        return self._rule_recommend(prefs)

    # ── Rule-based engine ────────────────────────────────────────────────────

    def _rule_recommend(self, prefs: dict) -> dict:
        candidates = list(self.menu)
        dietary = prefs.get("dietary", [])

        if "vegetarian" in dietary:
            filtered = [b for b in candidates if "vegetarian" in b.get("tags", [])]
            if filtered:
                candidates = filtered
        if "gluten_free" in dietary:
            filtered = [b for b in candidates if "gluten-free-friendly" in b.get("tags", [])]
            if filtered:
                candidates = filtered
        if "dairy_free" in dietary:
            filtered = [b for b in candidates if "dairy-free-friendly" in b.get("tags", [])]
            if filtered:
                candidates = filtered

        candidates.sort(key=lambda b: self._score(b, prefs), reverse=True)
        top = candidates[0]
        runner_up = candidates[1] if len(candidates) > 1 else None

        return {
            "recommended": top,
            "runner_up": runner_up,
            "reason": BOWL_REASONS.get(top["id"], "The system chose this. Trust the bowl."),
            "modifier_suggestion": self._modifier_hint(top, prefs),
            "powered_by": "MacaroniIntelligence (rule-based)",
        }

    def _score(self, bowl: dict, prefs: dict) -> int:
        s = 0
        tags = bowl.get("tags", [])

        flavor = prefs.get("flavor_pref", "")
        if flavor == "sweet" and "sweet" in tags:
            s += 4
        if flavor == "savory" and "savory" in tags:
            s += 4

        mood = prefs.get("mood", "")
        if mood == "adventurous" and "adventurous" in tags:
            s += 3
        if mood == "classic" and "classic" in tags:
            s += 3

        goal = prefs.get("energy_goal", "")
        if goal == "protein_heavy" and "protein-heavy" in tags:
            s += 3
        if goal == "comfort_forward" and "comfort" in tags:
            s += 3
        if goal == "light" and "light" in tags:
            s += 3

        hunger = prefs.get("hunger_level", "")
        if hunger == "very_hungry" and bowl["calories"] > 580:
            s += 2
        if hunger == "light" and bowl["calories"] < 470:
            s += 2

        group = prefs.get("group_type", "")
        if group == "family" and ("family" in tags or "kid-friendly" in tags):
            s += 2
        if group == "office_group" and ("office" in tags or "catering" in tags):
            s += 4

        timing = prefs.get("timing", "")
        if timing == "saving_for_later" and bowl.get("travel_rating", 0) >= 4:
            s += 2

        return s

    def _modifier_hint(self, bowl: dict, prefs: dict) -> Optional[str]:
        dietary = prefs.get("dietary", [])
        if "gluten_free" in dietary and "gluten-free-friendly" in bowl.get("tags", []):
            return "Request the GF pasta swap — same bowl, same taste."
        if "dairy_free" in dietary and bowl["id"] == "sweet-kugel":
            return "Ask us to hold the vanilla cream for a clean dairy-free bowl."
        if prefs.get("energy_goal") == "protein_heavy" and bowl["protein_g"] < 30:
            return "Add the extra protein upgrade (+$2.50) to hit your macro target."
        return None

    # ── Claude-powered engine ────────────────────────────────────────────────

    def _claude_recommend(self, prefs: dict) -> dict:
        menu_block = "\n".join(
            f"- {b['name']} (id: {b['id']}): {b['tagline']} | "
            f"tags: {', '.join(b['tags'])} | {b['calories']} cal | ${b['price']:.2f}"
            for b in self.menu
        )

        system = (
            "You are Macaroni Intelligence — the AI recommendation engine for Macaroni Hut, "
            "the Breakfast Hut of the Future. You know exactly which bowl is right for this customer. "
            "Respond with JSON only, no markdown fences."
        )

        user = f"""Available bowls:
{menu_block}

Customer preferences:
- Hunger level: {prefs.get('hunger_level')}
- Flavor preference: {prefs.get('flavor_pref')}
- Mood: {prefs.get('mood')}
- Energy goal: {prefs.get('energy_goal')}
- Timing: {prefs.get('timing')}
- Group type: {prefs.get('group_type')}
- Dietary needs: {', '.join(prefs.get('dietary', ['none']))}

Return JSON:
{{
  "bowl_id": "<id>",
  "reason": "<1-2 sentences, warm and confident, no AI language>",
  "modifier_suggestion": "<optional 1 sentence tweak, or null>"
}}"""

        resp = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=256,
            system=system,
            messages=[{"role": "user", "content": user}],
        )

        result = json.loads(resp.content[0].text)
        bowl = next((b for b in self.menu if b["id"] == result["bowl_id"]), self.menu[0])
        runner_up = next((b for b in self.menu if b["id"] != bowl["id"]), None)

        return {
            "recommended": bowl,
            "runner_up": runner_up,
            "reason": result["reason"],
            "modifier_suggestion": result.get("modifier_suggestion"),
            "powered_by": "MacaroniIntelligence (Claude)",
        }
