from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from dotenv import load_dotenv

from .collector import collect_anchor_observations, collect_existing_public_context
from .contract import validate_report_contract
from .regions import PUBLIC_SIGNAL_ANCHORS, US_SIGNAL_ANCHORS
from .report import build_daily_signal_report
from .writer import generate_platform_copy


def _read_json(path: str | Path | None) -> Any:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _previous_by_anchor(path: str | Path | None) -> dict[str, Mapping[str, Any]]:
    payload = _read_json(path)
    if not isinstance(payload, Mapping):
        return {}
    review_inputs = payload.get("review_inputs") if isinstance(payload.get("review_inputs"), Mapping) else {}
    rows = review_inputs.get("observations") if isinstance(review_inputs.get("observations"), list) else []
    return {
        str(row.get("anchor_id")): row
        for row in rows
        if isinstance(row, Mapping) and row.get("anchor_id")
    }


def _apply_copy(report: dict[str, Any], copy: Mapping[str, Any]) -> None:
    if copy.get("status") != "generated":
        return
    report["headline"] = copy.get("headline")
    report["quick_read"] = copy.get("quick_read")
    report["platform_copy"] = {
        "facebook": copy.get("facebook"),
        "instagram": copy.get("instagram"),
        "voiceover": copy.get("voiceover"),
        "reel_story": copy.get("reel_story"),
    }
    sections = copy.get("section_copy") if isinstance(copy.get("section_copy"), Mapping) else {}
    for key in ("regional_watch", "space_watch", "earth_signal", "major_events"):
        if isinstance(report.get(key), dict) and sections.get(key) is not None:
            report[key]["copy"] = sections.get(key)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a shadow-only public Gaia Eyes Health Snapshot.")
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--edition", choices=("global", "us"), default="global")
    parser.add_argument("--output", default=None)
    parser.add_argument("--observations-fixture", default=None)
    parser.add_argument("--context-fixture", default=None)
    parser.add_argument("--previous", default=None)
    parser.add_argument("--anchor-limit", type=int, default=0)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--model", default=None, help="Optional shadow-only OpenAI model override.")
    parser.add_argument("--no-writer", action="store_true")
    return parser


async def run(args: argparse.Namespace) -> Path:
    load_dotenv(dotenv_path=Path(".env"))
    observation_payload = _read_json(args.observations_fixture)
    if isinstance(observation_payload, Mapping):
        observations = observation_payload.get("observations") or []
    elif isinstance(observation_payload, list):
        observations = observation_payload
    else:
        anchors = PUBLIC_SIGNAL_ANCHORS[: args.anchor_limit] if args.anchor_limit > 0 else PUBLIC_SIGNAL_ANCHORS
        observations = await collect_anchor_observations(
            anchors,
            openweather_key=os.getenv("OPENWEATHER_API_KEY", "").strip(),
            pollen_key=os.getenv("GOOGLE_POLLEN_API_KEY", "").strip(),
            previous_by_anchor=_previous_by_anchor(args.previous),
            concurrency=args.concurrency,
        )

    context = _read_json(args.context_fixture)
    if not isinstance(context, Mapping):
        db_url = (
            os.getenv("SUPABASE_DB_URL", "").strip()
            or os.getenv("DIRECT_URL", "").strip()
            or os.getenv("DATABASE_URL", "").strip()
        )
        context = collect_existing_public_context(db_url) if db_url else {}

    report = build_daily_signal_report(
        day=args.date,
        observations=observations,
        context=context,
        expected_anchor_count=len(US_SIGNAL_ANCHORS) if args.edition == "us" else len(PUBLIC_SIGNAL_ANCHORS),
        edition=args.edition,
    )
    copy = (
        {"status": "not_generated", "reason": "--no-writer"}
        if args.no_writer
        else generate_platform_copy(
            report,
            api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            model=args.model,
        )
    )
    _apply_copy(report, copy)
    errors = validate_report_contract(report)
    if errors:
        raise RuntimeError("Invalid report contract: " + "; ".join(errors))

    default_name = f"{args.date}.json" if args.edition == "global" else f"{args.date}-{args.edition}.json"
    output = Path(args.output) if args.output else Path("tmp/public_signal_report") / default_name
    output.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "auto_publish": False,
        "report": report,
        "copy_runtime": dict(copy),
        "review_inputs": {
            "edition": args.edition,
            "observation_count": len(observations),
            "observations": observations,
            "context": context,
        },
    }
    output.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[public-signal-report.shadow] wrote {output}")
    return output


def main() -> None:
    args = build_parser().parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
