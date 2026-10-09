"""Layer 3 - plan diff with deterministic reason codes.

Reason codes are derived by comparing the derived inputs before and after, never
by the LLM:  travel_time_increased | demand_changed | urgency_changed |
capacity_reduced | resource_lost | fuel_reallocated | zone_unreachable
"""
from __future__ import annotations

import math

from .derive import Derived
from .evaluate import Plan, normalize_plan


def reason_codes(z: str, r: str, db: Derived, da: Derived) -> list[str]:
    codes: list[str] = []
    if not da.reachable[z]:
        codes.append("zone_unreachable")
    if da.available[r] < db.available[r]:
        codes.append("resource_lost")
    tb, ta = db.travel_h[z][r], da.travel_h[z][r]
    if da.reachable[z] and db.reachable[z] and ta > tb + 1e-9:
        codes.append("travel_time_increased")
    if da.reachable[z] and db.reachable[z] and da.capacity[z][r] < db.capacity[z][r]:
        codes.append("capacity_reduced")
    if da.demand[z][r] != db.demand[z][r]:
        codes.append("demand_changed")
    if da.urgency10[z] != db.urgency10[z]:
        codes.append("urgency_changed")
    if da.fuel_budget_dl != db.fuel_budget_dl or not codes:
        # fuel (C3) and access (C4) couple every pair: a change elsewhere frees or
        # consumes budget here, so a pair whose own inputs did not change moved
        # because the budget was re-allocated.
        codes.append("fuel_reallocated")
    return codes


def diff_plans(before: Plan, after: Plan, db: Derived, da: Derived) -> list[dict]:
    before = normalize_plan(before, da) if set(before) == set(da.zones) else normalize_plan(before, db)
    after = normalize_plan(after, da)
    rows: list[dict] = []
    for z in da.zones:
        for r in da.resources:
            b, a = before.get(z, {}).get(r, 0), after[z][r]
            if a != b:
                rows.append({
                    "zone": z, "zone_name": da.zone_name[z], "resource": r,
                    "before": b, "after": a, "delta": a - b,
                    "reason_codes": reason_codes(z, r, db, da),
                    "travel_h_before": None if math.isinf(db.travel_h[z][r]) else round(db.travel_h[z][r], 2),
                    "travel_h_after": None if math.isinf(da.travel_h[z][r]) else round(da.travel_h[z][r], 2),
                })
    return rows


def input_changes(db: Derived, da: Derived) -> list[str]:
    """Human-readable list of what changed in the inputs (used by the briefing)."""
    out: list[str] = []
    for z in da.zones:
        if db.reachable[z] and not da.reachable[z]:
            out.append(f"{z} ({da.zone_name[z]}) is now unreachable")
        elif da.reachable[z] and db.reachable[z] and da.dist_km[z] != db.dist_km[z]:
            out.append(f"{z} ({da.zone_name[z]}) route {db.dist_km[z]:.0f} km -> {da.dist_km[z]:.0f} km")
        if da.urgency10[z] != db.urgency10[z]:
            out.append(f"{z} urgency {db.urgency[z]:.1f} -> {da.urgency[z]:.1f}")
        for r in da.resources:
            if da.demand[z][r] != db.demand[z][r]:
                out.append(f"{z} {r} demand {db.demand[z][r]} -> {da.demand[z][r]}")
    for r in da.resources:
        if da.available[r] != db.available[r]:
            out.append(f"{r} available {db.available[r]} -> {da.available[r]}")
    if da.fuel_budget_dl != db.fuel_budget_dl:
        out.append(f"fuel budget {db.fuel_budget_l:.0f} L -> {da.fuel_budget_l:.0f} L")
    return out
