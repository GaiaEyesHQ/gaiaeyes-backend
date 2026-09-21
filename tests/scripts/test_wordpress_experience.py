import json
from pathlib import Path
import re
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
HARNESS = ROOT / 'tests/fixtures/wordpress_experience.php'


def render(scenario='current', view='home'):
    result = subprocess.run(['php', str(HARNESS), scenario, view], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert not result.stderr, result.stderr
    return json.loads(result.stdout)


@pytest.mark.parametrize('view', ['space', 'space-reverse'])
def test_space_uses_one_cached_history_request_and_one_ordered_chart_bundle(view):
    result = render(view=view)
    requests = [x for x in result['requests'] if '/v1/space/history?' in x['url']]
    assert len(requests) == 1
    assert 'hours=24' in requests[0]['url']
    assert requests[0]['headers']['Authorization'] == 'Bearer fixture-server-secret'
    assert list(result['scripts']) == ['gaiaeyes-chart', 'gaiaeyes-chart-date-adapter']
    adapter = result['scripts']['gaiaeyes-chart-date-adapter']
    assert adapter['deps'] == ['gaiaeyes-chart']
    assert '@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js' in adapter['src']
    assert result['footer'].index('gaiaeyes-chart.js') < result['footer'].index('gaiaeyes-chart-date-adapter.js') < result['footer'].index('window.GaiaSpark =')
    assert 'rtsw_mag' not in result['html'] and 'mag-1-day' not in result['html']
    assert 'chart.umd' not in result['html'] and 'chartjs-adapter' not in result['html']
    assert 'fixture-server-secret' not in result['html'] + result['footer']


@pytest.mark.parametrize('scenario,state,text', [
    ('current','current','Current edition'),
    ('stale','stale','Earlier edition'),
    ('unknown','unknown','Publication day unavailable'),
    ('api-day-missing','unknown','Publication day unavailable'),
])
def test_earthscope_dates_only_its_own_edition(scenario, state, text):
    html = render(scenario)['html'].split('<section class="gaia-sw">')[0]
    assert f'data-state="{state}"' in html and text in html
    assert 'Your Body Today' not in html and '>Now<' not in html
    if scenario == 'api-day-missing':
        assert '>Published' not in html and ' · Edition ' not in html


def test_missing_summary_is_explicit_and_never_turns_missing_bz_northward():
    html = render('missing')['html']
    assert 'EarthScope is unavailable' in html
    assert 'Space Weather: unavailable' in html
    assert 'northward' not in html


@pytest.mark.parametrize('scenario,state', [('current','current'), ('stale','stale'), ('missing','unavailable')])
def test_history_current_stale_and_missing_states(scenario, state):
    html = render(scenario, 'space')['html']
    for key, label in [('bz','IMF Bz'),('sw','Solar wind speed')]:
        panel = html.split(f'data-history="{key}"')[1].split('</canvas>')[0]
        assert f'data-state="{state}"' in panel
        assert f'{label} history:' in panel
        assert ('hidden' in panel) == (scenario == 'missing')
    if scenario != 'missing':
        assert '0.0 nT' in html
        assert '363 km/s' in html


def test_null_samples_do_not_become_zero_and_valid_zero_remains():
    data = render(view='contract')
    assert len(data['series']['bz']) == 1 and data['series']['bz'][0][1] == 0
    assert 'Time unavailable' in data['invalid_time']
    assert 'ahead of the current time' in data['future_time']
    html = render('partial', 'space')['html']
    assert 'IMF Bz history: Unavailable' in html
    assert 'Solar wind speed history: Current snapshot' in html
    assert 'id="sparkBzVal">—' in html


def test_history_works_even_if_features_endpoint_missing():
    html = render('no-features', 'space')['html']
    assert '363 km/s' in html and '0.0 nT' in html
    assert 'Solar wind: Current snapshot' in html


def test_api_feature_values_without_observation_time_are_not_stamped_now():
    html = render('no-history', 'space')['html']
    assert 'Solar wind: Time unavailable' in html
    assert 'IMF Bz history: Unavailable' in html
    assert '324 km/s' in html


@pytest.mark.parametrize('view', ['aurora-theme','aurora-fallback'])
def test_photo_deep_link_is_unique_focusable_and_outside_tabs(view):
    html = render(view=view)['html']
    assert html.count('id="photo-tips"') == 1
    assert 'aria-labelledby="ga-aurora-photo-tips-title" tabindex="-1"' in html
    assert html.index('id="photo-tips"') > html.rindex('role="tabpanel"')
    assert 'data-target="nowcast" aria-selected="true"' in html
    assert 'data-target="tonight" aria-selected="false"' in html
    assert 'data-target="tomorrow" aria-selected="false"' in html
    assert 'ISO 1600–3200' in html
    assert len(re.findall(r'<script>', html)) == 1
