from datetime import UTC, datetime
import pytest
from psycopg.errors import UndefinedTable
from app.routers import symptoms as router
from services.migraine.history import HistoryChanged
from test_symptoms import client, override_db_dependency, override_dev_bearer

HEADERS = {'Authorization': 'Bearer test-token', 'X-Dev-UserId': '90000000-0000-4000-8000-000000000001'}
PARAMS = {'start': '2026-09-01T00:00:00Z', 'end': '2026-10-01T00:00:00Z'}
PATH = '/v1/symptoms/migraine/history'


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.mark.anyio
async def test_disabled_and_input_validation(client, monkeypatch):
    monkeypatch.delenv('GAIA_MIGRAINE_CALENDAR_ENABLED', raising=False)
    assert (await client.get(PATH, params=PARAMS, headers=HEADERS)).status_code == 503
    monkeypatch.setenv('GAIA_MIGRAINE_CALENDAR_ENABLED', '1')
    for params in [{**PARAMS, 'start': '2026-09-01'}, {**PARAMS, 'limit': 101},
                   {**PARAMS, 'end': PARAMS['start']}, {**PARAMS, 'cursor': 'bad!'}]:
        assert (await client.get(PATH, params=params, headers=HEADERS)).status_code == 422
    assert (await client.get(PATH, params=PARAMS)).status_code in (401, 403)


@pytest.mark.anyio
@pytest.mark.parametrize('error,status', [(HistoryChanged('refresh'),409), (UndefinedTable('missing'),503), (RuntimeError('private DB detail'),500)])
async def test_failures_never_become_empty_success(client, monkeypatch, error, status):
    monkeypatch.setenv('GAIA_MIGRAINE_CALENDAR_ENABLED', '1')
    async def fail(*args, **kwargs): raise error
    monkeypatch.setattr(router, 'read_history', fail)
    response = await client.get(PATH, params=PARAMS, headers=HEADERS)
    assert response.status_code == status
    assert 'items' not in response.json() and 'private DB detail' not in response.text


@pytest.mark.anyio
async def test_route_uses_authenticated_scope_and_returns_page(client, monkeypatch):
    monkeypatch.setenv('GAIA_MIGRAINE_CALENDAR_ENABLED', '1')
    async def read(conn, user_id, **kwargs):
        assert user_id == HEADERS['X-Dev-UserId']
        assert kwargs['start'] == datetime(2026,9,1,tzinfo=UTC)
        return {'items': [], 'complete': True, 'next_cursor': None}
    monkeypatch.setattr(router, 'read_history', read)
    response = await client.get(PATH, params=PARAMS, headers=HEADERS)
    assert response.status_code == 200 and response.json()['data']['complete']
