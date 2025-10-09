"""
Gaia Eyes – Internal Agent Constants
Author: Jennifer (Gaia Eyes)
Version: 1.0 (2025-10-08)
Notes: Portable constants, schemas, tone/snippets, and helper utilities
for Daily EarthScope generation. Load RULES from the YAML file alongside this.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Any, Optional

# ------------------------------
# 0) Core thresholds & bands
# ------------------------------

KP_BANDS = {
    "quiet": (0, 2),
    "unsettled": (3, 3),
    "active": (4, 4),
    "G1": (5, 5),
    "G2": (6, 6),
    "G3": (7, 7),
    "G4": (8, 8),
    "G5": (9, 9),
}

BZ_THRESHOLDS = {
    "mild_south": {"value": -3.0, "minutes": 120},
    "significant_south": {"value": -5.0, "minutes": 180},
    "strong_south": {"value": -10.0, "minutes": 60},
}

SOLAR_WIND_SPEED_BANDS = {
    "calm": (0, 399),
    "moderate": (400, 500),
    "elevated": (501, 700),
    "high": (701, 10_000),
}

SOLAR_WIND_DENSITY_FLAGS = {
    "compressive": 3.0,      # dyn pressure nPa (computed)
    "strong_compression": 6.0,
    "density_notable": 20.0, # cm^-3 when speed is also high
}

DST_BANDS = {
    "quiet": (0, -29),
    "weak_storm": (-30, -49),
    "storm": (-50, -99),
    "strong_storm": (-100, -1000),
}

FLARE_CLASSES = ["C", "M", "X"]

SCHUMANN_FLAGS = {
    "spike_multiplier": 2.0,      # > 2x rolling median in 24h
    "sustained_pct": 75,          # f0 above 75th percentile
    "sustained_hours": 6,
    "broadband_min_harmonics": 3, # elevated across >= 3 harmonics
}

METEOROLOGY = {
    "pressure_drop_6_12h": 5.0,  # hPa
    "pressure_drop_24h": 8.0,    # hPa
    "storm_nearby_km": 25,
}

SEISMIC = {
    "nearby_mag": 5.0,
    "nearby_km": 500,
    "nearby_window_h": 72,
    "cluster_mag": 4.5,
    "cluster_count": 3,
    "cluster_window_h": 72,
    "cluster_km": 300,
    "far_large_mag": 6.5,
    "far_large_km": 1000,
    "far_large_window_d": 7,
}

# ------------------------------
# 1) Practice dictionary (ids -> copy)
# ------------------------------

PRACTICES: Dict[str, str] = {
    "phys_sigh": "5–10 min physiological sigh (double inhale, slow exhale).",
    "grounding_15": "15 min barefoot contact with earth (safe surface).",
    "electrolytes": "Water + electrolytes mid‑day.",
    "b478": "4‑7‑8 breathing × 3–5 cycles.",
    "walk20": "20‑minute outdoor walk.",
    "evening_blue_min": "Low blue‑light after sunset; warm lamps only.",
    "box_44": "Box breathing 4‑4‑4‑4 for 2–3 minutes.",
    "posture_reset": "Spine lengthen + shoulder openers 2 minutes.",
    "slow_6_bpm": "Coherent breathing ~6 breaths/min for 5–10 min.",
    "deep_work_40": "Single‑task 40‑minute block, notifications off.",
    "hydration_salt": "Hydrate; add pinch of salt if needed.",
    "mag_evening": "Magnesium (if tolerated and already used) in evening.",
    "early_winddown": "Wind‑down routine 45–60 min earlier.",
    "simplify_evening": "Reduce inputs/commitments tonight.",
    "short_meditation": "5–10 min guided or breath‑focused sit.",
    "gratitude3": "Write 3 quick gratitude lines."
}

# ------------------------------
# 2) Tone & prose snippets
# ------------------------------

VOICE = {
    "lead": "Warm, plain‑language, non‑alarmist. Always include a concise TL;DR.",
    "time": "Use explicit dates like 'Wednesday, Oct 8' in the user’s timezone.",
    "agency": "Offer 2–3 simple actions; avoid deterministic claims."
}

SNIPPETS = [
    "Today’s magnetic field ran a little fast; if you feel wired, that’s normal—two slow breathing breaks help.",
    "Southward Bz opened the door for solar wind to couple in; plan for steadier pacing this afternoon.",
    "Pressure fell quickly with the front—hydrate and keep the evening simple."
]

# ------------------------------
# 3) Example JSON schema fields (for internal validation)
# ------------------------------

EXAMPLE_OUTPUT_SCHEMA: Dict[str, Any] = {
    "date_local": "YYYY-MM-DD",
    "geo": {
        "kp_max_24h": 0,
        "kp_bins": [2, 3, 4, 5],
        "bz": {"min": -11.2, "south_2h": True, "south_3h": True},
        "sw": {"speed_max": 620, "density_max": 24, "p_dyn_max": 8.1},
        "dst_min": -62,
    },
    "solar": {
        "flares": [{"class": "M3.1", "peak": "2025-10-07T11:20Z"}],
        "proton_event": False,
        "cme": {"earth_directed": True, "eta": "2025-10-09T06:00Z", "speed": 900},
    },
    "schumann": {"f0_amp_spike": True, "broadband": False, "sustained": True},
    "met": {"pressure_drop_hPa_24h": 9.2, "storm_nearby_km": 18},
    "seismic": {"nearest": {"mag": 5.3, "km": 410, "hours_ago": 36}, "cluster": False},
    "derived_tags": ["kp_high_window", "bz_south_3h", "sr_sustained", "met_pressure_drop"],
    "confidence": "medium",
    "sections": {
        "tldr": "G1-level conditions with sustained southward Bz; expect edgy-then-tired pattern. Keep evening low-stim.",
        "today": "Kp peaked at 5, Bz held south ~3h while solar wind ran 600+ km/s. Schumann baseline elevated most of the day.",
        "next_72h": "A CME shock may arrive Thu morning; brief magnetic spike likely. Weather front continues today with falling pressure.",
        "nervous_system": "Sympathetic tilt during spikes; plan 2× breath resets and light evening.",
        "sleep": "Slightly higher sleep latency risk; warm lighting and earlier wind-down help.",
        "practices": ["Physiological sigh 5 min", "15 min barefoot grounding", "Electrolytes mid-day"],
        "notes": "Regional M5.3 quake yesterday—just a background mention."
    }
}

# ------------------------------
# 4) Utility helpers (pure Python; plug into your pipeline)
# ------------------------------

def dynamic_pressure_npa(density_cm3: float, speed_kms: float) -> float:
    """Compute solar wind dynamic pressure in nPa.
    P_dyn ≈ 1.6726e−6 * n(cm^-3) * v(km/s)^2
    """
    return 1.6726e-6 * density_cm3 * (speed_kms ** 2)

def confidence_word(score: float) -> str:
    """Map 0..1 to low/medium/high."""
    if score >= 0.66:
        return "high"
    if score >= 0.33:
        return "medium"
    return "low"