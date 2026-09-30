# -*- coding: utf-8 -*-
"""专题查询实现：研究文档 §9 的 9 条 SPARQL 设计（Q1–Q9）。

与底座分离的原因：
  * `kg_graph.py` 只负责 quadstore → 内存谓词子图的索引（GraphIndex）；
  * 本文件只负责**查询逻辑**，不碰 sqlite、不碰 Gradio，改查询/加查询只看这一个文件。

统一调用契约（UI 层与脚本共用）：
    qN_xxx(g: GraphIndex, ...参数) -> 见各函数 docstring
  * 单表查询：  (headers, rows, md)
  * 双表（图）： (headers_nodes, nodes, headers_edges, edges, md)
  * Q1 档案：   (md, flat_rows)   flat_rows 用于导出

不依赖 gradio；可 `python -c "import kg_query"` 单独自检。
"""
from collections import defaultdict


# ============================================================ Q1 完整档案
def q1_dossier(g, pid):
    s = g.pid2s.get(int(pid))
    if s is None:
        return "⚠️ 图谱中没有 `person/%s`。" % pid, []
    b = lambda k: g.d(k, s)
    sex = {True: "女", False: "男"}.get(b("isFemale"), "未詳")
    dys = g.o("dynastyOf", s)
    lines = [
        f"### {b('nameChn') or '（无名）'}　`person/{pid}`　（{b('namePinyin') or ''}）",
        "",
        f"- 性别 **{sex}**　|　朝代 **{g.label.get(dys[0], '—') if dys else '—'}**",
        f"- 生 **{b('birthYear') or '—'}**　卒 **{b('deathYear') or '—'}**　"
        f"享年 {b('deathAge') or '—'}",
        f"- 指数年 **{b('indexYear') or '—'}**"
        + (f"（{g.cname_of(g.o('indexYearRule', s)[0])}）" if g.o("indexYearRule", s) else ""),
        f"- 活跃期 {b('floruitStart') or '—'} ~ {b('floruitEnd') or '—'}",
        "", "#### 别名",
        "、" .join(g.Dm.get("altName", {}).get(s, [])) or "（无）",
    ]
    flat = [["基本", "姓名", b("nameChn") or ""], ["基本", "拼音", b("namePinyin") or ""],
            ["基本", "性别", sex], ["基本", "朝代", g.label.get(dys[0], "") if dys else ""],
            ["基本", "生年", b("birthYear")], ["基本", "卒年", b("deathYear")],
            ["基本", "享年", b("deathAge")], ["基本", "指数年", b("indexYear")],
            ["基本", "活跃期", f"{b('floruitStart') or ''}~{b('floruitEnd') or ''}"]]
    for a in g.Dm.get("altName", {}).get(s, []):
        flat.append(["别名", "altName", a])

    def sec(title, headers, rows, keys):
        lines.append("")
        lines.append(f"#### {title}（{len(rows)} 条）")
        if rows:
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("|" + "|".join(["---"] * len(headers)) + "|")
            for r in rows[:200]:
                lines.append("| " + " | ".join("" if x is None else str(x) for x in r) + " |")
            if len(rows) > 200:
                lines.append(f"| … 其余 {len(rows) - 200} 条省略 |")
        else:
            lines.append("（无）")
        for r in rows:
            flat.append([title] + ["" if x is None else x for x in r])

    # 亲属
    rows = []
    for claim in g.rev("kinSource").get(s, []):
        kt = (g.o("kinType", claim) or [None])[0]
        rows.append(["出", g.cname_of(kt), g.plabel((g.o("kinTarget", claim) or [None])[0]),
                     g.tname.get((g.o("kinSourceText", claim) or [None])[0], ""),
                     g.d("upStep", kt) or g.d("dwnStep", kt) or ""])
    for claim in g.rev("kinTarget").get(s, []):
        kt = (g.o("kinType", claim) or [None])[0]
        rows.append(["入", g.cname_of(kt), g.plabel((g.o("kinSource", claim) or [None])[0]),
                     g.tname.get((g.o("kinSourceText", claim) or [None])[0], ""),
                     g.d("upStep", kt) or g.d("dwnStep", kt) or ""])
    sec("亲属", ["方向", "称谓", "对方", "史料", "世代"], rows, None)

    # 地址（带层级路径）
    rows = []
    for c in g.rev("addrPerson").get(s, []):
        pl = (g.o("addrPlace", c) or [None])[0]
        rows.append([g.cname_of((g.o("addrKind", c) or [None])[0]),
                     g.pname.get(pl, ""), g.place_path(pl) if pl else "",
                     g.d("addrFirstYear", c), g.d("addrLastYear", c)])
    sec("地址", ["类型", "地点", "层级路径", "首年", "末年"], rows, None)

    # 任职
    rows = []
    for t in g.rev("tenureHolder").get(s, []):
        rows.append([g.oname.get((g.o("tenureOffice", t) or [None])[0], ""),
                     g.d("tenureFirstYear", t), g.d("tenureLastYear", t),
                     "、".join(g.pname.get(x, "") for x in g.o("tenurePlace", t)),
                     g.cname_of((g.o("apptType", t) or [None])[0]),
                     g.cname_of((g.o("officeCategoryOf", t) or [None])[0])])
    rows.sort(key=lambda r: (r[1] is None, r[1] or 0, r[2] or 0))
    sec("任职", ["官职", "首年", "末年", "地点", "任命", "类别"], rows, None)

    # 入仕
    rows = [[g.cname_of((g.o("entryMode", e) or [None])[0]), g.d("entryYear", e),
             g.d("examRank", e), g.d("examField", e), g.d("entryAge", e)]
            for e in g.rev("entryPerson").get(s, [])]
    sec("入仕", ["途径", "年份", "名次", "科目", "年龄"], rows, None)

    # 身份
    rows = [[g.cname_of((g.o("statusConcept", x) or [None])[0]),
             g.d("statusFirstYear", x), g.d("statusLastYear", x)]
            for x in g.rev("statusPerson").get(s, [])]
    sec("身份", ["身份", "首年", "末年"], rows, None)

    # 著作
    rows = []
    for l in g.rev("rolePerson").get(s, []):
        tx = (g.o("roleText", l) or [None])[0]
        rows.append([g.cname_of((g.o("roleType", l) or [None])[0]),
                     g.tname.get(tx, ""), g.d("textYear", tx)])
    sec("著作", ["角色", "书名", "成书年"], rows, None)

    # 史料
    rows = [[g.tname.get(t, ""), g.d("textYear", t)] for t in g.o("sourceOf", s)]
    sec("史料", ["书名", "成书年"], rows, None)

    # 交遊（可能很多，只放前 200）
    rows = []
    for a in g.rev("assocFrom").get(s, []):
        rows.append(["出", g.cname_of((g.o("assocType", a) or [None])[0]),
                     g.plabel((g.o("assocTo", a) or [None])[0]), g.d("assocFirstYear", a)])
    for a in g.rev("assocTo").get(s, []):
        rows.append(["入", g.cname_of((g.o("assocType", a) or [None])[0]),
                     g.plabel((g.o("assocFrom", a) or [None])[0]), g.d("assocFirstYear", a)])
    sec("交遊", ["方向", "关系", "对方", "年份"], rows, None)

    return "\n".join(lines), flat


# ============================================================ Q2 亲属及称谓
def q2_kin(g, pid, direction="双向"):
    s = g.pid2s.get(int(pid))
    if s is None:
        # 契约是 (headers, rows, md) 三元组，早退分支也必须返回 3 个值
        # （曾经只返回 2 个 → UI 侧 `h, rows, md = ...` 直接 ValueError）
        return ["⚠️ 未找到该人物。"], [], "⚠️ 未找到该人物。"
    rows, stat = [], defaultdict(int)
    if direction in ("双向", "出"):
        for c in g.rev("kinSource").get(s, []):
            kt = (g.o("kinType", c) or [None])[0]
            tgt = (g.o("kinTarget", c) or [None])[0]
            nm = g.cname_of(kt)
            stat[nm] += 1
            rows.append(["出", nm, g.name.get(tgt, ""), g.s2pid.get(tgt),
                         g.d("upStep", kt), g.d("dwnStep", kt),
                         g.tname.get((g.o("kinSourceText", c) or [None])[0], "")])
    if direction in ("双向", "入"):
        for c in g.rev("kinTarget").get(s, []):
            kt = (g.o("kinType", c) or [None])[0]
            src = (g.o("kinSource", c) or [None])[0]
            nm = g.cname_of(kt)
            stat[nm] += 1
            rows.append(["入", nm, g.name.get(src, ""), g.s2pid.get(src),
                         g.d("upStep", kt), g.d("dwnStep", kt),
                         g.tname.get((g.o("kinSourceText", c) or [None])[0], "")])
    headers = ["方向", "称谓", "对方姓名", "对方ID", "上世代", "下世代", "史料"]
    md = (f"**{g.name.get(s, '')}（{pid}）** 亲属断言 **{len(rows)}** 条，"
          f"涉及 **{len({r[3] for r in rows})}** 人、**{len(stat)}** 种称谓。\n\n"
          "称谓分布：" + "　".join(f"`{k}`×{v}" for k, v in
                                sorted(stat.items(), key=lambda x: -x[1])[:20]))
    return headers, rows, md


# ============================================================ Q3 N 度家族网
def q3_kinnet(g, pid, depth=2, include_assoc=False, max_nodes=3000):
    s = g.pid2s.get(int(pid))
    if s is None:
        return ["⚠️ 未找到该人物。"], [], [], [], "⚠️ 未找到该人物。"
    nb_props = ["hasKin"] + (["hasAssociate"] if include_assoc else [])
    adj = defaultdict(set)
    for pname in nb_props:
        for a, bs in g.E.get(pname, {}).items():
            for b in bs:
                adj[a].add(b)
                adj[b].add(a)
    dist = {s: 0}
    parent = {s: (None, "")}
    frontier = [s]
    truncated = False
    for d in range(1, int(depth) + 1):
        nxt = []
        for x in frontier:
            for y in adj.get(x, ()):
                if y in dist:
                    continue
                if len(dist) >= int(max_nodes):
                    truncated = True
                    break
                dist[y] = d
                parent[y] = (x, "亲属" if y in g.E.get("hasKin", {}).get(x, [])
                             or x in g.E.get("hasKin", {}).get(y, []) else "交遊")
                nxt.append(y)
            if truncated:
                break
        if truncated or not nxt:
            break
        frontier = nxt
    nodes = []
    for x, d in dist.items():
        par, rel = parent.get(x, (None, ""))
        nodes.append([d, g.s2pid.get(x), g.name.get(x, ""), g.d("birthYear", x),
                      g.d("deathYear", x), g.dynasty_of(x), rel,
                      g.name.get(par, "") if par else "", g.s2pid.get(par) if par else None])
    nodes.sort(key=lambda r: (r[0], r[1] or 0))
    edges = []
    for x in dist:
        for y in adj.get(x, ()):
            if y in dist and x < y:
                edges.append([g.s2pid.get(x), g.name.get(x, ""), g.s2pid.get(y),
                              g.name.get(y, ""),
                              "亲属" if y in g.E.get("hasKin", {}).get(x, [])
                              or x in g.E.get("hasKin", {}).get(y, []) else "交遊",
                              min(dist[x], dist[y])])
    edges.sort(key=lambda r: (r[5], r[0] or 0))
    byd = defaultdict(int)
    for r in nodes:
        byd[r[0]] += 1
    md = (f"起点 **{g.name.get(s, '')}（{pid}）**　深度 **{depth}**　"
          f"关系 **{'亲属+交遊' if include_assoc else '仅亲属'}**\n\n"
          f"节点 **{len(nodes)}**（" + "　".join(f"{k}度 {v}" for k, v in sorted(byd.items()))
          + f"）　边 **{len(edges)}**" + ("　⚠️ 已达节点上限被截断" if truncated else ""))
    return (["度", "personid", "姓名", "生", "卒", "朝代", "与上层关系", "经由", "经由ID"],
            nodes, ["A_ID", "A", "B_ID", "B", "关系", "最小度"], edges, md)


# ============================================================ Q4 师承链
STUDENT_SIDE = ["為Y之學生", "為Y之門人", "為Y之弟子", "對Y執弟子禮", "從Y學",
                "向Y問學", "私淑Y之學", "宗Y之學", "為Y學派的成員", "門孫"]
TEACHER_SIDE = ["學生為Y", "門人為Y", "弟子為Y", "受Y之弟子禮", "其學為Y所宗",
                "其學為Y所私淑", "門人為Y之後代", "其學由Y傳授學生", "為 Y 的門孫"]
PEER_SIDE = ["同學", "同門", "論學", "講學", "研修理學"]


def teacher_code_sets(g):
    """返回 (学生侧概念集合, 老师侧概念集合, 同门集合)：以 concept storid 表示。"""
    stu, tea, peer = set(), set(), set()
    for name, cs in g.name2c.items():
        n = str(name)
        if any(k in n for k in STUDENT_SIDE):
            stu.add(cs)
        if any(k in n for k in TEACHER_SIDE):
            tea.add(cs)
        if any(k in n for k in PEER_SIDE):
            peer.add(cs)
    return stu, tea, peer


def q4_teacher(g, pid, direction="求师(向上)", depth=2, max_nodes=1500):
    """direction: 求师(向上) / 求弟子(向下)"""
    s = g.pid2s.get(int(pid))
    if s is None:
        return ["⚠️ 未找到该人物。"], [], "⚠️ 未找到该人物。"
    stu, tea, _ = teacher_code_sets(g)
    # teacher_of[x] = x 的老师集合；student_of[x] = x 的学生集合
    teacher_of, student_of = defaultdict(set), defaultdict(set)
    for a, types in ((a_, g.o("assocType", a_)) for a_ in g.E.get("assocType", {})):
        t = types[0] if types else None
        frm = (g.o("assocFrom", a) or [None])[0]
        to = (g.o("assocTo", a) or [None])[0]
        if frm is None or to is None:
            continue
        if t in stu:            # frm 是 to 的学生
            teacher_of[frm].add(to)
            student_of[to].add(frm)
        elif t in tea:          # frm 是 to 的老师
            teacher_of[to].add(frm)
            student_of[frm].add(to)
    nxt_of = teacher_of if "向上" in direction else student_of
    dist, parent, rel = {s: 0}, {s: None}, {s: ""}
    frontier, truncated = [s], False
    for d in range(1, int(depth) + 1):
        nf = []
        for x in frontier:
            for y in nxt_of.get(x, ()):
                if y in dist:
                    continue
                if len(dist) >= int(max_nodes):
                    truncated = True
                    break
                dist[y] = d
                parent[y] = x
                rel[y] = "師" if "向上" in direction else "弟子"
                nf.append(y)
            if truncated:
                break
        if truncated or not nf:
            break
        frontier = nf
    rows = [[d, g.s2pid.get(x), g.name.get(x, ""), g.d("birthYear", x), g.d("deathYear", x),
             g.dynasty_of(x), rel.get(x, ""), g.name.get(parent.get(x), ""),
             g.s2pid.get(parent.get(x)) if parent.get(x) else None,
             " → ".join(_chain(parent, g, x))]
            for x, d in dist.items()]
    rows.sort(key=lambda r: (r[0], r[1] or 0))
    headers = ["度", "personid", "姓名", "生", "卒", "朝代", "相对起点的身份",
               "经由", "经由ID", "师承链"]
    md = (f"起点 **{g.name.get(s, '')}（{pid}）**　方向 **{direction}**　深度 **{depth}**\n\n"
          f"命中 **{len(rows) - 1}** 人"
          + ("　⚠️ 已达上限被截断" if truncated else "")
          + f"　（师承类关系码 {len(stu | tea)} 种）")
    return headers, rows, md


def _chain(parent, g, x):
    out, cur, guard = [], x, 0
    while cur is not None and guard < 12:
        out.append(g.name.get(cur, "?"))
        cur = parent.get(cur)
        guard += 1
    return out[::-1]


# ============================================================ Q5 同年进士
def q5_jinshi(g, year=None, pid=None, limit=500):
    hdr = ["年份", "personid", "姓名", "生", "卒", "朝代", "入仕途径", "名次", "科目", "年龄"]
    note = ""
    # 年份栏被误填成 personid（> 3000）时自动纠正
    if year is not None and int(year) > 3000:
        pid, year = int(year), None
        note = "（年份栏填的是 %d，看着像 personid，已按人物处理）" % pid
    if year is None and pid is not None:
        s = g.pid2s.get(int(pid))
        if s is None:
            return hdr, [], (f"⚠️ 当前图谱里没有 `person/{int(pid)}`。\n\n"
                             "可能原因：① 该图谱不是这个人的朝代（先在「🔍 查询」页确认朝代）；"
                             "② 图谱尚未重建。")
        cands = []
        for e in g.rev("entryPerson").get(s, []):
            nm = g.cname_of((g.o("entryMode", e) or [None])[0])
            y = g.d("entryYear", e)
            if y:
                try:
                    cands.append((0 if "進士" in nm else 1, int(y), nm))
                except (TypeError, ValueError):
                    pass
        if not cands:
            return hdr, [], (f"⚠️ **{g.name.get(s, '')}**（{int(pid)}）在本图谱中没有任何带年份的入仕记录，"
                             "无法推出同年。请直接在左侧「年份」栏填年份（如 1499）。")
        cands.sort()
        year = cands[0][1]
        who = g.name.get(s, "") or f"person/{int(pid)}"
        note += (f"（取自 **{who}** 的进士年 **{year}**）" if cands[0][0] == 0
                 else f"（**{who}** 没有进士记录，改用其入仕年 **{year}**：{cands[0][2]}）")
    if year is None:
        return hdr, [], "请填年份，或填一个人物 ID 自动取其进士年。"
    year = int(year)
    rows, seen = [], set()
    for e, y in g.D.get("entryYear", {}).items():
        if y != year:
            continue
        m = (g.o("entryMode", e) or [None])[0]
        nm = g.cname_of(m)
        if "進士" not in nm:
            continue
        p = (g.o("entryPerson", e) or [None])[0]
        if p is None or p in seen:
            continue
        seen.add(p)
        rows.append([year, g.s2pid.get(p), g.name.get(p, ""), g.d("birthYear", p),
                     g.d("deathYear", p), g.dynasty_of(p), nm,
                     g.d("examRank", e), g.d("examField", e), g.d("entryAge", e)])
    rows.sort(key=lambda r: (str(r[7] or ""), r[1] or 0))
    headers = ["年份", "personid", "姓名", "生", "卒", "朝代", "入仕途径", "名次", "科目", "年龄"]
    ranks = defaultdict(int)
    for r in rows:
        ranks[str(r[7] or "未詳")] += 1
    md = (f"**{year} 年進士**　命中 **{len(rows)}** 人"
          + (f"（显示前 {limit}）" if len(rows) > int(limit) else "") + "\n\n" + note)
    if rows:
        md += "\n\n名次分布：" + "　".join(f"`{k}`×{v}" for k, v in
                                      sorted(ranks.items(), key=lambda x: -x[1])[:12])
    else:
        md += ("\n\n⚠️ 该年份在本图谱中没有進士记录。可先在「① 完整档案」页确认此人的入仕年，"
               "再把年份填到左侧「年份」栏。")
    return headers, rows[: int(limit)], md


# ============================================================ Q6 任职轨迹
def q6_tenure(g, pid):
    s = g.pid2s.get(int(pid))
    if s is None:
        return ["⚠️ 未找到该人物。"], [], "⚠️ 未找到该人物。"
    rows = []
    for t in g.rev("tenureHolder").get(s, []):
        rows.append([g.d("tenureSequence", t),
                     g.oname.get((g.o("tenureOffice", t) or [None])[0], ""),
                     g.d("tenureFirstYear", t), g.d("tenureLastYear", t),
                     "、".join(g.pname.get(x, "") for x in g.o("tenurePlace", t)),
                     g.cname_of((g.o("apptType", t) or [None])[0]),
                     g.cname_of((g.o("assumeStatus", t) or [None])[0]),
                     g.cname_of((g.o("officeCategoryOf", t) or [None])[0])])
    rows.sort(key=lambda r: (r[2] is None, r[2] or 9999, r[0] if r[0] is not None else 9999))
    headers = ["序", "官职", "首年", "末年", "地点", "任命类型", "就任状态", "官职类别"]
    dated = [r for r in rows if r[2]]
    md = (f"**{g.name.get(s, '')}（{pid}）** 任职 **{len(rows)}** 条，"
          f"其中 **{len(dated)}** 条有起始年份。\n\n"
          + (f"首任 **{dated[0][1]}**（{dated[0][2]}）　末任 **{dated[-1][1]}**（{dated[-1][2]}）"
             if dated else "（无年份可排序）"))
    return headers, rows, md


# ============================================================ Q7 某县某朝人物
def q7_county(g, keyword, dynasty="", limit=1000):
    if not keyword:
        return ["⚠️ 请填县名关键词。"], [], "⚠️ 请填县名关键词。"
    cands = g.match_by_name(g.pname, g.pname_s, keyword)
    if not cands:
        hint = "　".join(f"`{n}`×{c}" for n, c in g.top_places(12))
        return (["⚠️ 未找到匹配的地点。"], [],
                f"⚠️ 图谱中没有名称含「{keyword}」的地点（已自动尝试简繁体转换）。\n\n"
                f"本图谱最常引用的地点：{hint}\n\n"
                "提示：CBDB 地名多为繁体，如「余姚」请查「餘姚」——若仍无，说明该图谱里没有这个地点。")
    roots = {s for s, _ in cands}
    closure = g.place_closure(roots)
    dyn_storids = None
    if dynasty:
        dyn_storids = {d for d, lab in ((d, g.label.get(d)) for d in
                                        set(x for v in g.E.get("dynastyOf", {}).values() for x in v))
                       if lab == dynasty}
    rows = []
    for c, places in g.E.get("addrPlace", {}).items():
        pl = places[0]
        if pl not in closure:
            continue
        p = (g.o("addrPerson", c) or [None])[0]
        if p is None:
            continue
        if dyn_storids is not None:
            ds = set(g.o("dynastyOf", p))
            if not (ds & dyn_storids):
                continue
        rows.append([g.s2pid.get(p), g.name.get(p, ""), g.d("birthYear", p),
                     g.d("deathYear", p), g.dynasty_of(p),
                     g.cname_of((g.o("addrKind", c) or [None])[0]),
                     g.pname.get(pl, ""), g.place_path(pl)])
    rows.sort(key=lambda r: (r[2] is None, r[2] or 0))
    headers = ["personid", "姓名", "生", "卒", "朝代", "地址类型", "地址", "层级路径"]
    md = (f"县/地点关键词「**{keyword}**」→ 匹配 **{len(cands)}** 个地点，"
          f"含后代共 **{len(closure)}** 个" + (f"；朝代 **{dynasty}**" if dynasty else "") + "\n\n"
          f"命中人物 **{len(rows)}** 人"
          + (f"（显示前 {limit}）" if len(rows) > int(limit) else ""))
    return headers, rows[: int(limit)], md


# ============================================================ Q8 某书关联人物
def q8_book(g, keyword, limit=1000):
    if not keyword:
        return ["⚠️ 请填书名关键词。"], [], "⚠️ 请填书名关键词。"
    texts = {s for s, _ in g.match_by_name(g.tname, g.tname_s, keyword)}
    if not texts:
        return ["⚠️ 未找到匹配的书。"], [], f"⚠️ 图谱中没有书名含「{keyword}」的文本（已尝试简繁体转换）。"
    rows = []
    for l, txs in g.E.get("roleText", {}).items():
        tx = txs[0] if txs else None
        if tx not in texts:
            continue
        p = (g.o("rolePerson", l) or [None])[0]
        if p is None:
            continue
        rows.append(["著作角色", g.s2pid.get(p), g.name.get(p, ""), g.d("birthYear", p),
                     g.d("deathYear", p), g.cname_of((g.o("roleType", l) or [None])[0]),
                     g.tname.get(tx, ""), g.d("textYear", tx)])
    src_rev = g.rev("sourceOf")
    for p, txs in g.E.get("sourceOf", {}).items():
        for tx in txs:
            if tx in texts:
                rows.append(["史料来源", g.s2pid.get(p), g.name.get(p, ""),
                             g.d("birthYear", p), g.d("deathYear", p), "sourceOf",
                             g.tname.get(tx, ""), g.d("textYear", tx)])
    rows.sort(key=lambda r: (r[0], r[1] or 0))
    headers = ["关联类型", "personid", "姓名", "生", "卒", "角色/关系", "书名", "成书年"]
    md = (f"书名关键词「**{keyword}**」→ 匹配 **{len(texts)}** 种文本\n\n"
          f"关联人物记录 **{len(rows)}** 条，涉及 **{len({r[1] for r in rows})}** 人"
          + (f"（显示前 {limit}）" if len(rows) > int(limit) else ""))
    return headers, rows[: int(limit)], md


# ============================================================ Q9 学派/主题网络
def topic_candidates(g, limit=15):
    """图谱里实际被 assocTopic 用到的主题概念（数据很稀疏，给用户提示用）。"""
    cnt = defaultdict(int)
    for a, ts in g.E.get("assocTopic", {}).items():
        for t in ts:
            cnt[g.cname_of(t)] += 1
    return sorted(cnt.items(), key=lambda x: -x[1])[: int(limit)]


def assoc_type_candidates(g, keyword=None, limit=15):
    """交遊关系名及其出现次数（可按关键词过滤）。"""
    cnt = defaultdict(int)
    for a, ts in g.E.get("assocType", {}).items():
        for t in ts:
            n = g.cname_of(t)
            if keyword and str(keyword) not in str(n):
                continue
            cnt[n] += 1
    return sorted(cnt.items(), key=lambda x: -x[1])[: int(limit)]


def q9_topic(g, keyword, limit=2000):
    """主题/学派网络：命中 assocTopic 概念**或** assocType 关系名。
    （CBDB 的 c_topic_code 极稀疏，全明朝仅 25 条，所以关系名是主要可用维度。）"""
    if not keyword:
        return ["⚠️ 请填主题/学派关键词。"], [], "⚠️ 请填主题/学派关键词。"
    cons = {s for s, _ in g.match_by_name(g.cname, g.cname_s, keyword)}
    topics, type_cons = set(cons), set(cons)
    edges, rels, src = [], defaultdict(int), defaultdict(int)
    for a, ts in g.E.get("assocTopic", {}).items():
        if not (set(ts) & topics):
            continue
        frm = (g.o("assocFrom", a) or [None])[0]
        to = (g.o("assocTo", a) or [None])[0]
        if frm is None or to is None:
            continue
        rel = g.cname_of((g.o("assocType", a) or [None])[0])
        rels[rel] += 1
        src["主题"] += 1
        edges.append([g.s2pid.get(frm), g.name.get(frm, ""), g.s2pid.get(to), g.name.get(to, ""),
                      rel, g.d("assocFirstYear", a), g.cname_of(ts[0]), "主题"])
    for a, ts in g.E.get("assocType", {}).items():
        if not (set(ts) & type_cons):
            continue
        frm = (g.o("assocFrom", a) or [None])[0]
        to = (g.o("assocTo", a) or [None])[0]
        if frm is None or to is None:
            continue
        rel = g.cname_of(ts[0])
        rels[rel] += 1
        src["关系"] += 1
        edges.append([g.s2pid.get(frm), g.name.get(frm, ""), g.s2pid.get(to), g.name.get(to, ""),
                      rel, g.d("assocFirstYear", a), "", "关系类型"])
    edges.sort(key=lambda r: (r[5] is None, r[5] or 0))
    people = {}
    for e in edges:
        people[e[0]] = e[1]
        people[e[2]] = e[3]
    nodes = [[k, v, g.dynasty_of(g.pid2s.get(k)) if k in g.pid2s else ""]
             for k, v in people.items()]
    md = (f"关键词「**{keyword}**」→ 命中主题概念 **{len(topics)}** 个 / "
          f"关系类型 **{len(type_cons)}** 种（主题来源 {src.get('主题', 0)} 条、"
          f"关系来源 {src.get('关系', 0)} 条）\n\n"
          f"边 **{len(edges)}** 条　节点 **{len(nodes)}** 人"
          + (f"（显示前 {limit}）" if len(edges) > int(limit) else ""))
    if rels:
        md += "\n\n主要关系：" + "　".join(f"`{k}`×{v}" for k, v in
                                      sorted(rels.items(), key=lambda x: -x[1])[:10])
    if not edges:
        tc = topic_candidates(g, 10)
        ac = assoc_type_candidates(g, None, 10)
        md += ("\n\n⚠️ 无命中。CBDB 的 `assocTopic`（学术主题）字段极稀疏，"
               "建议改用关系名检索。\n\n可用主题概念："
               + ("　".join(f"`{k}`×{v}" for k, v in tc) if tc else "（本图谱无）")
               + "\n\n高频关系名：" + "　".join(f"`{k}`×{v}" for k, v in ac))
    return (["personid", "姓名", "朝代"], nodes,
            ["A_ID", "A", "B_ID", "B", "关系", "年份", "主题", "命中来源"],
            edges[: int(limit)], md)
