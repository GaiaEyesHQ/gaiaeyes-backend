from __future__ import annotations

import json
from datetime import timezone
from os import getenv
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from psycopg.rows import dict_row

from app.db import get_db

router = APIRouter(prefix="/v1")

# Legacy default (GitHub) remains as last resort
_DEFAULT_MEDIA_BASE = ""


def _visuals_env_snapshot() -> dict:
    from os import getenv

    return {
        "VISUALS_MEDIA_BASE_URL": getenv("VISUALS_MEDIA_BASE_URL") or None,
        "MEDIA_BASE_URL": getenv("MEDIA_BASE_URL") or None,
        "GAIA_MEDIA_BASE": getenv("GAIA_MEDIA_BASE") or None,
    }


def _media_base() -> str:
    """
    Prefer a visuals-specific Supabase base if provided; otherwise try MEDIA_BASE_URL/GAIA_MEDIA_BASE.
    Return an empty string if unset (clients can still resolve relative URLs via their own base).
    """
    base = (
        getenv("VISUALS_MEDIA_BASE_URL")
        or getenv("MEDIA_BASE_URL")
        or getenv("GAIA_MEDIA_BASE")
        or ""
    )
    return base.rstrip("/") if base else ""


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


def _to_relative(url: str | None, base: str | None) -> str | None:
    """
    If `url` starts with `base`, strip it to a leading-slash relative path.
    If `url` is already relative, normalize to start with '/'.
    Otherwise, return the original absolute URL.
    """
    if not url:
        return None
    if base and isinstance(url, str) and url.startswith(base):
        rest = url[len(base):]
        return rest if rest.startswith("/") else f"/{rest}"
    # Already relative?
    if "://" not in url:
        return url if url.startswith("/") else f"/{url}"
    return url


def _rebase_path(rel_path: str | None, key: str | None) -> str | None:
    if not rel_path:
        return None
    rp = rel_path.lstrip("/")
    # Back-compat: if old rows had images/space/*, remap based on key
    if rp.startswith("images/space/"):
        k = (key or "").lower()
        # DRAP (any variant) -> single latest
        if k.startswith("drap"):
            return "drap/latest.png"
        # Aurora viewlines
        if k in ("ovation_nh", "aurora_north", "aurora_viewline_north"):
            return "aurora/viewline/tonight-north.png"
        if k in ("ovation_sh", "aurora_south", "aurora_viewline_south"):
            return "aurora/viewline/tonight-south.png"
        # NASA LASCO/AIA/HMI/CCOR
        if k in ("lasco_c2", "soho_c2"):
            return "nasa/lasco_c2/latest.jpg"
        if k == "lasco_c3":
            return "nasa/lasco_c3/latest.jpg"
        if k in ("aia_primary", "aia_304"):
            return "nasa/aia_304/latest.jpg"
        if k == "hmi_intensity":
            return "nasa/hmi_intensity/latest.jpg"
        if k in ("ccor1", "ccor1_jpeg"):
            return "nasa/ccor1/latest.jpg"
        # Magnetosphere geospace horizons: geospace_1d/3h/7d
        if k.startswith("geospace_"):
            try:
                horizon = k.split("_", 1)[1]
            except Exception:
                horizon = "latest"
            return f"magnetosphere/geospace/{horizon}.png"
        # KP station
        if k == "kp_station":
            return "space/kp_station/latest.png"
        # Fallback: strip the legacy prefix (clients may still resolve via cdn_base/GAIA_MEDIA_BASE)
        return rp[len("images/space/"):]
    return rp


async def _build_visuals_payload(conn, media_base: str) -> dict:
    cdn_out = media_base or None
    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            # Latest record per (asset_type, key)
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
        return {"ok": False, "data": None, "error": f"space_visuals failed: {exc}", "cdn_base": cdn_out}

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

        raw_rel = row.get("image_path") or ""
        rel_path = _rebase_path(raw_rel, row.get("key"))
        url = meta.get("url")
        if url:
            url = _to_relative(url, media_base)
        elif rel_path:
            url = f"/{rel_path}"
        else:
            url = None

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

    # Unified items array (new) — keeps legacy fields too
    items: List[Dict[str, Any]] = []
    for img in images:
        rel_url = _to_relative(img.get("url"), media_base)
        if not rel_url and img.get("image_path"):
            rel_url = f"/{(img.get('image_path') or '').lstrip('/')}"
        items.append(
            {
                "id": img.get("key") or img.get("asset_type") or "image",
                "title": (img.get("meta") or {}).get("title") or img.get("key"),
                "credit": img.get("credit"),
                "url": rel_url or img.get("url") or "",
                "meta": (img.get("meta") or {}) | {"captured_at": img.get("captured_at")},
            }
        )
    for s in series:
        key = s.get("key") or "series"
        samples = s.get("samples") or []
        items.append(
            {
                "id": key,
                "title": key,
                "credit": s.get("credit"),
                "url": "",
                "series": {key: samples},
                "meta": (s.get("meta") or {}) | {"captured_at": s.get("captured_at")},
            }
        )

    # Ensure a small baseline set so clients render even if DB yields few/none
    existing = {it.get("id") for it in items if it.get("id")}
    baseline: List[Dict[str, Any]] = [
        {"id": "enlil_cme",  "title": "ENLIL CME Propagation", "credit": "NOAA/WSA–ENLIL+Cone", "url": "/nasa/enlil/latest.mp4",
         "meta": {"source": "https://services.swpc.noaa.gov/images/animations/enlil/"}},
        {"id": "drap",       "title": "D-RAP Absorption",       "credit": "NOAA/SWPC",         "url": "/drap/latest.png"},
        {"id": "lasco_c2",   "title": "LASCO C2",               "credit": "SOHO/LASCO",        "url": "/nasa/lasco_c2/latest.jpg"},
        {"id": "aia_304",    "title": "AIA 304Å",               "credit": "SDO/AIA",           "url": "/nasa/aia_304/latest.jpg"},
        {"id": "ovation_nh", "title": "Aurora Viewline (N)",    "credit": "NOAA SWPC",         "url": "/aurora/viewline/tonight-north.png"},
        {"id": "ovation_sh", "title": "Aurora Viewline (S)",    "credit": "NOAA SWPC",         "url": "/aurora/viewline/tonight-south.png"},
    ]
    # Append any baseline not already present; also use baseline when items is empty
    for b in baseline:
        if b["id"] not in existing:
            items.append(b)

    cdn_out = media_base or None

    return {
        "ok": True,
        "schema_version": 1,
        "cdn_base": cdn_out,
        "generated_at": latest_ts,
        "images": images,
        "series": series,
        "feature_flags": overlay_flags,
        "items": items,
    }


@router.get("/space/visuals")
async def space_visuals(conn=Depends(get_db)):
    media_base = _media_base()
    payload = await _build_visuals_payload(conn, media_base)
    payload["cdn_base"] = payload.get("cdn_base") or (media_base or None)
    return payload


@router.get("/space/visuals/public")
async def space_visuals_public(conn=Depends(get_db)):
    media_base = _media_base()
    payload = await _build_visuals_payload(conn, media_base)
    payload["cdn_base"] = payload.get("cdn_base") or (media_base or None)
    return payload


@router.get("/space/visuals/diag")
async def space_visuals_diag(conn=Depends(get_db)):
    # What the service sees
    env = _visuals_env_snapshot()
    # Quick count from DB
    total = 0
    try:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute("select count(*) as c from ext.space_visuals", prepare=False)
            total = (await cur.fetchone())["c"]
    except Exception as exc:
        return {"ok": False, "env": env, "error": f"db failed: {exc}"}
    # Dry-run media base
    mb = _media_base()
    return {"ok": True, "env": env, "media_base": mb or None, "db_rows": total}
