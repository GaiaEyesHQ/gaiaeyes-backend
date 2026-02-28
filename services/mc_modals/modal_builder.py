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

_DRIVER_NOTICE = {
    "pressure": [
        "Head or sinus pressure sensitivity may increase for some.",
        "Joint or nerve sensitivity can feel higher for some.",
        "Pacing may feel more helpful than usual for some.",
    ],
    "temp": [
        "Temperature transitions may feel more draining for some.",
        "Energy steadiness may vary more for some people.",
        "Sleep quality can feel more fragile for some.",
    ],
    "aqi": [
        "Airway or sensory irritation may increase for some.",
        "Outdoor exertion may feel heavier for some people.",
        "Fatigue can show up faster for some.",
    ],
    "kp": [
        "Sleep or mood sensitivity may shift for some people.",
        "Some people may notice extra stress reactivity.",
        "Cognitive steadiness may feel less predictable for some.",
    ],
    "bz": [
        "Sleep continuity may feel less stable for some.",
        "Stress-load awareness can feel higher for some people.",
        "Energy recovery may feel slower for some.",
    ],
    "sw": [
        "Some people may notice a wired-and-tired pattern.",
        "Overstimulation may feel easier to trigger for some.",
        "Sleep depth can feel lighter for some.",
    ],
    "schumann": [
        "Some people may notice lighter sleep or vivid dreams.",
        "Sensory sensitivity may feel a bit sharper for some.",
        "Focus stability can feel more variable for some.",
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


def build_modal_models(
    *,
    day: date,
    gauges: Optional[Dict[str, Any]],
    gauges_meta: Optional[Dict[str, Dict[str, Any]]],
    gauge_labels: Optional[Dict[str, str]],
    drivers: Optional[Iterable[Dict[str, Any]]],
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    gauges = gauges or {}
    gauges_meta = gauges_meta or {}
    gauge_labels = gauge_labels or {}
    driver_rows = [d for d in list(drivers or []) if isinstance(d, dict)]
    drivers_by_key = {
        str(d.get("key") or "").strip(): d
        for d in driver_rows
        if str(d.get("key") or "").strip()
    }

    gauge_models: Dict[str, Dict[str, Any]] = {}
    for gauge_key in _GAUGE_ORDER:
        label = gauge_labels.get(gauge_key) or _GAUGE_FALLBACK_LABELS.get(gauge_key) or gauge_key
        status = _normalized_zone_label(gauges_meta.get(gauge_key) or {})
        related_keys = _GAUGE_DRIVER_MAP.get(gauge_key) or []
        related = [drivers_by_key[k] for k in related_keys if k in drivers_by_key]

        why_lines = [_driver_why_line(item) for item in related[:2]]
        if not why_lines:
            why_lines = _rotate_pick(
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

        notice = _rotate_pick(_GAUGE_NOTICES.get(gauge_key, []), day, gauge_key, "notice", 2)
        actions = _rotate_pick(_GAUGE_ACTIONS.get(gauge_key, []), day, gauge_key, "actions", 3)
        if not actions:
            actions = ["Hydrate, pace tasks, and protect your sleep window."]

        gauge_models[gauge_key] = {
            "title": f"{label} \u2014 {status}",
            "why": why_lines[:3],
            "what_you_may_notice": notice[:3],
            "suggested_actions": actions[:4],
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
        notices = _rotate_pick(_DRIVER_NOTICE.get(key, []), day, key, "driver-notice", 2)
        actions = _rotate_pick(_DRIVER_ACTIONS.get(key, []), day, key, "driver-actions", 3)
        if not notices:
            notices = ["Some people may notice mild sensitivity shifts with this driver."]
        if not actions:
            actions = ["Use steady pacing and track symptoms to see personal patterns."]

        driver_models[key] = {
            "title": f"{label} \u2014 {state}",
            "why": why_lines[:3],
            "what_you_may_notice": notices[:3],
            "suggested_actions": actions[:4],
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
    sentences.append("Tap highlighted gauges or drivers for details, supportive actions, and quick logging.")
    return " ".join(sentences[:4]).strip()
