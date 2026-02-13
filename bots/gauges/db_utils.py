from __future__ import annotations

from typing import Any, Dict, Iterable, List

from services.db import pg

_COLUMN_CACHE: Dict[tuple[str, str], List[str]] = {}


def table_columns(schema: str, table: str) -> List[str]:
    key = (schema, table)
    if key in _COLUMN_CACHE:
        return _COLUMN_CACHE[key]
    rows = pg.fetch(
        """
        select column_name
          from information_schema.columns
         where table_schema = %s
           and table_name = %s
         order by ordinal_position
        """,
        schema,
        table,
    )
    cols = [r["column_name"] for r in rows]
    _COLUMN_CACHE[key] = cols
    return cols


def pick_column(columns: Iterable[str], candidates: Iterable[str]) -> str | None:
    col_set = {c.lower(): c for c in columns}
    for cand in candidates:
        if cand.lower() in col_set:
            return col_set[cand.lower()]
    return None


def upsert_row(schema: str, table: str, data: Dict[str, Any], conflict_cols: List[str]) -> None:
    cols = table_columns(schema, table)
    insert_cols = [c for c in data.keys() if c in cols]
    if not insert_cols:
        raise RuntimeError(f"No matching columns for {schema}.{table}")

    conflict_cols = [c for c in conflict_cols if c in cols]
    if not conflict_cols:
        raise RuntimeError(f"Conflict columns missing for {schema}.{table}: {conflict_cols}")

    placeholders = ", ".join(["%s"] * len(insert_cols))
    updates = ", ".join([f"{c} = excluded.{c}" for c in insert_cols if c not in conflict_cols])
    if not updates:
        updates = ", ".join([f"{c} = excluded.{c}" for c in conflict_cols])

    sql = (
        f"insert into {schema}.{table} ({', '.join(insert_cols)}) "
        f"values ({placeholders}) "
        f"on conflict ({', '.join(conflict_cols)}) do update set {updates}"
    )
    pg.execute(sql, *[data[c] for c in insert_cols])
