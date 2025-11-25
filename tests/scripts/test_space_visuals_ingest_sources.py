import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from scripts import space_visuals_ingest as svi


class DummyResp:
    def __init__(self, status_code=200, content_type="image/jpeg"):
        self.status_code = status_code
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception("error")


def test_probe_url_prefers_head(monkeypatch):
    calls = []

    def fake_head(url, timeout=0, allow_redirects=True):
        calls.append(("head", url))
        return DummyResp(status_code=200)

    def fake_get(url, timeout=0, allow_redirects=True):
        calls.append(("get", url))
        return DummyResp(status_code=200)

    monkeypatch.setattr(svi.requests, "head", fake_head)
    monkeypatch.setattr(svi.requests, "get", fake_get)

    assert svi.probe_url("https://primary.example/image.jpg")
    assert calls[0] == ("head", "https://primary.example/image.jpg")


def test_probe_and_select_fallback(monkeypatch):
    def fake_head(url, timeout=0, allow_redirects=True):
        if "primary" in url:
            return DummyResp(status_code=500)
        return DummyResp(status_code=200)

    def fake_get(url, timeout=0, allow_redirects=True):
        if "primary" in url:
            return DummyResp(status_code=404)
        return DummyResp(status_code=200, content_type="image/png")

    monkeypatch.setattr(svi.requests, "head", fake_head)
    monkeypatch.setattr(svi.requests, "get", fake_get)

    chosen = svi.probe_and_select([
        "https://primary.example/latest.jpg",
    ], [
        "https://fallback.example/latest.jpg",
    ])

    assert chosen == "https://fallback.example/latest.jpg"


def test_select_solar_imagery_prefers_193_family(monkeypatch):
    monkeypatch.setenv("AIA_PRIMARY_URLS", "https://swpc.example/latest_0193.jpg")
    monkeypatch.setenv("AIA_193_FALLBACK_URLS", "https://sdo.example/latest_0193.jpg")
    monkeypatch.setenv("AIA_304_URLS", "https://swpc.example/latest_0304.jpg")
    monkeypatch.setenv("AIA_304_FALLBACK_URLS", "https://sdo.example/latest_0304.jpg")
    monkeypatch.setenv("HMI_INTENSITY_URLS", "https://swpc.example/latest_HMIIC.jpg")
    monkeypatch.setenv("HMI_INTENSITY_FALLBACK_URLS", "https://sdo.example/latest_HMIIC.jpg")

    calls = []

    def fake_probe(primary, secondary):
        calls.append((primary, secondary))
        # Simulate primary probe failure to force fallback selection
        return secondary[0] if secondary else None

    monkeypatch.setattr(svi, "probe_and_select", fake_probe)

    sources = svi.select_solar_imagery_sources()

    assert sources["aia_primary_url"] == "https://sdo.example/latest_0193.jpg"
    assert calls[0] == (
        ["https://swpc.example/latest_0193.jpg"],
        ["https://sdo.example/latest_0193.jpg"],
    )
