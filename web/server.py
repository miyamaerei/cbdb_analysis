#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CBDB 只读查询服务（零依赖，只用 Python 标准库）

    python web/server.py --db cbdb_20260926.sqlite3 --port 8787

前端（Vite 开发服务器 5173）通过 vite proxy 访问本服务的 /api/*。
数据库以 mode=ro 打开，SQLite 层面禁止任何写入。

接口
----
GET  /api/stats                      库概况
GET  /api/search?q=王安石&limit=30    按姓名搜索人物
GET  /api/person/<id>                人物档案（含区间轴体检）
GET  /api/person/<id>/timeline       区间年谱（可筛选阶段/精度）
GET  /api/person/<id>/relations      亲属 + 交遊 + 任官
GET  /api/person/<id>/graph          关系网络（可限深度）
POST /api/sql  {"sql": "SELECT ..."} 只读 SQL 沙盒
GET  /api/presets                    报告里的预设查询清单
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "frontend", "dist")

# SQL 沙盒：最长执行时间（秒）后的进度回调次数上限
MAX_QUERY_SECONDS = 20.0
MAX_ROWS = 2000

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".png": "image/png",
    ".woff2": "font/woff2",
}


# --------------------------------------------------------------------------
# 数据库
# --------------------------------------------------------------------------
def open_ro(path: str) -> sqlite3.Connection:
    uri = f"file:{path.replace(os.sep, '/')}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def rows_to_dicts(cur):
    return [dict(r) for r in cur.fetchall()]


def with_deadline(conn, seconds=MAX_QUERY_SECONDS):
    """超时中断：超过 seconds 秒的查询直接抛错，避免拖死服务。"""
    t0 = time.time()

    def handler():
        if time.time() - t0 > seconds:
            return 1
        return 0

    conn.set_progress_handler(handler, 10000)


# --------------------------------------------------------------------------
# 视图元数据（由 web/build_view_meta.py 预先剖析好）
# --------------------------------------------------------------------------
META_PATH = os.path.join(ROOT, "view_meta.json")
VIEW_META = None


def load_meta():
    global VIEW_META
    if os.path.isfile(META_PATH):
        with open(META_PATH, encoding="utf-8") as f:
            VIEW_META = json.load(f)
        print(f"视图元数据: {META_PATH} ({len(VIEW_META.get('views', {}))} 个)")
    else:
        VIEW_META = None
        print("警告：未找到 view_meta.json，请先运行 web/build_view_meta.py", file=sys.stderr)


def build_view_query(name, filters, sort, limit, offset, any_groups=None):
    """把前端给的筛选条件编译成 SQL。列名一律对照元数据白名单，杜绝注入。

    filters    —— 每列一条 AND 条件
    any_groups —— [{"cols": [...], "val": "x"}]，组内多列 OR、组间与 filters 一起 AND。
                  用于「一个搜索框搜遍所有文本列」，避免为每个视图写专门的全文查询。
    """
    if not VIEW_META or name not in VIEW_META["views"]:
        raise ValueError(f"未知视图: {name}")
    vm = VIEW_META["views"][name]
    allowed = {c["name"]: c for c in vm["filters"]}       # 可筛选（白名单）
    all_cols = set(vm["columns"])                          # 可排序（整表的列）

    where, args = [], []

    # ---- OR 组（组内 OR，与下方 AND 条件并列）
    for g in (any_groups or [])[:5]:
        if not isinstance(g, dict):
            continue
        val = g.get("val")
        if val in (None, "") or str(val).strip() == "":
            continue
        cols = [c for c in (g.get("cols") or []) if c in all_cols][:40]
        if not cols:
            continue
        like = " OR ".join(f'"{c}" LIKE ?' for c in cols)
        where.append(f"({like})")
        args += [f"%{val}%"] * len(cols)

    for f in filters or []:
        col, op = f.get("col"), f.get("op")
        if col not in allowed:
            continue
        kind = allowed[col]["kind"]
        val, val2 = f.get("val"), f.get("val2")
        colq = f'"{col}"'

        if op == "eq" and val not in (None, ""):
            where.append(f"{colq} = ?")
            args.append(val)
        elif op == "in" and isinstance(val, list) and val:
            where.append(f"{colq} IN ({','.join('?' * len(val))})")
            args += list(val)
        elif op == "contains" and val:
            where.append(f"{colq} LIKE ?")
            args.append(f"%{val}%")
        elif op == "startswith" and val:
            where.append(f"{colq} LIKE ?")
            args.append(f"{val}%")
        elif op == "gte" and val not in (None, ""):
            where.append(f"{colq} >= ?")
            args.append(val)
        elif op == "lte" and val not in (None, ""):
            where.append(f"{colq} <= ?")
            args.append(val)
        elif op == "between" and val not in (None, "") and val2 not in (None, ""):
            where.append(f"{colq} BETWEEN ? AND ?")
            args += [val, val2]
        elif op == "notnull":
            where.append(f"{colq} IS NOT NULL")
        elif op == "isnull":
            where.append(f"{colq} IS NULL")
        elif kind in ("year", "num", "pid") and val not in (None, ""):
            # 兜底：前端只给了单值
            where.append(f"{colq} = ?")
            args.append(val)

    sql = f'SELECT * FROM "{name}"'
    if where:
        sql += " WHERE " + " AND ".join(where)
    if sort and sort.get("col") in all_cols:
        d = "DESC" if str(sort.get("dir", "")).upper() == "DESC" else "ASC"
        sql += f' ORDER BY "{sort["col"]}" {d}'
    sql += " LIMIT ? OFFSET ?"
    return sql, args


def q_view(conn, name, payload):
    limit = max(1, min(int(payload.get("limit", 100)), 500))
    offset = max(0, int(payload.get("offset", 0)))
    sql, args = build_view_query(
        name, payload.get("filters"), payload.get("sort"), limit + 1, offset,
        any_groups=payload.get("any"),
    )
    with_deadline(conn)
    t0 = time.time()
    cur = conn.execute(sql, args + [limit + 1, offset])
    rows = [dict(r) for r in cur.fetchmany(limit + 1)]
    has_more = len(rows) > limit
    rows = rows[:limit]
    cols = list(rows[0].keys()) if rows else [d[0] for d in (cur.description or [])]
    return {
        "columns": cols,
        "rows": rows,
        "has_more": has_more,
        "offset": offset,
        "limit": limit,
        "elapsed": round(time.time() - t0, 3),
    }


# --------------------------------------------------------------------------
# 业务查询
# --------------------------------------------------------------------------
def q_stats(conn):
    def one(sql, args=()):
        try:
            return conn.execute(sql, args).fetchone()[0]
        except Exception:
            return None

    return {
        "persons": one("SELECT COUNT(*) FROM BIOG_MAIN"),
        "events": one("SELECT COUNT(*) FROM View_PersonLifeTimeline"),
        "resolved": one("SELECT COUNT(*) FROM LIFE_EVENT_RESOLVED"),
        "kin": one("SELECT COUNT(*) FROM KIN_DATA"),
        "assoc": one("SELECT COUNT(*) FROM ASSOC_DATA"),
        "office": one("SELECT COUNT(*) FROM POSTED_TO_OFFICE_DATA"),
        "tables": one("SELECT COUNT(*) FROM sqlite_master WHERE type='table'"),
        "views": one("SELECT COUNT(*) FROM sqlite_master WHERE type='view'"),
        "birth_year": one("SELECT COUNT(*) FROM BIOG_MAIN WHERE c_birthyear > 0"),
        "index_year": one("SELECT COUNT(*) FROM BIOG_MAIN WHERE c_index_year <> 0"),
        "db_file": os.path.basename(DB_PATH),
        "db_size_mb": round(os.path.getsize(DB_PATH) / 1048576, 1),
    }


def q_search(conn, q, limit=30):
    q = (q or "").strip()
    if not q:
        return []
    limit = max(1, min(int(limit or 30), 200))
    like = f"%{q}%"
    sql = """
    SELECT b.c_personid, b.c_name_chn, b.c_name, b.c_surname_chn,
           b.c_index_year, b.c_birthyear, b.c_deathyear,
           d.c_dynasty_chn AS dynasty,
           (SELECT COUNT(*) FROM LIFE_EVENT_RESOLVED r
             WHERE r.c_personid = b.c_personid) AS events
    FROM BIOG_MAIN b
    LEFT JOIN DYNASTIES d ON d.c_dy = b.c_dy
    WHERE b.c_name_chn LIKE ? OR b.c_name LIKE ? OR b.c_mingzi_chn LIKE ?
    ORDER BY events DESC
    LIMIT ?
    """
    return rows_to_dicts(conn.execute(sql, (like, like, like, limit)))


def q_person(conn, pid):
    row = conn.execute(
        """
        SELECT b.*, d.c_dynasty_chn AS dynasty
        FROM BIOG_MAIN b LEFT JOIN DYNASTIES d ON d.c_dy = b.c_dy
        WHERE b.c_personid = ?
        """,
        (pid,),
    ).fetchone()
    if row is None:
        return None
    p = dict(row)
    p.pop("c_notes", None)

    # 区间轴体检
    p["axis"] = rows_to_dicts(
        conn.execute(
            """SELECT precision, COUNT(*) AS n, ROUND(AVG(width),1) AS avg_width,
                      SUM(conflict) AS conflicts
               FROM LIFE_EVENT_RESOLVED WHERE c_personid = ? GROUP BY precision""",
            (pid,),
        )
    )
    p["stages"] = rows_to_dicts(
        conn.execute(
            """SELECT stage_no, stage, COUNT(*) AS n, ROUND(AVG(width),1) AS avg_width
               FROM LIFE_EVENT_RESOLVED WHERE c_personid = ? GROUP BY stage_no, stage
               ORDER BY n DESC""",
            (pid,),
        )
    )
    p["frame"] = None
    r = conn.execute(
        "SELECT frame_src FROM LIFE_EVENT_RESOLVED WHERE c_personid = ? LIMIT 1", (pid,)
    ).fetchone()
    if r:
        p["frame"] = r["frame_src"]
    p["total_events"] = conn.execute(
        "SELECT COUNT(*) FROM LIFE_EVENT_RESOLVED WHERE c_personid = ?", (pid,)
    ).fetchone()[0]

    # 籍贯
    p["addrs"] = rows_to_dicts(
        conn.execute(
            """SELECT a.c_addr_id, ad.c_name_chn AS addr, t.c_addr_desc_chn AS addr_type
               FROM BIOG_ADDR_DATA a
               LEFT JOIN ADDR_CODES ad ON ad.c_addr_id = a.c_addr_id
               LEFT JOIN BIOG_ADDR_CODES t ON t.c_addr_type = a.c_addr_type
               WHERE a.c_personid = ? LIMIT 20""",
            (pid,),
        )
    )
    p["altnames"] = rows_to_dicts(
        conn.execute(
            """SELECT c_alt_name_chn AS name, t.c_name_type_desc_chn AS name_type
               FROM ALTNAME_DATA n
               LEFT JOIN ALTNAME_CODES t ON t.c_name_type_code = n.c_alt_name_type_code
               WHERE n.c_personid = ? LIMIT 30""",
            (pid,),
        )
    )
    return p


def q_timeline(conn, pid, stages=None, precs=None, limit=2000):
    where, args = ["r.c_personid = ?"], [pid]
    if stages:
        where.append(f"r.stage_no IN ({','.join('?' * len(stages))})")
        args += list(stages)
    if precs:
        where.append(f"r.precision IN ({','.join('?' * len(precs))})")
        args += list(precs)
    sql = f"""
    SELECT r.order_rank, r.stage_no, r.stage, r.event_label, r.counterpart_name_chn,
           r.time_precision, r.prior_lo, r.prior_hi, r.lo, r.hi, r.width,
           r.narrowed, r.precision, r.conflict, r.locked, r.frame_src
    FROM LIFE_EVENT_RESOLVED r
    WHERE {' AND '.join(where)}
    ORDER BY r.lo, r.width, r.order_rank
    LIMIT ?
    """
    args.append(int(limit))
    return rows_to_dicts(conn.execute(sql, args))


def q_relations(conn, pid, limit=300):
    out = {}
    out["kin"] = rows_to_dicts(
        conn.execute(
            """SELECT k.c_kin_id AS other_id, b.c_name_chn AS other_name,
                      kc.c_kinrel_chn AS rel, kc.c_upstep AS upstep, kc.c_dwnstep AS dwnstep
               FROM KIN_DATA k
               LEFT JOIN BIOG_MAIN b ON b.c_personid = k.c_kin_id
               LEFT JOIN KINSHIP_CODES kc ON kc.c_kincode = k.c_kin_code
               WHERE k.c_personid = ? LIMIT ?""",
            (pid, limit),
        )
    )
    out["assoc"] = rows_to_dicts(
        conn.execute(
            """SELECT a.c_assoc_id AS other_id, b.c_name_chn AS other_name,
                      ac.c_assoc_desc_chn AS rel, a.c_assoc_first_year AS year
               FROM ASSOC_DATA a
               LEFT JOIN BIOG_MAIN b ON b.c_personid = a.c_assoc_id
               LEFT JOIN ASSOC_CODES ac ON ac.c_assoc_code = a.c_assoc_code
               WHERE a.c_personid = ? LIMIT ?""",
            (pid, limit),
        )
    )
    out["office"] = rows_to_dicts(
        conn.execute(
            """SELECT o.c_office_id AS other_id, oc.c_office_chn AS other_name,
                      o.c_firstyear AS year
               FROM POSTED_TO_OFFICE_DATA o
               LEFT JOIN OFFICE_CODES oc ON oc.c_office_id = o.c_office_id
               WHERE o.c_personid = ? AND o.c_firstyear > 0
               ORDER BY o.c_firstyear LIMIT ?""",
            (pid, min(limit, 100)),
        )
    )
    return out


def q_graph(conn, pid, depth=1, limit=250):
    """以某人为中心的关系网络（人物节点）。depth=2 会非常大，务必限深。"""
    depth = max(1, min(int(depth or 1), 2))
    seeds = {int(pid)}
    frontier = {int(pid)}
    edges = []
    for _ in range(depth):
        if not frontier:
            break
        ph = ",".join("?" * len(frontier))
        rows = conn.execute(
            f"""SELECT c_personid AS a, c_kin_id AS b, 'kinship' AS t FROM KIN_DATA
                WHERE c_personid IN ({ph}) AND c_kin_id > 0
                UNION ALL
                SELECT c_personid, c_assoc_id, 'assoc' FROM ASSOC_DATA
                WHERE c_personid IN ({ph}) AND c_assoc_id > 0""",
            tuple(frontier) * 2,   # UNION ALL 两个分支各要一份参数
        ).fetchall()
        nxt = set()
        for r in rows:
            edges.append((r["a"], r["b"], r["t"]))
            if r["b"] not in seeds:
                nxt.add(r["b"])
        frontier = nxt
        seeds |= nxt
        if len(seeds) > limit:
            break

    ids = sorted(seeds)[:limit]
    keep = set(ids)
    edges = [e for e in edges if e[0] in keep and e[1] in keep]
    if not ids:
        return {"nodes": [], "links": []}
    ph = ",".join("?" * len(ids))
    nodes = rows_to_dicts(
        conn.execute(
            f"""SELECT c_personid AS id, c_name_chn AS name, c_index_year AS iy
                FROM BIOG_MAIN WHERE c_personid IN ({ph})""",
            tuple(ids),
        )
    )
    return {"nodes": nodes, "links": [{"a": a, "b": b, "t": t} for a, b, t in edges]}


PRESETS = [
    {"key": "top_timeline", "name": "年谱最完整的人物 TOP20", "params": []},
    {"key": "dynasty_people", "name": "各朝代人物数量", "params": []},
    {"key": "kin_top", "name": "亲属关系类型分布", "params": []},
    {"key": "assoc_top", "name": "交游关系类型 TOP20", "params": []},
    {"key": "office_top", "name": "最常见的官职 TOP20", "params": []},
    {"key": "birthplace_top", "name": "籍贯人口 TOP20", "params": []},
    {"key": "axis_quality", "name": "全库区间轴质量分布", "params": []},
    {"key": "stage_solvable", "name": "各阶段时间可解性", "params": []},
    {"key": "conflicts", "name": "数据自相矛盾的记录（脏数据线索）", "params": []},
    {"key": "improved", "name": "被推理改善最多的人物", "params": []},
    {"key": "county_top", "name": "县城人口 TOP20", "params": []},
    {"key": "text_world", "name": "单本文献覆盖人数 TOP20", "params": []},
    {"key": "person_events", "name": "某人各类事件计数", "params": ["pid"]},
    {"key": "person_offices", "name": "某人任官年表", "params": ["pid"]},
    {"key": "person_addr", "name": "某人地理行迹", "params": ["pid"]},
]

PRESET_SQL = {
    "top_timeline": """
        SELECT p.c_personid, p.c_name_chn, COUNT(*) AS n
        FROM View_PersonLifeTimeline t JOIN BIOG_MAIN p ON p.c_personid = t.c_personid
        WHERE t.time_precision IN ('year','nianhao')
        GROUP BY p.c_personid ORDER BY n DESC LIMIT 20""",
    "dynasty_people": """
        SELECT d.c_dynasty_chn AS 朝代, COUNT(*) AS 人数
        FROM BIOG_MAIN b JOIN DYNASTIES d ON d.c_dy = b.c_dy
        GROUP BY d.c_dynasty_chn ORDER BY 人数 DESC LIMIT 30""",
    "kin_top": """
        SELECT kc.c_kinrel_chn AS 亲属关系, COUNT(*) AS 条数
        FROM KIN_DATA k JOIN KINSHIP_CODES kc ON kc.c_kincode = k.c_kin_code
        GROUP BY kc.c_kinrel_chn ORDER BY 条数 DESC LIMIT 30""",
    "assoc_top": """
        SELECT ac.c_assoc_desc_chn AS 交游关系, COUNT(*) AS 条数
        FROM ASSOC_DATA a JOIN ASSOC_CODES ac ON ac.c_assoc_code = a.c_assoc_code
        GROUP BY ac.c_assoc_desc_chn ORDER BY 条数 DESC LIMIT 20""",
    "office_top": """
        SELECT oc.c_office_chn AS 官职, COUNT(*) AS 任职次数
        FROM POSTED_TO_OFFICE_DATA o JOIN OFFICE_CODES oc ON oc.c_office_id = o.c_office_id
        GROUP BY oc.c_office_chn ORDER BY 任职次数 DESC LIMIT 20""",
    "birthplace_top": """
        SELECT ad.c_name_chn AS 籍贯, COUNT(*) AS 人数
        FROM BIOG_ADDR_DATA a
        JOIN ADDR_CODES ad ON ad.c_addr_id = a.c_addr_id
        JOIN BIOG_ADDR_CODES t ON t.c_addr_type = a.c_addr_type
        WHERE t.c_addr_desc_chn LIKE '%籍貫%'
        GROUP BY ad.c_name_chn ORDER BY 人数 DESC LIMIT 20""",
    "axis_quality": """
        SELECT precision AS 精度, COUNT(*) AS 条数, ROUND(AVG(width),1) AS 平均宽度
        FROM LIFE_EVENT_RESOLVED GROUP BY precision ORDER BY 条数 DESC""",
    "stage_solvable": """
        SELECT stage AS 阶段, COUNT(*) AS 条数,
               ROUND(AVG(prior_width),1) AS 原宽, ROUND(AVG(width),1) AS 现宽,
               ROUND(100.0*SUM(narrowed>0)/COUNT(*),1) AS 被收窄百分比
        FROM LIFE_EVENT_RESOLVED GROUP BY stage ORDER BY 条数 DESC""",
    "conflicts": """
        SELECT r.c_personid, p.c_name_chn, r.stage, r.event_label, r.prior_lo, r.prior_hi
        FROM LIFE_EVENT_RESOLVED r JOIN BIOG_MAIN p ON p.c_personid = r.c_personid
        WHERE r.conflict = 1 LIMIT 200""",
    "improved": """
        SELECT r.c_personid, p.c_name_chn, COUNT(*) AS 事件数,
               ROUND(AVG(r.prior_width),1) AS 原宽, ROUND(AVG(r.width),1) AS 现宽,
               SUM(r.narrowed) AS 总收窄
        FROM LIFE_EVENT_RESOLVED r JOIN BIOG_MAIN p ON p.c_personid = r.c_personid
        GROUP BY r.c_personid HAVING 事件数 >= 30 ORDER BY 总收窄 DESC LIMIT 20""",
    "county_top": """
        SELECT county_addr_id AS 县id, county_name_chn AS 县, COUNT(*) AS 人数
        FROM View_CountyPeopleData GROUP BY county_addr_id ORDER BY 人数 DESC LIMIT 20""",
    "text_world": """
        SELECT c_source AS 文献id, COUNT(DISTINCT c_personid) AS 覆盖人数
        FROM View_TextAssociationData
        GROUP BY c_source ORDER BY 覆盖人数 DESC LIMIT 20""",
    "person_events": """
        SELECT stage AS 阶段, time_precision AS 时间精度, COUNT(*) AS 条数
        FROM View_PersonLifeTimeline WHERE c_personid = :pid
        GROUP BY stage, time_precision ORDER BY 条数 DESC""",
    "person_offices": """
        SELECT o.c_firstyear AS 年, oc.c_office_chn AS 官职
        FROM POSTED_TO_OFFICE_DATA o
        LEFT JOIN OFFICE_CODES oc ON oc.c_office_id = o.c_office_id
        WHERE o.c_personid = :pid AND o.c_firstyear > 0
        ORDER BY o.c_firstyear""",
    "person_addr": """
        SELECT ad.c_name_chn AS 地点, t.c_addr_desc_chn AS 类型
        FROM BIOG_ADDR_DATA a
        LEFT JOIN ADDR_CODES ad ON ad.c_addr_id = a.c_addr_id
        LEFT JOIN BIOG_ADDR_CODES t ON t.c_addr_type = a.c_addr_type
        WHERE a.c_personid = :pid""",
}


def q_preset(conn, key, pid=None):
    sql = PRESET_SQL.get(key)
    if not sql:
        return None
    if ":pid" in sql:
        if pid is None:
            return {"columns": [], "rows": [], "note": "需要 pid 参数"}
        sql = sql.replace(":pid", str(int(pid)))
    with_deadline(conn)
    cur = conn.execute(sql)
    rows = rows_to_dicts(cur)
    cols = list(rows[0].keys()) if rows else [d[0] for d in (cur.description or [])]
    return {"columns": cols, "rows": rows[:MAX_ROWS]}


def q_raw_sql(conn, sql):
    s = (sql or "").strip().rstrip(";").strip()
    if not s:
        raise ValueError("SQL 为空")
    low = s.lower()
    if not (low.startswith("select") or low.startswith("with") or low.startswith("pragma")):
        raise ValueError("只允许 SELECT / WITH / PRAGMA 查询")
    for bad in ("insert", "update", "delete", "drop", "alter", "create", "attach", "vacuum"):
        if bad in low:
            raise ValueError(f"包含被禁止的关键字: {bad}")
    if ";" in s:
        raise ValueError("不允许一次执行多条语句")
    with_deadline(conn)
    cur = conn.execute(s)
    rows = rows_to_dicts(cur)
    cols = list(rows[0].keys()) if rows else [d[0] for d in (cur.description or [])]
    return {"columns": cols, "rows": rows[:MAX_ROWS], "truncated": len(rows) > MAX_ROWS}


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "CBDB-RO/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _static(self, path):
        if not os.path.isdir(DIST):
            self._send(404, {"error": "前端未构建：cd web/frontend && npm install && npm run build"})
            return
        rel = path.strip("/") or "index.html"
        fp = os.path.normpath(os.path.join(DIST, rel))
        if not fp.startswith(DIST) or not os.path.isfile(fp):
            fp = os.path.join(DIST, "index.html")  # SPA fallback
        ext = os.path.splitext(fp)[1]
        with open(fp, "rb") as f:
            self._send(200, f.read(), MIME.get(ext, "application/octet-stream"))

    def do_OPTIONS(self):
        self._send(204, b"", "text/plain")

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        seg = [unquote(s) for s in u.path.split("/") if s]

        if not seg or seg[0] != "api":
            return self._static(u.path)

        conn = None
        try:
            conn = open_ro(DB_PATH)
            if seg[1] == "stats":
                return self._send(200, q_stats(conn))
            if seg[1] == "search":
                return self._send(200, q_search(conn, qs.get("q", [""])[0],
                                                qs.get("limit", ["30"])[0]))
            if seg[1] == "views":
                if not VIEW_META:
                    return self._send(500, {"error": "缺少 view_meta.json"})
                return self._send(200, VIEW_META)
            if seg[1] == "presets":
                return self._send(200, {"presets": PRESETS})
            if seg[1] == "preset" and len(seg) > 2:
                pid = qs.get("pid", [None])[0]
                r = q_preset(conn, seg[2], pid)
                if r is None:
                    return self._send(404, {"error": "未知预设查询"})
                return self._send(200, r)
            if seg[1] == "person" and len(seg) > 2:
                pid = int(seg[2])
                if len(seg) == 3:
                    p = q_person(conn, pid)
                    return self._send(200, p if p else {"error": "人物不存在"})
                if seg[3] == "timeline":
                    stages = [int(x) for x in qs.get("stage", "").split(",") if x]
                    precs = [x for x in qs.get("prec", "").split(",") if x]
                    return self._send(200, q_timeline(conn, pid, stages or None,
                                                      precs or None,
                                                      qs.get("limit", ["2000"])[0]))
                if seg[3] == "relations":
                    return self._send(200, q_relations(conn, pid))
                if seg[3] == "graph":
                    return self._send(200, q_graph(conn, pid, qs.get("depth", ["1"])[0],
                                                   int(qs.get("limit", ["250"])[0])))
            return self._send(404, {"error": "未知接口"})
        except Exception as e:
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})
        finally:
            if conn:
                try:
                    conn.set_progress_handler(None, 0)
                    conn.close()
                except Exception:
                    pass

    def do_POST(self):
        u = urlparse(self.path)
        seg = [unquote(s) for s in u.path.split("/") if s]
        if len(seg) < 2 or seg[0] != "api":
            return self._send(404, {"error": "未知接口"})
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = {}
        conn = None
        try:
            conn = open_ro(DB_PATH)
            if seg[1] == "sql":
                t0 = time.time()
                r = q_raw_sql(conn, payload.get("sql", ""))
                r["elapsed"] = round(time.time() - t0, 3)
                return self._send(200, r)
            if seg[1] == "view" and len(seg) > 2:
                return self._send(200, q_view(conn, seg[2], payload))
            return self._send(404, {"error": "未知接口"})
        except Exception as e:
            return self._send(400, {"error": f"{type(e).__name__}: {e}"})
        finally:
            if conn:
                try:
                    conn.set_progress_handler(None, 0)
                    conn.close()
                except Exception:
                    pass


DB_PATH = ""


def main():
    global DB_PATH
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(ROOT, "..", "cbdb_20260926.sqlite3"))
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    DB_PATH = os.path.abspath(a.db)
    if not os.path.isfile(DB_PATH):
        print(f"找不到数据库: {DB_PATH}", file=sys.stderr)
        return 1
    print(f"数据库: {DB_PATH}")
    load_meta()          # 必须先加载，否则 /api/views 与 /api/view/<name> 全部 500
    print(f"服务:   http://{a.host}:{a.port}/   (API: /api/stats)")
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
