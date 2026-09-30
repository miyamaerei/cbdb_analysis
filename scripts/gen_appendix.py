#!/usr/bin/env python3
"""Regenerate the appendix table section of the CBDB usage report from the live DB."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

CAT = {
    "BIOG_MAIN": "人物", "ALTNAME_DATA": "人物", "ALTNAME_CODES": "人物",
    "BIOG_SOURCE_DATA": "人物", "BIOG_TEXT_DATA": "人物", "MERGED_PERSON_DATA": "人物",
    "ADDR_CODES": "地理", "ADDR_BELONGS_DATA": "地理", "ADDRESSES": "地理",
    "ADMIN_CAT_CODES": "地理", "ADMIN_CAT_TYPES": "地理",
    "ADMIN_CAT_CODE_TYPE_REL": "地理", "BIOG_ADDR_DATA": "地理",
    "BIOG_ADDR_CODES": "地理",
    "OFFICE_CODES": "任职", "OFFICE_TYPE_TREE": "任职", "OFFICE_CODE_TYPE_REL": "任职",
    "OFFICE_CATEGORIES": "任职", "POSTING_DATA": "任职",
    "POSTED_TO_OFFICE_DATA": "任职", "POSTED_TO_ADDR_DATA": "任职",
    "APPOINTMENT_CODES": "任职", "APPOINTMENT_TYPES": "任职",
    "APPOINTMENT_CODE_TYPE_REL": "任职", "ASSUME_OFFICE_CODES": "任职",
    "KIN_DATA": "亲属", "KINSHIP_CODES": "亲属", "KIN_MOURNING": "亲属",
    "KIN_MOURNING_STEPS": "亲属", "KINREL_REDUCTION": "亲属",
    "ASSOC_DATA": "社会关系", "ASSOC_CODES": "社会关系", "ASSOC_TYPES": "社会关系",
    "ASSOC_CODE_TYPE_REL": "社会关系", "OCCASION_CODES": "社会关系",
    "LITERARYGENRE_CODES": "社会关系", "SCHOLARLYTOPIC_CODES": "社会关系",
    "ENTRY_DATA": "入仕", "ENTRY_CODES": "入仕", "ENTRY_TYPES": "入仕",
    "ENTRY_CODE_TYPE_REL": "入仕", "PARENTAL_STATUS_CODES": "入仕",
    "STATUS_DATA": "身份", "STATUS_CODES": "身份", "STATUS_TYPES": "身份",
    "STATUS_CODE_TYPE_REL": "身份",
    "SOCIAL_INSTITUTION_CODES": "机构", "SOCIAL_INSTITUTION_NAME_CODES": "机构",
    "SOCIAL_INSTITUTION_TYPES": "机构", "SOCIAL_INSTITUTION_ADDR": "机构",
    "SOCIAL_INSTITUTION_ADDR_TYPES": "机构",
    "SOCIAL_INSTITUTION_ALTNAME_CODES": "机构",
    "SOCIAL_INSTITUTION_ALTNAME_DATA": "机构",
    "BIOG_INST_DATA": "机构", "BIOG_INST_CODES": "机构",
    "TEXT_CODES": "文本", "TEXT_INSTANCE_DATA": "文本", "TEXT_ROLE_CODES": "文本",
    "TEXT_BIBLCAT_CODES": "文本", "TEXT_BIBLCAT_TYPES": "文本",
    "TEXT_BIBLCAT_CODE_TYPE_REL": "文本", "TEXT_TYPE": "文本",
    "EXTANT_CODES": "文本", "COUNTRY_CODES": "文本",
    "POSSESSION_DATA": "财产", "POSSESSION_ADDR": "财产",
    "POSSESSION_ACT_CODES": "财产", "MEASURE_CODES": "财产",
    "EVENTS_DATA": "事件", "EVENTS_ADDR": "事件", "EVENT_CODES": "事件",
    "DYNASTIES": "代码表", "NIAN_HAO": "代码表", "GANZHI_CODES": "代码表",
    "YEAR_RANGE_CODES": "代码表", "INDEXYEAR_TYPE_CODES": "代码表",
    "CHORONYM_CODES": "代码表", "ETHNICITY_TRIBE_CODES": "代码表",
    "HOUSEHOLD_STATUS_CODES": "代码表",
}


def main() -> None:
    db = Path("cbdb_20260926.sqlite3")
    report = Path("CBDB_SQLite_使用报告.md")

    inv = json.loads(Path("schema_inventory.json").read_text(encoding="utf-8"))
    conn = sqlite3.connect(str(db))

    rows = []
    for t in inv["tables"]:
        name = t["name"]
        # refresh row count (ADDRESSES was created after the inventory dump)
        n = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
        pk = ", ".join(t["pk"]) or "—"
        rows.append((name, n, pk, CAT.get(name, "?")))
    rows.sort(key=lambda r: -r[1])

    lines = [
        "| # | 表名 | 行数 | 主键 | 分类 |",
        "|---:|---|---:|---|---|",
    ]
    for i, (name, n, pk, cat) in enumerate(rows, 1):
        lines.append(f"| {i} | `{name}` | {n:,} | {pk} | {cat} |")
    table_md = "\n".join(lines)

    text = report.read_text(encoding="utf-8")
    start = text.index("## 七、附录")
    end = text.index("## 八、延伸阅读")
    new_section = (
        "## 七、附录：表清单速查（79 张，按行数降序）\n\n"
        + table_md
        + "\n\n> 行数取自 `cbdb_20260926.sqlite3` 实时统计。"
        "空表（0 行）表示该模块尚未录入数据："
        "`ADMIN_CAT_TYPES`、`ADMIN_CAT_CODE_TYPE_REL`、`SOCIAL_INSTITUTION_ALTNAME_DATA`。\n\n"
    )
    report.write_text(text[:start] + new_section + text[end:], encoding="utf-8")
    print(f"Appendix regenerated: {len(rows)} tables")
    print(f"Top 5: {[r[0] for r in rows[:5]]}")


if __name__ == "__main__":
    main()
