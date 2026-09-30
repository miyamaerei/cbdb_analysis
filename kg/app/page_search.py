# -*- coding: utf-8 -*-
"""🔍 查询页：选图谱/朝代 + 条件检索（走源库 SQL，快）。

负责创建全局共享的「图谱下拉 / 朝代下拉 / 统计信息」，挂到 ctx 上给其它页复用。

## 布局：三区分离（对齐 web 端 `web/FILTER_UX.md` 第 3 节）

改版前这里平铺了 4 行控件（朝代+上限 / 姓名+拼音+性别 / 6 个年份 / 4 个复选框）
再加按钮和两段说明，结果表被顶到屏幕外，只剩不到半屏。

    ┌ 图谱行（一行）──── 知识图谱下拉 · 刷新 · 统计 ────────────┐
    ├ 工具栏（恒一行）── 姓名 · 朝代 · 最多返回 · 🔍 查询 ──────┤
    ├ 命中提示（一行）── 命中数 · 排序 · **已生效条件摘要** ────┤
    ├ ⚙ 更多条件（折叠）拼音/性别/年份/仅进士/排序/显示列/密度 ─┤
    └ 结果表（吃满剩余高度，表头吸顶，ID+姓名固定）────────────┘

两条刻意的设计：

1. **条件可以收起来，但「筛了什么」必须一直看得见** —— 折叠区的状态回显在
   命中提示那行（`K.cond_summary`），否则用户会不知道结果为什么是这些。
2. **Gradio 的 Dataframe 点不了表头排序**，所以排序做成折叠区里的一个下拉 +
   升/降方向，改动后自动重查（等价于 web 端「点表头」的即时反馈）。
"""
import gradio as gr

import kg_backend as K

from . import handlers as H
from .components import quad_row, refresh_handler, result_table
from .shared import quad_info, sync_dynasty

# 默认显示列（ID 与姓名恒定在最前，见 K.RESULT_LOCKED_COLS）
_INIT_COLS = K.result_cols(K.RESULT_DEFAULT_COLS)


def build(ctx):
    with gr.Tab("🔍 查询"):
        quad_dd, refresh_btn, info_md = quad_row(ctx)

        # ------------------------------------------------ 工具栏（恒定一行）
        with gr.Row(elem_classes=["kg-bar"]):
            name_tb = gr.Textbox(label="姓名（模糊，简繁自动）",
                                 placeholder="王守仁 / 王阳明 / 王", scale=3)
            dy_dd = gr.Dropdown(label="朝代", choices=K.dynasty_choices(),
                                value=19, scale=3)
            limit_dd = gr.Dropdown(label="最多返回", choices=[200, 500, 2000, 5000],
                                   value=500, scale=1)
            q_btn = gr.Button("🔍 查询", variant="primary", scale=1)

        count_md = gr.Markdown(elem_classes=["kg-md"])

        # ------------------------------------------------ 更多条件与显示设置
        with gr.Accordion(
                "⚙ 更多条件与显示设置　（拼音 / 性别 / 生卒年 / 指数年 / 仅进士 / 排序 / 显示列 / 行高）",
                open=False, elem_classes=["kg-cond"]):
            with gr.Row(elem_classes=["kg-bar"]):
                py_tb = gr.Textbox(label="拼音（模糊）", placeholder="Wang Shouren", scale=2)
                gender_rd = gr.Radio(["全部", "男", "女"], value="全部", label="性别", scale=2)
                order_dd = gr.Dropdown(label="排序", choices=K.ORDER_CHOICES,
                                       value="personid", scale=2)
                # choices 用 (标签, 值) 形式 → 直接拿到 bool，省一层转换
                order_dir = gr.Radio(choices=[("升序 ↑", False), ("降序 ↓", True)],
                                     value=False, label="方向", scale=1)
            # 年份一律用 Textbox：gr.Number 的空值会被前端提交成 0（CBDB 0=未知）→ 0 命中
            with gr.Row(elem_classes=["kg-bar"]):
                bf = gr.Textbox(label="生年 ≥", value="", placeholder="如 1472")
                bt = gr.Textbox(label="生年 ≤", value="", placeholder="留空=不限")
                df_ = gr.Textbox(label="卒年 ≥", value="", placeholder="留空=不限")
                dt = gr.Textbox(label="卒年 ≤", value="", placeholder="留空=不限")
                ifrom = gr.Textbox(label="指数年 ≥", value="", placeholder="留空=不限")
                ito = gr.Textbox(label="指数年 ≤", value="", placeholder="留空=不限")
            with gr.Row(elem_classes=["kg-bar"]):
                jinshi_cb = gr.Checkbox(label="仅进士", value=False)
                official_cb = gr.Checkbox(label="仅官员（有任职）", value=False)
                malt_cb = gr.Checkbox(label="别名也参与匹配", value=False)
                nb_cb = gr.Checkbox(label="含邻域人物（非本朝）", value=False)
                dense_cb = gr.Checkbox(label="紧凑行高", value=True)
            with gr.Row(elem_classes=["kg-bar"]):
                col_cb = gr.CheckboxGroup(
                    choices=K.RESULT_TOGGLE_COLS, value=K.RESULT_DEFAULT_COLS,
                    label="显示列（ID 与姓名恒显示；列越少单列越宽）")

        table = result_table(K.display_headers(_INIT_COLS),
                             label="结果（点一行 → 载入详情）",
                             pinned=list(range(len(K.RESULT_LOCKED_COLS))),
                             column_widths=K.col_widths(_INIT_COLS))

    ctx.dy = dy_dd

    # ---------------------------------------------------------- 本页事件
    _refresh = refresh_handler(ctx)
    refresh_btn.click(_refresh, outputs=[quad_dd])
    quad_dd.change(sync_dynasty, inputs=[quad_dd], outputs=[dy_dd])
    quad_dd.change(quad_info, inputs=[quad_dd], outputs=[info_md])

    # 「显示列 / 行高」→ 用上次查询的完整结果即时重绘，不重新查库
    for c in (col_cb, dense_cb):
        c.change(H.apply_view, inputs=[ctx.qstate, col_cb, dense_cb], outputs=[table])

    # 查询按钮在第 4 个输出上还要写「导出页」的条件栏，
    # 所以绑定放到 app.build_ui() 里做（那里所有页面都已建好）。
    return {"table": table, "count_md": count_md, "q_btn": q_btn,
            "quad": quad_dd, "info_md": info_md, "refresh": _refresh,
            "submitters": (name_tb,),
            # 这些控件一变就重查（排序是「点表头排序」在 Gradio 里的等价物）
            "reactive": (order_dd, order_dir, limit_dd),
            "inputs": [name_tb, py_tb, gender_rd, bf, bt, df_, dt, ifrom, ito,
                       jinshi_cb, official_cb, malt_cb, nb_cb, limit_dd, dy_dd,
                       quad_dd, ctx.db_state,
                       order_dd, order_dir, col_cb, dense_cb],
            "outputs": [table, count_md, ctx.qstate]}
