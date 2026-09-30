# NOTICE

## 项目

**cbdb_analysis —— CBDB SQLite 增强版（分析视图 + 知识图谱 + 查询台）**

Copyright (c) 2026 miyamaerei
https://github.com/miyamaerei/cbdb_analysis

本仓库整体采用 **CC BY-NC-SA 4.0**（知识共享 署名—非商业性使用—相同方式共享 4.0 国际）授权，
完整法律条款见 [`LICENSE`](./LICENSE)。

---

## 为何选用此许可证

本仓库的代码（脚本、查询台、文档）为原创作品，但其核心产出——分析视图定义（`View_*`）、
物化结果表（`LIFE_EVENT_RESOLVED`）、RDF/OWL 知识图谱（quadstore）——是对
「中国历代人物传记资料库」（China Biographical Database，CBDB）数据的**转换、重混与再表达**，
属于该数据的派生成果。

CBDB 数据本身以 CC BY-NC-SA 4.0 发布（见 <https://cbdb.fas.harvard.edu/cbdbapi> 与
<https://projects.iq.harvard.edu/cbdb>）。该授权中的**「相同方式共享」（ShareAlike）**条款要求：
基于原本素材的再创作，必须以相同授权条款散布。因此本仓库整体沿用 CC BY-NC-SA 4.0。

### 您可以自由地

- **共享** —— 以任何媒介或格式复制及散布本素材
- **改编** —— 重混、转换本素材，及依本素材建立新素材

### 惟须遵守以下条件

- **署名（BY）** —— 必须给予适当表彰、提供指向本授权条款的链接，并指明是否作了修改。
- **非商业性使用（NC）** —— 不得将本素材用于商业目的。
- **相同方式共享（SA）** —— 若您重混、转换或依本素材建立新素材，必须依相同授权条款散布您的贡献物。

> ⚠️ **因含「非商业性使用」限制，本仓库及其 CBDB 派生成果不可用于商业目的。**
> 如需商业使用，须另行取得 CBDB 项目方授权，并剥离本仓库中的 CBDB 派生部分。

本许可证不改变、也不能替代 CBDB 数据的原始授权条款；对本仓库中任何源自 CBDB 的数据与成果，
CBDB 的原始授权与引用要求始终适用并优先。

---

## 必须遵守的引用要求（CBDB 数据）

依据 CC BY-NC-SA 4.0 的**「署名」**条款，任何使用本仓库或其中 CBDB 派生数据的成果，
**均须规范引用 CBDB**。建议格式（日期请改为您实际使用的版本日期）：

**通用格式**

```
Harvard University, Academia Sinica, and Peking University, China Biographical
Database (CBDB) (April 24, 2018), https://projects.iq.harvard.edu/cbdb.
```

**BibTeX**

```bibtex
@misc{cbdb,
  title  = {{China} Biographical Database {(CBDB)}},
  url    = {https://projects.iq.harvard.edu/cbdb},
  author = {{Harvard University} and {Academia Sinica} and {Peking University}},
  year   = {2018}
}
```

**引用《用户指南》**

```
Fuller, Michael A. "The China Biographical Database User's Guide."
```

**引用中文版《用户指南》**

```
傅君勱. 中國歷代人物傳記資料庫用戶指南 (2017) [EB/OL].
https://projects.iq.harvard.edu/cbdb.
```

**引用本仓库**

若您同时使用了本仓库新增的分析视图、知识图谱或查询台，请一并注明来源：

```
miyamaerei. cbdb_analysis: CBDB SQLite 增强版（分析视图 + 知识图谱 + 查询台）,
https://github.com/miyamaerei/cbdb_analysis.
```

机器可读的引用元数据见 [`CITATION.cff`](./CITATION.cff)（GitHub 会据此显示
"Cite this repository" 按钮）。

---

## 第三方组件

| 组件 | 说明 | 授权 |
|---|---|---|
| CBDB 数据 | 由哈佛大学、中央研究院、北京大学合作维护；本仓库不包含任何数据文件 | CC BY-NC-SA 4.0 |
| `cbdb-project/cbdb_sqlite` | 本仓库的直接上游（下载与后处理脚本） | 未声明许可证 |
| Owlready2 / Gradio / Vue / Vite | 第三方依赖，各自遵循其原始许可 | 见各自项目 |

---

## 免责声明

本仓库为**第三方扩展项目**，与 CBDB 项目方（哈佛大学费正清中国研究中心、
中央研究院历史语言研究所、北京大学中国古代史研究中心）及上游仓库
`cbdb-project/cbdb_sqlite` **无隶属关系，亦未获其背书**。

仓库本身不包含任何数据库二进制文件（`.sqlite3` / `.zip` 等均已被 `.gitignore` 排除），
所有数据须由使用者自行从 CBDB 官方公开渠道下载。

本仓库按「现状」提供，不附带任何形式的明示或默示担保。
