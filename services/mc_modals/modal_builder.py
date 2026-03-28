from __future__ import annotations

from collections import defaultdict
import hashlib
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from services.personalization.health_context import (
    AIRWAY_KEYS,
    AUTONOMIC_KEYS,
    HEAD_PRESSURE_KEYS,
    PAIN_FLARE_KEYS,
    SINUS_KEYS,
    SLEEP_DISRUPTION_KEYS,
    PersonalizationProfile,
    build_personalization_profile,
)


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
    "pain": ["pressure", "temp", "aqi", "allergens"],
    "focus": ["pressure", "aqi", "allergens", "kp", "sw", "schumann"],
    "heart": ["kp", "bz", "sw", "aqi"],
    "stamina": ["temp", "aqi", "allergens", "sw"],
    "energy": ["temp", "aqi", "allergens", "sw", "kp"],
    "sleep": ["pressure", "temp", "allergens", "kp", "bz", "schumann"],
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
    "allergens": [
        "Sinus pressure or headache may feel more noticeable for some people on allergy-heavy days.",
        "Brain fog or fatigue can show up faster for some people when pollen is up.",
        "Breathing or histamine-style irritation may be easier to notice for some people.",
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
    "allergens": [
        "Use filters, rinses, or cleaner indoor air if those usually help you.",
        "Shift outdoor time away from your worst trigger windows when possible.",
        "Hydrate and keep effort a little steadier if allergy load tends to stack fatigue.",
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

_DRIVER_CONTEXT = {
    "pressure": "This driver is most often about head pressure, sinus or ear pressure, and joint stiffness.",
    "temp": "This driver is more about body load, stiffness, and recovery drag.",
    "aqi": "This driver is more about fatigue, fogginess, sinus irritation, or breathing irritation.",
    "allergens": "This driver is more about sinus pressure, headache sensitivity, brain fog, fatigue, and breathing or histamine-style irritation.",
    "kp": "This driver is more about restless edge, sleep disruption, focus drift, and nervous-system reactivity.",
    "bz": "This driver is more about restless edge, sleep disruption, focus drift, and nervous-system reactivity.",
    "sw": "This driver is more about restless edge, sleep disruption, focus drift, and nervous-system reactivity.",
    "schumann": "This driver is more about restless edge, sleep sensitivity, focus drift, and nervous-system reactivity.",
}

_GAUGE_SUPPORT_TERMS = {
    "pain": "pain, stiffness, or body load",
    "focus": "focus drift, brain fog, or sensory overload",
    "heart": "heart load, reactivity, or recovery strain",
    "stamina": "fatigue, body load, or recovery drag",
    "energy": "fatigue, energy swings, or recovery drag",
    "sleep": "lighter sleep, a harder wind-down, or restless edge",
    "mood": "overstimulation, nervous-system reactivity, or restless edge",
    "health_status": "overall body load and recovery strain",
}

_THEME_SUMMARY_LINES = {
    "headache_day": "Head pressure may be easier to notice than usual if this pattern holds.",
    "pain_flare_day": "Pain or stiffness may be easier to notice than usual if this pattern holds.",
    "fatigue_day": "Fatigue may stand out more than usual if this pattern holds.",
    "anxiety_day": "A restless edge may be easier to notice than usual if this pattern holds.",
    "poor_sleep_day": "Sleep may feel lighter or less settled if this pattern holds.",
    "focus_fog_day": "Focus may feel driftier than usual if this pattern holds.",
    "hrv_dip_day": "Recovery may feel less steady than usual if this pattern holds.",
    "high_hr_day": "Your system may feel a little more loaded than usual if this pattern holds.",
    "short_sleep_day": "Sleep length or recovery may feel lighter than usual if this pattern holds.",
}

_DRIVER_PREFILL = {
    "pressure": ["HEADACHE", "NERVE_PAIN", "PAIN"],
    "temp": ["FATIGUE", "PAIN", "STIFFNESS"],
    "aqi": ["HEADACHE", "DRAINED", "RESP_IRRITATION"],
    "allergens": ["SINUS_PRESSURE", "HEADACHE", "BRAIN_FOG"],
    "kp": ["ANXIOUS", "DRAINED", "BRAIN_FOG"],
    "bz": ["ANXIOUS", "DRAINED", "BRAIN_FOG"],
    "sw": ["ANXIOUS", "DRAINED", "BRAIN_FOG"],
    "schumann": ["WIRED", "BRAIN_FOG", "INSOMNIA"],
}

_DRIVER_QUICK_LOG = {
    "pressure": [
        {"code": "HEADACHE", "label": "Headache"},
        {"code": "NERVE_PAIN", "label": "Nerve pain"},
        {"code": "PAIN", "label": "Pain flare"},
    ],
    "temp": [
        {"code": "FATIGUE", "label": "Fatigue"},
        {"code": "PAIN", "label": "Body aches"},
        {"code": "STIFFNESS", "label": "Stiffness"},
    ],
    "aqi": [
        {"code": "HEADACHE", "label": "Headache"},
        {"code": "DRAINED", "label": "Brain fog"},
        {"code": "RESP_IRRITATION", "label": "Breathing irritation"},
    ],
    "allergens": [
        {"code": "SINUS_PRESSURE", "label": "Sinus pressure"},
        {"code": "HEADACHE", "label": "Headache"},
        {"code": "BRAIN_FOG", "label": "Brain fog"},
    ],
    "kp": [
        {"code": "ANXIOUS", "label": "Anxious"},
        {"code": "DRAINED", "label": "Drained"},
        {"code": "BRAIN_FOG", "label": "Brain fog"},
    ],
    "bz": [
        {"code": "ANXIOUS", "label": "Anxious"},
        {"code": "DRAINED", "label": "Drained"},
        {"code": "BRAIN_FOG", "label": "Brain fog"},
    ],
    "sw": [
        {"code": "ANXIOUS", "label": "Anxious"},
        {"code": "DRAINED", "label": "Drained"},
        {"code": "BRAIN_FOG", "label": "Brain fog"},
    ],
    "schumann": [
        {"code": "WIRED", "label": "Jittery"},
        {"code": "BRAIN_FOG", "label": "Focus drift"},
        {"code": "INSOMNIA", "label": "Sleep sensitivity"},
    ],
}

_PERSONALIZED_DRIVER_CONTENT = {
    ("pressure", "head_pressure"): {
        "notices": [
            "Headache or migraine sensitivity may feel closer to the surface for some people.",
            "Head or sinus pressure can feel more noticeable for some people during barometric swings.",
            "Light sensitivity can tag along for some people when head pressure is up.",
        ],
        "actions": [
            "Hydrate and lower light or screen intensity if that usually helps.",
            "Use a darker, quieter space if head pressure feels easier to trigger.",
            "Reduce extra sensory load and pace demanding blocks.",
        ],
        "quick_log": [
            {"code": "HEADACHE", "label": "Headache"},
            {"code": "SINUS_PRESSURE", "label": "Sinus pressure"},
            {"code": "LIGHT_SENSITIVITY", "label": "Light sensitivity"},
        ],
    },
    ("pressure", "pain_flare"): {
        "notices": [
            "Joint pain or stiffness may feel more noticeable for some people during pressure swings.",
            "Body aches or a pain flare can show up faster for some people.",
            "Pacing can feel more important for some people when pressure changes stack up.",
        ],
        "actions": [
            "Use warmth or gentle movement if that usually helps your body settle.",
            "Pace heavier tasks and add shorter resets between effort blocks.",
            "Hydrate steadily and avoid stacking long exertion back-to-back.",
        ],
        "quick_log": [
            {"code": "JOINT_PAIN", "label": "Joint pain"},
            {"code": "PAIN", "label": "Pain flare"},
            {"code": "STIFFNESS", "label": "Stiffness"},
        ],
    },
    ("temp", "pain_flare"): {
        "notices": [
            "Body aches or stiffness may feel more noticeable for some people during sharper temperature swings.",
            "Fibro-like pain or fatigue sensitivity can feel closer to the surface for some people.",
            "Recovery can feel slower for some people when temperature shifts are abrupt.",
        ],
        "actions": [
            "Favor warmth, layering, and gentle movement if those usually help.",
            "Pace exertion and leave more margin for recovery than usual.",
            "Keep hydration and meals steady through the swing.",
        ],
        "quick_log": [
            {"code": "FATIGUE", "label": "Fatigue"},
            {"code": "PAIN", "label": "Pain flare"},
            {"code": "STIFFNESS", "label": "Stiffness"},
        ],
    },
    ("aqi", "sinus"): {
        "notices": [
            "Sinus pressure or irritation may feel more noticeable for some people in poorer air.",
            "Brain fog can show up faster for some people when air quality slips.",
            "Headache can ride along with sinus sensitivity for some people.",
        ],
        "actions": [
            "Use cleaner indoor air or HEPA support if that is available to you.",
            "Saline or rinse support may feel soothing for some people.",
            "Reduce outdoor exposure during peak irritation windows when possible.",
        ],
        "quick_log": [
            {"code": "SINUS_PRESSURE", "label": "Sinus pressure"},
            {"code": "BRAIN_FOG", "label": "Brain fog"},
            {"code": "HEADACHE", "label": "Headache"},
        ],
    },
    ("aqi", "airway"): {
        "notices": [
            "Breathing irritation may feel more noticeable for some people when air quality worsens.",
            "Chest tightness or a heavier breathing feel can show up for some people.",
            "Fatigue can land faster for some people when irritated air stacks with effort.",
        ],
        "actions": [
            "Reduce outdoor exertion and favor cleaner indoor air when possible.",
            "Use shorter effort blocks and pause sooner if breathing feels irritated.",
            "Hydrate steadily and lower extra exposure where you can.",
        ],
        "quick_log": [
            {"code": "RESP_IRRITATION", "label": "Breathing irritation"},
            {"code": "CHEST_TIGHTNESS", "label": "Chest tightness"},
            {"code": "FATIGUE", "label": "Fatigue"},
        ],
    },
    ("allergens", "sinus"): {
        "notices": [
            "Sinus pressure or headache can feel more noticeable for some people on higher-pollen days.",
            "Brain fog or drained energy can show up faster for some people when allergens stack up.",
            "Histamine-style irritation can feel closer to the surface for some people.",
        ],
        "actions": [
            "Use the allergy supports that usually help you before symptoms stack up.",
            "Reduce exposure during your most irritating outdoor windows when possible.",
            "Keep hydration and recovery basics steadier than usual.",
        ],
        "quick_log": [
            {"code": "SINUS_PRESSURE", "label": "Sinus pressure"},
            {"code": "HEADACHE", "label": "Headache"},
            {"code": "BRAIN_FOG", "label": "Brain fog"},
        ],
    },
    ("allergens", "airway"): {
        "notices": [
            "Breathing irritation can feel more noticeable for some people on allergy-heavy days.",
            "Chest tightness or a scratchier airway feel can show up for some people.",
            "Fatigue can land faster when allergen irritation stacks with effort.",
        ],
        "actions": [
            "Shift outdoor exertion to lower-trigger windows when you can.",
            "Use cleaner indoor air and your normal breathing supports if they help.",
            "Pause sooner and shorten effort blocks if irritation starts building.",
        ],
        "quick_log": [
            {"code": "RESP_IRRITATION", "label": "Breathing irritation"},
            {"code": "CHEST_TIGHTNESS", "label": "Chest tightness"},
            {"code": "FATIGUE", "label": "Fatigue"},
        ],
    },
    ("kp", "autonomic"): {
        "notices": [
            "Palpitations or heart-awareness can feel easier to notice for some people during geomagnetic activity.",
            "A wired or restless feeling can show up for some people when autonomic load feels touchier.",
            "Energy can feel less steady or more drained after stimulation for some people.",
        ],
        "actions": [
            "Hydrate and use electrolytes if that is already part of your routine.",
            "Avoid sudden exertion or fast position changes if those usually hit you.",
            "Use shorter, steadier activity blocks with recovery breaks.",
        ],
        "quick_log": [
            {"code": "PALPITATIONS", "label": "Palpitations"},
            {"code": "WIRED", "label": "Wired"},
            {"code": "DRAINED", "label": "Drained"},
        ],
    },
    ("sw", "autonomic"): {
        "notices": [
            "Palpitations or heart-awareness can feel easier to notice for some people during solar wind spikes.",
            "A wired or restless feeling may show up for some people when autonomic load feels touchier.",
            "Energy can feel less steady or more drained after stimulation for some people.",
        ],
        "actions": [
            "Hydrate and use electrolytes if that is already part of your routine.",
            "Avoid sudden exertion or fast position changes if those usually hit you.",
            "Use shorter, steadier activity blocks with recovery breaks.",
        ],
        "quick_log": [
            {"code": "PALPITATIONS", "label": "Palpitations"},
            {"code": "WIRED", "label": "Wired"},
            {"code": "DRAINED", "label": "Drained"},
        ],
    },
    ("bz", "autonomic"): {
        "notices": [
            "Palpitations or heart-awareness can feel easier to notice for some people during stronger Bz coupling.",
            "A wired or restless feeling may show up for some people when autonomic load feels touchier.",
            "Energy can feel less steady or more drained after stimulation for some people.",
        ],
        "actions": [
            "Hydrate and use electrolytes if that is already part of your routine.",
            "Avoid sudden exertion or fast position changes if those usually hit you.",
            "Use shorter, steadier activity blocks with recovery breaks.",
        ],
        "quick_log": [
            {"code": "PALPITATIONS", "label": "Palpitations"},
            {"code": "WIRED", "label": "Wired"},
            {"code": "DRAINED", "label": "Drained"},
        ],
    },
    ("kp", "sleep"): {
        "notices": [
            "Restless sleep or longer sleep onset can show up for some people during geomagnetic activity.",
            "A wired feeling later in the day can make wind-down less predictable for some people.",
            "Energy or mood can feel more reactive after a rough night for some people.",
        ],
        "actions": [
            "Lower light and stimulation earlier if your sleep is feeling touchy.",
            "Protect your wind-down window and keep bedtime cues simple.",
            "Keep late caffeine and extra activation lighter than usual.",
        ],
        "quick_log": [
            {"code": "RESTLESS_SLEEP", "label": "Restless sleep"},
            {"code": "INSOMNIA", "label": "Insomnia"},
            {"code": "WIRED", "label": "Wired"},
        ],
    },
    ("sw", "sleep"): {
        "notices": [
            "Restless sleep or longer sleep onset can show up for some people during solar wind spikes.",
            "A wired feeling later in the day can make wind-down less predictable for some people.",
            "Energy or mood can feel more reactive after a rough night for some people.",
        ],
        "actions": [
            "Lower light and stimulation earlier if your sleep is feeling touchy.",
            "Protect your wind-down window and keep bedtime cues simple.",
            "Keep late caffeine and extra activation lighter than usual.",
        ],
        "quick_log": [
            {"code": "RESTLESS_SLEEP", "label": "Restless sleep"},
            {"code": "INSOMNIA", "label": "Insomnia"},
            {"code": "WIRED", "label": "Wired"},
        ],
    },
    ("bz", "sleep"): {
        "notices": [
            "Restless sleep or longer sleep onset can show up for some people during stronger Bz coupling.",
            "A wired feeling later in the day can make wind-down less predictable for some people.",
            "Energy or mood can feel more reactive after a rough night for some people.",
        ],
        "actions": [
            "Lower light and stimulation earlier if your sleep is feeling touchy.",
            "Protect your wind-down window and keep bedtime cues simple.",
            "Keep late caffeine and extra activation lighter than usual.",
        ],
        "quick_log": [
            {"code": "RESTLESS_SLEEP", "label": "Restless sleep"},
            {"code": "INSOMNIA", "label": "Insomnia"},
            {"code": "WIRED", "label": "Wired"},
        ],
    },
    ("schumann", "sleep"): {
        "notices": [
            "A buzzy or restless feeling may show up for some people when Schumann variability is larger.",
            "Sleep sensitivity can feel more noticeable for some people when the day already feels overstimulating.",
            "Focus or mood can feel a little more reactive for some people after lighter sleep.",
        ],
        "actions": [
            "Lower light and sensory load earlier if sleep feels easier to disrupt.",
            "Keep your wind-down routine simple and predictable tonight.",
            "Reduce extra stimulation and leave more buffer before bed.",
        ],
        "quick_log": [
            {"code": "RESTLESS_SLEEP", "label": "Restless sleep"},
            {"code": "INSOMNIA", "label": "Insomnia"},
            {"code": "WIRED", "label": "Wired"},
        ],
    },
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
    "allergens": "Allergen load looks relatively steady right now.",
    "kp": "Geomagnetic activity looks relatively steady right now.",
    "bz": "Bz coupling looks relatively steady right now.",
    "sw": "Solar wind speed looks relatively steady right now.",
    "schumann": "Schumann variability looks relatively steady right now.",
}

_DRIVER_SHORT_TIP = {
    "pressure": "Normal hydration and pacing should be enough for most people.",
    "temp": "Dress for comfort and keep hydration steady if conditions change.",
    "aqi": "Normal outdoor plans may be fine if you usually tolerate them well.",
    "allergens": "Use your usual allergy supports if you already know they help.",
    "kp": "Keep your normal pacing and sleep routine steady.",
    "bz": "Keep effort steady and avoid overreacting to small shifts.",
    "sw": "Use your usual pacing and sleep routine for now.",
    "schumann": "Keep sensory load and sleep routine steady if that usually helps.",
}

_CHECKIN_USABLE_ENERGY_LABELS = {
    "plenty": "plenty of usable energy",
    "enough": "enough usable energy",
    "limited": "limited usable energy",
    "very_limited": "very limited usable energy",
}

_CHECKIN_ENERGY_DETAIL_LABELS = {
    "tired": "tired",
    "drained": "drained",
    "heavy_body": "a heavy-body day",
    "brain_fog": "brain fog",
    "crashed_later": "a later crash",
}

_CHECKIN_PAIN_LABELS = {
    "none": "no unusual pain",
    "a_little": "a little pain",
    "noticeable": "noticeable pain",
    "strong": "strong pain",
}

_CHECKIN_MOOD_LABELS = {
    "calm": "a calmer day",
    "slightly_off": "a slightly off day",
    "noticeable": "a more sensitive day",
    "strong": "a strongly affected day",
}

_CHECKIN_SLEEP_IMPACT_LABELS = {
    "yes_strongly": "sleep affected the day",
    "yes_somewhat": "sleep affected part of the day",
    "not_much": "sleep was not the main issue",
    "unsure": "sleep impact was hard to read",
}

_SYMPTOM_DISPLAY_LABELS = {
    "ANXIOUS": "anxious",
    "BRAIN_FOG": "brain fog",
    "CHEST_TIGHTNESS": "chest tightness",
    "DRAINED": "low energy",
    "FATIGUE": "fatigue",
    "FOCUS_DRIFT": "focus drift",
    "HEADACHE": "a headache",
    "INSOMNIA": "insomnia",
    "JOINT_PAIN": "joint pain",
    "LIGHT_SENSITIVITY": "light sensitivity",
    "MIGRAINE": "a migraine",
    "NERVE_PAIN": "nerve pain",
    "PAIN": "a pain flare",
    "PALPITATIONS": "palpitations",
    "RESP_IRRITATION": "breathing irritation",
    "RESTLESS_SLEEP": "restless sleep",
    "SINUS_PRESSURE": "sinus pressure",
    "STIFFNESS": "stiffness",
    "WIRED": "a wired stretch",
}

_GAUGE_MODAL_STATE_LABELS = {
    "energy": {
        "low": "Steady",
        "mild": "Variable",
        "elevated": "Reduced",
        "high": "Low capacity",
    },
    "sleep": {
        "low": "Steady",
        "mild": "Lighter",
        "elevated": "Reduced",
        "high": "Reduced",
    },
    "stamina": {
        "low": "Steady",
        "mild": "Less steady",
        "elevated": "Reduced",
        "high": "Reduced",
    },
}

_GAUGE_STATE_LINES = {
    "pain": {
        "active": "Pain load looks elevated right now.",
        "steady": "Pain load looks relatively steady right now.",
    },
    "focus": {
        "active": "Focus load looks more strained right now.",
        "steady": "Focus looks relatively steady right now.",
    },
    "heart": {
        "active": "Heart load looks more watchful right now.",
        "steady": "Heart load looks relatively steady right now.",
    },
    "stamina": {
        "active": "Recovery capacity looks reduced right now.",
        "steady": "Recovery capacity looks relatively steady right now.",
    },
    "energy": {
        "active": "Capacity looks reduced right now.",
        "steady": "Capacity looks fairly steady right now.",
    },
    "sleep": {
        "active": "Recovery looks reduced right now.",
        "steady": "Recovery looks relatively steady right now.",
    },
    "mood": {
        "active": "Mood looks more sensitive right now.",
        "steady": "Mood looks relatively steady right now.",
    },
    "health_status": {
        "active": "Overall system load looks elevated right now.",
        "steady": "Overall system load looks relatively steady right now.",
    },
}

_GAUGE_ALLOWED_EFFECT_BUCKETS = {
    "pain": {"head_pressure", "sinus_irritation", "pain_flare"},
    "focus": {"focus_drag", "head_pressure", "fatigue_fog"},
    "heart": {"heart_reactivity", "fatigue_fog", "restlessness"},
    "stamina": {"fatigue_fog", "pain_flare", "sleep_fragility"},
    "energy": {"fatigue_fog", "restlessness", "sleep_fragility"},
    "sleep": {"sleep_fragility", "fatigue_fog", "restlessness"},
    "mood": {"mood_sensitivity", "restlessness", "fatigue_fog"},
    "health_status": {"fatigue_fog", "head_pressure", "pain_flare", "restlessness", "sleep_fragility"},
}

_EFFECT_BUCKET_PRIORITY = {
    "head_pressure": 9,
    "sinus_irritation": 8,
    "fatigue_fog": 10,
    "focus_drag": 7,
    "sleep_fragility": 8,
    "restlessness": 7,
    "pain_flare": 8,
    "heart_reactivity": 8,
    "mood_sensitivity": 7,
}

_EFFECT_BUCKET_QUICK_LOG = {
    "head_pressure": [
        {"code": "HEADACHE", "label": "Headache"},
        {"code": "SINUS_PRESSURE", "label": "Sinus pressure"},
        {"code": "BRAIN_FOG", "label": "Brain fog"},
    ],
    "sinus_irritation": [
        {"code": "SINUS_PRESSURE", "label": "Sinus pressure"},
        {"code": "HEADACHE", "label": "Headache"},
        {"code": "RESP_IRRITATION", "label": "Breathing irritation"},
    ],
    "fatigue_fog": [
        {"code": "DRAINED", "label": "Drained"},
        {"code": "BRAIN_FOG", "label": "Brain fog"},
        {"code": "FATIGUE", "label": "Fatigue"},
    ],
    "focus_drag": [
        {"code": "BRAIN_FOG", "label": "Brain fog"},
        {"code": "FOCUS_DRIFT", "label": "Focus drift"},
        {"code": "HEADACHE", "label": "Headache"},
    ],
    "sleep_fragility": [
        {"code": "RESTLESS_SLEEP", "label": "Restless sleep"},
        {"code": "INSOMNIA", "label": "Insomnia"},
        {"code": "DRAINED", "label": "Unrefreshed"},
    ],
    "restlessness": [
        {"code": "ANXIOUS", "label": "Anxious"},
        {"code": "WIRED", "label": "Wired"},
        {"code": "DRAINED", "label": "Drained"},
    ],
    "pain_flare": [
        {"code": "PAIN", "label": "Pain flare"},
        {"code": "JOINT_PAIN", "label": "Joint pain"},
        {"code": "STIFFNESS", "label": "Stiffness"},
    ],
    "heart_reactivity": [
        {"code": "PALPITATIONS", "label": "Palpitations"},
        {"code": "CHEST_TIGHTNESS", "label": "Chest tightness"},
        {"code": "RESP_IRRITATION", "label": "Breathing irritation"},
    ],
    "mood_sensitivity": [
        {"code": "ANXIOUS", "label": "Anxious"},
        {"code": "WIRED", "label": "Wired"},
        {"code": "DRAINED", "label": "Drained"},
    ],
}

_SYMPTOM_CODES_BY_GAUGE = {
    "pain": {"HEADACHE", "MIGRAINE", "SINUS_PRESSURE", "LIGHT_SENSITIVITY", "PAIN", "NERVE_PAIN", "JOINT_PAIN", "STIFFNESS"},
    "focus": {"BRAIN_FOG", "FOCUS_DRIFT", "HEADACHE", "DRAINED", "FATIGUE"},
    "heart": {"PALPITATIONS", "CHEST_TIGHTNESS", "RESP_IRRITATION", "ANXIOUS", "WIRED"},
    "stamina": {"FATIGUE", "DRAINED", "PAIN", "JOINT_PAIN", "STIFFNESS", "RESTLESS_SLEEP", "INSOMNIA"},
    "energy": {"FATIGUE", "DRAINED", "BRAIN_FOG", "RESTLESS_SLEEP", "INSOMNIA", "WIRED"},
    "sleep": {"RESTLESS_SLEEP", "INSOMNIA", "WIRED", "ANXIOUS", "DRAINED"},
    "mood": {"ANXIOUS", "WIRED", "DRAINED"},
    "health_status": {"HEADACHE", "MIGRAINE", "SINUS_PRESSURE", "PAIN", "NERVE_PAIN", "JOINT_PAIN", "STIFFNESS", "FATIGUE", "DRAINED", "BRAIN_FOG", "RESTLESS_SLEEP", "INSOMNIA", "ANXIOUS", "PALPITATIONS", "RESP_IRRITATION"},
}

_SYMPTOM_EFFECT_BUCKETS = {
    "ANXIOUS": {"restlessness", "mood_sensitivity", "heart_reactivity"},
    "BRAIN_FOG": {"fatigue_fog", "focus_drag"},
    "CHEST_TIGHTNESS": {"heart_reactivity"},
    "DRAINED": {"fatigue_fog"},
    "FATIGUE": {"fatigue_fog"},
    "FOCUS_DRIFT": {"focus_drag"},
    "HEADACHE": {"head_pressure"},
    "INSOMNIA": {"sleep_fragility", "fatigue_fog"},
    "JOINT_PAIN": {"pain_flare"},
    "LIGHT_SENSITIVITY": {"head_pressure"},
    "MIGRAINE": {"head_pressure"},
    "NERVE_PAIN": {"pain_flare"},
    "PAIN": {"pain_flare"},
    "PALPITATIONS": {"heart_reactivity"},
    "RESP_IRRITATION": {"heart_reactivity"},
    "RESTLESS_SLEEP": {"sleep_fragility", "fatigue_fog"},
    "SINUS_PRESSURE": {"sinus_irritation", "head_pressure"},
    "STIFFNESS": {"pain_flare"},
    "WIRED": {"restlessness", "sleep_fragility"},
}

_DRIVER_EFFECT_BUCKETS = {
    "pressure": {"head_pressure", "pain_flare"},
    "temp": {"pain_flare", "fatigue_fog"},
    "aqi": {"sinus_irritation", "fatigue_fog", "focus_drag", "heart_reactivity"},
    "allergens": {"sinus_irritation", "head_pressure", "fatigue_fog"},
    "kp": {"restlessness", "sleep_fragility", "focus_drag"},
    "bz": {"restlessness", "sleep_fragility", "focus_drag"},
    "sw": {"restlessness", "sleep_fragility", "fatigue_fog", "heart_reactivity"},
    "schumann": {"restlessness", "sleep_fragility", "focus_drag"},
}

_PHYSIOLOGY_EFFECT_BUCKETS = {
    "sleep_vs_14d_baseline_delta": {"fatigue_fog", "sleep_fragility"},
    "sleep_debt_proxy": {"fatigue_fog", "sleep_fragility"},
    "hrv_avg": {"fatigue_fog", "heart_reactivity"},
    "resting_hr_baseline_delta": {"heart_reactivity", "fatigue_fog"},
}

_DRIVER_HELP_BUCKETS = {
    "pressure": {"quieter_environment", "hydration_pacing"},
    "temp": {"hydration_pacing", "steadier_effort"},
    "aqi": {"cleaner_air", "hydration_pacing"},
    "allergens": {"allergy_support", "cleaner_air"},
    "kp": {"lower_stimulation", "sleep_routine"},
    "bz": {"lower_stimulation", "sleep_routine"},
    "sw": {"lower_stimulation", "steadier_effort"},
    "schumann": {"lower_stimulation", "sleep_routine"},
}

_EFFECT_HELP_BUCKETS = {
    "head_pressure": {"quieter_environment", "hydration_pacing"},
    "sinus_irritation": {"allergy_support", "cleaner_air"},
    "fatigue_fog": {"hydration_pacing", "sleep_routine"},
    "focus_drag": {"lower_stimulation", "hydration_pacing"},
    "sleep_fragility": {"sleep_routine", "lower_stimulation"},
    "restlessness": {"lower_stimulation", "sleep_routine"},
    "pain_flare": {"steadier_effort", "hydration_pacing"},
    "heart_reactivity": {"steadier_effort", "hydration_pacing"},
    "mood_sensitivity": {"lower_stimulation", "sleep_routine"},
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
    return 5


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


def _sentence(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    return cleaned if cleaned.endswith((".", "!", "?")) else f"{cleaned}."


def _delta_line(delta: int) -> Optional[str]:
    if abs(int(delta or 0)) < 5:
        return None
    direction = "up" if delta > 0 else "down"
    return f"This gauge moved {abs(delta)} points {direction} from the prior reading."


def _normalize_token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _humanize_token(value: Any) -> str:
    token = _normalize_token(value)
    if not token:
        return ""
    return token.replace("_", " ")


def _parse_iso_day(value: Any) -> Optional[date]:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except Exception:
        return None


def _feedback_time_phrase(entry_day: Optional[date], current_day: date) -> str:
    if entry_day is None:
        return "recently"
    if entry_day == current_day:
        return "earlier"
    if (current_day - entry_day).days == 1:
        return "yesterday"
    return "recently"


def _symptom_display_text(code: Any) -> str:
    normalized = str(code or "").strip().upper().replace("-", "_").replace(" ", "_")
    if not normalized:
        return ""
    return _SYMPTOM_DISPLAY_LABELS.get(normalized, normalized.lower().replace("_", " "))


def _gauge_modal_status_label(gauge_key: str, meta: Dict[str, Any]) -> str:
    zone = _normalized_zone_key(meta)
    override = (_GAUGE_MODAL_STATE_LABELS.get(gauge_key) or {}).get(zone)
    if override:
        return override
    return _normalized_zone_label(meta)


def _gauge_state_line(gauge_key: str, zone: str) -> str:
    bucket = "active" if zone in {"mild", "elevated", "high"} else "steady"
    lines = _GAUGE_STATE_LINES.get(gauge_key) or {}
    return lines.get(bucket, "This gauge looks steady right now.")


def _gauge_steady_why_line(gauge_key: str) -> str:
    fallback = {
        "pain": "No strong pain-load drivers are stacking up right now, so this gauge is staying steadier.",
        "focus": "No strong focus drags are stacking up right now, so this gauge is staying steadier.",
        "heart": "No strong recovery or reactivity signals are stacking up right now, so this gauge is staying steadier.",
        "stamina": "No strong recovery drags are stacking up right now, so this gauge is staying steadier.",
        "energy": "No strong fatigue or recovery drags are stacking up right now, so this gauge is staying steadier.",
        "sleep": "No strong sleep-disrupting signals are stacking up right now, so this gauge is staying steadier.",
        "mood": "No strong reactivity signals are stacking up right now, so this gauge is staying steadier.",
        "health_status": "No strong symptom or recovery load is stacking up right now, so this gauge is staying steadier.",
    }
    return fallback.get(gauge_key, "No strong drivers are stacking up right now, so this gauge is staying steadier.")


def _matching_symptom_rows(gauge_key: str, symptoms: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = [dict(item) for item in (symptoms or {}).get("top_symptoms") or [] if isinstance(item, dict)]
    allowed = _SYMPTOM_CODES_BY_GAUGE.get(gauge_key) or set()
    if not allowed:
        return rows
    filtered = [
        row for row in rows
        if str(row.get("symptom_code") or "").strip().upper() in allowed
    ]
    return filtered or rows


def _build_feedback_cause_candidates(
    *,
    day: date,
    gauge_key: str,
    daily_check_in: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not isinstance(daily_check_in, dict):
        return []

    entry_day = _parse_iso_day(daily_check_in.get("day"))
    when = _feedback_time_phrase(entry_day, day)
    same_day = entry_day == day if entry_day else False
    usable_energy = _normalize_token(daily_check_in.get("usable_energy"))
    energy_detail = _normalize_token(daily_check_in.get("energy_detail"))
    pain_level = _normalize_token(daily_check_in.get("pain_level"))
    pain_type = _humanize_token(daily_check_in.get("pain_type"))
    mood_level = _normalize_token(daily_check_in.get("mood_level"))
    mood_type = _humanize_token(daily_check_in.get("mood_type"))
    sleep_impact = _normalize_token(daily_check_in.get("sleep_impact"))
    system_load = _normalize_token(daily_check_in.get("system_load"))
    candidates: List[Dict[str, Any]] = []

    if gauge_key == "energy" and usable_energy in {"limited", "very_limited"}:
        label = _CHECKIN_USABLE_ENERGY_LABELS.get(usable_energy, "limited usable energy")
        if same_day:
            line = f"You reported {label} {when}, so your capacity is reduced."
        else:
            line = f"Because you reported {label} {when}, your energy baseline is still cautious today."
        if energy_detail in _CHECKIN_ENERGY_DETAIL_LABELS and usable_energy == "very_limited":
            detail = _CHECKIN_ENERGY_DETAIL_LABELS[energy_detail]
            if same_day:
                line = f"You reported {detail} with {label} {when}, so your capacity is reduced."
        candidates.append({"line": line, "priority": 100, "source": "user_feedback"})
    elif gauge_key == "energy" and usable_energy in {"plenty", "enough"} and same_day:
        label = _CHECKIN_USABLE_ENERGY_LABELS.get(usable_energy, "usable energy")
        candidates.append({"line": f"You reported {label} {when}, so this gauge is staying steadier.", "priority": 100, "source": "user_feedback"})

    if gauge_key == "pain" and pain_level in {"noticeable", "strong"}:
        descriptor = pain_type or _CHECKIN_PAIN_LABELS.get(pain_level, "pain")
        candidates.append({"line": f"You reported {descriptor} {when}, so pain load is elevated.", "priority": 100, "source": "user_feedback"})

    if gauge_key == "mood" and mood_level in {"slightly_off", "noticeable", "strong"}:
        descriptor = mood_type or _CHECKIN_MOOD_LABELS.get(mood_level, "a more reactive day")
        candidates.append({"line": f"You reported {descriptor} {when}, so mood is more sensitive right now.", "priority": 100, "source": "user_feedback"})

    if gauge_key in {"sleep", "stamina", "health_status"} and sleep_impact in {"yes_strongly", "yes_somewhat"}:
        impact_label = _CHECKIN_SLEEP_IMPACT_LABELS.get(sleep_impact, "sleep affected the day")
        candidates.append({"line": f"You said {impact_label}, so recovery is being read more cautiously.", "priority": 100, "source": "user_feedback"})

    if gauge_key == "health_status" and system_load in {"heavy", "overwhelming"}:
        candidates.append({"line": f"You reported a {system_load.replace('_', ' ')} system-load day {when}, so overall load is elevated.", "priority": 100, "source": "user_feedback"})

    return candidates


def _build_symptom_cause_candidates(
    *,
    gauge_key: str,
    symptoms: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rows = _matching_symptom_rows(gauge_key, symptoms)
    if not rows:
        return []

    if gauge_key == "health_status":
        labels = [_symptom_display_text(row.get("symptom_code")) for row in rows[:2]]
        labels = [label for label in labels if label]
        if len(labels) >= 2:
            return [{"line": f"You logged {labels[0]} and {labels[1]} today, so overall system load is elevated.", "priority": 90, "source": "recent_symptom"}]
        if labels:
            return [{"line": f"You logged {labels[0]} today, so overall system load is elevated.", "priority": 90, "source": "recent_symptom"}]
        return []

    code = str(rows[0].get("symptom_code") or "").strip().upper()
    label = _symptom_display_text(code)
    if not label:
        return []

    templates = {
        "pain": f"You logged {label} earlier, so pain load is elevated.",
        "focus": f"You logged {label} earlier, which is pulling focus down.",
        "heart": f"You logged {label} earlier, so heart load is more watchful right now.",
        "stamina": f"You logged {label} earlier, so recovery capacity is reduced.",
        "energy": f"You logged {label} earlier, so your capacity is reduced.",
        "sleep": f"You logged {label} earlier, which is still affecting recovery today.",
        "mood": f"You logged {label} earlier, so mood is more sensitive right now.",
    }
    line = templates.get(gauge_key)
    return [{"line": line, "priority": 90, "source": "recent_symptom"}] if line else []


def _build_physiology_cause_candidates(
    *,
    gauge_key: str,
    health_status_explainer: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    signals = [
        dict(item)
        for item in (health_status_explainer or {}).get("physiology_signals") or []
        if isinstance(item, dict)
    ]
    candidates: List[Dict[str, Any]] = []
    for signal in signals:
        if gauge_key not in set(signal.get("gauge_keys") or []):
            continue
        cause_line = str(signal.get("cause_line") or "").strip()
        if not cause_line:
            continue
        candidates.append(
            {
                "line": cause_line,
                "priority": int(signal.get("priority") or 70),
                "source": "physiology",
            }
        )
    return candidates


def _driver_cause_line_for_gauge(gauge_key: str, driver_key: str) -> str:
    templates = {
        "pain": {
            "pressure": "Pressure is still shifting, which can add to head pressure.",
            "temp": "Temperature swings can add to body tension or pain sensitivity.",
            "aqi": "AQI is elevated, which can add to headache or sinus irritation.",
            "allergens": "Allergen load is high, which can stack sinus irritation.",
        },
        "focus": {
            "pressure": "Pressure is still shifting, which can add to head pressure or focus drag.",
            "aqi": "AQI is elevated, which can add to brain fog or focus drag.",
            "allergens": "Allergen load is high, which can stack fog or distraction faster.",
            "kp": "Geomagnetic activity is active, which can make focus feel less steady for some people.",
            "sw": "Solar wind is elevated, which can make focus feel less steady for some people.",
            "schumann": "Schumann variability is elevated, which can make focus feel less steady for some people.",
        },
        "heart": {
            "aqi": "AQI is elevated, which can make exertion feel heavier.",
            "kp": "Geomagnetic activity is active, which can make your system feel more reactive.",
            "bz": "Bz is active, which can make your system feel less steady.",
            "sw": "Solar wind is elevated, which can make your system feel more reactive.",
        },
        "stamina": {
            "temp": "Temperature swings can make recovery feel slower.",
            "aqi": "AQI is elevated, which can stack fatigue faster.",
            "allergens": "Allergen load is high, which can stack fatigue or fog faster.",
            "sw": "Solar wind is elevated, which can make recovery feel less steady for some people.",
        },
        "energy": {
            "temp": "Temperature swings can make the day feel heavier.",
            "aqi": "AQI is elevated, which can add to fatigue or brain fog.",
            "allergens": "Allergen load is high, which can stack fatigue faster.",
            "sw": "Solar wind is elevated, which can make energy feel less steady for some people.",
            "kp": "Geomagnetic activity is active, which can make energy feel less steady for some people.",
        },
        "sleep": {
            "pressure": "Pressure is still shifting, which can make sleep feel lighter for some people.",
            "temp": "Temperature swings can make wind-down less steady.",
            "allergens": "Allergen load is high, which can make overnight irritation easier to notice.",
            "kp": "Geomagnetic activity is active, which can make wind-down feel less steady for some people.",
            "bz": "Bz is active, which can make sleep feel less settled for some people.",
            "sw": "Solar wind is elevated, which can make sleep feel less settled for some people.",
            "schumann": "Schumann variability is elevated, which can make sleep feel lighter for some people.",
        },
        "mood": {
            "pressure": "Pressure is still shifting, which can make the day feel a little less steady.",
            "kp": "Geomagnetic activity is active, which can make reactivity easier to notice for some people.",
            "sw": "Solar wind is elevated, which can make reactivity easier to notice for some people.",
            "schumann": "Schumann variability is elevated, which can make restlessness easier to notice for some people.",
        },
        "health_status": {
            "pressure": "Pressure is still shifting, which can add to overall body load.",
            "temp": "Temperature swings can make the day feel heavier.",
            "aqi": "AQI is elevated, which can add to fatigue or irritation load.",
            "allergens": "Allergen load is high, which can add to irritation or fatigue load.",
            "sw": "Solar wind is elevated, which can make the day feel less steady for some people.",
        },
    }
    return ((templates.get(gauge_key) or {}).get(driver_key) or "").strip()


def _build_driver_cause_candidates(
    *,
    gauge_key: str,
    related: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for index, driver in enumerate(_sorted_related_drivers(related)[:2]):
        driver_key = str(driver.get("key") or "").strip()
        line = _driver_cause_line_for_gauge(gauge_key, driver_key)
        if not line:
            continue
        candidates.append({"line": line, "priority": 60 - (index * 5), "source": "driver"})
    return candidates


def _build_pattern_cause_candidates(personal_summary: Optional[str]) -> List[Dict[str, Any]]:
    summary = str(personal_summary or "").strip()
    if not summary:
        return []
    return [{"line": summary, "priority": 40, "source": "pattern"}]


def _collect_effect_buckets(
    *,
    day: date,
    gauge_key: str,
    related: List[Dict[str, Any]],
    symptoms: Optional[Dict[str, Any]],
    daily_check_in: Optional[Dict[str, Any]],
    health_status_explainer: Optional[Dict[str, Any]],
) -> List[str]:
    allowed = _GAUGE_ALLOWED_EFFECT_BUCKETS.get(gauge_key) or set()
    scores: Dict[str, float] = defaultdict(float)

    def add(bucket: str, value: float) -> None:
        if bucket in allowed:
            scores[bucket] += value + _EFFECT_BUCKET_PRIORITY.get(bucket, 0)

    for idx, row in enumerate(_matching_symptom_rows(gauge_key, symptoms)[:3]):
        code = str(row.get("symptom_code") or "").strip().upper()
        for bucket in _SYMPTOM_EFFECT_BUCKETS.get(code, set()):
            add(bucket, 12 - (idx * 2))

    for idx, driver in enumerate(_sorted_related_drivers(related)[:2]):
        key = str(driver.get("key") or "").strip()
        for bucket in _DRIVER_EFFECT_BUCKETS.get(key, set()):
            add(bucket, 8 - (idx * 1.5))

    for signal in (health_status_explainer or {}).get("physiology_signals") or []:
        if not isinstance(signal, dict):
            continue
        if gauge_key not in set(signal.get("gauge_keys") or []):
            continue
        for bucket in _PHYSIOLOGY_EFFECT_BUCKETS.get(str(signal.get("key") or ""), set()):
            add(bucket, 7.5)

    if isinstance(daily_check_in, dict):
        usable_energy = _normalize_token(daily_check_in.get("usable_energy"))
        energy_detail = _normalize_token(daily_check_in.get("energy_detail"))
        pain_type = _normalize_token(daily_check_in.get("pain_type"))
        mood_type = _normalize_token(daily_check_in.get("mood_type"))
        sleep_impact = _normalize_token(daily_check_in.get("sleep_impact"))
        if gauge_key == "energy" and usable_energy in {"limited", "very_limited"}:
            add("fatigue_fog", 11 if usable_energy == "very_limited" else 9)
            if energy_detail == "brain_fog":
                add("focus_drag", 8)
        if gauge_key == "pain" and pain_type in {"sinus_pressure", "head_pressure", "migraine", "headache"}:
            add("head_pressure", 9)
        if gauge_key == "pain" and pain_type in {"joint_pain", "nerve_pain", "muscle_pain", "cycle_related_pain"}:
            add("pain_flare", 8)
        if gauge_key == "mood" and mood_type in {"anxious", "wired", "emotionally_sensitive"}:
            add("mood_sensitivity", 9)
            add("restlessness", 7)
        if gauge_key in {"sleep", "energy", "stamina", "health_status"} and sleep_impact in {"yes_strongly", "yes_somewhat"}:
            add("sleep_fragility", 8)
            add("fatigue_fog", 6)

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [bucket for bucket, _ in ranked[:3]]


def _render_effect_line(
    bucket: str,
    *,
    related: List[Dict[str, Any]],
    symptoms: Optional[Dict[str, Any]],
    daily_check_in: Optional[Dict[str, Any]],
    health_status_explainer: Optional[Dict[str, Any]],
) -> str:
    driver_keys = {str(driver.get("key") or "").strip() for driver in related if str(driver.get("key") or "").strip()}
    symptom_codes = {
        str(row.get("symptom_code") or "").strip().upper()
        for row in (symptoms or {}).get("top_symptoms") or []
        if isinstance(row, dict)
    }
    sleep_signal_keys = {
        str(item.get("key") or "")
        for item in (health_status_explainer or {}).get("physiology_signals") or []
        if isinstance(item, dict)
    }
    usable_energy = _normalize_token((daily_check_in or {}).get("usable_energy"))

    if bucket == "head_pressure":
        if {"pressure", "allergens"} <= driver_keys or {"pressure", "aqi"} <= driver_keys:
            return "Pressure shifts and irritation load can make head pressure or headaches easier to notice."
        if "pressure" in driver_keys:
            return "Head pressure or headaches may be easier to notice while pressure is shifting."
        if "MIGRAINE" in symptom_codes or "HEADACHE" in symptom_codes:
            return "Head pressure or headaches may stay closer to the surface."
        return "Head pressure or headaches may be easier to notice."

    if bucket == "sinus_irritation":
        if {"aqi", "allergens"} <= driver_keys:
            return "When pollen and air quality both stack up, sinus irritation can show up faster."
        if "allergens" in driver_keys:
            return "Allergen-heavy conditions can make sinus pressure or irritation easier to notice."
        return "Sinus irritation may be easier to notice."

    if bucket == "fatigue_fog":
        if {"aqi", "allergens"} <= driver_keys:
            return "When pollen and air quality both stack up, fatigue or brain fog may show up faster."
        if usable_energy in {"limited", "very_limited"}:
            return "Fatigue or brain fog may show up faster today."
        if {"sleep_vs_14d_baseline_delta", "sleep_debt_proxy"} & sleep_signal_keys:
            return "Fatigue or brain fog may show up faster while recovery is still catching up."
        return "Fatigue or brain fog may show up faster today."

    if bucket == "focus_drag":
        return "Focus may drift faster, and concentration may take more effort."

    if bucket == "sleep_fragility":
        return "Sleep may feel lighter or less settled."

    if bucket == "restlessness":
        return "Restlessness or a wired edge may feel closer to the surface."

    if bucket == "pain_flare":
        return "Body tension, stiffness, or a pain flare may be easier to notice."

    if bucket == "heart_reactivity":
        return "Exertion or a more reactive, fluttery feel may be easier to notice."

    if bucket == "mood_sensitivity":
        return "Reactivity or a more sensitive mood may sit closer to the surface."

    return "A few symptoms may stand out more easily right now."


def _collect_help_buckets(
    *,
    gauge_key: str,
    effect_buckets: List[str],
    related: List[Dict[str, Any]],
    daily_check_in: Optional[Dict[str, Any]],
) -> List[str]:
    scores: Dict[str, float] = defaultdict(float)

    for bucket in effect_buckets:
        for help_bucket in _EFFECT_HELP_BUCKETS.get(bucket, set()):
            scores[help_bucket] += 4.0

    for idx, driver in enumerate(_sorted_related_drivers(related)[:2]):
        key = str(driver.get("key") or "").strip()
        for help_bucket in _DRIVER_HELP_BUCKETS.get(key, set()):
            scores[help_bucket] += 3.0 - (idx * 0.4)

    if gauge_key == "energy" and _normalize_token((daily_check_in or {}).get("usable_energy")) in {"limited", "very_limited"}:
        scores["hydration_pacing"] += 2.5
        scores["sleep_routine"] += 1.4

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [bucket for bucket, _ in ranked[:3]]


def _render_help_line(bucket: str, *, related: List[Dict[str, Any]]) -> str:
    driver_keys = {str(driver.get("key") or "").strip() for driver in related if str(driver.get("key") or "").strip()}

    if bucket == "allergy_support":
        if {"aqi", "allergens"} & driver_keys:
            return "Favor your usual allergy supports and try to avoid your worst trigger windows if you can."
        return "Use the supports that usually help before irritation fully stacks up."

    if bucket == "cleaner_air":
        return "Cleaner indoor air and shorter exposure windows may help if irritation is stacking up."

    if bucket == "hydration_pacing":
        return "Keep hydration, meals, and effort a little steadier today."

    if bucket == "quieter_environment":
        return "A quieter, lower-friction environment may help if pressure is building."

    if bucket == "lower_stimulation":
        return "Lower stimulation and shorter work blocks may help if your system feels reactive."

    if bucket == "sleep_routine":
        return "Protect your wind-down and keep tonight as predictable as you can."

    if bucket == "steadier_effort":
        return "Favor steadier effort over spikes if your system feels easy to overload."

    return "Use the supports that usually help you and keep the day a little steadier."


def _priority_quick_log_options(effect_buckets: List[str]) -> List[Dict[str, str]]:
    options: List[Dict[str, str]] = []
    for bucket in effect_buckets:
        options.extend(_EFFECT_BUCKET_QUICK_LOG.get(bucket, []))
    return options


def _gauge_explanation_entry(
    *,
    day: date,
    gauge_key: str,
    label: str,
    meta: Dict[str, Any],
    delta: int,
    related: List[Dict[str, Any]],
    profile: PersonalizationProfile,
    symptoms: Optional[Dict[str, Any]],
    daily_check_in: Optional[Dict[str, Any]],
    health_status_explainer: Optional[Dict[str, Any]],
    personal_summary: Optional[str],
) -> Dict[str, Any]:
    zone = _normalized_zone_key(meta)
    status = _gauge_modal_status_label(gauge_key, meta)

    cause_candidates = (
        _build_feedback_cause_candidates(day=day, gauge_key=gauge_key, daily_check_in=daily_check_in)
        + _build_symptom_cause_candidates(gauge_key=gauge_key, symptoms=symptoms)
        + _build_physiology_cause_candidates(gauge_key=gauge_key, health_status_explainer=health_status_explainer)
        + _build_driver_cause_candidates(gauge_key=gauge_key, related=related)
        + _build_pattern_cause_candidates(personal_summary)
    )
    cause_candidates.sort(key=lambda item: (-int(item.get("priority") or 0), str(item.get("line") or "")))

    seen_lines: set[str] = set()
    ordered_lines: List[Dict[str, Any]] = []
    for candidate in cause_candidates:
        line = _sentence(str(candidate.get("line") or "").strip())
        if not line or line in seen_lines:
            continue
        seen_lines.add(line)
        ordered_lines.append({**candidate, "line": line})

    causal_callout: Optional[str] = None
    if ordered_lines and ordered_lines[0].get("source") in {"user_feedback", "recent_symptom"}:
        causal_callout = ordered_lines[0]["line"]

    why_lines = [item["line"] for item in ordered_lines if item["line"] != causal_callout][:3]
    if not why_lines:
        delta_line = _delta_line(delta)
        if delta_line:
            why_lines.append(delta_line)
        if not why_lines:
            why_lines.append(_gauge_steady_why_line(gauge_key))

    effect_buckets = _collect_effect_buckets(
        day=day,
        gauge_key=gauge_key,
        related=related,
        symptoms=symptoms,
        daily_check_in=daily_check_in,
        health_status_explainer=health_status_explainer,
    )
    effect_lines = _unique_lines(
        [
            _render_effect_line(
                bucket,
                related=related,
                symptoms=symptoms,
                daily_check_in=daily_check_in,
                health_status_explainer=health_status_explainer,
            )
            for bucket in effect_buckets
        ]
    )[:3]
    if not effect_lines:
        effect_lines = ["No strong symptom layer is standing out right now."]

    help_buckets = _collect_help_buckets(
        gauge_key=gauge_key,
        effect_buckets=effect_buckets,
        related=related,
        daily_check_in=daily_check_in,
    )
    help_lines = _unique_lines([_render_help_line(bucket, related=related) for bucket in help_buckets])[:3]
    if not help_lines:
        help_lines = ["Keep pacing and recovery basics steady."]

    personalized_options: List[Dict[str, str]] = []
    personalized_prefill: List[str] = []
    for driver in related:
        content = _driver_personalized_content(str(driver.get("key") or "").strip(), profile)
        personalized_options.extend(content.get("quick_log") or [])
        personalized_prefill.extend([item.get("code") for item in content.get("quick_log") or [] if item.get("code")])

    effect_priority_options = _priority_quick_log_options(effect_buckets)
    effect_priority_prefill = [item.get("code") for item in effect_priority_options if item.get("code")]
    quick_log = _quick_log(
        context_type="gauge",
        context_key=gauge_key,
        zone=zone,
        default_options=_GAUGE_QUICK_LOG.get(gauge_key, []),
        default_prefill=_GAUGE_PREFILL.get(gauge_key, ["OTHER"]),
        priority_options=_merge_quick_log_options(effect_priority_options, personalized_options),
        priority_prefill=_merge_prefill_codes(effect_priority_prefill, personalized_prefill),
        delta=delta if abs(delta) >= 1 else None,
    )

    return {
        "modal_type": "full",
        "title": f"{label} \u2014 {status}",
        "state_line": _gauge_state_line(gauge_key, zone),
        "causal_callout": causal_callout,
        "why": why_lines,
        "what_you_may_notice": effect_lines,
        "suggested_actions": help_lines,
        "quick_log": quick_log,
        "cta": {
            "label": "Log symptoms",
            "action": "open_symptom_log",
            "prefill": quick_log.get("prefill_codes") or _GAUGE_PREFILL.get(gauge_key, ["OTHER"]),
        },
    }


def _personal_relevance_gauge_summary(personal_relevance: Optional[Dict[str, Any]], gauge_key: str) -> Optional[str]:
    if not isinstance(personal_relevance, dict):
        return None
    for item in personal_relevance.get("pattern_relevant_gauges") or []:
        if str((item or {}).get("gauge_key") or "").strip() != gauge_key:
            continue
        summary = str((item or {}).get("summary") or "").strip()
        if summary:
            return summary
    return None


def _driver_role_rank(driver: Dict[str, Any]) -> int:
    role = str(driver.get("role") or "").strip().lower()
    if role == "primary":
        return 0
    if role == "supporting":
        return 1
    if role == "background":
        return 2
    return 3


def _sorted_related_drivers(related: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = [dict(item) for item in related if isinstance(item, dict)]
    rows.sort(
        key=lambda item: (
            _driver_role_rank(item),
            -float(item.get("personal_relevance_score") or 0.0),
            -float(item.get("raw_severity_score") or 0.0),
            -_driver_rank(item),
        )
    )
    return rows


def _driver_role_context(driver: Dict[str, Any]) -> str:
    role = str(driver.get("role") or "").strip().lower()
    if role == "primary":
        return "This is the clearest active signal for you right now."
    if role == "supporting":
        return "This is active too, but it stays secondary to the lead signal."
    if role == "background":
        return "This is still present, but it stays in the background right now."
    return ""


def _gauge_support_line(gauge_key: str, driver: Dict[str, Any]) -> str:
    label = str(driver.get("label") or driver.get("key") or "This driver").strip()
    role = str(driver.get("role_label") or "").strip().lower()
    terms = _GAUGE_SUPPORT_TERMS.get(gauge_key, "this gauge")
    if role:
        return f"{label} is {role} and can add pressure around {terms}."
    return f"{label} is also in the mix and can add pressure around {terms}."


def _summary_theme_sentence(theme: Optional[Dict[str, Any]]) -> Optional[str]:
    if not isinstance(theme, dict):
        return None
    key = str(theme.get("key") or "").strip()
    return _THEME_SUMMARY_LINES.get(key)


def _summary_action_sentence(day: date, driver: Optional[Dict[str, Any]], profile: PersonalizationProfile) -> Optional[str]:
    if not isinstance(driver, dict):
        return None
    key = str(driver.get("key") or "").strip()
    if not key:
        return None
    actions = _driver_action_lines(day, key, profile)
    if not actions:
        return None
    return _sentence(actions[0])


def _driver_variant(profile: PersonalizationProfile, key: str) -> Optional[str]:
    if key == "pressure":
        if profile.includes_any(HEAD_PRESSURE_KEYS):
            return "head_pressure"
        if profile.includes_any(PAIN_FLARE_KEYS):
            return "pain_flare"
        return None
    if key == "temp":
        return "pain_flare" if profile.includes_any(PAIN_FLARE_KEYS) else None
    if key == "aqi":
        if profile.has_any("asthma_breathing_sensitive"):
            return "airway"
        if profile.includes_any(SINUS_KEYS):
            return "sinus"
        return None
    if key == "allergens":
        if profile.has_any("asthma_breathing_sensitive"):
            return "airway"
        if profile.includes_any(SINUS_KEYS) or profile.has_any("migraine_history"):
            return "sinus"
        return None
    if key in {"kp", "sw", "bz"}:
        if profile.includes_any(AUTONOMIC_KEYS):
            return "autonomic"
        if profile.includes_any(SLEEP_DISRUPTION_KEYS):
            return "sleep"
        return None
    if key == "schumann":
        return "sleep" if profile.includes_any(SLEEP_DISRUPTION_KEYS) else None
    return None


def _driver_personalized_content(
    key: str,
    profile: PersonalizationProfile,
) -> Dict[str, Any]:
    variant = _driver_variant(profile, key)
    if not variant:
        return {}
    return dict(_PERSONALIZED_DRIVER_CONTENT.get((key, variant)) or {})


def _merge_quick_log_options(*groups: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    seen: set[str] = set()
    out: List[Dict[str, str]] = []
    for group in groups:
        for item in group or []:
            code = str(item.get("code") or "").strip().upper()
            label = str(item.get("label") or "").strip()
            if not code or not label or code in seen:
                continue
            seen.add(code)
            out.append({"code": code, "label": label})
    return out


def _merge_prefill_codes(*groups: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for group in groups:
        for raw in group or []:
            code = str(raw or "").strip().upper()
            if not code or code in seen:
                continue
            seen.add(code)
            out.append(code)
    return out


def _quick_log(
    *,
    context_type: str,
    context_key: str,
    zone: str,
    default_options: List[Dict[str, str]],
    default_prefill: List[str],
    priority_options: Optional[List[Dict[str, str]]] = None,
    priority_prefill: Optional[List[str]] = None,
    delta: Optional[int | float] = None,
) -> Dict[str, Any]:
    options = _merge_quick_log_options(priority_options or [], default_options)
    if not options:
        options = [
            {
                "code": str(code or "").strip(),
                "label": str(code or "").strip().replace("_", " ").title(),
            }
            for code in _merge_prefill_codes(priority_prefill or [], default_prefill)
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
        "prefill_codes": _merge_prefill_codes(priority_prefill or [], default_prefill),
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
    return f"{label} is {state.lower()} at {value_text}{suffix} right now."


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


def _gauge_modal_type(
    zone: str,
    delta: int,
    related: List[Dict[str, Any]],
    *,
    personal_summary: Optional[str] = None,
) -> str:
    if personal_summary:
        return "full"
    if any((driver.get("active_pattern_refs") or []) for driver in related):
        return "full"
    if zone in {"mild", "elevated", "high"}:
        return "full"
    if abs(int(delta or 0)) >= 5:
        return "full"
    if any(_driver_is_watch_or_high(driver) for driver in related):
        return "full"
    return "short"


def _driver_modal_type(driver: Dict[str, Any]) -> str:
    if (driver.get("active_pattern_refs") or []) or str(driver.get("role") or "").strip() in {"primary", "supporting"}:
        return "full"
    zone = _driver_zone_key(driver)
    return "full" if zone in {"mild", "elevated", "high"} else "short"


def _earthscope_refresh_bucket(now: Optional[datetime] = None) -> str:
    current = now or datetime.now(timezone.utc)
    minute_bucket = (current.minute // 15) * 15
    snapped = current.replace(minute=minute_bucket, second=0, microsecond=0)
    return snapped.isoformat()


def _earthscope_template_pick(
    options: List[str],
    *,
    user_id: str,
    bucket_key: str,
    driver_family: str,
    slot: str,
) -> str:
    values = [item for item in options if item]
    if not values:
        return ""
    seed = f"{user_id}|{bucket_key}|{driver_family}|{slot}".encode("utf-8")
    digest = hashlib.sha256(seed).hexdigest()
    index = int(digest[:8], 16) % len(values)
    return values[index]


def _earthscope_driver_family_key(driver: Dict[str, Any]) -> str:
    key = str(driver.get("key") or "").strip().lower()
    if key == "pressure":
        return "pressure"
    if key == "temp":
        return "temperature"
    if key == "aqi":
        return "air_quality"
    if key == "sw":
        return "solar_wind"
    if key in {"kp", "bz"}:
        return "geomagnetic"
    if key == "schumann":
        return "schumann"
    if key == "moon":
        return "moon"
    return "mixed"


def _earthscope_driver_state_fragment(driver: Dict[str, Any]) -> str:
    family = _earthscope_driver_family_key(driver)
    state = str(driver.get("state") or "").strip().lower()
    if not state:
        return "active"
    if family == "air_quality":
        return state
    return f"running {state}"


def _earthscope_lead_state_text(driver: Dict[str, Any]) -> str:
    state = str(driver.get("state") or "").strip().lower()
    if not state:
        return "still active"
    if _earthscope_driver_family_key(driver) == "air_quality":
        return f"at {state} levels"
    return f"still {state}"


def _earthscope_gauge_sentence(
    top_gauges: List[Dict[str, Any]],
    gauge_labels: Dict[str, str],
) -> str:
    if not top_gauges:
        return "Most gauges are still sitting in lower zones, though lighter energy or focus shifts can still show up for some people."

    labels: List[str] = []
    for gauge in top_gauges[:2]:
        key = gauge["key"]
        label = gauge_labels.get(key) or _GAUGE_FALLBACK_LABELS.get(key) or key
        labels.append(label)
    if len(labels) == 1:
        return f"{labels[0]} looks most changeable right now, so that area may feel less steady for some people."
    return f"{labels[0]} and {labels[1]} look most changeable right now, so those areas may feel less steady for some people."


def _join_labels(labels: List[str]) -> str:
    cleaned = [str(item).strip() for item in labels if str(item).strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"


_EARTHSCOPE_GAUGE_PHRASES = {
    "pain": ["pain flare", "joint pain", "stiffness"],
    "focus": ["brain fog", "focus drift", "headache"],
    "heart": ["palpitations", "restlessness", "low energy"],
    "stamina": ["fatigue", "low energy", "body aches"],
    "energy": ["low energy", "fatigue", "wired feeling"],
    "sleep": ["disruptive sleep", "restless sleep", "wired feeling"],
    "mood": ["anxious edge", "low energy", "wired feeling"],
    "health_status": ["low energy", "fatigue", "pain flare"],
}

_EARTHSCOPE_PHRASE_OVERRIDES = {
    "anxious": "anxious edge",
    "drained": "low energy",
    "insomnia": "disruptive sleep",
    "jittery": "jittery feeling",
    "restless": "restlessness",
    "sleep sensitivity": "disruptive sleep",
    "unrefreshed": "unrefreshing sleep",
    "wired": "wired feeling",
}

_EARTHSCOPE_SKIP_PHRASES = frozenset({"other"})
_EARTHSCOPE_DRIVER_WEIGHTS = {
    "high": 3.4,
    "watch": 2.8,
    "elevated": 2.8,
    "moderate": 2.6,
    "active": 2.1,
    "mild": 1.5,
    "low": 1.0,
}
_EARTHSCOPE_HEAD_PHRASES = frozenset({"headache", "sinus pressure", "light sensitivity"})
_EARTHSCOPE_PAIN_PHRASES = frozenset({"pain flare", "joint pain", "stiffness", "nerve pain", "body aches", "fatigue"})
_EARTHSCOPE_SINUS_PHRASES = frozenset({"sinus pressure", "brain fog", "headache"})
_EARTHSCOPE_AIRWAY_PHRASES = frozenset({"breathing irritation", "chest tightness", "fatigue"})
_EARTHSCOPE_AUTONOMIC_PHRASES = frozenset({"palpitations", "wired feeling", "low energy", "restlessness"})
_EARTHSCOPE_SLEEP_PHRASES = frozenset({"restless sleep", "disruptive sleep", "wired feeling", "unrefreshing sleep"})


def _earthscope_phrase(raw: Any) -> Optional[str]:
    label = str(raw or "").strip().lower()
    if not label:
        return None
    normalized = _EARTHSCOPE_PHRASE_OVERRIDES.get(label, label)
    return None if normalized in _EARTHSCOPE_SKIP_PHRASES else normalized


def _earthscope_add_phrase(
    scores: Dict[str, float],
    phrase_labels: Dict[str, str],
    raw_label: Any,
    score: float,
) -> None:
    phrase = _earthscope_phrase(raw_label)
    if not phrase or score <= 0:
        return
    scores[phrase] = scores.get(phrase, 0.0) + score
    phrase_labels.setdefault(phrase, phrase)


def earthscope_ranked_symptoms(
    *,
    gauge_keys: Iterable[str],
    drivers: Iterable[Dict[str, Any]],
    user_tags: Optional[Iterable[Any]] = None,
    limit: int = 3,
) -> List[Dict[str, Any]]:
    profile = build_personalization_profile(user_tags)
    scores: Dict[str, float] = {}
    labels: Dict[str, str] = {}

    seen_gauges: set[str] = set()
    ordered_gauges: List[str] = []
    for raw_key in gauge_keys:
        key = str(raw_key or "").strip()
        if not key or key in seen_gauges:
            continue
        seen_gauges.add(key)
        ordered_gauges.append(key)

    for gauge_idx, gauge_key in enumerate(ordered_gauges[:3]):
        base = max(2.8 - (gauge_idx * 0.45), 1.4)
        for phrase_idx, phrase in enumerate(_EARTHSCOPE_GAUGE_PHRASES.get(gauge_key, [])):
            _earthscope_add_phrase(scores, labels, phrase, base - (phrase_idx * 0.35))
        for option_idx, option in enumerate((_GAUGE_QUICK_LOG.get(gauge_key) or [])[:3]):
            _earthscope_add_phrase(scores, labels, option.get("label"), base - (option_idx * 0.25))

    seen_drivers: set[str] = set()
    ordered_drivers: List[Dict[str, Any]] = []
    for raw_driver in drivers or []:
        key = str((raw_driver or {}).get("key") or "").strip()
        if not key or key in seen_drivers:
            continue
        seen_drivers.add(key)
        ordered_drivers.append(dict(raw_driver))

    for driver_idx, driver in enumerate(ordered_drivers[:4]):
        key = str(driver.get("key") or "").strip()
        if not key:
            continue
        severity = str(driver.get("severity") or driver.get("state") or "").strip().lower()
        base = max(_EARTHSCOPE_DRIVER_WEIGHTS.get(severity, 1.4) - (driver_idx * 0.25), 1.0)
        personalized = _driver_personalized_content(key, profile).get("quick_log") or []
        options = _merge_quick_log_options(personalized, _DRIVER_QUICK_LOG.get(key) or [])
        for option_idx, option in enumerate(options[:3]):
            _earthscope_add_phrase(scores, labels, option.get("label"), base - (option_idx * 0.35))

    if profile.includes_any(HEAD_PRESSURE_KEYS):
        for phrase in _EARTHSCOPE_HEAD_PHRASES:
            _earthscope_add_phrase(scores, labels, phrase, 0.85)
    if profile.includes_any(PAIN_FLARE_KEYS):
        for phrase in _EARTHSCOPE_PAIN_PHRASES:
            _earthscope_add_phrase(scores, labels, phrase, 0.75)
    if profile.includes_any(SINUS_KEYS):
        for phrase in _EARTHSCOPE_SINUS_PHRASES:
            _earthscope_add_phrase(scores, labels, phrase, 0.7)
    if profile.includes_any(AIRWAY_KEYS):
        for phrase in _EARTHSCOPE_AIRWAY_PHRASES:
            _earthscope_add_phrase(scores, labels, phrase, 0.7)
    if profile.includes_any(AUTONOMIC_KEYS):
        for phrase in _EARTHSCOPE_AUTONOMIC_PHRASES:
            _earthscope_add_phrase(scores, labels, phrase, 0.75)
    if profile.includes_any(SLEEP_DISRUPTION_KEYS):
        for phrase in _EARTHSCOPE_SLEEP_PHRASES:
            _earthscope_add_phrase(scores, labels, phrase, 0.75)

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [
        {"phrase": labels.get(phrase, phrase), "score": round(score, 2)}
        for phrase, score in ranked[:max(limit, 0)]
    ]


def earthscope_condition_note(
    *,
    ranked_symptoms: Iterable[Dict[str, Any]],
    user_tags: Optional[Iterable[Any]] = None,
) -> Optional[str]:
    profile = build_personalization_profile(user_tags)
    phrases = {str(item.get("phrase") or "").strip().lower() for item in ranked_symptoms if str(item.get("phrase") or "").strip()}
    if not phrases:
        return None

    if profile.has_any("migraine_history") and phrases & _EARTHSCOPE_HEAD_PHRASES:
        return "Because you've marked migraine history, head pressure or light sensitivity may be easier to notice than usual."
    if profile.has_any("fibromyalgia") and phrases & (_EARTHSCOPE_PAIN_PHRASES | {"low energy"}):
        return "Because you've marked fibromyalgia, pain, stiffness, or fatigue may feel closer to the surface than usual."
    if profile.includes_any(PAIN_FLARE_KEYS) and phrases & _EARTHSCOPE_PAIN_PHRASES:
        return "Because you've marked pain or joint sensitivity, pain or stiffness may be easier to notice than usual."
    if profile.includes_any(AUTONOMIC_KEYS) and phrases & _EARTHSCOPE_AUTONOMIC_PHRASES:
        return "Because you've marked autonomic sensitivity, palpitations, wired energy, or a drained feeling may stand out faster."
    if profile.has_any("allergies_sinus") and phrases & _EARTHSCOPE_SINUS_PHRASES:
        return "Because you've marked allergies or sinus sensitivity, sinus pressure or foggier focus may stand out faster."
    if profile.includes_any(AIRWAY_KEYS) and phrases & _EARTHSCOPE_AIRWAY_PHRASES:
        return "Because you've marked breathing sensitivity, irritation or chest tightness may show up faster than usual."
    if profile.includes_any(SLEEP_DISRUPTION_KEYS) and phrases & _EARTHSCOPE_SLEEP_PHRASES:
        return "Because you've marked sleep sensitivity, lighter or more disruptive sleep may be easier to notice tonight."
    return None


def _gauge_why_lines(
    *,
    day: date,
    gauge_key: str,
    related: List[Dict[str, Any]],
    delta: int,
    personal_summary: Optional[str] = None,
) -> List[str]:
    ordered = _sorted_related_drivers(related)
    primary = ordered[0] if ordered else None
    supporting = ordered[1] if len(ordered) > 1 else None

    lines: List[str] = []
    if personal_summary:
        lines.append(personal_summary)
    elif primary:
        lines.append(str(primary.get("personal_reason") or "").strip())
    if primary:
        lines.append(_driver_why_line(primary))
    if supporting:
        lines.append(_gauge_support_line(gauge_key, supporting))
    delta_line = _delta_line(delta)
    if delta_line and len(lines) < 3:
        lines.append(delta_line)
    if not lines:
        lines = _rotate_pick(
            [
                "This gauge combines your current environmental context and personal baseline.",
                "Recent local and space drivers can nudge this gauge up or down.",
                "This score reflects context, not certainty, and can change quickly.",
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
    profile: PersonalizationProfile,
) -> List[str]:
    lines: List[str] = []
    for driver in _sorted_related_drivers(related)[:2]:
        driver_key = str(driver.get("key") or "").strip()
        personalized = _driver_personalized_content(driver_key, profile).get("notices") or []
        lines.extend(_rotate_pick(personalized, day, f"{gauge_key}:{driver_key}", "driver-personalized-notice", 1))
        lines.extend(_rotate_pick(_DRIVER_NOTICE.get(driver_key, []), day, f"{gauge_key}:{driver_key}", "driver-notice", 1))
    lines.extend(_rotate_pick(_GAUGE_NOTICES.get(gauge_key, []), day, gauge_key, "notice", 2))
    return _unique_lines(lines)[:3]


def _gauge_action_lines(
    *,
    day: date,
    gauge_key: str,
    related: List[Dict[str, Any]],
    profile: PersonalizationProfile,
) -> List[str]:
    lines: List[str] = []
    for driver in _sorted_related_drivers(related)[:2]:
        driver_key = str(driver.get("key") or "").strip()
        personalized = _driver_personalized_content(driver_key, profile).get("actions") or []
        lines.extend(_rotate_pick(personalized, day, f"{gauge_key}:{driver_key}", "driver-personalized-actions", 1))
        lines.extend(_rotate_pick(_DRIVER_ACTIONS.get(driver_key, []), day, f"{gauge_key}:{driver_key}", "driver-actions", 1))
    lines.extend(_rotate_pick(_GAUGE_ACTIONS.get(gauge_key, []), day, gauge_key, "actions", 3))
    lines = _unique_lines(lines)
    return lines[:3] if lines else ["Hydrate, pace tasks, and protect your sleep window."]


def _driver_notice_lines(day: date, key: str, profile: PersonalizationProfile) -> List[str]:
    personalized = _driver_personalized_content(key, profile).get("notices") or []
    notices = _rotate_pick(personalized, day, key, "driver-personalized-notice", 3)
    notices.extend(_rotate_pick(_DRIVER_NOTICE.get(key, []), day, key, "driver-notice", 3))
    notices = _unique_lines(notices)
    return notices[:3] if notices else ["Some people may notice mild sensitivity shifts with this driver."]


def _driver_action_lines(day: date, key: str, profile: PersonalizationProfile) -> List[str]:
    personalized = _driver_personalized_content(key, profile).get("actions") or []
    actions = _rotate_pick(personalized, day, key, "driver-personalized-actions", 3)
    actions.extend(_rotate_pick(_DRIVER_ACTIONS.get(key, []), day, key, "driver-actions", 3))
    actions = _unique_lines(actions)
    return actions[:3] if actions else ["Use steady pacing and track symptoms to see personal patterns."]


def build_modal_models(
    *,
    day: date,
    gauges: Optional[Dict[str, Any]],
    gauges_meta: Optional[Dict[str, Dict[str, Any]]],
    gauge_labels: Optional[Dict[str, str]],
    drivers: Optional[Iterable[Dict[str, Any]]] = None,
    gauges_delta: Optional[Dict[str, int]] = None,
    user_tags: Optional[Iterable[Any]] = None,
    personal_relevance: Optional[Dict[str, Any]] = None,
    symptoms: Optional[Dict[str, Any]] = None,
    daily_check_in: Optional[Dict[str, Any]] = None,
    health_status_explainer: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    gauges = gauges or {}
    gauges_meta = gauges_meta or {}
    gauge_labels = gauge_labels or {}
    gauges_delta = gauges_delta or {}
    profile = build_personalization_profile(user_tags)
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
        delta = int(gauges_delta.get(gauge_key) or 0)
        related_keys = _GAUGE_DRIVER_MAP.get(gauge_key) or []
        related = _sorted_related_drivers([drivers_by_key[k] for k in related_keys if k in drivers_by_key])
        personal_summary = _personal_relevance_gauge_summary(personal_relevance, gauge_key)
        gauge_models[gauge_key] = _gauge_explanation_entry(
            day=day,
            gauge_key=gauge_key,
            label=label,
            meta=meta,
            delta=delta,
            related=related,
            profile=profile,
            symptoms=symptoms,
            daily_check_in=daily_check_in,
            health_status_explainer=health_status_explainer,
            personal_summary=personal_summary,
        )

    driver_models: Dict[str, Dict[str, Any]] = {}
    for driver in driver_rows:
        key = str(driver.get("key") or "").strip()
        if not key:
            continue
        label = str(driver.get("label") or key.replace("_", " ").title())
        state = str(driver.get("state") or "Elevated")
        zone = _driver_zone_key(driver)
        personalized = _driver_personalized_content(key, profile)
        personalized_options = personalized.get("quick_log") or []
        personalized_prefill = [item.get("code") for item in personalized_options if item.get("code")]
        quick_log = _quick_log(
            context_type="driver",
            context_key=key,
            zone=zone,
            default_options=_DRIVER_QUICK_LOG.get(key, []),
            default_prefill=_DRIVER_PREFILL.get(key, ["OTHER"]),
            priority_options=personalized_options,
            priority_prefill=personalized_prefill,
            delta=driver.get("value") if key in {"pressure", "temp"} else None,
        )
        cta_prefill = quick_log.get("prefill_codes") or _DRIVER_PREFILL.get(key, ["OTHER"])
        why_lines = [
            str(driver.get("personal_reason") or "").strip(),
            _driver_role_context(driver),
            _driver_why_line(driver),
            _DRIVER_CONTEXT.get(key, "This signal can be useful context when your system feels more reactive than usual."),
        ]
        why_lines = _unique_lines([line for line in why_lines if line])
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
                    "prefill": cta_prefill,
                },
            }
            continue

        driver_models[key] = {
            "modal_type": "full",
            "title": f"{label} \u2014 {state}",
            "why": why_lines[:3],
            "what_you_may_notice": _driver_notice_lines(day, key, profile),
            "suggested_actions": _driver_action_lines(day, key, profile),
            "quick_log": quick_log,
            "cta": {
                "label": "Log symptoms",
                "action": "open_symptom_log",
                "prefill": cta_prefill,
            },
        }

    return {
        "gauges": gauge_models,
        "drivers": driver_models,
    }


def build_earthscope_summary(
    *,
    user_id: str = "",
    day: date,
    gauges: Optional[Dict[str, Any]],
    gauges_meta: Optional[Dict[str, Dict[str, Any]]],
    gauge_labels: Optional[Dict[str, str]],
    drivers: Optional[Iterable[Dict[str, Any]]],
    user_tags: Optional[Iterable[Any]] = None,
    personal_relevance: Optional[Dict[str, Any]] = None,
) -> str:
    gauges = gauges or {}
    gauges_meta = gauges_meta or {}
    gauge_labels = gauge_labels or {}
    profile = build_personalization_profile(user_tags)
    driver_rows = [d for d in list(drivers or []) if isinstance(d, dict)]
    driver_rows.sort(key=lambda item: _driver_rank(item), reverse=True)
    top_drivers = driver_rows[:2]
    top_gauges = _elevated_gauges(gauges, gauges_meta)[:2]
    bucket_key = _earthscope_refresh_bucket()
    relevance_explanations = (
        personal_relevance.get("today_relevance_explanations")
        if isinstance(personal_relevance, dict)
        else {}
    ) or {}
    daily_brief = str(relevance_explanations.get("daily_brief") or "").strip()
    personal_primary = (
        dict(personal_relevance.get("primary_driver"))
        if isinstance(personal_relevance, dict) and isinstance(personal_relevance.get("primary_driver"), dict)
        else None
    )
    personal_supporting = [
        dict(item)
        for item in (
            personal_relevance.get("supporting_drivers") or []
            if isinstance(personal_relevance, dict)
            else []
        )
        if isinstance(item, dict)
    ]
    personal_themes = [
        dict(item)
        for item in (
            personal_relevance.get("today_personal_themes") or []
            if isinstance(personal_relevance, dict)
            else []
        )
        if isinstance(item, dict)
    ]

    sentences: List[str] = []
    if daily_brief:
        sentences.append(daily_brief)
    elif personal_primary:
        label = str(personal_primary.get("label") or personal_primary.get("key") or "This signal").strip()
        short_reason = str(personal_primary.get("personal_reason_short") or "").strip()
        if short_reason:
            sentences.append(f"Right now, {label.lower()} looks most relevant for you. {short_reason}")
        else:
            sentences.append(f"Right now, {label.lower()} looks like the clearest current factor in your mix.")
    elif top_drivers:
        primary = top_drivers[0]
        primary_label = str(primary.get("label") or "The current mix").strip()
        secondary_clause = ""
        if len(top_drivers) > 1:
            secondary = top_drivers[1]
            secondary_label = str(secondary.get("label") or "another driver").strip()
            secondary_state = str(secondary.get("state") or "").strip().lower()
            secondary_clause = f", while {secondary_label} stays {secondary_state or 'active'}"
        sentences.append(
            _earthscope_template_pick(
                [
                    "{primary_label} is setting the pace right now, {state_text}{secondary_clause}.",
                    "Right now, {primary_label} is carrying the most weight, {state_text}{secondary_clause}.",
                    "At the moment, {primary_label} is the clearest influence, {state_text}{secondary_clause}.",
                    "Currently, {primary_label} is leading the mix, {state_text}{secondary_clause}.",
                    "For now, {primary_label} is doing more of the talking, {state_text}{secondary_clause}.",
                    "Right now, {primary_label} is out front, {state_text}{secondary_clause}.",
                    "At the moment, {primary_label} is the main thing to watch, {state_text}{secondary_clause}.",
                    "Currently, {primary_label} is the strongest external pull, {state_text}{secondary_clause}.",
                ],
                user_id=user_id,
                bucket_key=bucket_key,
                driver_family=_earthscope_driver_family_key(primary),
                slot="summary-lead",
            ).format(
                primary_label=primary_label,
                state_text=_earthscope_lead_state_text(primary),
                secondary_clause=secondary_clause,
            )
        )
    else:
        sentences.append(
            _earthscope_template_pick(
                [
                    "Right now, the environmental picture looks fairly even, with no single driver dominating.",
                    "At the moment, the outside signal mix looks relatively quiet, with no strong lead.",
                    "Currently, most environmental drivers are staying in lower zones.",
                    "In the current pattern, the driver mix looks lighter and fairly balanced.",
                    "For now, no single environmental signal is pulling especially hard.",
                ],
                user_id=user_id,
                bucket_key=bucket_key,
                driver_family="mixed",
                slot="summary-lead-fallback",
            )
        )

    support_driver = personal_supporting[0] if personal_supporting else (top_drivers[1] if len(top_drivers) > 1 else None)
    if support_driver:
        support_label = str(support_driver.get("label") or support_driver.get("key") or "").strip()
        if support_label and support_label.lower() not in daily_brief.lower():
            sentences.append(f"{support_label} is also in the mix right now.")

    theme_sentence = _summary_theme_sentence(personal_themes[0] if personal_themes else None)
    if theme_sentence:
        sentences.append(theme_sentence)
    else:
        sentences.append(_earthscope_gauge_sentence(top_gauges, gauge_labels))

    action_sentence = _summary_action_sentence(day, personal_primary or (top_drivers[0] if top_drivers else None), profile)
    if action_sentence:
        sentences.append(action_sentence)

    sentences.append("These are patterns to watch, not certainties.")
    return " ".join(sentences[:4]).strip()
