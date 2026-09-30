# kg/app · Gradio 界面代码结构

入口：`python kg/app_gradio.py --port 7860`（瘦启动器，只解析参数 + launch）。

## 分层（依赖单向，无循环导入）

```
                    ┌─────────────────────────────────────────────┐
数据/查询层          │ kg_backend.py   源库检索 / quadstore / 导出  │
（不含 Gradio）      │ kg_graph.py     GraphIndex 谓词子图索引      │
                    │ kg_query.py     Q1–Q9 查询实现 ★单独可检查    │
                    └─────────────────────────────────────────────┘
                                        ↑
样式层               theme.py      布局/密度 CSS（唯一的样式来源）
                                        ↑
共享层               shared.py      AppCtx / Field / Sheet / 图谱工具
                    components.py  组件工厂（结果表、图谱行、导出区…）
                                        ↑
逻辑/规格层          handlers.py    查询·详情·导出·构建的回调（无布局）
（不含布局）         specs.py       ①~⑨ 九个专题页的声明式规格
                                        ↑
页面层               page_search / page_detail / page_export
                    page_topics / page_build      （各管一个 Tab）
                                        ↑
组装                 __init__.py    build_ui()：建 State → 建页 → 连跨页事件
```

## 文件职责

| 文件 | 行数 | 做什么 | 不做什么 |
|---|---:|---|---|
| `../app_gradio.py` | ~63 | 命令行参数、依赖自检、`launch(css=theme.CSS)` | 不建任何组件 |
| `__init__.py` | ~92 | 建 `AppCtx`/State、按 Tab 顺序调各页、**连跨页事件**、注入 CSS | 不写具体控件 |
| `theme.py` | ~137 | 布局/密度 CSS（工具栏单行、表头吸顶、紧凑与舒适两档） | 不含组件、不含逻辑 |
| `shared.py` | ~147 | `AppCtx`、`Field`/`Sheet` 声明类、图谱列表/统计/异常文案 | 不建组件 |
| `components.py` | ~117 | `result_table` / `quad_row` / `build_field` / `export_result` / `sparql_note` | 不绑事件 |
| `handlers.py` | ~280 | `do_query` / `load_detail` / `do_export` / `run_etl_ui` / `pick_row` / `apply_view` | 不含 `gr.*` 布局 |
| `specs.py` | ~245 | 9 个 `QuerySpec`：字段、表头、怎么调 `kg_query` | 不含 Gradio |
| `page_search.py` | ~111 | 🔍 查询页（并创建全局图谱下拉/朝代下拉） | — |
| `page_detail.py` | ~50 | 📄 详情页 8 个分区表 | — |
| `page_export.py` | ~32 | 📦 导出页 | — |
| `page_topics.py` | ~81 | ①~⑨ 九页的**通用渲染器**（遍历 SPECS 生成） | 不含具体查询逻辑 |
| `page_build.py` | ~33 | ⚙️ 构建页（跑 ETL 子进程） | — |

## 共享方式：AppCtx

页面之间**不互相 import**。所有跨页共享的东西挂在 `AppCtx` 上：

| 字段 | 谁创建 | 谁用 |
|---|---|---|
| `db_state` / `qstate` | `__init__.py` | 全部 |
| `quad`（图谱下拉） | 查询页 | 详情/导出/专题/构建 |
| `dy`（朝代下拉） | 查询页 | 查询条件 |
| `info_md`（统计栏） | 查询页 | 构建页完成后刷新 |
| `pid`（personid 输入框） | 详情页 | 查询页点行跳转 |
| `detail_out`（10 个输出） | 详情页 | 查询页点行后刷新 |

跨页事件只有三类，都写在 `__init__.py::_bind_cross_page()` 里：
1. 查询按钮 / 姓名框回车 / 排序·上限变化 → 第 4 个输出写「导出页」的条件栏；
2. 「显示列 / 行高」→ `handlers.apply_view`：用 `qstate` 里的完整结果即时重绘，**不查库**；
3. 结果表点一行 → 详情页 `pid` → `load_detail`。

## 改代码去哪儿改

| 想改什么 | 改哪个文件 |
|---|---|
| 查询逻辑（Q1–Q9 的取数/筛选） | `kg/kg_query.py` |
| 加第 10 个专题查询 | `kg/kg_query.py` 加函数 → `app/specs.py` 加一条 `QuerySpec`（页面自动生成） |
| 改某个专题页的输入项/表头 | `app/specs.py` 对应那一条 |
| 改所有表格的样式/交互 | `app/components.py::result_table` |
| **改整体布局 / 字号 / 行密度** | `app/theme.py`（CSS 唯一来源，见 `kg/README.md` §6.3） |
| 改检索 SQL / 导出格式 / ETL 命令 | `kg/kg_backend.py` |
| 改「显示列 / 排序」的列清单 | `kg/kg_backend.py` 的 `RESULT_*` / `ORDER_CHOICES` 常量 |
| 加一个新 Tab | 新建 `app/page_xxx.py`（照 `page_export.py` 抄）→ 在 `__init__.py` 注册 |

## 坑（改代码时别踩回去）

1. **刷新图谱下拉必须改服务端 choices**：Gradio 用 `Block.choices` 校验值，`gr.update()` 只改前端。
   所以 `refresh_quads()` 要拿到 Dropdown 本体（`components.refresh_handler(ctx)` 生成闭包）。
   否则新建图谱后选中它再点按钮会静默无反应。
2. **流式输出必须是具名生成器函数**：`run_etl_ui` 用 `yield from`；
   写成 `lambda` 的话 Gradio 判定不是 generator，会把生成器当返回值序列化 → 点击无反应且不报错。
3. **CSS 只能在 `launch()` 给**（Gradio 6 把 `css` / `css_paths` / `head` 从 `Blocks()` 移走了）。
   `__init__.py:inject_css()` 还会额外用 `gr.HTML` 注入一份，两边互为兜底。
4. **布尔入参要过 `handlers._bool()`**：界面传的是真 `bool`，但经 API 层（`gradio_client`）
   枚举型 Radio 会变成字符串，`bool("False")` 是 **True** —— 升序会变降序。
5. **结果表第 0 列必须是 `personid`**：`pick_row` 靠它取 id。所以 ID 与姓名被列为锁定列
   （`K.RESULT_LOCKED_COLS`），不参与「显示列」勾选、且恒排在最前。

## 附：quadstore 与 owlready2 的锁

owlready2 的 `World` 会长期持有 quadstore 的写事务，导致 `kg_graph` 的只读连接报
`database is locked`（表现：先点「详情」再点专题页会失败）。
`kg_graph.get_index()` 检测到 locked 时会先关闭本进程的 World 缓存再读。
