# -*- coding: utf-8 -*-
"""明朝种子集 ETL（TBox v1.0 FROZEN → Owlready2 ABox）。
核心集 = BIOG_MAIN.c_dy={--dy}（默认 19=明，225,593 人）+ 1 度邻域（亲属/交遊对端）。

ETL 铁律（见 TBOX_v1.0.md §6）：
R1 零值(0/NULL)不落图  R2 MERGED ID 归一  R3 断言 hub 化+直边派生
R4 邻域轻量人物        R5 地址层级用 ADDRESSES 物化  R6 码表全量
R8 年份一律 int

用法：
    python etl_seed_ming.py [--db PATH] [--out PATH] [--dy N] [--limit-persons N]

--dy 朝代码（DYNASTIES.c_dy）：19=明(默认) 15=宋 6=唐 20=清 ...
--out 默认 quadstore/cbdb_dy{N}.sqlite3；结束后另写同名 .meta.json（Gradio 应用据此列出已构建图谱）
"""
import argparse, json, os, sqlite3, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from owlready2 import World  # noqa: E402
from tbox_cbdb import build_tbox, attach_jinshi_modes, CBDB  # noqa: E402

# 默认源库：相对仓库根目录（仓库可在任意路径克隆后直接运行，不写死本机绝对路径）
DEFAULT_DB = os.path.join(HERE, "..", "cbdb_20260926.sqlite3")
DEFAULT_DY = 19   # 明


def default_out(dy):
    return os.path.join(HERE, "quadstore", f"cbdb_dy{dy}.sqlite3")

LOG = lambda *a: print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


# ---------------------------------------------------------------- 源库工具
def open_src(path):
    src = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    src.execute("PRAGMA temp_store=MEMORY")
    return src


def build_id_map(src):
    """R2：MERGED 归一，链式解析到根。"""
    m = {}
    for a, b in src.execute("SELECT c_merged_from_personid, c_personid FROM MERGED_PERSON_DATA"):
        m[a] = b
    def root(x):
        seen = set()
        while x in m and x not in seen:
            seen.add(x)
            x = m[x]
        return x
    return {k: root(k) for k in m}


def norm(pid, id_map):
    return id_map.get(pid, pid)


def pos(v):
    """R1：年份类值，>0 返回 int 否则 None。"""
    if v is None:
        return None
    try:
        v = int(v)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def i(v):
    """安全 int 转换：空串/非法 → None。保留 0（度量列 0 有意义）。"""
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- ETL 主体
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--out", default=None, help="默认 quadstore/cbdb_dy{N}.sqlite3")
    ap.add_argument("--dy", type=int, default=DEFAULT_DY, help="朝代 c_dy（DYNASTIES），19=明")
    ap.add_argument("--limit-persons", type=int, default=0, help="调试用：只加载前 N 个核心人物")
    args = ap.parse_args()
    if not args.out:
        args.out = default_out(args.dy)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    t0 = time.time()
    src = open_src(args.db)

    LOG("0/10 world + TBox ...")
    world = World()
    world.set_backend(filename=args.out)
    onto, ns = build_tbox(world)
    C = lambda name: onto[name]

    id_map = build_id_map(src)
    LOG(f"    id_map: {len(id_map):,} 条归一映射")

    # ---- 核心人物集 → 临时表（供各断言 JOIN） ----
    LOG(f"1/10 核心人物集（c_dy={args.dy}）...")
    core = [r[0] for r in src.execute(
        "SELECT c_personid FROM BIOG_MAIN WHERE c_dy=? ORDER BY c_personid", (args.dy,))]
    if args.limit_persons:
        core = core[: args.limit_persons]
    core_set = set(core)
    core_set_norm = {norm(p, id_map) for p in core}   # 归一后：用于邻域判重
    skip_ids = set(id_map.keys())                     # C5 补丁：被合并的作废 ID 不单独建节点
    src.execute("CREATE TEMP TABLE core_ids(personid INTEGER PRIMARY KEY)")
    src.executemany("INSERT OR IGNORE INTO core_ids VALUES (?)", [(p,) for p in core])
    LOG(f"    核心人物: {len(core):,}")

    # ---- 2 码表 → 概念个体（R6 全量） ----
    LOG("2/10 码表概念个体 ...")
    concept_refs = {}   # (scheme, code_str) -> individual，供断言期引用

    def mk_concept(cls_name, scheme, code, zh, en=None, extra=None):
        ind = C(cls_name)(f"concept/{scheme}/{code}", namespace=ns)
        if zh:
            ind.conceptNameChn = str(zh)
        if en:
            ind.conceptNameEn = str(en)
        if extra:
            extra(ind)
        concept_refs[(scheme, str(code))] = ind
        return ind

    # KinType 488（带度量）
    for code, chn, en, up, dwn, mar, col in src.execute(
        "SELECT c_kincode, c_kinrel_chn, c_kinrel, c_upstep, c_dwnstep, c_marstep, c_colstep FROM KINSHIP_CODES"):
        def ex(up=up, dwn=dwn, mar=mar, col=col):
            def one(ind, val):
                iv = i(val)
                if iv is not None:
                    return iv
                return None
            def _apply(ind):
                for attr, val in (("upStep", up), ("dwnStep", dwn), ("marStep", mar), ("colStep", col)):
                    iv = one(ind, val)
                    if iv is not None:
                        setattr(ind, attr, iv)
            return _apply
        mk_concept("KinType", "kin", code, chn, en, ex)

    for code, chn, en, pair in src.execute(
        "SELECT c_assoc_code, c_assoc_desc_chn, c_assoc_desc, c_assoc_pair FROM ASSOC_CODES"):
        pv = i(pair)
        def ex(ind, pv=pv):
            if pv is not None:
                ind.assocPairCode = pv
        mk_concept("AssocType", "assoc", code, chn, en, ex)

    for code, chn, en in src.execute("SELECT c_entry_code, c_entry_desc_chn, c_entry_desc FROM ENTRY_CODES"):
        mk_concept("EntryModeConcept", "entry", code, chn, en)
    for t, chn, en in src.execute("SELECT c_entry_type, c_entry_type_desc_chn, c_entry_type_desc FROM ENTRY_TYPES"):
        mk_concept("EntryModeConcept", "entry", f"t{t}", chn, en)

    for nid, chn, en in src.execute(
        "SELECT c_office_type_node_id, c_office_type_desc_chn, c_office_type_desc FROM OFFICE_TYPE_TREE"):
        mk_concept("OfficeTypeConcept", "officetype", nid, chn, en)

    for code, chn, en in src.execute("SELECT c_status_code, c_status_desc_chn, c_status_desc FROM STATUS_CODES"):
        mk_concept("StatusConcept", "status", code, chn, en)
    for t, chn, en in src.execute("SELECT c_status_type_code, c_status_type_chn, c_status_type_desc FROM STATUS_TYPES"):
        mk_concept("StatusConcept", "status", f"t{t}", chn, en)

    for code, chn, en in src.execute("SELECT c_addr_type, c_addr_desc_chn, c_addr_desc FROM BIOG_ADDR_CODES"):
        mk_concept("AddrKind", "addrkind", code, chn, en)

    admincat = {}
    for code, hz, py in src.execute("SELECT c_admin_cat_code, c_admin_cat_hz, c_admin_cat_py FROM ADMIN_CAT_CODES"):
        admincat[str(code)] = mk_concept("AdminCatType", "admincat", code, hz, py)

    for code, chn, en in src.execute(
        "SELECT c_text_cat_code, c_text_cat_desc_chn, c_text_cat_desc FROM TEXT_BIBLCAT_CODES"):
        mk_concept("TextCategory", "textcat", code, chn, en)
    for t, chn, en in src.execute(
        "SELECT c_text_cat_type_id, c_text_cat_type_desc_chn, c_text_cat_type_desc FROM TEXT_BIBLCAT_TYPES"):
        mk_concept("TextCategory", "textcat", f"t{t}", chn, en)

    for code, chn, en in src.execute("SELECT c_role_id, c_role_desc_chn, c_role_desc FROM TEXT_ROLE_CODES"):
        mk_concept("RoleType", "role", code, chn, en)
    for code, chn, en in src.execute("SELECT c_topic_code, c_topic_desc_chn, c_topic_desc FROM SCHOLARLYTOPIC_CODES"):
        mk_concept("TopicType", "topic", code, chn, en)
    for code, chn, en in src.execute("SELECT c_occasion_code, c_occasion_desc_chn, c_occasion_desc FROM OCCASION_CODES"):
        mk_concept("OccasionType", "occasion", code, chn, en)
    for code, chn, en in src.execute("SELECT c_lit_genre_code, c_lit_genre_desc_chn, c_lit_genre_desc FROM LITERARYGENRE_CODES"):
        mk_concept("GenreType", "genre", code, chn, en)

    for code, chn, en in src.execute("SELECT c_appt_code, c_appt_desc_chn, c_appt_desc FROM APPOINTMENT_CODES"):
        mk_concept("AppointmentType", "appt", code, chn, en)
    for t, chn, en in src.execute("SELECT c_appt_type_code, c_appt_type_desc_chn, c_appt_type_desc FROM APPOINTMENT_TYPES"):
        mk_concept("AppointmentType", "appt", f"t{t}", chn, en)

    for code, chn, en in src.execute("SELECT c_office_category_id, c_category_desc_chn, c_category_desc FROM OFFICE_CATEGORIES"):
        mk_concept("OfficeCategory", "officecat", code, chn, en)

    indexrule = {}
    for code, hz, en in src.execute(
        "SELECT c_index_year_type_code, c_index_year_type_hz, c_index_year_type_desc FROM INDEXYEAR_TYPE_CODES"):
        c = i(code)
        if c is None:
            continue
        indexrule[c] = mk_concept("IndexYearRule", "indexyear", c, hz, en)

    # 概念层级（conceptBroader，物化直接边）
    broader_edges = 0
    def add_broader(child_scheme_code, parent_scheme_code):
        nonlocal broader_edges
        a = concept_refs.get(child_scheme_code)
        b = concept_refs.get(parent_scheme_code)
        if a is not None and b is not None and a is not b:
            a.conceptBroader.append(b)
            broader_edges += 1

    for code, t in src.execute("SELECT c_entry_code, c_entry_type FROM ENTRY_CODE_TYPE_REL"):
        add_broader(("entry", str(code)), ("entry", f"t{t}"))
    for t, p in src.execute("SELECT c_entry_type, c_entry_type_parent_id FROM ENTRY_TYPES WHERE c_entry_type_parent_id IS NOT NULL AND c_entry_type_parent_id<>''"):
        add_broader(("entry", f"t{t}"), ("entry", f"t{p}"))
    for nid, p in src.execute("SELECT c_office_type_node_id, c_parent_id FROM OFFICE_TYPE_TREE WHERE c_parent_id IS NOT NULL"):
        add_broader(("officetype", str(nid)), ("officetype", str(p)))
    for code, t in src.execute("SELECT c_status_code, c_status_type_code FROM STATUS_CODE_TYPE_REL"):
        add_broader(("status", str(code)), ("status", f"t{t}"))
    for code, p in src.execute("SELECT c_text_cat_code, c_text_cat_parent_id FROM TEXT_BIBLCAT_CODES WHERE c_text_cat_parent_id IS NOT NULL AND c_text_cat_parent_id<>0"):
        add_broader(("textcat", str(code)), ("textcat", str(p)))
    for code, t in src.execute("SELECT c_text_cat_code, c_text_cat_type_id FROM TEXT_BIBLCAT_CODE_TYPE_REL"):
        add_broader(("textcat", str(code)), ("textcat", f"t{t}"))
    for t, code in src.execute("SELECT c_appt_type_code, c_appt_code FROM APPOINTMENT_CODE_TYPE_REL"):
        add_broader(("appt", str(code)), ("appt", f"t{t}"))
    LOG(f"    概念个体: {len(concept_refs):,}；broader 边: {broader_edges:,}")

    # ---- 3 Dynasty 全量 ----
    LOG("3/10 Dynasty ...")
    dyn = {}
    for dy, chn, en in src.execute("SELECT c_dy, c_dynasty_chn, c_dynasty FROM DYNASTIES WHERE c_dy IS NOT NULL"):
        iv = i(dy)
        if iv is None:
            continue
        d = C("Dynasty")(f"dynasty/{iv}", namespace=ns)
        dyn[iv] = d
        from owlready2 import locstr
        if chn: d.label.append(locstr(str(chn), "zh"))
        if en: d.label.append(locstr(str(en), "en"))

    # ---- 4 核心人物 ----
    LOG("4/10 核心人物实例 ...")
    P = lambda pid: C("Person")(f"person/{pid}", namespace=ns)
    n = 0
    cur = src.execute("""
        SELECT c_personid, c_name_chn, c_name, c_female, c_birthyear, c_deathyear, c_death_age,
               c_index_year, c_index_year_type_code, c_dy, c_fl_earliest_year, c_fl_latest_year
        FROM BIOG_MAIN WHERE c_personid IN (SELECT personid FROM core_ids)""")
    while True:
        rows = cur.fetchmany(5000)
        if not rows:
            break
        for pid, chn, py, fem, by, dy_, dage, iy, iyt, cdy, fl1, fl2 in rows:
            if pid in skip_ids:      # C5：已被合并的 ID，属性并入目标节点，此处跳过
                continue
            p = P(pid)
            p.personId = int(pid)
            if chn: p.nameChn = str(chn)
            if py: p.namePinyin = str(py)
            if fem is not None: p.isFemale = bool(fem)
            v = pos(by)
            if v: p.birthYear = v
            v = pos(dy_)
            if v: p.deathYear = v
            v = pos(dage)
            if v: p.deathAge = v
            v = pos(iy)
            if v: p.indexYear = v
            iv = i(iyt)
            if iv is not None and iv in indexrule:
                p.indexYearRule = indexrule[iv]
            iv = i(cdy)
            if iv is not None and iv in dyn:
                p.dynastyOf = dyn[iv]
            v = pos(fl1)
            if v: p.floruitStart = v
            v = pos(fl2)
            if v: p.floruitEnd = v
            n += 1
        if n % 50000 == 0:
            world.graph.commit()
            LOG(f"    persons {n:,} ({time.time()-t0:.0f}s)")
    world.graph.commit()
    LOG(f"    核心人物完成: {n:,} ({time.time()-t0:.0f}s)")

    # ---- 5 邻域人物（KIN/ASSOC 对端，R4 轻量） ----
    LOG("5/10 邻域人物 ...")
    ext_ids = set()
    for (x,) in src.execute("SELECT DISTINCT c_kin_id FROM KIN_DATA WHERE c_personid IN (SELECT personid FROM core_ids) AND c_kin_id>0"):
        x = norm(x, id_map)
        if x not in core_set_norm:
            ext_ids.add(x)
    for (x,) in src.execute("SELECT DISTINCT c_assoc_id FROM ASSOC_DATA WHERE c_personid IN (SELECT personid FROM core_ids) AND c_assoc_id>0"):
        x = norm(x, id_map)
        if x not in core_set_norm:
            ext_ids.add(x)
    en = 0
    if ext_ids:
        src.execute("CREATE TEMP TABLE ext_ids(personid INTEGER PRIMARY KEY)")
        src.executemany("INSERT OR IGNORE INTO ext_ids VALUES (?)", [(x,) for x in ext_ids])
        for pid, chn, py, cdy in src.execute("""
            SELECT c_personid, c_name_chn, c_name, c_dy FROM BIOG_MAIN
            WHERE c_personid IN (SELECT personid FROM ext_ids)"""):
            p = P(pid)
            p.personId = int(pid)
            if chn: p.nameChn = str(chn)
            if py: p.namePinyin = str(py)
            iv = i(cdy)
            if iv is not None and iv in dyn:
                p.dynastyOf = dyn[iv]
            en += 1
    LOG(f"    邻域人物: {en:,}")

    # ---- 6 按需收集 Place/Office/Text ID 并建实例 ----
    LOG("6/10 Place / Office / Text 实例 ...")
    addr_ids, office_ids, text_ids = set(), set(), set()
    for (x,) in src.execute("SELECT DISTINCT c_addr_id FROM BIOG_ADDR_DATA WHERE c_personid IN (SELECT personid FROM core_ids) AND c_addr_id>0"):
        addr_ids.add(x)
    for (x,) in src.execute("""SELECT DISTINCT a.c_addr_id FROM POSTED_TO_ADDR_DATA a
            JOIN POSTED_TO_OFFICE_DATA o ON a.c_posting_id=o.c_posting_id AND a.c_office_id=o.c_office_id
            WHERE o.c_personid IN (SELECT personid FROM core_ids) AND a.c_addr_id>0"""):
        addr_ids.add(x)
    for (x,) in src.execute("SELECT DISTINCT c_addr_id FROM ASSOC_DATA WHERE c_personid IN (SELECT personid FROM core_ids) AND c_addr_id>0"):
        addr_ids.add(x)
    for (x,) in src.execute("SELECT DISTINCT c_office_id FROM POSTED_TO_OFFICE_DATA WHERE c_personid IN (SELECT personid FROM core_ids) AND c_office_id>0"):
        office_ids.add(x)
    for (x,) in src.execute("SELECT DISTINCT c_source FROM KIN_DATA WHERE c_personid IN (SELECT personid FROM core_ids) AND c_source>0"):
        text_ids.add(x)
    for (x,) in src.execute("SELECT DISTINCT c_textid FROM BIOG_TEXT_DATA WHERE c_personid IN (SELECT personid FROM core_ids) AND c_textid>0"):
        text_ids.add(x)
    for (x,) in src.execute("SELECT DISTINCT c_textid FROM BIOG_SOURCE_DATA WHERE c_personid IN (SELECT personid FROM core_ids) AND c_textid>0"):
        text_ids.add(x)

    # Place：层级 belongsTo 需把祖先地址也建出来（R5）
    addr_all = set(addr_ids)
    belongs_rows = {}
    src.execute("CREATE TEMP TABLE addr_seed(addr_id INTEGER PRIMARY KEY)")
    src.executemany("INSERT OR IGNORE INTO addr_seed VALUES (?)", [(x,) for x in addr_ids])
    frontier = list(addr_ids)
    while frontier:
        src.execute("DROP TABLE IF EXISTS frontier")
        src.execute("CREATE TEMP TABLE frontier(addr_id INTEGER PRIMARY KEY)")
        src.executemany("INSERT OR IGNORE INTO frontier VALUES (?)", [(x,) for x in frontier])
        nxt = []
        for row in src.execute("""
            SELECT c_addr_id, belongs1_ID, belongs2_ID, belongs3_ID, belongs4_ID, belongs5_ID
            FROM ADDRESSES WHERE c_addr_id IN (SELECT addr_id FROM frontier)"""):
            belongs_rows[row[0]] = row[1:]
            for b in row[1:]:
                if b and b > 0 and b not in addr_all:
                    addr_all.add(b)
                    nxt.append(b)
        frontier = nxt
    LOG(f"    地址(含祖先): {len(addr_all):,}（直接引用 {len(addr_ids):,}）")

    PL = lambda aid: C("Place")(f"place/{aid}", namespace=ns)
    src.execute("CREATE TEMP TABLE addr_all(addr_id INTEGER PRIMARY KEY)")
    src.executemany("INSERT OR IGNORE INTO addr_all VALUES (?)", [(x,) for x in addr_all])
    np_ = 0
    cur = src.execute("""
        SELECT c_addr_id, c_name_chn, c_name, c_admin_type, x_coord, y_coord, c_firstyear, c_lastyear
        FROM ADDR_CODES WHERE c_addr_id IN (SELECT addr_id FROM addr_all)""")
    while True:
        rows = cur.fetchmany(5000)
        if not rows:
            break
        for aid, chn, en_, atype, x, y, fy, ly in rows:
            pl = PL(aid)
            if chn: pl.placeNameChn = str(chn)
            if en_: pl.placeNameEn = str(en_)
            if atype is not None and str(atype) in admincat:
                pl.placeAdminCat = admincat[str(atype)]
            if x is not None: pl.xCoord = float(x)
            if y is not None: pl.yCoord = float(y)
            v = pos(fy)
            if v: pl.placeFirstYear = v
            v = pos(ly)
            if v: pl.placeLastYear = v
            np_ += 1
    # belongsTo 物化（belongs1..5 全部直接边）
    nb = 0
    for aid, bs in belongs_rows.items():
        pla = PL(aid)
        for b in bs:
            if b and b > 0:
                pla.belongsTo.append(PL(b))
                nb += 1
    LOG(f"    Place: {np_:,}；belongsTo 边: {nb:,}")

    OF = lambda oid: C("Office")(f"office/{oid}", namespace=ns)
    src.execute("CREATE TEMP TABLE office_seed(office_id INTEGER PRIMARY KEY)")
    src.executemany("INSERT OR IGNORE INTO office_seed VALUES (?)", [(x,) for x in office_ids])
    no_ = 0
    cur = src.execute("""
        SELECT c_office_id, c_office_chn, c_office_trans, c_office_pinyin
        FROM OFFICE_CODES WHERE c_office_id IN (SELECT office_id FROM office_seed)""")
    while True:
        rows = cur.fetchmany(5000)
        if not rows:
            break
        for oid, chn, trans, py in rows:
            o = OF(oid)
            if chn: o.officeNameChn = str(chn)
            ename = trans or py
            if ename: o.officeNameEn = str(ename)
            no_ += 1
    not_ = 0
    for oid, tid in src.execute("""
        SELECT c_office_id, c_office_tree_id FROM OFFICE_CODE_TYPE_REL
        WHERE c_office_id IN (SELECT office_id FROM office_seed)"""):
        t = concept_refs.get(("officetype", str(tid)))
        if t is not None:
            OF(oid).officeType.append(t)
            not_ += 1
    LOG(f"    Office: {no_:,}；officeType 边: {not_:,}")

    TX = lambda tid: C("Text")(f"text/{tid}", namespace=ns)
    src.execute("CREATE TEMP TABLE text_seed(text_id INTEGER PRIMARY KEY)")
    src.executemany("INSERT OR IGNORE INTO text_seed VALUES (?)", [(x,) for x in text_ids])
    nt = 0
    extant_map = {0: "enum/extant/0", 1: "enum/extant/1", 2: "enum/extant/2", 3: "enum/extant/3"}
    cur = src.execute("""
        SELECT c_textid, c_title_chn, c_title, c_text_year, c_bibl_cat_code, c_extant
        FROM TEXT_CODES WHERE c_textid IN (SELECT text_id FROM text_seed)""")
    while True:
        rows = cur.fetchmany(5000)
        if not rows:
            break
        for tid, chn, en_, yr, cat, ex in rows:
            t = TX(tid)
            if chn: t.textTitleChn = str(chn)
            if en_: t.textTitleEn = str(en_)
            v = pos(yr)
            if v: t.textYear = v
            c = concept_refs.get(("textcat", str(cat)))
            if cat and c is not None: t.textCategory.append(c)
            iv = i(ex)
            if iv is not None and iv in extant_map:
                t.extantStatus = ns[extant_map[iv]]
            nt += 1
    LOG(f"    Text: {nt:,}")

    # ---- 7 断言加载 ----
    LOG("7/10 断言（Kin/Assoc/Entry/Tenure/AddrClaim/Status/TextRole）...")
    kin_map_warn = set()

    # 7a KinshipAssertion
    nk = 0
    cur = src.execute("""
        SELECT rowid, c_personid, c_kin_id, c_kin_code, c_source FROM KIN_DATA
        WHERE c_personid IN (SELECT personid FROM core_ids)""")
    while True:
        rows = cur.fetchmany(5000)
        if not rows:
            break
        for rid, pid, kid, kc, srcid in rows:
            a = norm(pid, id_map); b = norm(kid, id_map) if kid else None
            kt = concept_refs.get(("kin", str(kc)))
            if b is None or b == 0 or kt is None:
                if kt is None and kc not in kin_map_warn:
                    kin_map_warn.add(kc)
                continue
            ka = C("KinshipAssertion")(f"kinassert/{rid}", namespace=ns)
            ka.kinSource = P(a); ka.kinTarget = P(b); ka.kinType = kt
            if srcid and srcid > 0:
                ka.kinSourceText = TX(srcid)
            P(a).hasKin.append(P(b))
            P(b).kinOf.append(P(a))
            nk += 1
        if nk % 50000 < 5000:
            world.graph.commit()
            LOG(f"    kin {nk:,} ({time.time()-t0:.0f}s)")
    world.graph.commit()
    LOG(f"    KinshipAssertion: {nk:,}")

    # 7b AssociationEvent
    na = 0
    cur = src.execute("""
        SELECT rowid, c_personid, c_assoc_id, c_assoc_code, c_addr_id,
               c_occasion_code, c_topic_code, c_litgenre_code, c_assoc_first_year
        FROM ASSOC_DATA WHERE c_personid IN (SELECT personid FROM core_ids)""")
    while True:
        rows = cur.fetchmany(5000)
        if not rows:
            break
        for rid, pid, aid, ac, addr, occ, topic, genre, fy in rows:
            a = norm(pid, id_map); b = norm(aid, id_map) if aid else None
            at = concept_refs.get(("assoc", str(ac)))
            if b is None or b == 0 or at is None:
                continue
            ev = C("AssociationEvent")(f"assoc/{rid}", namespace=ns)
            ev.assocFrom = P(a); ev.assocTo = P(b); ev.assocType = at
            if addr and addr > 0: ev.assocPlace = PL(addr)
            o = concept_refs.get(("occasion", str(occ)))
            if occ and o is not None: ev.assocOccasion = o
            tp = concept_refs.get(("topic", str(topic)))
            if topic and tp is not None: ev.assocTopic = tp
            g = concept_refs.get(("genre", str(genre)))
            if genre and g is not None: ev.assocGenre = g
            v = pos(fy)
            if v: ev.assocFirstYear = v
            P(a).hasAssociate.append(P(b))
            P(b).associateOf.append(P(a))
            na += 1
    LOG(f"    AssociationEvent: {na:,}")

    # 7c EntryRecord
    ner = 0
    cur = src.execute("""
        SELECT rowid, c_personid, c_entry_code, c_year, c_exam_rank, c_exam_field, c_age, c_parental_status_code
        FROM ENTRY_DATA WHERE c_personid IN (SELECT personid FROM core_ids)""")
    while True:
        rows = cur.fetchmany(5000)
        if not rows:
            break
        for rid, pid, ec, yr, rank, field, age, pstat in rows:
            em = concept_refs.get(("entry", str(ec)))
            if em is None:
                continue
            e = C("EntryRecord")(f"entry/{rid}", namespace=ns)
            e.entryPerson = P(norm(pid, id_map)); e.entryMode = em
            v = pos(yr)
            if v: e.entryYear = v
            if rank: e.examRank = str(rank)
            if field: e.examField = str(field)
            v = pos(age)
            if v: e.entryAge = v
            iv = i(pstat)
            if iv is not None and 1 <= iv <= 7:
                e.parentalStatus = ns[f"enum/parental/{iv}"]
            ner += 1
    LOG(f"    EntryRecord: {ner:,}")

    # 7d OfficeTenure（+ tenurePlace 来自 POSTED_TO_ADDR_DATA 按 posting+office 匹配）
    addr_by_posting = {}
    for pid_, oid_, aid_ in src.execute("""
        SELECT a.c_posting_id, a.c_office_id, a.c_addr_id FROM POSTED_TO_ADDR_DATA a
        JOIN POSTED_TO_OFFICE_DATA o ON a.c_posting_id=o.c_posting_id AND a.c_office_id=o.c_office_id
        WHERE o.c_personid IN (SELECT personid FROM core_ids) AND a.c_addr_id>0"""):
        addr_by_posting.setdefault((pid_, oid_), []).append(aid_)

    nto = 0
    cur = src.execute("""
        SELECT rowid, c_posting_id, c_personid, c_office_id, c_firstyear, c_lastyear,
               c_appt_code, c_assume_office_code, c_office_category_id, c_sequence
        FROM POSTED_TO_OFFICE_DATA WHERE c_personid IN (SELECT personid FROM core_ids)""")
    while True:
        rows = cur.fetchmany(5000)
        if not rows:
            break
        for rid, postid, pid, oid, fy, ly, appt, assume, ocat, seq in rows:
            if not oid or oid == 0:
                continue
            # C9：c_posting_id 非唯一（一次 posting 可挂多个 office），IRI 追加 rowid 保唯一
            t = C("OfficeTenure")(f"tenure/{postid}-{rid}", namespace=ns)
            t.tenureHolder = P(norm(pid, id_map)); t.tenureOffice = OF(oid)
            for aid_ in addr_by_posting.get((postid, oid), []):
                t.tenurePlace.append(PL(aid_))
            v = pos(fy)
            if v: t.tenureFirstYear = v
            v = pos(ly)
            if v: t.tenureLastYear = v
            v = pos(seq) if seq is not None else (0 if seq == 0 else None)
            if v: t.tenureSequence = v
            ap = concept_refs.get(("appt", str(appt)))
            if appt and ap is not None: t.apptType = ap
            iv = i(assume)
            if iv is not None and 1 <= iv <= 5:      # R1：0=未詳 不落图
                t.assumeStatus = ns[f"enum/assume/{iv}"]
            oc = concept_refs.get(("officecat", str(ocat)))
            if ocat and oc is not None: t.officeCategoryOf = oc
            nto += 1
        if nto % 50000 < 5000:
            world.graph.commit()
            LOG(f"    tenure {nto:,} ({time.time()-t0:.0f}s)")
    world.graph.commit()
    LOG(f"    OfficeTenure: {nto:,}")

    # 7e AddressClaim
    nac = 0
    cur = src.execute("""
        SELECT rowid, c_personid, c_addr_id, c_addr_type, c_firstyear, c_lastyear
        FROM BIOG_ADDR_DATA WHERE c_personid IN (SELECT personid FROM core_ids)""")
    while True:
        rows = cur.fetchmany(5000)
        if not rows:
            break
        for rid, pid, aid, at, fy, ly in rows:
            ak = concept_refs.get(("addrkind", str(at)))
            if not aid or aid == 0 or ak is None:
                continue
            c = C("AddressClaim")(f"addrclaim/{rid}", namespace=ns)
            c.addrPerson = P(norm(pid, id_map)); c.addrPlace = PL(aid); c.addrKind = ak
            v = pos(fy)
            if v: c.addrFirstYear = v
            v = pos(ly)
            if v: c.addrLastYear = v
            nac += 1
    LOG(f"    AddressClaim: {nac:,}")

    # 7f StatusPeriod
    nsp = 0
    cur = src.execute("""
        SELECT rowid, c_personid, c_status_code, c_firstyear, c_lastyear
        FROM STATUS_DATA WHERE c_personid IN (SELECT personid FROM core_ids)""")
    while True:
        rows = cur.fetchmany(5000)
        if not rows:
            break
        for rid, pid, sc, fy, ly in rows:
            sk = concept_refs.get(("status", str(sc)))
            if sk is None:
                continue
            s = C("StatusPeriod")(f"status/{rid}", namespace=ns)
            s.statusPerson = P(norm(pid, id_map)); s.statusConcept = sk
            v = pos(fy)
            if v: s.statusFirstYear = v
            v = pos(ly)
            if v: s.statusLastYear = v
            nsp += 1
    LOG(f"    StatusPeriod: {nsp:,}")

    # 7g TextRoleLink
    ntr = 0
    cur = src.execute("""
        SELECT rowid, c_personid, c_textid, c_role_id FROM BIOG_TEXT_DATA
        WHERE c_personid IN (SELECT personid FROM core_ids) AND c_textid>0""")
    while True:
        rows = cur.fetchmany(5000)
        if not rows:
            break
        for rid, pid, tid, role in rows:
            rt = concept_refs.get(("role", str(role)))
            if rt is None:
                continue
            l = C("TextRoleLink")(f"textrole/{rid}", namespace=ns)
            l.rolePerson = P(norm(pid, id_map)); l.roleText = TX(tid); l.roleType = rt
            ntr += 1
    LOG(f"    TextRoleLink: {ntr:,}")

    # ---- 8 sourceOf 直边（C2） ----
    LOG("8/10 sourceOf 直边 ...")
    nso = 0
    cur = src.execute("""
        SELECT DISTINCT c_personid, c_textid FROM BIOG_SOURCE_DATA
        WHERE c_personid IN (SELECT personid FROM core_ids) AND c_textid>0""")
    while True:
        rows = cur.fetchmany(10000)
        if not rows:
            break
        for pid, tid in rows:
            P(norm(pid, id_map)).sourceOf.append(TX(tid))
            nso += 1
    LOG(f"    sourceOf 边: {nso:,}")

    # ---- 9 altName ----
    LOG("9/10 altName ...")
    nal = 0
    cur = src.execute("""
        SELECT c_personid, c_alt_name_chn, c_alt_name FROM ALTNAME_DATA
        WHERE c_personid IN (SELECT personid FROM core_ids)""")
    while True:
        rows = cur.fetchmany(10000)
        if not rows:
            break
        for pid, chn, py in rows:
            v = chn or py
            if v:
                P(norm(pid, id_map)).altName.append(str(v))
                nal += 1
    LOG(f"    altName: {nal:,}")

    # ---- 10 JinshiModes（C4）+ 对账 ----
    LOG("10/10 JinshiModes 计算 + 对账 ...")
    src.execute("""
        CREATE TEMP TABLE jinshi_types AS
        WITH RECURSIVE sub(t) AS (
            SELECT c_entry_type FROM ENTRY_TYPES WHERE c_entry_type_desc_chn LIKE '%進士%'
            UNION
            SELECT e.c_entry_type FROM ENTRY_TYPES e JOIN sub s ON e.c_entry_type_parent_id = s.t
        ) SELECT DISTINCT t FROM sub""")
    jinshi_codes = set()
    for (code,) in src.execute("""
        SELECT DISTINCT c_entry_code FROM ENTRY_CODE_TYPE_REL
        WHERE c_entry_type IN (SELECT t FROM jinshi_types)"""):
        jinshi_codes.add(str(code))
    for (code,) in src.execute("SELECT c_entry_code FROM ENTRY_CODES WHERE c_entry_desc_chn LIKE '%進士%'"):
        jinshi_codes.add(str(code))
    jinshi_inds = [concept_refs[("entry", c)] for c in sorted(jinshi_codes) if ("entry", c) in concept_refs]
    attach_jinshi_modes(onto, jinshi_inds)
    LOG(f"    進士词条: {len(jinshi_inds):,} 个（OneOf 已挂）")

    # 落盘提交（owlready2 quadstore 缓存→sqlite）
    LOG("落盘 world.graph.commit() ...")
    world.graph.commit()

    LOG("==== ETL 载入计数（与 OWL 侧对账请运行 kg_stats.py）====")
    sql_core = len(core)
    for name, cnt in [
        ("Person 核心", sql_core), ("Person 邻域", en),
        ("KinshipAssertion", nk), ("AssociationEvent", na),
        ("OfficeTenure", nto), ("EntryRecord", ner),
        ("AddressClaim", nac), ("StatusPeriod", nsp),
        ("TextRoleLink", ntr), ("Place", np_),
        ("Office", no_), ("Text", nt),
        ("sourceOf 边", nso), ("altName", nal),
    ]:
        LOG(f"    {name}: {cnt:,}")
    LOG(f"总耗时 {time.time()-t0:.0f}s")
    # 释放 quadstore 连接（之后 kg_stats.py / Gradio 才能独占读取）
    world.close()

    # 元数据 sidecar：Gradio 应用据此列出「已构建的知识图谱」
    try:
        dname = None
        for (chn, en_,) in src.execute(
                "SELECT c_dynasty_chn, c_dynasty FROM DYNASTIES WHERE c_dy=?", (args.dy,)):
            dname = chn or en_
        con = sqlite3.connect(f"file:{args.out}?mode=ro", uri=True)
        triples = con.execute(
            "SELECT (SELECT COUNT(*) FROM objs)+(SELECT COUNT(*) FROM datas)").fetchone()[0]
        con.close()
        meta = {
            "dy": args.dy,
            "dynasty": dname,
            "db": args.db,
            "built_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "seconds": round(time.time() - t0, 1),
            "size_mb": round(os.path.getsize(args.out) / 1e6, 1),
            "triples": triples,
            "counts": {
                "Person(核心)": len(core), "Person(邻域)": en,
                "KinshipAssertion": nk, "AssociationEvent": na,
                "OfficeTenure": nto, "EntryRecord": ner,
                "AddressClaim": nac, "StatusPeriod": nsp,
                "TextRoleLink": ntr, "Place": np_,
                "Office": no_, "Text": nt,
                "sourceOf 边": nso, "altName": nal,
            },
        }
        with open(args.out + ".meta.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        LOG(f"meta: {os.path.basename(args.out)}.meta.json")
    except Exception as e:          # 元数据失败不影响 ETL 结果
        LOG(f"meta 写入失败（忽略）: {e}")

    LOG(f"quadstore: {args.out}")


if __name__ == "__main__":
    main()
