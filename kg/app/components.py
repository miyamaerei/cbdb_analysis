# -*- coding: utf-8 -*-
"""共同组件工厂：页面里反复出现的那几块 UI，全部在这里统一风格与默认值。

放在一处的好处：改一次表头样式/交互参数，13 个 Tab 一起生效；
也让页面文件只剩「摆控件 + 绑事件」，读起来是一页纸。

本轮的布局改造（对齐 web 端 `web/FILTER_UX.md`）主要落在两个函数：
  * `result_table()` —— 结果表统一 `max_height`（吃满剩余高度）、表头吸顶、
    行号列、表内快搜、左侧固定列；尺寸分两档 big/small。
  * `sparql_note()` —— 专题页顶部那段 SPARQL 原型说明很长，收进折叠条，
    默认只占一行。
"""
import gradio as gr

import kg_backend as K
from . import theme
from .shared import Field, refresh_quads


def result_table(headers, label=None, size="big", pinned=None,
                 elem_classes=None, **kw):
    """只读结果表（页面里所有表格都走这个，保证 type/wrap/interactive 一致）。

    size="big"   查询页 / 专题页：高度用 calc(100vh - N)，尽量吃满剩余视口
    size="small" 详情页的 8 个分区表：可能同时展开好几个，用固定 430px

    pinned 传列下标列表（如 [0, 1]）→ 横向滚动时这几列固定在最左，
    长表（专题页的 10 列、查询页 14 列）横拉时仍能看清是谁的行。
    """
    kw.setdefault("type", "array")
    kw.setdefault("interactive", False)
    kw.setdefault("wrap", True)
    kw.setdefault("show_row_numbers", True)
    kw.setdefault("show_search", "search")     # 表内前端快搜：已在结果里再过滤
    kw.setdefault("max_height", theme.BIG_DF if size == "big" else theme.SMALL_DF)
    if pinned:
        kw.setdefault("pinned_columns", list(pinned))
    cls = [f"kg-df{'-sm' if size == 'small' else ''}"]
    if elem_classes:
        cls = list(elem_classes) + cls
    kw["elem_classes"] = cls
    return gr.Dataframe(headers=list(headers), value=[], label=label, **kw)


def section_table(key, label=None):
    """详情页的分区表：表头取自 K.SECTION_HEADERS，尺寸走 small 档。"""
    return result_table(K.SECTION_HEADERS[key], label=label, size="small")


def build_field(f: Field):
    """把 Field 描述渲染成真实控件。"""
    kw = {"scale": f.scale} if f.scale else {}
    val = f.resolve_default()
    if f.kind == "number":
        # ⚠️ 不用 gr.Number：前端把空的 number input 序列化成 **0** 提交
        # （CBDB 里 0 = 未知年份），历史上造成 `生年>=0 AND 生年<=0` 的 0 命中。
        # 用 Textbox：空就是 ""，由后端解析成 None。
        return gr.Textbox(label=f.label, value="" if val is None else str(val),
                          placeholder="数字，留空=不限", **kw)
    if f.kind == "text":
        return gr.Textbox(label=f.label, value=val or "",
                          placeholder=f.placeholder or None, **kw)
    if f.kind == "radio":
        return gr.Radio(f.choices, value=val, label=f.label, **kw)
    if f.kind == "dropdown":
        return gr.Dropdown(choices=f.choices, value=val, label=f.label, **kw)
    if f.kind == "checkbox":
        return gr.Checkbox(label=f.label, value=bool(val), **kw)
    raise ValueError(f"未知控件类型：{f.kind}")


def quad_row(ctx, scale_dd=4, scale_btn=1):
    """顶部「知识图谱」选择行：下拉 + 刷新按钮 + 统计信息。

    返回 (quad_dd, refresh_btn, info_md)；并把 quad_dd / info_md 挂到 ctx 上。
    """
    choices = K.quad_choices()
    with gr.Row(elem_classes=["kg-bar"]):
        quad_dd = gr.Dropdown(label="知识图谱（quadstore）", choices=choices,
                              value=(choices[0][1] if choices else None),
                              allow_custom_value=True, scale=scale_dd)
        refresh_btn = gr.Button("🔄 刷新列表", scale=scale_btn)
    info_md = gr.Markdown(elem_classes=["kg-md"])
    ctx.quad = quad_dd
    ctx.info_md = info_md
    return quad_dd, refresh_btn, info_md


def export_result(files_label="导出文件"):
    """导出结果区：提示 Markdown + 可下载文件列表（专题页与导出页共用）。"""
    out_md = gr.Markdown(elem_classes=["kg-md"])
    files = gr.Files(label=files_label)
    return out_md, files


def sparql_note(sparql, hint=""):
    """专题页顶部那段「SPARQL 原型」说明。

    它天然有 2~4 行（原型一行 + 提示一行），9 个专题页各来一段，
    等于结果表每次都被顶下去 40~70px。收进折叠条后默认只占一行。
    """
    with gr.Accordion("🔍 SPARQL 原型与查询说明", open=False, elem_classes=["kg-cond"]):
        md = f"**SPARQL 原型**：{sparql}"
        if hint:
            md += f"\n\n{hint}"
        gr.Markdown(md, elem_classes=["kg-md"])


def refresh_handler(ctx):
    """返回闭包版的「刷新图谱列表」回调。

    ⚠️ 必须是闭包：refresh_quads 要拿到 quad_dd 本体去改服务端 choices，
    直接把函数塞进 .click() 拿不到组件对象。
    """
    def _refresh():
        return refresh_quads(ctx.quad)
    return _refresh
