import sys
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bots.earthscope_post import reel_builder


def test_reel_card_order_matches_public_carousel_flow():
    assert reel_builder.PREFERRED_CARD_NAMES == [
        "daily_affects.jpg",
        "daily_playbook.jpg",
        "daily_stats.jpg",
    ]


def test_reel_fallback_accepts_uppercase_image_extensions(tmp_path):
    image = tmp_path / "fallback-card.PNG"
    image.write_bytes(b"placeholder")

    assert reel_builder.pick_card_images(tmp_path, 1) == [image]


def test_reel_story_uses_a_different_generated_background_for_each_beat(tmp_path):
    for name in reel_builder.STORY_BACKGROUND_NAMES:
        (tmp_path / name).write_bytes(b"placeholder")

    backgrounds = reel_builder.pick_story_backgrounds(tmp_path, 4)

    assert [path.name for path in backgrounds] == reel_builder.STORY_BACKGROUND_NAMES
    assert len(set(backgrounds)) == 4


def test_reel_story_never_falls_back_to_finished_cards(tmp_path):
    for name in ("daily_affects.jpg", "daily_caption.jpg", "daily_playbook.jpg", "daily_stats.jpg"):
        (tmp_path / name).write_bytes(b"finished-card")

    assert reel_builder.pick_story_backgrounds(tmp_path, 4) == []


def test_reel_vo_uses_hook_signal_and_effects_without_playbook():
    row = {
        "caption": "Can't sleep even when your bed is perfect? Recovery may need a softer lane today.",
        "metrics_json": {
            "sections": {
                "snapshot": "Solar wind is elevated today. Magnetic conditions are shifting.",
                "affects": "Brain fog and lower HRV can show up when the background gets noisy.",
                "playbook": "- Take a five minute breathing reset\n- Keep evening light low",
            }
        },
    }

    vo_text = reel_builder.build_vo_text_from_post(row)

    assert "Can't sleep even when your bed is perfect?" in vo_text
    assert "Solar wind is elevated today." in vo_text
    assert "Brain fog and lower HRV" in vo_text
    assert "five minute breathing reset" not in vo_text


def test_reel_vo_prefers_explicit_short_caption():
    row = {
        "short_caption": "Start softer today.",
        "caption": "Can't sleep even when your bed is perfect? Recovery may need a softer lane today.",
        "metrics_json": {
            "sections": {
                "affects": "Brain fog can show up.",
                "playbook": "- Take a reset",
            }
        },
    }

    assert reel_builder.build_vo_text_from_post(row) == "Start softer today."


def test_reel_vo_prefers_generated_sections_voiceover():
    row = {
        "caption": "Take short movement breaks and sip water today.",
        "metrics_json": {
            "sections": {
                "voiceover": "Body buzzing for no clear reason? Try slow breathing first.",
                "playbook": "- Take a reset",
            }
        },
    }

    assert reel_builder.build_vo_text_from_post(row).startswith("Body buzzing")


def test_reel_audio_db_helper_normalizes_gain():
    assert reel_builder._audio_db("-8dB") == "-8dB"
    assert reel_builder._audio_db("-7") == "-7dB"
    assert reel_builder._audio_db("nope") == "-9dB"


def test_reel_hook_prefers_stored_title():
    row = {
        "title": "Body buzzing for no clear reason?",
        "caption": "A different caption opening should not replace the selected title.",
    }

    assert reel_builder.hook_text_from_post(row) == "Body buzzing for no clear reason?"


def test_reel_story_prefers_structured_writer_payload():
    row = {
        "title": "Fallback hook",
        "metrics_json": {
            "sections": {
                "snapshot": "Fallback signal.",
                "affects": "Fallback effects.",
                "reel_story": {
                    "hook": "Body buzzing for no clear reason?",
                    "signal": "Solar wind is elevated",
                    "effects": "Restless or jittery\nEnergy may spike, then dip",
                    "pattern": "An uneven-energy day",
                },
            }
        },
    }

    story = reel_builder.reel_story_from_post(row)

    assert story["hook"] == "Body buzzing for no clear reason?"
    assert story["signal"] == "Solar wind is elevated"
    assert story["effects"].splitlines() == ["Restless or jittery", "Energy may spike, then dip"]


def test_reel_story_rejects_stored_fragments_and_duplicate_variants():
    row = {
        "title": "Headache threshold lower today?",
        "metrics_json": {
            "sections": {
                "snapshot": "Geomagnetic signals are a touch unsettled with a southward tilt.",
                "affects": (
                    "Headache and migraine sensitivity may be a bit higher for some. "
                    "Focus can come in short bursts with quicker dips."
                ),
                "reel_story": {
                    "hook": "Headache threshold lower today?",
                    "signal": "Geomagnetic signals are a touch unsettled with a",
                    "effects": "Headache and migraine sensitivity may be",
                    "pattern": "Headache and migraine sensitivity may be a",
                },
            }
        },
    }

    story = reel_builder.reel_story_from_post(row)

    assert story["signal"] == "Geomagnetic signals are a touch unsettled with a southward tilt."
    assert story["effects"] == "Headache and migraine sensitivity may be a bit higher for some."
    assert story["pattern"] == "Focus can come in short bursts with quicker dips."


def test_reel_hook_card_is_vertical_and_hides_dense_source_copy(tmp_path):
    source = tmp_path / "daily_affects.jpg"
    Image.new("RGB", (1080, 1920), (35, 110, 85)).save(source)

    output = reel_builder.build_hook_card(
        source,
        tmp_path / "hook.jpg",
        "Body buzzing for no clear reason?",
    )

    with Image.open(output) as rendered:
        assert rendered.size == (1080, 1920)
        assert rendered.getbbox() is not None


def test_reel_story_card_is_vertical_and_readable(tmp_path):
    source = tmp_path / "daily_affects.jpg"
    Image.new("RGB", (1080, 1920), (35, 110, 85)).save(source)

    output = reel_builder.build_story_card(
        source,
        tmp_path / "signal.jpg",
        "What changed",
        "Solar wind is elevated",
    )

    with Image.open(output) as rendered:
        assert rendered.size == (1080, 1920)
        assert rendered.getbbox() is not None


def test_reel_opening_clip_uses_motion_from_frame_one(monkeypatch, tmp_path):
    captured = []
    monkeypatch.setattr(reel_builder, "run", captured.append)

    reel_builder.build_still_clip(
        tmp_path / "hook.jpg",
        tmp_path / "hook.mp4",
        reel_builder.HOOK_CLIP_DUR,
        motion=True,
    )

    command = captured[0]
    video_filter = command[command.index("-vf") + 1]
    assert "zoompan" in video_filter
    assert "d=1" in video_filter
    assert command[command.index("-framerate") + 1] == "30"
    assert command[command.index("-t") + 1] == "2.300"


def test_reel_crossfade_respects_short_hook_duration(monkeypatch, tmp_path):
    captured = []
    monkeypatch.setattr(reel_builder, "run", captured.append)
    clips = [tmp_path / f"clip-{index}.mp4" for index in range(3)]

    reel_builder.xfade_concat(
        clips,
        tmp_path / "out.mp4",
        [2.2, 5.4, 5.4],
        0.25,
    )

    command = captured[0]
    filters = command[command.index("-filter_complex") + 1]
    assert "offset=1.950" in filters
    assert "offset=7.100" in filters
