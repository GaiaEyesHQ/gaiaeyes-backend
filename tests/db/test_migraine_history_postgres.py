from datetime import UTC, datetime, timedelta
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from app.db.symptoms import fetch_migraine_episode_range
from services.migraine.history import HistoryChanged, read_history
from test_migraine_postgres_integration import _connect, _reset, _insert_parent, USER_A, USER_B


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def conn():
    conn = await _connect()
    await _reset(conn)
    # Existing production migration index, absent from the minimal old fixture.
    await conn.execute("create index if not exists user_symptom_episodes_user_started_idx on raw.user_symptom_episodes(user_id, started_at desc)")
    try:
        yield conn
    finally:
        await conn.close()


START = datetime(2026, 9, 1, tzinfo=UTC)
END = datetime(2026, 10, 1, tzinfo=UTC)


async def episode(conn, start=START, *, end=None, user=USER_A, state="ongoing", id=None):
    id = id or uuid4()
    await _insert_parent(conn, user_id=user, episode_id=id, event_id=uuid4(), start=start, source="g012_synthetic")
    await conn.execute("update raw.user_symptom_episodes set current_state=%s, resolution_ts=%s where id=%s", (state, end, id))
    return str(id)


@pytest.mark.anyio
async def test_over_80_episodes_tied_boundaries_updates_ownership_and_pages(conn):
    expected = []
    for i in range(105):
        id = await episode(conn, START + timedelta(hours=i // 8), id=UUID(int=i + 1))
        expected.append(id)
        for _ in range(2):
            await conn.execute("insert into raw.user_symptom_episode_updates(episode_id,user_id,update_kind) values(%s,%s,'note')", (id, USER_A))
    await episode(conn, user=USER_B)
    seen, cursor, snapshots = [], None, set()
    while True:
        page = await read_history(conn, USER_A, start=START, end=END, limit=13, cursor=cursor)
        seen += [row['id'] for row in page['items']]
        snapshots.add(page['snapshot'])
        cursor = page['next_cursor']
        assert page['complete'] == (cursor is None)
        if cursor is None:
            break
    assert seen == list(reversed(expected))
    assert len(set(seen)) == 105 and len(snapshots) == 1
    empty = await read_history(conn, USER_B, start=START - timedelta(days=62), end=START)
    assert empty['items'] == [] and empty['complete']


@pytest.mark.anyio
async def test_overlap_endpoints_and_unknown_end(conn):
    carry = await episode(conn, START-timedelta(hours=1), end=START+timedelta(hours=1), state='resolved')
    open_id = await episode(conn, START-timedelta(days=80))
    onset = await episode(conn, START, end=START, state='resolved')
    unknown = await episode(conn, START+timedelta(hours=1), state='resolved')
    await episode(conn, START-timedelta(days=1), end=START, state='resolved')
    await episode(conn, START-timedelta(days=1), state='resolved')
    await episode(conn, END)
    page = await fetch_migraine_episode_range(conn, USER_A, start=START, end=END,
        as_of=START+timedelta(days=1), limit=100)
    rows = {r['id']: r for r in page['items']}
    assert set(rows) == {carry, open_id, onset, unknown}
    assert rows[open_id]['end_status'] == 'open' and rows[open_id]['ended_at'] is None
    assert rows[unknown]['end_status'] == 'unknown' and rows[unknown]['ended_at'] is None
    future = await fetch_migraine_episode_range(conn, USER_A, start=END+timedelta(days=1),
        end=END+timedelta(days=2), as_of=START, limit=100)
    assert future['items'] == []


@pytest.mark.anyio
@pytest.mark.parametrize('change', ['insert', 'delete', 'edit', 'move_out'])
async def test_concurrent_change_requires_refresh(conn, change):
    first = await episode(conn, START+timedelta(days=1))
    second = await episode(conn, START+timedelta(days=2))
    page = await read_history(conn, USER_A, start=START, end=END, limit=1)
    if change == 'insert':
        await episode(conn)
    elif change == 'delete':
        await conn.execute('delete from raw.user_symptom_episodes where id=%s', (first,))
    elif change == 'edit':
        await conn.execute("update raw.user_symptom_episodes set latest_note_text='edited' where id=%s", (second,))
    else:
        await conn.execute('update raw.user_symptom_episodes set started_at=%s where id=%s', (END, first))
    with pytest.raises(HistoryChanged):
        await read_history(conn, USER_A, start=START, end=END, limit=1, cursor=page['next_cursor'])


@pytest.mark.anyio
async def test_bad_cursor_range_and_owner_rejected(conn):
    await episode(conn); await episode(conn)
    page = await read_history(conn, USER_A, start=START, end=END, limit=1)
    for args in [dict(cursor='garbage'), dict(cursor=''), dict(start=END),
                 dict(end=END+timedelta(days=63)), dict(start=START.replace(tzinfo=None)),
                 dict(limit=0), dict(user_id=USER_B, cursor=page['next_cursor']),
                 dict(end=END-timedelta(days=1), cursor=page['next_cursor'])]:
        params = dict(user_id=USER_A, start=START, end=END); params.update(args)
        with pytest.raises(ValueError):
            await read_history(conn, **params)


@pytest.mark.anyio
async def test_cursor_fingerprint_survives_connection_timezone_change(conn):
    await episode(conn); await episode(conn, START+timedelta(hours=1))
    page = await read_history(conn, USER_A, start=START, end=END, limit=1)
    await conn.execute("set time zone 'Asia/Tokyo'")
    second = await read_history(conn, USER_A, start=START, end=END, limit=1, cursor=page['next_cursor'])
    assert second['snapshot'] == page['snapshot'] and second['complete']
    assert second['items'][0]['started_at'].endswith('+00:00')


@pytest.mark.anyio
async def test_actual_range_query_plan_and_backend_json(conn, monkeypatch):
    from app.routers.symptoms import get_migraine_history
    from starlette.requests import Request
    # Representative owner-selectivity, all synthetic; no production access.
    await conn.execute("""insert into raw.user_symptom_events(user_id,ts_utc,symptom_code,source)
        select %s, %s::timestamptz - n * interval '1 hour', 'migraine', 'g012_plan'
        from generate_series(1,5000) n""", (USER_B, END))
    await conn.execute("""insert into raw.user_symptom_episodes(user_id,symptom_event_id,symptom_code,started_at)
        select user_id,id,symptom_code,ts_utc from raw.user_symptom_events where user_id=%s""", (USER_B,))
    id = await episode(conn, START+timedelta(hours=1), id=UUID('11111111-1111-4111-8111-111111111111'))
    await conn.execute('analyze raw.user_symptom_episodes')
    captured = {}
    class Capture:
        @asynccontextmanager
        async def cursor(self, **kwargs):
            async with conn.cursor(**kwargs) as cur:
                class Proxy:
                    async def execute(self, query, params, **options):
                        captured.update(query=query, params=params)
                        await cur.execute(query, params, **options)
                    async def fetchall(self): return await cur.fetchall()
                yield Proxy()
    await fetch_migraine_episode_range(Capture(), USER_A, start=START, end=END, as_of=END, limit=50)
    async with conn.cursor() as cur:
        await cur.execute('explain (analyze, buffers, format json) ' + captured['query'], captured['params'])
        plan = (await cur.fetchone())[0]
    assert 'user_symptom_episodes_user_started_idx' in json.dumps(plan)
    monkeypatch.setenv('GAIA_MIGRAINE_CALENDAR_ENABLED', '1')
    request = Request({'type':'http', 'state':{'user_id':USER_A}})
    response = await get_migraine_history(request, START, END, limit=50, cursor=None, conn=conn)
    assert response['data']['items'][0]['id'] == id and response['data']['complete']
    if directory := os.getenv('GAIA_HISTORY_EVIDENCE_DIR'):
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        (root/'range-query-plan.json').write_text(json.dumps(plan, indent=2)+'\n')
        (root/'actual-backend-history-page.json').write_text(json.dumps(response, indent=2)+'\n')
