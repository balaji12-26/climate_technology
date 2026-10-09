"""Synthetic random N-zone scenario generator (acceptance test 12: scale check)."""
from __future__ import annotations

import copy
import random

from .scenario import load_base_scenario


def random_scenario(n_zones: int = 50, seed: int = 7) -> dict:
    rng = random.Random(seed)
    base = load_base_scenario()
    sc = copy.deepcopy(base)
    sc["name"] = f"synthetic-{n_zones}"
    sc["zones"], sc["edges"], sc["junctions"], sc["disruptions"] = [], [], [], []
    depot = sc["depot"]["id"]
    for i in range(1, n_zones + 1):
        zid = f"Z{i}"
        sc["zones"].append({
            "id": zid, "name": f"Zone {i}",
            "coordinates": [9.3 + rng.random(), 76.2 + rng.random()],
            "population": rng.randint(5000, 60000),
            "stranded": rng.randint(100, 3000), "patients": rng.randint(10, 200),
            "displaced": rng.randint(2000, 25000),
            "flood_depth_m": round(rng.uniform(0.3, 4.0), 1),
            "infrastructure_damage": round(rng.random(), 2), "medical_urgency": round(rng.random(), 2),
            "access_difficulty": round(rng.random(), 2), "vulnerable_pct": round(rng.uniform(0.1, 0.4), 2),
        })
        # connect to depot directly or via a previous zone, so the graph is connected but non-trivial
        if i <= 5 or rng.random() < 0.3:
            sc["edges"].append({"a": depot, "b": zid, "km": rng.randint(10, 150)})
        else:
            prev = f"Z{rng.randint(1, i - 1)}"
            sc["edges"].append({"a": prev, "b": zid, "km": rng.randint(5, 60)})
        if rng.random() < 0.4 and i > 1:
            other = f"Z{rng.randint(1, i - 1)}"
            sc["edges"].append({"a": other, "b": zid, "km": rng.randint(5, 80)})
    sc["resources"]["rescue_boat"]["count"] = 4 * n_zones
    sc["resources"]["medical_team"]["count"] = n_zones
    sc["resources"]["supply_truck"]["count"] = 2 * n_zones
    sc["fuel_budget_l"] = 350 * n_zones
    return sc
