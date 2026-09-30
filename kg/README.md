# CBDB 知识图谱（Owlready2 + RDF/OWL + Gradio 查询台）

在 CBDB 的 SQLite 关系库之上叠一层**语义层**：把 KIN / ASSOC / POSTING / ENTRY / BIOG_ADDR /
STATUS / BIOG_TEXT 七张表 hub 化成 RDF/OWL 断言，做成 quadstore，再配一台查询台做
亲缘、师承、同年、任官、学派这类**网络型**查询——这些用纯 SQL 写起来动辄十几层自连接。

本体设计见 [`TBOX_v1.0.md`](./TBOX_v1.0.md)（**已冻结**）；界面代码结构见 [`app/README.md`](./app/README.md)。

> 与 `web/` 查询台的分工：`web/` 面向**关系表横向检索**（24 个视图、按列自动生成条件），
> `kg/` 面向**图上的多跳遍历**（A 的师承链、同年进士、学派网络）。两者的数据底座是同一个源库。

---

## 0. 快速开始

```bash
# 依赖（仓库根目录）
pip install -r requirements.txt   # gradio + owlready2 + zhconv
# 端到端冒烟测试另需：pip install gradio_client

# 1) 构建知识图谱（默认明朝 c_dy=19），产物 kg/quadstore/cbdb_dy19.sqlite3 + 同名 .meta.json
python kg/etl_seed_ming.py --db cbdb_20260926.sqlite3 --dy 19

# 2) 启动查询台（13 个 Tab），打开 http://127.0.0.1:7860
python kg/app_gradio.py --port 7860
```

> ⚠️ **`python` 必须和装依赖的是同一个解释器。** 两者不一致时会报
> `ModuleNotFoundError: No module named 'gradio'`——包明明装了，只是没装在这个解释器里。
> 用虚拟环境时改成显式指定：
> ```bash
> <venv>/Scripts/python.exe kg/app_gradio.py --port 7860    # Windows
> <venv>/bin/python         kg/app_gradio.py --port 7860    # macOS / Linux
> ```
> 查当前解释器：`python -c "import sys; print(sys.executable)"`。
> `app_gradio.py` 已内置依赖自检，缺包时会直接打印当前解释器路径与解决办法。

源库（`cbdb_20260926.sqlite3`）需先按仓库根 [`README.md`](../README.md) §5.2 准备好。
**`kg/quadstore/` 与 `kg/exports/` 都被 `.gitignore` 排除**——图谱是本地构建产物，不入仓。

---

## 1. 三层数据

| 层 | 位置 | 用途 | 为什么 |
|---|---|---|---|
| ① 源库 SQLite | `cbdb_20260926.sqlite3` | 朝代清单、人物检索 | 这些字段有现成索引，`idx_kin_data_person` 等查询 1.7 秒内出结果，没必要走图 |
| ② quadstore | `kg/quadstore/cbdb_dy<N>.sqlite3` | 人物详情、Q1–Q9 专题 | 语义层，多跳关系靠它 |
| ③ 导出目录 | `kg/exports/<条件>_<日期>/` | 查询结果落盘（CSV/JSON + 条件留痕） | 让"这次结论是怎么跑出来的"可复现 |

**关键设计：检索走 SQL，详情走图。** 两条链路分离，是因为图检索（打开 owlready2 World）慢，
而 SQL 检索快；反过来单人全量详情（<0.1 秒）走图比拼十几条 SQL 干净得多。

---

## 2. 本体：TBox v1.0（已冻结）

实现见 [`tbox_cbdb.py`](./tbox_cbdb.py)，**冻结文档是 [`TBOX_v1.0.md`](./TBOX_v1.0.md)**——
任何修改必须先改冻结文档并升版本号，不允许直接改代码。

几处关键决策：

- **码表统一走 SKOS 风格**：`概念个体 + broader 自关联`，不建 OWL 类层级。
  CBDB 的码表本质是叙词表（如「進士」有多种细分），硬套类继承会失真。
- **断言 hub 化**：七张关系表各自变成一个「断言类」hub 节点，三要素 exactly 1：
  `KinshipAssertion` / `AssociationEvent` / `OfficeTenure` / `EntryRecord` /
  `AddressClaim` / `StatusPeriod` / `TextRoleLink`。
  这样「一次任官」能挂年份、地点、任命类型，而不会把属性硬塞到人身上。
- **推理等价类在 TBox 里定义**（无需 Java 推理机即可用 SPARQL/字典推导）：

  | 类 | 定义 |
  |---|---|
  | `Official` | `Person ⊓ Inverse(tenureHolder) some OfficeTenure` |
  | `JinshiHolder` | `Person ⊓ Inverse(entryPerson) some (EntryRecord ⊓ entryMode some JinshiModes)` |
  | `Female` / `Male` | `Person ⊓ isFemale value true / false` |
  | `MingPerson` | `Person ⊓ dynastyOf value dynasty/19` |

- **单值属性一律 `FunctionalProperty`**：源表每行即单值，省掉推理负担。

> ⚠️ 无 Java 环境时 HermiT / Pellet 跑不了，等价类归类只能改用 SPARQL / SQL 手工对账。
> 这也是「等价类写进 TBox 定义」而非依赖推理机的原因。

---

## 3. ETL：种子集构建

```bash
python kg/etl_seed_ming.py [--db PATH] [--out PATH] [--dy N] [--limit-persons N]
```

| 参数 | 说明 |
|---|---|
| `--db` | 源库路径，默认相对仓库根（`os.path.join(HERE, "..", "cbdb_20260926.sqlite3")`） |
| `--dy` | 朝代 `DYNASTIES.c_dy`：**19=明（默认）**、15=宋、6=唐、20=清、77=周、53=三國蜀 |
| `--out` | 默认 `quadstore/cbdb_dy{N}.sqlite3` |
| `--limit-persons` | 调试用，只加载前 N 个核心人物 |

**种子集 = `BIOG_MAIN.c_dy={--dy}` 的全部人物 + 1 度邻域**（亲属 / 交遊对端）。
以明朝为例：核心集 225,593 人，加邻域后图内 `Person` 共 229,567。

### ETL 铁律（R1–R8，改动前必读）

| 编号 | 规则 | 为什么 |
|---|---|---|
| R1 | 零值（`0` / `NULL`）不落图 | RDF 里空值是开销而非信息，写进去只会让图膨胀、查询变慢 |
| R2 | `MERGED_PERSON_DATA` 的 ID 归一（链式解析到根） | 否则同一个人会有两个节点，图直接裂开 |
| R3 | 断言 hub 化 + 直边派生 | 既保留"这次任官"的完整上下文，也能 `tenureHolder` 直接连人，兼顾两种查询 |
| R4 | 邻域人物用轻量节点 | 只带姓名等最少属性，否则图会因邻域爆炸 |
| R5 | 地址层级用 `ADDRESSES` 物化，不现场递归 | 现场解析行政隶属会反复扫表 |
| R6 | 码表全量加载 | 概念个体要能覆盖历史行政区划，不能只加载用到的 |
| R8 | 年份一律 `int` | 避免字符串比较把 `"1000"` 排在 `"999"` 前 |

### 产物与 `.meta.json` 侧车

ETL 结束后在同目录写一份同名 `.meta.json`，查询台靠它列出「已构建的图谱」：

```json
{
  "dy": 19, "dynasty": "明", "built_at": "2026-09-30 10:09:47",
  "seconds": 122.0, "size_mb": 587.5, "triples": 6640573,
  "counts": { "Person": 229567, "KinshipAssertion": 283144, "OfficeTenure": 117332, ... }
}
```

实测规模：

| 朝代 | `--dy` | 三元组 | 体积 | 耗时 |
|---|---:|---:|---:|---:|
| 明 | 19 | 6,640,573 | 587.5 MB | 122.0 s |
| 宋 | 15 | 3,336,558 | 294.8 MB | 54.9 s |
| 周 | 77 | 67,410 | 6.8 MB | 2.6 s |
| 三國蜀 | 53 | 26,191 | 3.4 MB | 2.1 s |

> 缺 `.meta.json` 的 quadstore 在应用里会显示为「未知朝代」。
> 明朝那份 meta 是**事后手工补写**的，所以没有「核心 / 邻域」拆分；
> 后来构建的（宋等）会由脚本自动写入 `Person(核心)` / `Person(邻域)` 两项。

---

## 4. 查询底座：GraphIndex（内存谓词子图）

[`kg_graph.py`](./kg_graph.py) 只做一件事：把 quadstore 里用到的谓词子图**一次性抽进内存**
（约 3.4 秒 / 292 万边），之后所有查询都是纯字典查找（毫秒级）。

**为什么不直接用 owlready2 的 SPARQL？** 它自带的解析器**不支持尖括号 IRI**（`<http://…>` 直接
ParsingError），不支持属性路径，且大数据量下很慢。与其绕，不如一次性建索引。

```python
from kg_graph import get_index
g = get_index("kg/quadstore/cbdb_dy19.sqlite3")   # 按路径缓存
g.E["hasKin"][storid]        # 对象属性：prop → 主语 → [宾语]
g.D["birthYear"][storid]     # 数据属性：prop → 主语 → 值
```

⚠️ **quadstore 里有两张表，别混**：`objs(c,s,p,o)` 存对象属性（`o` 是 storid）；
`datas(c,s,p,o,d)` 存数据属性——**字面量值在 `o` 列，`d` 列是数据类型 / 语言标签**
（中文标签的 `d = '@zh'`）。直接连库写 SQL 时最容易在这里搞错。

⚠️ **`rev(prop)` 是懒构建的反向索引**，返回 `o → [s]`：**key 是宾语侧的 storid**，
value 才是主语列表。例如 `belongsTo` 的 key 是父级 `Place`（不是断言 hub 节点），
所以 `rev("belongsTo")` 能拿来求行政区的**后代闭包**（见 `place_closure`），
但**不能**把 key 当成某条断言的 id 去查它的其它属性。

### 与 owlready2 的写锁共存

owlready2 的 `World` 会**长期持有 quadstore 的写事务**，导致 `kg_graph` 的只读连接报
`database is locked`。典型症状：先点「详情」再点专题页会失败。
`get_index()` 检测到 locked 时会先释放本进程的 World 缓存再重读。

---

## 5. 专题查询 Q1–Q9

实现全在 [`kg_query.py`](./kg_query.py)，**不依赖 Gradio，可单独自检**：

```bash
python -c "import kg_query"          # 只验证能否导入
```

统一调用契约：`qN_xxx(g: GraphIndex, ...) -> (headers, rows, md)`，
双表（图）返回 `(headers_nodes, nodes, headers_edges, edges, md)`，Q1 返回 `(md, flat_rows)`。

| 编号 | 函数 | 专题 | 备注 |
|---|---|---|---|
| Q1 | `q1_dossier` | 人物履历完整档案 | 基本信息 + 别名 + 亲属/地理/任职/著作/身份六段 |
| Q2 | `q2_kin` | 亲属关系（双向） | |
| Q3 | `q3_kinnet` | 亲属 / 关系网络（k 度） | 可选含交遊，**超 3000 节点截断** |
| Q4 | `q4_teacher` | 师承链 | 向上求师 / 向下授徒，可设深度 |
| Q5 | `q5_jinshi` | 同年进士 | 按年份查，或给某人反查 |
| Q6 | `q6_tenure` | 任职网络（官职链） | |
| Q7 | `q7_county` | 同里 / 籍贯 | 关键词 + 朝代，**简繁归一** |
| Q8 | `q8_book` | 著作来源 | 一本书记了哪些人 |
| Q9 | `q9_topic` | 学派 / 主题网络 | 概念节点 + 关联人物 |

> 加第 10 个查询：在 `kg_query.py` 加函数 → 在 `app/specs.py` 加一条 `QuerySpec`，
> 页面自动生成（详见 [`app/README.md`](./app/README.md)）。

**⚠️ 稀疏字段实测（明）**：`assocTopic` 25 条 / `assocGenre` 0 条 / `assocOccasion` 12 条。
所以 Q9 主题类查询必须走 `assocType` 的名称，别指望 topic/genre 字段有数据。

---

## 6. Gradio 查询台（13 个 Tab）

```bash
python kg/app_gradio.py [--port 7860] [--host 127.0.0.1] [--share] [--no-browser]
```

| Tab | 内容 |
|---|---|
| 🔍 查询 | 按姓名（简繁自动扩展）/ 朝代 / 生卒年区间 / 进士 / 官员检索，双击结果行跳详情 |
| 📄 详情 | 人物档案 8 个分区表（TBox 语义，如「曾任官职」节点带年份与任命类型） |
| 📦 导出 | 把当前查询条件与结果导出成 CSV / JSON |
| ① ～ ⑨ | 对应 Q1–Q9 的九个专题页（**一份渲染器 + 声明式 `QuerySpec` 驱动**） |
| ⚙️ 构建 | 界面上直接跑 ETL 构建新朝代图谱（流式显示进度） |

界面代码的分层架构、AppCtx 共享方式、以及 Gradio 6 的几个静默失败坑，
见 [`app/README.md`](./app/README.md)。

**CBDB 是繁体库**：搜「王阳明」0 命中，要搜「王守仁」或勾上「别名参与匹配」再搜「陽明」。
脚本已做 简→繁→原样 三写扩展（`zhconv`，未安装时退化为原样匹配），但**别名回退链**
（原名 → 别名 → 去姓氏 + 别名）仍需在检索时开启对应开关。

---

## 7. 验证

```bash
# 图谱验收：OWL 侧实例/三元组计数 vs 源库对账（必须在 ETL 结束后跑，否则 quadstore 被写锁占用）
python kg/kg_stats.py --quad kg/quadstore/cbdb_dy19.sqlite3
python kg/kg_stats.py --sample 王守仁           # 额外跑抽检查询

# 端到端冒烟：需先启动服务，跑一遍所有页面的关键链路，打印 PASS / FAIL
python kg/app_gradio.py --port 7860 --no-browser
python kg/smoke_test.py                         # 默认 127.0.0.1:7860 / pid 30374
python kg/smoke_test.py --pid 25403 --quad cbdb_dy53 --name 王安石
```

冒烟测试必须走 HTTP 而非手动点界面——手动测不出「浏览器实际提交值」（如空 Number 会变成 `0`）。
各页按钮都有**显式 `api_name`**（`Q2_run` / `detail_load` / `search_query` …），
自动编号的 `_run_1` 会随页面顺序漂移，不能用。

---

## 8. 导出目录

导出落在 `kg/exports/<条件slug>_<YYYYMMDD>/`（重名自动追加 `_2`、`_3`）：

```
kg/exports/①_完整档案_person30374_20260930/
  ├── 档案明细.csv        结果数据（utf-8-sig，Excel 直接打开不乱码）
  ├── 档案明细.json
  ├── conditions.json     复现所需的全部条件 + 导出时间 + 各表行数
  └── README.md           人类可读的条件摘要（结果为空时只有这一个文件）
```

`conditions.json` 里会记下当时的 quadstore 与源库路径，便于回溯。加 `with_detail=True`
还会附带 `details/` 子目录（每人一份详情，默认上限 50 人）。

> ⚠️ 导出目录**含本机绝对路径**，因此已被 `.gitignore` 排除，不会进仓。

---

## 9. 文件

```
kg/
  tbox_cbdb.py           TBox v1.0 的 Owlready2 实现（本体定义，冻结）
  TBOX_v1.0.md           本体设计冻结文档 ★改本体先改这里
  etl_seed_ming.py       种子集 ETL（默认明朝，--dy 可换朝代）
  kg_graph.py            quadstore → 内存谓词子图索引（GraphIndex）
  kg_query.py            Q1–Q9 专题查询实现（不依赖 Gradio，可单独自检）
  kg_backend.py          三层数据后端：检索 / 详情 / 导出 / 跑 ETL
  kg_stats.py            图谱验收：计数对账 + 抽检
  smoke_test.py          端到端冒烟测试（走 HTTP，需服务已启动）
  app_gradio.py          查询台入口（瘦，约 40 行）
  app/                   查询台 UI（分层结构见 app/README.md）
  quadstore/             图谱产物 ★gitignore
  exports/               导出产物 ★gitignore（含本机绝对路径）
```

## 10. 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| `ModuleNotFoundError: No module named 'gradio'` | **运行用的 python ≠ 装依赖的 python**。依赖装在 venv 里、`python` 却指向系统/基础解释器时必然如此。用 `<venv>/Scripts/python.exe` 显式运行，见 §0；`app_gradio.py` 也有依赖自检会提示 |
| 点「详情」后点专题页失败 | owlready2 World 持股写锁 → `kg_graph.get_index()` 会自动释放缓存重读；仍失败则重启应用 |
| 下拉里默认图谱不是明朝 | `quad_choices()` 按**三元组数降序**排（规模优先）。曾按构建时间倒序，导致刚建的「周」小图谱成默认值，查王守仁报「图谱中未找到」 |
| 各朝代图谱都没有这个人 | 详情页会依次去别的图谱探测（`quad_has_person`，毫秒级轻量探测，不开 World） |
| 搜简体字 0 命中 | CBDB 全库繁体。已做简繁扩展，但姓名还需走别名回退链 |
| 校验报 `database is locked` | `kg_stats.py` 要在 ETL 完全结束后跑，两者不能同时占用 quadstore |
| 界面文字/主题改不动 | Gradio 6 的 `theme` 只能放 `launch()`，不能放 `Blocks()`；`show_api` 参数已移除 |
