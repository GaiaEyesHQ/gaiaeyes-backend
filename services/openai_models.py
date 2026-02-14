from __future__ import annotations

import os
from typing import Optional


_PURPOSE_ENV = {
    "member_writer": "OPENAI_MODEL_MEMBER_WRITER",
    "public_writer": "OPENAI_MODEL_PUBLIC_WRITER",
}


def resolve_openai_model(purpose: str) -> Optional[str]:
    """
    Resolve a model name by purpose with env-based fallback chain.
    No hardcoded model identifiers are used here.
    """
    keys = [
        _PURPOSE_ENV.get(purpose, ""),
        "OPENAI_MODEL_DEFAULT",
        "OPENAI_MODEL",
        "GAIA_OPENAI_MODEL",  # legacy compatibility
    ]
    for key in keys:
        if not key:
            continue
        value = (os.getenv(key) or "").strip()
        if value:
            return value
    return None

