from unittest.mock import Mock

import pytest

from bots.gauges import db_utils


def test_returning_proves_output_in_same_upsert_statement(monkeypatch):
    payload = {'user_id': 'synthetic', 'day': '2026-10-07',
               'inputs_hash': 'evaluated', 'updated_at': 'synthetic-time'}
    monkeypatch.setattr(db_utils, 'table_columns', lambda *args: list(payload))
    fetchrow = Mock(return_value={'inputs_hash': 'evaluated', 'updated_at': 'server-time'})
    execute = Mock(side_effect=AssertionError('No separate write or read-back'))
    monkeypatch.setattr(db_utils.pg, 'fetchrow', fetchrow)
    monkeypatch.setattr(db_utils.pg, 'execute', execute)

    result = db_utils.upsert_row('marts', 'user_gauges_day', payload, ['user_id', 'day'],
                                 returning=['inputs_hash', 'updated_at'])

    assert result == {'inputs_hash': 'evaluated', 'updated_at': 'server-time'}
    fetchrow.assert_called_once()
    sql, *params = fetchrow.call_args.args
    assert sql.startswith('insert into marts.user_gauges_day')
    assert 'on conflict (user_id, day) do update set' in sql
    assert sql.endswith(' returning inputs_hash, updated_at')
    assert params == list(payload.values())
    execute.assert_not_called()


def test_existing_upsert_callers_keep_execute_only_behavior(monkeypatch):
    monkeypatch.setattr(db_utils, 'table_columns', lambda *args: ['user_id', 'value'])
    execute = Mock()
    fetchrow = Mock(side_effect=AssertionError('No output proof requested'))
    monkeypatch.setattr(db_utils.pg, 'execute', execute)
    monkeypatch.setattr(db_utils.pg, 'fetchrow', fetchrow)
    assert db_utils.upsert_row('marts', 'example', {'user_id': 'synthetic', 'value': 1}, ['user_id']) is None
    execute.assert_called_once()
    fetchrow.assert_not_called()


def test_return_columns_missing_from_schema_fail_before_write(monkeypatch):
    monkeypatch.setattr(db_utils, 'table_columns', lambda *args: ['user_id'])
    execute, fetchrow = Mock(), Mock()
    monkeypatch.setattr(db_utils.pg, 'execute', execute)
    monkeypatch.setattr(db_utils.pg, 'fetchrow', fetchrow)
    with pytest.raises(RuntimeError, match='Return columns missing'):
        db_utils.upsert_row('marts', 'example', {'user_id': 'synthetic'}, ['user_id'],
                            returning=['inputs_hash', 'updated_at'])
    execute.assert_not_called()
    fetchrow.assert_not_called()
