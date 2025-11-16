import json
import pathlib
import sys

import pytest

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


def test_candidate_urls_prefers_raw_url():
    raw = "https://sos70.ru/wp-content/uploads/schumann-1024x512.jpg"
    urls = tomsk._candidate_urls(raw, "https://sos70.ru/?page_id=47")
    assert urls[0] == raw


def test_collect_wp_media_assets(monkeypatch):
    sample = [
        {
            "source_url": "https://sos70.ru/wp-content/uploads/schumann-01.jpg",
            "modified_gmt": "2024-12-30T12:00:00",
            "media_type": "image",
            "mime_type": "image/jpeg",
        },
        {"source_url": "https://sos70.ru/wp-content/uploads/file.pdf", "media_type": "file", "mime_type": "application/pdf"},
    ]

    calls = {}

    def fake_http_get(url):
        calls["url"] = url
        return json.dumps(sample).encode()

    monkeypatch.setattr(tomsk, "_http_get", fake_http_get)
    page = tomsk.TomskPage(
        slug="foo",
        url="https://sos70.ru/?page_id=47",
        label="Foo",
        feature_flags={"schumann_visual": True},
        wp_parent_id=47,
    )
    assets = tomsk._collect_wp_media_assets(page)
    assert len(assets) == 1
    assert assets[0][0].endswith("schumann-01.jpg")
    assert "wp-json" in calls["url"]


def test_parse_provider_listing_extracts_files():
    payload = b'<a href="provider.php?file=shm.jpg">shm</a><a href="provider.php?file=srf.jpg">srf</a>'
    files = tomsk._parse_provider_listing(payload)
    assert files == {"shm.jpg", "srf.jpg"}


def test_collect_provider_images(monkeypatch):
    listing_html = b'<a href="provider.php?file=foo.jpg">foo</a>'

    def fake_http_get(url):
        return listing_html

    def fake_download(urls, dest_dir, prefix):
        return urls[0], f"images/tomsk/{prefix}.jpg", None

    asset = tomsk.TomskProviderAsset(
        slug="foo_asset",
        file="foo.jpg",
        label="Foo",
        feature_flags={"schumann_visual": True},
        instrument="FooInst",
        credit="FooCredit",
    )

    monkeypatch.setattr(tomsk, "_http_get", fake_http_get)
    monkeypatch.setattr(tomsk, "_download_with_meta", fake_download)
    monkeypatch.setattr(tomsk, "TOMSK_PROVIDER_ASSETS", (asset,))

    assets = tomsk._collect_provider_images()
    assert len(assets) == 1
    provider_asset, source_url, rel_path, lm_dt = assets[0]
    assert provider_asset.file == "foo.jpg"
    assert source_url.endswith("file=foo.jpg")
    assert rel_path.endswith("foo_asset.jpg")
    assert lm_dt is None
