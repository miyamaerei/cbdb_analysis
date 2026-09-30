# -*- coding: utf-8 -*-
"""①~⑨ 专题查询页的**规格表**（纯声明，不含 Gradio 代码）。

每个 QuerySpec 描述一张页面：Tab 名 / SPARQL 原型 / 输入字段 / 结果表 / 怎么调 kg_query。
真正的查询逻辑在 `kg_query.py`，这里只做「参数 → 结果」的整形适配。

统一契约：
    spec.run(g, vals) -> (markdown, [rows, ...])
        rows 的个数与顺序必须和 spec.sheets 一一对应
        （show=False 的表只导出、不显示在页面上）

要新增一个查询页：在 SPECS 末尾加一条即可，`page_topics.py` 会自动渲染。
"""
from dataclasses import dataclass, field
from typing import Callable, List

import kg_backend as K
import kg_query as Q
from .shared import Field, Sheet, quad_dynasty


def _default_dynasty():
    """⑦ 页的朝代默认值 = 当前首个图谱的朝代。"""
    ch = K.quad_choices()
    return quad_dynasty(ch[0][1]) if ch else ""


def _int(v):
    """输入统一走 Textbox，拿到的是字符串：空/非数字 → None（当作不限）。"""
    if v in (None, ""):
        return None
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


@dataclass
class QuerySpec:
    key: str                       # Q1..Q9（同时用作 Gradio api_name 前缀）
    tab: str                       # Tab 标题
    sparql: str                    # SPARQL 原型（页面顶部说明）
    hint: str = ""                 # 例子 / 注意事项
    fields: List[Field] = field(default_factory=list)
    sheets: List[Sheet] = field(default_factory=list)
    run: Callable = None           # (g, vals) -> (md, [rows...])
    slug: Callable = lambda v: "query"
    btn: str = "🔍 查询"


# ---------------------------------------------------------------- Q1
def _q1(g, vals):
    pid = _int(vals[0])
    if pid is None:
        return "请填 personid。", [[]]
    md, flat = Q.q1_dossier(g, pid)
    return md, [flat]


# ---------------------------------------------------------------- Q2
def _q2(g, vals):
    pid, direction = _int(vals[0]), vals[1]
    if pid is None:
        return "请填 personid。", [[]]
    _h, rows, md = Q.q2_kin(g, pid, direction)
    return md, [rows]


# ---------------------------------------------------------------- Q3
def _q3(g, vals):
    pid, depth, inc_assoc = _int(vals[0]), vals[1], vals[2]
    maxn = _int(vals[3]) or 3000
    if pid is None:
        return "请填起点 personid。", [[], []]
    _hn, nodes, _he, edges, md = Q.q3_kinnet(g, pid, int(depth), bool(inc_assoc), maxn)
    return md, [nodes, edges]


# ---------------------------------------------------------------- Q4
def _q4(g, vals):
    pid, direction, depth = _int(vals[0]), vals[1], vals[2]
    if pid is None:
        return "请填 personid。", [[]]
    _h, rows, md = Q.q4_teacher(g, pid, direction, int(depth))
    return md, [rows]


# ---------------------------------------------------------------- Q5
def _q5(g, vals):
    year, pid = _int(vals[0]), _int(vals[1])
    if year is None and pid is None:
        return "请填年份，或填一个 personid 自动取其进士年。", [[]]
    _h, rows, md = Q.q5_jinshi(g, year, pid)
    return md, [rows]


# ---------------------------------------------------------------- Q6
def _q6(g, vals):
    pid = _int(vals[0])
    if pid is None:
        return "请填 personid。", [[]]
    _h, rows, md = Q.q6_tenure(g, pid)
    return md, [rows]


# ---------------------------------------------------------------- Q7
def _q7(g, vals):
    keyword, dynasty = vals[0] or "", vals[1] or ""
    _h, rows, md = Q.q7_county(g, keyword, dynasty)
    return md, [rows]


# ---------------------------------------------------------------- Q8
def _q8(g, vals):
    _h, rows, md = Q.q8_book(g, vals[0] or "")
    return md, [rows]


# ---------------------------------------------------------------- Q9
def _q9(g, vals):
    nodes_h, nodes, edges_h, edges, md = Q.q9_topic(g, vals[0] or "")
    return md, [nodes, edges]


SPECS = [
    QuerySpec(
        key="Q1",
        tab="① 完整档案",
        sparql=("`?p a Person; FILTER(?id=:X)` + `OPTIONAL {?p birthYear ?b} ?p dynastyOf ?d}`"
                " + `OPTIONAL {?c addrPerson ?p; addrPlace ?pl; addrKind ?k}`"),
        hint="一页看全：基本档案/别名/亲属/地址(含层级)/任职/入仕/身份/著作/史料/交遊　例：30374 = 王守仁",
        fields=[Field.number("personid")],
        sheets=[Sheet("档案明细", ["段落", "字段", "值"], show=False)],
        run=_q1,
        slug=lambda v: f"person{_int(v[0])}",
        btn="📄 生成档案",
    ),
    QuerySpec(
        key="Q2",
        tab="② 亲属称谓",
        sparql="`?a kinSource :X; kinTarget ?k; kinType ?t. ?t kinNameChn ?n`",
        hint="双向亲属断言 + 称谓分布统计 + 世代步数 + 出处史料",
        fields=[Field.number("personid"),
                Field.radio("方向", ["双向", "出", "入"], "双向")],
        sheets=[Sheet("亲属", ["方向", "称谓", "对方姓名", "对方ID", "上世代",
                               "下世代", "史料"])],
        run=_q2,
        slug=lambda v: f"person{_int(v[0])}_{v[1]}",
    ),
    QuerySpec(
        key="Q3",
        tab="③ N度家族网",
        sparql="便捷直边 `hasKin{1,3}`（属性路径；本实现用 BFS 展开，owlready2 不支持路径查询）",
        hint="⚠️ 深度 3 + 含交遊会爆炸，务必设节点上限",
        fields=[Field.number("起点 personid"),
                Field.dropdown("度数", [1, 2, 3], 2),
                Field.checkbox("含交遊关系"),
                Field.number("节点上限", 3000)],
        sheets=[Sheet("节点", ["度", "personid", "姓名", "生", "卒", "朝代",
                               "与上层关系", "经由", "经由ID"]),
                Sheet("边", ["A_ID", "A", "B_ID", "B", "关系", "最小度"])],
        run=_q3,
        slug=lambda v: f"person{_int(v[0])}_{v[1]}度",
        btn="🕸 展开",
    ),
    QuerySpec(
        key="Q4",
        tab="④ 师承链",
        sparql="`?a assocType :學生之師⁻¹` 链式",
        hint="沿「為Y之學生/門人/弟子/從Y學/私淑/問學…」等师承类关系做 BFS",
        fields=[Field.number("personid"),
                Field.radio("方向", ["求师(向上)", "求弟子(向下)"], "求师(向上)"),
                Field.dropdown("最大深度", [1, 2, 3], 2)],
        sheets=[Sheet("师承", ["度", "personid", "姓名", "生", "卒", "朝代",
                               "相对起点的身份", "经由", "经由ID", "师承链"])],
        run=_q4,
        slug=lambda v: f"person{_int(v[0])}_{v[1]}_{v[2]}度",
        btn="🔗 追溯",
    ),
    QuerySpec(
        key="Q5",
        tab="⑤ 同年进士",
        sparql=("`?e1 entryMode ?m; entryYear ?y. ?e2 entryMode ?m; entryYear ?y. "
                "FILTER(?m 属于進士 ∧ ?e1≠?e2)`"),
        hint="同年登科名单 + 甲第分布　例：年份 1499（王守仁登科年）",
        fields=[Field.number("年份（留空则用右侧人物ID的进士年）"),
                Field.number("或填 personid")],
        sheets=[Sheet("同年进士", ["年份", "personid", "姓名", "生", "卒", "朝代",
                                   "入仕途径", "名次", "科目", "年龄"])],
        run=_q5,
        slug=lambda v: f"{v[0] or ('person' + str(_int(v[1])))}年",
        btn="🎓 查同年",
    ),
    QuerySpec(
        key="Q6",
        tab="⑥ 任职轨迹",
        sparql=("`?t tenureHolder :X; tenureFirstYear ?y; tenureOffice/tenurePlace ?o/?pl "
                "ORDER BY ?y, ?seq`"),
        hint="按时间序的仕途",
        fields=[Field.number("personid")],
        sheets=[Sheet("任职", ["序", "官职", "首年", "末年", "地点", "任命类型",
                               "就任状态", "官职类别"])],
        run=_q6,
        slug=lambda v: f"person{_int(v[0])}",
        btn="📈 生成轨迹",
    ),
    QuerySpec(
        key="Q7",
        tab="⑦ 某县某朝",
        sparql="`?ac addrPlace/belongsTo* :county; addrPerson ?p. ?p dynastyOf ?d`",
        hint="地点层级闭包 + 朝代过滤（CBDB 地名多为繁体，输简体也能匹配）",
        fields=[Field.text("县/地点名关键词", "如：餘姚"),
                Field.text("朝代名（留空=全部）", default_fn=_default_dynasty)],
        sheets=[Sheet("人物", ["personid", "姓名", "生", "卒", "朝代", "地址类型",
                               "地址", "层级路径"])],
        run=_q7,
        slug=lambda v: f"{v[0]}_{v[1] or '全部朝代'}",
        btn="🏘 查询",
    ),
    QuerySpec(
        key="Q8",
        tab="⑧ 某书人物",
        sparql="`?trl roleType ?role; roleText :text; rolePerson ?p` ∪ `?p sourceOf :text`",
        hint="著作角色 + 史料来源两种关联",
        fields=[Field.text("书名关键词", "如：傳習錄")],
        sheets=[Sheet("人物", ["关联类型", "personid", "姓名", "生", "卒",
                               "角色/关系", "书名", "成书年"])],
        run=_q8,
        slug=lambda v: str(v[0]),
        btn="📖 查询",
    ),
    QuerySpec(
        key="Q9",
        tab="⑨ 学派主题网",
        sparql="`?ae assocTopic :理學; assocFrom/assocTo ?a/?b`",
        hint="按主题抽取交遊子网（节点 + 边）；CBDB 主题字段稀疏，无命中会自动列出可用候选",
        fields=[Field.text("主题/学派关键词", "如：理學")],
        sheets=[Sheet("人物节点", ["personid", "姓名", "朝代"]),
                Sheet("关系边", ["A_ID", "A", "B_ID", "B", "关系", "年份",
                                 "主题", "命中来源"])],
        run=_q9,
        slug=lambda v: str(v[0]),
        btn="🕸 展开网络",
    ),
]
