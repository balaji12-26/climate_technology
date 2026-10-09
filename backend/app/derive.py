"""Layers 1, 1b, 1c combined: everything the optimizer, the baselines and the
evaluator need, computed ONCE per scenario state.

All model coefficients are integers:
  * urgency is stored x10 (one decimal, e.g. 70.8 -> 708)
  * fuel is stored in deciliters
"""
from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal
from dataclasses import dataclass, field

from .routing import shortest_paths
from .scenario import DEMAND_FIELD, RESOURCES


def urgency_score(z: dict, w: dict) -> float:
    """Per-person urgency in [0, 100], quantized to one decimal with exact
    decimal arithmetic (ROUND_HALF_UP) so 45.75 -> 45.8, never 45.7.
    Population is NOT in this score."""
    D = lambda v: Decimal(str(v))  # noqa: E731
    depth_norm = min(D(z["flood_depth_m"]) / D(4), D(1))
    raw = (D(w["depth"]) * depth_norm
           + D(w["infrastructure"]) * D(z["infrastructure_damage"])
           + D(w["medical"]) * D(z["medical_urgency"])
           + D(w["access"]) * D(z["access_difficulty"])
           + D(w["vulnerable"]) * D(z["vulnerable_pct"]))
    return float((D(100) * raw).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def capacity_and_fuel(resource: str, spec: dict, dist_km: float, T: float) -> tuple[float, int, float]:
    """Return (travel_h, capacity_people, fuel_l) for ONE unit sent to a zone dist_km away."""
    t = dist_km / spec["road_speed_kmh"]
    if resource == "rescue_boat":
        op_h = max(0.0, T - t - spec["setup_h"])
        cap = math.floor(spec["people_per_h"] * op_h)
        fuel = 2 * dist_km * spec["fuel_l_per_km"] + spec["fuel_l_per_op_h"] * op_h
    elif resource == "medical_team":
        op_h = max(0.0, T - t - spec["setup_h"])
        cap = math.floor(spec["patients_per_h"] * op_h)
        fuel = 2 * dist_km * spec["fuel_l_per_km"]
    elif resource == "supply_truck":
        trips = math.floor(T / (2 * t + spec["unload_h"]))
        per_trip = math.floor(spec["payload_kg"] / spec["kg_per_person"])
        cap = trips * per_trip
        fuel = trips * 2 * dist_km * spec["fuel_l_per_km"]
    else:
        raise ValueError(resource)
    return t, int(cap), fuel


@dataclass
class Derived:
    zones: list[str]
    resources: list[str]
    zone_name: dict[str, str]
    urgency: dict[str, float]                       # 0..100, float
    urgency10: dict[str, int]                       # integer x10
    priority: dict[str, int]
    available: dict[str, int]
    demand: dict[str, dict[str, int]]               # demand[z][r]
    dist_km: dict[str, float]                       # reachable zones only
    route: dict[str, list[str]]
    reachable: dict[str, bool]
    travel_h: dict[str, dict[str, float]]           # travel_h[z][r] (inf if unreachable)
    capacity: dict[str, dict[str, int]]             # people served per unit
    fuel_l: dict[str, dict[str, float]]
    fuel_dl: dict[str, dict[str, int]]              # integer deciliters
    eligible: dict[str, dict[str, bool]]
    deep_water: dict[str, bool]
    critical: dict[str, bool]                        # urgency >= threshold AND reachable
    fuel_budget_dl: int
    fuel_budget_l: float
    T: float
    T_max: float
    critical_urgency: float = 60.0
    slack_penalty: int = 0
    unreachable_zones: list[str] = field(default_factory=list)

    def coef(self, z: str, r: str) -> int:
        """Objective coefficient per person served (integer)."""
        return self.urgency10[z] * self.priority[r]


def derive(sc: dict) -> Derived:
    T = float(sc["planning_window_h"])
    T_max = float(sc["max_response_h"])
    zones = [z["id"] for z in sc["zones"]]
    resources = [r for r in RESOURCES if r in sc["resources"]]
    dist, routes = shortest_paths(sc)

    urg = {z["id"]: urgency_score(z, sc["urgency_weights"]) for z in sc["zones"]}
    urg10 = {k: int(round(v * 10)) for k, v in urg.items()}
    prio = {r: int(sc["priority_weights"][r]) for r in resources}
    avail = {r: int(sc["resources"][r]["count"]) for r in resources}
    demand = {z["id"]: {r: int(z[DEMAND_FIELD[r]]) for r in resources} for z in sc["zones"]}
    reachable = {z: (z in dist) for z in zones}
    deep = {z["id"]: z["flood_depth_m"] >= sc["deep_water_threshold_m"] for z in sc["zones"]}
    critical = {z: (urg[z] >= sc["critical_urgency"] and reachable[z]) for z in zones}

    travel: dict[str, dict[str, float]] = {}
    cap: dict[str, dict[str, int]] = {}
    fuel_l: dict[str, dict[str, float]] = {}
    fuel_dl: dict[str, dict[str, int]] = {}
    elig: dict[str, dict[str, bool]] = {}
    for z in zones:
        travel[z], cap[z], fuel_l[z], fuel_dl[z], elig[z] = {}, {}, {}, {}, {}
        for r in resources:
            if not reachable[z]:
                travel[z][r], cap[z][r], fuel_l[z][r], fuel_dl[z][r], elig[z][r] = math.inf, 0, 0.0, 0, False
                continue
            t, c, f = capacity_and_fuel(r, sc["resources"][r], dist[z], T)
            travel[z][r], cap[z][r], fuel_l[z][r] = t, c, f
            fuel_dl[z][r] = int(round(f * 10))
            elig[z][r] = (t <= T_max) and (c > 0) and avail[r] > 0 and demand[z][r] > 0

    d = Derived(
        zones=zones, resources=resources,
        zone_name={z["id"]: z["name"] for z in sc["zones"]},
        urgency=urg, urgency10=urg10, priority=prio, available=avail, demand=demand,
        dist_km=dist, route=routes, reachable=reachable, travel_h=travel,
        capacity=cap, fuel_l=fuel_l, fuel_dl=fuel_dl, eligible=elig,
        deep_water=deep, critical=critical,
        fuel_budget_dl=int(round(sc["fuel_budget_l"] * 10)), fuel_budget_l=float(sc["fuel_budget_l"]),
        T=T, T_max=T_max, critical_urgency=float(sc["critical_urgency"]),
        unreachable_zones=[z for z in zones if not reachable[z]],
    )
    # P = 10 x (largest single-unit objective contribution)
    best = 0
    for z in zones:
        for r in resources:
            if elig[z][r]:
                best = max(best, d.coef(z, r) * min(cap[z][r], demand[z][r]))
    d.slack_penalty = 10 * best
    return d
