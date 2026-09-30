#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
剖析所有视图，生成 web/view_meta.json，供前端自动渲染查询条件。

对每一列采样最多 SAMPLE 行，据此判断该给什么控件：
  pid   主键 / 人物 id      → 精确匹配，且是可跨视图下钻的关联键
  year  年（100~2200）      → 最小/最大 两个输入框
  num   普通数字            → 最小/最大
  cat   文本且取值 ≤ 60 种   → 下拉多选（带每项的条数）
  text  文本且取值很多       → 包含 / 等于
  skip  全空或只有一个取值   → 不给控件

用法:
    python web/build_view_meta.py --db cbdb_20260926.sqlite3
    # 只更新中文标签（不连库、不重新采样，改完 columns_zh.py 就跑这个）
    python web/build_view_meta.py --labels-only
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time

import columns_zh as cz

SAMPLE = 30000        # 每列采样行数
CAT_MAX = 60          # 取值种类 ≤ 此数才做成下拉
TOP_VALUES = 40       # 下拉里最多给多少个取值

# --------------------------------------------------------------------------
# 分组：相互关联的视图放一组，组内可互相下钻
# --------------------------------------------------------------------------
GROUPS = [
    {
        "key": "person", "name": "人物主档", "desc": "人物基本信息、索引地址、史料出处、别名字号",
        "views": ["View_PeopleData", "View_PeopleAddrData", "View_BiogSourceData", "View_AltnameData"],
    },
    {
        "key": "life", "name": "生平与时间轴", "desc": "本项目新增：生平事件流、区间轴求解结果、属性图边表",
        "views": ["View_PersonLifeTimeline", "LIFE_EVENT_RESOLVED", "View_RelationEdges"],
    },
    {
        "key": "kin", "name": "亲属与族谱", "desc": "亲属关系、世代差、姻亲网络",
        "views": ["View_KinshipGenealogyData", "View_KinAddrData"],
    },
    {
        "key": "assoc", "name": "社会关系与交游", "desc": "非亲属的社会关系；按单本文献还原的交往世界",
        "views": ["View_AssociationData", "View_TextAssociationData"],
    },
    {
        "key": "office", "name": "入仕与任官", "desc": "科举/门荫等入仕途径、历任官职、治所",
        "views": ["View_EntryData", "View_PostingOfficeData", "View_PostingAddrData"],
    },
    {
        "key": "addr", "name": "地理与空间", "desc": "人物地址、县级政区人口、事件地点",
        "views": ["View_BiogAddrData", "View_CountyPeopleData", "View_EventAddrData"],
    },
    {
        "key": "status", "name": "身份与社会机构", "desc": "社会身份、所属机构及其地点",
        "views": ["View_StatusData", "View_BiogInstData", "View_BiogInstAddrData"],
    },
    {
        "key": "text", "name": "著作与事件", "desc": "著述、参与的历史事件",
        "views": ["View_BiogTextData", "View_EventData"],
    },
    {
        "key": "poss", "name": "财产", "desc": "财产处置记录（数据量极小，仅 60 条）",
        "views": ["View_PossessionsData", "View_PossessionsAddrData"],
    },
]

# 跨视图关联键：前端据此提供「在另一个视图里查这个值」
JOIN_KEYS = [
    ("c_personid", "人物"),
    ("kin_personid", "人物"),
    ("c_kin_id", "人物"),
    ("c_assoc_id", "人物"),
    ("c_addr_id", "地点"),
    ("county_addr_id", "地点"),
    ("c_office_id", "官职"),
    ("c_source", "文献"),
    ("c_textid", "文献"),
    ("c_inst_code", "机构"),
    ("c_status_code", "身份"),
    ("c_event_code", "事件"),
    ("c_entry_code", "入仕途径"),
    ("c_kin_code", "亲属关系"),
    ("c_assoc_code", "交游关系"),
    ("c_posting_id", "任命"),
]


def is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def make_sample(conn, view, cols, nrows):
    """
    先物化一份「系统性抽样」到临时表，后续所有列都基于它剖析。

    为什么不能直接用 `LIMIT 30000`：
      View_PersonLifeTimeline 这类 UNION ALL 视图的行是按分支顺序吐的，
      前 3 万行全是「生」这一个阶段 —— 采样会把 stage 误判成常量而丢掉。

    做法：挑一个数值列取模（`c_personid % K`），得到跨人物均匀分布的样本。
    只扫全表一次，之后逐列剖析都在小表上跑，又快又无偏。
    """
    conn.execute("DROP TABLE IF EXISTS _sample")
    if nrows and nrows <= SAMPLE:
        conn.execute(f'CREATE TEMP TABLE _sample AS SELECT * FROM "{view}"')
        return nrows

    # 优先按人物 id 取模（跨人物均匀），其次 rowid，最后退化
    pred = None
    for cand in ("c_personid", "src_id", "c_source", "c_addr_id"):
        if cand in cols:
            k = max(2, int(nrows / SAMPLE))
            pred = f'"{cand}" % {k} = 0'
            break
    if pred is None:
        try:
            conn.execute(f'SELECT rowid FROM "{view}" LIMIT 1')
            k = max(2, int(nrows / SAMPLE))
            pred = f"rowid % {k} = 0"
        except Exception:
            pred = None

    if pred:
        conn.execute(f'CREATE TEMP TABLE _sample AS SELECT * FROM "{view}" WHERE {pred}')
    else:
        conn.execute(f'CREATE TEMP TABLE _sample AS SELECT * FROM "{view}" LIMIT {SAMPLE}')
    n = conn.execute("SELECT COUNT(*) FROM _sample").fetchone()[0]
    if n == 0:  # 取模太狠，兜底
        conn.execute("DROP TABLE IF EXISTS _sample")
        conn.execute(f'CREATE TEMP TABLE _sample AS SELECT * FROM "{view}" LIMIT {SAMPLE}')
        n = conn.execute("SELECT COUNT(*) FROM _sample").fetchone()[0]
    return n


def profile_column(conn, view, col):
    """基于临时抽样表 _sample 判断该给什么控件。"""
    try:
        vals = [
            r[0]
            for r in conn.execute(
                f'SELECT "{col}" AS v FROM _sample WHERE "{col}" IS NOT NULL LIMIT {SAMPLE}'
            )
        ]
    except Exception as e:
        return {"name": col, "kind": "skip", "note": f"采样失败 {e}"}

    if not vals:
        return {"name": col, "kind": "skip", "note": "全空"}

    if col == "c_personid":
        return {"name": col, "kind": "pid", "min": min(vals), "max": max(vals)}

    # 数值型
    if all(is_num(v) for v in vals):
        lo, hi = min(vals), max(vals)
        kind = "year" if (("year" in col or "yr" in col) and -900 <= lo and hi <= 2200) else "num"
        return {"name": col, "kind": kind, "min": lo, "max": hi}

    # 文本型
    try:
        d = conn.execute(
            f'SELECT COUNT(DISTINCT "{col}") FROM _sample WHERE "{col}" IS NOT NULL'
        ).fetchone()[0]
    except Exception:
        d = 10 ** 9

    if d <= 1:
        return {"name": col, "kind": "skip", "note": "取值唯一"}

    if d <= CAT_MAX:
        rows = conn.execute(
            f'SELECT "{col}" AS v, COUNT(*) c FROM _sample WHERE "{col}" IS NOT NULL '
            f'GROUP BY v ORDER BY c DESC LIMIT {TOP_VALUES}'
        ).fetchall()
        return {
            "name": col,
            "kind": "cat",
            "distinct": d,
            "values": [{"v": r[0], "c": r[1]} for r in rows if r[0] not in (None, "")],
        }
    return {"name": col, "kind": "text", "distinct": d,
            "sample": [str(v)[:40] for v in vals[:5]]}


def profile_view(conn, view):
    t0 = time.time()
    q = f'"{view}"'
    nrows = conn.execute(f"SELECT COUNT(*) FROM {q}").fetchone()[0]
    cur = conn.execute(f"SELECT * FROM {q} LIMIT 0")
    cols = [d[0] for d in cur.description]

    ns = make_sample(conn, view, cols, nrows)
    out_cols = []
    for c in cols:
        info = profile_column(conn, view, c)
        if info["kind"] != "skip":
            info["label"] = cz.resolve(view, c) or c
            out_cols.append(info)
    conn.execute("DROP TABLE IF EXISTS _sample")

    print(
        f"  {view}: {nrows:,} 行 / {len(cols)} 列 / 可筛 {len(out_cols)} 列 "
        f"(样本 {ns:,}，耗时 {time.time()-t0:.1f}s)",
        file=sys.stderr,
    )

    return {
        "name": view,
        "rows": nrows,
        "columns": cols,
        "labels": cz.labels_for(view, cols),
        "filters": out_cols,
        "join_keys": [k for k, _ in JOIN_KEYS if k in cols],
        "sample_rows": ns,
    }


def patch_labels(out):
    """只重算 labels，就地写回已有 view_meta.json（不连库）。"""
    with open(out, encoding="utf-8") as f:
        doc = json.load(f)
    n = 0
    nf = 0
    for name, vm in doc["views"].items():
        vm["labels"] = cz.labels_for(name, vm.get("columns", []))
        n += len(vm["labels"])
        for f in vm.get("filters", []):
            f["label"] = cz.resolve(name, f["name"]) or f["name"]
            nf += 1
    # join_keys 的中文名跟着一起更新
    doc["join_keys"] = [[k, cz.KEY_LABELS.get(k, zh)] for k, zh in doc["join_keys"]]
    doc["view_labels"] = {
        v: {"zh": cz.view_label(v), "desc": cz.view_desc(v)}
        for v in doc["views"]
    }
    doc["labels_generated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)

    uncovered = []
    total = 0
    for name, vm in doc["views"].items():
        for c in vm.get("columns", []):
            total += 1
            if c not in vm["labels"]:
                uncovered.append(f"{name}.{c}")
    print(f"已就地更新标签：{len(doc['views'])} 个视图，共 {n} 条（筛选条件 {nf} 条）", file=sys.stderr)
    if uncovered:
        print(f"⚠ 仍未覆盖 {len(uncovered)} 列：{uncovered[:20]}", file=sys.stderr)
    else:
        print(f"✓ 覆盖完整（{total} 个「视图.列」全部有中文名）", file=sys.stderr)
    print(f"写入 {out}  ({os.path.getsize(out)/1024:.0f} KB)", file=sys.stderr)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=False)
    ap.add_argument("--out", default=None)
    ap.add_argument("--labels-only", action="store_true",
                    help="只更新中文标签，不连数据库")
    a = ap.parse_args()
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), "view_meta.json")

    if a.labels_only:
        return patch_labels(out)
    if not a.db:
        ap.error("非 --labels-only 模式必须提供 --db")

    conn = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True, timeout=30)
    names = [v for g in GROUPS for v in g["views"]]
    existing = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('view','table')")}
    missing = [n for n in names if n not in existing]
    if missing:
        print(f"警告：这些对象不存在，已跳过 → {missing}", file=sys.stderr)
        names = [n for n in names if n in existing]

    print(f"剖析 {len(names)} 个视图 …", file=sys.stderr)
    meta = {}
    for n in names:
        meta[n] = profile_view(conn, n)

    doc = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "db": os.path.basename(a.db),
        "sample": SAMPLE,
        "groups": [
            {**g, "views": [v for v in g["views"] if v in meta]} for g in GROUPS
        ],
        "join_keys": JOIN_KEYS,
        "view_labels": {v: {"zh": cz.view_label(v), "desc": cz.view_desc(v)} for v in meta},
        "labels_generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "views": meta,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
    print(f"\n写入 {out}  ({os.path.getsize(out)/1024:.0f} KB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
