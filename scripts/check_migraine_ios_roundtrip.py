#!/usr/bin/env python3
"""Local-only current Swift source -> real backend normalization -> Swift check.

Uses no database, HTTP client, application startup or provider data. Keeps the
original review fixtures intact and writes generated evidence to --output.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.migraine.episode_contract import MigraineEpisode
from services.migraine.follow_up import apply_follow_up_patch


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    seed_path = ROOT / 'gaiaeyes-ios/ios/GaiaExporterTests/Fixtures/migraine_episode_detail.json'
    seed = json.loads(seed_path.read_text())
    medicine = seed['episode']['medicines'][0]
    medicine['notes'] = 'Existing medicine-specific note'
    medicine['taken_at']['original_time'] = '2026-09-07 23:45'
    medicine['taken_at']['timezone_source'] = 'provider'
    second = deepcopy(medicine)
    second.update(name='Second synthetic medicine', dose_amount='2.5', notes='Keep this second entry')
    second['taken_at']['utc'] = '2026-09-08T05:00:00.125000+00:00'
    second['taken_at']['original_time'] = '2026-09-08 00:00:00.125'
    seed['episode']['medicines'].append(second)
    sign = seed['episode']['early_signs'][0]
    sign.update(code='LIGHT_SENSITIVITY', notes='Keep sign metadata', reported_at=deepcopy(medicine['taken_at']))
    second_sign = deepcopy(sign)
    second_sign.update(label='Neck tension', code='NECK_TENSION', notes='Second sign note')
    seed['episode']['early_signs'].append(second_sign)
    base = MigraineEpisode.model_validate(seed['episode'])
    detail = {'revision': 2, 'changed': False, 'episode': base.model_dump(mode='json')}
    (out / 'backend-detail.json').write_text(json.dumps(detail, indent=2) + '\n')
    binary = out / 'ios-roundtrip-probe'
    subprocess.run(['xcrun', 'swiftc', str(ROOT / 'gaiaeyes-ios/ios/GaiaExporter/Models/MigraineEpisodeModels.swift'),
                    str(ROOT / 'tests/fixtures/migraine_episode_contract/ios_roundtrip_probe.swift'), '-o', str(binary)], check=True)
    subprocess.run([str(binary), 'emit', str(out)], check=True)
    results = []
    for case in json.loads((out / 'swift-requests.json').read_text()):
        request = case['request']
        assert request['expected_revision'] == 2
        episode = apply_follow_up_patch(base, request, request.keys(), revision=3,
                                        now=datetime(2026, 9, 8, 6, tzinfo=timezone.utc))
        results.append({'name': case['name'], 'request': request,
                        'detail': {'revision': 3, 'changed': True, 'episode': episode.model_dump(mode='json')}})
    (out / 'backend-roundtrips.json').write_text(json.dumps(results, indent=2) + '\n')
    subprocess.run([str(binary), 'verify', str(out)], check=True)


if __name__ == '__main__':
    main()
