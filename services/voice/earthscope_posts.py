from __future__ import annotations

import hashlib
from datetime import date
from typing import Any, Dict, Mapping, Optional, Sequence

from .profiles import VoiceProfile
from .semantic import SemanticAction, SemanticGuardrails, SemanticPayload, SemanticRenderHints


_PUBLIC_HASHTAGS = "#GaiaEyes #SpaceWeather #Frequency #HRV #ChronicIllness #Schumann"


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return float(value)
    except Exception:
        return None


def _fmt_num(value: Optional[float], digits: int = 1) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}"


def _band_kp(kp: Optional[float]) -> str:
    if kp is None:
        return "unknown"
    if kp >= 7:
        return "severe"
    if kp >= 5:
        return "storm"
    if kp >= 4:
        return "active"
    if kp >= 3:
        return "unsettled"
    return "quiet"


def _band_sw(speed: Optional[float]) -> str:
    if speed is None:
        return "unknown"
    if speed >= 700:
        return "very-high"
    if speed >= 600:
        return "high"
    if speed >= 500:
        return "elevated"
    return "normal"


def _bz_desc(bz: Optional[float]) -> str:
    if bz is None:
        return "undetermined"
    if bz <= -10:
        return "strong southward"
    if bz <= -6:
        return "southward"
    if bz < 0:
        return "slightly southward"
    if bz >= 8:
        return "strong northward"
    if bz >= 3:
        return "northward"
    return "near neutral"


def _public_tone(kp: Optional[float], bz: Optional[float], sw: Optional[float]) -> str:
    if (kp is not None and kp >= 5) or ((bz is not None and bz <= -8) and (sw is not None and sw >= 550)):
        return "stormy"
    if (kp is not None and kp >= 3.5) or (sw is not None and sw >= 550) or (bz is not None and bz <= -6):
        return "unsettled"
    if (kp is not None and kp <= 2.5) and (bz is None or bz > -2):
        return "calm"
    return "neutral"


def _public_claim_strength(tone: str) -> str:
    if tone == "stormy":
        return "likely_notice"
    if tone == "unsettled":
        return "may_notice"
    return "observe_only"


def _public_confidence(kp: Optional[float], bz: Optional[float], sw: Optional[float], sr: Optional[float]) -> str:
    signal_count = sum(1 for item in (kp, bz, sw, sr) if item is not None)
    if signal_count >= 3:
        return "high"
    if signal_count >= 2:
        return "moderate"
    return "low"


def _public_max_urgency(tone: str) -> str:
    if tone == "stormy":
        return "high"
    if tone == "unsettled":
        return "watch"
    if tone == "neutral":
        return "notable"
    return "quiet"


def _public_driver_bits(
    *,
    cmes_24h: Optional[float],
    flares_24h: Optional[float],
    bz_desc: str,
    sw_band: str,
) -> list[str]:
    driver_bits: list[str] = []
    if (cmes_24h or 0) > 0:
        driver_bits.append("recent CME after-effects")
    if (flares_24h or 0) > 0:
        driver_bits.append("fresh flare activity")
    if bz_desc in {"southward", "strong southward", "slightly southward"}:
        driver_bits.append("southward IMF windows")
    if sw_band in {"elevated", "high", "very-high"}:
        driver_bits.append("faster solar wind")
    return driver_bits


def _public_actions(tone: str) -> list[str]:
    if tone in {"stormy", "unsettled"}:
        return [
            "5–10 min paced breathing or brief HRV biofeedback",
            "Hydration + electrolytes; short daylight exposure; move easy",
            "Protect sleep with a consistent wind-down and softer screens",
            "If you run sensitive, keep load lighter and use short reset breaks",
        ]
    return [
        "Use the steadier window for one or two focused work blocks",
        "Keep light movement and natural light in the day to reinforce rhythm",
        "Hydrate and keep caffeine earlier so sleep stays easier later",
    ]


def _member_health_status_line(value: Optional[Any], *, include_value: bool = False) -> str:
    if value is None:
        return "Health Status: calibrating"
    try:
        strain = float(value)
    except Exception:
        return "Health Status: calibrating"
    label = "very low strain"
    if strain >= 86:
        label = "very high strain"
    elif strain >= 71:
        label = "high strain"
    elif strain >= 41:
        label = "moderate strain"
    elif strain >= 21:
        label = "low strain"
    if include_value:
        return f"Health Status: {int(round(strain, 0))} ({label})"
    return f"Health Status: {label}"


def _member_driver_urgency(drivers: Sequence[Mapping[str, Any]]) -> str:
    severities = {_clean_text(item.get("severity")).lower() for item in drivers if isinstance(item, Mapping)}
    if any(level in {"high", "strong", "storm", "very_high", "unhealthy"} for level in severities):
        return "watch"
    if any(level in {"watch", "moderate", "elevated", "active"} for level in severities):
        return "notable"
    return "quiet"


def _stable_pick(values: Sequence[str], seed_text: str) -> str:
    options = [item for item in values if item]
    if not options:
        return ""
    digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    index = int(digest[:8], 16) % len(options)
    return options[index]


def build_public_earthscope_semantic(
    *,
    day: date,
    ctx: Mapping[str, Any],
) -> SemanticPayload:
    kp_now = _safe_float(ctx.get("kp_now"))
    kp_max = _safe_float(ctx.get("kp_max_24h"))
    bz_min = _safe_float(ctx.get("bz_min"))
    solar_wind = _safe_float(ctx.get("solar_wind_kms"))
    flares = _safe_float(ctx.get("flares_24h"))
    cmes = _safe_float(ctx.get("cmes_24h"))
    schumann = _safe_float(ctx.get("schumann_value_hz"))

    kp_band = _band_kp(kp_max)
    sw_band = _band_sw(solar_wind)
    bz_label = _bz_desc(bz_min)
    tone = _public_tone(kp_max, bz_min, solar_wind)
    driver_bits = _public_driver_bits(
        cmes_24h=cmes,
        flares_24h=flares,
        bz_desc=bz_label,
        sw_band=sw_band,
    )
    actions = [
        SemanticAction(
            key=f"public_action_{index + 1}",
            priority=index + 1,
            reason=tone,
            label=label,
        )
        for index, label in enumerate(_public_actions(tone))
    ]

    return SemanticPayload(
        schema_version="1.0",
        kind="earthscope_public_post",
        date=day.isoformat(),
        user_context={"audience": "public", "channel": "social_public"},
        facts={
            "kp_now": kp_now,
            "kp_max_24h": kp_max,
            "bz_min": bz_min,
            "solar_wind_kms": solar_wind,
            "flares_24h": flares,
            "cmes_24h": cmes,
            "schumann_value_hz": schumann,
            "aurora_headline": _clean_text(ctx.get("aurora_headline")) or None,
            "aurora_window": _clean_text(ctx.get("aurora_window")) or None,
            "quakes_count": ctx.get("quakes_count"),
            "severe_summary": _clean_text(ctx.get("severe_summary")) or None,
            "schumann_note": _clean_text(ctx.get("schumann_note")) or None,
            "first_person": bool(ctx.get("first_person")),
        },
        interpretation={
            "tone": tone,
            "bands": {
                "kp": kp_band,
                "sw": sw_band,
                "bz": bz_label,
            },
            "driver_bits": driver_bits,
        },
        actions={
            "primary": [item.__dict__ for item in actions],
            "secondary": [],
        },
        guardrails=SemanticGuardrails(
            confidence_overall=_public_confidence(kp_max, bz_min, solar_wind, schumann),
            claim_strength=_public_claim_strength(tone),
            evidence_basis=[
                basis
                for basis in (
                    "space_weather_daily" if any(item is not None for item in (kp_max, bz_min, solar_wind, flares, cmes)) else None,
                    "resonance_daily" if schumann is not None else None,
                    "contextual_impacts" if any(_clean_text(ctx.get(key)) for key in ("aurora_headline", "severe_summary")) else None,
                )
                if basis
            ],
            max_urgency=_public_max_urgency(tone),
        ),
        render_hints=SemanticRenderHints(
            preferred_summary_length="medium",
            preferred_detail_sections=["caption", "snapshot", "affects", "playbook"],
            humor_ok=True,
            metaphor_ok=True,
            persona_strength="light",
        ),
    )


def render_public_earthscope_post(
    payload: SemanticPayload,
    *,
    voice_profile: Optional[VoiceProfile] = None,
) -> Dict[str, str]:
    voice_profile = voice_profile or VoiceProfile.public_playful()
    facts = payload.facts or {}
    interpretation = payload.interpretation or {}

    kp_now = _safe_float(facts.get("kp_now"))
    kp_max = _safe_float(facts.get("kp_max_24h"))
    bz_min = _safe_float(facts.get("bz_min"))
    solar_wind = _safe_float(facts.get("solar_wind_kms"))
    flares = _safe_float(facts.get("flares_24h"))
    cmes = _safe_float(facts.get("cmes_24h"))
    schumann = _safe_float(facts.get("schumann_value_hz"))
    aurora_headline = _clean_text(facts.get("aurora_headline"))
    severe_summary = _clean_text(facts.get("severe_summary"))
    quakes_count = facts.get("quakes_count")
    tone = _clean_text(interpretation.get("tone")) or "neutral"
    bands = interpretation.get("bands") if isinstance(interpretation.get("bands"), Mapping) else {}
    driver_bits = [item for item in interpretation.get("driver_bits") or [] if isinstance(item, str) and item.strip()]

    title: str
    if kp_max is None and solar_wind is None:
        title = "Space Weather Update"
    elif kp_max is not None and kp_max >= 6:
        title = "Geomagnetic Storm Watch"
    elif kp_max is not None and kp_max >= 4:
        title = "Active Geomagnetics"
    elif solar_wind is not None and solar_wind >= 600:
        title = "High-Speed Solar Wind"
    else:
        title = _stable_pick(
            ["Magnetic Calm", "Steady Field", "Quiet Skies", "Clear Runway"],
            f"{payload.date}|{voice_profile.channel}|title",
        )

    parts: list[str] = []
    if kp_max is not None:
        parts.append(f"Kp {_fmt_num(kp_max, 1)} ({_clean_text(bands.get('kp')) or _band_kp(kp_max)})")
    if solar_wind is not None:
        parts.append(f"SW {int(round(solar_wind))} km/s ({_clean_text(bands.get('sw')) or _band_sw(solar_wind)})")
    if bz_min is not None:
        parts.append(f"Bz {_fmt_num(bz_min, 1)} nT ({_clean_text(bands.get('bz')) or _bz_desc(bz_min)})")
    cap_lead = " • ".join(parts) if parts else "Space weather update"

    trailing_map = {
        "stormy": "Charged backdrop today. Shorter bursts tend to beat heroic effort.",
        "unsettled": "Some variability is in the mix. Build in breaks before your body asks.",
        "calm": "Cleaner runway today. Good time for steady work and quieter recovery.",
        "neutral": "Moderate conditions overall. Consistency still tends to work best.",
    }
    caption = f"{cap_lead}. {trailing_map.get(tone, trailing_map['neutral'])}"

    snapshot_lines: list[str] = []
    if kp_now is not None:
        snapshot_lines.append(f"- Kp now: {_fmt_num(kp_now, 2)}")
    if kp_max is not None:
        snapshot_lines.append(f"- Kp max (24h): {_fmt_num(kp_max, 2)}")
    if solar_wind is not None:
        snapshot_lines.append(f"- Solar wind: {int(round(solar_wind))} km/s")
    if bz_min is not None:
        snapshot_lines.append(f"- Bz: {_fmt_num(bz_min, 1)} nT ({_clean_text(bands.get('bz')) or _bz_desc(bz_min)})")
    if flares is not None:
        snapshot_lines.append(f"- Flares (24h): {int(round(flares))}")
    if cmes is not None:
        snapshot_lines.append(f"- CMEs (24h): {int(round(cmes))}")
    if schumann is not None:
        snapshot_lines.append(f"- Schumann f0: {_fmt_num(schumann, 2)} Hz")
    snapshot = "\n".join(snapshot_lines)

    if tone == "stormy":
        qualitative_lines = ["It's an electrified day. Expect shorter surges and dips in energy."]
    elif tone == "unsettled":
        qualitative_lines = ["Things are looking lively in the field today, so expect some fluctuations."]
    elif tone == "calm":
        qualitative_lines = ["Steadier field today. It is a good day for focused work and cleaner recovery."]
    else:
        qualitative_lines = ["The field looks fairly middle-of-the-road today. Consistency wins."]
    if driver_bits:
        qualitative_lines.append("Drivers: " + ", ".join(driver_bits) + ".")
    if schumann is not None:
        qualitative_lines.append("Schumann resonance has been lively enough to notice for some sensitive systems.")
    else:
        qualitative_lines.append("Resonance looks relatively ordinary overall.")
    if aurora_headline:
        qualitative_lines.append("Aurora chances look more interesting at higher latitudes.")
    if quakes_count:
        qualitative_lines.append("Recent notable earthquakes were logged, so keep news checks brief if stress spirals you.")
    if severe_summary:
        qualitative_lines.append("Regional severe-weather alerts are active, so local guidance matters most there.")
    qualitative_lines.append("Keep a steady rhythm and make regulation easier than recovery.")
    qualitative_snapshot = "Space Weather Snapshot\n" + " ".join(qualitative_lines)

    first_person = bool(facts.get("first_person"))
    if tone in {"stormy", "unsettled"}:
        affects_lines = [
            "- Focus/energy: Expect more variability and shorter clean focus windows.",
            "- Autonomic/HRV: Active space weather can overlap with a less settled baseline for some.",
            "- Sleep: Protect the wind-down window and keep late stimulation lighter.",
            f"- {'Clinician' if first_person else 'Sensitivity'} note: If you run sensitive, pace flares instead of forcing through them.",
        ]
    else:
        affects_lines = [
            "- Focus/energy: Steadier conditions make longer focus windows easier to use.",
            "- Autonomic/HRV: A quieter field can make recovery work feel more cooperative.",
            "- Sleep: Keep evening light warm and low so the calmer window carries through.",
        ]
        if first_person:
            affects_lines.append("- Clinician note: I usually see steadier recovery patterns on days like this.")
    affects = "\n".join(affects_lines)

    action_rows = payload.actions.get("primary") if isinstance(payload.actions, Mapping) else []
    playbook_lines = [
        f"- {str(item.get('label') or '').strip()}"
        for item in action_rows
        if isinstance(item, Mapping) and str(item.get("label") or "").strip()
    ]
    playbook = "\n".join(playbook_lines)
    body_markdown = "Gaia Eyes — Daily EarthScope\n\n" + "\n\n".join(
        [section for section in (qualitative_snapshot, affects, playbook) if section.strip()]
    ).strip()

    return {
        "title": title,
        "caption": caption.strip(),
        "snapshot": snapshot.strip(),
        "qualitative_snapshot": qualitative_snapshot.strip(),
        "affects": affects.strip(),
        "playbook": playbook.strip(),
        "hashtags": _PUBLIC_HASHTAGS,
        "body_markdown": body_markdown,
    }


def build_member_earthscope_semantic(
    *,
    day: date,
    health_status: Optional[Any],
    highlights: Sequence[Mapping[str, Any]],
    drivers: Sequence[Mapping[str, Any]],
    driver_lines: Sequence[str],
    ranked_symptoms: Sequence[Mapping[str, Any]],
    condition_note: Optional[str],
    actions: Sequence[str],
    disclaimer: str,
    seed_now_text: str = "",
    seed_summary: str = "",
    title: str = "Your EarthScope",
    caption: Optional[str] = None,
) -> SemanticPayload:
    symptom_phrases = [
        _clean_text(item.get("phrase"))
        for item in ranked_symptoms
        if isinstance(item, Mapping) and _clean_text(item.get("phrase"))
    ]
    action_items = [
        SemanticAction(
            key=f"member_action_{index + 1}",
            priority=index + 1,
            reason="support",
            label=str(label).strip(),
        )
        for index, label in enumerate(actions)
        if str(label).strip()
    ]

    confidence = "moderate" if drivers or symptom_phrases else "low"
    if len(symptom_phrases) >= 2:
        confidence = "high"

    return SemanticPayload(
        schema_version="1.0",
        kind="earthscope_member_post",
        date=day.isoformat(),
        user_context={"audience": "member", "channel": "app_detail"},
        facts={
            "health_status": health_status,
            "gauges": [dict(item) for item in highlights if isinstance(item, Mapping)],
            "drivers": [dict(item) for item in drivers if isinstance(item, Mapping)],
            "driver_lines": [str(item).strip() for item in driver_lines if str(item).strip()],
            "symptom_phrases": symptom_phrases,
        },
        interpretation={
            "seed_now_text": _clean_text(seed_now_text) or None,
            "seed_summary": _clean_text(seed_summary) or None,
            "condition_note": _clean_text(condition_note) or None,
            "disclaimer": _clean_text(disclaimer),
            "title": _clean_text(title) or "Your EarthScope",
            "caption": _clean_text(caption) or None,
        },
        actions={
            "primary": [item.__dict__ for item in action_items],
            "secondary": [],
        },
        guardrails=SemanticGuardrails(
            confidence_overall=confidence,
            claim_strength="may_notice" if symptom_phrases else "observe_only",
            evidence_basis=[
                basis
                for basis in (
                    "current_driver_mix" if drivers else None,
                    "current_gauge_state" if highlights else None,
                    "symptom_ranking" if symptom_phrases else None,
                )
                if basis
            ],
            max_urgency=_member_driver_urgency(drivers),
        ),
        render_hints=SemanticRenderHints(
            preferred_summary_length="medium",
            preferred_detail_sections=["now", "drivers", "what_you_may_feel", "supportive_actions"],
            humor_ok=False,
            metaphor_ok=False,
            persona_strength="light",
        ),
    )


def render_member_earthscope_post(
    payload: SemanticPayload,
    *,
    voice_profile: Optional[VoiceProfile] = None,
) -> Dict[str, Any]:
    voice_profile = voice_profile or VoiceProfile(mode="scientific", tone="balanced", guide="none", channel="app_detail")
    _ = voice_profile
    facts = payload.facts or {}
    interpretation = payload.interpretation or {}
    driver_lines = [item for item in facts.get("driver_lines") or [] if isinstance(item, str) and item.strip()]
    symptom_phrases = [item for item in facts.get("symptom_phrases") or [] if isinstance(item, str) and item.strip()]
    condition_note = _clean_text(interpretation.get("condition_note"))
    disclaimer = _clean_text(interpretation.get("disclaimer"))

    now_text = _clean_text(interpretation.get("seed_now_text"))
    if not now_text:
        drivers = [item for item in facts.get("drivers") or [] if isinstance(item, Mapping)]
        if drivers:
            lead = drivers[0]
            label = _clean_text(lead.get("label") or lead.get("key") or "Current drivers")
            state = _clean_text(lead.get("state")) or "active"
            now_text = f"{label} is leading right now and looks {state.lower()}."
        else:
            now_text = "Right now, the outside signal mix looks fairly even."
        now_text = f"{now_text} {_member_health_status_line(facts.get('health_status'))}".strip()

    summary = _clean_text(interpretation.get("seed_summary"))
    if not summary:
        if symptom_phrases:
            summary = (
                "Based on the current drivers and your gauges, the strongest possibilities right now are "
                + ", ".join(symptom_phrases[:-1])
                + (f", and {symptom_phrases[-1]}" if len(symptom_phrases) > 1 else symptom_phrases[0])
                + "."
            )
        else:
            summary = "Based on the current drivers and your gauges, the main shifts still look fairly light right now."
        if condition_note:
            summary += f" {condition_note}"
        summary += " These are possibilities, not certainties. If something stands out, log it in the symptom tracker so your personal pattern gets sharper over time."

    action_rows = payload.actions.get("primary") if isinstance(payload.actions, Mapping) else []
    actions = [
        str(item.get("label") or "").strip()
        for item in action_rows
        if isinstance(item, Mapping) and str(item.get("label") or "").strip()
    ]

    driver_block = "\n".join(f"- {line}" for line in driver_lines) if driver_lines else "- No major external drivers are flagged right now."
    action_block = "\n".join(f"- {line}" for line in actions)
    body = (
        f"## Now\n{now_text}\n\n"
        f"## Current Drivers\n{driver_block}\n\n"
        f"## What You May Feel\n{summary}\n\n"
        f"## Supportive Actions\n{action_block}\n\n"
        f"## Disclaimer\n{disclaimer}\n"
    )
    return {
        "title": _clean_text(interpretation.get("title")) or "Your EarthScope",
        "caption": interpretation.get("caption"),
        "body_markdown": body,
        "driver_lines": driver_lines,
        "actions": actions,
        "health_line": _member_health_status_line(facts.get("health_status"), include_value=False),
    }
