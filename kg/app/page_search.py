# -*- coding: utf-8 -*-
"""🔍 查询页：选图谱/朝代 + 条件检索（走源库 SQL，快）。

负责创建全局共享的「图谱下拉 / 朝代下拉 / 统计信息」，挂到 ctx 上给其它页复用。
"""
import gradio as gr

import kg_backend as K

from .components import quad_row, refresh_handler, result_table
from .shared import quad_info, sync_dynasty


def build(ctx):
    with gr.Tab("🔍 查询"):
        quad_dd, refresh_btn, info_md = quad_row(ctx)

        with gr.Row():
            dy_dd = gr.Dropdown(label="朝代（随图谱联动，可手改）",
                                choices=K.dynasty_choices(), value=19, scale=2)
            limit_dd = gr.Dropdown(label="最多返回", choices=[50, 200, 1000, 5000],
                                   value=200, scale=1)
        with gr.Row():
            name_tb = gr.Textbox(label="姓名（模糊）", placeholder="如：王守仁 / 王")
            py_tb = gr.Textbox(label="拼音（模糊）", placeholder="如：Wang Shouren")
            gender_rd = gr.Radio(["全部", "男", "女"], value="全部", label="性别")
        # 年份一律用 Textbox：gr.Number 的空值会被前端提交成 0（CBDB 0=未知）→ 0 命中
        with gr.Row():
            bf = gr.Textbox(label="生年 ≥", value="", placeholder="如 1472，留空=不限")
            bt = gr.Textbox(label="生年 ≤", value="", placeholder="如 1528")
            df_ = gr.Textbox(label="卒年 ≥", value="", placeholder="留空=不限")
            dt = gr.Textbox(label="卒年 ≤", value="", placeholder="留空=不限")
            ifrom = gr.Textbox(label="指数年 ≥", value="", placeholder="留空=不限")
            ito = gr.Textbox(label="指数年 ≤", value="", placeholder="留空=不限")
        with gr.Row():
            jinshi_cb = gr.Checkbox(label="仅进士", value=False)
            official_cb = gr.Checkbox(label="仅官员（有任职）", value=False)
            malt_cb = gr.Checkbox(label="别名也参与匹配", value=False)
            nb_cb = gr.Checkbox(label="含邻域人物（非本朝）", value=False)

        q_btn = gr.Button("🔍 查询", variant="primary")
        count_md = gr.Markdown()
        table = result_table(K.RESULT_HEADERS, label="结果（点一行 → 载入详情）")
        gr.Markdown("提示：试试姓名填 **王守仁**；或勾选「仅进士」+ 生年 1472~1528。")

    ctx.dy = dy_dd

    # ---------------------------------------------------------- 本页事件
    _refresh = refresh_handler(ctx)
    refresh_btn.click(_refresh, outputs=[quad_dd])
    quad_dd.change(sync_dynasty, inputs=[quad_dd], outputs=[dy_dd])
    quad_dd.change(quad_info, inputs=[quad_dd], outputs=[info_md])

    # 查询按钮在第 4 个输出上还要写「导出页」的条件栏，
    # 所以绑定放到 app.build_ui() 里做（那里所有页面都已建好）。
    return {"table": table, "count_md": count_md, "q_btn": q_btn,
            "quad": quad_dd, "info_md": info_md, "refresh": _refresh,
            "submitters": (name_tb, py_tb),
            "inputs": [name_tb, py_tb, gender_rd, bf, bt, df_, dt, ifrom, ito,
                       jinshi_cb, official_cb, malt_cb, nb_cb, limit_dd, dy_dd,
                       quad_dd, ctx.db_state],
            "outputs": [table, count_md, ctx.qstate]}
