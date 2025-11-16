import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.tomsk_visuals_ingest as tomsk


def test_parser_collects_background_image():
    parser = tomsk._ImageHTMLParser()
    html = "<div style=\"background-image:url('/wp-content/uploads/foo-1024x724.png');\"></div>"
    parser.feed(html)
    assert "/wp-content/uploads/foo-1024x724.png" in parser.candidates
    urls = tomsk._candidate_urls(parser.candidates[0], "https://sos70.ru/?page_id=47")
    assert "https://sos70.ru/wp-content/uploads/foo-1024x724.png" in urls


def test_regex_image_candidates_finds_inline_urls():
    html = "var img='https://cdn.sos70.ru/assets/bar-chart.jpeg?ver=2';"
    matches = tomsk._regex_image_candidates(html)
    assert matches == ["https://cdn.sos70.ru/assets/bar-chart.jpeg?ver=2"]
