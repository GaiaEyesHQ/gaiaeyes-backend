from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Tuple


DEFAULT_DEFINITION_PATH = Path(__file__).resolve().parent / "gauge_logic_base_v1.json"

_REQUIRED_KEYS = [
    "version",
    "global_disclaimer",
    "confidence_multiplier",
    "gauges",
    "effect_tags",
    "scoring_model",
    "signal_definitions",
    "alert_pills",
    "writer_outputs",
]


def load_definition_base(path: Path | str | None = None) -> Tuple[Dict[str, Any], str]:
    """
    Load the Gaia Eyes logic definition base JSON and validate required keys.
    Returns (definition_obj, version).
    """
    definition_path = Path(path) if path else DEFAULT_DEFINITION_PATH
    with definition_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    root = raw.get("gaia_eyes_logic_base")
    if not isinstance(root, dict):
        raise ValueError("Definition base missing 'gaia_eyes_logic_base' root object")

    missing = [k for k in _REQUIRED_KEYS if k not in root]
    if missing:
        raise ValueError(f"Definition base missing keys: {', '.join(missing)}")

    version = str(root.get("version"))
    if not version:
        raise ValueError("Definition base missing version")

    return root, version
