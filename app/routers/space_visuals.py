from __future__ import annotations

import json
from datetime import timezone
from os import getenv
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from psycopg.rows import dict_row

from app.db import get_db

router = APIRouter(prefix="/v1")

_DEFAULT_MEDIA_BASE = "https://cdn.jsdelivr.net/gh/GaiaEyesHQ/gaiaeyes-media@main"


def _media_base() -> str:
    base = getenv("MEDIA_BASE_URL") or _DEFAULT_MEDIA_BASE
    return base.rstrip("/")


def _iso(ts):
    if ts is None:
        return None
    return ts.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return {}
    return {}


def _ensure_list(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            data = json.loads(value)
            return data if isinstance(data, list) else []
        except Exception:
            return []
    return []


@router.get("/space/visuals")
async def space_visuals(conn=Depends(get_db)):
    media_base = _media_base()
    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                select distinct on (asset_type, key)
                    ts,
                    key,
                    asset_type,
                    image_path,
                    meta,
                    series,
                    feature_flags,
                    instrument,
                    credit
                from ext.space_visuals
                order by asset_type, key, ts desc
                """,
                prepare=False,
            )
            rows = await cur.fetchall()
    except Exception as exc:
        return {"ok": False, "data": None, "error": f"space_visuals failed: {exc}"}

    images: List[Dict[str, Any]] = []
    series: List[Dict[str, Any]] = []
    overlay_flags: Dict[str, bool] = {}
    latest_ts = None

    for row in rows or []:
        asset_type = row.get("asset_type") or "image"
        ts = row.get("ts")
        iso_ts = _iso(ts)
        if iso_ts and (latest_ts is None or iso_ts > latest_ts):
            latest_ts = iso_ts
        flags = _ensure_json(row.get("feature_flags"))
        for key, value in flags.items():
            if value:
                overlay_flags[key] = True
        meta = _ensure_json(row.get("meta"))
        if asset_type == "series":
            samples = _ensure_list(row.get("series"))
            series.append(
                {
                    "key": row.get("key"),
                    "captured_at": iso_ts,
                    "samples": samples,
                    "meta": meta,
                    "instrument": row.get("instrument"),
                    "credit": row.get("credit"),
                    "feature_flags": flags,
                }
            )
            continue
        rel_path = row.get("image_path") or ""
        url = meta.get("url")
        if not url and rel_path:
            url = f"{media_base}/{rel_path.lstrip('/')}"
        images.append(
            {
                "key": row.get("key"),
                "captured_at": iso_ts,
                "url": url,
                "image_path": rel_path,
                "instrument": row.get("instrument"),
                "credit": row.get("credit"),
                "meta": meta,
                "feature_flags": flags,
                "asset_type": asset_type,
            }
        )

    images.sort(key=lambda item: (item.get("key") or "", item.get("captured_at") or ""))
    series.sort(key=lambda item: item.get("key") or "")

    return {
        "ok": True,
        "generated_at": latest_ts,
        "images": images,
        "series": series,
        "feature_flags": overlay_flags,
    }
