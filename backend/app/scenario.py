"""Scenario loading and disruption application.

A scenario is a plain dict (see data/scenario.json). Disruptions are applied
cumulatively, always starting from the base scenario, so the state of the
world is fully determined by (base, [applied disruption ids], weight overrides).
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "scenario.json"
RESOURCES = ("rescue_boat", "medical_team", "supply_truck")
DEMAND_FIELD = {"rescue_boat": "stranded", "medical_team": "patients", "supply_truck": "displaced"}


def load_base_scenario(path: Path | str = DATA_PATH) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        sc = json.load(fh)
    sc.setdefault("applied_disruptions", [])
    return sc


def zone_by_id(sc: dict, zid: str) -> dict:
    for z in sc["zones"]:
        if z["id"] == zid:
            return z
    raise KeyError(f"unknown zone {zid}")


def disruption_by_id(sc: dict, did: str) -> dict:
    for d in sc["disruptions"]:
        if d["id"] == did:
            return d
    raise KeyError(f"unknown disruption {did}")


def apply_effect(sc: dict, effect: dict) -> dict:
    """Return a NEW scenario with one effect applied. Effects are generic so the
    what-if endpoint can reuse the same vocabulary as the scripted disruptions."""
    sc = copy.deepcopy(sc)
    if "close_edges" in effect:
        ids = set(effect["close_edges"])
        # Closed roads are REMOVED from the graph (never a sentinel distance).
        sc["edges"] = [e for e in sc["edges"] if e.get("id") not in ids]
    if "close_edges_between" in effect:
        pairs = {frozenset(p) for p in effect["close_edges_between"]}
        sc["edges"] = [e for e in sc["edges"] if frozenset((e["a"], e["b"])) not in pairs]
    if "zone" in effect:
        z = zone_by_id(sc, effect["zone"])
        for k, v in effect.items():
            if k == "zone":
                continue
            if k.endswith("_add"):
                z[k[:-4]] = max(0, z[k[:-4]] + v)
            else:
                z[k] = v
    if "resource" in effect:
        r = sc["resources"][effect["resource"]]
        if "count_add" in effect:
            r["count"] = max(0, r["count"] + int(effect["count_add"]))
        if "count" in effect:
            r["count"] = max(0, int(effect["count"]))
    if "fuel_budget_multiplier" in effect:
        sc["fuel_budget_l"] = int(round(sc["fuel_budget_l"] * float(effect["fuel_budget_multiplier"])))
    if "fuel_budget_l" in effect:
        sc["fuel_budget_l"] = int(effect["fuel_budget_l"])
    if "priority_weights" in effect:
        for k, v in effect["priority_weights"].items():
            if k in sc["priority_weights"]:
                sc["priority_weights"][k] = int(v)
    if "urgency_weights" in effect:
        for k, v in effect["urgency_weights"].items():
            if k in sc["urgency_weights"]:
                sc["urgency_weights"][k] = float(v)
    return sc


def apply_disruptions(base: dict, ids: list[str]) -> dict:
    sc = copy.deepcopy(base)
    for did in ids:
        sc = apply_effect(sc, disruption_by_id(base, did)["effect"])
    sc["applied_disruptions"] = list(ids)
    return sc


def with_weights(sc: dict, priority_weights: dict | None = None,
                 urgency_weights: dict | None = None) -> dict:
    """Return a NEW scenario with adjusted policy weights (UI sliders)."""
    effect: dict[str, Any] = {}
    if priority_weights:
        effect["priority_weights"] = priority_weights
    if urgency_weights:
        effect["urgency_weights"] = urgency_weights
    return apply_effect(sc, effect) if effect else copy.deepcopy(sc)
