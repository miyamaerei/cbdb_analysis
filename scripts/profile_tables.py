# -*- coding: utf-8 -*-
"""CBDB 全表数据体检：密度（非空率）+ 关键外键完整性。
用法: python profile_tables.py [--db PATH] [--out DIR]
产物: profile_overview.md / profile_columns.csv / profile_fk.md
"""
import argparse, csv, json, sqlite3, sys, time

DEFAULT_DB = r"E:\git\cbdb_sqlite\cbdb_20260926.sqlite3"

# 关键外键清单: 表 -> [(列, 引用表, 引用列)]
FK_CHECKS = {
    "BIOG_MAIN": [
        ("c_dy", "DYNASTIES", "c_dy"),
        ("c_index_addr_id", "ADDR_CODES", "c_addr_id"),
        ("c_choronym_code", "CHORONYM_CODES", "c_choronym_code"),
        ("c_ethnicity_code", "ETHNICITY_TRIBE_CODES", "c_ethnicity_code"),
        ("c_household_status_code", "HOUSEHOLD_STATUS_CODES", "c_household_status_code"),
    ],
    "ALTNAME_DATA": [("c_personid", "BIOG_MAIN", "c_personid")],
    "BIOG_SOURCE_DATA": [("c_personid", "BIOG_MAIN", "c_personid"), ("c_textid", "TEXT_CODES", "c_textid")],
    "BIOG_TEXT_DATA": [("c_personid", "BIOG_MAIN", "c_personid"), ("c_textid", "TEXT_CODES", "c_textid")],
    "KIN_DATA": [
        ("c_personid", "BIOG_MAIN", "c_personid"),
        ("c_kin_id", "BIOG_MAIN", "c_personid"),
        ("c_kin_code", "KINSHIP_CODES", "c_kincode"),
    ],
    "ASSOC_DATA": [
        ("c_personid", "BIOG_MAIN", "c_personid"),
        ("c_assoc_id", "BIOG_MAIN", "c_personid"),
        ("c_assoc_code", "ASSOC_CODES", "c_assoc_code"),
    ],
    "ENTRY_DATA": [("c_personid", "BIOG_MAIN", "c_personid"), ("c_entry_code", "ENTRY_CODES", "c_entry_code")],
    "STATUS_DATA": [("c_personid", "BIOG_MAIN", "c_personid"), ("c_status_code", "STATUS_CODES", "c_status_code")],
    "POSTING_DATA": [("c_personid", "BIOG_MAIN", "c_personid")],
    "POSTED_TO_OFFICE_DATA": [
        ("c_personid", "BIOG_MAIN", "c_personid"),
        ("c_office_id", "OFFICE_CODES", "c_office_id"),
    ],
    "POSTED_TO_ADDR_DATA": [("c_posting_id", "POSTING_DATA", "c_posting_id"), ("c_addr_id", "ADDR_CODES", "c_addr_id")],
    "BIOG_ADDR_DATA": [
        ("c_personid", "BIOG_MAIN", "c_personid"),
        ("c_addr_id", "ADDR_CODES", "c_addr_id"),
        ("c_addr_type", "BIOG_ADDR_CODES", "c_addr_code"),
    ],
    "TEXT_INSTANCE_DATA": [("c_textid", "TEXT_CODES", "c_textid")],
    "EVENTS_DATA": [("c_personid", "BIOG_MAIN", "c_personid"), ("c_event_code", "EVENT_CODES", "c_event_code")],
    "POSSESSION_DATA": [("c_personid", "BIOG_MAIN", "c_personid")],
    "BIOG_INST_DATA": [("c_personid", "BIOG_MAIN", "c_personid"), ("c_inst_code", "SOCIAL_INSTITUTION_CODES", "c_inst_code")],
    "MERGED_PERSON_DATA": [("c_merged_from_personid", "BIOG_MAIN", "c_personid"), ("c_personid", "BIOG_MAIN", "c_personid")],
    "ADDR_BELONGS_DATA": [("c_addr_id", "ADDR_CODES", "c_addr_id"), ("c_belongs_to", "ADDR_CODES", "c_addr_id")],
}


def table_columns(cur, t):
    return [r[1] for r in cur.execute(f'PRAGMA table_info("{t}")')]


def scan_density(cur, tables):
    overview, columns = [], []
    for t in tables:
        cols = table_columns(cur, t)
        if not cols:
            continue
        expr = ", ".join(f'COUNT("{c}")' for c in cols)
        row = cur.execute(f'SELECT COUNT(*), {expr} FROM "{t}"').fetchone()
        n = row[0]
        rates = [(row[i + 1] / n * 100.0) if n else 0.0 for i in range(len(cols))]
        for c, nn, r in zip(cols, row[1:], rates):
            columns.append({"table": t, "column": c, "nonnull": nn, "rows": n, "pct": round(r, 2)})
        avg = sum(rates) / len(rates)
        empty = sum(1 for r in rates if r == 0)
        full = sum(1 for r in rates if r == 100)
        sparse = sum(1 for r in rates if 0 < r < 10)
        overview.append({
            "table": t, "rows": n, "cols": len(cols),
            "avg_pct": round(avg, 1), "empty_cols": empty, "sparse_cols": sparse, "full_cols": full,
        })
    return overview, columns


def scan_fk(cur):
    results = []
    for t, fks in FK_CHECKS.items():
        cols = set(table_columns(cur, t))
        for col, rt, rcol in fks:
            rcols = set(table_columns(cur, rt))
            if col not in cols:
                results.append({"table": t, "col": col, "ref": f"{rt}.{rcol}", "status": "SKIP: 列不存在"})
                continue
            if rcol not in rcols:
                results.append({"table": t, "col": col, "ref": f"{rt}.{rcol}", "status": "SKIP: 引用列不存在"})
                continue
            sql = f"""
                SELECT COUNT(*),
                       SUM(CASE WHEN "{col}" IS NULL THEN 1 ELSE 0 END),
                       SUM(CASE WHEN "{col}" = 0 THEN 1 ELSE 0 END),
                       SUM(CASE WHEN "{col}" IS NOT NULL AND "{col}" <> 0
                                AND "{col}" NOT IN (SELECT "{rcol}" FROM "{rt}") THEN 1 ELSE 0 END)
                FROM "{t}"
            """
            n, nulls, zeros, orphan = cur.execute(sql).fetchone()
            nulls, zeros, orphan = nulls or 0, zeros or 0, orphan or 0
            valid = n - nulls - zeros - orphan
            results.append({
                "table": t, "col": col, "ref": f"{rt}.{rcol}", "rows": n,
                "null": nulls, "zero": zeros, "orphan": orphan,
                "cover_pct": round(valid / n * 100, 2) if n else 0.0,
                "status": "OK",
            })
    return results


def grade(o):
    if o["rows"] == 0:
        return "空表"
    if o["avg_pct"] >= 70:
        return "高密度"
    if o["avg_pct"] >= 40:
        return "中密度"
    return "稀疏"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--out", default=r"E:\git\cbdb_sqlite\analysis")
    args = ap.parse_args()

    import os
    os.makedirs(args.out, exist_ok=True)
    con = sqlite3.connect(args.db)
    cur = con.cursor()
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    print(f"[1/3] {len(tables)} 张表，开始密度扫描 ...", flush=True)
    t0 = time.time()
    overview, columns = scan_density(cur, tables)
    print(f"      密度扫描完成 {time.time()-t0:.1f}s", flush=True)

    print("[2/3] 外键完整性检查 ...", flush=True)
    t0 = time.time()
    fk = scan_fk(cur)
    print(f"      FK 检查完成 {time.time()-t0:.1f}s, {len(fk)} 组", flush=True)

    print("[3/3] 写出结果 ...", flush=True)
    overview.sort(key=lambda o: -o["rows"])
    with open(os.path.join(args.out, "profile_overview.md"), "w", encoding="utf-8") as f:
        f.write("# CBDB 全表密度体检\n\n| 表 | 行数 | 列数 | 平均非空率 | 全空列 | 稀疏列(<10%) | 全满列 | 评级 |\n|---|---|---|---|---|---|---|---|\n")
        for o in overview:
            f.write(f"| {o['table']} | {o['rows']:,} | {o['cols']} | {o['avg_pct']}% | {o['empty_cols']} | {o['sparse_cols']} | {o['full_cols']} | {grade(o)} |\n")
    with open(os.path.join(args.out, "profile_columns.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["table", "column", "nonnull", "rows", "pct"])
        w.writeheader()
        w.writerows(columns)
    with open(os.path.join(args.out, "profile_fk.md"), "w", encoding="utf-8") as f:
        f.write("# CBDB 关键外键完整性\n\n| 表.列 | 引用 | 总行数 | NULL | 零值 | 孤儿(非零无引用) | 有效覆盖率 |\n|---|---|---|---|---|---|---|\n")
        for r in fk:
            if r["status"] != "OK":
                f.write(f"| {r['table']}.{r['col']} | {r['ref']} | - | - | - | {r['status']} | - |\n")
            else:
                f.write(f"| {r['table']}.{r['col']} | {r['ref']} | {r['rows']:,} | {r['null']:,} | {r['zero']:,} | {r['orphan']:,} | {r['cover_pct']}% |\n")
    with open(os.path.join(args.out, "profile_fk.json"), "w", encoding="utf-8") as f:
        json.dump(fk, f, ensure_ascii=False, indent=1)
    print("done ->", args.out)


if __name__ == "__main__":
    main()
