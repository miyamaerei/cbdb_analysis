# -*- coding: utf-8 -*-
"""查询台的布局与密度主题（自定义 CSS）。

设计依据与 web 端 `web/FILTER_UX.md` 同源——**问题不是「条件不够多」，而是
「条件占满了垂直空间，结果表只剩半屏」**。web 端当年把 24 个视图的几十张条件卡片
平铺在表格上方，结果表被顶出视口；本查询台早期版本是同一个病：查询页 4 行控件
（朝代/上限、姓名/拼音/性别、6 个年份、4 个复选框）+ 按钮 + 两段提示，
13 个 Tab 每个顶部还有一段 SPARQL 说明，表格 `max_height` 又是 Gradio 默认的
500px —— 一屏看得到的行数很有限。

三条落地手段（对应 FILTER_UX 第 3 节的「三区分离」）：

1. **工具栏恒定一行**：只留姓名 / 朝代 / 上限 / 查询，其余条件收进 `gr.Accordion`；
   已生效的条件用文字摘要回显在命中行上（等价于 web 的 chips）。
2. **结果表吃满剩余高度**：表头 `position: sticky`，高度用 `calc(100vh - N)` 而不是
   固定像素；横向滚动时 ID 与姓名列固定（`pinned_columns`）。
3. **密度压到信息型表格的水平**：字号 12.5px、单元格 padding 2px 8px、斑马纹 + hover，
   并提供「紧凑 / 舒适」两档（web 端是 `≣/≡` 按钮）。

⚠️ Gradio 6 把 `css` / `css_paths` / `head` 从 `Blocks()` 挪到了 `launch()`，
所以本模块的 CSS 由 `app_gradio.py` 在 `launch(css=...)` 注入；
另在 `build_ui()` 里同时用一段 `gr.HTML` 兜底（见 `app/__init__.py:inject_css`），
这样任何方式起服务都有样式。

选择器说明：Gradio 6 的 DOM 里结果表是 `.table-wrap > table`（表头行 `.tr-head`），
Tab 是 `.tab-header` / `.tab-container`，Markdown 是 `.wrap.prose`。
需要覆盖的地方一律带 `!important`：Dataframe 会把 `max_height` 写成行内样式，
而样式表里的 `!important` 正是唯一能压过行内普通声明的写法。
"""

# 大结果表（查询页 / 专题页）：吃满视口剩余高度。
#   `max()` 是给矮屏幕兜底——纯 calc 在 600px 高的窗口里会把表格压到只剩百来像素。
#   用 max-height 而不是固定 height：数据少时表格自然变矮，不留大片空白。
#   350px ≈ 标题 + Tab 头 + 图谱行 + 工具栏 + 命中行 + 折叠的条件区
BIG_DF = "calc(100vh - 350px)"
BIG_DF_CSS = f"max(280px, {BIG_DF})"
# 小结果表（详情页 8 个分区表，同时可能开多个）
SMALL_DF = "430px"


CSS = f"""
/* ============================================================
 * 1 · 全局密度：把垂直空间还给结果表
 * ============================================================ */
.gradio-container {{ max-width: 100% !important; padding: 6px 12px 10px !important; }}
.gradio-container .block {{ padding: 3px 5px !important; }}
.gradio-container .form, .gradio-container .gap {{ gap: 4px !important; }}

/* 标题压成一行（原来是 H1 + 两行说明） */
.kg-title .wrap {{ padding: 0 !important; }}
.kg-title h1 {{ font-size: 17px !important; margin: 0 8px 0 0 !important; display: inline; }}
.kg-title p {{ font-size: 11.5px !important; color: #6b7280 !important; margin: 0 !important; }}

/* Markdown 提示行（命中提示 / 图谱统计 / 分区说明） */
.kg-md .wrap {{ font-size: 12.5px !important; padding: 1px 4px !important; }}
.kg-md p {{ margin: 1px 0 !important; line-height: 1.45 !important; }}
.kg-md hr {{ margin: 4px 0 !important; }}

/* Tab 导航 */
.tab-header {{ margin-bottom: 4px !important; gap: 2px !important; }}
.tab-header button {{ padding: 4px 12px !important; font-size: 12.5px !important; }}
.tab-container .tab-content {{ padding-top: 2px !important; }}

/* ============================================================
 * 2 · 工具栏：恒定一行，不被条件撑高
 * ============================================================ */
.kg-bar {{ flex-wrap: nowrap !important; align-items: flex-end !important; gap: 6px !important; }}
.kg-bar > .block, .kg-bar .form > .block {{ padding: 0 !important; }}
.kg-bar label > span, .kg-cond label > span {{
    font-size: 11.5px !important; color: #6b7280 !important; margin-bottom: 1px !important;
}}
.kg-bar input, .kg-bar textarea {{
    height: 30px !important; min-height: 30px !important;
    font-size: 12.5px !important; padding: 2px 8px !important;
}}
.kg-bar button {{
    height: 30px !important; min-height: 30px !important; max-height: 30px !important;
    font-size: 12.5px !important; padding: 0 12px !important;
}}

/* ============================================================
 * 3 · 高级条件区（Accordion）
 * ============================================================ */
.kg-cond .block {{ padding: 1px 4px !important; }}
.kg-cond input, .kg-cond textarea {{
    height: 28px !important; min-height: 28px !important;
    font-size: 12px !important; padding: 1px 8px !important;
}}
.kg-cond label > span {{ font-size: 11.5px !important; }}
.kg-cond .label-wrap, .kg-cond > .label-wrap > span {{ font-size: 12.5px !important; }}
/* 折叠时只占一行，别留大块空白 */
.kg-cond .block.padded {{ padding: 4px 6px !important; }}

/* ============================================================
 * 4 · 结果表：表头吸顶 + 紧凑行高 + 斑马纹
 * ============================================================ */
.kg-df .table-wrap {{
    border: 1px solid #e4e8ef !important; border-radius: 6px !important;
    max-height: {BIG_DF_CSS} !important;
}}
.kg-df-sm .table-wrap {{ max-height: {SMALL_DF} !important; }}
.kg-df .table-wrap table, .kg-df-sm .table-wrap table {{ font-size: 12.5px !important; }}

.kg-df .table-wrap thead th, .kg-df-sm .table-wrap thead th {{
    position: sticky; top: 0; z-index: 4;
    background: #f1f4f9 !important; color: #344054 !important;
    padding: 4px 8px !important; font-size: 12px !important; font-weight: 600 !important;
    white-space: nowrap; border-bottom: 1px solid #d6dce6 !important;
}}
.kg-df .table-wrap tbody td, .kg-df-sm .table-wrap tbody td {{
    padding: 2px 8px !important; font-size: 12.5px !important; line-height: 1.4 !important;
    border-bottom: 1px solid #f0f2f6 !important; vertical-align: top;
}}
.kg-df .table-wrap tbody tr:nth-child(even),
.kg-df-sm .table-wrap tbody tr:nth-child(even) {{ background: #fafbfd; }}
.kg-df .table-wrap tbody tr:hover,
.kg-df-sm .table-wrap tbody tr:hover {{ background: #eef4ff; }}

/* 舒适档（web 端 ≣/≡ 按钮的等价物） */
.kg-df.kg-cozy .table-wrap thead th {{ padding: 8px 10px !important; font-size: 12.5px !important; }}
.kg-df.kg-cozy .table-wrap tbody td {{ padding: 7px 10px !important; font-size: 13px !important; }}
.kg-df-sm.kg-cozy .table-wrap thead th {{ padding: 7px 10px !important; }}
.kg-df-sm.kg-cozy .table-wrap tbody td {{ padding: 6px 9px !important; font-size: 13px !important; }}

/* 表格自带的前端过滤框（show_search） */
.kg-df .table-wrap ~ * input, .kg-df input[type="search"] {{
    font-size: 12px !important; height: 28px !important;
}}

/* ============================================================
 * 5 · 表格上方的「显示列 / 密度」小工具条
 * ============================================================ */
.kg-tools {{ flex-wrap: nowrap !important; align-items: center !important; gap: 8px !important; }}
.kg-tools .block {{ padding: 0 !important; }}
.kg-tools label > span {{ font-size: 11.5px !important; color: #6b7280 !important; }}
.kg-tools .wrap {{ max-height: 92px; overflow: auto; }}
"""
