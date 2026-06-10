from pathlib import Path

import pytest
from fastapi import HTTPException

from app.routers.exposures import _normalize_exposure_key
from app.routers.feedback import _EXPOSURE_VALUES
from services.exposures.catalog import ALL_EXPOSURE_KEYS, EVERYDAY_EXPOSURE_KEYS


def test_exposure_api_accepts_everyday_diary_keys():
    for key in EVERYDAY_EXPOSURE_KEYS:
        assert _normalize_exposure_key(key) == key


def test_exposure_api_rejects_unknown_keys():
    with pytest.raises(HTTPException):
        _normalize_exposure_key("nearby_factory")


def test_exposure_migration_matches_backend_allowlist():
    migration = Path("supabase/migrations/20260610120000_expand_exposure_diary_v1.sql").read_text()

    for key in ALL_EXPOSURE_KEYS:
        assert f"'{key}'" in migration


def test_daily_checkin_feedback_accepts_same_exposure_keys():
    assert _EXPOSURE_VALUES == set(ALL_EXPOSURE_KEYS)
