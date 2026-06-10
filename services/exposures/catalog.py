from __future__ import annotations

LEGACY_EXPOSURE_KEYS = (
    "allergen_exposure",
    "overexertion",
)

ILLNESS_EXPOSURE_KEYS = (
    "temporary_illness",
    "illness_respiratory",
    "illness_gastrointestinal",
    "illness_fever",
    "illness_other",
)

EVERYDAY_EXPOSURE_KEYS = (
    "fragrance_scented_products",
    "cleaning_products",
    "plastics_heated_food",
    "ultra_processed_meal",
    "alcohol",
    "high_histamine_foods",
    "pesticide_heavy_produce",
    "mold_damp_space",
    "workplace_exposure",
    "heavy_traffic",
    "poor_air_quality",
    "new_supplement_medication",
)

EXPOSURE_LABELS = {
    "allergen_exposure": "Allergen exposure",
    "overexertion": "Heavy activity",
    "temporary_illness": "Temporary illness",
    "illness_respiratory": "Sinus / respiratory illness",
    "illness_gastrointestinal": "Stomach / GI illness",
    "illness_fever": "Fever / infection",
    "illness_other": "Other illness",
    "fragrance_scented_products": "Fragrance / scented products",
    "cleaning_products": "Cleaning products",
    "plastics_heated_food": "Plastics or heated food containers",
    "ultra_processed_meal": "Ultra-processed meal",
    "alcohol": "Alcohol",
    "high_histamine_foods": "High-histamine foods",
    "pesticide_heavy_produce": "Pesticide-heavy produce",
    "mold_damp_space": "Mold or damp space",
    "workplace_exposure": "Workplace exposure",
    "heavy_traffic": "Heavy traffic",
    "poor_air_quality": "Poor air quality",
    "new_supplement_medication": "New supplement or medication",
}

ALL_EXPOSURE_KEYS = frozenset(
    (*LEGACY_EXPOSURE_KEYS, *ILLNESS_EXPOSURE_KEYS, *EVERYDAY_EXPOSURE_KEYS)
)


def exposure_label(key: str) -> str:
    normalized = str(key or "").strip().lower()
    return EXPOSURE_LABELS.get(normalized) or normalized.replace("_", " ").title()
