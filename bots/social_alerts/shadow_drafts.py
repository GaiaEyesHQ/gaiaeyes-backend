#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


CTA = "Open Gaia Eyes for the full signal read."
CONTEXT_LINE = "Context only; not medical advice or a forecast of symptoms."
DEFAULT_HASHTAGS = "#GaiaEyes #SpaceWeather #EarthSignals"
SEVERITY_RANK = {"high": 0, "watch": 1, "info": 2}


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return float(value)
    except Exception:
        return None


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _dig(data: Mapping[str, Any], path: Sequence[str]) -> Any:
    cur: Any = data
    for key in path:
        if isinstance(cur, list):
            try:
                cur = cur[int(key)]
                continue
            except Exception:
                return None
        if not isinstance(cur, Mapping):
            return None
        cur = cur.get(key)
    return cur


def _first(data: Mapping[str, Any], paths: Iterable[Sequence[str]]) -> Any:
    for path in paths:
        value = _dig(data, path)
        if value is not None and value != "":
            return value
    return None


def _first_float(data: Mapping[str, Any], paths: Iterable[Sequence[str]]) -> Optional[float]:
    for path in paths:
        value = _safe_float(_dig(data, path))
        if value is not None:
            return value
    return None


def _fmt_number(value: Optional[float], *, digits: int = 1, suffix: str = "") -> str:
    if value is None:
        return "--"
    if digits == 0:
        rendered = str(int(round(value)))
    else:
        rendered = f"{value:.{digits}f}"
    return f"{rendered}{suffix}"


def _flare_rank(flare_class: str | None) -> tuple[int, float]:
    text = _clean_text(flare_class).upper()
    if not text:
        return (0, 0.0)
    band = text[0]
    try:
        magnitude = float(text[1:] or 0)
    except ValueError:
        magnitude = 0.0
    return ({"A": 0, "B": 1, "C": 2, "M": 3, "X": 4}.get(band, 0), magnitude)


def _event_id(category: str, severity: str, metrics: Mapping[str, Any]) -> str:
    seed = json.dumps({"category": category, "severity": severity, "metrics": metrics}, sort_keys=True, default=str)
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    return f"social_alert.{category}.{severity}.{digest}"


def _source_ref(label: str, path: str) -> Dict[str, str]:
    return {"label": label, "path": path}


def _base_overlay(
    *,
    category: str,
    severity: str,
    title: str,
    subtitle: str,
    chips: List[Dict[str, str]],
    theme_keys: List[str],
    background_candidates: List[str],
) -> Dict[str, Any]:
    return {
        "square_image": {
            "canvas": {"width": 1080, "height": 1080},
            "safe_area": {"left": 96, "right": 96, "top": 104, "bottom": 132},
            "title": title,
            "subtitle": subtitle,
            "metric_chips": chips,
            "footer": "Gaia Eyes - Decode the unseen",
            "theme_keys": theme_keys,
            "background_candidates": background_candidates,
        },
        "story_reel": {
            "canvas": {"width": 1080, "height": 1920},
            "safe_area": {"left": 92, "right": 92, "top": 220, "bottom": 260},
            "frames": [
                {"role": "hook", "text": title},
                {"role": "signal", "text": subtitle, "metric_chips": chips},
                {"role": "cta", "text": CTA},
            ],
            "theme_keys": theme_keys,
            "background_candidates": background_candidates,
            "motion_notes": "Shadow spec only. Use subtle zoom and chip fade-ins when reel rendering is enabled.",
        },
        "rendering_status": "spec_only",
        "category": category,
        "severity": severity,
    }


def _caption(title: str, subtitle: str, *, hashtags: str = DEFAULT_HASHTAGS) -> str:
    return f"{title}. {subtitle} {CTA} {CONTEXT_LINE}\n\n{hashtags}"


def _draft(
    *,
    category: str,
    severity: str,
    title: str,
    subtitle: str,
    metrics: Dict[str, Any],
    chips: List[Dict[str, str]],
    theme_keys: List[str],
    background_candidates: List[str],
    source_refs: List[Dict[str, str]],
    asof: Optional[str],
) -> Dict[str, Any]:
    event_id = _event_id(category, severity, metrics)
    return {
        "id": event_id,
        "mode": "shadow",
        "auto_publish": False,
        "review_status": "needs_human_review",
        "category": category,
        "severity": severity,
        "asof": asof,
        "title": title,
        "subtitle": subtitle,
        "caption": _caption(title, subtitle),
        "metrics": metrics,
        "source_refs": source_refs,
        "overlay_spec": _base_overlay(
            category=category,
            severity=severity,
            title=title,
            subtitle=subtitle,
            chips=chips,
            theme_keys=theme_keys,
            background_candidates=background_candidates,
        ),
        "guardrails": {
            "claim_strength": "context_only",
            "medical_causality": "avoid",
            "requires_review_before_publish": True,
        },
        "dedupe_key": event_id.rsplit(".", 1)[0],
    }


def _asof(snapshot: Mapping[str, Any]) -> Optional[str]:
    value = _first(
        snapshot,
        [
            ("generated_at",),
            ("timestamp_utc",),
            ("asof",),
            ("as_of",),
            ("space_weather", "timestamp_utc"),
            ("space_daily", "updated_at"),
            ("local", "asof"),
        ],
    )
    return _clean_text(value) or None


def _space_drafts(snapshot: Mapping[str, Any], asof: Optional[str]) -> List[Dict[str, Any]]:
    kp = _first_float(
        snapshot,
        [
            ("space_weather", "now", "kp"),
            ("space_weather", "kp_now"),
            ("space_daily", "kp_now"),
            ("space_daily", "kp_max"),
            ("today", "kp"),
            ("kp_now",),
        ],
    )
    kp_max = _first_float(
        snapshot,
        [
            ("space_weather", "last_24h", "kp_max"),
            ("space_weather", "kp_max_24h"),
            ("space_daily", "kp_max"),
            ("kp_max_24h",),
        ],
    )
    kp_signal = max([value for value in (kp, kp_max) if value is not None], default=None)
    bz = _first_float(
        snapshot,
        [
            ("space_weather", "now", "bz_nt"),
            ("space_weather", "bz_now"),
            ("space_weather", "bz_min"),
            ("space_daily", "bz_now"),
            ("space_daily", "bz_min"),
            ("today", "bz_nt"),
            ("bz_now",),
        ],
    )
    solar_wind = _first_float(
        snapshot,
        [
            ("space_weather", "now", "solar_wind_kms"),
            ("space_weather", "solar_wind_kms"),
            ("space_daily", "sw_speed_now_kms"),
            ("space_daily", "sw_speed_avg"),
            ("today", "sw_kms"),
            ("solar_wind_kms",),
        ],
    )
    flare_class = _clean_text(
        _first(
            snapshot,
            [
                ("space_weather", "xray_max_class"),
                ("space_daily", "xray_max_class"),
                ("flares", "max_24h"),
                ("today", "flare_24h"),
                ("flare_24h",),
            ],
        )
    ).upper()

    drafts: List[Dict[str, Any]] = []
    geomagnetic_severity: Optional[str] = None
    if kp_signal is not None:
        if kp_signal >= 6:
            geomagnetic_severity = "high"
        elif kp_signal >= 5:
            geomagnetic_severity = "watch"
    if bz is not None and solar_wind is not None:
        if bz <= -12 or (solar_wind >= 650 and bz <= -8):
            geomagnetic_severity = "high"
        elif bz <= -8 or (solar_wind >= 550 and bz <= -5):
            geomagnetic_severity = geomagnetic_severity or "watch"

    if geomagnetic_severity:
        title = "Geomagnetic conditions are active" if geomagnetic_severity == "watch" else "Geomagnetic storm watch"
        subtitle = "Kp/Bz and solar wind are worth a closer look right now."
        metrics = {"kp": kp, "kp_max_24h": kp_max, "bz_nt": bz, "solar_wind_kms": solar_wind}
        drafts.append(
            _draft(
                category="geomagnetic",
                severity=geomagnetic_severity,
                title=title,
                subtitle=subtitle,
                metrics=metrics,
                chips=[
                    {"label": "Kp", "value": _fmt_number(kp_signal)},
                    {"label": "Bz", "value": _fmt_number(bz, suffix=" nT")},
                    {"label": "SW", "value": _fmt_number(solar_wind, digits=0, suffix=" km/s")},
                ],
                theme_keys=["geomagnetic", "solar", "space_weather"],
                background_candidates=[
                    "nasa/geospace_3h/latest.jpg",
                    "nasa/aia_304/latest.jpg",
                    "aurora/viewline/tonight-north.png",
                ],
                source_refs=[
                    _source_ref("SWPC space weather", "space_weather.now"),
                    _source_ref("Space daily mart", "marts.space_weather_daily"),
                ],
                asof=asof,
            )
        )

    flare_rank = _flare_rank(flare_class)
    flare_severity: Optional[str] = None
    if flare_rank[0] >= 4:
        flare_severity = "high"
    elif flare_rank[0] == 3 and flare_rank[1] >= 5.0:
        flare_severity = "watch"
    if flare_severity:
        title = "Solar flare activity is elevated" if flare_severity == "watch" else "X-class solar flare watch"
        subtitle = "The flare signal is notable; review the live solar context before posting."
        drafts.append(
            _draft(
                category="solar_flare",
                severity=flare_severity,
                title=title,
                subtitle=subtitle,
                metrics={"xray_max_class": flare_class},
                chips=[{"label": "Max flare", "value": flare_class}],
                theme_keys=["solar_flare", "solar", "space_weather"],
                background_candidates=["nasa/aia_304/latest.jpg", "nasa/lasco_c2/latest.jpg"],
                source_refs=[
                    _source_ref("GOES X-ray", "space_weather.xray_max_class"),
                    _source_ref("SWPC flare feed", "GOES_XRS_URL"),
                ],
                asof=asof,
            )
        )

    return drafts


def _schumann_draft(snapshot: Mapping[str, Any], asof: Optional[str]) -> Optional[Dict[str, Any]]:
    zscore = _first_float(
        snapshot,
        [
            ("schumann", "zscore_30d"),
            ("schumann", "variability", "zscore_30d"),
            ("schumann", "signal", "evidence", "zscore_30d"),
        ],
    )
    active_states = snapshot.get("active_states")
    if zscore is None and isinstance(active_states, list):
        for item in active_states:
            if not isinstance(item, Mapping):
                continue
            if item.get("signal_key") == "schumann.variability_24h":
                evidence = item.get("evidence") if isinstance(item.get("evidence"), Mapping) else {}
                zscore = _safe_float(evidence.get("zscore_30d"))
                asof = _clean_text(evidence.get("ts")) or asof
                break
    if zscore is None or zscore < 2.0:
        return None
    severity = "high" if zscore >= 3.0 else "watch"
    value = _first_float(
        snapshot,
        [
            ("schumann", "combined", "f1_hz"),
            ("schumann", "value_hz"),
            ("schumann", "fundamental_hz"),
        ],
    )
    return _draft(
        category="schumann",
        severity=severity,
        title="Schumann variability is elevated" if severity == "watch" else "Schumann spike detected",
        subtitle="The resonance feed is moving more than usual; keep the post observational.",
        metrics={"zscore_30d": zscore, "value_hz": value},
        chips=[
            {"label": "Z-score", "value": _fmt_number(zscore)},
            {"label": "F1", "value": _fmt_number(value, suffix=" Hz")},
        ],
        theme_keys=["schumann", "resonance", "earthscope"],
        background_candidates=[
            "social/earthscope/latest/tomsk_share_latest.jpg",
            "social/earthscope/latest/cumiana_share_latest.jpg",
        ],
        source_refs=[
            _source_ref("Tomsk/Cumiana Schumann", "schumann"),
            _source_ref("Schumann active state", "active_states.schumann.variability_24h"),
        ],
        asof=asof,
    )


def _local_drafts(snapshot: Mapping[str, Any], asof: Optional[str]) -> List[Dict[str, Any]]:
    aqi = _first_float(
        snapshot,
        [
            ("local", "air", "aqi"),
            ("air", "aqi"),
            ("forecast_daily", "0", "aqi_forecast"),
        ],
    )
    drafts: List[Dict[str, Any]] = []
    if aqi is not None and aqi >= 101:
        severity = "high" if aqi >= 151 else "watch"
        drafts.append(
            _draft(
                category="air_quality",
                severity=severity,
                title="Air quality is elevated" if severity == "watch" else "Air quality alert",
                subtitle="Local AQI is high enough to make this a reviewable public post.",
                metrics={"aqi": aqi},
                chips=[{"label": "AQI", "value": _fmt_number(aqi, digits=0)}],
                theme_keys=["aqi", "air_quality", "local_conditions"],
                background_candidates=["social/share/backgrounds/aqi.jpg", "social/share/backgrounds/air_quality.jpg"],
                source_refs=[
                    _source_ref("Local check", "/v1/local/check"),
                    _source_ref("AirNow", "local.air"),
                ],
                asof=asof,
            )
        )

    pollen_level = _clean_text(
        _first(
            snapshot,
            [
                ("local", "allergens", "overall_level"),
                ("allergens", "overall_level"),
                ("local", "forecast_daily", "0", "pollen_overall_level"),
                ("forecast_daily", "0", "pollen_overall_level"),
            ],
        )
    ).lower()
    pollen_index = _first_float(
        snapshot,
        [
            ("local", "allergens", "overall_index"),
            ("allergens", "overall_index"),
            ("local", "forecast_daily", "0", "pollen_overall_index"),
            ("forecast_daily", "0", "pollen_overall_index"),
        ],
    )
    primary = _clean_text(
        _first(
            snapshot,
            [
                ("local", "allergens", "primary_label"),
                ("allergens", "primary_label"),
                ("local", "forecast_daily", "0", "pollen_primary_label"),
                ("forecast_daily", "0", "pollen_primary_label"),
            ],
        )
    )
    pollen_triggered = pollen_level in {"high", "very_high"} or (pollen_index is not None and pollen_index >= 4)
    if pollen_triggered:
        severity = "high" if pollen_level == "very_high" or (pollen_index is not None and pollen_index >= 5) else "watch"
        label = primary or "Pollen"
        drafts.append(
            _draft(
                category="pollen",
                severity=severity,
                title=f"{label} is elevated",
                subtitle="Allergen context is notable locally; avoid symptom-cause language.",
                metrics={"overall_level": pollen_level or None, "overall_index": pollen_index, "primary_label": primary or None},
                chips=[
                    {"label": "Pollen", "value": (pollen_level or "high").replace("_", " ").title()},
                    {"label": "Index", "value": _fmt_number(pollen_index)},
                ],
                theme_keys=["pollen", "allergens", "seasonal_irritants"],
                background_candidates=["social/share/backgrounds/pollen.jpg", "social/share/backgrounds/allergens.jpg"],
                source_refs=[
                    _source_ref("Local check", "/v1/local/check"),
                    _source_ref("Google Pollen", "local.allergens"),
                ],
                asof=asof,
            )
        )

    return drafts


def _quake_draft(snapshot: Mapping[str, Any], asof: Optional[str]) -> Optional[Dict[str, Any]]:
    events = _dig(snapshot, ("quakes", "events"))
    if not isinstance(events, list):
        events = _dig(snapshot, ("quakes", "items"))
    if not isinstance(events, list):
        events = snapshot.get("events") if isinstance(snapshot.get("events"), list) else []
    top_event: Optional[Mapping[str, Any]] = None
    top_mag: Optional[float] = None
    m5_count = 0
    for item in events:
        if not isinstance(item, Mapping):
            continue
        mag = _safe_float(item.get("mag") or item.get("magnitude"))
        if mag is None:
            continue
        if mag >= 5:
            m5_count += 1
        if top_mag is None or mag > top_mag:
            top_mag = mag
            top_event = item
    if top_mag is None:
        top_mag = _first_float(snapshot, [("quakes", "latest", "mag"), ("quake", "mag")])
    if top_mag is None or top_mag < 6.0:
        return None
    severity = "high" if top_mag >= 7.0 else "watch"
    place = _clean_text((top_event or {}).get("place") or (top_event or {}).get("location"))
    title = f"M{top_mag:.1f} earthquake reported"
    subtitle = f"Reported near {place}; use official sources for safety details." if place else "Review official sources before sharing details."
    return _draft(
        category="earthquake",
        severity=severity,
        title=title,
        subtitle=subtitle,
        metrics={"mag": top_mag, "place": place or None, "m5_plus_count": m5_count or None},
        chips=[
            {"label": "Magnitude", "value": f"M{top_mag:.1f}"},
            {"label": "M5+ count", "value": str(m5_count or "--")},
        ],
        theme_keys=["earthquake", "hazards", "earthscope"],
        background_candidates=["social/share/backgrounds/earthquake.jpg", "social/share/backgrounds/earthscope.jpg"],
        source_refs=[
            _source_ref("USGS earthquakes", "/v1/quakes/events"),
            _source_ref("Quake daily mart", "marts.quakes_daily"),
        ],
        asof=_clean_text((top_event or {}).get("time_utc")) or asof,
    )


def _hazard_draft(snapshot: Mapping[str, Any], asof: Optional[str]) -> Optional[Dict[str, Any]]:
    items = _dig(snapshot, ("hazards", "items"))
    if not isinstance(items, list):
        items = _dig(snapshot, ("pulse", "cards"))
    if not isinstance(items, list):
        return None
    notable: List[Mapping[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        severity = _clean_text(item.get("severity")).lower()
        kind = _clean_text(item.get("kind") or item.get("type")).lower()
        if severity in {"red", "orange", "high", "medium"} or kind in {"quake", "global", "severe"}:
            notable.append(item)
    if not notable:
        return None
    high_count = sum(1 for item in notable if _clean_text(item.get("severity")).lower() in {"red", "high"})
    severity = "high" if high_count else "watch"
    first = notable[0]
    kind = _clean_text(first.get("kind") or first.get("type") or "global hazard").replace("_", " ")
    return _draft(
        category="global_hazard",
        severity=severity,
        title="Global hazards are active" if len(notable) > 1 else f"{kind.title()} alert",
        subtitle="Share only verified location and advisory context from official feeds.",
        metrics={"notable_count": len(notable), "high_count": high_count},
        chips=[
            {"label": "Notable", "value": str(len(notable))},
            {"label": "High", "value": str(high_count)},
        ],
        theme_keys=["hazards", "earthscope", "local_conditions"],
        background_candidates=["social/share/backgrounds/hazards.jpg", "social/share/backgrounds/earthscope.jpg"],
        source_refs=[
            _source_ref("Global hazards brief", "/v1/hazards/brief"),
            _source_ref("GDACS hazards", "/v1/hazards/gdacs/full"),
        ],
        asof=asof,
    )


def build_shadow_payload(
    snapshot: Mapping[str, Any],
    *,
    generated_at: Optional[str] = None,
    max_drafts: int = 6,
) -> Dict[str, Any]:
    """Build local-only social alert drafts from existing Gaia Eyes signal payloads."""
    asof = _asof(snapshot)
    drafts: List[Dict[str, Any]] = []
    drafts.extend(_space_drafts(snapshot, asof))
    schumann = _schumann_draft(snapshot, asof)
    if schumann:
        drafts.append(schumann)
    drafts.extend(_local_drafts(snapshot, asof))
    quake = _quake_draft(snapshot, asof)
    if quake:
        drafts.append(quake)
    hazard = _hazard_draft(snapshot, asof)
    if hazard:
        drafts.append(hazard)

    drafts.sort(key=lambda item: (SEVERITY_RANK.get(item.get("severity"), 9), item.get("category") or ""))
    if max_drafts > 0:
        drafts = drafts[:max_drafts]

    return {
        "schema_version": "social_alerts_shadow_v1",
        "mode": "shadow",
        "auto_publish": False,
        "generated_at": generated_at
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source_mode": "existing_signal_snapshot",
        "draft_count": len(drafts),
        "drafts": drafts,
        "review_notes": [
            "Human review is required before any social publish.",
            "Payload is text, metadata, and overlay specs only; no media rendering or platform posting is performed.",
            "Copy intentionally avoids medical causality and symptom prediction.",
        ],
    }


def write_shadow_payload(payload: Mapping[str, Any], output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _default_output_path() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path("tmp") / "social_alerts_shadow" / f"{stamp}.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build shadow-mode social alert drafts from a Gaia Eyes signal JSON snapshot.")
    parser.add_argument("--input", required=True, help="Path to a JSON snapshot from existing Gaia Eyes signal outputs.")
    parser.add_argument("--output", default="", help="Output JSON path. Defaults to tmp/social_alerts_shadow/<timestamp>.json.")
    parser.add_argument("--max-drafts", type=int, default=6, help="Maximum drafts to include.")
    args = parser.parse_args()

    in_path = Path(args.input)
    snapshot = json.loads(in_path.read_text(encoding="utf-8"))
    if not isinstance(snapshot, Mapping):
        raise SystemExit("Input JSON must be an object.")
    payload = build_shadow_payload(snapshot, max_drafts=args.max_drafts)
    out_path = write_shadow_payload(payload, args.output or _default_output_path())
    print(f"[social_alerts.shadow] wrote {payload['draft_count']} draft(s) -> {out_path}")


if __name__ == "__main__":
    main()
