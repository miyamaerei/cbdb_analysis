# CBDB SQLite · 增强版（分析视图 + 知识图谱 + 查询台）

> 本仓库在官方 [`cbdb-project/cbdb_sqlite`](https://github.com/cbdb-project/cbdb_sqlite) 基础上扩展，
> 新增了**分析视图**、**Owlready2 知识图谱**与**两套查询界面**（Gradio 桌面台 / Vue 网页台）。
> 底层的 CBDB 数据文件由公开渠道下载，仓库本身**不存放任何数据库二进制**。

---

## 0. 原项目地址（公开数据源）

本仓库的所有人物数据均来自 **中国历代人物传记资料库（China Biographical Database, CBDB）**，
由哈佛大学等机构维护。公开获取渠道如下：

| 项目 | 地址 | 说明 |
|---|---|---|
| CBDB 官网 | https://cbdb.hsites.harvard.edu/ | 数据结构、Codebook、索引年规则等权威文档 |
| SQLite 发布仓库（上游） | https://github.com/cbdb-project/cbdb_sqlite | 本仓库的直接上游；含下载与后处理脚本 |
| SQLite 数据集（HuggingFace） | https://huggingface.co/datasets/cbdb/cbdb-sqlite | **官方公开下载地址**：`latest.zip` 为当前版本，`history/` 为历史版本 |
| 版本元数据 | `latest.json`（本仓库根目录，亦见上游 `master/latest.json`） | 当前发布日期、文件名、`sha256` 校验值、HuggingFace 直链 |

> 简体中文使用指南见 [`USAGE.zh.md`](./USAGE.zh.md)；英文指南见 [`USAGE.md`](./USAGE.md)。

---

## 1. 本仓库新增了什么

| 类别 | 内容 | 来源脚本 |
|---|---|---|
| **分析视图（5 个）** | `View_KinshipGenealogyData` / `View_CountyPeopleData` / `View_TextAssociationData` / `View_PersonLifeTimeline` / `View_RelationEdges` | `scripts/create_custom_views.sh` |
| **物化结果表（1 个）** | `LIFE_EVENT_RESOLVED`（生平区间轴，300 万行级） | `scripts/life_order.py` |
| **辅助索引（12 个）** | 为上述视图的过滤列建索引（否则县城视图等会退化成全表扫描） | `scripts/create_custom_views.sh` |
| **知识图谱（Owlready2）** | TBox v1.0 本体 + 明朝种子集 quadstore（RDF/OWL 语义层） | `kg/tbox_cbdb.py` + `kg/etl_seed_ming.py` |
| **查询界面（2 套）** | Gradio 查询台（13 个 Tab）+ Vue 网页查询台 | `kg/app/` + `web/` |

> 上游 `cbdb-project/cbdb_sqlite` 自带的**外键约束、18 个便利视图、`ADDRESSES` 反规范化表**
> 本仓库一并沿用（见 §2.1），并新增上表的分析视图与知识图谱。

---

## 2. 新增的数据表 / 视图，以及它们是怎么生成的

> ⚠️ **重要**：这些视图与表都是**由脚本在本地数据库上即时生成**的，仓库不提交 `.sqlite3` 文件
> （见 `.gitignore`）。拿到数据库后，按 §5.2 跑一遍脚本即可全部重建。

### 2.1 沿用上游后处理（一键 Colab 或本地脚本）

| 产物 | 脚本 | 说明 |
|---|---|---|
| 外键约束 | `scripts/add_foreign_keys.py` | 从 GitHub 拉取 `foreign_keys_regen.csv`，按表重建并追加 `FOREIGN KEY`（幂等） |
| 18 个便利视图 | `scripts/create_views.sh` | 如 `View_PeopleData`、`View_EntryData`、`View_PostingOfficeData`、`View_BiogAddrData`、`View_AssociationData` 等，把多张码表 JOIN 成可读宽表 |
| `ADDRESSES` 表 | `scripts/create_addresses_table.py` | 按时间分段解析每个地址的行政隶属层级（县→府→路/省），保留数据缺口 |

### 2.2 本仓库新增的分析视图（`scripts/create_custom_views.sh`）

都是 `DROP VIEW IF EXISTS … CREATE VIEW …`，幂等、可重复跑：

| 视图 | 视角 | 关键设计 |
|---|---|---|
| `View_KinshipGenealogyData` | **族谱** | 每条亲属关系 + 双方生卒/朝代/郡望 + 世代差（`c_upstep - c_dwnstep`）+ 同姓判定 + 史料出处 |
| `View_CountyPeopleData` | **县城** | 只取县级政区（`xian`/`Xian`/`County`，大小写兼容），从 `ADDRESSES` 取上级府州路省链；**必须先有 `ADDRESSES(c_addr_id)` 索引** |
| `View_TextAssociationData` | **单本文献** | 一本书（`c_source`）里记录的全部关联：社会关系/亲属/入仕/任官/身份/地理/著作，共 7 路 `UNION ALL` |
| `View_PersonLifeTimeline` | **生平时间轴** | 把 12 张关系表摊成 14 阶段事件流，并标出每条事件的**时间精度**（`year`/`nianhao`/`sequence`/`anchor`/`dynasty`/`undated`） |
| `View_RelationEdges` | **属性图边表** | 把 CBDB 建成属性图（节点 P/A/O/I/T/S/E/N/C/Y），供递归 CTE 做 A→B→C 链式遍历 |

该脚本还会建立 **12 个辅助索引**（如 `ADDRESSES(c_addr_id)`、`KIN_DATA(c_personid)`、`ASSOC_DATA(c_source)` 等），
没有它们，县城视图的相关子查询会退化成「全表扫描 × 行数」（原本 17 分钟不出结果）。

### 2.3 本仓库新增的物化结果表（`scripts/life_order.py`）

CBDB 的时间轴极残缺（仅 9% 有确切生年、亲属/著作 0% 有年份）。`life_order.py` 把这些编译成
**时间约束网络（STP）**，做弧一致性传播，把每条记录从一个点或无穷区间收窄成有限区间，并给出拓扑序。

输出表 **`LIFE_EVENT_RESOLVED`** 含三根轴：

1. **区间轴** `lo` / `hi` —— 传播后的可能年份范围
2. **序轴** `order_rank` —— 纯先后顺序（不含任何年份）
3. **精度轴** `precision` —— `exact` / `propagated` / `interval` / `frame`（可信度分级）

```bash
python scripts/life_order.py --db cbdb_20260926.sqlite3 --all --write   # 全库物化（约 300 万行）
python scripts/life_order.py --db cbdb_20260926.sqlite3 --person 30374  # 单人看过效果
```

> 该表是 Web 查询台「区间年谱」甘特图的数据底座（详见 `web/README.md`）。

---

## 3. 新增的知识图谱（Owlready2 + RDF/OWL）

### 3.1 本体设计（TBox v1.0，已冻结）

设计文档：`kg/TBOX_v1.0.md`；本体实现：`kg/tbox_cbdb.py`（Owlready2）。
相对于研究报告的关键冻结决策（节选）：

- **码表统一走 SKOS 风格**：`概念个体 + conceptBroader` 自关联，不建 OWL 类层级（CBDB 码表本质是叙词表）。
- **推理等价类**（TBox 定义，无需 Java 推理机即可用 SPARQL/字典推导）：
  - `Official ≡ Person ⊓ Inverse(tenureHolder) some OfficeTenure`
  - `JinshiHolder ≡ Person ⊓ Inverse(entryPerson) some (EntryRecord ⊓ entryMode some JinshiModes)`
  - `Female ≡ Person ⊓ isFemale value true`，`Male ≡ Person ⊓ isFemale value false`
  - `MingPerson ≡ Person ⊓ dynastyOf value dynasty/19`
- **断言类**（hub 节点，三要素 exactly 1）：`KinshipAssertion` / `AssociationEvent` / `OfficeTenure` /
  `EntryRecord` / `AddressClaim` / `StatusPeriod` / `TextRoleLink`，分别来自 KIN/ASSOC/POSTING/ENTRY/BIOG_ADDR/STATUS/BIOG_TEXT 七张表。
- 单值属性一律 `FunctionalProperty`，源表每行即单值，省去推理负担。

> 无 Java 环境时 HermiT/Pellet 跑不了，等价类归类改为 SPARQL/SQL 手工对账（见 `kg/TBOX_v1.0.md`）。

### 3.2 ETL 种子集与 quadstore

- 种子集：**明朝** `c_dy = 19`（1368–1644），**225,593 人** + 1 度邻域（亲属/交遊对端）。
- 全程遵守 ETL 铁律（零值不落图、MERGED ID 归一、断言 hub 化 + 直边派生、邻域轻量人物、地址层级用 `ADDRESSES` 物化等）。
- 输出：Owlready2 **quadstore**，`kg/quadstore/cbdb_dy<N>.sqlite3`（如明朝 587MB / 664 万三元组），
  并写同名 `.meta.json`（朝代名 / 三元组数 / 各类计数），供应用列出已构建图谱。
- 可扩展其他朝代：`--dy 15`（宋）/ `6`（唐）/ `20`（清）等。

### 3.3 查询底座：内存谓词子图索引（`kg/kg_graph.py`）

owlready2 自带 SPARQL 解析器不支持尖括号 IRI、不支持属性路径、大数据量慢。
因此把需要的谓词子图一次性抽进内存（约 3.4s / 292 万边），之后所有查询都是**纯字典查找（毫秒级）**。
`GraphIndex` 按 quadstore 路径缓存，`get_index()` 检测到 `database is locked` 时会先释放本进程 World 缓存再读（规避 owlready2 长期持写事务的坑）。

### 3.4 专题查询 Q1–Q9（`kg/kg_query.py`）

实现研究文档 §9 的 9 条图谱查询，**不依赖 Gradio、可单独自检**（`python -c "import kg_query"`）：

| 编号 | 函数 | 专题 |
|---|---|---|
| Q1 | `q1_dossier` | 人物履历完整档案（基本信息 + 别名 + 亲属/地理/任职/著作/身份分段） |
| Q2 | `q2_kin` | 亲属关系（双向：出/入） |
| Q3 | `q3_kinnet` | 亲属 / 关系网络（k 度，可选含交遊，超 3000 节点截断） |
| Q4 | `q4_teacher` | 师承链（向上求师 / 向下授徒，可设深度） |
| Q5 | `q5_jinshi` | 同年进士（按年份或某人反查） |
| Q6 | `q6_tenure` | 任职网络（某人官职链） |
| Q7 | `q7_county` | 同里 / 籍贯（关键词 + 朝代，简繁归一） |
| Q8 | `q8_book` | 著作来源（一本书记录了哪些人） |
| Q9 | `q9_topic` | 主题 / 理学网络（概念节点 + 关联人物） |

### 3.5 如何构建知识图谱

```bash
# 构建明朝种子集（默认 --dy 19），产物写入 kg/quadstore/cbdb_dy19.sqlite3
python kg/etl_seed_ming.py --db cbdb_20260926.sqlite3 --dy 19
```

---

## 4. Python 查询页面的设计（`kg/app/`）

Gradio 查询台采用**单向依赖、无循环导入**的分层架构：

```
kg_backend / kg_graph / kg_query      数据层与查询层（无 Gradio）
        ↑
app.shared / app.components           共享上下文（AppCtx）与组件工厂
        ↑
app.handlers / app.specs              回调逻辑与「页面规格」（无布局代码）
        ↑
app.page_*                            每个文件一个 Tab：摆控件 + 绑本页事件
        ↑
app.build_ui()                        建 State → 按 Tab 顺序建页 → 连跨页事件
```

设计要点：

- **页面之间不互相 import**，需要共享的东西一律走 `AppCtx`（图谱 / 朝代 / 选中人物 / 详情输出 / 查询状态）。
- **9 个专题页用一份渲染器 + 声明式 `QuerySpec` 驱动**：在 `app/specs.py` 声明
  `QuerySpec(tab, fields, sheets, run, key)`，由 `app/page_topics.py` 遍历生成；
  新增查询 = 在 `kg_query.py` 加函数 + 在 `specs.py` 加一条，页面自动生成。
- **跨页事件集中管理**：结果表点一行 → 自动切到详情页；查询条件同步到导出页。
- 入口 `kg/app_gradio.py` 仅做「解析参数 → `build_ui()` → `launch()`」，约 42 行。

五个 Tab：**🔍 查询 / 📄 详情 / 📦 导出 / ①~⑨ 专题查询 / ⚙️ 构建**。

---

## 5. 如何运行与使用

### 5.1 环境依赖

- **Python** ≥ 3.10
  ```bash
  pip install gradio owlready2 zhconv
  # 端到端自测可选：pip install gradio_client
  ```
- **前端**（仅 Web 查询台需要，Gradio 台不需要）：Node.js + npm
  ```bash
  cd web/frontend && npm install && npm run build   # 产出 dist/，交给 server.py 托管
  ```
  > 依赖见 `web/frontend/package.json`（Vue 3 + Vite）。Windows 若缺原生二进制，见 `web/README.md` 的提示。
- **sqlite3 CLI**（运行 `create_views.sh` / `create_custom_views.sh` 需要）。

### 5.2 准备数据库与视图

```bash
# 1) 下载 CBDB SQLite（见 §0 的 HuggingFace 地址），解压到仓库根目录，文件名如 cbdb_20260926.sqlite3
# 2) 重建全部视图 / 表（外键 + 18 视图 + ADDRESSES + 5 分析视图 + 索引）
bash scripts/create_views.sh        cbdb_20260926.sqlite3
python scripts/add_foreign_keys.py  --db cbdb_20260926.sqlite3
python scripts/create_addresses_table.py --db cbdb_20260926.sqlite3
bash scripts/create_custom_views.sh cbdb_20260926.sqlite3
# 3)（可选）物化生平区间轴
python scripts/life_order.py --db cbdb_20260926.sqlite3 --all --write
```

> 所有脚本的 `--db` / 路径参数都**相对仓库根目录**，克隆到任意路径即可直接跑（已脱敏，无本机绝对路径）。

### 5.3 启动 Gradio 查询台（桌面式，13 个 Tab）

```bash
python kg/app_gradio.py --port 7860 --no-browser
# 打开 http://127.0.0.1:7860
```

功能：人物检索、详情档案、导出 CSV/JSON、Q1–Q9 专题查询、一键构建知识图谱。
支持按姓名（简繁自动扩展）/ 朝代 / 生卒年区间检索；双击结果行跳转详情。

### 5.4 启动 Web 查询台（Vue 3 网页，零后端依赖）

```bash
# 后端（Python 标准库，无第三方依赖，默认 8787）
python web/server.py --db cbdb_20260926.sqlite3 --port 8787
# 浏览器打开 http://127.0.0.1:8787/
```

- 两种模式：**人物年谱**（单人纵向：区间甘特年谱 / 关系网络 / 档案 / 预设查询 / SQL 沙盒）与**视图检索**（24 个数据集 × 9 组，元数据驱动的条件卡片 + 关联键下钻）。
- 查询条件的唯一来源是 `web/view_meta.json`（由 `web/build_view_meta.py` 剖析 24 个视图生成，改库/改分组后需重跑，约 45s）。
- 数据库以 `mode=ro` + `query_only=ON` 打开，SQL 沙盒另做关键字黑名单，只读安全。
- API 清单见 `web/README.md`。

### 5.5 构建知识图谱（见 §3.5）

```bash
python kg/etl_seed_ming.py --db cbdb_20260926.sqlite3 --dy 19
```

---

## 6. 目录结构速览

```
cbdb_sqlite/
├── README.md                本文件
├── LICENSE                  许可法律条款（CC BY-NC-SA 4.0）
├── NOTICE.md                版权声明 / CBDB 引用要求 / 免责声明
├── CITATION.cff             机器可读引用元数据（GitHub「Cite this repository」）
├── latest.json              版本元数据（发布日期 / 文件名 / sha256 / HF 直链）
├── scripts/                 下载与后处理脚本（外键 / 18 视图 / ADDRESSES / 5 分析视图 / 区间轴 / 体检）
├── kg/                      知识图谱
│   ├── tbox_cbdb.py         TBox v1.0 本体（Owlready2）
│   ├── etl_seed_ming.py     种子集 ETL（默认明朝）
│   ├── kg_graph.py          quadstore → 内存谓词子图索引（GraphIndex）
│   ├── kg_query.py          Q1–Q9 专题查询实现
│   ├── kg_backend.py        检索 / 详情 / 导出 / 跑 ETL 的后端
│   ├── kg_stats.py          图谱验收脚本
│   ├── app_gradio.py         Gradio 查询台入口（瘦）
│   ├── TBOX_v1.0.md         本体设计冻结文档
│   └── app/                 查询台 UI（shared / components / handlers / specs / page_*）
├── web/                     网页查询台
│   ├── server.py           只读 API + 静态托管（Python 标准库）
│   ├── build_view_meta.py  剖析视图 → view_meta.json
│   ├── view_meta.json       生成物（约 280KB）
│   └── frontend/           Vue 3 + Vite 源码（src/ + dist/）
├── CBDB_SQLite_使用报告.md   使用报告（视图/年谱/查询设计详解）
├── CBDB_知识图谱本体设计研究.md  知识图谱本体设计研究报告
└── 表分类速查.md            码表分类速查
```

---

## 7. 注意事项

- **数据库文件不入仓**：`cbdb_*.sqlite3` / `*.zip` / `kg/quadstore/` / `kg/exports/` / `web/frontend/node_modules/` 等
  已被 `.gitignore` 忽略（合计约 2.7 GB 生成产物）。克隆后请按 §5.2 自行下载与重建。
- **数据库链接已脱敏**：源码中数据库路径一律相对仓库根目录，不写死本机绝对路径。
- **字符集**：CBDB 是繁体库（如「餘姚」非「余姚」、「陽明」非「王陽明」），检索时脚本会自动做简繁扩展。
- 历史版本数据集：https://huggingface.co/datasets/cbdb/cbdb-sqlite/tree/main/history

---

## 8. 许可与引用

### 8.1 许可证

本仓库整体采用 **CC BY-NC-SA 4.0**（知识共享 署名—非商业性使用—相同方式共享 4.0 国际），
完整法律条款见 [`LICENSE`](./LICENSE)；**项目版权声明、CBDB 引用要求与免责声明**另见
[`NOTICE.md`](./NOTICE.md)（§8.2 为其中的摘要）。

之所以不是常见的 MIT/Apache，是因为本仓库的核心产出——分析视图（`View_*`）、
物化表 `LIFE_EVENT_RESOLVED`、知识图谱 quadstore——是对 CBDB 数据的**转换、重混与再表达**，
属于派生成果。CBDB 数据本身以 CC BY-NC-SA 4.0 发布，其 **「相同方式共享」（ShareAlike）**
条款要求派生物必须以相同条款散布，因此本仓库整体沿用该许可。

> ⚠️ **因含「非商业性使用」限制，本仓库及其中 CBDB 派生成果不可用于商业目的。**
> 如需商业使用，须另行取得 CBDB 项目方授权，并剥离本仓库中的 CBDB 派生部分。

### 8.2 必须遵守的 CBDB 引用要求

依据 CC BY-NC-SA 4.0 的「署名」条款，任何使用本仓库或其中 CBDB 派生数据的成果，
**均须规范引用 CBDB**。建议格式（日期请改为您实际使用的版本日期）：

```
Harvard University, Academia Sinica, and Peking University, China Biographical
Database (CBDB) (April 24, 2018), https://projects.iq.harvard.edu/cbdb.
```

BibTeX：

```bibtex
@misc{cbdb,
  title  = {{China} Biographical Database {(CBDB)}},
  url    = {https://projects.iq.harvard.edu/cbdb},
  author = {{Harvard University} and {Academia Sinica} and {Peking University}},
  year   = {2018}
}
```

引用《用户指南》：`Fuller, Michael A. "The China Biographical Database User's Guide."`
引用中文版《用户指南》：`傅君勱. 中國歷代人物傳記資料庫用戶指南 (2017) [EB/OL].`

若同时使用了本仓库新增的视图 / 知识图谱 / 查询台，请一并注明来源：

```
miyamaerei. cbdb_analysis: CBDB SQLite 增强版（分析视图 + 知识图谱 + 查询台）,
https://github.com/miyamaerei/cbdb_analysis.
```

机器可读的引用元数据见 [`CITATION.cff`](./CITATION.cff)（GitHub 会据此显示
"Cite this repository" 按钮）。

### 8.3 免责声明

本仓库为**第三方扩展项目**，与 CBDB 项目方（哈佛大学费正清中国研究中心、
中央研究院历史语言研究所、北京大学中国古代史研究中心）及上游仓库
`cbdb-project/cbdb_sqlite` **无隶属关系，亦未获其背书**。
仓库不包含任何数据库二进制文件，所有数据须由使用者自行从官方渠道下载。
本仓库按「现状」提供，不附带任何形式的明示或默示担保。
