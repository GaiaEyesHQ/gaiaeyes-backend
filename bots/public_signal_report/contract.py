from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Mapping


REPORT_VERSION = "public-daily-signal-report.v1"
SECTION_ORDER = ("regional_watch", "space_watch", "earth_signal", "major_events")
REPORT_EDITIONS = {
    "global": {
        "public_name": "Gaia Eyes Global Health Snapshot",
        "geographic_scope": "global",
    },
    "us": {
        "public_name": "Gaia Eyes U.S. Health Snapshot",
        "geographic_scope": "United States",
    },
}


def empty_report(
    *,
    day: str | date,
    edition: str = "global",
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if edition not in REPORT_EDITIONS:
        raise ValueError(f"unsupported report edition: {edition}")
    timestamp = generated_at or datetime.now(timezone.utc)
    edition_config = REPORT_EDITIONS[edition]
    return {
        "report_version": REPORT_VERSION,
        "day": str(day),
        "edition": edition,
        "public_name": edition_config["public_name"],
        "geographic_scope": edition_config["geographic_scope"],
        "section_order": list(SECTION_ORDER),
        "headline": None,
        "quick_read": None,
        "regional_watch": {"items": []},
        "space_watch": {},
        "earth_signal": {},
        "major_events": {"items": []},
        "platform_copy": {
            "facebook": None,
            "instagram": None,
            "voiceover": None,
            "reel_story": None,
        },
        "coverage": {},
        "sources": [],
        "generated_at_utc": timestamp.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "auto_publish": False,
    }


def validate_report_contract(report: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("report_version") != REPORT_VERSION:
        errors.append("unexpected report_version")
    edition = report.get("edition")
    if edition not in REPORT_EDITIONS:
        errors.append("unsupported report edition")
    elif report.get("public_name") != REPORT_EDITIONS[str(edition)]["public_name"]:
        errors.append("public_name does not match report edition")
    if tuple(report.get("section_order") or ()) != SECTION_ORDER:
        errors.append("section_order must be Regional, Space, Earth, Major Events")
    if report.get("auto_publish") is not False:
        errors.append("shadow report must set auto_publish=false")
    regional = report.get("regional_watch")
    if not isinstance(regional, Mapping) or not isinstance(regional.get("items"), list):
        errors.append("regional_watch.items must be a list")
    major = report.get("major_events")
    if not isinstance(major, Mapping) or not isinstance(major.get("items"), list):
        errors.append("major_events.items must be a list")
    if not isinstance(report.get("space_watch"), Mapping):
        errors.append("space_watch must be an object")
    if not isinstance(report.get("earth_signal"), Mapping):
        errors.append("earth_signal must be an object")
    return errors
