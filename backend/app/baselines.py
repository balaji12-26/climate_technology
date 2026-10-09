"""Baselines. Identical inputs and constraints as the optimizer; scored by the
same evaluate() and checked by the same validate().

Resource order is boats -> medical -> trucks so that the access coupling
(C4: medical <= 2 x boats in deep water) can be honoured unit by unit.
"""
from __future__ import annotations

from .derive import Derived
from .evaluate import Plan, empty_plan, fuel_used_dl

ORDER = ("rescue_boat", "medical_team", "supply_truck")


def _can_add(plan: Plan, d: Derived, z: str, r: str) -> bool:
    if not d.eligible[z][r]:
        return False
    if sum(plan[zz][r] for zz in d.zones) + 1 > d.available[r]:
        return False
    if fuel_used_dl(plan, d) + d.fuel_dl[z][r] > d.fuel_budget_dl:
        return False
    if r == "medical_team" and d.deep_water[z] and plan[z][r] + 1 > 2 * plan[z]["rescue_boat"]:
        return False
    return True


def _served(plan: Plan, d: Derived, z: str, r: str) -> int:
    return min(d.capacity[z][r] * plan[z][r], d.demand[z][r])


def equal_split(d: Derived) -> Plan:
    """Round-robin units across eligible zones that still have unmet demand.
    A unit is skipped if it would break the fuel or access constraints."""
    plan = empty_plan(d)
    for r in [r for r in ORDER if r in d.resources]:
        zones = [z for z in d.zones if d.eligible[z][r]]
        remaining = d.available[r]
        progress = True
        while remaining > 0 and progress and zones:
            progress = False
            for z in zones:
                if remaining == 0:
                    break
                if _served(plan, d, z, r) >= d.demand[z][r]:
                    continue
                if _can_add(plan, d, z, r):
                    plan[z][r] += 1
                    remaining -= 1
                    progress = True
    return plan


def severity_greedy(d: Derived) -> Plan:
    """Repeatedly add the single unit with the highest marginal objective gain
    (same objective as the optimizer, incl. the soft-minimum penalty) that
    keeps all constraints satisfied. Stops when no unit adds value.

    Marginal gains are computed incrementally (O(1) per candidate) so the
    greedy stays fast on large synthetic scenarios; the result is identical
    to re-evaluating service_objective() after each candidate addition."""
    plan = empty_plan(d)
    used = {r: 0 for r in d.resources}
    fuel = 0
    while True:
        best_gain, best_zr = 0, None
        for z in d.zones:
            zone_units = sum(plan[z].values())
            for r in d.resources:
                if not d.eligible[z][r] or used[r] >= d.available[r]:
                    continue
                if fuel + d.fuel_dl[z][r] > d.fuel_budget_dl:
                    continue
                if r == "medical_team" and d.deep_water[z] and plan[z][r] + 1 > 2 * plan[z]["rescue_boat"]:
                    continue
                x = plan[z][r]
                gain = d.coef(z, r) * (min(d.capacity[z][r] * (x + 1), d.demand[z][r])
                                       - min(d.capacity[z][r] * x, d.demand[z][r]))
                if d.critical[z] and zone_units == 0:
                    gain += d.slack_penalty
                if gain > best_gain:
                    best_gain, best_zr = gain, (z, r)
        if best_zr is None:
            return plan
        z, r = best_zr
        plan[z][r] += 1
        used[r] += 1
        fuel += d.fuel_dl[z][r]
