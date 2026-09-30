# -*- coding: utf-8 -*-
"""⚙️ 构建页：动态选朝代跑 etl_seed_ming.py，产物写入 kg/quadstore/cbdb_dy<N>.sqlite3。"""
import gradio as gr

import kg_backend as K

from . import handlers as H
from .shared import quad_info


def build(ctx):
    with gr.Tab("⚙️ 构建"):
        gr.Markdown("选择朝代 → 运行 `etl_seed_ming.py --dy <朝代>`，"
                    "产物写入 `kg/quadstore/cbdb_dy<N>.sqlite3` + `.meta.json`。")
        with gr.Row():
            bdy_dd = gr.Dropdown(label="朝代", choices=K.dynasty_choices(), value=19, scale=3)
            blimit_nb = gr.Textbox(label="限制人物数（留空/0=全部，调试用）", value="0", scale=1)
        with gr.Accordion("源库路径（高级）", open=False):
            db_tb = gr.Textbox(label="CBDB SQLite 路径", value=K.DEFAULT_DB)
            db_btn = gr.Button("应用路径")
        run_btn = gr.Button("▶ 运行 ETL 构建知识图谱", variant="primary")
        log_tb = gr.Textbox(label="运行日志", lines=18, max_lines=24, autoscroll=True)

    # ---------------------------------------------------------- 本页事件
    db_btn.click(H.set_db, inputs=[db_tb], outputs=[ctx.db_state])
    run_btn.click(H.run_etl_ui, inputs=[ctx.db_state, bdy_dd, blimit_nb],
                  outputs=[log_tb], api_name="build_run") \
           .then(ctx.pages["search"]["refresh"], outputs=[ctx.quad]) \
           .then(quad_info, inputs=[ctx.quad], outputs=[ctx.info_md])

    return {"run_btn": run_btn, "log_tb": log_tb, "dy": bdy_dd}
