"""Exercise the actual deployment helper against private synthetic directories."""
import hashlib
from pathlib import Path
import shutil
import subprocess

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/deploy_dashboard_pair.sh'
FILES = ('gaia-dashboard.php', 'gaia-dashboard.js')


@pytest.fixture
def deployment(tmp_path):
    upload = tmp_path / 'private upload'
    target_root = tmp_path / 'site with spaces/wp-content'
    target = target_root / 'mu-plugins'
    commands = tmp_path / 'commands'
    for folder in (upload, target, commands):
        folder.mkdir(parents=True)
    shutil.copyfile(SCRIPT, upload / SCRIPT.name)
    for file in FILES:
        (upload / file).write_text('new ' + file)
        (target / file).write_text('old ' + file)
        (target / file).chmod(0o640)
    (target / 'unrelated.php').write_text('preserve this')
    (commands / 'php').write_text('#!/bin/sh\nexit "${PHP_TEST_EXIT:-0}"\n')
    (commands / 'php').chmod(0o755)
    env = {'PATH': str(commands) + ':/usr/bin:/bin', 'SG_TARGET_PATH_PROD': str(target_root),
           'RELEASE_ID': '12345-1', 'PHP_SHA256': hashlib.sha256((upload / FILES[0]).read_bytes()).hexdigest(),
           'JS_SHA256': hashlib.sha256((upload / FILES[1]).read_bytes()).hexdigest()}
    return upload, target, commands, env


def run(deployment):
    upload, target, commands, env = deployment
    return subprocess.run(['bash', str(upload / SCRIPT.name)], env=env, capture_output=True, text=True)


def assert_original(target):
    for file in FILES:
        assert (target / file).read_text() == 'old ' + file
    assert (target / 'unrelated.php').read_text() == 'preserve this'


def test_installs_only_pair_keeps_backups_and_modes(deployment):
    upload, target, _, _ = deployment
    result = run(deployment)
    assert result.returncode == 0, result.stdout + result.stderr
    for file in FILES:
        assert (target / file).read_bytes() == (upload / file).read_bytes()
        assert (upload / 'backups' / file).read_text() == 'old ' + file
        assert (target / file).stat().st_mode & 0o777 == 0o640
    assert sorted(p.name for p in target.iterdir()) == sorted([*FILES, 'unrelated.php'])
    assert (target / 'unrelated.php').read_text() == 'preserve this'
    assert 'deployment=complete' in result.stdout
    assert run(deployment).returncode != 0  # An uncertain retry must be investigated.


@pytest.mark.parametrize('failure', ['checksum', 'short_checksum', 'php', 'symlink', 'staging_symlink', 'wrong_destination'])
def test_rejects_invalid_input_before_replacing_files(deployment, failure):
    upload, target, _, env = deployment
    if failure == 'checksum':
        env['JS_SHA256'] = '0' * 64
    elif failure == 'short_checksum':
        env['JS_SHA256'] = '0'
    elif failure == 'php':
        env['PHP_TEST_EXIT'] = '1'
    elif failure == 'symlink':
        (target / FILES[0]).rename(target / 'original.php')
        (target / FILES[0]).symlink_to(target / 'original.php')
    elif failure == 'staging_symlink':
        (target / ('.' + FILES[0] + '.' + env['RELEASE_ID'])).symlink_to(target / 'missing')
    else:
        env['SG_TARGET_PATH_PROD'] = str(target.parent.parent)
    assert run(deployment).returncode != 0
    assert_original(target)


def test_failure_between_replacements_restores_only_our_change(deployment):
    upload, target, commands, env = deployment
    real_mv = shutil.which('mv')
    assert real_mv
    (commands / 'mv').write_text('#!/bin/sh\ncase "$3" in */gaia-dashboard.js) exit 1;; esac\nexec "' + real_mv + '" "$@"\n')
    (commands / 'mv').chmod(0o755)
    assert run(deployment).returncode != 0
    assert_original(target)
    assert not (target / '.gaia-dashboard-pair.lock').exists()


def test_concurrent_unrelated_edit_is_preserved(deployment):
    _, target, commands, env = deployment
    real_mv = shutil.which('mv')
    assert real_mv
    env['TEST_TARGET'] = str(target)
    (commands / 'mv').write_text('#!/bin/sh\n"' + real_mv + '" "$@" || exit $?\ncase "$3" in */gaia-dashboard.php) printf other-edit > "$TEST_TARGET/gaia-dashboard.js";; esac\n')
    (commands / 'mv').chmod(0o755)
    result = run(deployment)
    assert result.returncode != 0
    assert (target / FILES[0]).read_text() == 'old ' + FILES[0]
    assert (target / FILES[1]).read_text() == 'other-edit'
    assert 'Concurrent change detected' in result.stdout
    assert (target / 'unrelated.php').read_text() == 'preserve this'
