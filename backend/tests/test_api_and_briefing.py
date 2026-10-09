"""Acceptance test 14 (briefing offline, no key) plus API contract tests."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from app import main
from app.briefing import _number_set, briefing, build_briefing_json, foreign_numbers
from app.rainfall import get_rainfall
from app.scenario import load_base_scenario
from app.service import optimize


@pytest.fixture()
def client():
    main.STATE.reset()
    return TestClient(main.app)


# 14. Briefing template works with network disabled and no API key
def test_14_briefing_template_offline(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    sc = load_base_scenario()
    plan = optimize(sc)
    out = briefing(plan, sc, use_llm=True)        # asks for LLM, must fall back cleanly
    assert out["source"] == "template"
    assert out["llm_note"] is not None
    assert "OPERATIONAL BRIEFING" in out["text"]
    assert str(plan["metrics"]["weighted_service_pct"]) in out["text"]
    # the template itself introduces no numbers that are not in the JSON
    assert foreign_numbers(out["text"].replace("Z1", "").replace("Z2", "").replace("Z3", "")
                           .replace("Z4", "").replace("Z5", ""), out["json"]) == []


def test_foreign_number_guard():
    sc = load_base_scenario()
    plan = optimize(sc)
    b = build_briefing_json(plan, sc)
    # 1. the live metric, formatted exactly as the template formats it, is not foreign
    live = b["metrics"]["weighted_service_pct"]
    sentence = f"Weighted service: {live}% of urgency-weighted demand"
    assert foreign_numbers(sentence, b) == []
    # 2. a number verified absent from the solver JSON is flagged
    absent = "99.9"
    assert absent not in _number_set(b), "pick a different probe value: 99.9 occurs in the JSON"
    assert foreign_numbers(f"We expect {absent}% coverage", b) == [absent]


def test_rainfall_offline_fallback():
    sc = load_base_scenario()
    data = get_rainfall(sc["zones"], allow_network=False)
    assert data["source"] in ("cached", "stub")
    assert len(data["zones"]) == 5
    assert all(0.0 <= z["depth_add_m"] <= 1.0 for z in data["zones"])


def test_api_flow(client):
    r = client.get("/api/scenario"); assert r.status_code == 200
    assert [z["id"] for z in r.json()["zones"]] == ["Z1", "Z2", "Z3", "Z4", "Z5"]

    p = client.post("/api/optimize", json={}).json()
    assert p["status"] == "OPTIMAL" and p["valid"]
    base_obj = p["metrics"]["objective"]

    d1 = client.post("/api/disrupt", json={"id": "D1"}).json()
    assert d1["status"] == "OPTIMAL" and d1["applied_disruptions"] == ["D1"]
    assert len(d1["diff"]) >= 1 and all(r["reason_codes"] for r in d1["diff"])

    d2 = client.post("/api/disrupt", json={"id": "D2"}).json()
    assert d2["applied_disruptions"] == ["D1", "D2"]          # cumulative
    z4 = next(a for a in d2["allocations"] if a["zone"] == "Z4" and a["resource"] == "medical_team")
    assert z4["demand"] == 180                                  # D2 effect visible through the API

    cmp_ = client.get("/api/compare").json()
    assert cmp_["optimizer_dominates"]
    assert set(cmp_["metrics"]) == {"equal_split", "severity_greedy", "cp_sat"}

    ex = client.post("/api/explain", json={"zone": "Z1", "resource": "medical_team"}).json()
    assert ex["status"] == "OK" and ex["units"] >= 0

    cf = client.post("/api/counterfactual", json={"type": "force_move", "resource": "medical_team",
                                                   "from_zone": "Z1", "to_zone": "Z2"}).json()
    assert cf["status"] in ("OPTIMAL", "FEASIBLE", "INFEASIBLE", "ERROR")
    if cf["status"] in ("OPTIMAL", "FEASIBLE"):
        assert cf["objective_delta"] <= 0

    wi = client.post("/api/counterfactual", json={"type": "param_change",
                                                   "effect": {"resource": "rescue_boat", "count_add": -2}}).json()
    assert wi["status"] == "OPTIMAL" and wi["objective_delta"] <= 0

    u = client.get("/api/uniqueness").json()
    assert u["answer"] in ("yes", "no")

    br = client.post("/api/briefing", json={"use_llm": False}).json()
    assert br["source"] == "template" and "CHANGES VS PREVIOUS PLAN" in br["text"]

    rs = client.post("/api/reset").json()
    assert rs["applied_disruptions"] == [] and rs["metrics"]["objective"] == base_obj

    bad = client.post("/api/disrupt", json={"id": "D9"})
    assert bad.status_code == 400 and bad.json()["status"] == "ERROR"


def test_api_weight_change_reruns_solver(client):
    p0 = client.post("/api/optimize", json={}).json()
    p1 = client.post("/api/optimize", json={"priority_weights": {"supply_truck": 100}}).json()
    assert p1["weights"]["priority"]["supply_truck"] == 100
    assert p1["status"] == "OPTIMAL"
    assert p1["metrics"]["coverage"]["supply_truck"]["pct"] >= p0["metrics"]["coverage"]["supply_truck"]["pct"]


def test_api_d5_unreachable_and_rainfall_toggle(client):
    client.post("/api/optimize", json={})
    d5 = client.post("/api/disrupt", json={"id": "D5"}).json()
    assert "Z5" in d5["unreachable_zones"] and d5["status"] == "OPTIMAL"
    rf = client.get("/api/rainfall", params={"live": "false"}).json()
    assert rf["source"] in ("cached", "stub")
    t = client.post("/api/rainfall/toggle", json={"enabled": True}).json()
    assert t["status"] == "OPTIMAL" and t["live_rainfall"] is True
    t = client.post("/api/rainfall/toggle", json={"enabled": False}).json()
    assert t["live_rainfall"] is False
