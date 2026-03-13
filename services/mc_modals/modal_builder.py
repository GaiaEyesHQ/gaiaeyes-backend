from __future__ import annotations

import hashlib
from datetime import date
from typing import Any, Dict, Iterable, List, Optional


_GAUGE_ORDER = [
    "pain",
    "focus",
    "heart",
    "stamina",
    "energy",
    "sleep",
    "mood",
    "health_status",
]

_GAUGE_FALLBACK_LABELS = {
    "pain": "Pain",
    "focus": "Focus",
    "heart": "Heart",
    "stamina": "Recovery Load",
    "energy": "Energy",
    "sleep": "Sleep",
    "mood": "Mood",
    "health_status": "Health Status",
}

_SEVERITY_RANK = {
    "high": 4,
    "watch": 3,
    "elevated": 3,
    "mild": 2,
    "low": 1,
}

_GAUGE_DRIVER_MAP = {
    "pain": ["pressure", "temp", "aqi"],
    "focus": ["pressure", "aqi", "kp", "sw", "schumann"],
    "heart": ["kp", "bz", "sw", "aqi"],
    "stamina": ["temp", "aqi", "sw"],
    "energy": ["temp", "sw", "kp"],
    "sleep": ["pressure", "temp", "kp", "bz", "schumann"],
    "mood": ["kp", "sw", "schumann", "pressure"],
    "health_status": [],
}

_GAUGE_NOTICES = {
    "pain": [
        "Headache or migraine sensitivity may rise for some people.",
        "Joint or nerve flare sensitivity can be more noticeable for some.",
        "Body tension may feel easier to trigger than usual.",
    ],
    "focus": [
        "Attention can feel patchy for some people.",
        "Short-term mental fatigue may show up faster for some.",
        "Context switching may feel heavier than usual.",
    ],
    "heart": [
        "Some people may notice extra cardiovascular or stress-reactive awareness.",
        "Perceived strain during effort can feel higher for some.",
        "Recovery between demanding tasks may feel slower for some.",
    ],
    "stamina": [
        "Energy reserve may feel lower than expected for some people.",
        "Long tasks can feel heavier to sustain for some.",
        "Recovery after exertion may take longer for some.",
    ],
    "energy": [
        "Some people may feel a wired-and-tired pattern.",
        "Energy swings can feel sharper for some.",
        "Late-day drop-off may show up earlier for some.",
    ],
    "sleep": [
        "Sleep onset may feel less predictable for some people.",
        "Light or fragmented sleep can be more common for some.",
        "Rest quality may feel less steady for some.",
    ],
    "mood": [
        "Mood reactivity may be a little stronger for some people.",
        "Stress sensitivity can feel higher for some.",
        "Overstimulation may show up faster for some.",
    ],
    "health_status": [
        "Body load can feel higher when sleep or recovery is limited.",
        "It may be easier to feel depleted if routine slips.",
        "Small stressors may feel larger until recovery catches up.",
    ],
}

_GAUGE_ACTIONS = {
    "pain": [
        "Hydrate steadily through the day.",
        "Use gentle heat, steam, or saline support if helpful.",
        "Pace heavy tasks and add short resets.",
    ],
    "focus": [
        "Use short focused blocks with brief breaks.",
        "Reduce extra notifications when possible.",
        "Front-load high-priority tasks earlier in the day.",
    ],
    "heart": [
        "Favor steady effort over sudden spikes.",
        "Use slower breathing breaks when stress rises.",
        "Keep caffeine and stimulation moderate later in the day.",
    ],
    "stamina": [
        "Use lighter pacing and protect recovery windows.",
        "Add hydration and simple fueling before long tasks.",
        "Choose low-intensity movement over all-out sessions.",
    ],
    "energy": [
        "Keep meals and hydration consistent.",
        "Use brief daylight or movement breaks to reset.",
        "Protect your wind-down routine tonight.",
    ],
    "sleep": [
        "Protect your sleep window and lights-down timing.",
        "Reduce high stimulation late in the evening.",
        "Keep room temperature and bedtime routine steady.",
    ],
    "mood": [
        "Lower stimulation where possible.",
        "Take short decompression breaks between intense tasks.",
        "Prioritize calming routines that usually help you.",
    ],
    "health_status": [
        "Prioritize sleep opportunity and recovery basics.",
        "Keep exertion moderate if body load feels high.",
        "Log symptoms to track what patterns repeat for you.",
    ],
}

_GAUGE_PREFILL = {
    "pain": ["NERVE_PAIN", "HEADACHE"],
    "focus": ["DRAINED", "HEADACHE"],
    "heart": ["ANXIOUS", "DRAINED"],
    "stamina": ["DRAINED", "OTHER"],
    "energy": ["DRAINED", "INSOMNIA"],
    "sleep": ["INSOMNIA", "DRAINED"],
    "mood": ["ANXIOUS", "DRAINED"],
    "health_status": ["OTHER", "DRAINED"],
}

_GAUGE_QUICK_LOG = {
    "pain": [
        {"code": "HEADACHE", "label": "Headache"},
        {"code": "NERVE_PAIN", "label": "Pain flare"},
        {"code": "OTHER", "label": "Joint stiffness"},
    ],
    "focus": [
        {"code": "HEADACHE", "label": "Headache"},
        {"code": "DRAINED", "label": "Brain fog"},
        {"code": "OTHER", "label": "Focus drift"},
    ],
    "heart": [
        {"code": "ANXIOUS", "label": "Restless"},
        {"code": "DRAINED", "label": "Drained"},
        {"code": "OTHER", "label": "Heart awareness"},
    ],
    "stamina": [
        {"code": "DRAINED", "label": "Drained"},
        {"code": "OTHER", "label": "Body aches"},
        {"code": "NERVE_PAIN", "label": "Pain flare"},
    ],
    "energy": [
        {"code": "DRAINED", "label": "Drained"},
        {"code": "ANXIOUS", "label": "Wired"},
        {"code": "OTHER", "label": "Energy swing"},
    ],
    "sleep": [
        {"code": "INSOMNIA", "label": "Insomnia"},
        {"code": "ANXIOUS", "label": "Restless"},
        {"code": "DRAINED", "label": "Unrefreshed"},
    ],
    "mood": [
        {"code": "ANXIOUS", "label": "Anxious"},
        {"code": "DRAINED", "label": "Drained"},
        {"code": "OTHER", "label": "Overstimulated"},
    ],
    "health_status": [
        {"code": "DRAINED", "label": "Drained"},
        {"code": "NERVE_PAIN", "label": "Pain flare"},
        {"code": "OTHER", "label": "Other"},
    ],
}

_DRIVER_NOTICE = {
    "pressure": [
        "Headaches or migraines may feel easier to trigger for some people.",
        "Head, sinus, or ear pressure can feel more noticeable for some people.",
        "Joint, arthritis, or nerve flare sensitivity may increase for some people.",
    ],
    "temp": [
        "Body aches or fatigue may feel more noticeable for some people.",
        "Fibro flare sensitivity can rise for some people during bigger swings.",
        "Circulation discomfort can feel more noticeable for some people.",
    ],
    "aqi": [
        "Sinus irritation or headache may feel more noticeable for some people.",
        "Fatigue or brain fog can show up faster for some people.",
        "Breathing irritation may be easier to notice for some people.",
    ],
    "kp": [
        "Scattered focus can show up for some people during geomagnetic activity.",
        "Some people may notice a wired or restless feeling.",
        "Sleep disruption or autonomic wobble can feel more noticeable for some people.",
    ],
    "bz": [
        "Scattered focus can feel more noticeable for some people.",
        "A wired or restless feeling may be easier to notice for some people.",
        "Sleep disruption or autonomic wobble can show up for some people.",
    ],
    "sw": [
        "A wired or restless feeling may show up for some people.",
        "Scattered focus can feel more noticeable for some people.",
        "Sleep disruption or autonomic wobble can show up for some people.",
    ],
    "schumann": [
        "A jittery or buzzy feeling may show up for some people.",
        "Focus drift can feel more noticeable for some people.",
        "Sleep sensitivity may feel higher for some people.",
    ],
}

_DRIVER_ACTIONS = {
    "pressure": [
        "Hydrate steadily.",
        "Use gentle sinus/steam support if useful.",
        "Avoid stacking intense tasks back-to-back.",
    ],
    "temp": [
        "Layer clothing and limit abrupt temperature swings.",
        "Hydrate and pace exertion.",
        "Protect your evening wind-down.",
    ],
    "aqi": [
        "Reduce outdoor exertion when possible.",
        "Use cleaner indoor air if available.",
        "Hydrate and use shorter activity blocks.",
    ],
    "kp": [
        "Reduce late stimulation.",
        "Add short regulation breaks during the day.",
        "Prioritize consistent sleep timing.",
    ],
    "bz": [
        "Keep effort steady instead of spiky.",
        "Use calmer pacing through high-demand windows.",
        "Protect sleep setup and routine tonight.",
    ],
    "sw": [
        "Use shorter work blocks with resets.",
        "Limit extra stimulation late day.",
        "Keep movement gentle and regular.",
    ],
    "schumann": [
        "Keep evening routine simple and consistent.",
        "Lower sensory load before bed.",
        "Track symptoms so patterns are easier to spot.",
    ],
}

_DRIVER_PREFILL = {
    "pressure": ["HEADACHE", "NERVE_PAIN"],
    "temp": ["DRAINED", "INSOMNIA"],
    "aqi": ["DRAINED", "HEADACHE"],
    "kp": ["ANXIOUS", "INSOMNIA"],
    "bz": ["INSOMNIA", "ANXIOUS"],
    "sw": ["DRAINED", "ANXIOUS"],
    "schumann": ["INSOMNIA", "OTHER"],
}

_DRIVER_QUICK_LOG = {
    "pressure": [
        {"code": "HEADACHE", "label": "Headache"},
        {"code": "NERVE_PAIN", "label": "Pain flare"},
        {"code": "OTHER", "label": "Sinus pressure"},
    ],
    "temp": [
        {"code": "DRAINED", "label": "Fatigue"},
        {"code": "OTHER", "label": "Body aches"},
        {"code": "NERVE_PAIN", "label": "Fibro flare"},
    ],
    "aqi": [
        {"code": "HEADACHE", "label": "Headache"},
        {"code": "DRAINED", "label": "Brain fog"},
        {"code": "OTHER", "label": "Breathing irritation"},
    ],
    "kp": [
        {"code": "ANXIOUS", "label": "Restless"},
        {"code": "INSOMNIA", "label": "Sleep disruption"},
        {"code": "OTHER", "label": "Focus drift"},
    ],
    "bz": [
        {"code": "ANXIOUS", "label": "Restless"},
        {"code": "INSOMNIA", "label": "Sleep disruption"},
        {"code": "OTHER", "label": "Autonomic wobble"},
    ],
    "sw": [
        {"code": "ANXIOUS", "label": "Wired"},
        {"code": "INSOMNIA", "label": "Sleep disruption"},
        {"code": "OTHER", "label": "Focus drift"},
    ],
    "schumann": [
        {"code": "ANXIOUS", "label": "Jittery"},
        {"code": "INSOMNIA", "label": "Sleep sensitivity"},
        {"code": "OTHER", "label": "Buzzy"},
    ],
}

_GAUGE_SHORT_BODY = {
    "pain": "Steady is a good sign. No strong pain-load drivers stand out right now.",
    "focus": "Steady is a good sign. No strong focus-load drivers stand out right now.",
    "heart": "Steady is a good sign. No strong heart-load drivers stand out right now.",
    "stamina": "Steady is a good sign. No strong stamina-load drivers stand out right now.",
    "energy": "Steady is a good sign. No strong energy-load drivers stand out right now.",
    "sleep": "Steady is a good sign. No strong sleep-load drivers stand out right now.",
    "mood": "Steady is a good sign. No strong mood-load drivers stand out right now.",
    "health_status": "Steady is a good sign. No strong body-load drivers stand out right now.",
}

_GAUGE_SHORT_TIP = {
    "pain": "Stay hydrated and keep pacing gentle if needed.",
    "focus": "Use normal pacing and protect your most important focus blocks.",
    "heart": "Stay hydrated and pace intense effort if needed.",
    "stamina": "Keep recovery basics steady and avoid stacking heavy exertion.",
    "energy": "Keep hydration and meals steady to help energy stay even.",
    "sleep": "Keep your wind-down routine steady tonight.",
    "mood": "Keep stimulation moderate and use short resets if needed.",
    "health_status": "Keep recovery basics steady and check in if anything shifts.",
}

_DRIVER_SHORT_BODY = {
    "pressure": "Pressure change looks fairly steady right now.",
    "temp": "Temperature change looks fairly steady right now.",
    "aqi": "Air quality looks relatively steady right now.",
    "kp": "Geomagnetic activity looks relatively steady right now.",
    "bz": "Bz coupling looks relatively steady right now.",
    "sw": "Solar wind speed looks relatively steady right now.",
    "schumann": "Schumann variability looks relatively steady right now.",
}

_DRIVER_SHORT_TIP = {
    "pressure": "Normal hydration and pacing should be enough for most people.",
    "temp": "Dress for comfort and keep hydration steady if conditions change.",
    "aqi": "Normal outdoor plans may be fine if you usually tolerate them well.",
    "kp": "Keep your normal pacing and sleep routine steady.",
    "bz": "Keep effort steady and avoid overreacting to small shifts.",
    "sw": "Use your usual pacing and sleep routine for now.",
    "schumann": "Keep sensory load and sleep routine steady if that usually helps.",
}


def _seed_index(day: date, key: str, bucket: str) -> int:
    text = f"{day.isoformat()}|{key}|{bucket}".encode("utf-8")
    digest = hashlib.sha256(text).hexdigest()
    return int(digest[:8], 16)


def _rotate_pick(options: List[str], day: date, key: str, bucket: str, count: int) -> List[str]:
    values = [item for item in options if item]
    if not values:
        return []
    if len(values) <= count:
        return values
    start = _seed_index(day, key, bucket) % len(values)
    out: List[str] = []
    for idx in range(count):
        out.append(values[(start + idx) % len(values)])
    return out


def _normalized_zone_label(meta: Dict[str, Any]) -> str:
    label = str(meta.get("label") or "").strip()
    if label:
        return label
    zone = str(meta.get("zone") or "").strip().replace("_", " ")
    if zone:
        return zone[:1].upper() + zone[1:]
    return "Calibrating"


def _normalized_zone_key(meta: Dict[str, Any]) -> str:
    zone = str(meta.get("zone") or "").strip().lower()
    if zone in {"low", "mild", "elevated", "high"}:
        return zone
    return "low"


def _driver_zone_key(driver: Dict[str, Any]) -> str:
    severity = str(driver.get("severity") or "").strip().lower()
    if severity == "high":
        return "high"
    if severity in {"watch", "elevated"}:
        return "elevated"
    if severity == "mild":
        return "mild"
    return "low"


def _default_severity(zone: str) -> int:
    if zone == "high":
        return 4
    if zone == "elevated":
        return 3
    if zone == "mild":
        return 2
    return 1


def _unique_lines(items: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for raw in items:
        line = str(raw or "").strip()
        if not line or line in seen:
            continue
        seen.add(line)
        out.append(line)
    return out


def _delta_line(delta: int) -> Optional[str]:
    if abs(int(delta or 0)) < 5:
        return None
    direction = "up" if delta > 0 else "down"
    return f"This gauge moved {abs(delta)} points {direction} from the prior reading."


def _quick_log(
    *,
    context_type: str,
    context_key: str,
    zone: str,
    default_options: List[Dict[str, str]],
    default_prefill: List[str],
    delta: Optional[int | float] = None,
) -> Dict[str, Any]:
    options = [
        {"code": str(item.get("code") or "").strip(), "label": str(item.get("label") or "").strip()}
        for item in default_options
        if str(item.get("code") or "").strip() and str(item.get("label") or "").strip()
    ]
    if not options:
        options = [
            {
                "code": str(code or "").strip(),
                "label": str(code or "").strip().replace("_", " ").title(),
            }
            for code in default_prefill
            if str(code or "").strip()
        ]

    tags = [
        "source:quick_log",
        f"context:{context_type}:{context_key}",
        f"zone:{zone}",
    ]
    if delta is not None:
        try:
            numeric = float(delta)
            if numeric.is_integer():
                tags.append(f"delta:{int(numeric)}")
            else:
                tags.append(f"delta:{numeric:.1f}")
        except Exception:
            pass

    return {
        "title": "Log what you're feeling:",
        "confirm_label": "Log Symptoms",
        "options": options[:3],
        "default_severity": _default_severity(zone),
        "base_tags": tags,
    }


def _driver_why_line(driver: Dict[str, Any]) -> str:
    label = str(driver.get("label") or "Driver")
    state = str(driver.get("state") or "Elevated")
    value = driver.get("value")
    unit = str(driver.get("unit") or "").strip()
    if value is None:
        return f"{label} is {state.lower()} right now."

    if isinstance(value, float):
        if abs(value - round(value, 0)) < 0.01:
            value_text = str(int(round(value, 0)))
        else:
            value_text = f"{value:.1f}"
    else:
        value_text = str(value)

    suffix = f" {unit}" if unit else ""
    return f"{label} is {state.lower()} ({value_text}{suffix})."


def _driver_rank(driver: Dict[str, Any]) -> int:
    return int(_SEVERITY_RANK.get(str(driver.get("severity") or "").lower(), 0))


def _elevated_gauges(
    gauges: Dict[str, Any],
    gauges_meta: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for key, raw in gauges.items():
        try:
            value = float(raw)
        except Exception:
            continue
        meta = gauges_meta.get(key) or {}
        zone = str(meta.get("zone") or "").lower()
        if zone not in {"elevated", "high"}:
            continue
        rows.append({"key": key, "value": value, "meta": meta})
    rows.sort(key=lambda item: item["value"], reverse=True)
    return rows


def _driver_is_watch_or_high(driver: Dict[str, Any]) -> bool:
    return str(driver.get("severity") or "").strip().lower() in {"watch", "high"}


def _gauge_modal_type(zone: str, delta: int, related: List[Dict[str, Any]]) -> str:
    if zone in {"mild", "elevated", "high"}:
        return "full"
    if abs(int(delta or 0)) >= 5:
        return "full"
    if any(_driver_is_watch_or_high(driver) for driver in related):
        return "full"
    return "short"


def _driver_modal_type(driver: Dict[str, Any]) -> str:
    zone = _driver_zone_key(driver)
    return "full" if zone in {"mild", "elevated", "high"} else "short"


def _gauge_why_lines(
    *,
    day: date,
    gauge_key: str,
    related: List[Dict[str, Any]],
    delta: int,
) -> List[str]:
    lines = [_driver_why_line(item) for item in related[:3]]
    delta_line = _delta_line(delta)
    if delta_line:
        lines.append(delta_line)
    if not lines:
        lines = _rotate_pick(
            [
                "This gauge combines your current environmental context and personal baseline.",
                "Recent local and space drivers can nudge this gauge up or down.",
                "Today’s score reflects context, not certainty, and can change quickly.",
            ],
            day,
            gauge_key,
            "why",
            2,
        )
    return _unique_lines(lines)[:3]


def _gauge_notice_lines(
    *,
    day: date,
    gauge_key: str,
    related: List[Dict[str, Any]],
) -> List[str]:
    lines: List[str] = []
    for driver in related[:2]:
        driver_key = str(driver.get("key") or "").strip()
        lines.extend(_rotate_pick(_DRIVER_NOTICE.get(driver_key, []), day, f"{gauge_key}:{driver_key}", "driver-notice", 1))
    lines.extend(_rotate_pick(_GAUGE_NOTICES.get(gauge_key, []), day, gauge_key, "notice", 2))
    return _unique_lines(lines)[:3]


def _gauge_action_lines(
    *,
    day: date,
    gauge_key: str,
    related: List[Dict[str, Any]],
) -> List[str]:
    lines: List[str] = []
    for driver in related[:2]:
        driver_key = str(driver.get("key") or "").strip()
        lines.extend(_rotate_pick(_DRIVER_ACTIONS.get(driver_key, []), day, f"{gauge_key}:{driver_key}", "driver-actions", 1))
    lines.extend(_rotate_pick(_GAUGE_ACTIONS.get(gauge_key, []), day, gauge_key, "actions", 3))
    lines = _unique_lines(lines)
    return lines[:4] if lines else ["Hydrate, pace tasks, and protect your sleep window."]


def _driver_notice_lines(day: date, key: str) -> List[str]:
    notices = _rotate_pick(_DRIVER_NOTICE.get(key, []), day, key, "driver-notice", 3)
    return notices[:3] if notices else ["Some people may notice mild sensitivity shifts with this driver."]


def _driver_action_lines(day: date, key: str) -> List[str]:
    actions = _rotate_pick(_DRIVER_ACTIONS.get(key, []), day, key, "driver-actions", 3)
    return actions[:4] if actions else ["Use steady pacing and track symptoms to see personal patterns."]


def build_modal_models(
    *,
    day: date,
    gauges: Optional[Dict[str, Any]],
    gauges_meta: Optional[Dict[str, Dict[str, Any]]],
    gauge_labels: Optional[Dict[str, str]],
    drivers: Optional[Iterable[Dict[str, Any]]] = None,
    gauges_delta: Optional[Dict[str, int]] = None,
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    gauges = gauges or {}
    gauges_meta = gauges_meta or {}
    gauge_labels = gauge_labels or {}
    gauges_delta = gauges_delta or {}
    driver_rows = [d for d in list(drivers or []) if isinstance(d, dict)]
    drivers_by_key = {
        str(d.get("key") or "").strip(): d
        for d in driver_rows
        if str(d.get("key") or "").strip()
    }

    gauge_models: Dict[str, Dict[str, Any]] = {}
    for gauge_key in _GAUGE_ORDER:
        label = gauge_labels.get(gauge_key) or _GAUGE_FALLBACK_LABELS.get(gauge_key) or gauge_key
        meta = gauges_meta.get(gauge_key) or {}
        zone = _normalized_zone_key(meta)
        status = _normalized_zone_label(meta)
        delta = int(gauges_delta.get(gauge_key) or 0)
        related_keys = _GAUGE_DRIVER_MAP.get(gauge_key) or []
        related = [drivers_by_key[k] for k in related_keys if k in drivers_by_key]
        modal_type = _gauge_modal_type(zone, delta, related)

        quick_log = _quick_log(
            context_type="gauge",
            context_key=gauge_key,
            zone=zone,
            default_options=_GAUGE_QUICK_LOG.get(gauge_key, []),
            default_prefill=_GAUGE_PREFILL.get(gauge_key, ["OTHER"]),
            delta=delta if abs(delta) >= 1 else None,
        )

        if modal_type == "short":
            gauge_models[gauge_key] = {
                "modal_type": "short",
                "title": f"{label} \u2014 Steady",
                "body": _GAUGE_SHORT_BODY.get(gauge_key, "Steady is a good sign right now."),
                "tip": _GAUGE_SHORT_TIP.get(gauge_key, "Keep pacing and recovery basics steady."),
                "quick_log": quick_log,
                "cta": {
                    "label": "Log symptoms",
                    "action": "open_symptom_log",
                    "prefill": _GAUGE_PREFILL.get(gauge_key, ["OTHER"]),
                },
            }
            continue

        gauge_models[gauge_key] = {
            "modal_type": "full",
            "title": f"{label} \u2014 {status}",
            "why": _gauge_why_lines(day=day, gauge_key=gauge_key, related=related, delta=delta),
            "what_you_may_notice": _gauge_notice_lines(day=day, gauge_key=gauge_key, related=related),
            "suggested_actions": _gauge_action_lines(day=day, gauge_key=gauge_key, related=related),
            "quick_log": quick_log,
            "cta": {
                "label": "Log symptoms",
                "action": "open_symptom_log",
                "prefill": _GAUGE_PREFILL.get(gauge_key, ["OTHER"]),
            },
        }

    driver_models: Dict[str, Dict[str, Any]] = {}
    for driver in driver_rows:
        key = str(driver.get("key") or "").strip()
        if not key:
            continue
        label = str(driver.get("label") or key.replace("_", " ").title())
        state = str(driver.get("state") or "Elevated")
        zone = _driver_zone_key(driver)
        quick_log = _quick_log(
            context_type="driver",
            context_key=key,
            zone=zone,
            default_options=_DRIVER_QUICK_LOG.get(key, []),
            default_prefill=_DRIVER_PREFILL.get(key, ["OTHER"]),
            delta=driver.get("value") if key in {"pressure", "temp"} else None,
        )
        why_lines = [
            _driver_why_line(driver),
            _rotate_pick(
                [
                    "This signal may coincide with sensitivity shifts for some people.",
                    "Responses vary by person, so treat this as context, not destiny.",
                    "This can be useful context when pacing your day and recovery.",
                ],
                day,
                key,
                "driver-why",
                1,
            )[0],
        ]
        if _driver_modal_type(driver) == "short":
            driver_models[key] = {
                "modal_type": "short",
                "title": f"{label} \u2014 Steady",
                "body": _DRIVER_SHORT_BODY.get(key, "This driver looks relatively steady right now."),
                "tip": _DRIVER_SHORT_TIP.get(key, "Keep your normal pacing steady for now."),
                "quick_log": quick_log,
                "cta": {
                    "label": "Log symptoms",
                    "action": "open_symptom_log",
                    "prefill": _DRIVER_PREFILL.get(key, ["OTHER"]),
                },
            }
            continue

        driver_models[key] = {
            "modal_type": "full",
            "title": f"{label} \u2014 {state}",
            "why": why_lines[:3],
            "what_you_may_notice": _driver_notice_lines(day, key),
            "suggested_actions": _driver_action_lines(day, key),
            "quick_log": quick_log,
            "cta": {
                "label": "Log symptoms",
                "action": "open_symptom_log",
                "prefill": _DRIVER_PREFILL.get(key, ["OTHER"]),
            },
        }

    return {
        "gauges": gauge_models,
        "drivers": driver_models,
    }


def build_earthscope_summary(
    *,
    day: date,
    gauges: Optional[Dict[str, Any]],
    gauges_meta: Optional[Dict[str, Dict[str, Any]]],
    gauge_labels: Optional[Dict[str, str]],
    drivers: Optional[Iterable[Dict[str, Any]]],
) -> str:
    gauges = gauges or {}
    gauges_meta = gauges_meta or {}
    gauge_labels = gauge_labels or {}
    driver_rows = [d for d in list(drivers or []) if isinstance(d, dict)]
    driver_rows.sort(key=lambda item: _driver_rank(item), reverse=True)
    top_drivers = driver_rows[:2]
    top_gauges = _elevated_gauges(gauges, gauges_meta)[:2]

    sentences: List[str] = []
    if top_drivers:
        parts = [f"{d.get('label')} ({d.get('state')})" for d in top_drivers]
        if len(parts) == 1:
            sentences.append(f"Today\u2019s strongest environmental driver is {parts[0]}.")
        else:
            sentences.append(f"Today\u2019s strongest environmental drivers are {parts[0]} and {parts[1]}.")
    else:
        sentences.append("Environmental drivers look mostly low to mild right now.")

    if top_gauges:
        labels: List[str] = []
        for gauge in top_gauges:
            key = gauge["key"]
            label = gauge_labels.get(key) or _GAUGE_FALLBACK_LABELS.get(key) or key
            status = _normalized_zone_label(gauge.get("meta") or {})
            labels.append(f"{label} ({status})")
        if len(labels) == 1:
            sentences.append(f"Your most elevated gauge is {labels[0]}.")
        else:
            sentences.append(f"Your most elevated gauges are {labels[0]} and {labels[1]}.")
    else:
        sentences.append("Most gauges are currently in lower zones.")

    bridge = _rotate_pick(
        [
            "These patterns may align with sensitivity or fatigue shifts for some people.",
            "For some people, this context can coincide with sleep, mood, or energy shifts.",
            "Individual response can vary, so use this as context rather than certainty.",
        ],
        day,
        "earthscope_summary",
        "bridge",
        1,
    )
    sentences.extend(bridge[:1])
    sentences.append("Tap any gauge or driver for details, supportive actions, and quick logging.")
    return " ".join(sentences[:4]).strip()
