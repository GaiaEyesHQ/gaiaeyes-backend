import datetime as dt
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.space_visuals_ingest as svi


def test_parse_timestamp_defaults_naive_strings_to_utc():
    ts = svi._parse_timestamp("2024-11-16 04:20:00")
    assert ts.tzinfo == dt.timezone.utc
    assert ts.isoformat() == "2024-11-16T04:20:00+00:00"
