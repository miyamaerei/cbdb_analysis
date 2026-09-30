# -*- coding: utf-8 -*-
"""共同组件工厂：页面里反复出现的那几块 UI，全部在这里统一风格与默认值。

放在一处的好处：改一次表头样式/交互参数，13 个 Tab 一起生效；
也让页面文件只剩「摆控件 + 绑事件」，读起来是一页纸。
"""
import gradio as gr

import kg_backend as K
from .shared import Field, refresh_quads


def result_table(headers, label=None, **kw):
    """只读结果表（页面里所有表格都走这个，保证 type/wrap/interactive 一致）。"""
    kw.setdefault("type", "array")
    kw.setdefault("interactive", False)
    kw.setdefault("wrap", True)
    return gr.Dataframe(headers=list(headers), value=[], label=label, **kw)


def section_table(key, label=None):
    """详情页的分区表：表头取自 K.SECTION_HEADERS。"""
    return result_table(K.SECTION_HEADERS[key], label=label)


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
    with gr.Row():
        quad_dd = gr.Dropdown(label="知识图谱（quadstore）", choices=choices,
                              value=(choices[0][1] if choices else None),
                              allow_custom_value=True, scale=scale_dd)
        refresh_btn = gr.Button("🔄 刷新列表", scale=scale_btn)
    info_md = gr.Markdown()
    ctx.quad = quad_dd
    ctx.info_md = info_md
    return quad_dd, refresh_btn, info_md


def export_result(files_label="导出文件"):
    """导出结果区：提示 Markdown + 可下载文件列表（专题页与导出页共用）。"""
    out_md = gr.Markdown()
    files = gr.Files(label=files_label)
    return out_md, files


def sparql_note(sparql, hint=""):
    """专题页顶部那行「SPARQL 原型」说明。"""
    md = f"**SPARQL 原型**：{sparql}"
    if hint:
        md += f"\n\n{hint}"
    return gr.Markdown(md)


def refresh_handler(ctx):
    """返回闭包版的「刷新图谱列表」回调。

    ⚠️ 必须是闭包：refresh_quads 要拿到 quad_dd 本体去改服务端 choices，
    直接把函数塞进 .click() 拿不到组件对象。
    """
    def _refresh():
        return refresh_quads(ctx.quad)
    return _refresh
