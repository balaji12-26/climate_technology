"""Layer 5 - operational briefing.

1. build_briefing_json(): the ONLY source of facts (all numbers come from the
   plan response, which came from evaluate()).
2. render_template(): deterministic text, works offline with no key.
3. render_llm(): optional Claude formatting of the SAME JSON. The LLM never
   computes; every number in its output is checked against the number set of
   the JSON and the template is used instead if a foreign number appears.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any

REASON_TEXT = {
    "travel_time_increased": "travel time increased",
    "demand_changed": "demand changed",
    "urgency_changed": "urgency changed",
    "capacity_reduced": "per-unit capacity reduced",
    "resource_lost": "resource lost",
    "fuel_reallocated": "fuel budget re-allocated",
    "zone_unreachable": "zone unreachable",
}
RES_LABEL = {"rescue_boat": "rescue boats", "medical_team": "medical teams", "supply_truck": "supply trucks"}


def build_briefing_json(plan: dict, scenario: dict, diff: list[dict] | None = None,
                        input_changes: list[str] | None = None) -> dict[str, Any]:
    m = plan["metrics"]
    by_zone: dict[str, dict] = {}
    for a in plan["allocations"]:
        z = by_zone.setdefault(a["zone"], {"zone": a["zone"], "name": a["zone_name"], "urgency": a["urgency"],
                                            "resources": []})
        if a["units"] > 0 or a["demand"] > 0:
            z["resources"].append({"resource": a["resource"], "units": a["units"], "served": a["served"],
                                   "demand": a["demand"], "unmet": a["unmet"], "travel_h": a["travel_h"]})
    return {
        "scenario_name": scenario.get("name", "scenario"),
        "applied_disruptions": [
            {"id": d["id"], "description": d["description"]}
            for d in scenario.get("disruptions", []) if d["id"] in plan.get("applied_disruptions", [])
        ],
        "status": plan["status"], "method": plan.get("method"), "solve_ms": plan["solve_ms"],
        "planning_window_h": scenario["planning_window_h"],
        "metrics": {
            "weighted_service_pct": m["weighted_service_pct"],
            "critical_demand_served_pct": m["critical_demand_served_pct"],
            "coverage": {r: c["pct"] for r, c in m["coverage"].items()},
            "total_served": m["total_served"],
            "avg_response_h": m["avg_response_h"],
            "fuel_used_l": m["fuel_used_l"], "fuel_budget_l": m["fuel_budget_l"], "fuel_pct": m["fuel_pct"],
            "units_used": m["units_used"], "units_available": m["units_available"],
            "zones_zero_service": m["zones_zero_service"],
        },
        "zones": sorted(by_zone.values(), key=lambda z: -z["urgency"]),
        "unreachable_zones": plan.get("unreachable_zones", []),
        "binding_constraints": [b["detail"] for b in plan.get("binding_constraints", [])],
        "warnings": plan.get("warnings", []),
        "diff": [{"zone": r["zone"], "zone_name": r["zone_name"], "resource": r["resource"],
                  "before": r["before"], "after": r["after"], "delta": r["delta"],
                  "reasons": [REASON_TEXT.get(c, c) for c in r["reason_codes"]]}
                 for r in (diff if diff is not None else plan.get("diff", []))],
        "input_changes": input_changes or [],
    }


def render_template(b: dict[str, Any]) -> str:
    m = b["metrics"]
    lines: list[str] = []
    lines.append(f"OPERATIONAL BRIEFING - {b['scenario_name']}")
    lines.append(f"Planning window {b['planning_window_h']} h. Solver status: {b['status']} ({b['solve_ms']} ms).")
    if b["applied_disruptions"]:
        lines.append("Active disruptions: " + "; ".join(f"{d['id']} {d['description']}" for d in b["applied_disruptions"]) + ".")
    if b["input_changes"]:
        lines.append("What changed: " + "; ".join(b["input_changes"]) + ".")
    lines.append("")
    lines.append("SUMMARY")
    lines.append(f"- Weighted service: {m['weighted_service_pct']}% of urgency-weighted demand; "
                 f"critical-zone demand served: {m['critical_demand_served_pct']}%.")
    cov = m["coverage"]
    lines.append(f"- Coverage: evacuation {cov.get('rescue_boat', 0)}%, treatment {cov.get('medical_team', 0)}%, "
                 f"supply {cov.get('supply_truck', 0)}%. People served: {m['total_served']}.")
    lines.append(f"- Fuel: {m['fuel_used_l']} of {m['fuel_budget_l']} L ({m['fuel_pct']}%). "
                 f"Units deployed: " + ", ".join(f"{m['units_used'][r]}/{m['units_available'][r]} {RES_LABEL.get(r, r)}"
                                                 for r in m["units_used"]) + ".")
    if m["avg_response_h"] is not None:
        lines.append(f"- Average response time (service-weighted): {m['avg_response_h']} h.")
    if m["zones_zero_service"]:
        lines.append(f"- Zones with no service: {', '.join(m['zones_zero_service'])}.")
    if b["unreachable_zones"]:
        lines.append(f"- UNREACHABLE: {', '.join(b['unreachable_zones'])}.")
    lines.append("")
    lines.append("ALLOCATION BY ZONE (highest urgency first)")
    for z in b["zones"]:
        parts = []
        for r in z["resources"]:
            if r["units"] > 0:
                parts.append(f"{r['units']} {RES_LABEL.get(r['resource'], r['resource'])} -> {r['served']}/{r['demand']} served, "
                             f"{r['travel_h']} h travel")
            elif r["demand"] > 0:
                parts.append(f"no {RES_LABEL.get(r['resource'], r['resource'])} ({r['demand']} unmet)")
        lines.append(f"- {z['zone']} {z['name']} (urgency {z['urgency']}): " + ("; ".join(parts) if parts else "no allocation") + ".")
    if b["diff"]:
        lines.append("")
        lines.append("CHANGES VS PREVIOUS PLAN")
        for r in b["diff"]:
            sign = "+" if r["delta"] > 0 else ""
            lines.append(f"- {r['zone']} {r['zone_name']} {RES_LABEL.get(r['resource'], r['resource'])}: "
                         f"{r['before']} -> {r['after']} ({sign}{r['delta']}); reason: {', '.join(r['reasons'])}.")
    if b["binding_constraints"]:
        lines.append("")
        lines.append("BINDING CONSTRAINTS")
        for c in b["binding_constraints"]:
            lines.append(f"- {c}")
    if b["warnings"]:
        lines.append("")
        lines.append("WARNINGS")
        for w in b["warnings"]:
            lines.append(f"- {w}")
    lines.append("")
    lines.append("Decision support on a SIMULATED, Kerala-inspired scenario. All figures are solver output; "
                 "weights are documented policy assumptions.")
    return "\n".join(lines)


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _number_set(obj: Any, acc: set[str] | None = None) -> set[str]:
    """Every numeric literal in the JSON, as canonical strings (ints and 1/2-decimal floats)."""
    acc = set() if acc is None else acc
    if isinstance(obj, bool):
        return acc
    if isinstance(obj, (int, float)):
        acc.add(str(int(obj)) if float(obj).is_integer() else str(obj))
        acc.add(f"{obj:.1f}")
        acc.add(f"{obj:.2f}")
        acc.add(str(abs(obj)))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _number_set(v, acc)
            if isinstance(k, str):
                for n in _NUM_RE.findall(k):
                    acc.add(n)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _number_set(v, acc)
    elif isinstance(obj, str):
        for n in _NUM_RE.findall(obj):
            acc.add(n)
    return acc


def foreign_numbers(text: str, b: dict[str, Any]) -> list[str]:
    allowed = _number_set(b)
    allowed |= {str(b["planning_window_h"])}
    out = []
    for n in _NUM_RE.findall(text):
        n_clean = n.lstrip("-")
        if n_clean in allowed or n in allowed:
            continue
        # allow a zone id like Z1 (digit after Z) and ordinal list numbers 1..9
        out.append(n)
    return out


def _strip_zone_ids(text: str) -> str:
    return re.sub(r"\b[ZDJ]\d+\b", "", text)


LLM_SYSTEM = (
    "You format emergency-response optimizer output into a concise operational briefing for an "
    "emergency operations centre. You receive a JSON object that is the ONLY source of truth. "
    "Rules: use only numbers that appear in the JSON, verbatim; never compute, round, sum, "
    "average or estimate anything; never add facts, recommendations or caveats that are not in "
    "the JSON; keep the zone ids (Z1..Z5) next to the zone names; plain text, no markdown tables, "
    "at most 220 words. Structure: headline, allocation by zone, changes (if any), constraints, warnings."
)


def render_llm(b: dict[str, Any], model: str = "claude-opus-5-5") -> tuple[str | None, str | None]:
    """Return (text, error). Uses the Anthropic SDK if an API key is present; else (None, reason)."""
    if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return None, "no API key configured (ANTHROPIC_API_KEY); using template"
    try:
        import anthropic  # optional dependency
    except ImportError:
        return None, "anthropic SDK not installed; using template"
    try:
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=model, max_tokens=2000, system=LLM_SYSTEM,
            messages=[{"role": "user", "content": "Format this briefing JSON:\n" + json.dumps(b, indent=1)}],
        )
        if resp.stop_reason == "refusal":
            return None, "LLM refused; using template"
        text = "".join(blk.text for blk in resp.content if blk.type == "text").strip()
        if not text:
            return None, "LLM returned no text; using template"
        bad = foreign_numbers(_strip_zone_ids(text), b)
        if bad:
            return None, f"LLM output contained numbers not in the solver JSON ({', '.join(bad[:5])}); using template"
        return text, None
    except anthropic.RateLimitError:
        return None, "LLM rate-limited; using template"
    except anthropic.APIStatusError as e:
        return None, f"LLM API error {e.status_code}; using template"
    except anthropic.APIConnectionError:
        return None, "network unavailable; using template"
    except Exception as e:  # never crash the demo
        return None, f"LLM error {type(e).__name__}; using template"


def briefing(plan: dict, scenario: dict, diff: list[dict] | None = None,
             input_changes: list[str] | None = None, use_llm: bool = False) -> dict:
    b = build_briefing_json(plan, scenario, diff, input_changes)
    template = render_template(b)
    out = {"source": "template", "text": template, "json": b, "llm_note": None}
    if use_llm:
        text, err = render_llm(b)
        if text:
            out.update({"source": "llm", "text": text, "template_text": template})
        else:
            out["llm_note"] = err
    return out
