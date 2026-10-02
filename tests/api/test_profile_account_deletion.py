"""Offline deletion contract tests. Run with synthetic settings from an empty cwd."""
from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi import HTTPException
import httpx
from httpx import AsyncClient as RealAsyncClient

from app.routers import profile


USER = "00000000-0000-4000-8000-000000000001"
OTHER = "00000000-0000-4000-8000-000000000002"
CANARY = "synthetic-private-provider-detail"


class MemoryCursor:
    """Small ownership fixture, not a Postgres engine or live schema claim."""
    def __init__(self, conn):
        self.conn = conn
        self.rows = []
        self.rowcount = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def execute(self, query, params=None, **kwargs):
        text = query if isinstance(query, str) else query.as_string()
        params = tuple(params or ())
        self.conn.queries.append((text, params))
        if "join information_schema.tables" in text:
            # Assert the real query's coverage filters, then model their result.
            assert "c.column_name = 'user_id'" in text
            assert "t.table_type = 'BASE TABLE'" in text
            self.rows = [dict(table_schema=s, table_name=t)
                         for (s, t), meta in self.conn.tables.items()
                         if s in params[0] and meta['kind'] == 'BASE TABLE' and meta['owner'] == 'user_id']
        elif "information_schema.columns" in text:
            meta = self.conn.tables.get(params)
            self.rows = [{'column_name': meta['owner']}] if meta else []
        else:
            for (schema, table), meta in self.conn.tables.items():
                if f'"{schema}"."{table}"' not in text:
                    continue
                assert f'where "{meta["owner"]}" = %s' in text
                if text.startswith('delete from'):
                    self.rowcount = meta['rows'].pop(params[0], 0)
                elif text.startswith('select count'):
                    self.rows = [{'count': meta['rows'].get(params[0], 0)}]
                else:
                    raise AssertionError(text)
                break
            else:
                raise AssertionError(text)

    async def fetchall(self):
        return self.rows

    async def fetchone(self):
        return self.rows[0] if self.rows else None


class MemoryConn:
    def __init__(self):
        self.events = []
        self.queries = []
        self.tables = {}
        for schema, table, owner, kind in [
            ('raw', 'user_symptom_events', 'user_id', 'BASE TABLE'),
            ('app', 'user_tags', 'user_id', 'BASE TABLE'),
            ('content', 'user_home_feed_seen', 'user_id', 'BASE TABLE'),
            ('marts', 'user_daily_features', 'user_id', 'BASE TABLE'),
            ('gaia', 'samples', 'user_id', 'BASE TABLE'),
            ('gaia', 'users', 'id', 'BASE TABLE'),
            ('public', 'app_stripe_customers', 'user_id', 'BASE TABLE'),
            ('marts', 'symptom_daily', 'user_id', 'MATERIALIZED VIEW'),
        ]:
            self.tables[(schema, table)] = {'owner': owner, 'kind': kind, 'rows': {USER: 2, OTHER: 3}}

    def cursor(self, **kwargs):
        return MemoryCursor(self)

    async def commit(self):
        self.events.append('commit')


class AccountDeletionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        # No socket can be opened by a fixture or an accidental real provider call.
        self.stack.enter_context(patch.object(socket.socket, 'connect', side_effect=AssertionError('Network prohibited')))
        self.stack.enter_context(patch.object(socket, 'getaddrinfo', side_effect=AssertionError('DNS prohibited')))
        self.stack.enter_context(patch.object(profile.settings, 'SUPABASE_URL', 'https://auth.fixture.invalid'))
        self.stack.enter_context(patch.object(profile.settings, 'SUPABASE_SERVICE_ROLE_KEY', 'synthetic-service-key'))
        self.calls = []

    def provider(self, response=None, error=None):
        def handler(request):
            self.calls.append(request)
            self.assertEqual(request.method, 'DELETE')
            self.assertEqual(str(request.url), f'https://auth.fixture.invalid/auth/v1/admin/users/{USER}')
            self.assertEqual(request.headers['apikey'], 'synthetic-service-key')
            self.assertEqual(request.headers['authorization'], 'Bearer synthetic-service-key')
            if error:
                raise error
            return response

        def client(**kwargs):
            return RealAsyncClient(transport=httpx.MockTransport(handler), **kwargs)
        self.stack.enter_context(patch.object(profile.httpx, 'AsyncClient', client))

    async def test_confirmed_success_and_identified_absent_user_allow_completion(self):
        for response in [httpx.Response(200, json={}), httpx.Response(204),
                         httpx.Response(404, json={'code': 404, 'error_code': 'user_not_found', 'msg': CANARY})]:
            with self.subTest(status=response.status_code):
                self.provider(response=response)
                await profile._delete_supabase_auth_user(USER)
        self.assertEqual(len(self.calls), 3)

    async def test_unidentified_404_never_confirms_deletion(self):
        bodies = [b'<html>route missing</html>', b'{}', b'[]', b'null',
                  b'{"msg":"User not found"}', b'{"code":"user_not_found"}',
                  b'{"error_code":"route_not_found"}', b'{"error_code":["user_not_found"]}']
        for body in bodies:
            with self.subTest(body=body):
                self.provider(response=httpx.Response(404, content=body))
                with self.assertRaises(HTTPException) as caught:
                    await profile._delete_supabase_auth_user(USER)
                self.assertEqual(caught.exception.status_code, 502)

    async def test_other_status_and_private_provider_body_remain_unconfirmed(self):
        for status in [400, 401, 403, 409, 429, 500, 503]:
            with self.subTest(status=status):
                self.provider(response=httpx.Response(status, json={'error_code':'user_not_found', 'message':CANARY}))
                with self.assertRaises(HTTPException) as caught:
                    await profile._delete_supabase_auth_user(USER)
                self.assertEqual(caught.exception.status_code, 502)
                self.assertNotIn(CANARY, str(caught.exception.detail))
        self.assertEqual(len(self.calls), 7)  # No internal retry.

    async def test_transport_error_is_sanitized_and_not_retried(self):
        self.provider(error=httpx.ReadTimeout(CANARY))
        with self.assertRaises(HTTPException) as caught:
            await profile._delete_supabase_auth_user(USER)
        self.assertEqual(caught.exception.status_code, 502)
        self.assertNotIn(CANARY, str(caught.exception.detail))
        self.assertIsNone(caught.exception.__cause__)
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertEqual(len(self.calls), 1)

    async def test_scan_deletes_only_selected_owner_and_documents_exclusions(self):
        conn = MemoryConn()
        before = await profile._count_user_scoped_rows(conn, USER)
        self.assertEqual(before['rows_found'], 12)
        deleted = await profile._delete_user_scoped_rows(conn, USER)
        self.assertEqual(deleted['rows_deleted'], 12)
        self.assertEqual(deleted['tables_touched'], 6)
        for (schema, _), meta in conn.tables.items():
            self.assertEqual(meta['rows'][OTHER], 3)
            if schema == 'public' or meta['kind'] == 'MATERIALIZED VIEW':
                self.assertEqual(meta['rows'][USER], 2)
            else:
                self.assertNotIn(USER, meta['rows'])
        self.assertEqual((await profile._delete_user_scoped_rows(conn, USER))['rows_deleted'], 0)

    async def test_database_and_commit_failures_do_not_call_auth(self):
        for stage in ['delete', 'commit']:
            with self.subTest(stage=stage):
                conn = MemoryConn()
                auth = AsyncMock()
                deletion = AsyncMock(return_value={'rows_deleted': 2, 'tables_touched': 1})
                if stage == 'delete':
                    deletion.side_effect = RuntimeError('synthetic database failure')
                else:
                    conn.commit = AsyncMock(side_effect=RuntimeError('synthetic commit failure'))
                with patch.object(profile, '_delete_user_scoped_rows', deletion), patch.object(profile, '_delete_supabase_auth_user', auth):
                    with self.assertRaises(RuntimeError):
                        await profile.profile_delete_account(SimpleNamespace(state=SimpleNamespace(user_id=USER)), conn)
                auth.assert_not_awaited()

    async def test_auth_failure_after_commit_never_returns_success(self):
        conn = MemoryConn()
        self.provider(response=httpx.Response(404, text=CANARY))
        with self.assertRaises(HTTPException):
            await profile.profile_delete_account(SimpleNamespace(state=SimpleNamespace(user_id=USER)), conn)
        self.assertEqual(conn.events, ['commit'])
        self.assertNotIn(USER, conn.tables[('raw','user_symptom_events')]['rows'])
        self.assertEqual(len(self.calls), 1)

    async def test_endpoint_success_preserves_native_response_contract(self):
        conn = MemoryConn()
        self.provider(response=httpx.Response(200, json={}))
        result = await profile.profile_delete_account(SimpleNamespace(state=SimpleNamespace(user_id=USER)), conn)
        self.assertEqual(conn.events, ['commit'])
        self.assertEqual(result, {'ok': True, 'data': {'deleted_user_id': USER, 'rows_deleted': 12, 'tables_touched': 6}})


if __name__ == '__main__':
    unittest.main(verbosity=2)
