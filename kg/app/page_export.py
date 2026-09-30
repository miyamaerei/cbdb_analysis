# -*- coding: utf-8 -*-
"""📦 导出页：复用「🔍 查询」最近一次的查询条件与结果，导出到 exports/<条件>_<日期>/。"""
import gradio as gr

import kg_backend as K

from . import handlers as H


def build(ctx):
    with gr.Tab("📦 导出"):
        gr.Markdown("复用「🔍 查询」页最近一次的查询条件与结果；"
                    "导出目录 = `kg/exports/<查询条件>_<日期>/`。", elem_classes=["kg-md"])
        cond_md = gr.Markdown("（尚未查询）", elem_classes=["kg-md"])
        with gr.Row(elem_classes=["kg-bar"]):
            sync_btn = gr.Button("↻ 同步当前查询条件")
            fmt_cg = gr.CheckboxGroup(["CSV", "JSON"], value=["CSV"], label="导出格式")
        with gr.Row(elem_classes=["kg-bar"]):
            detail_cb = gr.Checkbox(label="同时导出每人明细摘要", value=False)
            dlimit_nb = gr.Textbox(label="明细最多人数", value="50")
        exp_btn = gr.Button("📦 导出到文件夹", variant="primary")
        out_md = gr.Markdown("", elem_classes=["kg-md"])
        files_fl = gr.Files(label="导出文件（可直接下载）")

    # ---------------------------------------------------------- 本页事件
    sync_btn.click(lambda st: K.cond_summary((st or {}).get("cond")),
                   inputs=[ctx.qstate], outputs=[cond_md])
    exp_btn.click(H.do_export,
                  inputs=[ctx.qstate, fmt_cg, detail_cb, dlimit_nb, ctx.quad],
                  outputs=[out_md, files_fl], api_name="export_run")

    return {"cond_md": cond_md, "exp_btn": exp_btn, "out_md": out_md, "files": files_fl}
