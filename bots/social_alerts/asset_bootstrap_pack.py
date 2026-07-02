from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Mapping, Sequence


BOOTSTRAP_PREFIX = "bootstrap:social_alerts"


@dataclass(frozen=True)
class BootstrapBackground:
    key: str
    keywords: tuple[str, ...]
    prompt: str
    palette: tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]

    @property
    def candidate(self) -> str:
        return f"{BOOTSTRAP_PREFIX}/{self.key}"


BACKGROUND_PACKS: Mapping[str, BootstrapBackground] = {
    "resonance_field": BootstrapBackground(
        key="resonance_field",
        keywords=("schumann", "resonance", "earthscope", "frequency", "ulf"),
        prompt=(
            "Dark blue Schumann-style resonance field with soft cyan and violet frequency bands, "
            "subtle spectrogram texture, and quiet space for a health-first alert overlay."
        ),
        palette=((2, 8, 18), (35, 167, 154), (115, 76, 196)),
    ),
    "nervous_system_static": BootstrapBackground(
        key="nervous_system_static",
        keywords=("hrv", "sleep", "focus", "restlessness", "nervous_system"),
        prompt=(
            "Moody abstract nervous-system signal art with fine electric threads, soft teal glow, "
            "deep navy shadows, and room for symptom chips."
        ),
        palette=((4, 10, 20), (61, 203, 213), (109, 164, 255)),
    ),
    "migraine_pressure": BootstrapBackground(
        key="migraine_pressure",
        keywords=("migraine", "headache", "sinus", "pressure", "barometric"),
        prompt=(
            "Atmospheric pressure-wave background for migraine and head-pressure alerts, with "
            "muted indigo, stormy teal, and a soft amber horizon."
        ),
        palette=((8, 11, 27), (48, 130, 152), (221, 154, 75)),
    ),
    "solar_aurora": BootstrapBackground(
        key="solar_aurora",
        keywords=("geomagnetic", "kp", "bz", "solar_wind", "space_weather", "aurora"),
        prompt=(
            "Subtle aurora arcs over a dark horizon, scientific but human, with cyan-green light "
            "and a calm black-blue card-safe background."
        ),
        palette=((3, 10, 24), (63, 145, 238), (121, 218, 139)),
    ),
    "solar_heat": BootstrapBackground(
        key="solar_heat",
        keywords=("solar_flare", "flare", "solar", "xray"),
        prompt=(
            "Solar flare inspired glow with warm orange plasma, dark navy edges, and restrained "
            "contrast for readable alert text."
        ),
        palette=((18, 7, 8), (225, 114, 43), (247, 205, 100)),
    ),
    "cme_wave": BootstrapBackground(
        key="cme_wave",
        keywords=("cme", "coronal", "solar_wind", "solar"),
        prompt=(
            "Deep-space CME wave background with blue-white motion arcs and amber solar haze, "
            "designed for carousel and reel overlays."
        ),
        palette=((5, 13, 31), (54, 143, 214), (236, 146, 73)),
    ),
    "air_quality_haze": BootstrapBackground(
        key="air_quality_haze",
        keywords=("aqi", "air_quality", "smoke", "haze"),
        prompt=(
            "Soft smoky haze over a dark city-edge horizon, muted teal and gold, with enough "
            "negative space for health-context text."
        ),
        palette=((8, 13, 18), (87, 141, 135), (197, 147, 82)),
    ),
    "weather_pressure": BootstrapBackground(
        key="weather_pressure",
        keywords=("humidity", "weather", "temperature", "local", "pressure_swing"),
        prompt=(
            "Layered weather-map pressure bands with humid teal, storm blue, and warm edge light, "
            "abstract enough for broad local-condition alerts."
        ),
        palette=((8, 14, 21), (54, 127, 157), (211, 166, 86)),
    ),
    "exposure_indoor": BootstrapBackground(
        key="exposure_indoor",
        keywords=("exposure", "fragrance", "cleaning", "mold", "traffic", "pesticide"),
        prompt=(
            "Dim indoor environmental-trigger background with soft dust motes, green-blue shadows, "
            "and a clean clinical-not-alarming mood."
        ),
        palette=((7, 12, 18), (73, 150, 122), (157, 118, 83)),
    ),
    "earthscope_cosmic": BootstrapBackground(
        key="earthscope_cosmic",
        keywords=("earthscope", "pattern", "health", "signals", "body_context"),
        prompt=(
            "Gaia Eyes cosmic health-pattern background: earth glow, subtle signal lines, "
            "deep navy field, and premium wellness-tech restraint."
        ),
        palette=((3, 9, 20), (53, 185, 174), (96, 132, 218)),
    ),
}


def _norm(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _candidate_keys(category: str, keywords: Sequence[str]) -> List[str]:
    tokens = {_norm(category)}
    tokens.update(_norm(keyword) for keyword in keywords if keyword)

    ranked: List[tuple[int, str]] = []
    for key, pack in BACKGROUND_PACKS.items():
        score = sum(1 for keyword in pack.keywords if keyword in tokens)
        if score:
            ranked.append((score, key))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    keys = [key for _, key in ranked]
    if "earthscope_cosmic" not in keys:
        keys.append("earthscope_cosmic")
    return keys[:4]


def bootstrap_background_candidates(category: str, keywords: Sequence[str]) -> List[str]:
    return [BACKGROUND_PACKS[key].candidate for key in _candidate_keys(category, keywords)]


def bootstrap_background_prompts(category: str, keywords: Sequence[str]) -> List[str]:
    return [BACKGROUND_PACKS[key].prompt for key in _candidate_keys(category, keywords)]


def bootstrap_palette(candidate: str) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]] | None:
    prefix = f"{BOOTSTRAP_PREFIX}/"
    if not candidate.startswith(prefix):
        return None
    key = candidate.removeprefix(prefix)
    pack = BACKGROUND_PACKS.get(key)
    if pack is None:
        return None
    return pack.palette


def all_bootstrap_candidates() -> Iterable[str]:
    for pack in BACKGROUND_PACKS.values():
        yield pack.candidate
