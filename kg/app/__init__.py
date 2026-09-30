# -*- coding: utf-8 -*-
"""UI 组装层：把 5 个页面模块拼成一个 Gradio Blocks。

分层约定（依赖单向，不出现循环导入）：
    kg_backend / kg_graph / kg_query   数据层与查询层（无 Gradio）
        ↑
    app.shared / app.components       共享上下文与组件工厂
        ↑
    app.handlers / app.specs          回调逻辑与页面规格（无布局代码）
        ↑
    app.page_*                        各自一个 Tab：摆控件 + 绑本页事件
        ↑
    app.build_ui()                    建 State、按显示顺序建页、连跨页事件

页面之间不互相 import，需要共享的东西一律走 AppCtx。
"""
import os
import sys

import gradio as gr

HERE = os.path.dirname(os.path.abspath(__file__))
KG_DIR = os.path.dirname(HERE)
for _p in (KG_DIR, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import kg_backend as K                                    # noqa: E402
from .shared import AppCtx, quad_info                     # noqa: E402
from . import handlers as H                               # noqa: E402
from . import page_search, page_detail, page_export       # noqa: E402
from . import page_topics, page_build                     # noqa: E402

TITLE_MD = """# CBDB 知识图谱 · 查询台
数据源：源库 `cbdb_20260926.sqlite3`（检索） + Owlready2 quadstore（详情，TBox v1.0）。
五个页面：**🔍 查询** / **📄 详情** / **📦 导出** / **①~⑨ 专题查询** / **⚙️ 构建**。"""


def build_ui():
    with gr.Blocks(title="CBDB 知识图谱查询台") as demo:
        gr.Markdown(TITLE_MD)

        ctx = AppCtx()
        ctx.db_state = gr.State(K.DEFAULT_DB)
        ctx.qstate = gr.State({"cond": None, "rows": []})

        with gr.Tabs() as tabs:
            ctx.tabs = tabs
            ctx.pages["search"] = page_search.build(ctx)
            ctx.pages["detail"] = page_detail.build(ctx)
            ctx.pages["export"] = page_export.build(ctx)
            ctx.pages["topics"] = page_topics.build(ctx)
            ctx.pages["build"] = page_build.build(ctx)

        _bind_cross_page(ctx)
        # 首屏刷新图谱列表 + 统计信息
        demo.load(ctx.pages["search"]["refresh"], outputs=[ctx.quad]).then(
            quad_info, inputs=[ctx.quad], outputs=[ctx.info_md])

    return demo


def _bind_cross_page(ctx):
    """所有跨页事件集中在这里（因为要同时引用多个页面的组件）。"""
    search, export = ctx.pages["search"], ctx.pages["export"]

    # ① 查询按钮：第 4 个输出是导出页的条件栏
    outputs = search["outputs"] + [export["cond_md"]]
    search["q_btn"].click(H.do_query, inputs=search["inputs"], outputs=outputs,
                          api_name="search_query")
    for b in search["submitters"]:
        b.submit(H.do_query, inputs=search["inputs"], outputs=outputs)

    # ② 结果表点一行 → 详情页载入
    H.bind_cross_page(ctx, search, ctx.pages["detail"])
    return ctx
