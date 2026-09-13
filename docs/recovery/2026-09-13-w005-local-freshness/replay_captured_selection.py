"""One offline W005 evidence replay. No live provider or database calls."""
import asyncio
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SOURCE = REPO / 'services/external/nws.py'
spec = importlib.util.spec_from_file_location('w005_nws_snapshot_replay', SOURCE)
nws = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nws)

points = json.loads((HERE / 'nws-points-sample.json').read_text())
stations = json.loads((HERE / 'nws-stations-sample.json').read_text())
records = [json.loads(path.read_text()) for path in sorted(HERE.glob('nws-*-latest.json'))]
fixtures = {row['url']: row['payload'] for row in [stations, *records]}
snapshot_time = dt.datetime.fromisoformat(max(row['completed_at'] for row in records))
requests = []


class SnapshotDateTime(dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return snapshot_time.astimezone(tz or dt.timezone.utc)


async def recorded_get(url):
    requests.append(url)
    if url not in fixtures:
        raise AssertionError('Uncaptured provider request; replay cannot use the network: ' + url)
    return fixtures[url]


with patch.object(nws, '_get_json', recorded_get), \
     patch.object(nws, 'dt', SimpleNamespace(datetime=SnapshotDateTime, timezone=dt.timezone,
                                            timedelta=dt.timedelta)), \
     patch('httpx.AsyncClient', side_effect=AssertionError('Network prohibited in offline replay')):
    selected = asyncio.run(nws._station_latest_conditions(points['payload']))

public = json.loads((HERE / 'local-check-sample.json').read_text())['payload']['weather']
fields = ('temp_c', 'humidity_pct', 'pressure_hpa', 'obs_time')
assert all(selected[field] == public[field] for field in fields)
matching_stations = [row['payload']['properties'].get('stationId', row['url'].split('/stations/')[1].split('/')[0])
                     for row in records if nws._parse_obs_props(row['payload']['properties']) == selected]
assert len(requests) == 6  # One station list plus five latest observations.
result = {'replayed_at': dt.datetime.now(dt.timezone.utc).isoformat(),
          'source_path': str(SOURCE), 'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
          'captured_provider_time': snapshot_time.isoformat(), 'offline_replays': 1,
          'selected': selected, 'matching_station_candidates': matching_stations,
          'public_core_weather_fields_match': True, 'fixture_requests': requests,
          'live_requests': 0, 'database_access': False, 'passed': True,
          'limitation': 'Replays the captured provider set only; does not prove which station was available at earlier breach times.'}
(HERE / 'selection-replay-result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
