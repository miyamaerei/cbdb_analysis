# CBDB 知识图谱本体设计研究（Owlready2 路线）

> 目标：把 `cbdb_20260926.sqlite3`（80 表 + 23 视图）建模为 OWL 2 本体，用 Owlready2 实现。
> 本文只给**研究结论与设计方案**，不含实现代码。公理用 Manchester Syntax 风格表述。
> 数据依据：`analysis/profile_overview.md`（80 表逐列密度）、`analysis/profile_fk.md`（38 组外键完整性），由 `scripts/profile_tables.py` 实测生成（2026-09-29）。

---

## 0. 一句话结论

**CBDB 的连边质量极高（人物外键 100%、码表外键 99.9%+），非常适合建图；真正的瓶颈不是关系而是时间（生年 9%、交遊年份 8.3%），且全量约 7,100 万三元组超出 Owlready2 单机甜点区，需要「种子子集验证 + 全量外置 store」两段式落地。**

---

## 1. 数据体检结果（任务 1 交付）

### 1.1 密度分层（80 表实测）

| 层 | 特征 | 代表表 | 建模含义 |
|---|---|---|---|
| **码表层** | 非空率 ≈100% | 全部 `*_CODES` / `*_TYPES` / `*_CODE_TYPE_REL`、`DYNASTIES`、`NIAN_HAO` | 直接转类层级 / 枚举个体，质量无忧 |
| **核心事实表** | 40%–70% | `KIN_DATA` 64.6%、`ASSOC_DATA` 53.6%、`ENTRY_DATA` 58.8%、`POSTED_TO_OFFICE_DATA` 47.7%、`BIOG_ADDR_DATA` 40.1% | 主键外键全满、可选属性稀疏 → 主边可信，属性按需挂 |
| **稀疏主表** | 33%–40% | `BIOG_MAIN` 39.7%（55 列中 23 列 <10%）、`POSTING_DATA` 33.8% | 数据属性要分层：核心属性（姓名/性别/朝代）必建，稀疏属性（郡望/族属/户籍）做成「有则挂」 |
| **空表 3 张** | 0 行 | `ADMIN_CAT_TYPES`、`ADMIN_CAT_CODE_TYPE_REL`、`SOCIAL_INSTITUTION_ALTNAME_DATA` | **本体中不建对应结构** |

### 1.2 外键完整性：连边质量极高

实测 38 组 FK（`analysis/profile_fk.md`）：

- **人物锚点全绿**：所有事实表的 `c_personid` → `BIOG_MAIN` 覆盖率 **100%，孤儿 0**。这是建图最关键的一条——所有边都能落到真实人物节点上。
- **类型化极干净**：`KIN_DATA.c_kin_code`→`KINSHIP_CODES` 99.94%、`ASSOC_DATA.c_assoc_code` 99.96%、`ENTRY_DATA.c_entry_code` 100%、`STATUS_DATA.c_status_code` 99.99%、`POSTED_TO_OFFICE_DATA.c_office_id` 99.92%。
- 两个「看似异常实为预期」：
  - `MERGED_PERSON_DATA.c_merged_from_personid` 只有 1.23% 在主表——**这正是该表的意义**：5,920 个被并掉的旧 ID 已不在主表，图谱加载时必须先做 ID 归一映射（旧 ID → 新 ID 建 `owl:sameAs` 或直接改写）。
  - `EVENTS_DATA.c_event_code` 仅 17.1% 有效（354/427 是 0 值）——事件模块本就边缘，归入低优先级。

### 1.3 三个建模前必须处理的语义陷阱

| 陷阱 | 实测数字 | 建模规则 |
|---|---|---|
| **0 = 未知**（CBDB 惯例） | `ENTRY_DATA.c_year` 非空 100%，但 **>0 仅 37.9%**；`POSTED_TO_OFFICE_DATA.c_firstyear` 非空 72.4%，>0 仅 **52.6%**；`ASSOC_DATA.c_assoc_first_year` 非空 100%，>0 仅 **8.3%**；`BIOG_MAIN` 的郡望/族属/户籍码 0 值占 60%+ | ETL 规则：**0 与 NULL 一律不生成三元组**。否则图谱里会堆满指向「未知」的垃圾边 |
| **生卒年极稀疏** | 生年 >0 仅 **9.0%**（59,838）、卒年 **10.8%**（71,279），但 `c_index_year` 覆盖 **46.5%** | 时间属性设计成三级：`birthYear`（9%）≺ `floruitStart/End`（c_fl_*）≺ `indexYear`（46.5%，来自 INDEXYEAR_TYPE 推导规则，本身就是"推断值"，标注 `indexYearType` 个体） |
| **关系单向存储** | `KIN_DATA` 562,953 行单向（「A 视 B 为某亲」）；去重后对子数 560,981 | 对象属性必须显式声明逆属性（如 `hasKin` / `kinOf`），或加载时按 `KINSHIP_CODES` 的配对码（c_kincode ↔ c_pair_kincode）补反向边 |

### 1.4 各表建图价值分级

| 级 | 表 | 角色 |
|---|---|---|
| **S（骨架）** | `BIOG_MAIN`、`KIN_DATA`、`ASSOC_DATA`、`ENTRY_DATA`、`POSTED_TO_OFFICE_DATA`、`POSTED_TO_ADDR_DATA`、`BIOG_ADDR_DATA`、`ADDR_CODES`、`ADDRESSES` | 五类核心断言 + 地址层级，构成图的主干 |
| **A（增强）** | `TEXT_CODES`、`BIOG_TEXT_DATA`、`BIOG_SOURCE_DATA`、`STATUS_DATA`、`ALTNAME_DATA`、`MERGED_PERSON_DATA` | 著述/史料/身份/别名/归一 |
| **B（边缘，可后补）** | `SOCIAL_INSTITUTION_*`（4 千机构）、`EVENTS_DATA`（427 行）、`POSSESSION_*`（60 行）、`BIOG_INST_DATA`（571 行） | 数据量太小，Phase 2 之后再挂 |
| **C（码表）** | 其余 ~45 张 `_CODES/_TYPES/_REL` | 转成类层级/枚举个体，**不是实例数据** |
| **不建** | 3 张空表、`KINREL_REDUCTION`（统计规则表）、`POSTING_DATA`（纯发号，并入 `OfficeTenure`）、`LIFE_EVENT_RESOLVED`（自建推导产物，可选单挂为注释层） | — |

---

## 2. 本体总体架构

### 2.1 IRI 与命名空间

```
cbdb:   http://cbdb.example.org/ontology#   ← TBox（类、属性）
cbdbi:  http://cbdb.example.org/id/         ← ABox（实例）
  cbdbi:person/1722        (BIOG_MAIN.c_personid)
  cbdbi:place/101051       (ADDR_CODES.c_addr_id)
  cbdbi:office/1253        (OFFICE_CODES.c_office_id)
  cbdbi:text/1006          (TEXT_CODES.c_textid)
  cbdbi:kin/562953-1       (KIN_DATA 行级断言，无自然主键 → 用行号或 (person,kin,code) 哈希)
  cbdbi:tenure/591683-1
  cbdbi:entry/265037-1
  cbdbi:assoc/190064-1
```
双标签：每个类/属性/个体挂 `rdfs:label "xxx"@zh` + `"xxx"@en`（CBDB 码表自带中英双语列，直接映射）。

### 2.2 核心决策：关系必须实例化（n-ary / reification）

CBDB 的关系记录**全都带属性**：亲属带来源文献（`c_source`）、交遊带地点/场合/文体/学术主题、任职带起止年/任命类型/是否赴任、入仕带年份/名次/年龄。OWL 的二元对象属性挂不住这些，因此：

> **五种核心关系一律建模为「断言/事件类」实例（hub 节点），人物之间只保留一条「便捷直边」用于图遍历。**

| 断言类 | 来源表 | 中心属性 | 便捷直边（冗余但好用） |
|---|---|---|---|
| `KinshipAssertion` | KIN_DATA | `kinSource`→Person, `kinTarget`→Person, `kinType`→KinType 个体, `kinSourceText`→Text | `hasKin`（对称展开） |
| `AssociationEvent` | ASSOC_DATA | `assocFrom`/`assocTo`→Person, `assocType`, `assocPlace`, `assocOccasion`, `assocTopic`, `assocGenre`, `assocFirstYear` | `hasAssociate` |
| `OfficeTenure` | POSTED_TO_OFFICE_DATA+POSTED_TO_ADDR_DATA | `tenureHolder`→Person, `tenureOffice`→Office, `tenurePlace`→Place, `apptType`, `assumeStatus`, `firstYear/lastYear/sequence` | `heldOffice` |
| `EntryRecord` | ENTRY_DATA | `entryPerson`→Person, `entryMode`→EntryMode, `entryYear`, `examRank`, `examField`, `age`, `parentalStatus` | `enteredVia` |
| `AddressClaim` | BIOG_ADDR_DATA | `addrPerson`→Person, `addrPlace`→Place, `addrKind`（22 种：籍貫/遷住/葬地…）, `firstYear/lastYear` | `hasAddress` |

另加两个轻量断言：`TextRoleLink`（BIOG_TEXT_DATA：人-书-角色）、`StatusPeriod`（STATUS_DATA：身份+起止年）。

### 2.3 码表 → OWL 的三种映射策略

| 策略 | 适用 | CBDB 落点 |
|---|---|---|
| **层级码表 → 子类层级** | 码表有父子结构 | `OFFICE_TYPE_TREE`（2,742 节点）→ `OfficeType` 子类树；`ENTRY_TYPES`（宮廷門⊃科舉門⊃進士…）→ `EntryMode` 子类；`TEXT_BIBLCAT_TYPES`（經部⊃易類…）→ `TextCategory` 子类 |
| **小枚举 → 命名个体 + oneOf** | <30 个值、封闭 | `ASSUME_OFFICE_CODES`（6 值）→ `AssumeStatus ≡ {赴任, 辭不就, 未赴任而卒, 未赴任而改命, 未赴任, 未詳}`；`PARENTAL_STATUS_CODES`（7 值）、`EXTANT_CODES`（4 值）、`YEAR_RANGE_CODES`（6 值）同理 |
| **大字典 → 携带度量的个体** | 百级取值 + 自带属性列 | 488 个 `KINSHIP_CODES` → `KinType` 个体，挂数据属性 `upStep/dwnStep/colStep/marStep`（推理亲属距离的燃料）；498 `ASSOC_CODES` → `AssocType` 个体（带 `pairCode` 指配对关系） |

### 2.4 为什么不直接用现成方案（工具对比）

| 路线 | 说明 | 适用性 |
|---|---|---|
| **Owlready2（选定）** | Python 原生建 OWL，SQLite quadstore，HermiT/Pellet 推理（需 Java），RDFlib SPARQL | 本体设计与种子子集验证的最佳体验 |
| 纯 RDFLib | 只有 RDF 无 OWL 公理推理，类层级全靠手查 | 失去等价类/约束推理的价值，不推荐 |
| 直接灌 GraphDB/Jena | 跳过本体设计，视图当 ETL | 推理弱（GraphDB Free 仅 RDFS+部分 OWL-Horst），等价类用不了 |
| 官方资源 | CBDB 提供 API/下载，**无官方 OWL 本体**（见使用报告 §1.2） | 无现成可抄，必须自建 |

---

## 3. 类层级（Class / SubClassOf）

```
owl:Thing
├── Agent
│   ├── Person                 ← BIOG_MAIN（662,152 实例；Female/Male 子类见 §8）
│   └── Institution            ← SOCIAL_INSTITUTION_CODES（4,012）
│       ├── Academy            (書院)   ├── BuddhistTemple (佛寺)
│       ├── DaoistTemple (道觀)  └── PoetryClub/Shrine/Temple…(SOCIAL_INSTITUTION_TYPES 7 值 → 子类)
├── Place                      ← ADDR_CODES（30,160；行政单位实例）
│   └── (按 ADMIN_CAT_CODES 213 类细分，可选)
├── Office                     ← OFFICE_CODES（34,176，官职词条）
├── OfficeType                 ← OFFICE_TYPE_TREE 层级（2,742 子类节点）
├── EntryMode                  ← ENTRY_TYPES/ENTRY_CODES 层级（科舉門⊃進士…）
├── Text                       ← TEXT_CODES（62,378）
│   └── (TEXT_BIBLCAT_TYPES 51 大类 → 子类)
├── SocialStatus               ← STATUS_CODES（285 身份词条 → 个体；STATUS_TYPES 14 大类 → 子类）
├── KinType / AssocType        ← 个体容器类（488 / 498 个体，带度量数据属性）
├── Assertion（断言超类）
│   ├── KinshipAssertion   (562,953)
│   ├── AssociationEvent   (190,064)
│   ├── OfficeTenure       (591,683)
│   ├── EntryRecord        (265,037)
│   ├── AddressClaim       (461,830)
│   ├── TextRoleLink       (53,354)
│   └── StatusPeriod       (73,571)
├── TemporalEntity
│   ├── Dynasty (85)  ├── NianHao (682)  └── GanzhiYear (61)
├── Event (427) / Possession (60)   ← B 级，后挂
└── Enumeration 容器：AssumeStatus / ParentalStatus / ExtantStatus / OccasionType / LiteraryGenre / TopicType
```

---

## 4. 属性设计

### 4.1 对象属性（核心 18 条）

| 属性 | domain → range | 特性 | 来源 |
|---|---|---|---|
| `kinSource` / `kinTarget` | KinshipAssertion → Person | 各 exactly 1 | KIN_DATA.c_personid / c_kin_id |
| `kinType` | KinshipAssertion → KinType | functional | c_kin_code |
| `kinSourceText` | Assertion → Text | — | c_source（KIN 100% 有值） |
| `hasKin` | Person → Person | **inverseOf kinOf；非对称**（父子≠子父） | 便捷直边 |
| `marriedTo` | Person → Person | **symmetric** | kinType ∈ 配偶类时推导/抽取 |
| `hasAncestor` | Person → Person | **transitive**（由 upstep≥1 链推导，可选） | KINSHIP 度量推导 |
| `assocFrom` / `assocTo` | AssociationEvent → Person | 各 exactly 1 | ASSOC_DATA |
| `hasAssociate` | Person → Person | inverse 对 | 便捷直边 |
| `tenureHolder` / `tenureOffice` / `tenurePlace` | OfficeTenure → Person/Office/Place | functional | POSTED_TO_* |
| `heldOffice` | Person → OfficeTenure | inverse tenureHolder | — |
| `officeType` | Office → OfficeType | — | OFFICE_CODE_TYPE_REL |
| `officeCategory` | OfficeTenure → OfficeCategory 个体 | — | OFFICE_CATEGORIES 15 值 |
| `entryPerson` / `entryMode` | EntryRecord → Person/EntryMode | functional | ENTRY_DATA |
| `addrPerson` / `addrPlace` / `addrKind` | AddressClaim → Person/Place/AddrKind | functional | BIOG_ADDR_DATA |
| `belongsTo` | Place → Place | **transitive**（行政层级，来自 ADDRESSES belongs1..5 展开） | ADDRESSES |
| `hasCoord` → 拆数据属性 x/y | Place → xsd:float | — | ADDR_CODES.x_coord |
| `textAuthor`/`textRole` | TextRoleLink → Person/Text + `roleType`→RoleType 个体 | — | BIOG_TEXT_DATA |
| `sourceOf` | BIOG_SOURCE_DATA → Person/Text | — | 史料溯源 |
| `instAddress` | Institution → Place | — | SOCIAL_INSTITUTION_ADDR |
| `samePersonAs` | Person → Person | **用 owl:sameAs 或自定义 + 加载期归一** | MERGED_PERSON_DATA |

### 4.2 数据属性（按覆盖率取舍，0 值不落图）

| 属性 | domain | range | 覆盖率 | 决策 |
|---|---|---|---|---|
| `personId` | Person | xsd:int | 100% | exactly 1，IRI 对齐 |
| `nameChn` / `namePinyin` | Person | xsd:string | 100% / ~100% | 标签+检索双挂 |
| `isFemale` | Person | xsd:boolean | 96.3% | 落图；缺值不补 |
| `birthYear` / `deathYear` | Person | xsd:gYear | **9.0% / 10.8%** | 有则挂，max 1 |
| `indexYear` + `indexYearType` | Person | xsd:int + 个体 | 46.5% | 主时间锚点 |
| `floruitStart/End` | Person | xsd:int | c_fl_* 区间 | 兜底时间窗 |
| `dynastyOf`（对象属性→Dynasty） | Person | Dynasty | 99.8% | 高价值分期维度 |
| `firstYear/lastYear/sequence` | OfficeTenure | xsd:int | 52.6%有效 / 46.8% / 61.2% | sequence 是年内排序的关键 |
| `entryYear/examRank/age` | EntryRecord | int/int/int | 37.9% / 41.5% / 10.6% | — |
| `assocFirstYear` | AssociationEvent | xsd:int | **8.3%** | 有则挂，别指望 |
| `upStep/dwnStep/colStep/marStep` | KinType | xsd:int | KINSHIP_CODES 93.1% 密度 | 亲属距离推理燃料 |
| `textTitle/textYear` | Text | string/int | TEXT_CODES 49.6% 密度 | — |
| `belongsFirstYear/LastYear` | belongsTo 边上→ 拆 `PlaceBelonging` 断言类 | int | ADDRESSES 66.8% | 带时间的行政隶属（如需精确） |

---

## 5. 等价类（EquivalentClasses，推理机的核心价值）

```
Official        ≡ Person ⊓ (∃tenureHolder⁻¹.OfficeTenure)          # 有任官记录的人（~按 POSTING 覆盖自动归类）
JinshiHolder    ≡ Person ⊓ (∃entryPerson⁻¹.(EntryRecord ⊓ (∃entryMode.JinshiMode)))
SongPerson      ≡ Person ⊓ (∃dynastyOf.{宋})                        # 或按 indexYear ∈ [960,1279] 的区间定义
JinshiOfficial  ≡ JinshiHolder ⊓ Official                          # 自动交集归类
PersonWithKin   ≡ Person ⊓ (∃kinSource.KinshipAssertion)
```
意义：这些类**不写死成员**，由 HermiT 推理自动归类——本体建好后 `jinshiOfficials = list(JinshiOfficial.instances())` 直接出结果，等价于一次复杂 SQL，但语义可复用。
⚠️ 代价：HermiT 对百万级实例做全量归类不现实 → 等价类推理只在**种子子集**上跑（见 §11）。

## 6. 基数约束与属性约束

| 约束 | 公理 | 作用 |
|---|---|---|
| exactly 1 | `Person SubClassOf hasPersonId exactly 1 xsd:int` | 数据完整性校验（推理机可报不一致） |
| exactly 1 | `KinshipAssertion SubClassOf (kinSource exactly 1 Person) ⊓ (kinTarget exactly 1 Person) ⊓ (kinType exactly 1 KinType)` | 断言类三要素强制 |
| max 1 | `Person SubClassOf birthYear max 1 xsd:gYear` | 函数性：一生只有一个生年 |
| some | `OfficeTenure SubClassOf tenureOffice some Office` | 任职必挂官职（0 值行在 ETL 已被剔除，与约束自洽） |
| only | `AssociationEvent SubClassOf assocPlace only Place` | range 限定 |
| value | `SongJinshi ≡ JinshiHolder ⊓ (∃dynastyOf.value Song)` | 锚定具体个体 |

⚠️ OWA 提醒：OWL 是开放世界——「没有生年」不违反 `max 1`，只违反 `min 1`。约束用来**校验**（让推理机报冲突），不是用来**过滤**的。过滤永远在 ETL 层做。

## 7. 析取类与联合类（UnionOf）

```
Agent       ≡ Person ⊔ Institution            # ASSOC 的主体允许是机构（c_inst_code 参与时）
PlaceRef    ≡ AdminPlace ⊔ InstitutionSite    # 地址断言的目标允许精确到机构坐标
Relative    ≡ (∃kinType.(KinType ⊓ (∃upStep.{>0}))) ⊔ (∃kinType.(…dwnStep/colStep/marStep…))  # 由度量并出的「亲属」
FemaleKin   ≡ KinType ⊓ (∃kinNameChn.{…})     # 可配合枚举做性别析取
EntryMode   ≡ ExamEntry ⊔ NonExamEntry        # 科舉門 vs 其他門（ENTRY_TYPES 顶层分叉）
```
实际用途：给对象属性的 domain/range 留扩展口，避免「一个属性建三个变体」。

## 8. 补集类（ComplementOf）与 OWA 陷阱

```
Male            ≡ Person ⊓ ¬Female             # 注意：c_female 96.3% 有值，3.7% 缺值者在 OWA 下不会被归进 Male！
NonKinAssociate ≡ AssociationEvent ⊓ ¬(∃assocViaKin.KinshipAssertion)   # 非经由亲属建立的交遊
LivingPerson    ≡ Person ⊓ ¬(∃deathYear.xsd:gYear)  # ⚠️ 语义陷阱：OWA 下「没记卒年」≠「在世」，此类推理结果不可靠，**不建议建**
```
**这是关系库思维转 OWL 最容易踩的坑**：SQL 的 `WHERE c_female <> 1` 是封闭世界否定（没记=否），OWL 的 `¬Female` 是开放世界否定（未知≠否）。结论：补集类只在**字段覆盖率 ~100%** 时用；`isFemale` 96.3% 可接受（缺 3.7%），`deathYear` 10.8% **不可**用于补集。

## 9. 匿名类（Anonymous Class / Restriction）

匿名类不是独立建模元素，而是上述所有定义中的 ∃/∀/基数表达式本身，Owlready2 里即 `Property.some(...)` 返回的 Restriction 对象。两个典型用途：
1. **定义中**：§5 每个等价类右部都是匿名类（如 `∃entryMode.JinshiMode`）。
2. **查询/描述中**：`kinSource.some(KinshipAssertion ⊓ kinType.value(FatherOf))` ——「所有父亲」这个集合不需要预定义类名，随用随构造。Owlready2 的 `.instances()`/`.subclasses()` 可直接对匿名类求值（经推理机）。

## 10. SPARQL 方案

**Owlready2 内置 SPARQL 走 RDFlib 引擎**：支持基本图模式、OPTIONAL、FILTER，对 property path（如 `kinTarget+`）支持有限，百万三元组以上明显变慢。因此：
- **种子子集**（≤500 万三元组）：直接 `world.sparql()` 够用于验证。
- **全量**：导出 Turtle/N-Triples → GraphDB Free 或 Jena Fuseki，SPARQL 1.1 全特性 + 物化推理。

为真实研究问题准备的 10 个查询（设计稿，前缀略）：

| # | 问题 | 模式要点 |
|---|---|---|
| 1 | 某人的完整档案 | `?p a Person; FILTER id` + OPTIONAL 挂 birthYear/dynasty/AddressClaim |
| 2 | 某人的全部亲属及称谓 | `?a kinSource :X; kinTarget ?k; kinType ?t. ?t kinNameChn ?n` |
| 3 | 某人的 N 度家族网 | 便捷直边 `hasKin{1,3}`（path 查询，外置 store） |
| 4 | 师承链 | `?a assocType :学生之師⁻¹` 链式 |
| 5 | 同年进士（同年会） | `?e1,?e2 entryMode ?m; entryYear ?y. FILTER ?m 属于進士 ∧ ?e1≠?e2` |
| 6 | 任职轨迹（时间序） | `?t tenureHolder :X; firstYear ?y; tenureOffice/tenurePlace ?o/?pl ORDER BY ?y, sequence` |
| 7 | 某县某朝全部人物 | `?ac addrPlace/belongsTo* :county; addrPerson ?p. ?p dynastyOf ?d` |
| 8 | 某书关联的所有人物 | `?trl textRole ?role; textT :text; textAuthor ?p` |
| 9 | 某学派/主题网络 | `?ae assocTopic :理學; assocFrom/assocTo ?a/?b` |
| 10 | 推理验证：所有 JinshiOfficial | 直接 `?x a :JinshiOfficial`（靠 §5 等价类物化） |

## 11. 规模估算与可行性（关键风险）

**三元组估算**（数据行 × 平均每行有效三元组，0/NULL 不落图）：

| 层 | 行数 | 估算 | 三元组 |
|---|---|---|---|
| S 级五断言+人物+地址 | ~3.25M | ×12 | ~3,900 万 |
| A 级（文本/身份/别名/来源） | ~1.6M | ×10 | ~1,600 万 |
| 码表/字典个体 | ~4.2 万 | ×8 | ~35 万 |
| B 级（机构/事件/财产） | ~9 千 | ×10 | ~9 万 |
| **合计（不含 LIFE_EVENT_RESOLVED）** | | | **≈ 5,500–7,000 万** |
| （可选）LIFE_EVENT_RESOLVED | 3.0M | ×19 | +5,700 万（建议不挂） |

**可行性判断**：
- Owlready2 的 SQLite quadstore 甜点区在**数百万到 ~2,000 万**三元组；5,500 万级全量会出现加载极慢（逐实例 Python 对象化）、`sync_reasoner` 不可用。
- HermiT/Pellet 全量归类在千万级实例上**实际不可行**。

**推荐两段式**：

| 阶段 | 规模 | 工具 | 目的 |
|---|---|---|---|
| **Phase A：种子子集** | 5 万人物及其全维度邻域 ≈ 300–500 万三元组 | Owlready2 + HermiT + 内置 SPARQL | 验证本体设计（等价类/约束/匿名类全部可跑通） |
| **Phase B：全量** | ~7,000 万 | Owlready2 只做 TBox + 批量生成 N-Triples ABox → GraphDB Free（OWL-Horst 物化）或 Jena TDB2 | 全量 SPARQL 查询服务 |

子集抽样必须**按连通邻域切**（选定种子人物后带出其一二度亲属/交遊/任职），不能 `ORDER BY RANDOM()` 抽——否则图被撕碎，推理验证失去意义。

## 12. 落地路线图（不写代码，只定阶段）

| 阶段 | 产出 | 验收 |
|---|---|---|
| 0. 准备 | 本报告 + 体检数据（已完成） | — |
| 1. TBox 设计冻结 | 类/属性/公理清单（本报告 §3–§9 评审定稿） | 公理评审通过 |
| 2. 种子 ETL | 5 万人物连通子集 → Owlready2 ABox；ETL 规则：0/NULL 不落图、MERGED 归一、KIN 双向展开 | 密度抽检与 SQL 对账一致 |
| 3. 推理验证 | HermiT 一致性检查 + §5 等价类归类 + §6 约束校验 | 无 unsatisfiable；JinshiOfficial 数与 SQL 对比误差 <1% |
| 4. 查询验证 | §10 的 10 条 SPARQL 全过 | 与现有 Web 查询台结果对账 |
| 5. 全量外置 | N-Triples 导出 → GraphDB/Jena；Owlready2 仅维护 TBox | endpoint 可查 |

---

## 附：本文未覆盖的后续问题

- LIFE_EVENT_RESOLVED（自建推导层）是否挂图：建议作为 `prov:wasDerivedFrom` 注释层，不进主图。
- 亲属距离推理（upstep/dwnstep 链式求和）OWL 表达不了算术，需要 SPARQL 计算或 SWRL 规则（HermiT 不支持 SWRL 算术内建）→ 放查询层解决。
- 年号/干支与公历的互转：建模为 `TemporalEntity` 个体 + 数据属性，换算逻辑放应用层。
