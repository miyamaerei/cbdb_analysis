# -*- coding: utf-8 -*-
"""Web 端专题查询的调度层（**不依赖任何界面框架**，Gradio 时代等价物是 app/specs.py，已删）。

把 kg_query.Q1–Q9 的纯函数 + 参数适配 + JSON 化字段规格集中在这里，
供 api_server 调用。最终删掉 Gradio 的 app/ 整层后，本文件成为专题查询的唯一来源。

契约
----
  * TOPIC_SCHEMA：9 个专题的声明式规格（key / tab / hint / btn / fields），
    字段规格是 JSON 可序列化的（kind: number|text|radio|dropdown|checkbox）。
  * run_topic(key, g, vals) -> {"md": str, "sheets": [{"name","headers","rows"}]}
    vals 是前端按 fields 顺序传来的原始值列表；本函数负责类型解析与参数展开。
"""
from collections import defaultdict

import kg_query as Q


def _int(v):
    """空/非数字 → None（当作不限）。"""
    if v in (None, ""):
        return None
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


# ============================================================ 字段规格（JSON 化）
TOPIC_SCHEMA = [
    {
        "key": "Q1", "tab": "① 完整档案", "btn": "📄 生成档案",
        "hint": "一页看全：基本档案/别名/亲属/地址/任职/入仕/身份/著作/史料/交遊　例：30374 = 王守仁",
        "fields": [{"kind": "number", "label": "personid", "placeholder": "如 30374"}],
    },
    {
        "key": "Q2", "tab": "② 亲属称谓", "btn": "🔍 查询",
        "hint": "双向亲属断言 + 称谓分布统计 + 世代步数 + 出处史料",
        "fields": [
            {"kind": "number", "label": "personid", "placeholder": "如 30374"},
            {"kind": "radio", "label": "方向", "choices": ["双向", "出", "入"], "default": "双向"},
        ],
    },
    {
        "key": "Q3", "tab": "③ N度家族网", "btn": "🕸 展开",
        "hint": "⚠️ 深度 3 + 含交遊会爆炸，务必设节点上限",
        "fields": [
            {"kind": "number", "label": "起点 personid", "placeholder": "如 30374"},
            {"kind": "dropdown", "label": "度数", "choices": [1, 2, 3], "default": 2},
            {"kind": "checkbox", "label": "含交遊关系", "default": False},
            {"kind": "number", "label": "节点上限", "default": 3000},
        ],
    },
    {
        "key": "Q4", "tab": "④ 师承链", "btn": "🔗 追溯",
        "hint": "沿「為Y之學生/門人/弟子/從Y學/私淑/問學…」等师承类关系做 BFS",
        "fields": [
            {"kind": "number", "label": "personid", "placeholder": "如 30374"},
            {"kind": "radio", "label": "方向", "choices": ["求师(向上)", "求弟子(向下)"],
             "default": "求师(向上)"},
            {"kind": "dropdown", "label": "最大深度", "choices": [1, 2, 3], "default": 2},
        ],
    },
    {
        "key": "Q5", "tab": "⑤ 同年进士", "btn": "🎓 查同年",
        "hint": "同年登科名单 + 甲第分布　例：年份 1499（王守仁登科年）",
        "fields": [
            {"kind": "number", "label": "年份（留空则用右侧人物ID的进士年）", "placeholder": "如 1499"},
            {"kind": "number", "label": "或填 personid", "placeholder": "如 30374"},
        ],
    },
    {
        "key": "Q6", "tab": "⑥ 任职轨迹", "btn": "📈 生成轨迹",
        "hint": "按时间序的仕途",
        "fields": [{"kind": "number", "label": "personid", "placeholder": "如 30374"}],
    },
    {
        "key": "Q7", "tab": "⑦ 某县某朝", "btn": "🏘 查询",
        "hint": "地点层级闭包 + 朝代过滤（CBDB 地名多为繁体，输简体也能匹配）",
        "fields": [
            {"kind": "text", "label": "县/地点名关键词", "placeholder": "如 餘姚"},
            {"kind": "text", "label": "朝代名（留空=全部）", "placeholder": "如 明", "default": ""},
        ],
    },
    {
        "key": "Q8", "tab": "⑧ 某书人物", "btn": "📖 查询",
        "hint": "著作角色 + 史料来源两种关联",
        "fields": [{"kind": "text", "label": "书名关键词", "placeholder": "如 傳習錄"}],
    },
    {
        "key": "Q9", "tab": "⑨ 学派主题网", "btn": "🕸 展开网络",
        "hint": "按主题抽取交遊子网（节点 + 边）；CBDB 主题字段稀疏，无命中会自动列出可用候选",
        "fields": [{"kind": "text", "label": "主题/学派关键词", "placeholder": "如 理學"}],
    },
]


# ============================================================ 运行
def run_topic(key, g, vals):
    """按 key 调 kg_query 对应函数，归一化返回 {md, sheets}。

    vals 是前端按 fields 顺序传来的原始值（字符串/数字/布尔）。
    各专题早退分支也返回三元结构，保证前端渲染不崩。
    """
    vals = vals or []
    if key == "Q1":
        pid = _int(vals[0]) if len(vals) > 0 else None
        if pid is None:
            return {"md": "请填 personid。", "sheets": []}
        md, flat = Q.q1_dossier(g, pid)
        return {"md": md, "sheets": [{"name": "档案明细", "headers": ["段落", "字段", "值"], "rows": flat}]}

    if key == "Q2":
        pid = _int(vals[0]) if len(vals) > 0 else None
        direction = vals[1] if len(vals) > 1 else "双向"
        if pid is None:
            return {"md": "请填 personid。", "sheets": []}
        h, rows, md = Q.q2_kin(g, pid, direction)
        return {"md": md, "sheets": [{"name": "亲属", "headers": h, "rows": rows}]}

    if key == "Q3":
        pid = _int(vals[0]) if len(vals) > 0 else None
        depth = vals[1] if len(vals) > 1 else 2
        inc = bool(vals[2]) if len(vals) > 2 else False
        maxn = _int(vals[3]) or 3000
        if pid is None:
            return {"md": "请填起点 personid。", "sheets": []}
        hn, nodes, he, edges, md = Q.q3_kinnet(g, pid, int(depth), inc, maxn)
        return {"md": md, "sheets": [
            {"name": "节点", "headers": hn, "rows": nodes},
            {"name": "边", "headers": he, "rows": edges},
        ]}

    if key == "Q4":
        pid = _int(vals[0]) if len(vals) > 0 else None
        direction = vals[1] if len(vals) > 1 else "求师(向上)"
        depth = vals[2] if len(vals) > 2 else 2
        if pid is None:
            return {"md": "请填 personid。", "sheets": []}
        h, rows, md = Q.q4_teacher(g, pid, direction, int(depth))
        return {"md": md, "sheets": [{"name": "师承", "headers": h, "rows": rows}]}

    if key == "Q5":
        year = _int(vals[0]) if len(vals) > 0 else None
        pid = _int(vals[1]) if len(vals) > 1 else None
        if year is None and pid is None:
            return {"md": "请填年份，或填一个 personid 自动取其进士年。", "sheets": []}
        h, rows, md = Q.q5_jinshi(g, year, pid)
        return {"md": md, "sheets": [{"name": "同年进士", "headers": h, "rows": rows}]}

    if key == "Q6":
        pid = _int(vals[0]) if len(vals) > 0 else None
        if pid is None:
            return {"md": "请填 personid。", "sheets": []}
        h, rows, md = Q.q6_tenure(g, pid)
        return {"md": md, "sheets": [{"name": "任职", "headers": h, "rows": rows}]}

    if key == "Q7":
        keyword = (vals[0] if len(vals) > 0 else "") or ""
        dynasty = (vals[1] if len(vals) > 1 else "") or ""
        h, rows, md = Q.q7_county(g, keyword, dynasty)
        return {"md": md, "sheets": [{"name": "人物", "headers": h, "rows": rows}]}

    if key == "Q8":
        keyword = (vals[0] if len(vals) > 0 else "") or ""
        h, rows, md = Q.q8_book(g, keyword)
        return {"md": md, "sheets": [{"name": "人物", "headers": h, "rows": rows}]}

    if key == "Q9":
        keyword = (vals[0] if len(vals) > 0 else "") or ""
        nodes_h, nodes, edges_h, edges, md = Q.q9_topic(g, keyword)
        return {"md": md, "sheets": [
            {"name": "人物节点", "headers": nodes_h, "rows": nodes},
            {"name": "关系边", "headers": edges_h, "rows": edges},
        ]}

    return {"md": "未知专题 key：%s" % key, "sheets": []}
