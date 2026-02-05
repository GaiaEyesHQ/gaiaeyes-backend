from pathlib import Path
import csv
from typing import Tuple, Optional

import requests

from ..db import pg

DATA_CSV = Path("data/zip_centroids.csv")
USER_AGENT = "gaiaeyes-local/zip-fallback (+https://gaiaeyes.com)"


def _normalize_zip(z: str) -> str:
    """Coerce anything resembling a US ZIP into 5 ASCII digits."""
    s = "".join(ch for ch in str(z) if ch.isdigit())
    return s[:5].zfill(5) if s else ""


def _zippopotam_latlon(zip_code: str) -> Optional[Tuple[float, float]]:
    """
    Free, no-key ZIP→lat/lon:
    https://api.zippopotam.us/us/{zip}
    """
    try:
        r = requests.get(
            f"https://api.zippopotam.us/us/{zip_code}",
            timeout=6,
            headers={"User-Agent": USER_AGENT},
        )
        if r.status_code == 200:
            j = r.json()
            places = j.get("places") or []
            if places:
                lat = float(places[0]["latitude"])
                lon = float(places[0]["longitude"])
                return lat, lon
    except Exception:
        pass
    return None


def _census_latlon(zip_code: str) -> Optional[Tuple[float, float]]:
    """
    US Census Geocoder ZIP endpoint (no key):
    https://geocoding.geo.census.gov/geocoder/locations/zip?zip=XXXXX&benchmark=Public_AR_Current&format=json

    Response shapes vary a bit; try common fields.
    """
    try:
        params = {
            "zip": zip_code,
            "benchmark": "Public_AR_Current",
            "format": "json",
        }
        r = requests.get(
            "https://geocoding.geo.census.gov/geocoder/locations/zip",
            params=params,
            timeout=8,
            headers={"User-Agent": USER_AGENT},
        )
        if r.status_code == 200:
            j = r.json()
            res = j.get("result") or {}

            # Some responses include addressMatches with coordinates {x: lon, y: lat}
            matches = res.get("addressMatches") or []
            if matches:
                coords = matches[0].get("coordinates") or {}
                x = coords.get("x")
                y = coords.get("y")
                if x is not None and y is not None:
                    return float(y), float(x)

            # Others may include a zipCodes array with centroid {x, y}
            zipcodes = res.get("zipCodes") or res.get("ZIPCodes") or []
            if zipcodes:
                centroid = zipcodes[0].get("centroid") or {}
                x = centroid.get("x")
                y = centroid.get("y")
                if x is not None and y is not None:
                    return float(y), float(x)
    except Exception:
        pass
    return None


def _cache_zip(zip_code: str, lat: float, lon: float) -> None:
    """Best-effort upsert into ext.zip_centroids so future lookups are instant."""
    try:
        pg.execute(
            """
            insert into ext.zip_centroids (zip, lat, lon)
            values (%s, %s, %s)
            on conflict (zip) do update
              set lat = excluded.lat, lon = excluded.lon
            """,
            zip_code,
            lat,
            lon,
        )
    except Exception:
        # Caching failure should never break the request path
        pass


def zip_to_latlon(zip_code: str) -> Tuple[float, float]:
    """
    Resolve a US ZIP to (lat, lon), with fallback order:
    1) ext.zip_centroids
    2) data/zip_centroids.csv (legacy)
    3) Zippopotam.us
    4) US Census Geocoder

    On success via (2-4) we upsert back into ext.zip_centroids.
    """
    z = _normalize_zip(zip_code)
    if not z:
        raise ValueError(f"Invalid ZIP: {zip_code}")

    # 1) DB cache
    row = pg.fetchrow("select lat, lon from ext.zip_centroids where zip = %s", z)
    if row:
        return float(row["lat"]), float(row["lon"])

    # 2) Legacy CSV fallback
    if DATA_CSV.exists():
        try:
            with DATA_CSV.open(newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    if _normalize_zip(r.get("zip", "")) == z:
                        lat, lon = float(r["lat"]), float(r["lon"])
                        _cache_zip(z, lat, lon)
                        return lat, lon
        except Exception:
            # Continue to network fallbacks
            pass

    # 3) Zippopotam.us
    hit = _zippopotam_latlon(z)
    if hit:
        lat, lon = hit
        _cache_zip(z, lat, lon)
        return lat, lon

    # 4) US Census Geocoder
    hit = _census_latlon(z)
    if hit:
        lat, lon = hit
        _cache_zip(z, lat, lon)
        return lat, lon

    raise ValueError(f"Unknown ZIP: {z}")
