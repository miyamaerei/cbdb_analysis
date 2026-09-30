# -*- coding: utf-8 -*-
"""跨页面共享层：应用上下文 AppCtx、字段/表规格、图谱工具函数。

这里**不创建任何 Gradio 组件**，只定义页面之间要传递的东西：
  * AppCtx  —— 页面之间共享的 State / 组件引用（图谱下拉、personid、详情输出区…）
  * Field   —— 输入控件的**描述**（由 components.build_field 渲染成真实控件）
  * Sheet   —— 结果表的**描述**（名字 + 表头 + 是否显示在页面上）
  * 图谱相关纯函数（列表刷新、元信息、异常文案）
"""
import os
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

import gradio as gr

import kg_backend as K


# ============================================================ 应用上下文
@dataclass
class AppCtx:
    """页面之间共享的组件与状态。

    约定：每个页面的 build(ctx) 只负责本页 UI 与本页内部事件；
    需要给别人用的组件挂到 ctx 上，跨页连线统一在 app.build_ui() 里做。
    """
    db_state: Any = None          # gr.State：源库路径
    qstate: Any = None            # gr.State：最近一次查询 {"cond":..., "rows":...}
    quad: Any = None              # gr.Dropdown：当前知识图谱（查询页创建）
    dy: Any = None                # gr.Dropdown：朝代（查询页创建）
    info_md: Any = None           # gr.Markdown：图谱统计信息（查询页创建）
    tabs: Any = None              # gr.Tabs：用于点结果行后自动切页
    pid: Any = None               # 详情 personid 输入框（详情页创建，Textbox）
    detail_out: List[Any] = field(default_factory=list)   # 详情页全部输出组件
    pages: dict = field(default_factory=dict)             # 页名 -> 该页组件字典


# ============================================================ 控件/结果表规格
@dataclass
class Field:
    """输入控件的声明式描述（kind: number|text|radio|dropdown|checkbox）。"""
    kind: str
    label: str
    default: Any = None
    choices: Optional[List] = None
    placeholder: str = ""
    scale: int = 0
    default_fn: Optional[Callable] = None   # 惰性默认值（如「当前图谱的朝代」）

    @classmethod
    def number(cls, label, default=None, scale=0):
        return cls("number", label, default, scale=scale)

    @classmethod
    def text(cls, label, placeholder="", default="", scale=0, default_fn=None):
        return cls("text", label, default, placeholder=placeholder, scale=scale,
                   default_fn=default_fn)

    @classmethod
    def radio(cls, label, choices, default=None, scale=0):
        return cls("radio", label, default, choices=list(choices), scale=scale)

    @classmethod
    def dropdown(cls, label, choices, default=None, scale=0):
        return cls("dropdown", label, default, choices=list(choices), scale=scale)

    @classmethod
    def checkbox(cls, label, default=False, scale=0):
        return cls("checkbox", label, default, scale=scale)

    def resolve_default(self):
        return self.default_fn() if self.default_fn is not None else self.default


@dataclass
class Sheet:
    """结果表声明：show=False 表示只导出、不在页面上显示（如 Q1 的档案明细）。"""
    name: str
    headers: List[str]
    show: bool = True


# ============================================================ 图谱工具
def quad_meta(path):
    for i in K.quadstores():
        if i["path"] == path:
            return i
    return {}


def quad_dynasty(quad):
    return quad_meta(quad).get("dynasty") or ""


def sync_dynasty(quad):
    """切换图谱 → 联动朝代下拉。"""
    m = quad_meta(quad)
    if m.get("dy") is not None:
        return gr.update(value=m["dy"])
    return gr.update()


def refresh_quads(quad_dd=None):
    """刷新图谱下拉。

    ⚠️ Gradio 在**服务端**用 Block.choices 校验 Dropdown 的值（dropdown.preprocess），
    而 gr.update() 只改前端。所以构建完新图谱后必须同步改服务端 quad_dd.choices，
    否则选中新图谱再点任何按钮都会报 "Value ... is not in the list of choices"
    （表现为点击无反应）。
    """
    ch = K.quad_choices()
    val = ch[0][1] if ch else None
    if quad_dd is not None:
        quad_dd.choices = ch
    return gr.update(choices=ch, value=val)


def quad_info(quad):
    if not quad:
        return "尚未选择图谱。"
    m = quad_meta(quad)
    st = K.quad_stats(quad)
    if not st:
        return "图谱不存在。"
    rows = "　".join(f"`{k}` {v:,}" for k, v in st["classes"].items())
    return (f"**{m.get('dynasty', '?')}** · `{os.path.basename(quad)}` · "
            f"{st['size_mb']} MB · 总三元组 **{st['triples']:,}**\n\n{rows}")


def err_md(e, where="操作"):
    """统一的异常文案（页面回调里 try/except 后直接返回）。"""
    return (f"❌ {where}失败：{type(e).__name__}: {e}\n\n"
            f"```\n{traceback.format_exc()[-800:]}\n```")


def need_graph(quad):
    """专题页统一的「没选图谱」提示；返回 None 表示 OK。"""
    if not quad:
        return "⚠️ 请先在「🔍 查询」页顶部选择一个知识图谱。"
    return None


def need_pid(pid):
    if pid is None or pid == "":
        return "请填 personid。"
    return None
