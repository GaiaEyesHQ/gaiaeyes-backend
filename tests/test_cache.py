from decimal import Decimal

import pytest

from app.cache import FeatureCache


pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def test_feature_cache_serializes_decimal_values():
    cache = FeatureCache()
    user_id = "test-user"
    payload = {"value": Decimal("1.25"), "nested": {"score": Decimal("2.5")}}

    await cache.set(user_id, payload)

    restored = await cache.get(user_id)
    assert restored == {"value": 1.25, "nested": {"score": 2.5}}
