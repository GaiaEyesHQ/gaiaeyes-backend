#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


CTA = "Open Gaia Eyes for the full signal read."
DEFAULT_HASHTAGS = "#GaiaEyes #SpaceWeather #EarthSignals"
SEVERITY_RANK = {"high": 0, "watch": 1, "info": 2}
SOCIAL_BACKGROUND_PREFIX = "social/share/backgrounds"
VISUAL_STYLE = {
    "layout": "background_image_with_flowing_pill_blocks",
    "notes": "Use a dark, cinematic background with translucent rounded metric pills and small glass blocks that match the Gaia Eyes app style.",
}
BACKGROUND_KEYWORDS = {
    "geomagnetic": ["space_weather", "kp", "bz", "solar_wind"],
    "solar_flare": ["solar_flare", "space_weather"],
    "cme": ["cme", "space_weather", "solar_wind"],
    "schumann": ["schumann", "earthscope"],
    "earthquake": ["earthquake", "hazards"],
    "global_hazard": ["hazards", "earthscope"],
}
MEDIA_ASSETS = {
    "solar_flare": {
        "videos": ["nasa/ccor1/latest.mp4", "nasa/enlil/latest.mp4"],
        "stills": ["nasa/ccor1/latest.jpg", "nasa/enlil/latest.jpg", "nasa/aia_304/latest.jpg"],
    },
    "cme": {
        "videos": ["nasa/ccor1/latest.mp4", "nasa/enlil/latest.mp4"],
        "stills": ["nasa/ccor1/latest.jpg", "nasa/enlil/latest.jpg"],
    },
    "schumann": {
        "videos": [],
        "stills": ["schumann/latest/tomsk_share_latest.jpg", "social/earthscope/latest/tomsk_share_latest.jpg"],
    },
}


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


def _viral_background_candidate(kind: str) -> Optional[str]:
    media_roots = [
        Path(os.getenv("MEDIA_REPO_PATH", "/Users/jenniferobrien/Documents/gaiaeyes-media")).expanduser(),
        Path(__file__).resolve().parents[2] / "gaiaeyes-media",
    ]
    subdir = "wide"
    if kind == "square":
        subdir = "square"
    elif kind == "tall":
        subdir = "tall"
    for media_root in media_roots:
        base = media_root / "backgrounds" / subdir
        if not base.exists():
            continue
        files = sorted(path for path in base.glob("*.*") if path.suffix.lower() in {".jpg", ".jpeg", ".png"})
        if not files:
            continue
        try:
            return f"media_repo:{files[0].relative_to(media_root).as_posix()}"
        except Exception:
            return str(files[0])

    return None


def _background_paths_for_keywords(keywords: Sequence[str]) -> List[str]:
    return [f"{SOCIAL_BACKGROUND_PREFIX}/{keyword}.jpg" for keyword in keywords]


def _social_background_candidates(keywords: Sequence[str], fallbacks: Sequence[str]) -> List[str]:
    candidates: List[str] = []
    for candidate in _background_paths_for_keywords(keywords):
        if candidate not in candidates:
            candidates.append(candidate)
    for kind in ("square", "tall"):
        candidate = _viral_background_candidate(kind)
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    for fallback in fallbacks:
        if fallback not in candidates:
            candidates.append(fallback)
    return candidates


def _base_overlay(
    *,
    category: str,
    severity: str,
    title: str,
    subtitle: str,
    chips: List[Dict[str, str]],
    theme_keys: List[str],
    background_candidates: List[str],
    background_keywords: List[str],
    media_assets: Optional[Mapping[str, Sequence[str]]] = None,
) -> Dict[str, Any]:
    assets = media_assets or {}
    videos = list(assets.get("videos") or [])
    stills = list(assets.get("stills") or [])
    return {
        "square_image": {
            "canvas": {"width": 1080, "height": 1080},
            "safe_area": {"left": 96, "right": 96, "top": 104, "bottom": 132},
            "visual_style": VISUAL_STYLE,
            "title": title,
            "subtitle": subtitle,
            "metric_chips": chips,
            "footer": "Gaia Eyes - Decode the unseen",
            "theme_keys": theme_keys,
            "background_keywords": background_keywords,
            "background_candidates": background_candidates,
            "background_source": "gaiaeyes-media/backgrounds/{square,tall}; compatible with gaia_eyes_viral_bot.py",
            "still_candidates": stills,
        },
        "story_reel": {
            "canvas": {"width": 1080, "height": 1920},
            "safe_area": {"left": 92, "right": 92, "top": 220, "bottom": 260},
            "visual_style": VISUAL_STYLE,
            "frames": [
                {"role": "hook", "text": title},
                {"role": "signal", "text": subtitle, "metric_chips": chips},
                {"role": "cta", "text": CTA},
            ],
            "theme_keys": theme_keys,
            "background_keywords": background_keywords,
            "background_candidates": background_candidates,
            "background_source": "gaiaeyes-media/backgrounds/{square,tall}; compatible with gaia_eyes_viral_bot.py",
            "video_candidates": videos,
            "still_candidates": stills,
            "motion_notes": "Shadow spec only. Use subtle zoom and chip fade-ins when reel rendering is enabled.",
        },
        "rendering_status": "spec_only",
        "category": category,
        "severity": severity,
    }


def _caption(title: str, subtitle: str, *, hashtags: str = DEFAULT_HASHTAGS) -> str:
    return f"{title}. {subtitle} {CTA}\n\n{hashtags}"


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
    background_keywords: Optional[List[str]] = None,
    media_assets: Optional[Mapping[str, Sequence[str]]] = None,
) -> Dict[str, Any]:
    event_id = _event_id(category, severity, metrics)
    resolved_background_keywords = background_keywords or BACKGROUND_KEYWORDS.get(category, [])
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
            background_keywords=resolved_background_keywords,
            media_assets=media_assets,
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
    cmes_count = _first_float(
        snapshot,
        [
            ("space_weather", "cmes_count"),
            ("space_daily", "cmes_count"),
            ("cmes", "count_24h"),
            ("today", "cmes_24h"),
            ("cmes_count",),
        ],
    )
    cmes_max_speed = _first_float(
        snapshot,
        [
            ("space_weather", "cmes_max_speed_kms"),
            ("space_daily", "cmes_max_speed_kms"),
            ("cmes", "max_speed_kms"),
            ("cmes_max_speed_kms",),
        ],
    )

    drafts: List[Dict[str, Any]] = []
    geomagnetic_severity: Optional[str] = None
    if kp_signal is not None:
        if kp_signal >= 5:
            geomagnetic_severity = "high"
        elif kp_signal >= 3.5:
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
                background_candidates=_social_background_candidates(
                    BACKGROUND_KEYWORDS["geomagnetic"],
                    [
                        "nasa/geospace_3h/latest.jpg",
                        "nasa/aia_304/latest.jpg",
                        "aurora/viewline/tonight-north.png",
                    ]
                ),
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
                background_candidates=_social_background_candidates(
                    BACKGROUND_KEYWORDS["solar_flare"],
                    [
                        "nasa/ccor1/latest.jpg",
                        "nasa/enlil/latest.jpg",
                        "nasa/aia_304/latest.jpg",
                        "nasa/lasco_c2/latest.jpg",
                    ],
                ),
                source_refs=[
                    _source_ref("GOES X-ray", "space_weather.xray_max_class"),
                    _source_ref("SWPC flare feed", "GOES_XRS_URL"),
                ],
                asof=asof,
                media_assets=MEDIA_ASSETS["solar_flare"],
            )
        )

    cme_severity: Optional[str] = None
    if cmes_count is not None:
        if cmes_count >= 3:
            cme_severity = "high"
        elif cmes_count >= 1:
            cme_severity = "watch"
    if cmes_max_speed is not None:
        if cmes_max_speed >= 1000:
            cme_severity = "high"
        elif cmes_max_speed >= 600:
            cme_severity = cme_severity or "watch"
    if cme_severity:
        title = "CME activity is on the board" if cme_severity == "watch" else "CME activity is elevated"
        subtitle = "Review coronagraph and ENLIL context before sharing."
        drafts.append(
            _draft(
                category="cme",
                severity=cme_severity,
                title=title,
                subtitle=subtitle,
                metrics={"cmes_count": cmes_count, "cmes_max_speed_kms": cmes_max_speed},
                chips=[
                    {"label": "CMEs", "value": _fmt_number(cmes_count, digits=0)},
                    {"label": "Max speed", "value": _fmt_number(cmes_max_speed, digits=0, suffix=" km/s")},
                ],
                theme_keys=["cme", "solar", "space_weather"],
                background_candidates=_social_background_candidates(
                    BACKGROUND_KEYWORDS["cme"],
                    ["nasa/ccor1/latest.jpg", "nasa/enlil/latest.jpg"],
                ),
                source_refs=[
                    _source_ref("CCOR-1", "nasa/ccor1/latest.mp4"),
                    _source_ref("ENLIL", "nasa/enlil/latest.mp4"),
                ],
                asof=asof,
                media_assets=MEDIA_ASSETS["cme"],
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
        background_candidates=_social_background_candidates(
            BACKGROUND_KEYWORDS["schumann"],
            [
                "schumann/latest/tomsk_share_latest.jpg",
                "social/earthscope/latest/tomsk_share_latest.jpg",
                "social/earthscope/latest/cumiana_share_latest.jpg",
            ]
        ),
        source_refs=[
            _source_ref("Tomsk/Cumiana Schumann", "schumann"),
            _source_ref("Schumann active state", "active_states.schumann.variability_24h"),
        ],
        asof=asof,
        media_assets=MEDIA_ASSETS["schumann"],
    )


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
        background_candidates=_social_background_candidates(
            BACKGROUND_KEYWORDS["earthquake"],
            ["social/share/backgrounds/earthquake.jpg", "social/share/backgrounds/earthscope.jpg"],
        ),
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
        background_candidates=_social_background_candidates(
            BACKGROUND_KEYWORDS["global_hazard"],
            ["social/share/backgrounds/hazards.jpg", "social/share/backgrounds/earthscope.jpg"],
        ),
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


def build_review_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# Social Alerts Shadow Review",
        "",
        f"- Mode: `{payload.get('mode', 'shadow')}`",
        f"- Auto publish: `{payload.get('auto_publish', False)}`",
        f"- Generated at: `{payload.get('generated_at') or '--'}`",
        f"- Draft count: `{payload.get('draft_count', 0)}`",
        "",
    ]
    drafts = payload.get("drafts") if isinstance(payload.get("drafts"), list) else []
    if not drafts:
        lines.extend(["No reviewable drafts were generated.", ""])
        return "\n".join(lines)

    for index, draft in enumerate(drafts, start=1):
        if not isinstance(draft, Mapping):
            continue
        overlay = draft.get("overlay_spec") if isinstance(draft.get("overlay_spec"), Mapping) else {}
        square = overlay.get("square_image") if isinstance(overlay.get("square_image"), Mapping) else {}
        story = overlay.get("story_reel") if isinstance(overlay.get("story_reel"), Mapping) else {}
        backgrounds = square.get("background_candidates") if isinstance(square.get("background_candidates"), list) else []
        background_keywords = square.get("background_keywords") if isinstance(square.get("background_keywords"), list) else []
        stills = square.get("still_candidates") if isinstance(square.get("still_candidates"), list) else []
        videos = story.get("video_candidates") if isinstance(story.get("video_candidates"), list) else []
        visual_style = square.get("visual_style") if isinstance(square.get("visual_style"), Mapping) else {}
        metrics = draft.get("metrics") if isinstance(draft.get("metrics"), Mapping) else {}
        sources = draft.get("source_refs") if isinstance(draft.get("source_refs"), list) else []
        lines.extend(
            [
                f"## {index}. {draft.get('title') or 'Untitled Draft'}",
                "",
                f"- Category: `{draft.get('category') or '--'}`",
                f"- Severity: `{draft.get('severity') or '--'}`",
                f"- Review status: `{draft.get('review_status') or '--'}`",
                f"- As of: `{draft.get('asof') or '--'}`",
                "",
                "Caption:",
                "",
                "```text",
                str(draft.get("caption") or "").strip(),
                "```",
                "",
                "Metrics:",
            ]
        )
        if metrics:
            for key, value in metrics.items():
                lines.append(f"- `{key}`: `{value}`")
        else:
            lines.append("- `none`: `--`")
        lines.extend(["", "Background candidates:"])
        if backgrounds:
            for candidate in backgrounds[:4]:
                lines.append(f"- `{candidate}`")
        else:
            lines.append("- `none`: `--`")
        lines.extend(["", "Background keywords:"])
        if background_keywords:
            for keyword in background_keywords:
                lines.append(f"- `{keyword}`")
        else:
            lines.append("- `none`: `--`")
        lines.extend(["", "Still candidates:"])
        if stills:
            for still in stills:
                lines.append(f"- `{still}`")
        else:
            lines.append("- `none`: `--`")
        lines.extend(["", "Reel video candidates:"])
        if videos:
            for video in videos:
                lines.append(f"- `{video}`")
        else:
            lines.append("- `none`: `--`")
        if visual_style:
            lines.extend(
                [
                    "",
                    "Visual style:",
                    f"- Layout: `{visual_style.get('layout') or '--'}`",
                    f"- Notes: {visual_style.get('notes') or '--'}",
                ]
            )
        lines.extend(["", "Sources:"])
        if sources:
            for source in sources:
                if isinstance(source, Mapping):
                    lines.append(f"- {source.get('label') or 'Source'}: `{source.get('path') or '--'}`")
        else:
            lines.append("- `none`: `--`")
        lines.append("")

    return "\n".join(lines)


def write_shadow_review_markdown(payload: Mapping[str, Any], output_path: Path | str) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_review_markdown(payload), encoding="utf-8")
    return path


def _default_output_path() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return Path("tmp") / "social_alerts_shadow" / f"{stamp}.json"


def _default_review_path(json_output_path: Path | str) -> Path:
    return Path(json_output_path).with_suffix(".md")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build shadow-mode social alert drafts from a Gaia Eyes signal JSON snapshot.")
    parser.add_argument("--input", required=True, help="Path to a JSON snapshot from existing Gaia Eyes signal outputs.")
    parser.add_argument("--output", default="", help="Output JSON path. Defaults to tmp/social_alerts_shadow/<timestamp>.json.")
    parser.add_argument(
        "--review-output",
        nargs="?",
        const="auto",
        default="",
        help="Optional Markdown review path. Use without a value to write beside the JSON output.",
    )
    parser.add_argument("--max-drafts", type=int, default=6, help="Maximum drafts to include.")
    args = parser.parse_args()

    in_path = Path(args.input)
    snapshot = json.loads(in_path.read_text(encoding="utf-8"))
    if not isinstance(snapshot, Mapping):
        raise SystemExit("Input JSON must be an object.")
    payload = build_shadow_payload(snapshot, max_drafts=args.max_drafts)
    out_path = write_shadow_payload(payload, args.output or _default_output_path())
    print(f"[social_alerts.shadow] wrote {payload['draft_count']} draft(s) -> {out_path}")
    if args.review_output:
        review_path = _default_review_path(out_path) if args.review_output == "auto" else Path(args.review_output)
        write_shadow_review_markdown(payload, review_path)
        print(f"[social_alerts.shadow] wrote review markdown -> {review_path}")


if __name__ == "__main__":
    main()
