"""THE single evaluate() and validate() used for every plan from every method.

A plan is `dict[zone_id][resource] -> units` (integers). People served are
derived deterministically from units: served = min(capacity x units, demand).
"""
from __future__ import annotations

from .derive import Derived, derive

Plan = dict[str, dict[str, int]]


def empty_plan(d: Derived) -> Plan:
    return {z: {r: 0 for r in d.resources} for z in d.zones}


def normalize_plan(plan: Plan | None, d: Derived) -> Plan:
    out = empty_plan(d)
    if plan:
        for z, row in plan.items():
            if z in out:
                for r, u in row.items():
                    if r in out[z]:
                        out[z][r] = int(u)
    return out


def served_of(plan: Plan, d: Derived) -> dict[str, dict[str, int]]:
    return {z: {r: min(d.capacity[z][r] * plan[z][r], d.demand[z][r]) for r in d.resources} for z in d.zones}


def fuel_used_dl(plan: Plan, d: Derived) -> int:
    return sum(d.fuel_dl[z][r] * plan[z][r] for z in d.zones for r in d.resources)


def slack_of(plan: Plan, d: Derived) -> dict[str, int]:
    """s[z] = 1 when a critical, reachable zone receives no unit at all."""
    return {z: (1 if d.critical[z] and sum(plan[z].values()) == 0 else 0) for z in d.zones}


def service_objective(plan: Plan, d: Derived) -> int:
    """The stated objective: sum u10 x p x y  -  P x sum s. Integer."""
    y = served_of(plan, d)
    obj = sum(d.coef(z, r) * y[z][r] for z in d.zones for r in d.resources)
    obj -= d.slack_penalty * sum(slack_of(plan, d).values())
    return int(obj)


def validate(plan: Plan, sc: dict, d: Derived | None = None) -> list[str]:
    """Return a list of hard-constraint violations (empty list == valid)."""
    d = d or derive(sc)
    plan = normalize_plan(plan, d)
    errs: list[str] = []
    for z in d.zones:
        for r in d.resources:
            u = plan[z][r]
            if not isinstance(u, int) or u < 0:
                errs.append(f"{z}/{r}: units must be a non-negative integer, got {u!r}")
            elif u > 0 and not d.eligible[z][r]:
                errs.append(f"{z}/{r}: {u} unit(s) assigned but pair is ineligible "
                            f"(reachable={d.reachable[z]}, travel_h={d.travel_h[z][r]:.2f}, cap={d.capacity[z][r]})")
    for r in d.resources:  # C1
        tot = sum(plan[z][r] for z in d.zones)
        if tot > d.available[r]:
            errs.append(f"C1 capacity: {r} uses {tot} > available {d.available[r]}")
    used = fuel_used_dl(plan, d)  # C3
    if used > d.fuel_budget_dl:
        errs.append(f"C3 fuel: {used / 10:.1f} L > budget {d.fuel_budget_l:.1f} L")
    for z in d.zones:  # C4
        if d.deep_water[z] and plan[z]["medical_team"] > 2 * plan[z]["rescue_boat"]:
            errs.append(f"C4 access: {z} medical_team {plan[z]['medical_team']} > 2 x rescue_boat {plan[z]['rescue_boat']}")
    return errs


def evaluate(plan: Plan, sc: dict, d: Derived | None = None) -> dict:
    """Score a plan. Every number in the UI metrics panel comes from here."""
    d = d or derive(sc)
    plan = normalize_plan(plan, d)
    y = served_of(plan, d)
    s = slack_of(plan, d)

    num = sum(d.coef(z, r) * y[z][r] for z in d.zones for r in d.resources)
    den = sum(d.coef(z, r) * d.demand[z][r] for z in d.zones for r in d.resources)
    crit_num = sum(d.coef(z, r) * y[z][r] for z in d.zones for r in d.resources if d.urgency[z] >= d.critical_urgency)
    crit_den = sum(d.coef(z, r) * d.demand[z][r] for z in d.zones for r in d.resources if d.urgency[z] >= d.critical_urgency)

    coverage = {}
    for r in d.resources:
        sv = sum(y[z][r] for z in d.zones)
        dm = sum(d.demand[z][r] for z in d.zones)
        coverage[r] = {"served": sv, "demand": dm, "pct": round(100.0 * sv / dm, 1) if dm else 0.0}

    tot_served = sum(y[z][r] for z in d.zones for r in d.resources)
    wt = sum(y[z][r] * d.travel_h[z][r] for z in d.zones for r in d.resources if y[z][r] > 0)
    avg_resp = round(wt / tot_served, 2) if tot_served else None

    unmet = {z: {r: d.demand[z][r] - y[z][r] for r in d.resources} for z in d.zones}
    units_used = {r: sum(plan[z][r] for z in d.zones) for r in d.resources}
    fuel = fuel_used_dl(plan, d) / 10.0

    return {
        "objective": num - d.slack_penalty * sum(s.values()),
        "service_value": num,
        "slack_penalty_total": d.slack_penalty * sum(s.values()),
        "weighted_service_pct": round(100.0 * num / den, 1) if den else 0.0,
        "critical_demand_served_pct": round(100.0 * crit_num / crit_den, 1) if crit_den else 0.0,
        "coverage": coverage,
        "unmet": unmet,
        "zones_zero_service": [z for z in d.zones if sum(plan[z].values()) == 0],
        "critical_zones_unserved": [z for z in d.zones if s[z] == 1],
        "avg_response_h": avg_resp,
        "fuel_used_l": round(fuel, 1),
        "fuel_budget_l": d.fuel_budget_l,
        "fuel_pct": round(100.0 * fuel / d.fuel_budget_l, 1) if d.fuel_budget_l else 0.0,
        "units_used": units_used,
        "units_available": dict(d.available),
        "total_served": tot_served,
    }
