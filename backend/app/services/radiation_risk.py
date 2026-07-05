"""Radiation environment ingest, risk scoring, and visualization payloads."""

from __future__ import annotations

import asyncio
import json
import math
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.config import settings

EARTH_RADIUS_KM = 6371
MOCK_ENV_PATH = Path(__file__).resolve().parents[2] / "data" / "radiation-environment.mock.json"
POES_LAT_STEP_DEG = 15
POES_LON_STEP_DEG = 20

NOAA_ENDPOINTS = {
    "solarWindPlasma": "https://services.swpc.noaa.gov/products/solar-wind/plasma-1-day.json",
    "solarWindMag": "https://services.swpc.noaa.gov/products/solar-wind/mag-1-day.json",
    "xrayFlux": "https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json",
    "protonFlux": "https://services.swpc.noaa.gov/json/goes/primary/integral-protons-6-hour.json",
    "kpIndex": "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
}

_environment_cache: dict[str, Any] | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _normalize_lon(lon: float) -> float:
    return ((lon + 180) % 360) - 180


def _level_for_score(score: float) -> str:
    if score >= 82:
        return "CRITICAL"
    if score >= 62:
        return "HIGH"
    if score >= 34:
        return "MEDIUM"
    return "LOW"


def _legacy_risk(level: str) -> str:
    return {
        "LOW": "low",
        "MEDIUM": "elevated",
        "HIGH": "high",
        "CRITICAL": "critical",
    }.get(level, "elevated")


def _action_for_level(level: str) -> str:
    return {
        "LOW": "continue",
        "MEDIUM": "delay compute",
        "HIGH": "migrate workload",
        "CRITICAL": "shutdown sensitive tasks",
    }[level]


async def _read_mock_environment(reason: str = "mock source") -> dict[str, Any]:
    raw = await asyncio.to_thread(MOCK_ENV_PATH.read_text, encoding="utf-8")
    environment = json.loads(raw)
    environment.setdefault("sourceMode", "mock")
    environment.setdefault("ingestStatus", reason)
    environment.setdefault("sources", [str(MOCK_ENV_PATH)])
    return environment


async def _fetch_live_source(client: httpx.AsyncClient, name: str, url: str) -> dict[str, Any]:
    response = await client.get(url)
    response.raise_for_status()
    return {"name": name, "url": url, "data": response.json()}


def _rows_from_product(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, list) or not data:
        return []
    if all(isinstance(item, dict) for item in data):
        return data
    if not isinstance(data[0], list):
        return []
    headers = [str(item) for item in data[0]]
    rows: list[dict[str, Any]] = []
    for row in data[1:]:
        if isinstance(row, list):
            rows.append({header: row[index] if index < len(row) else None for index, header in enumerate(headers)})
    return rows


def _latest(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    return rows[-1] if rows else None


def _parse_solar_wind(plasma: Any, mag: Any) -> dict[str, float | None]:
    plasma_row = _latest(_rows_from_product(plasma)) or {}
    mag_row = _latest(_rows_from_product(mag)) or {}
    return {
        "speedKms": _number(plasma_row.get("speed")),
        "densityPcc": _number(plasma_row.get("density")),
        "btNt": _number(mag_row.get("bt")),
        "bzNt": _number(mag_row.get("bz_gsm") or mag_row.get("bz")),
    }


def _parse_xray_flux(data: Any) -> float | None:
    rows = [row for row in _rows_from_product(data) if str(row.get("energy") or "").lower() in {"0.1-0.8nm", "long"}]
    row = _latest(rows or _rows_from_product(data))
    return _number(row.get("flux")) if row else None


def _parse_proton_flux(data: Any) -> float | None:
    rows = [
        row
        for row in _rows_from_product(data)
        if str(row.get("energy") or "").replace(" ", "") in {">=10MeV", ">10MeV", ">=10"}
    ]
    values = [_number(row.get("flux")) for row in (rows or _rows_from_product(data))[-12:]]
    finite = [value for value in values if value is not None]
    return max(finite) if finite else None


def _parse_kp_index(data: Any) -> float | None:
    row = _latest(_rows_from_product(data))
    if not row:
        return None
    return _number(row.get("kp") or row.get("kp_index") or row.get("estimated_kp"))


async def fetch_radiation_environment() -> dict[str, Any]:
    """Return live NOAA/SWPC drivers with mock fallback and a short cache."""

    global _environment_cache
    mode = settings.robinson_radiation_source.lower()
    now = time.monotonic()
    cache_seconds = max(1, settings.robinson_radiation_cache_seconds)
    if (
        _environment_cache
        and _environment_cache["mode"] == mode
        and now - _environment_cache["created_at"] < cache_seconds
    ):
        return deepcopy(_environment_cache["environment"])

    if mode == "mock":
        environment = await _read_mock_environment()
        _environment_cache = {"mode": mode, "created_at": now, "environment": environment}
        return deepcopy(environment)

    async with httpx.AsyncClient(timeout=settings.robinson_radiation_timeout_seconds) as client:
        results = await asyncio.gather(
            *(_fetch_live_source(client, name, url) for name, url in NOAA_ENDPOINTS.items()),
            return_exceptions=True,
        )

    successful = [result for result in results if isinstance(result, dict)]
    failed = [result for result in results if isinstance(result, Exception)]

    if not successful:
        if mode == "live":
            raise RuntimeError("All live radiation sources failed.")
        environment = await _read_mock_environment("live radiation ingest failed")
        environment["failedSources"] = [str(error) for error in failed]
        _environment_cache = {"mode": mode, "created_at": now, "environment": environment}
        return deepcopy(environment)

    live_data = {result["name"]: result["data"] for result in successful}
    fallback = await _read_mock_environment("partial live ingest")
    proton_flux = _parse_proton_flux(live_data.get("protonFlux"))
    environment = {
        "sourceMode": "live",
        "generatedAt": _now_iso(),
        "ingestStatus": "partial_live" if failed else "live",
        "solarWind": _parse_solar_wind(live_data.get("solarWindPlasma"), live_data.get("solarWindMag")),
        "xrayFluxWattsM2": _parse_xray_flux(live_data.get("xrayFlux")) or fallback.get("xrayFluxWattsM2"),
        "protonFluxPfu": proton_flux if proton_flux is not None else fallback.get("protonFluxPfu"),
        "kpIndex": _parse_kp_index(live_data.get("kpIndex")) or fallback.get("kpIndex"),
        "protonEvent": (proton_flux or 0) >= 10 if proton_flux is not None else fallback.get("protonEvent", False),
        "sources": [result["url"] for result in successful],
        "failedSources": [str(error) for error in failed],
    }
    _environment_cache = {"mode": mode, "created_at": now, "environment": environment}
    return deepcopy(environment)


def _solar_factor(environment: dict[str, Any]) -> float:
    wind = environment.get("solarWind") or {}
    speed = _number(wind.get("speedKms")) or 350
    density = _number(wind.get("densityPcc")) or 3
    bz = _number(wind.get("bzNt")) or 0
    xray = _number(environment.get("xrayFluxWattsM2")) or 0
    protons = _number(environment.get("protonFluxPfu")) or 0
    speed_factor = _clamp((speed - 350) / 450, 0, 1)
    density_factor = _clamp((density - 3) / 18, 0, 1)
    bz_factor = _clamp((-bz - 2) / 8, 0, 1)
    xray_factor = _clamp((math.log10(max(xray, 1e-9)) + 6) / 2, 0, 1)
    proton_factor = _clamp(math.log10(max(protons, 0.1)) / 2, 0, 1)
    event_boost = 0.24 if environment.get("protonEvent") else 0
    return _clamp(speed_factor * 0.24 + density_factor * 0.18 + bz_factor * 0.16 + xray_factor * 0.18 + proton_factor * 0.24 + event_boost, 0, 1)


def _geomagnetic_factor(environment: dict[str, Any]) -> float:
    kp = _number(environment.get("kpIndex")) or 0
    bz = _number((environment.get("solarWind") or {}).get("bzNt")) or 0
    return _clamp((kp - 2) / 7 + max(0, -bz - 3) / 22, 0, 1)


def _operational_integrity_factor(world_state: dict[str, Any]) -> float:
    radiation = world_state.get("radiation") or {}
    ecc = _number(radiation.get("ecc_errors_last_5min")) or 0
    risk = str(radiation.get("risk") or "").lower()
    value = _clamp(ecc / 1200, 0, 1)
    if radiation.get("xid_event"):
        value = max(value, 0.75)
    if any(token in risk for token in ("elevated", "high", "critical")):
        value = max(value, 0.52)
    return value


def _van_allen_factor(point: dict[str, Any]) -> float:
    lat = _number(point.get("lat") or point.get("latDeg")) or 0
    lon = _normalize_lon(_number(point.get("lon") or point.get("lonDeg")) or 0)
    altitude = _number(point.get("alt_km") or point.get("altitudeKm")) or 550
    saa_lat = (lat + 25) / 18
    saa_lon = (_normalize_lon(lon + 45)) / 38
    saa = math.exp(-0.5 * (saa_lat * saa_lat + saa_lon * saa_lon))
    equatorial_belt = math.exp(-0.5 * (lat / 26) ** 2) * 0.42
    altitude_factor = _clamp((altitude - 350) / 900, 0.12, 0.82)
    return _clamp((max(saa, equatorial_belt) * (0.75 + altitude_factor * 0.45)), 0, 1)


def build_trajectory(world_state: dict[str, Any], generated_at: str) -> list[dict[str, Any]]:
    satellite = world_state.get("satellite") or {}
    lat = _number(satellite.get("lat")) or 0
    lon = _number(satellite.get("lon")) or 0
    altitude_km = _number(satellite.get("alt_km")) or 550
    velocity_kms = _number(satellite.get("velocity_km_s")) or 7.67
    circumference_km = 2 * math.pi * (EARTH_RADIUS_KM + altitude_km)
    deg_per_sec = (velocity_kms / circumference_km) * 360
    epoch_ms = int((datetime.fromisoformat(generated_at.replace("Z", "+00:00")).timestamp()) * 1000)

    points: list[dict[str, Any]] = []
    for index in range(13):
        offset_sec = index * 300
        phase = (offset_sec / 3600) * math.pi * 2
        point = {
            "latDeg": round(_clamp(lat + math.sin(phase) * 51.6, -85, 85), 3),
            "lonDeg": round(_normalize_lon(lon + deg_per_sec * offset_sec), 3),
            "altitudeKm": round(altitude_km, 1),
            "timestamp": datetime.fromtimestamp((epoch_ms + offset_sec * 1000) / 1000, timezone.utc).isoformat(),
        }
        points.append(point)
    return points


def _build_band_points(latitude_deg: float, phase_deg: float, amplitude_deg: float = 2.5, step_deg: int = 8) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    for lon in range(-180, 181, step_deg):
        lat = latitude_deg + math.sin(math.radians(lon + phase_deg)) * amplitude_deg
        points.append({"latDeg": round(lat, 3), "lonDeg": float(lon)})
    return points


def _build_ellipse_points(center_lat_deg: float, center_lon_deg: float, radius_lat_deg: float, radius_lon_deg: float, wobble_deg: float) -> list[dict[str, float]]:
    points: list[dict[str, float]] = []
    for index in range(48):
        angle = (index / 48) * math.pi * 2
        points.append(
            {
                "latDeg": round(center_lat_deg + math.sin(angle) * radius_lat_deg, 3),
                "lonDeg": round(_normalize_lon(center_lon_deg + math.cos(angle + math.radians(wobble_deg * 0.12)) * radius_lon_deg), 3),
            }
        )
    points.append(points[0])
    return points


def _flux_color(log_flux: float) -> str:
    if log_flux >= 4.6:
        return "#ff6f4f"
    if log_flux >= 3.6:
        return "#f0b35a"
    if log_flux >= 2.6:
        return "#ffda7a"
    if log_flux >= 1.8:
        return "#65f5c8"
    return "#3f86ff"


def _build_poes_flux_cells(solar: float, geomagnetic: float, timestamp: str) -> list[dict[str, Any]]:
    phase = ((datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp() / 60) % 360)
    cells: list[dict[str, Any]] = []
    for lat_min in range(-90, 90, POES_LAT_STEP_DEG):
        for lon_min in range(-180, 180, POES_LON_STEP_DEG):
            lat_mid = lat_min + POES_LAT_STEP_DEG / 2
            lon_mid = lon_min + POES_LON_STEP_DEG / 2
            auroral = max(0, (abs(lat_mid) - 55) / 28) * geomagnetic
            saa = _van_allen_factor({"latDeg": lat_mid, "lonDeg": lon_mid, "altitudeKm": 550}) * 0.8
            solar_wave = solar * (0.55 + 0.45 * math.sin(math.radians(lon_mid + phase)) ** 2)
            log_flux = 1 + _clamp(auroral * 2.2 + saa * 2.0 + solar_wave * 1.8, 0, 4.7)
            if log_flux < 1.3:
                continue
            cells.append(
                {
                    "latMinDeg": lat_min,
                    "latMaxDeg": lat_min + POES_LAT_STEP_DEG,
                    "lonMinDeg": lon_min,
                    "lonMaxDeg": lon_min + POES_LON_STEP_DEG,
                    "log10Flux": round(log_flux, 2),
                    "normalizedFlux": round((log_flux - 1) / 5, 3),
                    "color": _flux_color(log_flux),
                }
            )
    return cells


def _build_radiation_zones(solar: float, geomagnetic: float, timestamp: str) -> list[dict[str, Any]]:
    phase_deg = ((datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp() / 60) % 360)
    aurora_latitude = 66 - geomagnetic * 12
    aurora_score = round(_clamp(geomagnetic * 100, 0, 100))
    solar_score = round(_clamp(solar * 100, 0, 100))
    zones: list[dict[str, Any]] = [
        {
            "id": "aurora-north",
            "type": "auroral_curtain",
            "cause": "geomagnetic storm",
            "level": _level_for_score(aurora_score),
            "riskScore": aurora_score,
            "color": "#65f5c8",
            "opacity": round(0.18 + geomagnetic * 0.45, 2),
            "altitudeScale": 1.055,
            "widthDeg": round(7 + geomagnetic * 16, 1),
            "thickness": round(0.004 + geomagnetic * 0.006, 4),
            "pulseRate": 0.8,
            "points": _build_band_points(aurora_latitude, phase_deg),
        },
        {
            "id": "aurora-south",
            "type": "auroral_curtain",
            "cause": "geomagnetic storm",
            "level": _level_for_score(aurora_score),
            "riskScore": aurora_score,
            "color": "#7db7ff",
            "opacity": round(0.16 + geomagnetic * 0.42, 2),
            "altitudeScale": 1.055,
            "widthDeg": round(7 + geomagnetic * 15, 1),
            "thickness": round(0.004 + geomagnetic * 0.006, 4),
            "pulseRate": 0.72,
            "points": _build_band_points(-aurora_latitude, phase_deg + 70),
        },
        {
            "id": "south-atlantic-anomaly",
            "type": "particle_hotspot",
            "cause": "Van Allen",
            "level": "HIGH",
            "riskScore": 72,
            "color": "#f0b35a",
            "opacity": 0.5,
            "altitudeScale": 1.045,
            "widthDeg": 18,
            "thickness": 0.008,
            "pulseRate": 0.45,
            "points": _build_ellipse_points(-25, _normalize_lon(-45 + math.sin(math.radians(phase_deg)) * 4), 18, 38, phase_deg),
        },
    ]
    if solar > 0.08:
        zones.append(
            {
                "id": "solar-particle-wash",
                "type": "solar_particle_wash",
                "cause": "solar",
                "level": _level_for_score(solar_score),
                "riskScore": solar_score,
                "color": "#ffda7a",
                "opacity": round(0.12 + solar * 0.38, 2),
                "altitudeScale": 1.07,
                "widthDeg": round(16 + solar * 30, 1),
                "thickness": round(0.006 + solar * 0.008, 4),
                "pulseRate": 1.2,
                "points": _build_band_points(8, phase_deg + 120, 18, 10),
            }
        )
    return zones


def _point_risk_score(solar: float, geomagnetic: float, point: dict[str, Any], integrity: float) -> int:
    return round(_clamp(solar * 35 + geomagnetic * 25 + _van_allen_factor(point) * 32 + integrity * 18, 0, 100))


def compute_radiation_risk(world_state: dict[str, Any], generated_at: str, environment: dict[str, Any]) -> dict[str, Any]:
    solar = _solar_factor(environment)
    geomagnetic = _geomagnetic_factor(environment)
    integrity = _operational_integrity_factor(world_state)
    trajectory = build_trajectory(world_state, generated_at)
    for point in trajectory:
        point["riskScore"] = _point_risk_score(solar, geomagnetic, point, integrity)
        point["level"] = _level_for_score(point["riskScore"])

    satellite = world_state.get("satellite") or {}
    current_van_allen = _van_allen_factor({"lat": satellite.get("lat"), "lon": satellite.get("lon"), "alt_km": satellite.get("alt_km")})
    trajectory_van_allen = max([current_van_allen, *(_van_allen_factor(point) for point in trajectory)])
    score = round(_clamp(solar * 35 + geomagnetic * 25 + trajectory_van_allen * 32 + integrity * 18, 0, 100))
    radiation_level = _level_for_score(score)
    causes = [
        ("solar", solar),
        ("geomagnetic storm", geomagnetic),
        ("Van Allen", max(trajectory_van_allen, integrity * 0.82)),
    ]
    main_cause = sorted(causes, key=lambda item: item[1], reverse=True)[0][0]
    source_text = (
        "NOAA/SWPC partial live ingest"
        if environment.get("sourceMode") == "live" and environment.get("ingestStatus") == "partial_live"
        else "NOAA/SWPC live ingest"
        if environment.get("sourceMode") == "live"
        else "backend fallback ingest"
    )
    zones = _build_radiation_zones(solar, geomagnetic, generated_at)
    flux_cells = _build_poes_flux_cells(solar, geomagnetic, generated_at)
    frame = {
        "id": "latest-poes-style-p6-flux",
        "index": 0,
        "timestamp": generated_at,
        "solarExposure": round(solar, 3),
        "geomagneticStorm": round(geomagnetic, 3),
        "fluxCells": flux_cells,
        "zones": zones,
    }

    return {
        "radiationRiskScore": score,
        "radiationLevel": radiation_level,
        "mainCause": main_cause,
        "recommendedAction": _action_for_level(radiation_level),
        "explanation": (
            f"{source_text}: solar {round(solar * 100)}%, Van Allen "
            f"{round(trajectory_van_allen * 100)}%, geomagnetic {round(geomagnetic * 100)}%, "
            f"ECC/Xid integrity {round(integrity * 100)}%."
        ),
        "components": {
            "solarExposure": round(solar, 3),
            "vanAllenBelt": round(trajectory_van_allen, 3),
            "geomagneticStorm": round(geomagnetic, 3),
            "integrityEvents": round(integrity, 3),
        },
        "inputs": {
            # Snapshot mutable world-state dicts: enrich_agent_world_state assigns this
            # result back into state["radiation"], so live references would create a
            # radiation -> computed_risk -> inputs -> radiationState cycle that breaks
            # json.dumps in agent prompts and event publishing.
            "position": dict(satellite),
            "radiationState": {
                key: value
                for key, value in (world_state.get("radiation") or {}).items()
                if key != "computed_risk"
            },
            "solarWind": environment.get("solarWind"),
            "xrayFluxWattsM2": environment.get("xrayFluxWattsM2"),
            "protonFluxPfu": environment.get("protonFluxPfu"),
            "kpIndex": environment.get("kpIndex"),
            "protonEvent": bool(environment.get("protonEvent")),
            "ingestStatus": environment.get("ingestStatus"),
        },
        "trajectory": trajectory,
        "visualization": {
            "mode": "latest_poes_style_particle_flux_asset",
            "generatedAt": _now_iso(),
            "assetCount": 1,
            "refreshCadenceSeconds": max(1, settings.robinson_radiation_cache_seconds),
            "particleProduct": {
                "style": "NOAA POES MEPED cylindrical particle flux",
                "channel": "P6",
                "species": "protons",
                "energy": "> 6900 keV",
                "detector": "zenith 0 deg",
                "scale": "log10 protons/cm2/s/ster",
                "grid": {"latitudeStepDeg": POES_LAT_STEP_DEG, "longitudeStepDeg": POES_LON_STEP_DEG},
            },
            "liveImageAvailability": {
                "exactPoesCylindricalImageFeed": False,
                "reason": "NOAA/NCEI POES cylindrical maps are archive/browse products; Robinson generates a latest POES-style asset from NOAA/SWPC drivers.",
            },
            "note": "Backend-modeled POES-style particle flux overlay from live or fallback space-weather drivers.",
            "latestAsset": frame,
            "zones": zones,
            "frames": [frame],
            "trajectory": trajectory,
        },
        "sources": environment.get("sources") or [],
        "sourceMode": environment.get("sourceMode"),
        "generatedAt": _now_iso(),
        "legacyRadiationRisk": _legacy_risk(radiation_level),
    }


async def get_radiation_risk_for_state(world_state: dict[str, Any], generated_at: str | None = None) -> dict[str, Any]:
    timestamp = generated_at or _now_iso()
    environment = await fetch_radiation_environment()
    return compute_radiation_risk(world_state, timestamp, environment)
