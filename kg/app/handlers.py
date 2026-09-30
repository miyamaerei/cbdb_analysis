# -*- coding: utf-8 -*-
"""页面回调（handlers）：查询 / 详情 / 导出 / 构建四条主链路的业务逻辑。

这里不出现任何 gr.* 组件创建代码，只做「入参 → 出参」，
方便单独 import 后跑脚本自检（不需要 Gradio 在跑）。
"""
import gradio as gr

import kg_backend as K

from .shared import AppCtx, err_md


# ============================================================ 查询
def _year(x):
    """年份输入统一走 Textbox：空 / 非数字 → None（当作不限）。

    历史坑：这里曾经是 gr.Number，前端把空值提交成 0，
    于是生成 `生年>=0 AND 生年<=0` → 永远 0 命中。
    """
    if x in (None, "", 0):
        return None
    try:
        return int(str(x).strip())
    except (TypeError, ValueError):
        return None


def do_query(name, pinyin, gender, bf, bt, df_, dt, ifrom, ito,
             jinshi, official, malt, nb, lim, dy, quad, db):
    """条件检索（走源库 SQL）。0 命中时自动降级：开别名 → 去姓氏试字号。"""
    # 年份可能是 ""（Textbox 空）或 0（旧版 Number 提交），统一归一成 int/None
    bf, bt, df_, dt, ifrom, ito = (_year(x) for x in (bf, bt, df_, dt, ifrom, ito))
    note, used = "", name or ""

    def _search(nm, ma):
        return K.search_persons(
            db=db, dy=dy, name=nm, pinyin=pinyin, gender=gender,
            birth_from=bf, birth_to=bt, death_from=df_, death_to=dt,
            index_from=ifrom, index_to=ito, jinshi_only=jinshi,
            official_only=official, match_alt=ma, include_neighbors=nb,
            limit=int(lim or 200))

    try:
        rows, total = _search(name, malt)
        # 回退链：① 开别名 ② 去姓氏试字号（王阳明 → 阳明 → 命中别名「陽明先生」）
        if total == 0 and name:
            chain = [(name, True, "别名")]
            if len(name) >= 3:
                for cut in (name[1:], name[-2:]):
                    if cut != name:
                        chain.append((cut, True, f"去姓氏「{cut}」+ 别名"))
            for nm, ma, label in chain:
                rows, total = _search(nm, ma)
                if total:
                    malt, used, note = ma, nm, f"（原名 0 命中，已自动改用 **{label}** 匹配）"
                    break
    except Exception as e:
        msg = err_md(e, "查询")
        return [], msg, {"cond": None, "rows": []}, msg

    # 回退命中时把「同姓氏」的排前面（王阳明 → 王守仁 优先于 傅陽明）
    if note and name and len(name) >= 2 and rows:
        first = name[0]
        rows = sorted(rows, key=lambda r: (0 if first in (r[1] or "") else 1, r[0]))

    cond = {"dy": dy, "dynasty_name": K.dynasty_name(dy, db), "name": name or "",
            "pinyin": pinyin or "", "gender": gender, "birth_from": bf, "birth_to": bt,
            "death_from": df_, "death_to": dt, "index_from": ifrom, "index_to": ito,
            "jinshi_only": bool(jinshi), "official_only": bool(official),
            "match_alt": bool(malt), "include_neighbors": bool(nb),
            "limit": int(lim or 200), "quad": quad, "db": db}
    md = (f"命中 **{total:,}** 条，显示前 **{len(rows):,}** 条　|　"
          f"朝代 **{cond['dynasty_name']}**（c_dy={dy}）　|　"
          "点结果中的一行可载入「📄 详情」" + note)
    if total == 0:
        md += ("\n\n⚠️ 0 命中排查：① 当前朝代是 **{d}**，此人可能不在该朝（换朝代试试）；"
               "② CBDB 是**繁体**库，简体已自动转换并已试过别名/字号，仍无则库里确实没有；"
               "③ 试只输一个字（如「王」）；④ 勾选「含邻域人物」。"
               ).format(d=cond["dynasty_name"])
    return rows, md, {"cond": cond, "rows": rows}, K.cond_summary(cond)


def pick_row(evt: gr.SelectData, table):
    """查询页结果表：点一行 → 取 personid。"""
    try:
        idx = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
        return int(table[int(idx)][0])
    except Exception:
        return gr.skip()


def pick_person(evt: gr.SelectData, table, col=3):
    """详情表：点一行 → 取「对方ID」列。"""
    try:
        idx = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
        pid = table[int(idx)][col]
        return int(pid) if pid not in (None, "") else gr.skip()
    except Exception:
        return gr.skip()


# ============================================================ 详情
def _empty_sections():
    return [[] for _ in range(8)]


def _quad_dyn(quad):
    """图谱路径 → 朝代名（用于提示文案）。"""
    for i in K.quadstores():
        if i["path"] == quad:
            return i["dynasty"]
    return "?"


def load_detail(pid, quad, db):
    """单人全部信息（读 quadstore）。返回 [基本md, 统计md, 8 张分区表]。

    当前图谱里没有这个人时，会去**其它图谱里找**（常见于默认图谱不是该人物所属朝代），
    找到就直接显示，并在统计栏注明「已自动切到《明》图谱」。
    """
    if pid in (None, ""):
        return ["请填写人物 c_personid（可先在「🔍 查询」页点一行）", ""] + _empty_sections()
    try:
        pid_i = int(str(pid).strip())
    except (TypeError, ValueError):
        return [f"⚠️ personid 必须是数字，收到「{pid}」。", ""] + _empty_sections()

    try:
        d = K.person_detail(quad, pid_i, db)
        switched = ""
        if d is None:
            # 当前图谱没有 → 扫描其它 quadstore
            hit = K.find_quad_with_person(pid_i, exclude=quad)
            if hit is not None:
                d = K.person_detail(hit["path"], pid_i, db)
                switched = (f"　|　⚠️ 当前图谱《{_quad_dyn(quad)}》里没有 `person/{pid_i}`，"
                            f"已自动改用《{hit['dynasty']}》图谱")
    except Exception as e:
        return [err_md(e, "载入"), ""] + _empty_sections()

    if d is None:
        known = "、".join(f"《{i['dynasty']}》" for i in K.quadstores())
        return [f"⚠️ 所有已构建的图谱里都没有 `person/{pid_i}`。"
                f"（现有图谱：{known or '无'}）\n\n"
                f"可能原因：① 该人物所属朝代还没构建图谱（到「⚙️ 构建」页跑一下）；"
                f"② personid 输错了（可回「🔍 查询」页按姓名搜）。", ""] + _empty_sections()
    if "error" in d:
        return [f"⚠️ {d['error']}", ""] + _empty_sections()
    return [K.format_basic(d),
            f"亲属 {len(d['kin'])} · 交遊 {len(d['assoc'])} · 任职 {len(d['tenure'])} · "
            f"入仕 {len(d['entry'])} · 地址 {len(d['addr'])} · 身份 {len(d['status'])} · "
            f"著作 {len(d['text'])} · 史料 {len(d['source'])}" + switched,
            d["kin"], d["assoc"], d["tenure"], d["entry"],
            d["addr"], d["status"], d["text"], d["source"]]


# ============================================================ 导出
def do_export(state, formats, with_detail, dlimit, quad):
    cond = (state or {}).get("cond")
    rows = (state or {}).get("rows") or []
    if not cond:
        return "⚠️ 请先在「🔍 查询」页执行一次查询。", []
    try:
        folder, files, msg = K.export_results(
            cond, rows, formats=formats or ("CSV",), with_detail=bool(with_detail),
            detail_limit=int(dlimit or 50), quad=quad, db=cond.get("db"))
    except Exception as e:
        return err_md(e, "导出"), []
    return msg, files


# ============================================================ 构建
def set_db(p):
    p = (p or "").strip()
    return K.DEFAULT_DB if not p else p


def run_etl_ui(db, dy, lim):
    """必须是**具名生成器函数**：Gradio 用 inspect.isgeneratorfunction 判断是否流式输出。

    之前写成 `lambda db, dy, lim: K.run_etl(...)`，lambda 不是生成器函数，
    Gradio 会把「生成器对象」当成返回值去序列化 → 点击构建毫无反应（且不报错）。
    """
    yield from K.run_etl(db, dy, int(lim or 0))


# ============================================================ 跨页连线
def load_detail_from_row(evt: gr.SelectData, table, quad, db, col=0):
    """点表格某一行 → 直接载入该行对应人物（col=0 是自己，col=3 是「对方ID」）。

    为什么不写成 `select(pick_x).then(load_detail)`：
    then 链要由前端驱动第二次请求，脚本化调用（curl / gradio_client）拿不到后续事件，
    而且链断掉时详情区会静默不更新。改成同事件的**第二个独立回调**，两条都稳。
    """
    try:
        idx = evt.index[0] if isinstance(evt.index, (list, tuple)) else evt.index
        pid = table[int(idx)][col]
        if pid in (None, ""):
            return gr.skip()
    except Exception:
        return gr.skip()
    return load_detail(pid, quad, db)


def load_self_from_row(evt: gr.SelectData, table, quad, db):
    """查询页结果表：点一行载入「自己」（第 0 列 personid）。"""
    return load_detail_from_row(evt, table, quad, db, col=0)


def load_other_from_row(evt: gr.SelectData, table, quad, db):
    """详情页关系表：点一行载入「对方」（第 3 列 对方ID）。"""
    return load_detail_from_row(evt, table, quad, db, col=3)


def _goto_tab(tab_id):
    """返回「切到某个 Tab」的回调（Gradio 用 gr.Tabs(selected=<Tab 的 id>) 控制）。"""
    def _fn():
        return gr.Tabs(selected=tab_id)
    return _fn


def bind_cross_page(ctx: AppCtx, search: dict, detail: dict):
    """跨页事件链：查询页点一行 → 写 personid → 载入详情 → 自动切到详情 Tab。

    放在这里是因为它同时引用多个页面的组件，页面自己拿不全。
    不切 Tab 的话详情数据变了但用户看不见，会以为「点了没反应」。
    """
    table = search["table"]
    # ① 把 personid 写进详情页输入框
    table.select(pick_row, inputs=[table], outputs=[ctx.pid])
    # ② 直接载入详情（不靠 then 链）
    table.select(load_self_from_row, inputs=[table, ctx.quad, ctx.db_state],
                 outputs=ctx.detail_out)
    # ③ 自动切到详情页（否则数据变了用户看不见）
    if getattr(ctx, "tabs", None) is not None:
        table.select(_goto_tab("tab_detail"), inputs=None, outputs=[ctx.tabs])
