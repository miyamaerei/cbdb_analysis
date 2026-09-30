# -*- coding: utf-8 -*-
"""①~⑨ 九个专题查询页的**渲染器**。

页面本身不写死：遍历 specs.SPECS，按 QuerySpec 生成控件、绑定「查询 / 导出」两个按钮。
九个页面共用一套代码（约 60 行），改样式只改这里。
"""
import gradio as gr

import kg_backend as K
import kg_graph as QG
from . import specs as S
from .components import build_field, export_result, result_table, sparql_note
from .shared import err_md


def _index(quad):
    """取谓词子图索引（首次按 quadstore 抽取，约 3~4 秒，之后缓存）。"""
    return QG.get_index(quad) if quad else None


def build_topic_page(spec: S.QuerySpec, ctx):
    """按一个 QuerySpec 渲染出一整页（Tab）。"""
    with gr.Tab(spec.tab):
        sparql_note(spec.sparql, spec.hint)     # 已折成一行（见 components.sparql_note）
        with gr.Row(elem_classes=["kg-bar"]):
            blocks = [build_field(f) for f in spec.fields]
            run_btn = gr.Button(spec.btn, variant="primary")
            exp_btn = gr.Button("📦 导出")
        out_md = gr.Markdown(elem_classes=["kg-md"])
        shown = [s for s in spec.sheets if s.show]
        # 专题结果动辄 10 列：固定前两列（ID/姓名 或 A_ID/A），横向滚动时仍认得出是哪一行
        tables = [result_table(s.headers, label=s.name, pinned=[0, 1]) for s in shown]
        exp_md, exp_files = export_result()

    inputs = [ctx.quad] + blocks
    outputs = [out_md] + tables

    def _pack(md, rows=()):
        """单个输出时不能返回 tuple（Gradio 会把 (md,) 当成一个值去渲染）。"""
        return md if not shown else (md, *rows)

    def _run(quad, *vals):
        if not quad:
            return _pack("⚠️ 请先在「🔍 查询」页选择一个知识图谱。", [[]] * len(shown))
        try:
            g = _index(quad)      # 首次会抽子图，可能撞上 World 的写锁，一并兜住
            md, rows = spec.run(g, vals)
        except Exception as e:
            return _pack(err_md(e, "查询"), [[]] * len(shown))
        return _pack(md, [r for s, r in zip(spec.sheets, rows) if s.show])

    def _export(quad, *vals):
        if not quad:
            return "⚠️ 请先在「🔍 查询」页选择一个知识图谱。", []
        try:
            md, rows = spec.run(_index(quad), vals)
        except Exception as e:
            return err_md(e, "导出"), []
        tables_out = {s.name: (s.headers, r)
                      for s, r in zip(spec.sheets, rows) if r}
        _folder, files, msg = K.export_page(spec.tab, spec.slug(vals), tables_out)
        return msg, files

    # 显式 api_name（如 Q2_run / Q2_export）：自动编号的 _run_1 会随页面顺序漂移，
    # 脚本化调用和回归测试必须用稳定名字
    run_btn.click(_run, inputs=inputs, outputs=outputs, api_name=f"{spec.key}_run")
    # 关键词页支持回车即查
    for b in blocks:
        if isinstance(b, gr.Textbox):
            b.submit(_run, inputs=inputs, outputs=outputs)
    exp_btn.click(_export, inputs=inputs, outputs=[exp_md, exp_files],
                  api_name=f"{spec.key}_export")
    return {"run": run_btn, "exp": exp_btn, "md": out_md, "tables": tables}


def build(ctx):
    """渲染全部专题页（①~⑨）。"""
    pages = {}
    for spec in S.SPECS:
        pages[spec.tab] = build_topic_page(spec, ctx)
    return pages
