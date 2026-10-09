"""Layer 5 - live rainfall from Open-Meteo (free, no key, non-commercial use).

The demo never depends on the network: the last successful response is cached
to data/rainfall_cache.json and a seeded cache ships with the repo.

Documented adjustment rule (only when the UI toggle is ON):
    flood_depth_m += min(rain_mm_last_24h / 100, 1.0)
i.e. +0.1 m per 10 mm of 24-hour rainfall, capped at +1.0 m.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "rainfall_cache.json"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_S = 6
DEPTH_PER_MM = 0.01   # metres per mm
DEPTH_CAP_M = 1.0


def depth_adjustment_m(rain_mm_24h: float) -> float:
    return round(min(rain_mm_24h * DEPTH_PER_MM, DEPTH_CAP_M), 2)


def _load_cache() -> dict | None:
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _save_cache(data: dict) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=1)
    except Exception:
        pass


def fetch_live(zones: list[dict]) -> dict:
    """Query Open-Meteo for all zones in one request. Raises on any failure."""
    import requests  # local import so the module loads without network libs in tests

    lats = ",".join(str(z["coordinates"][0]) for z in zones)
    lons = ",".join(str(z["coordinates"][1]) for z in zones)
    params = {"latitude": lats, "longitude": lons, "hourly": "precipitation",
              "past_hours": 24, "forecast_hours": 1, "timezone": "UTC"}
    r = requests.get(OPEN_METEO_URL, params=params, timeout=TIMEOUT_S)
    r.raise_for_status()
    payload = r.json()
    results = payload if isinstance(payload, list) else [payload]
    if len(results) != len(zones):
        raise ValueError(f"expected {len(zones)} locations, got {len(results)}")
    out_zones = []
    for z, res in zip(zones, results):
        vals = [v for v in res["hourly"]["precipitation"][:24] if v is not None]
        mm = round(float(sum(vals)), 1)
        out_zones.append({"zone": z["id"], "name": z["name"], "coordinates": z["coordinates"],
                          "rain_mm_24h": mm, "depth_add_m": depth_adjustment_m(mm)})
    return {"source": "live", "provider": "Open-Meteo", "fetched_at": datetime.now(timezone.utc).isoformat(),
            "zones": out_zones, "rule": "+0.1 m flood depth per 10 mm of 24-h rain, capped at +1.0 m"}


def get_rainfall(zones: list[dict], allow_network: bool = True) -> dict:
    """Live data if possible, else cached data, else a zero-rain stub. Never raises."""
    if allow_network:
        try:
            t0 = time.perf_counter()
            data = fetch_live(zones)
            data["latency_ms"] = round((time.perf_counter() - t0) * 1000)
            _save_cache(data)
            return data
        except Exception as exc:
            err = f"{type(exc).__name__}: {exc}"[:200]
    else:
        err = "network disabled"
    cached = _load_cache()
    if cached:
        cached = dict(cached)
        cached["source"] = "cached"
        cached["error"] = err
        return cached
    return {"source": "stub", "provider": "none", "error": err, "fetched_at": None,
            "zones": [{"zone": z["id"], "name": z["name"], "coordinates": z["coordinates"],
                       "rain_mm_24h": 0.0, "depth_add_m": 0.0} for z in zones],
            "rule": "+0.1 m flood depth per 10 mm of 24-h rain, capped at +1.0 m"}
