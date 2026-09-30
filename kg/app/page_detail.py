# -*- coding: utf-8 -*-
"""📄 详情页：单人的全部 TBox v1.0 信息（读 Owlready2 quadstore）。"""
import gradio as gr

import kg_backend as K

from . import handlers as H
from .components import section_table

SECTIONS = ["kin", "assoc", "tenure", "entry", "addr", "status", "text", "source"]
SECTION_TITLES = {
    "kin": "亲属 KinshipAssertion", "assoc": "交遊 AssociationEvent",
    "tenure": "任职 OfficeTenure", "entry": "入仕 EntryRecord",
    "addr": "地址 AddressClaim", "status": "社会身份 StatusPeriod",
    "text": "著作 TextRoleLink", "source": "史料来源 sourceOf",
}
# 点一行可跳转下一人的分区（表里第 4 列是「对方ID」）
NAV_SECTIONS = ("kin", "assoc")


def build(ctx):
    # id="tab_detail"：查询页点结果行后要用 gr.Tabs(selected=...) 自动跳到这里
    with gr.Tab("📄 详情", id="tab_detail"):
        with gr.Row(elem_classes=["kg-bar"]):
            # Textbox 而非 Number：Number 的空值会被前端提交成 0（person/0 无意义）
            pid_nb = gr.Textbox(label="人物 c_personid", value="",
                                placeholder="如 30374（可先在「🔍 查询」点一行）", scale=3)
            load_btn = gr.Button("📄 载入详情", variant="primary", scale=1)
        basic_md = gr.Markdown("在上方填入 personid，或回到「🔍 查询」点一行结果。",
                               elem_classes=["kg-md"])
        stat_md = gr.Markdown("", elem_classes=["kg-md"])

        tables = {}
        for key in SECTIONS:
            with gr.Accordion(SECTION_TITLES[key], open=(key == "kin")):
                tables[key] = section_table(key)

    ctx.pid = pid_nb
    ctx.detail_out = [basic_md, stat_md] + [tables[k] for k in SECTIONS]

    # ---------------------------------------------------------- 本页事件
    load_btn.click(H.load_detail, inputs=[pid_nb, ctx.quad, ctx.db_state],
                   outputs=ctx.detail_out, api_name="detail_load")
    for key in NAV_SECTIONS:
        df = tables[key]
        df.select(H.pick_person, inputs=[df], outputs=[pid_nb])
        df.select(H.load_other_from_row, inputs=[df, ctx.quad, ctx.db_state],
                  outputs=ctx.detail_out)

    return {"pid": pid_nb, "tables": tables, "basic_md": basic_md, "stat_md": stat_md}
