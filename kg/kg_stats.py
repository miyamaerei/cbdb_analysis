# -*- coding: utf-8 -*-
"""明朝种子集验收：OWL 侧实例/三元组计数 vs SQLite 源库对账 + 抽检查询。
必须在 etl_seed_ming.py 结束后运行（否则 quadstore 被写锁占用）。

用法：
    python kg_stats.py                      # 对账
    python kg_stats.py --sample 王守仁       # 额外跑抽检查询
"""
import argparse, os, sqlite3, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# 默认源库：相对仓库根目录（仓库可在任意路径克隆后直接运行，不写死本机绝对路径）
DEFAULT_DB = os.path.join(HERE, "..", "cbdb_20260926.sqlite3")
DEFAULT_QUAD = os.path.join(HERE, "quadstore", "cbdb_ming.sqlite3")
CBDB = "http://cbdb.example.org/ontology#"


class QuadStore:
    def __init__(self, path):
        self.con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        r = self.con.execute(
            "SELECT storid FROM resources WHERE iri LIKE '%1999/02/22-rdf-syntax-ns#type'").fetchone()
        self.type_id = r[0] if r else 6

    def total(self):
        return self.con.execute(
            "SELECT (SELECT COUNT(*) FROM objs)+(SELECT COUNT(*) FROM datas)").fetchone()[0]

    def prop_triples(self, prop_iri=None):
        if prop_iri is None:
            return self.total()
        r = self.con.execute("SELECT storid FROM resources WHERE iri=?", (prop_iri,)).fetchone()
        if not r:
            return 0
        return self.con.execute(
            "SELECT (SELECT COUNT(*) FROM objs WHERE p=?) + (SELECT COUNT(*) FROM datas WHERE p=?)",
            (r[0], r[0])).fetchone()[0]

    def cls(self, local_name):
        r = self.con.execute("SELECT storid FROM resources WHERE iri=?", (CBDB + local_name,)).fetchone()
        if not r:
            return 0
        return self.con.execute(
            "SELECT COUNT(DISTINCT s) FROM objs WHERE p=? AND o=?", (self.type_id, r[0])).fetchone()[0]


def sql_expected(src, limit=0):
    q = "CREATE TEMP TABLE m19 AS SELECT c_personid FROM BIOG_MAIN WHERE c_dy=19 ORDER BY c_personid"
    if limit:
        q += f" LIMIT {limit}"
    src.execute(q)
    one = lambda q: src.execute(q).fetchone()[0]
    exp = {}
    exp["KinshipAssertion"] = one("""
        SELECT COUNT(*) FROM KIN_DATA WHERE c_personid IN (SELECT c_personid FROM m19)
          AND c_kin_id>0 AND c_kin_code IN (SELECT c_kincode FROM KINSHIP_CODES)""")
    exp["AssociationEvent"] = one("""
        SELECT COUNT(*) FROM ASSOC_DATA WHERE c_personid IN (SELECT c_personid FROM m19)
          AND c_assoc_id>0 AND c_assoc_code IN (SELECT c_assoc_code FROM ASSOC_CODES)""")
    exp["OfficeTenure"] = one("""
        SELECT COUNT(*) FROM POSTED_TO_OFFICE_DATA WHERE c_personid IN (SELECT c_personid FROM m19)
          AND c_office_id>0 AND c_personid>0""")
    exp["EntryRecord"] = one("""
        SELECT COUNT(*) FROM ENTRY_DATA WHERE c_personid IN (SELECT c_personid FROM m19)
          AND c_entry_code IN (SELECT c_entry_code FROM ENTRY_CODES)""")
    exp["AddressClaim"] = one("""
        SELECT COUNT(*) FROM BIOG_ADDR_DATA WHERE c_personid IN (SELECT c_personid FROM m19)
          AND c_addr_id>0 AND c_addr_type IN (SELECT c_addr_type FROM BIOG_ADDR_CODES)""")
    exp["StatusPeriod"] = one("""
        SELECT COUNT(*) FROM STATUS_DATA WHERE c_personid IN (SELECT c_personid FROM m19)
          AND c_status_code IN (SELECT c_status_code FROM STATUS_CODES)""")
    exp["TextRoleLink"] = one("""
        SELECT COUNT(*) FROM BIOG_TEXT_DATA WHERE c_personid IN (SELECT c_personid FROM m19)
          AND c_textid>0 AND c_role_id IN (SELECT c_role_id FROM TEXT_ROLE_CODES)""")
    exp["sourceOf(边)"] = one("""
        SELECT COUNT(*) FROM (SELECT DISTINCT c_personid, c_textid FROM BIOG_SOURCE_DATA
          WHERE c_personid IN (SELECT c_personid FROM m19) AND c_textid>0)""")
    exp["altName(值)"] = one("""
        SELECT COUNT(*) FROM ALTNAME_DATA WHERE c_personid IN (SELECT c_personid FROM m19)
          AND COALESCE(c_alt_name_chn, c_alt_name) IS NOT NULL AND COALESCE(c_alt_name_chn, c_alt_name)<>''""")
    # MERGED_PERSON_DATA 的 ID 归一（口径必须与 ETL 完全一致）
    mm = dict(src.execute("SELECT c_merged_from_personid, c_personid FROM MERGED_PERSON_DATA"))

    def root(x):
        seen = set()
        while x in mm and x not in seen:
            seen.add(x)
            x = mm[x]
        return x

    # Person = 核心实际建节点数（排除被合并的作废 ID）+ 邻域
    core_raw = [r[0] for r in src.execute("SELECT c_personid FROM m19")]
    merged_from = set(mm.keys())
    # 精确模拟 ETL 的建节点行为：
    #   ① 核心里每个 pid → 若被合并则规范到 root(pid)，否则自身
    #   ② 邻域 = KIN/ASSOC 对端归一后、且不在 core_norm 中
    loaded_core = {x if x not in mm else root(x) for x in core_raw}
    exp["core_persons"] = len(loaded_core)

    exts = set()
    for (x,) in src.execute("SELECT DISTINCT c_kin_id FROM KIN_DATA WHERE c_personid IN (SELECT c_personid FROM m19) AND c_kin_id>0"):
        exts.add(root(x))
    for (x,) in src.execute("SELECT DISTINCT c_assoc_id FROM ASSOC_DATA WHERE c_personid IN (SELECT c_personid FROM m19) AND c_assoc_id>0"):
        exts.add(root(x))
    exts -= {root(x) for x in core_raw}
    # ETL 邻域加载仅对主表中存在的 ID 建完整节点
    exp["ext_persons"] = len([x for x in exts if src.execute(
        "SELECT 1 FROM BIOG_MAIN WHERE c_personid=?", (x,)).fetchone()])
    exp["Person"] = len(loaded_core | exts)
    # 直接引用规模（Place 含祖先扩展，OWL 侧应 >= 直接引用）
    exp["addr_direct"] = one("""
        SELECT COUNT(*) FROM (
          SELECT DISTINCT c_addr_id a FROM BIOG_ADDR_DATA
            WHERE c_personid IN (SELECT c_personid FROM m19) AND c_addr_id>0
          UNION SELECT DISTINCT a.c_addr_id FROM POSTED_TO_ADDR_DATA a
            JOIN POSTED_TO_OFFICE_DATA o ON a.c_posting_id=o.c_posting_id AND a.c_office_id=o.c_office_id
            WHERE o.c_personid IN (SELECT c_personid FROM m19) AND a.c_addr_id>0
          UNION SELECT DISTINCT c_addr_id FROM ASSOC_DATA
            WHERE c_personid IN (SELECT c_personid FROM m19) AND c_addr_id>0)""")
    exp["office_direct"] = one("""
        SELECT COUNT(DISTINCT c_office_id) FROM POSTED_TO_OFFICE_DATA
          WHERE c_personid IN (SELECT c_personid FROM m19) AND c_office_id>0""")
    exp["text_direct"] = one("""
        SELECT COUNT(*) FROM (
          SELECT DISTINCT c_textid t FROM BIOG_TEXT_DATA WHERE c_personid IN (SELECT c_personid FROM m19) AND c_textid>0
          UNION SELECT DISTINCT c_textid FROM BIOG_SOURCE_DATA WHERE c_personid IN (SELECT c_personid FROM m19) AND c_textid>0
          UNION SELECT DISTINCT c_source FROM KIN_DATA WHERE c_personid IN (SELECT c_personid FROM m19) AND c_source>0)""")
    return exp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--quad", default=DEFAULT_QUAD)
    ap.add_argument("--sample", default=None, help="抽检：人名（如 王守仁）")
    ap.add_argument("--limit-persons", type=int, default=0,
                    help="与 ETL 的 --limit-persons 保持一致，否则对账口径不同")
    args = ap.parse_args()

    q = QuadStore(args.quad)
    src = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    exp = sql_expected(src, args.limit_persons)

    print("=" * 62)
    print("明朝种子集 对账报告")
    print("=" * 62)
    print(f"quadstore : {args.quad}  ({os.path.getsize(args.quad)/1e6:.1f} MB)")
    print(f"总三元组  : {q.total():,}")
    print("-" * 62)
    print(f"{'项':<22}{'源库/ETL预期':>16}{'OWL 实际':>14}{'状态':>10}")

    rows = [
        ("Person", exp["Person"], q.cls("Person")),
        ("  ├ 核心(明)", exp["core_persons"], None),
        ("  └ 邻域扩展", exp["ext_persons"], None),
        ("KinshipAssertion", exp["KinshipAssertion"], q.cls("KinshipAssertion")),
        ("AssociationEvent", exp["AssociationEvent"], q.cls("AssociationEvent")),
        ("OfficeTenure", exp["OfficeTenure"], q.cls("OfficeTenure")),
        ("EntryRecord", exp["EntryRecord"], q.cls("EntryRecord")),
        ("AddressClaim", exp["AddressClaim"], q.cls("AddressClaim")),
        ("StatusPeriod", exp["StatusPeriod"], q.cls("StatusPeriod")),
        ("TextRoleLink", exp["TextRoleLink"], q.cls("TextRoleLink")),
    ]
    ok_all = True
    for name, e, a in rows:
        if a is None:
            print(f"{name:<22}{e:>16,}{'—':>14}{'':>10}")
        else:
            ok = e == a
            ok_all &= ok
            print(f"{name:<22}{e:>16,}{a:>14,}{'OK' if ok else 'MISMATCH':>10}")

    print("-" * 62)
    print("辅助实体（Place 含祖先扩展，OWL ≥ 直接引用）")
    for name, key, owl in [("Place", "addr_direct", q.cls("Place")),
                           ("Office", "office_direct", q.cls("Office")),
                           ("Text", "text_direct", q.cls("Text"))]:
        flag = "OK" if owl >= exp[key] else "WARN"
        print(f"{name:<22}{exp[key]:>16,}{owl:>14,}{flag:>10}")
    print("-" * 62)
    print("边/值计数")
    for label, prop in [("sourceOf", "sourceOf"), ("hasKin", "hasKin"), ("belongsTo", "belongsTo")]:
        print(f"{label + ' 三元组':<22}{'':>16}{q.prop_triples(CBDB + prop):>14,}{'':>10}")
    print(f"{'altName 值(预期)':<22}{exp['altName(值)']:>16,}{'':>14}{'':>10}")
    print("=" * 62)
    print("结论:", "对账全部通过" if ok_all else "存在 MISMATCH，需排查")

    if args.sample:
        run_sample(args.quad, args.sample)


def run_sample(quad, name):
    from owlready2 import World
    print("\n" + "=" * 62)
    print(f"抽检查询：{name}")
    print("=" * 62)
    w = World()
    w.set_backend(filename=quad)
    onto = w.get_ontology(CBDB).load()
    hits = list(onto.search(nameChn=name))[:5]
    if not hits:
        print("未找到人物")
        return
    for p in hits:
        print(f"\nIRI        : {p.iri}")
        print(f"  nameChn  : {p.nameChn}  拼音: {p.namePinyin}")
        print(f"  personId : {p.personId}   朝代: {getattr(p.dynastyOf, 'label', None)}")
        print(f"  生卒     : {p.birthYear} / {p.deathYear}  indexYear={p.indexYear}")
        print(f"  别名     : {p.altName[:5]}")
        # 断言类的中心属性以 hub 为主体，人物侧要用 search(by object) 或直边
        n_kin = len(list(onto.search(kinSource=p)))
        n_assoc = len(list(onto.search(assocFrom=p)))
        n_ten = len(list(onto.search(tenureHolder=p)))
        n_entry = len(list(onto.search(entryPerson=p)))
        n_addr = len(list(onto.search(addrPerson=p)))
        print(f"  亲属断言 : {n_kin} 条（hasKin 直边 {len(p.hasKin or [])}）")
        print(f"  交遊断言 : {n_assoc} 条（hasAssociate 直边 {len(p.hasAssociate or [])}）")
        print(f"  任职     : {n_ten} 条")
        print(f"  入仕     : {n_entry} 条")
        print(f"  地址断言 : {n_addr} 条")
        for k in list(onto.search(kinSource=p))[:8]:
            t = k.kinTarget
            print(f"    · {getattr(k.kinType, 'conceptNameChn', None)} → {t.nameChn}({t.personId})")
        for e in list(onto.search(entryPerson=p))[:4]:
            print(f"    · 入仕 {getattr(e.entryMode, 'conceptNameChn', None)}"
                  f" 年份={e.entryYear} 名次={e.examRank}")
        for t in list(onto.search(tenureHolder=p))[:6]:
            print(f"    · 任官 {getattr(t.tenureOffice, 'officeNameChn', None)}"
                  f" {t.tenureFirstYear}-{t.tenureLastYear}"
                  f" @ {getattr(t.tenurePlace, 'placeNameChn', None) if t.tenurePlace else None}")


if __name__ == "__main__":
    main()
