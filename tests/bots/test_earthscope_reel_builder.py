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


def test_reel_vo_uses_caption_and_playbook_before_affects():
    row = {
        "caption": "Can't sleep even when your bed is perfect? Recovery may need a softer lane today.",
        "metrics_json": {
            "sections": {
                "affects": "Brain fog and lower HRV can show up when the background gets noisy.",
                "playbook": "- Take a five minute breathing reset\n- Keep evening light low",
            }
        },
    }

    vo_text = reel_builder.build_vo_text_from_post(row)

    assert "Can't sleep even when your bed is perfect?" in vo_text
    assert "Brain fog and lower HRV" not in vo_text
    assert "Try this today: Take a five minute breathing reset." in vo_text


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
    assert command[command.index("-t") + 1] == "2.200"


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
