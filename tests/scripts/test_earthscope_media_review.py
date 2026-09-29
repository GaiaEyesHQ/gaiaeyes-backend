"""Focused review boundary checks; no model, database, network or rendering."""
import ast
from pathlib import Path
from unittest.mock import Mock
import subprocess
import pytest
import yaml
from services import earthscope_local_primary

ROOT = Path(__file__).resolve().parents[2]

def runner(monkeypatch, tmp_path, primary, voice=False):
    tree = ast.parse((ROOT / 'bots/earthscope_post/reel_builder.py').read_text())
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
    ns = dict(REEL_REQUIRE_VO=False, REEL_VOICE_ENABLED=voice,
              which_ffmpeg=Mock(), IMAGES_DIR=tmp_path, REEL_OUT_PATH=tmp_path/'out.mp4',
              env_get=lambda *a: None, pick_story_backgrounds=Mock(side_effect=RuntimeError('render boundary')))
    loader = Mock(return_value=primary)
    monkeypatch.setattr(earthscope_local_primary, 'load_primary_post', loader)
    exec(compile(ast.Module(body=[main], type_ignores=[]), '<reel-main>', 'exec'), ns)
    return ns, loader

@pytest.mark.parametrize('review', [False, True])
def test_review_permission_is_explicit(monkeypatch, tmp_path, review):
    ns, loader = runner(monkeypatch, tmp_path, {'day': '2026-09-29'})
    with pytest.raises(RuntimeError, match='render boundary'):
        ns['main'](review_only=review)
    loader.assert_called_once_with(allow_review=review)

def test_review_cannot_fall_back_to_legacy(monkeypatch, tmp_path):
    ns, loader = runner(monkeypatch, tmp_path, None)
    with pytest.raises(SystemExit, match='exact local-primary artifact'):
        ns['main'](review_only=True)
    ns['pick_story_backgrounds'].assert_not_called()

def test_review_refuses_model_voice_before_work(monkeypatch, tmp_path):
    ns, loader = runner(monkeypatch, tmp_path, {}, voice=True)
    with pytest.raises(SystemExit, match='no model calls'):
        ns['main'](review_only=True)
    loader.assert_not_called()
    ns['which_ffmpeg'].assert_not_called()

def test_hosted_review_has_no_generation_or_publication_capabilities():
    source = (ROOT/'.github/workflows/earthscope_media_review.yml').read_text()
    workflow = yaml.safe_load(source)
    assert workflow['permissions'] == {'contents': 'read', 'actions': 'read'}
    for forbidden in ('OPENAI_API_KEY', 'DATABASE_URL', 'DSN', 'SERVICE_ROLE_KEY',
                      'meta_poster', 'upload_earthscope_images', 'git push'):
        assert forbidden not in source
    for step in workflow['jobs']['media']['steps']:
        if 'run' in step:
            assert '${{' not in step['run']
            subprocess.run(['bash', '-n'], input=step['run'], text=True, check=True)
    assert 'load_primary_post(allow_review=True)' in source
    assert "receipt['post_sha256'] == sha256(post)" in source
    assert "receipt['writer_source']['outcome_sha256'] == expected" in source
