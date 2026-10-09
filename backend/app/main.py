"""FastAPI application - the frozen API contract.

GET  /api/scenario, POST /api/optimize, POST /api/disrupt, POST /api/reset,
GET  /api/baselines, GET /api/compare, POST /api/explain, POST /api/counterfactual,
GET  /api/rainfall, POST /api/rainfall/toggle, POST /api/briefing, GET /api/uniqueness
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import audit
from .briefing import briefing as make_briefing
from .derive import derive
from .diff import input_changes
from .evaluate import evaluate
from .rainfall import get_rainfall
from .report import metric_deltas, zone_summaries
from .service import SessionState, baseline_plans

app = FastAPI(title="Climate Disaster Response Optimizer", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
STATE = SessionState()


class OptimizeBody(BaseModel):
    priority_weights: dict[str, float] | None = None
    urgency_weights: dict[str, float] | None = None
    reoptimize: bool = False


class DisruptBody(BaseModel):
    id: str


class ExplainBody(BaseModel):
    zone: str
    resource: str


class CounterfactualBody(BaseModel):
    type: str                                   # force_move | param_change | remove_zone | uniqueness
    resource: str | None = None
    from_zone: str | None = None
    to_zone: str | None = None
    units: int = 1
    effect: dict[str, Any] | None = None
    zone: str | None = None


class BriefingBody(BaseModel):
    use_llm: bool = False


class RainfallToggleBody(BaseModel):
    enabled: bool


def _ensure_plan() -> dict:
    if STATE.last_plan is None:
        STATE.run_optimize()
    return STATE.last_plan


def _scenario_payload() -> dict:
    sc = STATE.scenario()
    d = derive(sc)
    return {
        "name": sc["name"], "depot": sc["depot"], "junctions": sc["junctions"], "zones": sc["zones"],
        "zone_summaries": zone_summaries(d), "edges": sc["edges"], "base_edges": STATE.base["edges"],
        "resources": sc["resources"], "priority_weights": sc["priority_weights"],
        "urgency_weights": sc["urgency_weights"], "fuel_budget_l": sc["fuel_budget_l"],
        "planning_window_h": sc["planning_window_h"], "max_response_h": sc["max_response_h"],
        "deep_water_threshold_m": sc["deep_water_threshold_m"], "critical_urgency": sc["critical_urgency"],
        "disruptions": sc["disruptions"], "applied_disruptions": sc["applied_disruptions"],
        "live_rainfall": STATE.live_rainfall, "live_rainfall_adjustment": sc.get("live_rainfall_adjustment", {}),
        "unreachable_zones": d.unreachable_zones,
        "capacity": d.capacity, "fuel_l": {z: {r: round(v, 1) for r, v in row.items()} for z, row in d.fuel_l.items()},
        "travel_h": {z: {r: (None if v == float("inf") else round(v, 2)) for r, v in row.items()} for z, row in d.travel_h.items()},
        "eligible": d.eligible,
    }


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/scenario")
def get_scenario():
    return _scenario_payload()


@app.post("/api/optimize")
def post_optimize(body: OptimizeBody):
    if body.priority_weights is not None:
        STATE.priority_weights.update({k: v for k, v in body.priority_weights.items()})
    if body.urgency_weights is not None:
        STATE.urgency_weights.update({k: v for k, v in body.urgency_weights.items()})
    return STATE.run_optimize(reoptimize=body.reoptimize)


@app.post("/api/disrupt")
def post_disrupt(body: DisruptBody):
    ids = {d["id"] for d in STATE.base["disruptions"]}
    if body.id not in ids:
        return JSONResponse(status_code=400, content={"status": "ERROR", "error": f"unknown disruption {body.id}"})
    _ensure_plan()
    if body.id not in STATE.applied:
        STATE.applied.append(body.id)
    prev_d = STATE.last_derived
    resp = STATE.run_optimize(reoptimize=True)
    resp["input_changes"] = input_changes(prev_d, STATE.last_derived) if prev_d else []
    resp["disruption"] = next(d for d in STATE.base["disruptions"] if d["id"] == body.id)
    return resp


@app.post("/api/reset")
def post_reset():
    STATE.reset()
    return STATE.run_optimize()


@app.get("/api/baselines")
def get_baselines():
    sc = STATE.scenario()
    return baseline_plans(sc)


@app.get("/api/compare")
def get_compare():
    sc = STATE.scenario()
    d = derive(sc)
    plans = baseline_plans(sc, d)
    plans["cp_sat"] = _ensure_plan()
    rows = {name: p["metrics"] for name, p in plans.items()}
    opt = rows["cp_sat"]["objective"]
    return {
        "plans": plans,
        "metrics": rows,
        "objective_gap_pct": {name: (round(100.0 * (opt - r["objective"]) / abs(opt), 2) if opt else None)
                              for name, r in rows.items()},
        "optimizer_dominates": all(opt >= r["objective"] for r in rows.values()),
    }


@app.post("/api/explain")
def post_explain(body: ExplainBody):
    sc = STATE.scenario()
    plan = _ensure_plan()
    d = STATE.last_derived or derive(sc)
    return audit.explain(sc, d, plan["plan"], body.zone, body.resource)


@app.post("/api/counterfactual")
def post_counterfactual(body: CounterfactualBody):
    sc = STATE.scenario()
    plan = _ensure_plan()
    d = STATE.last_derived or derive(sc)
    if body.type == "force_move":
        if not (body.resource and body.from_zone and body.to_zone):
            return JSONResponse(status_code=400, content={"status": "ERROR", "error": "resource, from_zone, to_zone required"})
        return audit.compare_force_move(sc, d, plan["plan"], body.resource, body.from_zone, body.to_zone, body.units)
    if body.type == "param_change":
        if not body.effect:
            return JSONResponse(status_code=400, content={"status": "ERROR", "error": "effect required"})
        return audit.what_if(sc, d, plan["plan"], body.effect)
    if body.type == "remove_zone":
        if not body.zone:
            return JSONResponse(status_code=400, content={"status": "ERROR", "error": "zone required"})
        return audit.remove_zone(sc, d, plan["plan"], body.zone)
    if body.type == "uniqueness":
        return audit.uniqueness(sc, d, plan["plan"])
    return JSONResponse(status_code=400, content={"status": "ERROR", "error": f"unknown type {body.type}"})


@app.get("/api/uniqueness")
def get_uniqueness():
    sc = STATE.scenario()
    plan = _ensure_plan()
    d = STATE.last_derived or derive(sc)
    return audit.uniqueness(sc, d, plan["plan"])


@app.get("/api/rainfall")
def get_rainfall_endpoint(live: bool = True):
    data = get_rainfall(STATE.base["zones"], allow_network=live)
    STATE.rainfall_depth_add = {z["zone"]: z["depth_add_m"] for z in data["zones"]}
    data["enabled"] = STATE.live_rainfall
    return data


@app.post("/api/rainfall/toggle")
def post_rainfall_toggle(body: RainfallToggleBody):
    if body.enabled and not STATE.rainfall_depth_add:
        data = get_rainfall(STATE.base["zones"], allow_network=True)
        STATE.rainfall_depth_add = {z["zone"]: z["depth_add_m"] for z in data["zones"]}
    _ensure_plan()
    STATE.live_rainfall = body.enabled
    resp = STATE.run_optimize(reoptimize=True)
    resp["live_rainfall"] = STATE.live_rainfall
    return resp


@app.post("/api/briefing")
def post_briefing(body: BriefingBody):
    sc = STATE.scenario()
    plan = _ensure_plan()
    return make_briefing(plan, sc, diff=plan.get("diff"), input_changes=plan.get("input_changes"),
                         use_llm=body.use_llm)


# ---- static frontend (built with `npm run build` in ../frontend) ----
DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        target = DIST / full_path
        if full_path and target.is_file():
            return FileResponse(target)
        return FileResponse(DIST / "index.html")
