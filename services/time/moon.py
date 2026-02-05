from math import cos, pi
from datetime import datetime, timezone

PHASES = [
    ("New Moon", 0.0),
    ("Waxing Crescent", 0.03),
    ("First Quarter", 0.23),
    ("Waxing Gibbous", 0.27),
    ("Full Moon", 0.47),
    ("Waning Gibbous", 0.52),
    ("Last Quarter", 0.73),
    ("Waning Crescent", 0.77),
]


def moon_phase(dt: datetime) -> dict:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    known = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
    days = (dt - known).total_seconds() / 86400.0
    synodic = 29.53058867
    cycle = (days % synodic) / synodic
    illum = 0.5 * (1 - cos(2 * pi * cycle))
    name = next((n for n, t in reversed(PHASES) if cycle >= t), "New Moon")
    return {"phase": name, "illum": round(illum, 3), "cycle": round(cycle, 3)}
