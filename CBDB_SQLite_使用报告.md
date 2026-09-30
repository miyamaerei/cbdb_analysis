# CBDB SQLite 数据库：表结构与视图使用报告

> 基于 `cbdb_20260926.sqlite3`（生成于 2026-09-26，人物 662,152 条）
> 79 张表 · 23 个视图（官方 18 个 + 本项目新增 5 个）· 89 个索引 · 174 个外键约束 · `integrity_check = ok`
> 报告日期：2026-09-27

---

## 一、先回答你的问题：网上有没有现成资料？

**有，而且官方资料相当完整。** 但存在一个明确的缺口，这份报告就是来补它的。

### 1.1 现成的官方资料清单

| 资料 | 链接 | 内容 |
|---|---|---|
| **Structure of the CBDB**（官方逐表说明，英文） | https://cbdb.hsites.harvard.edu/structure-cbdb | 按「实体 / 关系 / 代码表」三层讲 CBDB 的设计，逐个说明 BIOG_MAIN、ADDR_CODES、OFFICE_CODES、KINSHIP_CODES、ASSOC_CODES、STATUS_CODES、TEXT_CODES 等表的作用和字段 |
| **CBDB Codebook 逐表逐欄位介紹** | https://docs.qq.com/sheet/DYkJGbVRBdUhUcHhO | 官方逐表逐字段的对照表（在线表格） |
| **CBDB User's Guide 中文版** (20250521) | https://chinesecbdb.hsites.harvard.edu/sites/g/files/omnuum3961/files/2026-07/CBDB%20Users%20Guide%20CH%2020250521.pdf | 中文用户指南 |
| **CBDB User's Guide 英文版** (20260413) | https://chinesecbdb.hsites.harvard.edu/sites/g/files/omnuum3961/files/2026-06/CBDB%20Users%20Guide%2020260413.pdf | 英文用户指南 |
| **指數年計算規則**（xlsx） | https://cbdb.hsites.harvard.edu/sites/g/files/omnuum3101/files/cbdb/files/20200603_rules_for_index_years_20230911.xlsx | 26 条 index year 推导规则 |
| **2013 唐学会 Workshop 讲义**（Michael Fuller） | https://cbdb.hsites.harvard.edu/file_url/182 | 逐表讲解 + 带查询示例，很实用 |
| **上海图书馆 CBDB 开发简介**（中文 PDF） | https://opendata.library.sh.cn/2020/download/docs/18/CBDB/ | 中文概览，含表用途对照 |
| 第三方中文博客 | CSDN「中国历史人物传记数据库 CBDB 若干表简介」 | 中文速查，但基于旧版本 |

### 1.2 缺口在哪

官方文档是在 **Access / MDB 时代**写的，大量篇幅讲的是 `ZZZ_*` 反规范化表（`ZZZ_BIOG_MAIN`、`ZZZ_BELONGS_TO` 等）。而本仓库 README 明确说：

> *The ZZZ releases are now deprecated in favor of views.*

也就是说，**官方那套 ZZZ 表说明已经对不上现在这份 SQLite 了**。而取代 ZZZ 的 18 个视图（`View_PeopleData`、`View_EntryData` …）——**没有任何官方文档逐个讲它们的字段和用法**，`create_views.sh` 里唯一的验证只有一句 `COUNT(*)`。

**所以本报告的做法是**：
- 表（79 张）→ 以官方文档为准，用本地 schema 逐条核对、补全真实行数字段
- 视图（18 个）→ 官方没有，我从 `create_views.sh` 源码 + 实际列结构**逐列整理出来**，并配可运行的示例查询

---

## 二、数据模型总览

CBDB 是标准的三层关系模型。理解这三层，79 张表就不会迷路：

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│  实体主表    │    │   关系表      │    │  代码/查找表  │
│ (Entity)    │◄───┤ (Relation)   ├───►│  (Codes)    │
│             │    │              │    │             │
│ BIOG_MAIN   │    │ KIN_DATA     │    │ KINSHIP_    │
│ ADDR_CODES  │    │ ASSOC_DATA   │    │   CODES     │
│ OFFICE_CODES│    │ ENTRY_DATA   │    │ ENTRY_CODES │
│ TEXT_CODES  │    │ POSTED_TO_*  │    │ DYNASTIES   │
│ ...         │    │ BIOG_ADDR_*  │    │ NIAN_HAO    │
└─────────────┘    └──────────────┘    └─────────────┘
   一条 = 一个实体     一条 = 一次关系       一条 = 一个编码含义
   662,152 人         562,953 条亲属         488 种亲属称谓
```

**10 个核心实体**：人物 People、地址 Places(Addresses)、官职 Offices、亲属 Kinship、社会关系 Associations、社会身份 Status、入仕途径 Entry、社会机构 Social Institutions、文本 Texts、族属 Ethnicity。

**一切以 `c_personid` 为中心**。绝大多数分析都是「从 BIOG_MAIN 拿到 personid → 去各关系表扇出 → 回代码表翻译编码」。

### 2.1 五个必须先懂的建模约定

**① 编码 vs 文本**
原始表里存的全是编码（`c_dy=15`、`c_ethnicity_code`…），要 JOIN 代码表才能看懂。这就是视图存在的意义——视图帮你把 JOIN 做好了。

**② 时间：公历年 + 年号 + range 三件套**
史料常只有「生於開元間」这类模糊信息。CBDB 用三列联合表达：

| 列 | 含义 |
|---|---|
| `c_firstyear` / `c_birthyear` | 公历年份（可能为空） |
| `c_by_nh_code` / `c_fy_nh_code` | 年号 ID → `NIAN_HAO` |
| `c_by_range` / `c_fy_range` | 精度 → `YEAR_RANGE_CODES` |

`YEAR_RANGE_CODES` 只有 6 个值：

| code | 英文 | 中文 |
|---|---|---|
| -1 | before | 之前 |
| 0 | during | 之間 |
| 1 | after | 之後 |
| 2 | around | 約 |
| 300 | 960-1082 | 元豐五年前 |
| 301 | 1082-1279 | 元豐五年後 |

**统计时不要只筛 `c_firstyear`，否则会漏掉只有年号的记录。**

**③ 索引年 `c_index_year`**
为把人物摆到时间轴上而人为设定的单一年份，定义为「出生年或出生年的最佳估计」。推导规则见官方 xlsx。作图、分期统计都用它。

**④ 地址是「行政管辖权的实例」，不是地名**
同一地名在不同朝代是**不同的 `c_addr_id`**。比如「吳縣」在库里有 1368-1643（明·蘇州府）和 1949-2005（中華人民共和國·江蘇省）两条。做跨朝代空间分析时必须带上年份区间。

**⑤ 一次任职（posting）拆成三张表**
因为一次任命可能含多个官职、管辖多个地方：

```
POSTING_DATA (591,652)  ← 一次任职事件，给 c_posting_id
   ├─ POSTED_TO_OFFICE_DATA (591,683)  ← 这次任职命了什么官
   └─ POSTED_TO_ADDR_DATA  (465,390)  ← 官对应的治所在哪
```

---

## 三、79 张表逐一说明

格式：`表名` (行数) — 用途 ｜ 关键字段

### A. 人物（6 张）

| 表 | 行数 | 说明 |
|---|---|---|
| **BIOG_MAIN** | 662,152 | **人物主表，一切分析的起点。** 每人一行。关键列：`c_personid`(PK)、`c_name_chn`/`c_name`(中/拼音名)、`c_surname_chn`/`c_mingzi_chn`(拆分的姓/名)、`c_female`(1=女)、`c_index_year`、`c_birthyear`/`c_deathyear`、`c_death_age`、`c_dy`(朝代)、`c_index_addr_id`(籍贯/索引地)、`c_ethnicity_code`、`c_choronym_code`(郡望)、`c_household_status_code`(户籍状况)、`c_fl_earliest_year`/`c_fl_latest_year`(在世活动区间) |
| **ALTNAME_DATA** | 208,878 | 人物的其他称谓。一人多条。`c_alt_name_type_code` → `ALTNAME_CODES` |
| **ALTNAME_CODES** | 21 | 称谓类型：字(4)、室名別號(5)、諡號(6)、行第(7)、封爵(8)、小名(9)、法號(19)、道號(20)… |
| **BIOG_SOURCE_DATA** | 1,254,352 | **人物↔史料来源**。每行=某人的某条传记出自哪本书第几页。`c_main_source`(1=主要来源)、`c_self_bio`(1=自传)。做史料溯源、可信度加权用 |
| **BIOG_TEXT_DATA** | 53,354 | 人物在文本中的角色（撰著者/編者/校對者…）。`c_role_id` → `TEXT_ROLE_CODES` |
| **MERGED_PERSON_DATA** | 5,994 | **重复人物合并记录**。`c_merged_from_personid` 已被并入 `c_personid`。**做 JOIN 前务必先过一遍这张表做 ID 归一**，否则同一个人会被算两次 |

### B. 地理/地址（8 张）

| 表 | 行数 | 说明 |
|---|---|---|
| **ADDR_CODES** | 30,160 | **地址主表**。一个 `c_addr_id` = 某朝代某行政单位的一个实例。含 `c_name_chn`、`c_admin_type`(州/县/府…)、`x_coord`/`y_coord`(治所经纬度，做地图用)、`c_firstyear`/`c_lastyear`(该建制起止年) |
| **ADDR_BELONGS_DATA** | 37,180 | **行政隶属关系的原始表**：`c_addr_id` 在某年份区间隶属于 `c_belongs_to`。多对多、带时间，直接查很痛苦 |
| **ADDRESSES** | 64,347 | ⭐ **上表的展开版**（由 `create_addresses_table.py` 生成）。把层级拉平成 `belongs1..belongs5` 五级 + 对应的时间区间，保留数据空缺。**做层级归属分析直接用它**，别去啃 `ADDR_BELONGS_DATA` |
| **ADMIN_CAT_CODES** | 213 | 行政单位类别（安撫司/群島/堡/八旗…） |
| **ADMIN_CAT_TYPES** | 0 | 类别分组（**当前为空表**） |
| **ADMIN_CAT_CODE_TYPE_REL** | 0 | 类别↔分组关联（**当前为空表**） |
| **BIOG_ADDR_DATA** | 461,830 | **人物↔地址关系表**。`c_addr_type` → `BIOG_ADDR_CODES` 决定这条是什么关系 |
| **BIOG_ADDR_CODES** | 22 | 地址关系类型（**重要**）：1=籍貫(基本地址)、2=遷住地、5=祖籍、6=落籍(實際居住地)、7=本貫、8=出生地、9=葬地、10=死所、12=遊歷或曾經到過、15=避兵之地、17=流放之地、19=僑居、21=在某地有田土 |

### C. 官职与任职（11 张）

| 表 | 行数 | 说明 |
|---|---|---|
| **OFFICE_CODES** | 34,176 | **官职字典**。`c_office_id`(PK)、`c_office_chn`(中文官名)、`c_office_pinyin`、`c_office_trans`(英译)、`c_dy` |
| **OFFICE_TYPE_TREE** | 2,742 | 官职分类树（朝代→门类→细目），自引用 `c_parent_id` |
| **OFFICE_CODE_TYPE_REL** | 43,797 | 官职↔分类树的多对多关联 |
| **OFFICE_CATEGORIES** | 15 | 官制范畴：階官(1)、差遣(2)、職事官(6)、散官(7)、爵(9)、寄祿官(11)、祠祿官(12)…（依 Kracke 宋代官制研究） |
| **POSTING_DATA** | 591,652 | **任职事件表**，只发号：`c_posting_id`(PK) + `c_personid` |
| **POSTED_TO_OFFICE_DATA** | 591,683 | ⭐ **任职的核心数据表**。官名+任期+任命性质。`c_firstyear`/`c_lastyear`、`c_appt_code`(任命类型)、`c_assume_office_code`(是否赴任)、`c_office_category_id`、`c_sequence`(年份不明时用顺序代替) |
| **POSTED_TO_ADDR_DATA** | 465,390 | 这次任职的治所在哪（`c_posting_id`+`c_office_id`+`c_addr_id`） |
| **APPOINTMENT_CODES** | 116 | 任命类型明细 |
| **APPOINTMENT_TYPES** | 13 | 任命大类：授任(01)、署理(02)、特授(03)、榮譽虛銜(04)、擢升(06)、封(07)、試任(08)、蔭(09)、兼(10)、調(12)、貶(13) |
| **APPOINTMENT_CODE_TYPE_REL** | 109 | 明细↔大类关联 |
| **ASSUME_OFFICE_CODES** | 6 | **是否赴任**（很实用）：0=未詳、1=赴任、2=辭不就、3=未赴任而卒、4=未赴任而改命、5=未赴任 |

### D. 亲属关系（5 张）

| 表 | 行数 | 说明 |
|---|---|---|
| **KIN_DATA** | 562,953 | ⭐ **亲属关系表**。`c_personid` 的 `c_kin_code` 是 `c_kin_id`。语义是「A 把 B 当作某亲属」。**注意：关系是单向存储的**，做家族网络要双向展开 |
| **KINSHIP_CODES** | 488 | 亲属称谓字典。精髓在四个度量列：`c_upstep`(上几代)、`c_dwnstep`(下几代)、`c_colstep`(旁系)、`c_marstep`(姻亲)。**用这四个值就能把 488 种称谓归约成可计算的亲属距离**，不用逐个硬编码 |
| **KIN_MOURNING** | 159 | 服丧关系（五服制度） |
| **KIN_MOURNING_STEPS** | 159 | 服丧等级细目 |
| **KINREL_REDUCTION** | 8 | 亲属关系统计归约规则 |

### E. 社会关系（非亲属，7 张）

| 表 | 行数 | 说明 |
|---|---|---|
| **ASSOC_DATA** | 190,064 | ⭐ **社会关系表，42 列，做社会网络分析的核心**。`c_personid` 与 `c_assoc_id` 之间是 `c_assoc_code` 关系。还记录了：通过哪个亲属建立(`c_kin_id`/`c_kin_code`)、关系发生地(`c_addr_id`)、场合(`c_occasion_code`)、文体(`c_litgenre_code`)、学术主题(`c_topic_code`)、所在机构(`c_inst_code`)、谁主张的(`c_assoc_claimer_id`)、时间(`c_assoc_first_year`) |
| **ASSOC_CODES** | 498 | 关系类型字典。**关系成对生成**（A 是 B 的学生 ⇄ B 是 A 的老师） |
| **ASSOC_TYPES** | 45 | 关系大类 |
| **ASSOC_CODE_TYPE_REL** | 463 | 明细↔大类关联 |
| **OCCASION_CODES** | 10 | 建立关系的场合 |
| **LITERARYGENRE_CODES** | 12 | 文体/体裁 |
| **SCHOLARLYTOPIC_CODES** | 32 | 学术主题（做思想史、学派网络用） |

### F. 入仕途径（5 张）

| 表 | 行数 | 说明 |
|---|---|---|
| **ENTRY_DATA** | 265,037 | ⭐ **入仕记录**。`c_entry_code`(什么途径)、`c_year`(年份)、`c_exam_rank`(名次)、`c_exam_field`(科目)、`c_attempt_count`(考了几次)、`c_parental_status_code`(父母存殁)、`c_age`。**科举研究的主战场** |
| **ENTRY_CODES** | 273 | 入仕方式明细（進士類、舉人科、恩蔭、軍功補授…） |
| **ENTRY_TYPES** | 29 | 入仕大类，带层级 `c_entry_type_parent_id`：宮廷門(01)、血親門(02)、姻親門(03)、**科舉門(04)**、學校門(05)、恩蔭門(06)、徵召門(07)、薦舉門(08)、軍功補授門(09)、進納門(12)… |
| **ENTRY_CODE_TYPE_REL** | 284 | 明细↔大类关联 |
| **PARENTAL_STATUS_CODES** | 7 | 父母存殁状况（具慶/嚴侍/慈侍/永感…） |

### G. 社会身份（4 张）

| 表 | 行数 | 说明 |
|---|---|---|
| **STATUS_DATA** | 73,571 | 人物因何闻名。`c_status_code` + 时间区间 |
| **STATUS_CODES** | 285 | 身份明细（書法家、畫家、僧侶、理學家…） |
| **STATUS_TYPES** | 14 | 身份大类：事業(01)、學術(02)、理學(0201)、武功(03)、宗社(04)、藝術(05)、宗教(06)、時事(07)、布衣事(08)、政治(09)、愛好(10)、文章(11)、列女(12) |
| **STATUS_CODE_TYPE_REL** | 285 | 明细↔大类关联 |

### H. 社会机构（9 张）

| 表 | 行数 | 说明 |
|---|---|---|
| **SOCIAL_INSTITUTION_CODES** | 4,012 | 机构实例（`c_inst_code` + `c_inst_name_code` 联合 PK）。含起止年、朝代、first/last known year |
| **SOCIAL_INSTITUTION_NAME_CODES** | 2,603 | 机构名称字典（**机构名会变，但 inst_code 不变**） |
| **SOCIAL_INSTITUTION_TYPES** | 7 | 机构类型：書院(1)、佛寺(2)、道觀(3)、詩社文社(4)、太廟(5)、祠(6) |
| **SOCIAL_INSTITUTION_ADDR** | 3,859 | 机构所在地，可带比行政单位更精确的 `inst_xcoord`/`inst_ycoord` |
| **SOCIAL_INSTITUTION_ADDR_TYPES** | 2 | 地址类型：指數地址(1) |
| **SOCIAL_INSTITUTION_ALTNAME_CODES** | 1 | 机构别名类型（几乎空） |
| **SOCIAL_INSTITUTION_ALTNAME_DATA** | 0 | 机构别名（**空表**） |
| **BIOG_INST_DATA** | 571 | 人物在机构中的角色（`c_bi_role_code`）。**数据量很小，别指望用它做大规模分析** |
| **BIOG_INST_CODES** | 26 | 机构内角色字典 |

### I. 文本与书籍（9 张）

| 表 | 行数 | 说明 |
|---|---|---|
| **TEXT_CODES** | 62,378 | ⭐ **文本主表**，同时也是「史料来源」字典。`c_textid`(PK)、`c_title_chn`/`c_title`、`c_text_year`、`c_bibl_cat_code`(分类)、`c_extant`(存佚)、`c_url_api`/`c_url_homepage`(外链) |
| **TEXT_INSTANCE_DATA** | 9,817 | 版本/刻本信息（`c_text_edition_id`、`c_text_instance_id`） |
| **TEXT_ROLE_CODES** | 12 | 人物在文本中的角色：撰著者(1)、編輯者(2)、編纂者(3)、出版者(4)、捐助者(5)、翻譯者(7)、註疏者(8)、註釋者(9)、校對者(10) |
| **TEXT_BIBLCAT_CODES** | 144 | 书目分类 |
| **TEXT_BIBLCAT_TYPES** | 51 | 分类大类，带层级：古書原文(01) → 經部(01101) → 易類/尚書類/詩經類… |
| **TEXT_BIBLCAT_CODE_TYPE_REL** | 144 | 分类↔大类关联 |
| **TEXT_TYPE** | 126 | 文本类型 |
| **EXTANT_CODES** | 4 | 存佚：未詳(0)、現存(1)、已佚(2)、Secondary source(3) |
| **COUNTRY_CODES** | 11 | 出版地国家 |

### J. 财产（4 张）

| 表 | 行数 | 说明 |
|---|---|---|
| **POSSESSION_DATA** | 60 | 财产记录。`c_possession_desc_chn`、`c_quantity`、`c_measure_code`、`c_possession_act_code` |
| **POSSESSION_ADDR** | 62 | 财产所在地 |
| **POSSESSION_ACT_CODES** | 4 | 行为：擁有(1)、購買(2)、捐出(3) |
| **MEASURE_CODES** | 7 | 计量单位：石(1)、匹(2)、緡貫(3)、兩(4)、楹(5)、卷(6) |

> ⚠️ 财产模块只有 60 条记录，属于**尚未大规模录入**的边缘模块。

### K. 事件（3 张）

| 表 | 行数 | 说明 |
|---|---|---|
| **EVENTS_DATA** | 427 | 人物参与的事件 |
| **EVENTS_ADDR** | 4 | 事件发生的地址 |
| **EVENT_CODES** | 117 | 事件类型字典 |

> ⚠️ 事件模块同样是**起步阶段**（427 条），不要指望用它做事件史分析。

### L. 通用代码表与时间（8 张）

| 表 | 行数 | 说明 |
|---|---|---|
| **DYNASTIES** | 85 | 朝代：`c_dy`、`c_dynasty_chn`、`c_start`/`c_end`(起止年)、`c_sort`。**做分期统计必 JOIN** |
| **NIAN_HAO** | 682 | 年号：`c_nianhao_id`、`c_nianhao_chn`、`c_dy`、`c_firstyear`/`c_lastyear`。公历年 ↔ 年号互转就靠它 |
| **GANZHI_CODES** | 61 | 干支（六十甲子） |
| **YEAR_RANGE_CODES** | 6 | 时间精度（見 §2.1） |
| **INDEXYEAR_TYPE_CODES** | 31 | 索引年推导规则编号（據生年/據卒年-享年+1/據進士登科年-30…） |
| **CHORONYM_CODES** | 173 | 郡望（地名+族姓，如「博陵崔氏」） |
| **ETHNICITY_TRIBE_CODES** | 498 | 族属/部落 |
| **HOUSEHOLD_STATUS_CODES** | 34 | 户籍状况 |

---

## 四、23 个视图怎么用（官方没有的部分）

> 其中 18 个来自上游 `scripts/create_views.sh`；
> 另有 **3 个是本项目自行新增的分析型视图**（4.3 节），面向族谱、县城、单本文献三个具体研究视角。

视图 = **已经帮你 JOIN 好代码表的反规范化表**。原始数据里那些 `c_dy=15`、`c_status_code=...` 全部被翻译成了中英文文本，而且**原始编码列也保留着**，方便你既看得懂又筛得动。

命名规律：`View_<主题>Data` 是主题本身，`View_<主题>AddrData` 是同一主题 + 地理信息。

### 4.1 总览

| 视图 | 行数 | 列数 | 基于 | 一句话用途 |
|---|---:|---:|---|---|
| `View_PeopleData` | 662,152 | 91 | BIOG_MAIN + 10 张代码表 | **人物全档案**，91 列，最宽的一张 |
| `View_PeopleAddrData` | 662,152 | 13 | BIOG_MAIN + ADDR_CODES | 人物 + 籍贯经纬度，**轻量版，画地图用它** |
| `View_AltnameData` | 208,878 | 12 | ALTNAME_DATA | 别名 + 类型中文 |
| `View_KinAddrData` | 562,953 | 17 | KIN_DATA | 亲属关系 + 双方姓名 + 籍贯 |
| `View_AssociationData` | 190,064 | 48 | ASSOC_DATA + 11 张代码表 | **社会关系全展开**，网络分析首选 |
| `View_EntryData` | 265,037 | 64 | ENTRY_DATA + 12 张代码表 | 入仕记录全展开，科举研究首选 |
| `View_PostingOfficeData` | 591,683 | 56 | POSTED_TO_OFFICE_DATA + 10 张 | 任职全展开（官名/任期/任命性质/朝代） |
| `View_PostingAddrData` | 465,390 | 6 | POSTED_TO_ADDR_DATA | 任职 + 治所地名（精简） |
| `View_BiogAddrData` | 461,830 | 37 | BIOG_ADDR_DATA | 人物↔地址关系全展开（含 9 种地址关系类型） |
| `View_StatusData` | 73,571 | 27 | STATUS_DATA | 社会身份 + 中文类别 |
| `View_BiogInstData` | 571 | 35 | BIOG_INST_DATA | 人物在机构的角色 |
| `View_BiogInstAddrData` | 571 | 39 | 同上 + ADDR_CODES | 机构角色 + 机构地址 |
| `View_BiogTextData` | 53,354 | 13 | BIOG_TEXT_DATA | 人物↔著作 + 角色 |
| `View_BiogSourceData` | 1,254,352 | 13 | BIOG_SOURCE_DATA | **人物↔史料来源** + 外链 |
| `View_PossessionsData` | 66 | 26 | POSSESSION_DATA | 财产记录 |
| `View_PossessionsAddrData` | 66 | 28 | + ADDR_CODES | 财产 + 所在地 |
| `View_EventData` | 427 | 30 | EVENTS_DATA | 事件记录 |
| `View_EventAddrData` | 4 | 26 | EVENTS_ADDR | 事件 + 发生地 |
| **`View_KinshipGenealogyData`** 🆕 | 562,953 | 37 | KIN_DATA + 6 张 | **族谱视角**：世代偏移 / 直系旁系姻亲 / 是否同姓 |
| **`View_CountyPeopleData`** 🆕 | 353,679 | 33 | BIOG_ADDR + ADDRESSES | **县城视角**：只留县级地址 + 上级行政层级 |
| **`View_TextAssociationData`** 🆕 | 2,198,492 | 16 | 7 张表 UNION ALL | **单本文献视角**：`c_source` 一本书里的全部关联 |
| **`View_PersonLifeTimeline`** 🆕 | 3,006,222 | 13 | 12 张表 UNION ALL | **生平年谱**：14 个人生阶段 + 分层时间精度 |
| **`View_RelationEdges`** 🆕 | 2,245,701 | 12 | 12 类关系 UNION ALL | **关系图谱**：属性图边表，递归 CTE 多跳遍历 |

### 4.2 逐视图说明

#### ① `View_PeopleData`（91 列）— 人物主视图
`BIOG_MAIN` 把 10 张代码表都 JOIN 进来了：朝代、籍贯（含经纬度）、族属、户籍、郡望、索引年规则、生卒年号、干支。
**关键列**：`c_personid`、`c_name_chn`/`c_name`、`c_dynasty_chn`、`c_index_year`、`c_birthyear`/`c_deathyear`、`c_index_addr_chn`、`c_index_addr_x_coord`/`c_index_addr_y_coord`、`c_ethnicity_desc_chn`、`c_female`、`c_surname_chn`/`c_mingzi_chn`。
**注意**：91 列很宽，如果只要人名+籍贯+经纬度，**用 `View_PeopleAddrData`（13 列）会快很多**。

#### ② `View_PeopleAddrData`（13 列）— 画地图专用
一人一行，带 `x_coord`/`y_coord`。空间分析的人口底表。

#### ③ `View_AltnameData`
`c_alt_name_chn` + `c_name_type_desc_chn`（字/號/諡…）。查一个人所有叫法。

#### ④ `View_KinAddrData`
亲属关系的读法：`c_personid`(本人) — `c_kinrel_chn`(关系) → `c_kin_id`(对方)。列名 `c_kin_name`/`c_kin_chn` 是对方姓名，`c_addr_name`/`c_addr_chn` 是对方籍贯。

#### ⑤ `View_AssociationData`（48 列）— 社会网络首选
`c_personid`(本人) → `c_link_chn`(关系) → `c_node_chn`(对方姓名)、`c_node_id`(对方 ID)。**注意列名变了**：底表 `ASSOC_DATA` 叫 `c_assoc_id`，视图里改叫 `c_node_id`。
比底表多了：关系类型中文、通过哪位亲属建立(`c_kin_name_chn`/`c_assoc_kin_name_chn`)、文体/场合/主题中文、关系发生地(`c_assoc_addr_chn`)、年号中文(`c_assoc_fy_nh_chn`)。
**做 Pajek/Gephi 网络图直接导出这张表即可。**

#### ⑥ `View_EntryData`（64 列）— 科举研究首选
含入仕方式中文(`c_entry_desc_chn`)、年份、名次(`c_exam_rank`)、科目(`c_exam_field`)、年龄、考试地(`c_entry_addr_chn`+经纬度)、父母存殁(`c_parental_status_desc_chn`)。

#### ⑦ `View_PostingOfficeData`（56 列）— 任官研究首选
官名(`c_office_chn`/`c_office_pinyin`/`c_office_trans`)、任期(`c_firstyear`/`c_lastyear`)、任命性质(`c_appt_desc_chn`)、是否赴任(`c_assume_office_desc_chn`)、官制范畴(`c_category_desc_chn`)、朝代。

#### ⑧ `View_PostingAddrData`（6 列）
只有 `c_personid`/`c_posting_id`/`c_office_id`/`c_addr_id`/`c_office_addr_name`/`c_office_addr_chn`。要官名就 JOIN `OFFICE_CODES`。

#### ⑨ `View_BiogAddrData`（37 列）
`c_addr_desc_chn` 就是地址关系类型（籍貫/遷住地/葬地/死所…）。**做人口迁徙、籍贯分布用这张，不要用 `View_PeopleAddrData`**（后者只给索引地）。

#### ⑩ `View_StatusData`
`c_status_desc_chn` 直接给中文身份（書法家、畫家…）。

#### ⑪⑫ `View_BiogInstData` / `View_BiogInstAddrData`
人物在书院/寺观的角色。后者多了机构地址与坐标。

#### ⑬ `View_BiogTextData`
`c_title_chn`(书名) + `c_role_desc_chn`(撰著者/編者…)。

#### ⑭ `View_BiogSourceData` — 史料溯源
`c_title_chn`(来源书名)、`c_pages`(页码)、`c_main_source`(1=主要来源)、`c_url_api`/`c_url_homepage`/`c_hyperlink`。**评估某条记载可信度、溯源时用。**

#### ⑮⑯ `View_PossessionsData` / `View_PossessionsAddrData`
财产。数据量极小（66 条）。

#### ⑰⑱ `View_EventData` / `View_EventAddrData`
事件。数据量极小（427 / 4 条）。

### 4.3 新增的 5 个分析型视图

上游那 18 个视图是「把一张事实表 + 它的代码表摊平」，回答的是**这张表里有什么**。
但做研究时我们更常问的是**跨表的主题性问题**。下面 3 个视图就是为此新增的，
由 `scripts/create_custom_views.sh` 创建（幂等，可重复执行）。

| 视图 | 行数 | 研究视角 | 回答的问题 |
|---|---:|---|---|
| `View_KinshipGenealogyData` | 562,953 | 族谱 | 某人有哪些亲属？隔几代？是父系、母系还是姻亲？是否同宗同姓？ |
| `View_CountyPeopleData` | 353,679 | 县城 | 某个县（及其上级府州路省）下有哪些人？以什么身份与该县关联？ |
| `View_TextAssociationData` | 2,198,492 | 单本文献 | 只看某一本书，它记载了哪些人、哪些关系？ |

---

#### ① `View_KinshipGenealogyData`（族谱视角）

**来源**：`KIN_DATA` + `KINSHIP_CODES` + `BIOG_MAIN`(×2) + `DYNASTIES` + `CHORONYM_CODES` + `ADDR_CODES` + `TEXT_CODES`

在原 `KIN_DATA` 基础上补了四类族谱研究必需的字段：

| 字段 | 说明 |
|---|---|
| `generation_offset` | **世代差** = `c_upstep - c_dwnstep`。正数 = 长辈几代，负数 = 晚辈几代，0 = 同辈。父=+1，祖父=+2，子=−1 |
| `lineage_type` | **宗亲分类**：`直系尊長` / `直系卑幼` / `旁系` / `姻親` / `未詳`。由 `KINSHIP_CODES` 的四个度量列推导：先看 `c_marstep`(姻亲) → `c_colstep`(旁系) → `c_upstep`(尊长) → `c_dwnstep`(卑幼) |
| `same_surname` | **是否同姓**（1/0）。判断父系宗亲的关键信号——姻亲几乎必然异姓 |
| `person_choronym_chn` | 本人的**郡望**（如「博陵崔氏」），宗族归属标识 |

两侧人物信息都展开：姓名、姓、生卒年、索引年、朝代、籍贯。附 `kin_identified`(1=亲属已识别到具体人物) 与出处书名页码。

> ⚠️ 亲属是**单向存储**的。要建完整家谱，需要把反向关系也补上（见 5.4 节示例 ㉓）。

**实测**（王安石 1762）：父 王益(+1) / 母 吳氏 / 兄 王安仁(0,同姓) / 弟 王安禮、王安國(0,同姓) / 妻 吳氏(姻親,异姓) / 岳父 吳蕡(姻親) / 妹夫 朱明之 / 連襟 王令 / 姪女之夫 蔡京(−1)。

全库亲属类型分布：直系卑幼 172,885 · 直系尊長 171,315 · 旁系 132,499 · 姻親 83,502（其中同姓仅 728 条，即表亲婚）。

---

#### ② `View_CountyPeopleData`（县城视角）

**来源**：`BIOG_ADDR_DATA` + `ADDR_CODES`(县级) + `BIOG_MAIN` + `ADDRESSES`(层级) + `BIOG_ADDR_CODES` + `DYNASTIES` + `TEXT_CODES`

把「人—地址」关系限定到**县级政区**，并把该县的**上级行政链**一并带出。

| 字段 | 说明 |
|---|---|
| `county_name_chn` / `county_addr_id` | 县名与地址 ID |
| `county_admin_type` | 级别，取值 `Xian` / `xian` / `County`（**源码大小写不统一**，视图里已用 `LOWER()` 兼容） |
| `county_x_coord` / `county_y_coord` | 县治经纬度，可直接画图 |
| `county_firstyear` / `county_lastyear` | 该县建制的起止年 |
| `parent1..parent5_name_chn` | **上级行政链**（府/州 → 路/省 → …），来自 `ADDRESSES` |
| `belongs_firstyear` / `belongs_lastyear` | 这条隶属关系有效的时段 |
| `addr_relation_code` / `addr_relation_chn` | 人与该县的关系：1=籍貫、7=本貫、2=遷住地、9=葬地、10=死所… |
| 人物侧 | 姓名、姓、性别、索引年、生卒年、朝代 |

> ⚠️ **层级是「代表性」的一条**。`ADDRESSES` 里每个 `c_addr_id` 平均有 2.14 条隶属记录（一个朝代一条），直接 JOIN 会让同一个人重复出现。视图按「**优先取覆盖该人物索引年的时段，否则取存续最长的时段**」挑单条，保证一人一行。要逐时段精确层级，请直查 `ADDRESSES`。

**实测**：籍贯人口 TOP — 大興 5,411（順天府/直隸省 1644-1911）、洛陽 3,040、山陰 2,873、歙縣 2,619。
吳縣 → 蘇州 → 兩浙西路（960-1112）下的人物：程師孟、張詵、張詢 等宋代人物，层级与时段都正确。

---

#### ③ `View_TextAssociationData`（单本文献视角）

**来源**：7 张事实表 `UNION ALL` + `TEXT_CODES`

「**只看这一本书**」——把 CBDB 里所有带 `c_source`（出处文献）的关联关系汇成一条流，用 `c_source = <c_textid>` 就能还原一本书记载的社会世界。

| 字段 | 说明 |
|---|---|
| `c_source` / `source_title_chn` | 出处文献 ID 与书名 |
| `relation_category` | 关联大类（见下表） |
| `relation_desc_chn` | 具体关系（如「友」「彈劾」「是Y的恩主」「進士」「知州」「籍貫」） |
| `c_personid` / `person_name_chn` | 主体人物 |
| `counterpart_id` / `counterpart_name_chn` | **关系的另一端** |
| `counterpart_is_person` | 1 = 另一端是另一个人物；0 = 另一端是编码（官职/入仕途径/身份/地名/书名） |
| `c_year` / `c_pages` / `c_notes` | 年份、页码、备注 |

七类关联（全库条数）：

| relation_category | 条数 | counterpart 是什么 |
|---|---:|---|
| 任官 | 591,683 | 官职（`OFFICE_CODES`） |
| 親屬關係 | 562,953 | 亲属人物 |
| 人物地理 | 461,830 | 地名（`ADDR_CODES`） |
| 入仕 | 265,037 | 入仕途径（`ENTRY_CODES`） |
| 社會關係 | 190,064 | 关系人物 |
| 社會身份 | 73,571 | 身份（`STATUS_CODES`） |
| 著作角色 | 53,354 | 书名（`TEXT_CODES`） |

**实测**：`c_source = 7596`（宋人傳記資料索引·電子版）覆盖 **25,589 位人物**、18,461 个关联对象，年份跨度 −1 至 1370。
其中王安石的记录：與陳升之「是Y的恩主」、與趙鼎臣/謝景溫/孫覺/王存「友」、與程昉「彈劾」、被余象/張戩「被Y彈劾」…

> 💡 这个视图的典型用法是**限定单一史源做子集分析**，避免把不同性质、不同可信度的史料混在一起统计。

#### ④ `View_PersonLifeTimeline`（生平年谱视角，3,006,222 行）

**来源**：12 张事实表 `UNION ALL` 成 14 个人生阶段 + 8 张维表

「**一个人的一生**」——把散落在 12 张关系表里的记录摊成一条事件流，每行带 `stage`（阶段）与 `time_precision`（这条记录的时间精确到哪一级）。

| 字段 | 说明 |
|---|---|
| `stage_no` / `stage` | 1 生 / 2 名號 / 3 親屬 / 4 地理 / 5 機構 / 6 入仕 / 7 任官 / 8 任職地 / 9 交遊 / 10 身份 / 11 著作 / 12 財產 / 13 事件 / 14 卒 |
| `event_label` | 拼好的中文事件描述（含关系名与对象） |
| `counterpart_type` / `_id` / `_name_chn` | 关系另一端（人物/地名/官職/文本/身份/事件/財產/入仕途徑） |
| `year_from` / `year_to` | 原始起止年（无则 NULL） |
| `time_precision` | `year` / `nianhao` / `anchor` / `sequence` / `dynasty` / `undated` |
| `sort_year` / `sort_seq` | 排序用的年与序号（配合 `time_precision` 使用，见 §6.4） |
| `c_source` | 出处文献 ID |

**注意**：`sort_year` 不是「真实年份」——`nianhao` 级取的是年号区间中点，`anchor` 级取的是**关联对象**的年份（亲属用对方的 `c_index_year`，著作借用 `TEXT_CODES.c_text_year`）。做年代统计前务必先按 `time_precision` 过滤。

#### ⑤ `View_RelationEdges`（关系图谱视角，2,245,701 行）

**来源**：12 类关系 `UNION ALL`，建模成属性图（property graph）

「**A 关系 B、B 关系 C**」——把 CBDB 全库当成一张图，供递归 CTE 做多跳遍历。

| 字段 | 说明 |
|---|---|
| `src_type` / `src_id` / `src_name_chn` | 边的起点（类型 + ID + 中文名） |
| `dst_type` / `dst_id` / `dst_name_chn` | 边的终点 |
| 节点类型 | `P` 人物 / `A` 地址 / `O` 官職 / `I` 機構 / `T` 文本 / `S` 身份 / `E` 事件 / `N` 財產 / `C` 入仕途徑 / `Y` 朝代 |
| `relation` | 关系中文名（如「父」「友」「知州」「籍貫」「隸屬於」） |
| `edge_type` | `kinship` / `association` / `identity` / `person_place` / `person_office` / `person_institution` / `person_text` / `person_status` / `person_entry` / `person_event` / `place_hierarchy` / `institution_place` |
| `year_from` / `year_to` / `time_precision` | 边的时间窗 |
| `c_source` | 出处 |

**用法要点**：直接在 224 万行的 UNION ALL 视图上跑递归会全表重扫。正确姿势是先物化成临时表（`src_type='P' AND dst_type='P'`）+ **双向补全**（亲属/交游是单向存储的）+ **建索引**，再递归。完整方法论见 §6.5。

---

## 五、实战查询 Cookbook

> 以下 22 条全部在本机 `cbdb_20260926.sqlite3` 上**实测通过**。可直接粘贴到 DBeaver。
> 演示人物：`c_personid = 1762`（王安石）。

### 5.1 单个人物的完整档案

```sql
-- ① 基本信息
SELECT c_personid, c_name_chn, c_name, c_dynasty_chn, c_index_year,
       c_birthyear, c_deathyear, c_index_addr_chn
FROM View_PeopleData WHERE c_name_chn LIKE '%蘇軾%' LIMIT 5;
-- 结果：3767 蘇軾 Su Shi 宋 1036 1036 1101 眉山

-- ② 所有别名（字、號、諡…）
SELECT c_personid, c_alt_name_chn, c_name_type_desc_chn
FROM View_AltnameData WHERE c_personid = 1762;
-- 结果：介甫(字)、半山老人(室名、別號)…

-- ③ 亲属（注意要自己 JOIN 姓名）
SELECT k.c_personid, p1.c_name_chn AS 本人, k.c_kin_id,
       p2.c_name_chn AS 亲属, kc.c_kinrel_chn AS 关系
FROM KIN_DATA k
JOIN BIOG_MAIN p1 ON p1.c_personid = k.c_personid
JOIN BIOG_MAIN p2 ON p2.c_personid = k.c_kin_id
JOIN KINSHIP_CODES kc ON kc.c_kincode = k.c_kin_code
WHERE k.c_personid = 1762 AND k.c_kin_id > 0;
-- 结果：王貫之(從祖;伯叔祖)、王益(父)…

-- ④ 社会关系
SELECT c_personid, c_node_chn AS 对方, c_link_chn AS 关系, c_assoc_first_year AS 年份
FROM View_AssociationData WHERE c_personid = 1762;
-- 结果：陳升之(是Y的恩主)、張吉甫(是Y的恩主, 1080)…

-- ⑤ 入仕
SELECT c_name_chn, c_entry_desc_chn AS 途径, c_year AS 年份, c_exam_rank AS 名次
FROM View_EntryData WHERE c_personid = 1762;
-- 结果：王安石 | 科舉: 進士(籠統) | 1042

-- ⑥ 任官经历
SELECT c_office_chn AS 官职, c_firstyear, c_lastyear,
       c_appt_desc_chn AS 任命性质, c_assume_office_desc_chn AS 赴任情况, c_dynasty_chn
FROM View_PostingOfficeData WHERE c_personid = 1762 ORDER BY c_firstyear;

-- ⑦ 任职地点
SELECT a.c_office_id, o.c_office_chn AS 官职, a.c_addr_id, a.c_office_addr_chn AS 治所
FROM View_PostingAddrData a
LEFT JOIN OFFICE_CODES o ON o.c_office_id = a.c_office_id
WHERE a.c_personid = 1762;

-- ⑧ 地理轨迹（籍贯、迁徙、葬地…）
SELECT c_addr_chn AS 地点, c_addr_desc_chn AS 关系, c_firstyear, c_lastyear
FROM View_BiogAddrData WHERE c_personid = 1762;
-- 结果：臨川(籍貫)、江寧府(死所, 1086)

-- ⑨ 社会身份
SELECT c_status_desc_chn FROM View_StatusData WHERE c_personid = 1762;
-- 结果：書法家、畫家…

-- ⑩ 著作
SELECT c_title_chn AS 书名, c_role_desc_chn AS 角色
FROM View_BiogTextData WHERE c_personid = 1762;
-- 结果：臨川先生文集、周官新義(撰著者)…

-- ⑪ 这条记载出自哪本书（史料溯源）
SELECT c_title_chn AS 来源, c_pages AS 页码, c_main_source AS 主要来源
FROM View_BiogSourceData WHERE c_personid = 1762;
-- 结果：宋人傳記資料索引(電子版) p.1536、中國哲學書電子化計劃 …
```

### 5.2 群体统计

```sql
-- ⑫ 各朝代人物数量（清最多 23.8 万，明 22.6 万）
SELECT d.c_dynasty_chn AS 朝代, COUNT(*) AS 人数
FROM BIOG_MAIN b JOIN DYNASTIES d ON d.c_dy = b.c_dy
GROUP BY d.c_dynasty_chn ORDER BY 人数 DESC LIMIT 12;

-- ⑬ 北宋进士录取人数逐年
SELECT c_year AS 年份, COUNT(*) AS 人数
FROM View_EntryData
WHERE c_entry_desc_chn LIKE '%進士%' AND c_year BETWEEN 960 AND 1127
GROUP BY c_year ORDER BY c_year;

-- ⑭ 籍贯地理分布 TOP10（含经纬度，可直接导入 QGIS）
SELECT c_index_addr_chn AS 籍贯, x_coord, y_coord, COUNT(*) AS 人数
FROM View_PeopleAddrData
WHERE c_index_addr_id > 0
GROUP BY c_index_addr_id ORDER BY 人数 DESC LIMIT 10;
-- 结果：大興 4605、山陰 2832…

-- ⑮ 女性人物总数（58,402 人，约占 8.8%）
SELECT COUNT(*) FROM BIOG_MAIN WHERE c_female = 1;

-- ⑯ 各类地址关系（籍贯/遷住地/葬地…）的条目分布
--    注意：视图里没有 c_addr_type 原始编码列，只能按中文描述分组
SELECT c_addr_desc_chn AS 关系类型, COUNT(*) AS 条数
FROM View_BiogAddrData GROUP BY c_addr_desc_chn ORDER BY 条数 DESC;
```

### 5.3 特定主题

```sql
-- ⑰ 行政层级归属（某地某年归谁管）
SELECT c_addr_id, c_name_chn AS 地名, c_admin_type AS 级别,
       c_belongs_firstyear, c_belongs_lastyear,
       belongs1_Name_chn AS 一级, belongs2_Name_chn AS 二级, belongs3_Name_chn AS 三级
FROM ADDRESSES WHERE c_name_chn LIKE '%吳縣%';
-- 结果：1368-1643 蘇州府→中都留守司→明朝 | 1949-2005 蘇州→江蘇省→中華人民共和國

-- ⑱ 官名检索 + 英译
SELECT c_office_id, c_office_chn, c_office_pinyin, c_dy
FROM OFFICE_CODES WHERE c_office_chn LIKE '%知州%';

-- ⑲ 官职在官制分类树中的位置
SELECT o.c_office_chn AS 官名, t.c_office_type_desc_chn AS 分类
FROM OFFICE_CODES o
JOIN OFFICE_CODE_TYPE_REL r ON r.c_office_id = o.c_office_id
JOIN OFFICE_TYPE_TREE t ON t.c_office_type_node_id = r.c_office_tree_id
WHERE o.c_office_chn = '知州';
-- 结果：唐朝 / 府州郡縣官類

-- ⑳ 亲属距离计算（用 KINSHIP_CODES 的四个度量值）
--     父: upstep=1  子: dwnstep=1  兄弟: colstep=1  妻: marstep=1
SELECT kc.c_kinrel_chn AS 称谓, kc.c_upstep, kc.c_dwnstep, kc.c_colstep, kc.c_marstep,
       COUNT(*) AS 条数
FROM KIN_DATA k JOIN KINSHIP_CODES kc ON kc.c_kincode = k.c_kin_code
GROUP BY k.c_kin_code ORDER BY 条数 DESC LIMIT 20;

-- ㉑ 重复人物合并（做 JOIN 前必须归一化）
SELECT m.c_personid, b1.c_name_chn AS 保留记录,
       m.c_merged_from_personid, b2.c_name_chn AS 被合并记录
FROM MERGED_PERSON_DATA m
LEFT JOIN BIOG_MAIN b1 ON b1.c_personid = m.c_personid
LEFT JOIN BIOG_MAIN b2 ON b2.c_personid = m.c_merged_from_personid;

-- ㉒ 导出社会网络（Pajek / Gephi 的边表）
--    注意：视图里对方人物的 ID 列名是 c_node_id，不是 ASSOC_DATA 的 c_assoc_id
SELECT c_personid AS source, c_node_id AS target,
       c_link_chn AS relation, c_assoc_first_year AS year
FROM View_AssociationData
WHERE c_node_id > 0 AND c_personid > 0;
```

### 5.4 三个新增视图的用法

```sql
-- ㉓ 族谱：某人的完整亲属表（按世代差排序，长辈在上）
SELECT kin_personid, kin_name_chn AS 姓名, kinrel_chn AS 称谓,
       generation_offset AS 世代差, lineage_type AS 宗亲类别,
       same_surname AS 同姓, kin_index_year AS 亲属索引年, source_title_chn AS 出处
FROM View_KinshipGenealogyData
WHERE c_personid = 1762 AND kin_identified = 1
ORDER BY generation_offset DESC;

-- ㉔ 族谱：把单向关系补成双向，得到可画树的完整边表
--    正向：A 的亲属是 B（世代差 = +n）；反向：B 的亲属是 A（世代差取反）
SELECT c_personid AS person, kin_personid AS relative,
       kinrel_chn AS 称谓, generation_offset AS 世代差, lineage_type
FROM View_KinshipGenealogyData WHERE kin_identified = 1
UNION ALL
SELECT kin_personid AS person, c_personid AS relative,
       '（反向）' || kinrel_chn AS 称谓,
       -generation_offset AS 世代差, lineage_type
FROM View_KinshipGenealogyData WHERE kin_identified = 1;

-- ㉕ 族谱：找规模最大的同姓宗族（按「同姓亲属对」计数）
SELECT person_surname_chn AS 姓氏, COUNT(*) AS 同姓亲属对数
FROM View_KinshipGenealogyData
WHERE same_surname = 1 AND person_surname_chn IS NOT NULL
GROUP BY person_surname_chn ORDER BY 同姓亲属对数 DESC LIMIT 20;
-- 实测 TOP：李 31,871 / 王 26,021 / 張 22,395 / 陳 15,588 / 劉 14,818

-- ㉖ 族谱：某姓氏的联姻对象（看姻亲网络）
SELECT kin_surname_chn AS 联姻姓氏, COUNT(*) AS 次数
FROM View_KinshipGenealogyData
WHERE lineage_type = '姻親' AND person_surname_chn = '王'
  AND kin_surname_chn IS NOT NULL AND kin_surname_chn <> '王'
GROUP BY kin_surname_chn ORDER BY 次数 DESC LIMIT 20;

-- ㉗ 县城：各县籍贯人口 TOP20（带上级府州 + 经纬度，可直接导入 QGIS）
SELECT county_name_chn AS 县, parent1_name_chn AS 府州, parent2_name_chn AS 路省,
       belongs_firstyear AS 起始年, belongs_lastyear AS 终止年,
       county_x_coord AS 经度, county_y_coord AS 纬度,
       COUNT(DISTINCT c_personid) AS 人数
FROM View_CountyPeopleData
WHERE addr_relation_code = 1          -- 1 = 籍貫(基本地址)
GROUP BY county_addr_id ORDER BY 人数 DESC LIMIT 20;

-- ㉘ 县城：某县在某一时段的全部人物（含关系类型）
SELECT person_name_chn AS 姓名, dynasty_chn AS 朝代, c_index_year AS 索引年,
       addr_relation_chn AS 与该县关系, belongs_firstyear, belongs_lastyear
FROM View_CountyPeopleData
WHERE county_name_chn = '吳縣' AND addr_relation_code = 1;

-- ㉙ 县城：某府下辖各县的科举产出对比（县 → 进士数）
SELECT c.county_name_chn AS 县, c.parent1_name_chn AS 府,
       COUNT(DISTINCT e.c_personid) AS 进士人数
FROM View_CountyPeopleData c
JOIN View_EntryData e ON e.c_personid = c.c_personid
WHERE c.addr_relation_code = 1 AND c.parent1_name_chn = '蘇州府'
  AND e.c_entry_desc_chn LIKE '%進士%'
GROUP BY c.county_addr_id ORDER BY 进士人数 DESC;

-- ㉚ 文献：先找一本书的 c_textid
SELECT c_textid, c_title_chn, c_text_dy FROM TEXT_CODES
WHERE c_title_chn LIKE '%宋人傳記資料索引%';
-- → 7596

-- ㉛ 文献：这本书记载了哪些人、哪些关系（核心用法）
SELECT relation_category AS 类别, relation_desc_chn AS 关系,
       c_personid, person_name_chn AS 人物,
       counterpart_name_chn AS 关联对象, c_year AS 年份, c_pages AS 页码
FROM View_TextAssociationData
WHERE c_source = 7596                 -- ← 换成目标书的 c_textid
ORDER BY relation_category, c_personid
LIMIT 200;

-- ㉜ 文献：一本书的覆盖面统计
SELECT relation_category AS 类别, COUNT(*) AS 条数,
       COUNT(DISTINCT c_personid) AS 涉及人数
FROM View_TextAssociationData
WHERE c_source = 7596
GROUP BY relation_category ORDER BY 条数 DESC;

-- ㉝ 文献：某书中某个人的全部记载
SELECT relation_category, relation_desc_chn, counterpart_name_chn, c_year, c_pages
FROM View_TextAssociationData
WHERE c_source = 7596 AND person_name_chn = '王安石';

-- ㉞ 文献：两本书共同记载的人物（史料交叉验证）
SELECT a.c_personid, a.person_name_chn, COUNT(DISTINCT a.c_source) AS 书数
FROM View_TextAssociationData a
WHERE a.c_source IN (7596, 27147)     -- 宋人傳記資料索引 / 明人傳記資料索引
GROUP BY a.c_personid HAVING 书数 > 1;
```

---

## 六、一个人的一生：生平轨迹与 A→B→C 链式关系遍历

这一章回答三个问题：**查一个人的生平要关联哪些表？表够不够用？** 以及 **想做「A 关系 B、B 关系 C」这种不断扩展、不断排序的链式查询，方法论是什么？**

### 6.1 结论先行

| 问题 | 结论 |
|---|---|
| 表结构够不够用？ | **够用。** CBDB 的 12 张关系表 + 40 余张代码表，已经覆盖了「生 → 名号 → 亲属 → 籍贯 → 教育 → 入仕 → 任官 → 任职地 → 交游 → 身份 → 著作 → 财产 → 事件 → 卒」全部 14 个人生阶段，不存在「某类信息根本没表可放」的结构性缺失。 |
| 那缺什么？ | **缺的是时间轴，不是表。** 全库 662,152 人中只有 **59,838 人（9.0%）** 有确切生年、**71,279 人（10.8%）** 有确切卒年、**37,442 人（5.7%）** 生卒俱全；亲属关系 **0%** 有年份、著作 **0%** 有年份、任职地 **0 个自有时间字段**。所以「按时间排序的一生」在多数人身上只能做到**分层精度**，做不到精确时间线。 |
| 链式遍历能做吗？ | **能做，但必须当成图来算，不能当表来 JOIN。** 已建好 `View_RelationEdges`（224.6 万条带类型的边）+ 递归 CTE 模板。深度 1 = 1,370 条、深度 2 = 22.3 万条、深度 3 = **5,183 万条**——三跳就组合爆炸，必须剪枝。 |

---

### 6.2 一条完整生平需要关联哪些表

按人生 14 个阶段列出。每张关系表左侧是「事实」，右侧是「把代码翻译成人话」的维表——**只查左表只能拿到数字，必须 JOIN 右表才有意义**。

| # | 人生阶段 | 事实表 | 必须关联的维表 | 时间字段 | 有公历年占比 |
|---:|---|---|---|---|---:|
| 1 | **生** | `BIOG_MAIN` | `DYNASTIES` / `NIAN_HAO`（`c_by_nh_code`） | `c_birthyear` | 59,838 / 662,152 |
| 2 | **名號**（字、号、谥、室名…） | `ALTNAME_DATA` | `ALTNAME_CODES` | 无，仅 `c_sequence` | 0 |
| 3 | **親屬** | `KIN_DATA` | `KINSHIP_CODES` + `BIOG_MAIN`（对方） | **无** → 用对方 `c_index_year` 作锚点 | 0 |
| 4 | **地理**（籍贯/迁住/葬地/死所） | `BIOG_ADDR_DATA` | `BIOG_ADDR_CODES` + `ADDR_CODES`（+`ADDRESSES` 取层级） | `c_firstyear` / `c_fy_nh_code` | 8,144 / 461,830 (1.8%) |
| 5 | **教育 / 宗教機構** | `BIOG_INST_DATA` | `BIOG_INST_CODES` + `SOCIAL_INSTITUTION_NAME_CODES` | `c_bi_begin_year` | 23 / 571 |
| 6 | **入仕**（科举、荫补、荐举…） | `ENTRY_DATA` | `ENTRY_CODES`（+`ENTRY_TYPES` 归大类） | `c_year` / `c_entry_nh_id` | 100,431 / 265,037 (37.9%) |
| 7 | **任官** | `POSTED_TO_OFFICE_DATA` | `OFFICE_CODES` + `APPOINTMENT_CODES` + `ASSUME_OFFICE_CODES` | `c_firstyear` / `c_fy_nh_code` | 311,311 / 591,683 (52.6%) |
| 8 | **任職地** | `POSTED_TO_ADDR_DATA` | `ADDR_CODES` + `OFFICE_CODES` | **无自有字段** → 借 stage 7 的年份 | 0（自带） |
| 9 | **交遊**（师友、唱和、碑传、政争…） | `ASSOC_DATA` | `ASSOC_CODES` + `BIOG_MAIN`（对方） | `c_assoc_first_year` | 15,761 / 190,064 (8.3%) |
| 10 | **社會身份** | `STATUS_DATA` | `STATUS_CODES` | `c_firstyear` / `c_fy_nh_code` | 1,244 / 73,571 (1.7%) |
| 11 | **著作** | `BIOG_TEXT_DATA` | `TEXT_CODES` + `TEXT_ROLE_CODES` | `c_year`（**100% 空**）→ `TEXT_CODES.c_text_year` 弱锚点 | 0 |
| 12 | **財產** | `POSSESSION_DATA` | `MEASURE_CODES` | `c_possession_yr` | 16 / 60 |
| 13 | **事件** | `EVENTS_DATA` | `EVENT_CODES` | `c_year` / `c_nh_code` | 98 / 427 |
| 14 | **卒** | `BIOG_MAIN` | `DYNASTIES` / `NIAN_HAO`（`c_dy_nh_code`） | `c_deathyear` | 71,279 / 662,152 |

**贯穿全程的三张辅助表**（不是阶段，但每条记录都该挂上）：

- `BIOG_SOURCE_DATA`（125 万行）——每条事实出自哪本书哪一页，做史料溯源/可信度分级时必 JOIN。
- `NIAN_HAO`（年号）+ `YEAR_RANGE_CODES`（`-1 之前 / 0 之間 / 1 之後 / 2 約 / 300 元豐五年前 / 301 元豐五年後`）——只有年号没有公历年时的翻译层。
- `MERGED_PERSON_DATA`（5,994 条）——同一人的重复 ID，统计前必须归并，否则会重复计数。

**`POSTING_DATA` 是个陷阱**：它只有 `c_personid` + `c_posting_id` 两列，**没有任何时间字段**，只是把一次任命的「官职」和「治所」缝在一起的联结表。想补年份只能回到 `POSTED_TO_OFFICE_DATA`。

---

### 6.3 真正的瓶颈：时间轴的四个断层

按严重程度排序：

1. **年内顺序几乎无法还原。** 全表月/日覆盖率：`POSTED_TO_OFFICE_DATA` 有月 1,490 / 日 261（591,683 行中）；`ASSOC_DATA` 有月 470 / 日 257；`EVENTS_DATA` 有月 2 / 日 1。**同一年内的先后只能靠 `c_sequence`（CBDB 录入时的人工排序）**，而 `c_sequence` 只在部分表里有值，且跨表不可比。
2. **亲属关系完全无时间。** 562,953 条 `KIN_DATA` 里公历年、年号、序号**全为 0**。这是最大的结构缺口——CBDB 的亲属表设计成「A 有亲属 B + 关系类型」，不含「何时成为亲属」。
3. **交游关系 91.6% 无时间。** 190,064 条里只有 15,761 条有年份。
4. **生卒年覆盖率极低。** 只有 5.7% 的人有完整生卒。对剩下 94.3% 的人，「从出生到死亡」的区间得用 `c_index_year`（307,858 人，46.5%）± 一个假设窗口（如 ±40 年）近似。

因为这四个断层，**任何声称「按时间精确排序的一生」的查询，都在对 90% 的记录撒谎**。正确做法是显式标注每条记录的时间属于哪一级，见 6.4。

---

### 6.4 `View_PersonLifeTimeline`：分层时间精度（3,006,222 行）

把上表 14 个阶段摊成一条事件流，每条记录带 `time_precision` 标出**它的时间究竟精确到哪一级**，而不是塞一个假年份：

| `time_precision` | 含义 | 做法 | 排序权重 |
|---|---|---|---|
| `year` | 有确切公历年 | 直接用 | 0（最优先） |
| `nianhao` | 只有年号 | 取该年号 `[c_firstyear, c_lastyear]` 的**中点**估算 | 1 |
| `anchor` | 本身无时间 | 借用关联实体的年份（亲属用对方的 `c_index_year`；著作用 `TEXT_CODES.c_text_year`） | 2 |
| `sequence` | 只有录入序号 | 只定先后不定年份，`sort_year` 留空 | 3 |
| `dynasty` | 只有朝代 | 用朝代起始年 | 4 |
| `undated` | 完全无时间 | 沉底 | 5 |

**标准排序写法**（精度高的排前面，无时间的沉底）：

```sql
ORDER BY CASE time_precision WHEN 'year' THEN 0 WHEN 'nianhao' THEN 1 WHEN 'anchor' THEN 2
              WHEN 'sequence' THEN 3 WHEN 'dynasty' THEN 4 ELSE 5 END,
         sort_year, stage_no, sort_seq
```

各阶段实际的时间精度分布（这是判断「某人能不能排出年谱」的直接依据）：

| 阶段 | 总行数 | year | nianhao | anchor | sequence | undated |
|---|---:|---:|---:|---:|---:|---:|
| 生 | 60,427 | 59,838 | 589 | 0 | 0 | 0 |
| 名號 | 208,878 | 0 | 0 | 0 | 13,207 | 195,671 |
| 親屬 | 562,953 | 0 | 0 | 471,971 | 0 | 90,982 |
| 地理 | 461,830 | 8,144 | 158 | 0 | 380,880 | 72,648 |
| 機構 | 571 | 23 | 9 | 0 | 0 | 539 |
| 入仕 | 265,037 | 100,431 | 1,279 | 0 | 153,711 | 9,616 |
| 任官 | 591,683 | 311,311 | 52,030 | 0 | 55,265 | 173,077 |
| 任職地 | 465,390 | 289,301 | 34,891 | 0 | 0 | 141,198 |
| 交遊 | 190,064 | 15,761 | 305 | 0 | 1,906 | 172,092 |
| 身份 | 73,571 | 1,244 | 43 | 0 | 35,895 | 36,389 |
| 著作 | 53,354 | 0 | 0 | 6,255 | 0 | 47,099 |
| 財產 | 60 | 16 | 1 | 0 | 25 | 18 |
| 事件 | 427 | 98 | 17 | 0 | 23 | 289 |
| 卒 | 71,977 | 71,279 | 698 | 0 | 0 | 0 |

**覆盖率**：662,152 人中 **637,985 人（96.3%）** 至少有一条生平记录；**327,736 人（49.5%）** 至少有一条 `year`/`nianhao` 级精度的记录；**25,004 人** 只有生卒、中间完全空白。

**实例——王安石（c_personid = 1762）**（真实输出片段，已按上式排序）：

```
1021  生      出生
1042  入仕    科舉: 進士(籠統)
1042  任官    簽書節度判官廳（正授）
1042  任職地  淮南東路：簽書節度判官廳
1047  任官    知某縣事（正授）  /  任職地 鄞縣
1051  任官    通判（正授）      /  任職地 舒州
1058  任官    提點刑獄所、三司度支判官
1069  任官    參知政事（正授）
1070  任官    同中書門下平章事（正授）
1074  任官    觀文殿大學士、知某州軍州事
1075  任官    同中書門下平章事、昭文館大學士、監修國史
1086  卒      卒（享年 66）
```
> ⚠️ 同一份输出里还混着「999 年 李興為Y作神道碑」「1030 年 譚昉為Y之學生」这类**关联人物自带年份**的记录——那是交游关系的年份，不是王安石本人的年份，且早于其生年。用 `anchor`/`year` 混排时一定要意识到这一点，必要时用「限制在 [生年, 卒年] 区间内」过滤。

---

### 6.5 A → B → C 链式遍历的方法论

CBDB 的关系天然是图：**节点**是人/地/官职/机构/文本/身份/事件，**边**是「任官、亲属、交游、隶屬」等。用表 JOIN 表达多跳会写出来 N 层嵌套且无法控制深度，正确做法是 **把关系物化成边表 + 递归 CTE**。

#### 第 0 步：选一张边表 —— `View_RelationEdges`（2,245,701 行）

统一了 12 种边，每条边带 `relation`（关系名）、`year_from/year_to`、`time_precision`、`c_source`：

| edge_type | 方向 | 行数 | 有年份 |
|---|---|---:|---:|
| `person_office` | P→O | 591,225 | 311,225 |
| `kinship` | P→P | 562,952 | 0 |
| `person_place` | P→A | 461,792 | 8,126 |
| `person_entry` | P→C | 265,037 | 100,431 |
| `association` | P→P | 190,064 | 15,761 |
| `person_status` | P→S | 73,571 | 1,244 |
| `person_text` | P→T | 53,317 | 0 |
| `place_hierarchy` | A→A | 37,180 | 36,394 |
| `identity` | P→P | 5,994 | 0 |
| `institution_place` | I→A | 3,615 | 0 |
| `person_institution` | P→I | 527 | 22 |
| `person_event` | P→E | 427 | 98 |

#### 五步法

1. **物化子图**——先把需要的边拷进临时表（`CREATE TEMP TABLE ... AS SELECT`），不要直接在 224 万行的 UNION ALL 视图上递归，那会全表重扫。
2. **双向补全**——`KIN_DATA` 和 `ASSOC_DATA` 都是单向的（「A 有 B 为父」≠ 库里有「B 有 A 为子」）。用 `UNION ALL` 把 (`a`,`b`) 和 (`b`,`a`) 都放进去，否则网络会缺一半边。
3. **建索引**——`CREATE INDEX ON tmp(a)`（以及 `tmp(b)`）。**这一步决定了递归是 1 秒还是 10 分钟。**
4. **递归 CTE + 路径去重**——用 `path` 字符串 + `instr()` 防环，用 `depth < N` 限深。
5. **时间窗单调折叠 + 剪枝**——沿路径维护 `[lo, hi]` 区间，每走一步 `lo = MAX(lo, 新下界)`、`hi = MIN(hi, 新上界)`；一旦 `lo > hi` 说明这条路径在时间上自相矛盾，立即剪掉。同时把 `[lo, hi]` 与当事人 `[c_birthyear, c_deathyear]`（无生卒则用 `c_index_year ± 40`）求交。

#### 可运行模板

```sql
-- 步骤 1+2+3：物化人物—人物的双向边（含索引）
CREATE TEMP TABLE e_pp AS
SELECT src_id AS a, dst_id AS b, relation, edge_type, year_from, year_to
FROM View_RelationEdges WHERE src_type='P' AND dst_type='P'
UNION ALL
SELECT dst_id, src_id, relation, edge_type, year_from, year_to
FROM View_RelationEdges WHERE src_type='P' AND dst_type='P';   -- 1,518,020 条
CREATE INDEX tmp_e_pp_a ON e_pp(a);

-- 步骤 4+5：递归遍历，带路径去重与时间窗交集
WITH RECURSIVE walk(a, b, depth, path, rels, lo, hi) AS (
  SELECT e.a, e.b, 1, '|'||e.a||'|'||e.b||'|', e.relation,
         COALESCE(e.year_from, -9999), COALESCE(e.year_to, 9999)
  FROM e_pp e WHERE e.a = 1762                       -- 起点：王安石
  UNION ALL
  SELECT w.a, e.b, w.depth+1, w.path||e.b||'|', w.rels||' / '||e.relation,
         MAX(w.lo, COALESCE(e.year_from, -9999)),
         MIN(w.hi, COALESCE(e.year_to,  9999))
  FROM walk w JOIN e_pp e ON e.a = w.b
  WHERE w.depth < 3
    AND instr(w.path, '|'||e.b||'|') = 0             -- 防环
    AND w.lo <= w.hi                                  -- 时间窗自洽
)
SELECT depth, COUNT(*) AS paths,
       SUM(lo <= 1086 AND hi >= 1021) AS within_王安石生卒窗
FROM walk GROUP BY depth;
```

**实测规模（起点 王安石，仅 kinship + association 边）**：

| 深度 | 路径数 | 落在 1021–1086 生卒窗内 |
|---:|---:|---:|
| 1 | 1,370 | 1,318 |
| 2 | 222,703 | 200,921 |
| 3 | **51,835,694** | 43,357,678 |

**深度 3 就是 5,183 万条路径**——这不是数据库慢，是图论意义上的组合爆炸。做多跳分析时必须：限深（通常 2–3）、限制边类型（只走 `association` 或只走 `kinship`）、限制时间窗、限制终点集合（如「只到进士出身的人」）。

#### 「不断排序」怎么实现

SQL 的递归 CTE 是**宽度优先、不可控序**的，做不到「每次扩展后挑最优的那条继续走」。要真正做到动态排序，有两种做法：

- **两阶段法（推荐，纯 SQL）**：先让递归 CTE 把候选路径全跑出来（带 `depth`、`lo`、`hi`、`rels`），再在**外层** `ORDER BY` 你自己的打分函数，例如
  `ORDER BY (depth权重) + (时间窗宽度) + (边类型权重) + (有无确切年份)`。
  这样排序规则可以随时改，不用重跑遍历。
- **优先级队列法（需要程序）**：用 Python 把边表读进内存（`networkx` 或自写 BFS），维护一个优先队列，每次弹出分数最高的节点扩展，直到达到预算。这等价于在图上运行 Dijkstra/A\*，适合「找出 A 到 Z 最可信的一条关系链」这类问题。

打分函数的建议权重（可调）：

```
score = w_depth * depth                     -- 跳数越少越可信
      + w_time  * (1 - 时间窗宽度/100)       -- 窗口越窄越可信
      + w_prec  * (year=0 / nianhao=1 / anchor=2 / undated=3)
      + w_type  * (亲属=0 / 交游=1 / 同僚=2 / 文本=3)
      + w_src   * (史料等级)
```

---

### 6.6 「从出生到死亡的所有 relation」应该长什么样

**理想形态**（CBDB 结构已能承载，只是数据没填满）：

```
生 (c_birthyear)
 └─ 名號：字 / 号 / 谥 / 室名            [应有年份：取字号之年]
 └─ 親屬：父 / 母 / 祖 / 兄弟 / 子 / 婿   [缺年份 —— 最大缺口]
 └─ 地理：籍貫 → 遷住地 → 死所 → 葬地     [籍贯应有"生平有效区间"，现多为 sequence]
 └─ 機構：求学 / 讲学 / 修道 / 寺院        [应有起止年]
 └─ 入仕：科举年份 + 名次 + 考场           [37.9% 有年份，最可用]
 └─ 任官：逐任官职 + 起止年 + 治所         [52.6% 有年份，最可用]
 └─ 交遊：师友 / 唱和 / 碑传 / 举荐 / 政争 [8.3% 有年份]
 └─ 身份：隐士 / 僧道 / 乡绅 / 勋爵        [1.7% 有年份]
 └─ 著作：成书年 + 角色（撰/序/刻/评）      [缺年份，需借 TEXT_CODES.c_text_year]
 └─ 財產：田产 / 宅第                     [几乎无数据]
 └─ 事件：参与的历史事件                   [427 条，几乎无数据]
卒 (c_deathyear, c_death_age)
```

**现实形态**：对绝大多数人，你能拿到的是一条**两端清楚、中间模糊**的序列——

- 两端：入仕年、任官年（这两个是 CBDB 最强的时间锚点，占全库有年份记录的 80% 以上）；
- 中间：籍贯、亲属、交游大部分只能定「在哪一跳之后」，不能定年份；
- 全程：用 `c_index_year`（46.5% 的人有）作为「此人活跃于何时」的单一代表年兜底。

**如果要补齐，最小改动是三件事**（CBDB 官方层面的建议，不是本库能做的）：
1. `KIN_DATA` 增加亲属关系的起止年（或其出生事件年）——否则族谱永远排不进时间；
2. `BIOG_TEXT_DATA` 的 `c_year` 字段已经有结构但没有数据，应回填成书年；
3. `BIOG_ADDR_DATA` 大量只有 `c_sequence`，应把「居住时段」填进 `c_firstyear/c_lastyear`。

---

### 6.7 这一章的可复用查询

```sql
-- ㉟ 任意一个人的完整年谱（改 c_personid 即可）
SELECT stage_no, stage, time_precision, sort_year, sort_seq,
       counterpart_type, counterpart_name_chn, event_label, c_source
FROM View_PersonLifeTimeline
WHERE c_personid = 1762
ORDER BY CASE time_precision WHEN 'year' THEN 0 WHEN 'nianhao' THEN 1 WHEN 'anchor' THEN 2
              WHEN 'sequence' THEN 3 WHEN 'dynasty' THEN 4 ELSE 5 END,
         sort_year, stage_no, sort_seq;

-- ㊱ 只要「有确切年份」的骨架年谱（剔除估算）
SELECT sort_year, stage, event_label
FROM View_PersonLifeTimeline
WHERE c_personid = 1762 AND time_precision = 'year'
ORDER BY sort_year, stage_no;

-- ㊲ 判断某人值不值得做年谱：各时间精度有多少条
SELECT time_precision, COUNT(*) FROM View_PersonLifeTimeline
WHERE c_personid = 1762 GROUP BY time_precision;

-- ㊳ 限定在生卒区间内的年谱（剔除早于生年/晚于卒年的噪声）
SELECT t.stage, t.sort_year, t.event_label
FROM View_PersonLifeTimeline t
JOIN BIOG_MAIN p ON p.c_personid = t.c_personid
WHERE t.c_personid = 1762
  AND (t.sort_year IS NULL
       OR (p.c_birthyear > 0 AND t.sort_year >= p.c_birthyear
           AND p.c_deathyear > 0 AND t.sort_year <= p.c_deathyear))
ORDER BY t.sort_year;

-- ㊴ 两跳关系链：起点 → 中间人 → 终点（带关系名拼接）
--    先执行 6.5 的 CREATE TEMP TABLE e_pp / CREATE INDEX
WITH RECURSIVE walk(a,b,depth,path,rels) AS (
  SELECT e.a, e.b, 1, '|'||e.a||'|'||e.b||'|', e.relation FROM e_pp e WHERE e.a = 1762
  UNION ALL
  SELECT w.a, e.b, w.depth+1, w.path||e.b||'|', w.rels||' / '||e.relation
  FROM walk w JOIN e_pp e ON e.a = w.b
  WHERE w.depth < 2 AND instr(w.path, '|'||e.b||'|') = 0
)
SELECT w.b, bm.c_name_chn AS end_name, w.rels
FROM walk w LEFT JOIN BIOG_MAIN bm ON bm.c_personid = w.b
WHERE w.depth = 2 LIMIT 100;

-- ㊵ 任意类型的边都能查：某地的全部上级隶属（place_hierarchy 递归）
WITH RECURSIVE up(a, b, depth, path) AS (
  SELECT src_id, dst_id, 1, src_name_chn FROM View_RelationEdges
  WHERE edge_type='place_hierarchy' AND src_id = 15279
  UNION ALL
  SELECT e.src_id, e.dst_id, u.depth+1, u.path||' < '||e.dst_name_chn
  FROM up u JOIN View_RelationEdges e ON e.src_id = u.b AND e.edge_type='place_hierarchy'
  WHERE u.depth < 5
)
SELECT depth, path FROM up;
```

---

### 6.8 优化方案：把「时间轴」升级成「区间轴 + 序轴」的双轴模型

#### 6.8.1 先回答「要不要再来一根事件轴」

**不要。** 加事件轴不解决任何问题——事件轴只是换一种**分组标签**（按事件类型排），它不产生新的时间信息。CBDB 缺的是**时间值本身**，不是轴的刻度。

真正该做的，是把原来「一个标量 `sort_year`」的时间轴，升级成：

| 轴 | 类型 | 含义 | 为什么不撒谎 |
|---|---|---|---|
| **区间轴** `lo / hi` | 一对整数 | 这条记录**可能**落在哪一段年 | 区间永远为真，宽度即诚实度 |
| **序轴** `order_rank` | 一个序号 | 纯先后，**不含任何年份** | 不知道年份也能知道先后 |
| **精度轴** `precision` | 枚举 | `exact / propagated / interval / frame` | 告诉下游这条区间能信到什么程度 |

这三者是**同一个模型的三个输出**，不是三套方案。模型就是 **STP（Simple Temporal Problem，简单时间问题）**：把每条记录当成一个时间变量 $t_i$，把「先于 / 晚于 / 相隔 N~M 年」写成约束 $t_j - t_i \in [g_{min}, g_{max}]$，然后做**弧一致性传播**（反复用每条边收窄两端，直到不再变化）。这套东西在调度、规划领域是标准解法，CBDB 正好是它的一个实例。

**为什么 CBDB 特别适合**：CBDB 丢掉了*绝对年份*，但**没有丢掉顺序信息**——

- `c_sequence` —— 录入时的人工排序（任官 27.9 万条有）
- 年号 —— 至少能定 `[c_firstyear, c_lastyear]`
- 生卒边界 —— 一生所有事件必然落在 `[生年, 卒年]`
- 亲属世代 —— 尊长必早于本人出生、卑幼必晚于本人成年
- 领域常识 —— 字在 15~30 岁取、諡號在死后、科举在 12~60 岁、入仕早于任官
- 对方活跃年 —— 交遊/亲属的对方有生卒或 `c_index_year`，可反推窗口

把这些编译成约束网络，就能把「没有年份的一生」变成「**有区间的一生 + 有先后的一生**」。

#### 6.8.2 约束规则表（R1–R8）

脚本 `scripts/life_order.py` 对每个人生成如下约束（写作 `(a, b, min, max, rule)`，意思是 *b 落在 a 之后 [min, max] 年内*）：

| # | 规则 | 内容 | 依据 |
|---|---|---|---|
| R1 | `birth_first` | 出生早于一切（尊长亲属豁免） | 定义 |
| R2 | `death_last` | 死亡晚于一切（卑幼亲属、諡號、著作豁免） | 定义 |
| R3 | `courtesy/childhood/studio/religious/posthumous/enfeoffment/bestowed_name` | 字 15~30 岁、小名 0~12 岁、室名 25~70 岁、法號道號 20~70 岁、諡號卒后 0~60 年、封爵/賜號在入仕之后 | `ALTNAME_CODES` 21 种名号类型 |
| R4 | `entry_age` / `entry_before_office` | 入仕在 12~60 岁；入仕早于首次任官 0~45 年 | 科举与铨选常识 |
| R5 | `kin_ascendant/descendant/affinal` | 尊长关系成立于本人出生前 0~60 年；卑幼在出生后 12~70 年；姻親在 15~70 年 | `KINSHIP_CODES.c_upstep / c_dwnstep / c_marstep` |
| R6 | `office_sequence` | 相邻两任官职相隔 0~30 年（**只对真正带 `c_sequence` 的任官**） | `POSTED_TO_OFFICE_DATA.c_sequence` |
| R7 | `posting_addr_sync` | 任職地跟随同年（±2 年）的任官 | `POSTING_DATA` |
| R8 | `sequence_order` | 同阶段内 `c_sequence` 相邻两条相隔 0~40 年 | 录入序号 |

**三条防止「过度推理」的设计**：

1. **硬锚点锁定** —— 数据直接给了确切公历年的记录（`time_precision='year'`）标记 `locked=1`，**只允许它影响别人，不允许被别人改写**。第一版没做这件事，结果把王安石的出生年从 1021 推成了 1010。
2. **冲突回退而非静默折叠** —— 传播后若 `lo > hi`，说明数据自相矛盾（比如某人 1050 年任官却生于 1060 年），**回退到先验区间并打标记**，绝不折叠成一个假年份。全库这类记录约 0.5%，它们本身就是脏数据的线索。
3. **规则外置可调** —— 所有年龄区间、误差幅度都是脚本顶部的常量，想「胆子大一点」或「保守一点」改常量即可，不用动算法。

#### 6.8.3 用同伴锚点补上最大的窟窿

光有 R1–R8 对最大的两块无效：**交遊（占 top500 事件的 62%）和著作（98% 完全无约束）**，因为它们既无年份也无序号，只能落回整段人生框架。解决办法是**借对方的生命窗口**：

```
交遊 A→B 的年份  ∈  [A生年, A卒年] ∩ [B生年 − 10, B卒年 + 10]
                 （B 无生卒时退化为 [B.index_year − 30, B.index_year + 30]）
亲属 A→B 的年份  ∈  [A生年, A卒年] ∩ [B生年, B卒年]
```

⚠️ **`index_year ± 45` 是个陷阱**：45 年×2 = 90 年，比典型寿命（65 年）还宽，跟人生框架求交集**等于没约束**。这就是为什么必须收到 ±30 才看得到效果（见下表）。

#### 6.8.4 实测：每加一条规则收窄多少

在 **top 500 人（104,729 条事件，209,916 条约束边）** 上逐项 A/B：

| 版本 | 平均最终区间宽 | ≤50 年的窄区间 | 被传播收窄的事件 | 约束违反 |
|---|---:|---:|---:|---:|
| 基线（只用人生框架 + R1–R8） | 77.3 年 | 29,747 | 13,427 (12.8%) | 1,185 |
| + 亲属本人生卒锚点 | 77.1 年 | 30,255 | 12,534 (12.0%) | **966** |
| + 交遊对方锚点（±45） | 70.2 年 | 42,718 | 12,399 (11.8%) | 1,000 |
| + 锚点收紧到 ±30、身份/著作加成年下限（**当前默认**） | **67.6 年** | **45,516** | 13,629 (13.0%) | 1,006 |

净效果：平均区间 **77.3 → 67.6 年（收窄 12.6%）**，窄区间（≤50 年）**29,747 → 45,516 条（+53%）**，同时自相矛盾的记录从 1,185 降到 1,006。

**读这张表要注意的两点**：

- 亲属锚点那一档「收窄百分比」反而难看，是因为它把**先验区间**也收窄了，分母变小；看绝对指标（最终宽度、窄区间数）它是一直在改善的，而且它把矛盾数砍了 18%。
- 交遊对方锚点是**唯一有量级提升**的一条（42,718 vs 30,255）。因为它打的是最大的那一块。

#### 6.8.5 全库实测（637,985 人 / 3,006,222 条事件）

`--all --write` 跑完 **2 分 37 秒**，生成 2,684,768 条约束边：

| 指标 | 传播前 | 传播后 |
|---|---:|---:|
| 平均区间宽度 | 512.0 年 | **407.3 年**（收窄 20.5%） |
| ≤50 年的窄区间 | 1,095,775 | **1,459,052**（+363,277，+33%） |
| 约束违反（数据自相矛盾） | — | 18,814（0.63%，已回退保留原区间） |

精度轴分布：**exact 861,352 (28.7%) / propagated 587,672 (19.5%) / interval 1,179,607 (39.2%) / frame 377,591 (12.6%)**。

各阶段的「时间可解性」——这张表直接告诉你哪一类事件能定年、哪一类不能：

| 阶段 | 事件数 | 原平均宽 | 现平均宽 | 被收窄的比例 |
|---|---:|---:|---:|---:|
| 入仕 | 265,037 | 1249.4 | **170.0** | **52.7%** ← 收益最大 |
| 名號 | 208,878 | 767.0 | 741.2 | 42.1% |
| 親屬 | 562,953 | 252.5 | 238.8 | 31.3% |
| 身份 | 73,571 | 1135.1 | 1128.0 | 28.2% |
| 任官 | 591,683 | 140.5 | 120.4 | 17.6% |
| 地理 | 461,830 | 1086.7 | 1082.4 | 6.9% |
| 任職地 | 465,390 | 347.4 | 345.6 | 5.0% |
| 著作 | 53,354 | 772.3 | 768.6 | 4.1% |
| 機構 / 事件 / 財產 | 1,058 | — | — | 0~3.5% |
| **交遊** | **190,064** | 174.4 | 173.0 | **2.4%** ← 最难啃 |
| 生 / 卒 | 132,404 | 0.4 | 0.3 | —（本来就是精确值） |

**入仕为什么收益最大**：它自己没年份，但被 `entry_before_office`（入仕早于任官 0~45 年）和 `entry_age`（12~60 岁）两头夹住——只要这个人有**任何一条有年份的任官记录**，入仕年份就被锁进 45 年窗口。

**交遊为什么最难**：`ASSOC_DATA` 91.7% 无年份，而对方人物自己也多半没生卒年（全库只有 9% 有生年），能借的锚点太少。

#### 6.8.6 产物：`LIFE_EVENT_RESOLVED`

```bash
python scripts/life_order.py --db cbdb_20260926.sqlite3 --person 1762      # 单人多打印
python scripts/life_order.py --db cbdb_20260926.sqlite3 --top 500 --write  # 物化前 500 人
python scripts/life_order.py --db cbdb_20260926.sqlite3 --all --write      # 物化全库
python scripts/life_order.py --db cbdb_20260926.sqlite3 --top 500 --no-peer-anchor  # A/B 对照
```

| 列 | 说明 |
|---|---|
| `c_personid`, `order_rank` | 人物 + **序轴**（拓扑排序得到的纯先后序号，不含年份） |
| `stage_no`, `stage`, `event_label`, `counterpart_name_chn` | 事件本身 |
| `time_precision` | 视图给的六级精度（输入） |
| `prior_lo/hi/width` | 传播**前**的先验区间 |
| `lo/hi/width` | 传播**后**的区间轴（输出） |
| `narrowed` | 收窄了多少年 |
| `precision` | 精度轴：`exact`(0) / `propagated`(被推理收窄) / `interval`(仍是区间) / `frame`(只剩人生框架) |
| `conflict` | 1 = 约束自相矛盾，已回退 |
| `locked` | 1 = 数据本身的硬年份，未被改写 |
| `frame_src` | 人生框架来源：`birth_death` / `index_year` / `fallback` |

**用法**：把 `View_PersonLifeTimeline` 换掉，按区间排序即可，宽区间自动沉底：

```sql
SELECT order_rank, stage, lo, hi, width, precision, event_label
FROM LIFE_EVENT_RESOLVED WHERE c_personid = 1762
ORDER BY lo, width, order_rank;
```

王安石（`c_personid = 1762`，794 条事件）的真实输出片段——注意父母被正确地推到出生**之前**，而原先那些「999 年」的噪声交遊被夹进了人生区间：

```
[967,1021]   親屬  王貫之（從祖;伯叔祖）
[993,1021]   親屬  王益（父）
[998,1021]   親屬  吳氏(王益妻)（母）
999          交遊  李興：為Y作神道碑
1021         生    出生
[1021,1022]  交遊  陳執古：為Y作墓誌銘
[1021,1027]  交遊  王師錫：為Y作墓誌銘
...
1086         卒    卒（享年66）
[1086,1146]  名號  文（諡號）
```

他这一生：exact 196 条 / propagated 47 条 / interval 551 条（平均宽 50.4 年）。

#### 6.8.7 一个必须知道的性能坑（已修）

`View_PersonLifeTimeline` 是 **14 张表的 `UNION ALL`**，SQLite **无法把 `WHERE c_personid = ?` 下推到各分支用索引**。逐人查询等于**每人全表扫 300 万行**——实测 ~100 ms/人，63.8 万人需要 **17.8 小时**，跑 28 分钟才处理了 16,484 人（2.6%）。

修法：全库模式改为「**预加载 + 有序流式扫描**」（`preload()` + `iter_event_chunks()`）：

1. `BIOG_MAIN` 生卒/`index_year`、`KIN_DATA`、`ASSOC_DATA` 一次性读进内存（3 个大查询）
2. 事件用 `WHERE c_personid >= ? ORDER BY c_personid LIMIT 50000` 分块取，块尾那个人的记录留到下一块重取（单人最多 2,705 条，远小于块大小）
3. 全程不落全量事件，内存受块大小限制

→ **2 分 37 秒，快了约 400 倍**。

> 这条坑对本项目所有 `UNION ALL` 视图都成立（`View_TextAssociationData` 219 万行同理）：**别在 UNION ALL 视图上做逐主键的点查询，要么一次性排序扫描，要么直接查底表。**

#### 6.8.8 还剩什么没解决

| 残障 | 现状 | 能不能再修 |
|---|---|---|
| **33 万人连 `index_year` 都没有** | `frame_src='fallback'` 330,132 人，区间被拉到 2,800 年 | 只能靠**跨人物联合求解**（见下） |
| 交遊收窄率只有 2.4% | 对方人物自己也多半没生卒年 | 同上，单人范围内已到天花板 |
| 著作几乎无约束 | `BIOG_TEXT_DATA` 无任何时间、无对方人物 | 只能靠「成年后 + 死后 40 年」的常识框 |
| 年内顺序 | 月/日覆盖率 < 0.3% | **无法修复**，数据里没有 |
| 亲属关系本身 | `KIN_DATA` 0% 有年份 | 只能靠世代与对方生卒，不能凭空产生年份 |

**下一步如果还要继续**：把 STP 从「单人」推广到「**跨人物联合求解**」——把每个人的生卒年也当成变量，用亲属边（世代间隔 20~40 年/代）和交遊边（同代 ±80 年）把 66 万人连成一张约束图做全局弧一致性传播。目标很明确：**让 33 万 `fallback` 的人借亲属/交遊对象反推出人生框架**，直接攻击「只有 9% 的人有生年、12.6% 的记录只剩框架」这个根子上的缺口。取数层的批量化已经做完了，剩下的只是把变量从「事件」扩到「人 + 事件」。

---

## 七、陷阱与注意事项

| # | 陷阱 | 后果 / 对策 |
|---|---|---|
| 1 | **人物 ID 重复** | 5,994 条合并记录。统计前用 `MERGED_PERSON_DATA` 把 `c_merged_from_personid` 映射到 `c_personid` |
| 2 | **只筛公历年会漏数据** | 大量记录只有年号没有公历年。要么用 `c_index_year`（每人必有一个），要么联合 `c_*_nh_code` + `c_*_range` 判断 |
| 3 | **地址 ID 不能跨朝代复用** | 同一个「吳縣」有多个 `c_addr_id`。跨朝代比较必须限定年份区间，或走 `ADDRESSES` 的 `belongs*` 层级 |
| 4 | **亲属关系是单向的** | 「A 有 B 为父」不代表库里有「B 有 A 为子」。建网络要双向补全 |
| 5 | **关系表会扇出** | 一次 posting 可能对应多行 office / addr。`COUNT(*)` 得到的是「任职条数」不是「人数」，统计人数要用 `COUNT(DISTINCT c_personid)` |
| 6 | **空表 / 微量表** | `ADMIN_CAT_TYPES`(0)、`ADMIN_CAT_CODE_TYPE_REL`(0)、`SOCIAL_INSTITUTION_ALTNAME_DATA`(0) 是空的；财产(60)、事件(427)、机构(571) 数据量极小，不足以做定量分析 |
| 7 | **大表别全表扫描** | `BIOG_SOURCE_DATA` 125 万行、`BIOG_MAIN` 66 万行。DBeaver 里务必加 `LIMIT`，或先 `COUNT(*)` 看看量级 |
| 8 | **空值编码不是 NULL** | CBDB 用 `-1` / `0` 表示「缺失/未詳」（如 `c_addr_type = -1` 是 `[Missing Data]`）。`WHERE x IS NOT NULL` 挡不住它们，要显式排除 `x > 0` |
| 9 | **ADDRESSES 表有 444 条脏数据被剔除** | 建表时 37,180 条 belongs 里有 444 条时间区间非法（如起始年 > 结束年），已跳过。地址层级分析有约 1.2% 的缺口 |
| 10 | **视图是只读的** | 23 个视图都是 `CREATE VIEW`，不能 INSERT/UPDATE。要改数据请改底表 |
| 11 | **`View_CountyPeopleData` 的层级是「代表性」的** | `ADDRESSES` 每个 `c_addr_id` 平均有 2.14 条隶属记录（按时段），直接 JOIN 会让人物翻倍。该视图已按「优先覆盖人物索引年的时段，否则取存续最长的时段」挑选**单条**层级，因此一人一行。需要逐时段精确层级时请直查 `ADDRESSES` |
| 12 | **`View_TextAssociationData` 是全库 UNION** | 219 万行，务必先 `WHERE c_source = <textid>` 再查 |
| 13 | **`sort_year` 不代表「此人的年份」** | `View_PersonLifeTimeline` 里 `anchor` 级的 `sort_year` 取的是**关联对象**的年份（亲属用对方 `c_index_year`，著作用 `TEXT_CODES.c_text_year`）。实测王安石年谱里混入「999 年 李興為Y作神道碑」这类早于其生年的记录。做年代统计前先按 `time_precision` 过滤，或用 `BIOG_MAIN` 的生卒年做区间约束 |
| 14 | **多跳遍历会组合爆炸** | 以王安石为起点、只走 kinship+association：深度 1 = 1,370 条，深度 2 = 22.3 万条，深度 3 = **5,183 万条**。务必限深（≤3）、限边类型、限时间窗，否则查询跑不完 |
| 15 | **图的边要双向补全** | `KIN_DATA` / `ASSOC_DATA` 都是单向存储。只按 `src→dst` 走会漏掉一半关系，必须先 `UNION ALL` 反向边 |

---

## 八、附录：表清单速查（79 张，按行数降序）

| # | 表名 | 行数 | 主键 | 分类 |
|---:|---|---:|---|---|
| 1 | `BIOG_SOURCE_DATA` | 1,254,352 | c_personid, c_textid, c_pages | 人物 |
| 2 | `BIOG_MAIN` | 662,152 | c_personid | 人物 |
| 3 | `POSTED_TO_OFFICE_DATA` | 591,683 | c_office_id, c_posting_id | 任职 |
| 4 | `POSTING_DATA` | 591,652 | c_posting_id | 任职 |
| 5 | `KIN_DATA` | 562,953 | c_personid, c_kin_id, c_kin_code | 亲属 |
| 6 | `POSTED_TO_ADDR_DATA` | 465,390 | c_posting_id, c_office_id, c_addr_id | 任职 |
| 7 | `BIOG_ADDR_DATA` | 461,830 | c_personid, c_addr_id, c_addr_type, c_sequence | 地理 |
| 8 | `ENTRY_DATA` | 265,037 | c_personid, c_entry_code, c_sequence, c_kin_code, c_kin_id, c_assoc_code, c_assoc_id, c_year, c_inst_code, c_inst_name_code | 入仕 |
| 9 | `ALTNAME_DATA` | 208,878 | c_personid, c_alt_name_chn, c_alt_name_type_code | 人物 |
| 10 | `ASSOC_DATA` | 190,064 | c_assoc_code, c_personid, c_kin_code, c_kin_id, c_assoc_id, c_assoc_kin_code, c_assoc_kin_id, c_assoc_first_year, c_text_title | 社会关系 |
| 11 | `STATUS_DATA` | 73,571 | c_personid, c_sequence, c_status_code | 身份 |
| 12 | `ADDRESSES` | 64,347 | — | 地理 |
| 13 | `TEXT_CODES` | 62,378 | c_textid | 文本 |
| 14 | `BIOG_TEXT_DATA` | 53,354 | c_textid, c_personid, c_role_id | 人物 |
| 15 | `OFFICE_CODE_TYPE_REL` | 43,797 | c_office_id, c_office_tree_id | 任职 |
| 16 | `ADDR_BELONGS_DATA` | 37,180 | c_addr_id, c_belongs_to, c_firstyear, c_lastyear | 地理 |
| 17 | `OFFICE_CODES` | 34,176 | c_office_id | 任职 |
| 18 | `ADDR_CODES` | 30,160 | c_addr_id | 地理 |
| 19 | `TEXT_INSTANCE_DATA` | 9,817 | c_textid, c_text_edition_id, c_text_instance_id | 文本 |
| 20 | `MERGED_PERSON_DATA` | 5,994 | c_personid, c_merged_from_personid | 人物 |
| 21 | `SOCIAL_INSTITUTION_CODES` | 4,012 | c_inst_name_code, c_inst_code | 机构 |
| 22 | `SOCIAL_INSTITUTION_ADDR` | 3,859 | c_inst_name_code, c_inst_code, c_inst_addr_type_code, c_inst_addr_id, inst_xcoord, inst_ycoord | 机构 |
| 23 | `OFFICE_TYPE_TREE` | 2,742 | c_office_type_node_id | 任职 |
| 24 | `SOCIAL_INSTITUTION_NAME_CODES` | 2,603 | c_inst_name_code | 机构 |
| 25 | `NIAN_HAO` | 682 | c_nianhao_id | 代码表 |
| 26 | `BIOG_INST_DATA` | 571 | c_personid, c_inst_name_code, c_inst_code, c_bi_role_code | 机构 |
| 27 | `ASSOC_CODES` | 498 | c_assoc_code | 社会关系 |
| 28 | `ETHNICITY_TRIBE_CODES` | 498 | c_ethnicity_code | 代码表 |
| 29 | `KINSHIP_CODES` | 488 | c_kincode | 亲属 |
| 30 | `ASSOC_CODE_TYPE_REL` | 463 | c_assoc_code, c_assoc_type_code | 社会关系 |
| 31 | `EVENTS_DATA` | 427 | c_personid, c_sequence, c_event_code | 事件 |
| 32 | `STATUS_CODES` | 285 | c_status_code | 身份 |
| 33 | `STATUS_CODE_TYPE_REL` | 285 | c_status_code, c_status_type_code | 身份 |
| 34 | `ENTRY_CODE_TYPE_REL` | 284 | c_entry_code, c_entry_type | 入仕 |
| 35 | `ENTRY_CODES` | 273 | c_entry_code | 入仕 |
| 36 | `ADMIN_CAT_CODES` | 213 | c_admin_cat_code | 地理 |
| 37 | `CHORONYM_CODES` | 173 | c_choronym_code | 代码表 |
| 38 | `KIN_MOURNING` | 159 | c_kinrel | 亲属 |
| 39 | `KIN_MOURNING_STEPS` | 159 | c_kinrel | 亲属 |
| 40 | `TEXT_BIBLCAT_CODES` | 144 | c_text_cat_code | 文本 |
| 41 | `TEXT_BIBLCAT_CODE_TYPE_REL` | 144 | c_text_cat_code, c_text_cat_type_id | 文本 |
| 42 | `TEXT_TYPE` | 126 | c_text_type_code | 文本 |
| 43 | `EVENT_CODES` | 117 | c_event_code | 事件 |
| 44 | `APPOINTMENT_CODES` | 116 | c_appt_code | 任职 |
| 45 | `APPOINTMENT_CODE_TYPE_REL` | 109 | c_appt_type_code, c_appt_code | 任职 |
| 46 | `DYNASTIES` | 85 | c_dy | 代码表 |
| 47 | `POSSESSION_ADDR` | 62 | c_possession_record_id, c_personid, c_addr_id | 财产 |
| 48 | `GANZHI_CODES` | 61 | c_ganzhi_code | 代码表 |
| 49 | `POSSESSION_DATA` | 60 | c_possession_record_id | 财产 |
| 50 | `TEXT_BIBLCAT_TYPES` | 51 | c_text_cat_type_id | 文本 |
| 51 | `ASSOC_TYPES` | 45 | c_assoc_type_code | 社会关系 |
| 52 | `HOUSEHOLD_STATUS_CODES` | 34 | c_household_status_code | 代码表 |
| 53 | `SCHOLARLYTOPIC_CODES` | 32 | c_topic_code | 社会关系 |
| 54 | `INDEXYEAR_TYPE_CODES` | 31 | c_index_year_type_code | 代码表 |
| 55 | `ENTRY_TYPES` | 29 | c_entry_type | 入仕 |
| 56 | `BIOG_INST_CODES` | 26 | c_bi_role_code | 机构 |
| 57 | `BIOG_ADDR_CODES` | 22 | c_addr_type | 地理 |
| 58 | `ALTNAME_CODES` | 21 | c_name_type_code | 人物 |
| 59 | `OFFICE_CATEGORIES` | 15 | c_office_category_id | 任职 |
| 60 | `STATUS_TYPES` | 14 | c_status_type_code | 身份 |
| 61 | `APPOINTMENT_TYPES` | 13 | c_appt_type_code | 任职 |
| 62 | `LITERARYGENRE_CODES` | 12 | c_lit_genre_code | 社会关系 |
| 63 | `TEXT_ROLE_CODES` | 12 | c_role_id | 文本 |
| 64 | `COUNTRY_CODES` | 11 | c_country_code | 文本 |
| 65 | `OCCASION_CODES` | 10 | c_occasion_code | 社会关系 |
| 66 | `KINREL_REDUCTION` | 8 | c_kinrel_target, c_sex | 亲属 |
| 67 | `MEASURE_CODES` | 7 | c_measure_code | 财产 |
| 68 | `PARENTAL_STATUS_CODES` | 7 | c_parental_status_code | 入仕 |
| 69 | `SOCIAL_INSTITUTION_TYPES` | 7 | c_inst_type_code | 机构 |
| 70 | `ASSUME_OFFICE_CODES` | 6 | c_assume_office_code | 任职 |
| 71 | `YEAR_RANGE_CODES` | 6 | c_range_code | 代码表 |
| 72 | `EVENTS_ADDR` | 4 | c_event_code, c_personid, c_sequence, c_addr_id | 事件 |
| 73 | `EXTANT_CODES` | 4 | c_extant_code | 文本 |
| 74 | `POSSESSION_ACT_CODES` | 4 | c_possession_act_code | 财产 |
| 75 | `SOCIAL_INSTITUTION_ADDR_TYPES` | 2 | c_inst_addr_type_code | 机构 |
| 76 | `SOCIAL_INSTITUTION_ALTNAME_CODES` | 1 | — | 机构 |
| 77 | `ADMIN_CAT_CODE_TYPE_REL` | 0 | c_admin_cat_code, c_admin_cat_type_code | 地理 |
| 78 | `ADMIN_CAT_TYPES` | 0 | c_admin_cat_type_code | 地理 |
| 79 | `SOCIAL_INSTITUTION_ALTNAME_DATA` | 0 | — | 机构 |

> 行数取自 `cbdb_20260926.sqlite3` 实时统计。空表（0 行）表示该模块尚未录入数据：`ADMIN_CAT_TYPES`、`ADMIN_CAT_CODE_TYPE_REL`、`SOCIAL_INSTITUTION_ALTNAME_DATA`。

## 九、延伸阅读

- 官方表结构说明：https://cbdb.hsites.harvard.edu/structure-cbdb
- 官方 Codebook（逐表逐字段）：https://docs.qq.com/sheet/DYkJGbVRBdUhUcHhO
- 索引年计算规则：https://cbdb.hsites.harvard.edu/sites/g/files/omnuum3101/files/cbdb/files/20200603_rules_for_index_years_20230911.xlsx
- CBDB API（在线查询，可对照验证）：https://projects.iq.harvard.edu/chinesecbdb/cbdb-api
- 官方视图定义源码：`scripts/create_views.sh`（18 个视图的完整 SQL 都在这里）
- **本项目新增的 5 个分析型视图**：`scripts/create_custom_views.sh`（族谱 / 县城 / 单本文献 / 生平年谱 / 关系图谱，幂等可重复执行）
- 本仓库的 schema 导出工具：`scripts/dump_schema.py`（本报告的数据来源，可随时重新生成）
