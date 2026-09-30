#!/usr/bin/env python3
"""Dump CBDB SQLite schema inventory (tables, columns, row counts, FKs, views) to JSON."""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path


def q1(conn, sql, args=()):
    row = conn.execute(sql, args).fetchone()
    return row[0] if row else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    tables = []
    for (name,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall():
        cols = []
        pk = []
        for r in conn.execute(f'PRAGMA table_info("{name}")').fetchall():
            cols.append(
                {
                    "name": r["name"],
                    "type": r["type"] or "",
                    "notnull": bool(r["notnull"]),
                    "pk": bool(r["pk"]),
                }
            )
            if r["pk"]:
                pk.append(r["name"])
        fks = [
            {
                "column": r["from"],
                "ref_table": r["table"],
                "ref_column": r["to"],
            }
            for r in conn.execute(f'PRAGMA foreign_key_list("{name}")').fetchall()
        ]
        indexes = [
            {"name": r["name"], "cols": r["name"]}
            for r in conn.execute(f'PRAGMA index_list("{name}")').fetchall()
        ]
        nrows = q1(conn, f'SELECT COUNT(*) FROM "{name}"')
        create_sql = q1(
            conn, "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)
        )
        tables.append(
            {
                "name": name,
                "rows": nrows,
                "columns": cols,
                "pk": pk,
                "fks": fks,
                "indexes": indexes,
                "create_sql": create_sql,
            }
        )

    views = []
    for (name, sql) in conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='view' ORDER BY name"
    ).fetchall():
        try:
            # 注意：LIMIT 0 取不到行，列名只能从 cursor.description 拿
            cur = conn.execute(f'SELECT * FROM "{name}" LIMIT 0')
            cols = [d[0] for d in (cur.description or [])]
            cur.fetchall()
            nrows = q1(conn, f'SELECT COUNT(*) FROM "{name}"')
        except Exception as exc:  # pragma: no cover
            cols, nrows = [], f"ERROR: {exc}"
        # Tables referenced by the view SQL.
        refs = sorted(set(re.findall(r"(?i)\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)", sql or "")))
        views.append(
            {"name": name, "rows": nrows, "columns": cols, "refs": refs, "sql": sql}
        )

    out = {
        "db": str(args.db),
        "sqlite_version": sqlite3.sqlite_version,
        "table_count": len(tables),
        "view_count": len(views),
        "tables": tables,
        "views": views,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {args.out}: {len(tables)} tables, {len(views)} views")


if __name__ == "__main__":
    main()
