from __future__ import annotations

from datetime import timedelta


SEVERITY_RANK = {"info": 1, "watch": 2, "high": 3}

COOLDOWNS = {
    "info": timedelta(hours=12),
    "watch": timedelta(hours=6),
    "high": timedelta(hours=3),
}

ESCALATION_ONLY = True
