"""Local orchestration checks: synthetic inputs, no HTTP or ffmpeg execution."""

import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bots.earthscope_post import reel_builder as reel


@pytest.fixture
def audio_run(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TARGET_DAY", "2026-09-15")
    monkeypatch.setenv("REEL_VO_TAIL_PAD_SEC", "0.8")
    monkeypatch.delenv("REEL_DURATION_SEC", raising=False)
    images = tmp_path / "images"
    images.mkdir()
    for name in [*reel.STORY_BACKGROUND_NAMES, "daily_stats.jpg"]:
        (images / name).write_bytes(b"synthetic card")
    scratch = tmp_path / "tmp_reel"
    scratch.mkdir()
    (scratch / "vo.wav").write_bytes(b"STALE NARRATION")
    (scratch / "bed.wav").write_bytes(b"STALE MUSIC")
    state = SimpleNamespace(commands=[], timeouts=[], gets=[], tts=[], clips=[], cards=[], scratch=scratch)

    def capture_command(command, *, timeout=None):
        state.commands.append(command)
        state.timeouts.append(timeout)

    def forbidden(*args, **kwargs):
        raise AssertionError("Unexpected narration, network, or media execution")

    def response(url, **kwargs):
        state.gets.append(url)
        return SimpleNamespace(status_code=200, content=b"synthetic music", text="")

    def card(background, out, *text):
        state.cards.append((background, out, text))
        out.write_bytes(b"synthetic rendered card")
        return out

    def clip(image, out, duration, fps, motion):
        state.clips.append((image, out, duration, motion))

    monkeypatch.setattr(reel, "IMAGES_DIR", images)
    monkeypatch.setattr(reel, "REEL_OUT_PATH", tmp_path / "reel.mp4")
    monkeypatch.setattr(reel, "OPENAI_API_KEY", "synthetic-key-is-present")
    monkeypatch.setattr(reel, "REEL_VOICE_ENABLED", False)
    monkeypatch.setattr(reel, "REEL_REQUIRE_VO", False)
    monkeypatch.setattr(reel, "REEL_BED_URL", "https://example.invalid/social/audio/beds/bed01.wav")
    monkeypatch.setattr(reel, "SUPABASE_AUDIO_BASE", "https://example.invalid/social/audio")
    monkeypatch.setattr(reel, "REEL_MOOD", "calm")
    monkeypatch.setattr(reel, "REEL_MUSIC_VOLUME_DB", "-9")
    monkeypatch.setattr(reel, "which_ffmpeg", lambda: "synthetic-ffmpeg")
    monkeypatch.setattr(reel, "fetch_post_for_day", lambda *args: {})
    monkeypatch.setattr(reel, "reel_story_from_post", lambda row: {
        "hook": "Synthetic readable hook",
        "signal": "Synthetic why-today statement.",
        "effects": "Synthetic effect statement.",
    })
    monkeypatch.setattr(reel, "build_hook_card", card)
    monkeypatch.setattr(reel, "build_story_card", card)
    monkeypatch.setattr(reel, "build_still_clip", clip)
    monkeypatch.setattr(reel, "xfade_concat", lambda *args: None)
    monkeypatch.setattr(reel, "run", capture_command)
    monkeypatch.setattr(reel, "resolve_caption", forbidden)
    monkeypatch.setattr(reel, "resolve_vo_text", forbidden)
    monkeypatch.setattr(reel, "guess_vo_text", forbidden)
    monkeypatch.setattr(reel, "tts_to_wav", forbidden)
    monkeypatch.setattr(reel, "probe_duration_seconds", forbidden)
    monkeypatch.setattr(reel.requests, "get", response)
    monkeypatch.setattr(reel.requests, "post", forbidden)
    monkeypatch.setattr(reel.requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(reel.subprocess, "run", forbidden)
    return state


def test_disabled_voice_with_key_skips_all_narration_and_muxes_existing_bed(audio_run):
    reel.main()

    assert audio_run.gets == [reel.REEL_BED_URL]
    assert not (audio_run.scratch / "vo.wav").exists()
    assert (audio_run.scratch / "bed.wav").read_bytes() == b"synthetic music"
    assert len(audio_run.commands) == 1
    command = audio_run.commands[0]
    assert [command[i + 1] for i, item in enumerate(command) if item == "-i"] == [
        "tmp_reel/video_no_audio.mp4", "tmp_reel/bed.wav",
    ]
    assert command[command.index("-stream_loop") + 1] == "-1"
    filters = command[command.index("-filter_complex") + 1]
    assert "loudnorm=I=-18:TP=-1.5:LRA=7,aresample=44100" in filters
    assert "volume=" not in filters and "afade=t=out" in filters
    assert audio_run.timeouts == [180]
    assert "sidechaincompress" not in filters and "amix" not in filters
    assert command[command.index("-c:a") + 1] == "aac"
    assert "-an" not in command
    # Narration cannot stretch the music-only card cadence, even with stale VO.
    assert [clip[2] for clip in audio_run.clips] == [2.5, 3.6, 3.6, 4.0]
    assert command[command.index("-t") + 1] == "12.950"
    assert len(audio_run.cards) == 3
    assert audio_run.clips[-1][0].name == "daily_stats.jpg"


@pytest.mark.parametrize("gain", ["-30", "12"])
def test_intentional_music_only_does_not_apply_narration_bed_gain(monkeypatch, audio_run, gain):
    monkeypatch.setattr(reel, "REEL_MUSIC_VOLUME_DB", gain)
    reel.main()
    command = audio_run.commands[0]
    filters = command[command.index("-filter_complex") + 1]
    assert "loudnorm=I=-18:TP=-1.5:LRA=7" in filters
    assert "volume=" not in filters
    assert audio_run.timeouts == [180]


@pytest.mark.parametrize("track_key", ["url", "file"])
def test_manifest_mood_selection_remains_available_without_explicit_bed(monkeypatch, audio_run, track_key):
    monkeypatch.setattr(reel, "REEL_BED_URL", None)
    tracks = [
        {"mood": "tense", "url": "other.wav"},
        {"mood": "calm", track_key: "bed01.wav"},
    ]

    def get(url, **kwargs):
        audio_run.gets.append(url)
        return SimpleNamespace(status_code=200, content=b"selected music", json=lambda: tracks)

    monkeypatch.setattr(reel.requests, "get", get)
    reel.main()

    assert audio_run.gets == [
        "https://example.invalid/social/audio/tracks.json",
        "https://example.invalid/social/audio/bed01.wav",
    ]
    assert "tmp_reel/bed.wav" in audio_run.commands[0]


@pytest.mark.parametrize("status,content", [(404, b""), (200, b"")])
def test_music_only_rejects_missing_or_empty_bed_without_stale_audio(monkeypatch, audio_run, status, content):
    monkeypatch.setattr(reel.requests, "get", lambda *args, **kwargs:
                        SimpleNamespace(status_code=status, content=content, text="synthetic failure"))
    with pytest.raises(SystemExit, match="Music-only reel requires"):
        reel.main()
    assert audio_run.commands == []
    assert not (audio_run.scratch / "vo.wav").exists()
    assert not (audio_run.scratch / "bed.wav").exists() or (audio_run.scratch / "bed.wav").stat().st_size == 0


def enable_narration(monkeypatch, state, outcomes):
    monkeypatch.setattr(reel, "REEL_VOICE_ENABLED", True)
    monkeypatch.setattr(reel, "REEL_TTS_MODEL", "synthetic-primary")
    monkeypatch.setattr(reel, "REEL_TTS_FALLBACK_MODEL", "synthetic-fallback")
    monkeypatch.setattr(reel, "resolve_caption", lambda **kwargs: "A synthetic caption kept available for narration.")
    monkeypatch.setattr(reel, "resolve_vo_text", lambda **kwargs: "A synthetic voiceover with enough text for the existing narration path.")
    monkeypatch.setattr(reel, "probe_duration_seconds", lambda path: 20.0)

    def tts(text, out, **kwargs):
        state.tts.append((text, kwargs))
        assert not out.exists()  # The previous run's VO was cleared before TTS.
        ok = outcomes[len(state.tts) - 1]
        if ok:
            out.write_bytes(b"synthetic current narration")
        return ok

    monkeypatch.setattr(reel, "tts_to_wav", tts)


@pytest.mark.parametrize("outcomes", [[True], [False, True]])
def test_enabled_narration_retains_primary_fallback_ducking_and_duration(monkeypatch, audio_run, outcomes):
    enable_narration(monkeypatch, audio_run, outcomes)
    reel.main()

    assert len(audio_run.tts) == len(outcomes)
    assert audio_run.tts[0][1]["model"] == "synthetic-primary"
    if len(outcomes) == 2:
        assert audio_run.tts[1][1]["model"] == "synthetic-fallback"
    assert all(call[1]["api_key"] == "synthetic-key-is-present" for call in audio_run.tts)
    command = audio_run.commands[0]
    assert "tmp_reel/vo.wav" in command
    filters = command[command.index("-filter_complex") + 1]
    assert "sidechaincompress" in filters and "volume=-9dB" in filters
    assert "loudnorm" not in filters
    assert audio_run.timeouts == [None]
    assert command[command.index("-t") + 1] == "20.800"
    assert audio_run.clips[4][2] == 2.5  # Fast hook survives the VO extension.


@pytest.mark.parametrize("gain", ["-15", "3"])
def test_enabled_optional_narration_failure_keeps_music_without_stale_voice(monkeypatch, audio_run, gain):
    enable_narration(monkeypatch, audio_run, [False, False])
    monkeypatch.setattr(reel, "REEL_MUSIC_VOLUME_DB", gain)
    reel.main()
    assert len(audio_run.tts) == 2
    assert not (audio_run.scratch / "vo.wav").exists()
    assert "tmp_reel/vo.wav" not in audio_run.commands[0]
    assert "tmp_reel/bed.wav" in audio_run.commands[0]
    command = audio_run.commands[0]
    filters = command[command.index("-filter_complex") + 1]
    assert f"volume={gain}dB" in filters and "loudnorm" not in filters
    assert audio_run.timeouts == [None]


def test_command_timeout_reaches_subprocess(monkeypatch):
    calls = []
    monkeypatch.setattr(reel.subprocess, "run", lambda *args, **kwargs: calls.append((args, kwargs)))
    reel.run(["synthetic-ffmpeg"], timeout=180)
    assert calls == [((["synthetic-ffmpeg"],), {"check": True, "timeout": 180})]


def test_enabled_required_narration_still_fails_on_tts_failure(monkeypatch, audio_run):
    enable_narration(monkeypatch, audio_run, [False, False])
    monkeypatch.setattr(reel, "REEL_REQUIRE_VO", True)
    with pytest.raises(SystemExit, match="VO required but TTS failed"):
        reel.main()
    assert len(audio_run.tts) == 2
    assert audio_run.commands == []


def test_enabled_without_api_key_does_not_call_tts(monkeypatch, audio_run):
    enable_narration(monkeypatch, audio_run, [])
    monkeypatch.setattr(reel, "OPENAI_API_KEY", None)
    reel.main()
    assert audio_run.tts == []
    assert "tmp_reel/vo.wav" not in audio_run.commands[0]


def test_conflicting_required_voice_stops_before_any_work(monkeypatch, audio_run):
    monkeypatch.setattr(reel, "REEL_REQUIRE_VO", True)
    with pytest.raises(SystemExit, match="conflicts"):
        reel.main()
    assert audio_run.gets == [] and audio_run.clips == [] and audio_run.commands == []


@pytest.mark.parametrize("setting,expected", [("0", False), ("1", True), (None, True)])
def test_voice_switch_loads_explicit_env_and_preserves_other_callers_default(monkeypatch, setting, expected):
    if setting is None:
        monkeypatch.delenv("REEL_VOICE_ENABLED", raising=False)
    else:
        monkeypatch.setenv("REEL_VOICE_ENABLED", setting)
    namespace = runpy.run_path(str(ROOT / "bots/earthscope_post/reel_builder.py"))
    assert namespace["REEL_VOICE_ENABLED"] is expected


def test_daily_workflow_selects_music_only_without_removing_writer_key():
    workflow = yaml.safe_load((ROOT / ".github/workflows/gaia_eyes_daily.yml").read_text())
    job = workflow["jobs"]["reel"]
    assert job["env"]["REEL_VOICE_ENABLED"] == "0"
    build = next(step for step in job["steps"] if step.get("name") == "Build reel (reel_builder.py)")
    assert build["env"]["REEL_REQUIRE_VO"] == "0"
    assert build["env"]["REEL_BED_URL"].endswith("/social/audio/beds/bed01.wav")
    assert "--bed-url" not in build["run"] and "--out" not in build["run"]
    assert "python reel_builder.py" in build["run"]
    assert workflow["jobs"]["generate"]["env"]["OPENAI_API_KEY"] == "${{ secrets.OPENAI_API_KEY }}"
    assert "REEL_VOICE_ENABLED" not in workflow["jobs"]["generate"]["env"]
