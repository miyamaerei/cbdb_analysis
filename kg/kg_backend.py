# -*- coding: utf-8 -*-
"""CBDB 知识图谱 Gradio 应用后端。

三层数据：
  ① 源库 SQLite（cbdb_20260926.sqlite3）→ 朝代清单、人物检索（快，有索引）
  ② Owlready2 quadstore（quadstore/cbdb_dy*.sqlite3）→ 人物详情（TBox v1.0 语义）
  ③ exports/ → 导出目录（查询条件 + 日期命名）

对外提供：dynasty_choices / quad_choices / quad_stats / search_persons /
          person_detail / export_results / run_etl
"""
import csv
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

CBDB = "http://cbdb.example.org/ontology#"
CBDBI = "http://cbdb.example.org/id/"

# 默认源库：相对仓库根目录（仓库可在任意路径克隆后直接运行，不写死本机绝对路径）
DEFAULT_DB = os.path.join(HERE, "..", "cbdb_20260926.sqlite3")
QUAD_DIR = os.path.join(HERE, "quadstore")
EXPORT_DIR = os.path.join(HERE, "exports")

# 结果表头（查询页 / 导出共用）
RESULT_HEADERS = ["personid", "姓名", "拼音", "性别", "生年", "卒年", "指数年",
                  "朝代", "进士", "官员", "亲属", "交遊", "任职", "入仕"]

# 详情各段表头
SECTION_HEADERS = {
    "kin":    ["方向", "亲属关系", "对方", "对方ID", "世代", "史料"],
    "assoc":  ["方向", "关系类型", "对方", "对方ID", "年份", "地点", "场合", "主题", "文体"],
    "tenure": ["官职", "首年", "末年", "地点", "任命类型", "就任状态", "官职类别", "序"],
    "entry":  ["入仕途径", "年份", "名次", "科目", "年龄", "父母状况"],
    "addr":   ["地址类型", "地点", "首年", "末年"],
    "status": ["社会身份", "首年", "末年"],
    "text":   ["角色", "书名", "成书年"],
    "source": ["史料书名", "成书年"],
}

_dyn_cache = {}
_nb_cache = {}
_jinshi_cache = {}
_worlds = {}
_etl_running = False


# ============================================================ 源库
def src_conn(db=None):
    db = db or DEFAULT_DB
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.execute("PRAGMA temp_store=MEMORY")
    return con


def dynasties(db=None):
    """[(dy, chn, en, start, end, persons)]，按人物数降序。"""
    db = db or DEFAULT_DB
    mt = os.path.getmtime(db) if os.path.exists(db) else 0
    if db in _dyn_cache and _dyn_cache[db][0] == mt:
        return _dyn_cache[db][1]
    con = src_conn(db)
    counts = dict(con.execute("SELECT c_dy, COUNT(*) FROM BIOG_MAIN GROUP BY c_dy"))
    rows = []
    for dy, chn, en, s, e in con.execute(
            "SELECT c_dy, c_dynasty_chn, c_dynasty, c_start, c_end FROM DYNASTIES ORDER BY c_dy"):
        rows.append({"dy": dy, "chn": chn or "", "en": en or "", "start": s, "end": e,
                     "persons": counts.get(dy, 0)})
    con.close()
    _dyn_cache[db] = (mt, rows)
    return rows


def dynasty_choices(db=None):
    """Gradio Dropdown 用 [(label, dy)]，只含有人物的朝代。"""
    ds = [d for d in dynasties(db) if d["persons"] > 0]
    ds.sort(key=lambda d: -d["persons"])
    return [(f"{d['dy']} · {d['chn']}（{d['en']}，{d['start']}~{d['end']}）· {d['persons']:,} 人", d["dy"])
            for d in ds]


def dynasty_name(dy, db=None):
    for d in dynasties(db):
        if d["dy"] == dy:
            return d["chn"]
    return f"c_dy={dy}"


def neighborhood(db, dy):
    """1 度邻域（亲属/交遊对端，MERGED 归一后、排除本朝人物）。带缓存。"""
    k = (db, dy)
    if k in _nb_cache:
        return _nb_cache[k]
    con = src_conn(db)
    try:
        con.execute("CREATE TEMP TABLE c_ids(personid INTEGER PRIMARY KEY)")
        con.executemany("INSERT OR IGNORE INTO c_ids VALUES (?)",
                        [(r[0],) for r in con.execute(
                            "SELECT c_personid FROM BIOG_MAIN WHERE c_dy=?", (dy,))])
        mm = dict(con.execute(
            "SELECT c_merged_from_personid, c_personid FROM MERGED_PERSON_DATA"))

        def root(x):
            seen = set()
            while x in mm and x not in seen:
                seen.add(x)
                x = mm[x]
            return x

        core = {root(r[0]) for r in con.execute(
            "SELECT c_personid FROM BIOG_MAIN WHERE c_dy=?", (dy,))}
        ext = set()
        for (x,) in con.execute(
                "SELECT DISTINCT c_kin_id FROM KIN_DATA "
                "WHERE c_personid IN (SELECT personid FROM c_ids) AND c_kin_id>0"):
            ext.add(root(x))
        for (x,) in con.execute(
                "SELECT DISTINCT c_assoc_id FROM ASSOC_DATA "
                "WHERE c_personid IN (SELECT personid FROM c_ids) AND c_assoc_id>0"):
            ext.add(root(x))
        ext -= core
        _nb_cache[k] = ext
        return ext
    finally:
        con.close()


def jinshi_codes(db=None):
    """進士类 entry_code 集合（递归 ENTRY_TYPES 子树 + 名称含「進士」）。"""
    db = db or DEFAULT_DB
    if db in _jinshi_cache:
        return _jinshi_cache[db]
    con = src_conn(db)
    con.execute("""
        CREATE TEMP TABLE js_types AS
        WITH RECURSIVE sub(t) AS (
            SELECT c_entry_type FROM ENTRY_TYPES WHERE c_entry_type_desc_chn LIKE '%進士%'
            UNION
            SELECT e.c_entry_type FROM ENTRY_TYPES e JOIN sub s ON e.c_entry_type_parent_id = s.t
        ) SELECT DISTINCT t FROM sub""")
    codes = {str(r[0]) for r in con.execute(
        "SELECT DISTINCT c_entry_code FROM ENTRY_CODE_TYPE_REL "
        "WHERE c_entry_type IN (SELECT t FROM js_types)")}
    codes |= {str(r[0]) for r in con.execute(
        "SELECT c_entry_code FROM ENTRY_CODES WHERE c_entry_desc_chn LIKE '%進士%'")}
    con.close()
    _jinshi_cache[db] = codes
    return codes


# ============================================================ 检索
def name_variants(s):
    """姓名检索用的「简繁变体」集合。

    CBDB 全库是繁体（王守仁 / 王陽明 / 餘姚），用户常输简体（王阳明 / 余姚），
    直接 LIKE 会 0 命中。这里把输入同时展开成 原样 / 繁体 / 简体 三种写法。
    """
    s = (s or "").strip()
    if not s:
        return []
    out, seen = [], set()

    def add(x):
        if x and x not in seen:
            seen.add(x)
            out.append(x)

    add(s)
    for tgt in ("zh-hant", "zh-hans"):
        try:
            from zhconv import convert
            add(convert(s, tgt))
        except Exception:
            break
    return out


def search_persons(db=None, dy=19, name="", pinyin="", gender="全部",
                   birth_from=None, birth_to=None, death_from=None, death_to=None,
                   index_from=None, index_to=None, jinshi_only=False, official_only=False,
                   match_alt=False, include_neighbors=False, limit=200):
    """返回 (rows, total)：rows 为 RESULT_HEADERS 顺序的二维列表。"""
    db = db or DEFAULT_DB
    con = src_conn(db)
    dyn_names = {d["dy"]: d["chn"] for d in dynasties(db)}
    where, args = [], []

    if include_neighbors:
        nb = neighborhood(db, dy)
        con.execute("DROP TABLE IF EXISTS tmp_scope")
        con.execute("CREATE TEMP TABLE tmp_scope(personid INTEGER PRIMARY KEY)")
        con.executemany("INSERT OR IGNORE INTO tmp_scope VALUES (?)", [(x,) for x in nb])
        where.append("(b.c_dy=? OR b.c_personid IN (SELECT personid FROM tmp_scope))")
        args.append(dy)
    else:
        where.append("b.c_dy=?")
        args.append(dy)

    name = (name or "").strip()
    if name:
        # 简繁变体 OR 匹配（如「王阳明」自动也试「王陽明」）
        conds, vargs = [], []
        for v in name_variants(name):
            conds.append("b.c_name_chn LIKE ?")
            vargs.append(f"%{v}%")
            if match_alt:
                conds.append("b.c_personid IN (SELECT c_personid FROM ALTNAME_DATA "
                             "WHERE c_alt_name_chn LIKE ? OR c_alt_name LIKE ?)")
                vargs += [f"%{v}%", f"%{v}%"]
        where.append("(" + " OR ".join(conds) + ")")
        args += vargs
    if (pinyin or "").strip():
        where.append("b.c_name LIKE ?")
        args.append(f"%{pinyin.strip()}%")
    if gender == "男":
        where.append("b.c_female=0")
    elif gender == "女":
        where.append("b.c_female=1")

    def rng(col, lo, hi):
        # ⚠️ CBDB 里 0 == 未知，且 Gradio 的 Number 组件空值会提交成 0，
        # 必须把 0 当成「未填」，否则会生成 `col>=0 AND col<=0` 导致 0 命中。
        lo = int(lo) if lo else None
        hi = int(hi) if hi else None
        if lo is not None:
            where.append(f"{col} >= ?")
            args.append(lo)
        if hi is not None:
            where.append(f"{col} <= ?")
            args.append(hi)

    rng("b.c_birthyear", birth_from, birth_to)
    rng("b.c_deathyear", death_from, death_to)
    rng("b.c_index_year", index_from, index_to)

    if jinshi_only:
        codes = sorted(jinshi_codes(db))
        if codes:
            where.append("EXISTS (SELECT 1 FROM ENTRY_DATA e WHERE e.c_personid=b.c_personid "
                         f"AND e.c_entry_code IN ({','.join('?' * len(codes))}))")
            args += codes
    if official_only:
        where.append("EXISTS (SELECT 1 FROM POSTED_TO_OFFICE_DATA o "
                     "WHERE o.c_personid=b.c_personid AND o.c_office_id>0)")

    wsql = " AND ".join(where)
    total = con.execute(f"SELECT COUNT(*) FROM BIOG_MAIN b WHERE {wsql}", args).fetchone()[0]
    rows = con.execute(
        f"""SELECT b.c_personid, b.c_name_chn, b.c_name, b.c_female, b.c_birthyear,
                   b.c_deathyear, b.c_index_year, b.c_dy
            FROM BIOG_MAIN b WHERE {wsql} ORDER BY b.c_personid LIMIT ?""",
        args + [int(limit)]).fetchall()

    pids = [r[0] for r in rows]
    con.execute("DROP TABLE IF EXISTS tmp_hit")
    con.execute("CREATE TEMP TABLE tmp_hit(personid INTEGER PRIMARY KEY)")
    con.executemany("INSERT INTO tmp_hit VALUES (?)", [(p,) for p in pids])

    def cnt(sql):
        return dict(con.execute(sql).fetchall())

    c_kin = cnt("SELECT c_personid, COUNT(*) FROM KIN_DATA "
                "WHERE c_personid IN (SELECT personid FROM tmp_hit) AND c_kin_id>0 GROUP BY 1")
    c_asc = cnt("SELECT c_personid, COUNT(*) FROM ASSOC_DATA "
                "WHERE c_personid IN (SELECT personid FROM tmp_hit) AND c_assoc_id>0 GROUP BY 1")
    c_ten = cnt("SELECT c_personid, COUNT(*) FROM POSTED_TO_OFFICE_DATA "
                "WHERE c_personid IN (SELECT personid FROM tmp_hit) AND c_office_id>0 GROUP BY 1")
    c_ent = cnt("SELECT c_personid, COUNT(*) FROM ENTRY_DATA "
                "WHERE c_personid IN (SELECT personid FROM tmp_hit) GROUP BY 1")
    js_codes = sorted(jinshi_codes(db))
    jinshi_ids = set()
    if js_codes and pids:
        jinshi_ids = {r[0] for r in con.execute(
            f"SELECT DISTINCT c_personid FROM ENTRY_DATA WHERE c_personid IN "
            f"(SELECT personid FROM tmp_hit) AND c_entry_code IN ({','.join('?' * len(js_codes))})",
            js_codes)}
    con.close()

    out = []
    for pid, chn, py, fem, by, dyy, iy, cdy in rows:
        out.append([
            pid, chn or "", py or "",
            ("女" if fem == 1 else ("男" if fem == 0 else "")),
            by if by else None, dyy if dyy else None, iy if iy else None,
            dyn_names.get(cdy, cdy),
            "✔" if pid in jinshi_ids else "",
            "✔" if c_ten.get(pid) else "",
            c_kin.get(pid, 0), c_asc.get(pid, 0), c_ten.get(pid, 0), c_ent.get(pid, 0),
        ])
    return out, total


# ============================================================ quadstore
def quadstores():
    """扫描 QUAD_DIR 下的 quadstore + .meta.json 侧车文件。"""
    os.makedirs(QUAD_DIR, exist_ok=True)
    items = []
    for fn in sorted(os.listdir(QUAD_DIR)):
        if not fn.endswith(".sqlite3"):
            continue
        path = os.path.join(QUAD_DIR, fn)
        meta = {}
        mp = path + ".meta.json"
        if os.path.exists(mp):
            try:
                meta = json.load(open(mp, encoding="utf-8"))
            except Exception:
                meta = {}
        dy = meta.get("dy")
        items.append({
            "path": path, "file": fn, "dy": dy,
            "dynasty": meta.get("dynasty") or (f"c_dy={dy}" if dy is not None else "未知朝代"),
            "triples": meta.get("triples"), "built_at": meta.get("built_at"), "meta": meta,
        })
    # 排序：**规模优先**（三元组多的排前），再按构建时间。
    # 之前按 built_at 倒序，结果刚构建的「周」小图谱排在「明」前面成了默认值，
    # 导致用户查 30374（王守仁，明）时提示「图谱中未找到」。
    items.sort(key=lambda x: (-(x["triples"] or 0), x["built_at"] or ""), reverse=False)
    return items


def quad_has_person(path, pid):
    """轻量探测：某 quadstore 里有没有 person/<pid>（不打开 owlready2 World，毫秒级）。

    用于详情页「当前图谱里没有这个人」时去别的图谱里找。
    """
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
        r = con.execute(
            "SELECT 1 FROM datas d JOIN resources r ON r.storid = d.p "
            "WHERE r.iri = ? AND CAST(d.o AS INTEGER) = ? LIMIT 1",
            (CBDB + "personId", int(pid))).fetchone()
        con.close()
        return r is not None
    except Exception:
        return False


def find_quad_with_person(pid, exclude=None):
    """返回第一个含 person/<pid> 的 quadstore 元信息 dict，没有则 None。"""
    for it in quadstores():
        if exclude and it["path"] == exclude:
            continue
        if quad_has_person(it["path"], pid):
            return it
    return None


def quad_choices():
    items = quadstores()
    if not items:
        return [("（尚未构建，请到「⚙️ 构建」页运行 ETL）", "")]
    out = []
    for i in items:
        extra = []
        if i["triples"]:
            extra.append(f"{i['triples']:,} 三元组")
        if i["built_at"]:
            extra.append(i["built_at"])
        label = f"{i['dynasty']} · {i['file']}" + ((" · " + " · ".join(extra)) if extra else "")
        out.append((label, i["path"]))
    return out


def quad_stats(path):
    if not path or not os.path.exists(path):
        return {}
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    total = con.execute(
        "SELECT (SELECT COUNT(*) FROM objs)+(SELECT COUNT(*) FROM datas)").fetchone()[0]
    r = con.execute("SELECT storid FROM resources WHERE iri LIKE '%22-rdf-syntax-ns#type'").fetchone()
    tid = r[0] if r else 6

    def cls(n):
        rr = con.execute("SELECT storid FROM resources WHERE iri=?", (CBDB + n,)).fetchone()
        if not rr:
            return 0
        return con.execute("SELECT COUNT(DISTINCT s) FROM objs WHERE p=? AND o=?",
                           (tid, rr[0])).fetchone()[0]

    classes = {k: cls(k) for k in
               ["Person", "KinshipAssertion", "AssociationEvent", "OfficeTenure",
                "EntryRecord", "AddressClaim", "StatusPeriod", "TextRoleLink",
                "Place", "Office", "Text"]}
    con.close()
    return {"triples": total, "classes": classes,
            "size_mb": round(os.path.getsize(path) / 1e6, 1)}


def get_world(path):
    if path in _worlds:
        return _worlds[path]
    from owlready2 import World
    w = World()
    w.set_backend(filename=path)
    onto = w.get_ontology(CBDB).load()
    inst = w.get_ontology(CBDBI)
    _worlds[path] = (w, onto, inst)
    return _worlds[path]


def close_worlds(path=None):
    if path is None:
        for p, (w, _, _) in list(_worlds.items()):
            try:
                w.close()
            except Exception:
                pass
        _worlds.clear()
    elif path in _worlds:
        try:
            _worlds[path][0].close()
        except Exception:
            pass
        del _worlds[path]


# ------------------------------------------------------------ 详情
def _nm(x, *attrs):
    if x is None:
        return ""
    for a in attrs:
        v = getattr(x, a, None)
        if v not in (None, ""):
            return str(v)
    lab = getattr(x, "label", None)
    if lab:
        return str(lab[0]) if isinstance(lab, (list, tuple)) else str(lab)
    return str(getattr(x, "name", x))


def _pid_of(x):
    m = re.search(r"/(\d+)$", getattr(x, "iri", "") or "")
    return int(m.group(1)) if m else None


def person_detail(quad, pid, db=None):
    """按 TBox v1.0 组织单个人的全部信息。返回 dict 或 None。"""
    if not quad or not os.path.exists(quad):
        return None
    try:
        w, onto, inst = get_world(quad)
        p = None
        try:
            p = inst[f"person/{int(pid)}"]
        except Exception:
            p = None
        if p is None:
            hits = list(onto.search(personId=int(pid)))
            if not hits:
                return None
            p = hits[0]

        def y(v):
            return v if v else None

        basic = {
            "personid": p.personId if p.personId else int(pid),
            "iri": p.iri,
            "nameChn": p.nameChn or "",
            "namePinyin": p.namePinyin or "",
            "isFemale": None if p.isFemale in ([], None) else bool(p.isFemale),
            "birthYear": y(p.birthYear), "deathYear": y(p.deathYear),
            "deathAge": y(p.deathAge), "indexYear": y(p.indexYear),
            "indexYearRule": _nm(p.indexYearRule, "conceptNameChn"),
            "dynastyOf": _nm(p.dynastyOf),
            "floruitStart": y(p.floruitStart), "floruitEnd": y(p.floruitEnd),
        }
        alts = [str(a) for a in (p.altName or [])]

        kin_rows = []
        for k in onto.search(kinSource=p):
            kt = k.kinType
            up, dwn = getattr(kt, "upStep", None), getattr(kt, "dwnStep", None)
            step = f"↑{up}" if up else (f"↓{dwn}" if dwn else "")
            kin_rows.append(["出", _nm(kt, "conceptNameChn"), _nm(k.kinTarget, "nameChn"),
                             _pid_of(k.kinTarget), step, _nm(k.kinSourceText, "textTitleChn")])
        for k in onto.search(kinTarget=p):
            kt = k.kinType
            up, dwn = getattr(kt, "upStep", None), getattr(kt, "dwnStep", None)
            step = f"↓{dwn}" if dwn else (f"↑{up}" if up else "")
            kin_rows.append(["入", _nm(kt, "conceptNameChn"), _nm(k.kinSource, "nameChn"),
                             _pid_of(k.kinSource), step, _nm(k.kinSourceText, "textTitleChn")])

        assoc_rows = []
        for a in onto.search(assocFrom=p):
            assoc_rows.append(["出", _nm(a.assocType, "conceptNameChn"),
                               _nm(a.assocTo, "nameChn"), _pid_of(a.assocTo),
                               y(a.assocFirstYear), _nm(a.assocPlace, "placeNameChn"),
                               _nm(a.assocOccasion, "conceptNameChn"),
                               _nm(a.assocTopic, "conceptNameChn"),
                               _nm(a.assocGenre, "conceptNameChn")])
        for a in onto.search(assocTo=p):
            assoc_rows.append(["入", _nm(a.assocType, "conceptNameChn"),
                               _nm(a.assocFrom, "nameChn"), _pid_of(a.assocFrom),
                               y(a.assocFirstYear), _nm(a.assocPlace, "placeNameChn"),
                               _nm(a.assocOccasion, "conceptNameChn"),
                               _nm(a.assocTopic, "conceptNameChn"),
                               _nm(a.assocGenre, "conceptNameChn")])

        tenure_rows = []
        for t in onto.search(tenureHolder=p):
            tenure_rows.append([
                _nm(t.tenureOffice, "officeNameChn"), y(t.tenureFirstYear), y(t.tenureLastYear),
                "、".join(_nm(x, "placeNameChn") for x in (t.tenurePlace or [])),
                _nm(t.apptType, "conceptNameChn"), _nm(t.assumeStatus),
                _nm(t.officeCategoryOf, "conceptNameChn"), y(t.tenureSequence)])

        entry_rows, jinshi_hit = [], False
        for e in onto.search(entryPerson=p):
            mode = _nm(e.entryMode, "conceptNameChn")
            if "進士" in mode:
                jinshi_hit = True
            entry_rows.append([mode, y(e.entryYear), e.examRank or "", e.examField or "",
                               y(e.entryAge), _nm(e.parentalStatus)])

        addr_rows = [[_nm(c.addrKind, "conceptNameChn"), _nm(c.addrPlace, "placeNameChn"),
                      y(c.addrFirstYear), y(c.addrLastYear)]
                     for c in onto.search(addrPerson=p)]
        status_rows = [[_nm(s.statusConcept, "conceptNameChn"), y(s.statusFirstYear), y(s.statusLastYear)]
                       for s in onto.search(statusPerson=p)]
        text_rows = [[_nm(l.roleType, "conceptNameChn"), _nm(l.roleText, "textTitleChn"),
                      y(getattr(l.roleText, "textYear", None))]
                     for l in onto.search(rolePerson=p)]
        source_rows = [[_nm(t, "textTitleChn"), y(getattr(t, "textYear", None))]
                       for t in (p.sourceOf or [])]

        # 等价类标签（本机无 Java，HermiT 不可用 → 按等价类定义手工计算）
        labels = []
        if tenure_rows:
            labels.append("Official ≡ Person ⊓ ∃tenureHolder⁻¹.OfficeTenure")
        if jinshi_hit:
            labels.append("JinshiHolder ≡ Person ⊓ ∃entryMode.JinshiModes")
        if tenure_rows and jinshi_hit:
            labels.append("JinshiOfficial ≡ JinshiHolder ⊓ Official")
        meta = None
        for i in quadstores():
            if i["path"] == quad:
                meta = i
        if meta and meta["dynasty"] and basic["dynastyOf"] == meta["dynasty"]:
            labels.append(f"DynastyPerson「{meta['dynasty']}」≡ Person ⊓ "
                          f"dynastyOf.value({meta['dynasty']})")
        if basic["isFemale"] is True:
            labels.append("Female ≡ Person ⊓ isFemale.value(true)")
        elif basic["isFemale"] is False:
            labels.append("Male ≡ Person ⊓ isFemale.value(false)")

        return {"basic": basic, "alts": alts, "labels": labels,
                "kin": kin_rows, "assoc": assoc_rows, "tenure": tenure_rows,
                "entry": entry_rows, "addr": addr_rows, "status": status_rows,
                "text": text_rows, "source": source_rows}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def format_basic(d):
    """详情 → Markdown（基本信息块 + 推理标签）。"""
    if d is None:
        return "⚠️ 未选择/未找到 quadstore，请先在「⚙️ 构建」页构建，或在查询页选择已有图谱。"
    if "error" in d:
        return f"⚠️ 载入失败：{d['error']}"
    b = d["basic"]
    sex = {True: "女", False: "男", None: "未详"}[b["isFemale"]]
    lines = [
        f"### {b['nameChn'] or '（无名）'}　`person/{b['personid']}`",
        "",
        f"- **拼音**：{b['namePinyin'] or '—'}　|　**性别**：{sex}　|　**朝代**：{b['dynastyOf'] or '—'}",
        f"- **生年**：{b['birthYear'] or '—'}　|　**卒年**：{b['deathYear'] or '—'}"
        f"　|　**享年**：{b['deathAge'] or '—'}",
        f"- **指数年 index_year**：{b['indexYear'] or '—'}"
        + (f"（规则：{b['indexYearRule']}）" if b["indexYearRule"] else ""),
        f"- **在世活跃期 floruit**：{b['floruitStart'] or '—'} ~ {b['floruitEnd'] or '—'}",
        f"- **IRI**：`{b['iri']}`",
        "",
        "**别名**：" + ("、".join(d["alts"]) if d["alts"] else "（无）"),
        "",
        "**等价类标签**（无 Java → 按定义手工计算，非 HermiT 推理）：",
    ]
    lines += [f"- ✔ {x}" for x in d["labels"]] if d["labels"] else ["- （无）"]
    lines += ["", f"亲属 {len(d['kin'])} · 交遊 {len(d['assoc'])} · 任职 {len(d['tenure'])} · "
                  f"入仕 {len(d['entry'])} · 地址 {len(d['addr'])} · 身份 {len(d['status'])} · "
                  f"著作 {len(d['text'])} · 史料 {len(d['source'])}"]
    return "\n".join(lines)


# ============================================================ 导出
def _safe(s):
    return re.sub(r'[\\/:*?"<>|\s]+', "_", str(s)).strip("_") or "x"


def cond_summary(cond):
    if not cond:
        return "（尚未执行查询）"
    p = [f"朝代=**{cond.get('dynasty_name', cond.get('dy'))}**"]
    if cond.get("name"):
        p.append(f"姓名含「{cond['name']}」")
    if cond.get("pinyin"):
        p.append(f"拼音含「{cond['pinyin']}」")
    if cond.get("gender") and cond["gender"] != "全部":
        p.append(f"性别={cond['gender']}")
    for key, lab in [("birth_from", "生年≥"), ("birth_to", "生年≤"), ("death_from", "卒年≥"),
                     ("death_to", "卒年≤"), ("index_from", "指数年≥"), ("index_to", "指数年≤")]:
        if cond.get(key) is not None:
            p.append(f"{lab}{int(cond[key])}")
    if cond.get("jinshi_only"):
        p.append("仅进士")
    if cond.get("official_only"):
        p.append("仅官员")
    if cond.get("match_alt"):
        p.append("含别名匹配")
    if cond.get("include_neighbors"):
        p.append("含邻域人物")
    p.append(f"上限={cond.get('limit', 200)}")
    return "　|　".join(p)


def cond_slug(cond):
    parts = [_safe(cond.get("dynasty_name") or cond.get("dy") or "全部")]
    if cond.get("name"):
        parts.append(f"姓名含{_safe(cond['name'])}")
    if cond.get("pinyin"):
        parts.append(f"拼音{_safe(cond['pinyin'])}")
    if cond.get("gender") and cond["gender"] != "全部":
        parts.append(_safe(cond["gender"]))
    if cond.get("jinshi_only"):
        parts.append("进士")
    if cond.get("official_only"):
        parts.append("官员")
    if cond.get("birth_from") or cond.get("birth_to"):
        parts.append(f"生{int(cond.get('birth_from') or 0)}-{int(cond.get('birth_to') or 0)}")
    if cond.get("death_from") or cond.get("death_to"):
        parts.append(f"卒{int(cond.get('death_from') or 0)}-{int(cond.get('death_to') or 0)}")
    slug = "_".join(parts)[:60]
    return f"{slug}_{datetime.now().strftime('%Y%m%d')}"


def export_results(cond, rows, formats=("CSV",), with_detail=False, detail_limit=50,
                   quad=None, db=None):
    """导出到 exports/<条件>_<日期>/。返回 (folder, files, message)。"""
    os.makedirs(EXPORT_DIR, exist_ok=True)
    folder = os.path.join(EXPORT_DIR, cond_slug(cond))
    n = 2
    base = folder
    while os.path.exists(folder):
        folder = f"{base}_{n}"
        n += 1
    os.makedirs(folder)
    files = []

    if not rows:
        with open(os.path.join(folder, "README.md"), "w", encoding="utf-8") as f:
            f.write("# 导出结果为空\n\n查询条件：" + cond_summary(cond) + "\n")
        return folder, [], "⚠️ 当前没有可导出的结果，请先在「🔍 查询」页执行一次查询。"

    if "CSV" in formats:
        fp = os.path.join(folder, "results.csv")
        with open(fp, "w", encoding="utf-8-sig", newline="") as f:
            wcsv = csv.writer(f)
            wcsv.writerow(RESULT_HEADERS)
            wcsv.writerows(rows)
        files.append(fp)
    if "JSON" in formats:
        fp = os.path.join(folder, "results.json")
        json.dump({"conditions": cond, "headers": RESULT_HEADERS, "rows": rows},
                  open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        files.append(fp)

    details = []
    if with_detail and quad:
        for r in rows[: int(detail_limit or 50)]:
            d = person_detail(quad, r[0], db)
            if d and "error" not in d:
                details.append(d)

    if details:
        fp = os.path.join(folder, "details.json")
        json.dump(details, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        files.append(fp)
        fp = os.path.join(folder, "details.csv")
        with open(fp, "w", encoding="utf-8-sig", newline="") as f:
            wcsv = csv.writer(f)
            wcsv.writerow(["personid", "姓名"] + [f"{k}条数" for k in
                          ["kin", "assoc", "tenure", "entry", "addr", "status", "text", "source"]]
                          + ["别名", "推理标签"])
            for d in details:
                b = d["basic"]
                wcsv.writerow([b["personid"], b["nameChn"]]
                              + [len(d[k]) for k in
                                 ["kin", "assoc", "tenure", "entry", "addr", "status", "text", "source"]]
                              + ["、".join(d["alts"]), "；".join(d["labels"])])
        files.append(fp)

    json.dump({"exported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               "conditions": cond, "row_count": len(rows),
               "quadstore": quad or "", "source_db": db or DEFAULT_DB},
              open(os.path.join(folder, "conditions.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    files.append(os.path.join(folder, "conditions.json"))

    with open(os.path.join(folder, "README.md"), "w", encoding="utf-8") as f:
        f.write(f"# CBDB 知识图谱导出\n\n- 导出时间：{datetime.now():%Y-%m-%d %H:%M:%S}\n"
                f"- 查询条件：{cond_summary(cond)}\n- 命中行数：{len(rows)}\n"
                f"- 图谱：{quad or '（未选）'}\n- 源库：{db or DEFAULT_DB}\n\n"
                f"## 文件\n- `results.csv/json`：查询命中列表\n"
                f"- `details.csv/json`：前 {len(details)} 人的明细摘要\n"
                f"- `conditions.json`：本次查询条件原始参数\n")

    msg = (f"✅ 已导出 **{len(rows)}** 行"
           + (f"（含 {len(details)} 人明细）" if details else "")
           + f"\n\n📁 `{folder}`\n\n"
           + "\n".join(f"- `{os.path.basename(x)}`（{os.path.getsize(x) / 1024:.1f} KB）" for x in files))
    return folder, files, msg


def export_page(page, cond, tables, note=""):
    """专题页导出。tables: {文件名: (headers, rows)}，可多张表。
    目录名 = <页面>_<条件>_<日期>"""
    import re as _re
    os.makedirs(EXPORT_DIR, exist_ok=True)

    def _s(x):
        return _re.sub(r'[\\/:*?"<>|\s]+', "_", str(x)).strip("_") or "x"

    base = os.path.join(EXPORT_DIR, f"{_s(page)}_{_s(cond)[:50]}_{datetime.now():%Y%m%d}")
    folder, n = base, 2
    while os.path.exists(folder):
        folder = f"{base}_{n}"
        n += 1
    os.makedirs(folder)
    files = []
    for name, (headers, rows) in tables.items():
        if not rows:
            continue
        fp = os.path.join(folder, f"{name}.csv")
        with open(fp, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(headers)
            w.writerows(rows)
        files.append(fp)
        fp = os.path.join(folder, f"{name}.json")
        json.dump({"headers": headers, "rows": rows}, open(fp, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        files.append(fp)
    json.dump({"page": page, "conditions": str(cond), "exported_at":
               datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               "tables": {k: len(v[1]) for k, v in tables.items()}},
              open(os.path.join(folder, "conditions.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    files.append(os.path.join(folder, "conditions.json"))
    with open(os.path.join(folder, "README.md"), "w", encoding="utf-8") as f:
        f.write(f"# {page}\n\n- 条件：{cond}\n- 导出时间：{datetime.now():%Y-%m-%d %H:%M:%S}\n"
                + (f"- 备注：{note}\n" if note else "")
                + "\n## 表\n"
                + "\n".join(f"- `{k}.csv/json`：{len(v[1])} 行" for k, v in tables.items()))
    msg = (f"✅ 已导出到 `{folder}`\n\n"
           + "\n".join(f"- `{os.path.basename(x)}`（{os.path.getsize(x) / 1024:.1f} KB）"
                       for x in files))
    return folder, files, msg


# ============================================================ 运行 ETL
def etl_out_path(dy):
    return os.path.join(QUAD_DIR, f"cbdb_dy{int(dy)}.sqlite3")


def run_etl(db, dy, limit=0):
    """生成器：逐行产出 ETL 日志（供 Gradio 流式显示）。"""
    global _etl_running
    if _etl_running:
        yield "⚠️ 已有构建任务在运行，请等待其结束。"
        return
    _etl_running = True
    close_worlds()
    out = etl_out_path(dy)
    os.makedirs(QUAD_DIR, exist_ok=True)
    cmd = [sys.executable, os.path.join(HERE, "etl_seed_ming.py"),
           "--db", db, "--out", out, "--dy", str(int(dy))]
    if limit:
        cmd += ["--limit-persons", str(int(limit))]
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    buf = [f"$ {' '.join(cmd)}", ""]
    yield "\n".join(buf)
    try:
        proc = subprocess.Popen(cmd, cwd=HERE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace", env=env, bufsize=1)
        for line in iter(proc.stdout.readline, ""):
            buf.append(line.rstrip("\n"))
            yield "\n".join(buf[-400:])
        proc.stdout.close()
        rc = proc.wait()
        buf.append("")
        buf.append(f"[退出码 {rc}]")
        if rc == 0:
            try:
                meta = json.load(open(out + ".meta.json", encoding="utf-8"))
                buf.append(f"✅ 构建完成：{meta.get('triples', 0):,} 三元组，"
                           f"{meta.get('size_mb', 0)} MB，耗时 {meta.get('seconds')}s")
                for k, v in (meta.get("counts") or {}).items():
                    buf.append(f"    {k}: {v:,}")
            except Exception as e:
                buf.append(f"✅ 构建完成（meta 读取失败：{e}）")
            _nb_cache.pop((db, int(dy)), None)
        else:
            buf.append("❌ 构建失败，请检查上方日志。")
        yield "\n".join(buf[-400:])
    except Exception as e:
        yield "\n".join(buf + [f"❌ 启动失败：{type(e).__name__}: {e}"])
    finally:
        _etl_running = False
        try:                      # 重建后作废专题页的谓词子图缓存
            import kg_graph
            kg_graph.drop_index(out)
        except Exception:
            pass
