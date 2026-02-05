from pathlib import Path
import csv
from typing import Tuple

from ..db import pg

DATA_CSV = Path("data/zip_centroids.csv")


def zip_to_latlon(zip_code: str) -> Tuple[float, float]:
    row = pg.fetchrow("select lat, lon from ext.zip_centroids where zip = $1", zip_code)
    if row:
        return float(row["lat"]), float(row["lon"])

    if DATA_CSV.exists():
        with DATA_CSV.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("zip") == zip_code:
                    return float(r["lat"]), float(r["lon"])

    raise ValueError(f"Unknown ZIP: {zip_code}")
