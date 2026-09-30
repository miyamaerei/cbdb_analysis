# CBDB 知识图谱 TBox 设计冻结 v1.0

> 状态：**FROZEN** · 2026-09-29 · 实现唯一依据
> 依据：《CBDB_知识图谱本体设计研究.md》§3–§9 评审定稿；数据事实见 analysis/ 体检结果
> 实现：`kg/tbox_cbdb.py`（Owlready2）｜种子集：明朝（`c_dy=19`，225,593 人）

## 0. 相对研究报告的变更记录（冻结决策）

| # | 变更 | 理由 |
|---|---|---|
| C1 | **所有码表统一走 SKOS 风格「概念个体 + `conceptBroader` 自关联」**，不再建 OWL 子类层级 | CBDB 码表（2,742 官职树、273 入仕词条、488 亲属码…）本质是叙词表；类层级会让 TBox 膨胀且 OWL 类表达式不支持 `broader*` 路径，等价类反而写不了 |
| C2 | `BIOG_SOURCE_DATA`（47 万行）种子期降级为 `sourceOf` **直边**（放弃页码） | 省 ~47 万 hub 实例；全量期再升级 `SourceClaim` 断言类 |
| C3 | 性别相关定义用**值约束**不用补集（`isFemale value false` 定义 Male），弃用 `¬Female` | OWA 下缺值 3.7% 会被错误排除（研究报告 §8 已预警，冻结为规则） |
| C4 | `JinshiHolder` 的「進士」集合由 **ETL 期计算生成 OneOf 列表**（ENTRY_TYPES 树中「進士」子树的全部词条个体），不写死在 TBox | 列表来自数据，TBox 只冻结规则 |
| C5 | `MERGED_PERSON_DATA` 用 **ETL 期 ID 归一**（旧 ID 不建实例），不建 `owl:sameAs` | 推理机合并不可控；归一后图更干净。映射日志落盘备查 |
| C6 | 别名降级为 `altName` 多值数据属性（不做类型化断言） | ALTNAME_CODES 21 类价值低，种子期从简 |
| C7 | 郡望/族属/户籍（覆盖率 2%–6%）、年号表、`ASSOC_DATA.c_kin_code`（经何亲属）、`marriedTo` 推导 —— **v1.0 只定义不加载** | 低覆盖或需推导，留待后续版本 |
| C8 | 单值属性一律 `FunctionalProperty`（v1.0.1 实现期补丁）：`nameChn`/`namePinyin` 及 12 个对象属性（`indexYearRule` `placeAdminCat` `extantStatus` `kinSourceText` `assocPlace` `assocOccasion` `assocTopic` `assocGenre` `parentalStatus` `apptType` `assumeStatus` `officeCategoryOf`） | 源表每行这些列就是单值；functional 让 ETL 直接赋值、推理期可校验 |
| C9 | `OfficeTenure` 的 IRI 改为 `tenure/{c_posting_id}-{rowid}`（原定只用 `c_posting_id`） | **冻结时的错误假设**：实测 591,652 posting 对应 591,683 行，一次 posting 可挂多个 office，只用 posting_id 会让不同 tenure 复用同一节点（本次相差 18 条） |
| C10 | 人物属性加载跳过 `MERGED_PERSON_DATA` 的作废 ID（补充 C5） | 仅断言层归一而属性层不归一，会把同一人拆成两个节点（本次多出 4 个孤儿 Person：55346/55365/80197/576569） |

## 1. 命名空间与 IRI 规则

```
cbdb:  http://cbdb.example.org/ontology#    TBox
cbdbi: http://cbdb.example.org/id/          ABox
  person/{c_personid}   place/{c_addr_id}   office/{c_office_id}   text/{c_textid}
  concept/{scheme}/{code}      scheme ∈ kin|assoc|entry|officetype|status|addrkind|admincat|textcat|role|topic|occasion|genre|appt|officecat|indexyear
  dynasty/{c_dy}        enum/{scheme}/{code}  scheme ∈ assume|parental|extant|yearrange
  kinassert/{rowid}     tenure/{c_posting_id}  entry/{rowid}  assoc/{rowid}  addrclaim/{rowid}
  status/{rowid}        textrole/{rowid}
```
断言类无自然主键的（KIN/ASSOC/ENTRY/BIOG_ADDR/STATUS/TEXTROLE）用 SQLite `rowid`；`OfficeTenure` 用 `c_posting_id`（POSTING_DATA 天然发号）。
双语标签：所有 TBox 元素挂 `rdfs:label @zh/@en`。

## 2. 类清单（冻结）

### 2.1 实体类

| 类 | 父类 | 来源表 | 种子集实例量 |
|---|---|---|---|
| `Person` | Thing | BIOG_MAIN | 225,593（核心）+ 邻域扩展 |
| `Place` | Thing | ADDR_CODES | 种子涉及地址（≤3 万） |
| `Office` | Thing | OFFICE_CODES | 种子涉及官职（≤3.4 万） |
| `Text` | Thing | TEXT_CODES | 种子涉及文本 |
| `Institution` | Thing | SOCIAL_INSTITUTION_CODES | v1.0 定义不加载 |
| `Dynasty` | TemporalEntity | DYNASTIES | 85（全量小表，直接全载） |

### 2.2 断言类（Assertion 子类，hub 节点）

| 类 | 来源表 | 种子集实例量 | 三要素（exactly 1） |
|---|---|---|---|
| `KinshipAssertion` | KIN_DATA | 283,145 | kinSource, kinTarget, kinType |
| `AssociationEvent` | ASSOC_DATA | 57,140 | assocFrom, assocTo, assocType |
| `OfficeTenure` | POSTED_TO_OFFICE_DATA | 117,433 | tenureHolder, tenureOffice |
| `EntryRecord` | ENTRY_DATA | 74,790 | entryPerson, entryMode |
| `AddressClaim` | BIOG_ADDR_DATA | 123,561 | addrPerson, addrPlace, addrKind |
| `StatusPeriod` | STATUS_DATA | 11,333 | statusPerson, statusConcept |
| `TextRoleLink` | BIOG_TEXT_DATA | 10,435 | rolePerson, roleText, roleType |

### 2.3 概念容器类（Concept 子类，ABox 加载码表个体）

`KinType`(488, 带度量) `AssocType`(498) `EntryModeConcept`(273+29大类) `OfficeTypeConcept`(2,742) `StatusConcept`(285+14大类) `AddrKind`(22) `AdminCatType`(213) `TextCategory`(144+51大类) `RoleType`(12) `TopicType`(32) `OccasionType`(10) `GenreType`(12) `AppointmentType`(116+13大类) `OfficeCategory`(15) `IndexYearRule`(31)

### 2.4 枚举类（TBox OneOf 写死，个体属 TBox）

| 枚举类 | 个体（c_code 顺序） | 来源 |
|---|---|---|
| `AssumeStatus` | 未詳0 赴任1 辭不就2 未赴任而卒3 未赴任而改命4 未赴任5 | ASSUME_OFFICE_CODES |
| `ParentalStatus` | 7 值 | PARENTAL_STATUS_CODES |
| `ExtantStatus` | 未詳0 現存1 已佚2 secondary3 | EXTANT_CODES |
| `YearRangeType` | 6 值 | YEAR_RANGE_CODES |

### 2.5 推理类（等价类，TBox 定义）

```
Official     ≡ Person ⊓ Inverse(tenureHolder) some OfficeTenure
JinshiHolder ≡ Person ⊓ Inverse(entryPerson) some (EntryRecord ⊓ entryMode some JinshiModes)
                 其中 JinshiModes ≡ OneOf({ETL 生成的進士词条个体集})      ← C4
Female       ≡ Person ⊓ isFemale value true
Male         ≡ Person ⊓ isFemale value false                             ← C3
MingPerson   ≡ Person ⊓ dynastyOf value dynasty/19
JinshiOfficial ≡ JinshiHolder ⊓ Official
```

## 3. 对象属性清单（冻结）

| 属性 | domain → range | 特性 | 来源列 | 种子期加载 |
|---|---|---|---|---|
| `kinSource` `kinTarget` | KinshipAssertion→Person | 各 functional | c_personid / c_kin_id | ✅ |
| `kinType` | KinshipAssertion→KinType | functional | c_kin_code | ✅ |
| `kinSourceText` | KinshipAssertion→Text | — | c_source | ✅ |
| `hasKin` / `kinOf` | Person→Person | 互逆 | 由 KinshipAssertion 派生直边 | ✅ |
| `assocFrom` `assocTo` | AssociationEvent→Person | 各 functional | c_personid / c_assoc_id | ✅ |
| `assocType` | AssociationEvent→AssocType | functional | c_assoc_code | ✅ |
| `assocPlace` | AssociationEvent→Place | — | c_addr_id | ✅ |
| `assocOccasion`/`assocTopic`/`assocGenre` | AssociationEvent→相应概念 | — | c_occasion_code/c_topic_code/c_litgenre_code | ✅ |
| `assocViaKin` | AssociationEvent→KinshipAssertion | — | c_kin_code | ❌ C7 |
| `hasAssociate` / `associateOf` | Person→Person | 互逆 | 派生直边 | ✅ |
| `tenureHolder` | OfficeTenure→Person | functional | c_personid | ✅ |
| `tenureOffice` | OfficeTenure→Office | functional | c_office_id | ✅ |
| `tenurePlace` | OfficeTenure→Place | — | POSTED_TO_ADDR_DATA.c_addr_id | ✅ |
| `apptType` | OfficeTenure→AppointmentType | — | c_appt_code | ✅ |
| `assumeStatus` | OfficeTenure→AssumeStatus | — | c_assume_office_code | ✅ |
| `officeCategoryOf` | OfficeTenure→OfficeCategory | — | c_office_category_id | ✅ |
| `heldOffice` | Person→OfficeTenure | inverse tenureHolder | — | 推理/查询期 |
| `officeType` | Office→OfficeTypeConcept | — | OFFICE_CODE_TYPE_REL | ✅ |
| `entryPerson` | EntryRecord→Person | functional | c_personid | ✅ |
| `entryMode` | EntryRecord→EntryModeConcept | functional | c_entry_code | ✅ |
| `parentalStatus` | EntryRecord→ParentalStatus | — | c_parental_status_code | ✅ |
| `addrPerson`/`addrPlace`/`addrKind` | AddressClaim→Person/Place/AddrKind | 前二 functional | BIOG_ADDR_DATA | ✅ |
| `statusPerson` | StatusPeriod→Person | functional | c_personid | ✅ |
| `statusConcept` | StatusPeriod→StatusConcept | functional | c_status_code | ✅ |
| `rolePerson`/`roleText`/`roleType` | TextRoleLink→Person/Text/RoleType | 前二 functional | BIOG_TEXT_DATA | ✅ |
| `sourceOf` | Person→Text | — （C2 直边） | BIOG_SOURCE_DATA | ✅ |
| `dynastyOf` | Person→Dynasty | functional | c_dy | ✅ |
| `belongsTo` | Place→Place | **transitive** | ADDRESSES.belongs1..5 | ✅ |
| `placeAdminCat` | Place→AdminCatType | — | c_admin_type→ADMIN_CAT_CODES | ✅ |
| `textCategory` | Text→TextCategory | — | c_bibl_cat_code | ✅ |
| `extantStatus` | Text→ExtantStatus | — | c_extant | ✅ |
| `conceptBroader` | Concept→Concept | **transitive** | *_TYPES 层级 / *_CODE_TYPE_REL | ✅ |
| `conceptName`? —— 用数据属性（见 §4） | | | | |
| `marriedTo` | Person→Person | symmetric | 推导，❌ C7 | 仅定义 |

## 4. 数据属性清单（冻结）

| 属性 | domain | range | 来源列 / 备注 |
|---|---|---|---|
| `personId` | Person | int | functional，exactly 1 |
| `nameChn` / `namePinyin` | Person | string | c_name_chn / c_name |
| `isFemale` | Person | boolean | c_female，functional |
| `birthYear` / `deathYear` | Person | int | 各 max 1；**>0 才挂** |
| `deathAge` | Person | int | c_death_age，>0 |
| `indexYear` | Person | int | max 1 |
| `indexYearRule` | Person→`IndexYearRule`（对象属性） | | c_index_year_type_code，≥0 |
| `floruitStart` / `floruitEnd` | Person | int | c_fl_earliest_year / c_fl_latest_year |
| `altName` | Person | string | 多值，C6 |
| `upStep`/`dwnStep`/`colStep`/`marStep` | KinType | int | KINSHIP_CODES 度量 |
| `conceptNameChn` / `conceptNameEn` | Concept | string | 各码表 *_chn/*_desc 列 |
| `assocPairCode` | AssocType | int | c_assoc_pair_code |
| `tenureFirstYear`/`tenureLastYear`/`tenureSequence` | OfficeTenure | int | >0 才挂；sequence 是年内序 |
| `entryYear`/`entryAge` | EntryRecord | int | >0 |
| `examRank`/`examField` | EntryRecord | string | c_exam_rank/c_exam_field |
| `assocFirstYear` | AssociationEvent | int | >0（仅 8.3%） |
| `addrFirstYear`/`addrLastYear` | AddressClaim | int | >0 |
| `statusFirstYear`/`statusLastYear` | StatusPeriod | int | >0 |
| `placeNameChn`/`placeNameEn` | Place | string | |
| `xCoord`/`yCoord` | Place | float | |
| `placeFirstYear`/`placeLastYear` | Place | int | |
| `officeNameChn`/`officeNameEn` | Office | string | |
| `textTitleChn`/`textTitleEn`/`textYear` | Text | string/string/int | |

## 5. TBox 公理清单（冻结）

```
A1  AllDisjoint(Person, Place, Office, Text, Assertion)
A2  Person ⊑ personId exactly 1 xsd:int
A3  Person ⊑ birthYear max 1 int ⊓ deathYear max 1 int ⊓ indexYear max 1 int
A4  KinshipAssertion ⊑ kinSource exactly 1 Person ⊓ kinTarget exactly 1 Person ⊓ kinType exactly 1 KinType
A5  AssociationEvent ⊑ assocFrom exactly 1 Person ⊓ assocTo exactly 1 Person ⊓ assocType exactly 1 AssocType
A6  OfficeTenure ⊑ tenureHolder exactly 1 Person ⊓ tenureOffice exactly 1 Office
A7  EntryRecord ⊑ entryPerson exactly 1 Person ⊓ entryMode exactly 1 EntryModeConcept
A8  AddressClaim ⊑ addrPerson exactly 1 Person ⊓ addrPlace exactly 1 Place ⊓ addrKind exactly 1 AddrKind
A9  belongsTo transitive；conceptBroader transitive；hasKin inverse kinOf；hasAssociate inverse associateOf；marriedTo symmetric
A10 枚举：AssumeStatus ≡ OneOf{6}；ParentalStatus ≡ OneOf{7}；ExtantStatus ≡ OneOf{4}；YearRangeType ≡ OneOf{6}
A11 等价类：§2.5 全部（Official / JinshiHolder / Female / Male / MingPerson / JinshiOfficial）
```

## 6. ABox 加载契约（ETL 铁律）

| 规则 | 内容 |
|---|---|
| **R1 零值不落图** | 任何属性值为 NULL 或 0（含 '0'）一律不生成三元组；外键 0 = 无引用 |
| **R2 ID 归一** | 加载前构建 `id_map`（MERGED_PERSON_DATA: merged_from→personid，5,920 条）；所有 c_personid/c_kin_id/c_assoc_id 出现处先过 map；映射日志写 `kg/merged_id_map.csv` |
| **R3 断言 hub 化** | 五断言 + StatusPeriod/TextRoleLink 按 §2.2 建 hub 实例；同时派生直边 hasKin/hasAssociate |
| **R4 核心集与邻域** | 核心 = `c_dy=19`；断言仅载 `c_personid ∈ 核心` 的行；KIN/ASSOC 对端 ∉ 核心时创建**轻量 Person**（仅 personId/nameChn/namePinyin/dynastyOf） |
| **R5 地址层级** | Place 的 belongsTo 用 ADDRESSES 的 belongs1..5（非 0/NULL 者），不啃 ADDR_BELONGS_DATA |
| **R6 码表个体全量** | 概念个体不按种子裁剪（码表本身小，全量载入，避免"类型指向不存在的个体"） |
| **R7 批量提交** | 每 10,000 实例 commit 一次，进度日志到 stdout |
| **R8 年份类型** | 所有年份属性用 int（xsd:int），不用 xsd:gYear（Owlready2 对 gYear 支持差，ETL 保证整型） |

## 7. 验证标准（种子集验收）

| 项 | 标准 |
|---|---|
| V1 实例对账 | 各类实例数 == SQL 计数（核心集 + R1/R2 过滤后），误差 0 |
| V2 三元组规模 | 预期 ~1,200–1,400 万，落盘 quadstore 可复开 |
| V3 SPARQL 抽检 | ① 王阳明（王守仁）的亲属断言数 == SQL；② 某進士的 EntryRecord；③ 明代某县人物数（AddressClaim+belongsTo） |
| V4 等价类 | 无 Java/HermiT → 降级：用 SPARQL 按等价类语义手写查询，结果与 SQL 对账误差 <1%；HermiT 验证列为遗留项 |

## 8. 未冻结项（显式留白，v1.1+ 再议）

Institution 全模块、Event/Possession、NianHao/Ganzhi 时间实体、assocViaKin、marriedTo 推导、SourceClaim 页码升级、LIFE_EVENT_RESOLVED 注释层、SWRL/算术亲属距离推理。
