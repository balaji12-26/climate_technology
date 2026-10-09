"""Acceptance tests 1-13, 15 from the frozen master prompt (14 lives in test_briefing.py)."""
from __future__ import annotations

import copy
import time

import pytest

from app.audit import uniqueness
from app.baselines import equal_split, severity_greedy
from app.derive import derive
from app.diff import diff_plans
from app.evaluate import evaluate, validate
from app.model import solve
from app.routing import shortest_paths
from app.scenario import apply_disruptions, load_base_scenario, with_weights
from app.service import optimize
from app.synthetic import random_scenario

ALL_DISRUPTIONS = ["D1", "D2", "D3", "D4", "D5"]


@pytest.fixture(scope="module")
def base():
    return load_base_scenario()


def _all_scenarios(base):
    yield "base", base
    for did in ALL_DISRUPTIONS:
        yield did, apply_disruptions(base, [did])
    yield "all", apply_disruptions(base, ALL_DISRUPTIONS)


# 1. Shortest paths
def test_01_shortest_paths(base):
    dist, _ = shortest_paths(base)
    assert dist == {"Z1": 20, "Z3": 50, "Z4": 92, "Z2": 101, "Z5": 95}
    d1, _ = shortest_paths(apply_disruptions(base, ["D1"]))
    assert d1["Z3"] == 110
    assert all(d1[z] == dist[z] for z in ("Z1", "Z2", "Z4", "Z5"))


# 2. Urgency values
def test_02_urgency(base):
    d = derive(base)
    assert {z: round(u, 1) for z, u in d.urgency.items()} == {"Z1": 70.8, "Z2": 64.2, "Z3": 35.6, "Z4": 21.5, "Z5": 44.8}
    d2 = derive(apply_disruptions(base, ["D2"]))
    assert round(d2.urgency["Z4"], 1) == 45.8


# 3. validate() passes for every plan from all three methods, every scenario
@pytest.mark.parametrize("name", ["base"] + ALL_DISRUPTIONS + ["all"])
def test_03_validate_all_methods(base, name):
    sc = base if name == "base" else apply_disruptions(base, ALL_DISRUPTIONS if name == "all" else [name])
    d = derive(sc)
    plans = {"equal_split": equal_split(d), "greedy": severity_greedy(d)}
    res = solve(sc, d)
    assert res.status in ("OPTIMAL", "FEASIBLE"), res
    plans["cp_sat"] = res.plan
    for m, p in plans.items():
        assert validate(p, sc, d) == [], f"{name}/{m}"


# 4. Optimizer objective >= greedy and >= equal split
@pytest.mark.parametrize("name", ["base"] + ALL_DISRUPTIONS + ["all"])
def test_04_optimizer_dominates(base, name):
    sc = base if name == "base" else apply_disruptions(base, ALL_DISRUPTIONS if name == "all" else [name])
    d = derive(sc)
    opt = evaluate(solve(sc, d).plan, sc, d)["objective"]
    assert opt >= evaluate(severity_greedy(d), sc, d)["objective"]
    assert opt >= evaluate(equal_split(d), sc, d)["objective"]


# 5. D1 changes at least one allocation
def test_05_d1_changes_plan(base):
    d0 = derive(base)
    p0 = optimize(base, d0)
    sc1 = apply_disruptions(base, ["D1"])
    d1 = derive(sc1)
    p1 = optimize(sc1, d1, prev_plan=p0["plan"], lam=1, prev_derived=d0)
    assert p1["status"] == "OPTIMAL"
    assert len(p1["diff"]) >= 1, "D1 produced an empty diff: calibrate detour length or F"
    assert all(len(r["reason_codes"]) >= 1 for r in p1["diff"])


# 6. D2 moves at least one medical team to Z4
def test_06_d2_medical_to_z4(base):
    d0 = derive(base)
    p0 = optimize(base, d0)
    sc2 = apply_disruptions(base, ["D2"])
    d2 = derive(sc2)
    p2 = optimize(sc2, d2, prev_plan=p0["plan"], lam=1, prev_derived=d0)
    assert p2["plan"]["Z4"]["medical_team"] >= 1
    assert p2["plan"]["Z4"]["medical_team"] > p0["plan"]["Z4"]["medical_team"]


# 7. D3: truck units <= 7
def test_07_d3_truck_cap(base):
    sc3 = apply_disruptions(base, ["D3"])
    p = optimize(sc3)
    assert p["metrics"]["units_used"]["supply_truck"] <= 7
    assert p["status"] == "OPTIMAL"


# 8. D5: Z5 unreachable, status OPTIMAL, no crash
def test_08_d5_unreachable(base):
    sc5 = apply_disruptions(base, ["D5"])
    p = optimize(sc5)
    assert "Z5" in p["unreachable_zones"]
    assert p["status"] == "OPTIMAL"
    assert all(u == 0 for u in p["plan"]["Z5"].values())


# 9. Starvation scenario
def test_09_starvation(base):
    sc = copy.deepcopy(base)
    for r in sc["resources"].values():
        r["count"] = 1
    sc["fuel_budget_l"] = 100
    p = optimize(sc)
    assert p["status"] == "OPTIMAL"
    assert p["valid"]
    total_unmet = sum(sum(row.values()) for row in p["metrics"]["unmet"].values())
    assert total_unmet > 0
    assert p["metrics"]["fuel_used_l"] <= 100


# 10. Determinism
def test_10_determinism(base):
    plans = [optimize(base)["plan"] for _ in range(5)]
    assert all(p == plans[0] for p in plans)


# 11. Fuel constraint binding in base scenario
def test_11_fuel_binding(base):
    p = optimize(base)
    types = {b["type"] for b in p["binding_constraints"]}
    assert "fuel_binding" in types, p["binding_constraints"]


# 12. Solve time
def test_12_solve_time(base):
    t0 = time.perf_counter()
    p = optimize(base)
    assert (time.perf_counter() - t0) < 3.0
    sc50 = random_scenario(50)
    d50 = derive(sc50)
    t0 = time.perf_counter()
    res = solve(sc50, d50, hint=severity_greedy(d50))
    elapsed = time.perf_counter() - t0
    print(f"\n50-zone scenario: status={res.status} solve_ms={res.solve_ms:.0f} wall={elapsed * 1000:.0f} ms")
    assert res.status in ("OPTIMAL", "FEASIBLE")
    assert elapsed < 3.5
    assert validate(res.plan, sc50, d50) == []


# 13. Re-optimizing with no disruption -> empty diff
def test_13_reopt_no_change_empty_diff(base):
    d = derive(base)
    p0 = optimize(base, d)
    p1 = optimize(base, d, prev_plan=p0["plan"], lam=1, prev_derived=d)
    assert p1["diff"] == []
    assert p1["plan"] == p0["plan"]


# 15. Uniqueness check returns yes/no
def test_15_uniqueness(base):
    d = derive(base)
    p = optimize(base, d)
    u = uniqueness(base, d, p["plan"])
    assert u["answer"] in ("yes", "no")


def test_model_always_feasible_even_when_everything_is_ineligible(base):
    sc = copy.deepcopy(base)
    sc["edges"] = []  # nothing reachable
    p = optimize(sc)
    assert p["status"] == "OPTIMAL"
    assert p["unreachable_zones"] == ["Z1", "Z2", "Z3", "Z4", "Z5"]
    assert p["metrics"]["total_served"] == 0


# 16. D1 then D2 cumulatively at default weights: all 5 medical teams deployed, Z4 gets >= 1
def test_16_d1_d2_all_medical_deployed(base):
    d0 = derive(base)
    p0 = optimize(base, d0)
    sc1 = apply_disruptions(base, ["D1"])
    d1 = derive(sc1)
    p1 = optimize(sc1, d1, prev_plan=p0["plan"], lam=1, prev_derived=d0)
    sc12 = apply_disruptions(base, ["D1", "D2"])
    d12 = derive(sc12)
    p12 = optimize(sc12, d12, prev_plan=p1["plan"], lam=1, prev_derived=d1)
    assert p12["status"] == "OPTIMAL"
    assert p12["metrics"]["units_used"]["medical_team"] == 5
    assert p12["plan"]["Z4"]["medical_team"] >= 1


# 17. Robustness margin: D1+D2 allocation identical at medical priority 150, 200, 300
def test_17_medical_priority_robustness(base):
    sc12 = apply_disruptions(base, ["D1", "D2"])
    plans = []
    for pri in (150, 200, 300):
        sc = with_weights(sc12, priority_weights={"medical_team": pri})
        p = optimize(sc)
        assert p["status"] == "OPTIMAL"
        plans.append(p["plan"])
    assert plans[0] == plans[1] == plans[2]
