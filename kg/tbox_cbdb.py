# -*- coding: utf-8 -*-
"""CBDB TBox v1.0（FROZEN）的 Owlready2 实现。
冻结文档：kg/TBOX_v1.0.md —— 任何修改必须先改冻结文档并升版本。

用法：
    from owlready2 import World
    from tbox_cbdb import build_tbox, CBDB, CBDBI
    world = World()
    world.set_backend(filename="kg/quadstore/cbdb_ming.sqlite3")
    onto, ns = build_tbox(world)      # onto=TBox 本体, ns=实例命名空间 cbdbi
"""
from owlready2 import (
    Thing, ObjectProperty, DataProperty, FunctionalProperty,
    TransitiveProperty, SymmetricProperty, Inverse, OneOf, AllDisjoint,
    get_ontology, rdfs,
)

CBDB = "http://cbdb.example.org/ontology#"
CBDBI = "http://cbdb.example.org/id/"


def _lab(e, zh=None, en=None):
    """挂双语 rdfs:label。"""
    if zh:
        e.label.append(_locstr(zh, "zh"))
    if en:
        e.label.append(_locstr(en, "en"))


def _locstr(s, lang):
    from owlready2 import locstr
    return locstr(s, lang)


def build_tbox(world):
    # 必须走同一个 world（全局 get_ontology() 用的是 default_world，
    # 与 set_backend 的 world 不一致会导致三元组全落在内存、不进 quadstore）
    onto = world.get_ontology(CBDB)      # TBox
    inst = world.get_ontology(CBDBI)     # ABox 本体：实例命名空间
    inst.imported_ontologies.append(onto)
    ns = inst

    with onto:
        # ============ 2.1 实体类 ============
        class TemporalEntity(Thing): pass
        class Dynasty(TemporalEntity): pass
        class NianHao(TemporalEntity): pass

        class Person(Thing): pass
        class Place(Thing): pass
        class Office(Thing): pass
        class Text(Thing): pass
        class Institution(Thing): pass

        # ============ 2.2 断言类 ============
        class Assertion(Thing): pass
        class KinshipAssertion(Assertion): pass
        class AssociationEvent(Assertion): pass
        class OfficeTenure(Assertion): pass
        class EntryRecord(Assertion): pass
        class AddressClaim(Assertion): pass
        class StatusPeriod(Assertion): pass
        class TextRoleLink(Assertion): pass

        # ============ 2.3 概念容器类 ============
        class Concept(Thing): pass
        class KinType(Concept): pass
        class AssocType(Concept): pass
        class EntryModeConcept(Concept): pass
        class OfficeTypeConcept(Concept): pass
        class StatusConcept(Concept): pass
        class AddrKind(Concept): pass
        class AdminCatType(Concept): pass
        class TextCategory(Concept): pass
        class RoleType(Concept): pass
        class TopicType(Concept): pass
        class OccasionType(Concept): pass
        class GenreType(Concept): pass
        class AppointmentType(Concept): pass
        class OfficeCategory(Concept): pass
        class IndexYearRule(Concept): pass

        # ============ 2.4 枚举类 ============
        class AssumeStatus(Thing): pass
        class ParentalStatus(Thing): pass
        class ExtantStatus(Thing): pass
        class YearRangeType(Thing): pass

        # ============ 3 对象属性 ============
        class kinSource(ObjectProperty, FunctionalProperty):
            domain = [KinshipAssertion]; range = [Person]
        class kinTarget(ObjectProperty, FunctionalProperty):
            domain = [KinshipAssertion]; range = [Person]
        class kinType(ObjectProperty, FunctionalProperty):
            domain = [KinshipAssertion]; range = [KinType]
        class kinSourceText(ObjectProperty, FunctionalProperty):
            domain = [KinshipAssertion]; range = [Text]
        class kinOf(ObjectProperty):
            domain = [Person]; range = [Person]
        class hasKin(ObjectProperty):
            domain = [Person]; range = [Person]
            inverse_property = kinOf

        class assocFrom(ObjectProperty, FunctionalProperty):
            domain = [AssociationEvent]; range = [Person]
        class assocTo(ObjectProperty, FunctionalProperty):
            domain = [AssociationEvent]; range = [Person]
        class assocType(ObjectProperty, FunctionalProperty):
            domain = [AssociationEvent]; range = [AssocType]
        class assocPlace(ObjectProperty, FunctionalProperty):
            domain = [AssociationEvent]; range = [Place]
        class assocOccasion(ObjectProperty, FunctionalProperty):
            domain = [AssociationEvent]; range = [OccasionType]
        class assocTopic(ObjectProperty, FunctionalProperty):
            domain = [AssociationEvent]; range = [TopicType]
        class assocGenre(ObjectProperty, FunctionalProperty):
            domain = [AssociationEvent]; range = [GenreType]
        class assocViaKin(ObjectProperty):
            domain = [AssociationEvent]; range = [KinshipAssertion]  # v1.0 仅定义（C7）
        class associateOf(ObjectProperty):
            domain = [Person]; range = [Person]
        class hasAssociate(ObjectProperty):
            domain = [Person]; range = [Person]
            inverse_property = associateOf

        class tenureHolder(ObjectProperty, FunctionalProperty):
            domain = [OfficeTenure]; range = [Person]
        class tenureOffice(ObjectProperty, FunctionalProperty):
            domain = [OfficeTenure]; range = [Office]
        class tenurePlace(ObjectProperty):
            domain = [OfficeTenure]; range = [Place]
        class apptType(ObjectProperty, FunctionalProperty):
            domain = [OfficeTenure]; range = [AppointmentType]
        class assumeStatus(ObjectProperty, FunctionalProperty):
            domain = [OfficeTenure]; range = [AssumeStatus]
        class officeCategoryOf(ObjectProperty, FunctionalProperty):
            domain = [OfficeTenure]; range = [OfficeCategory]
        class heldOffice(ObjectProperty):
            domain = [Person]; range = [OfficeTenure]
            inverse_property = tenureHolder
        class officeType(ObjectProperty):
            domain = [Office]; range = [OfficeTypeConcept]

        class entryPerson(ObjectProperty, FunctionalProperty):
            domain = [EntryRecord]; range = [Person]
        class entryMode(ObjectProperty, FunctionalProperty):
            domain = [EntryRecord]; range = [EntryModeConcept]
        class parentalStatus(ObjectProperty, FunctionalProperty):
            domain = [EntryRecord]; range = [ParentalStatus]

        class addrPerson(ObjectProperty, FunctionalProperty):
            domain = [AddressClaim]; range = [Person]
        class addrPlace(ObjectProperty, FunctionalProperty):
            domain = [AddressClaim]; range = [Place]
        class addrKind(ObjectProperty, FunctionalProperty):
            domain = [AddressClaim]; range = [AddrKind]

        class statusPerson(ObjectProperty, FunctionalProperty):
            domain = [StatusPeriod]; range = [Person]
        class statusConcept(ObjectProperty, FunctionalProperty):
            domain = [StatusPeriod]; range = [StatusConcept]

        class rolePerson(ObjectProperty, FunctionalProperty):
            domain = [TextRoleLink]; range = [Person]
        class roleText(ObjectProperty, FunctionalProperty):
            domain = [TextRoleLink]; range = [Text]
        class roleType(ObjectProperty, FunctionalProperty):
            domain = [TextRoleLink]; range = [RoleType]

        class sourceOf(ObjectProperty):
            domain = [Person]; range = [Text]  # C2：种子期直边（无页码）

        class dynastyOf(ObjectProperty, FunctionalProperty):
            domain = [Person]; range = [Dynasty]
        class indexYearRule(ObjectProperty, FunctionalProperty):
            domain = [Person]; range = [IndexYearRule]
        class belongsTo(ObjectProperty, TransitiveProperty):
            domain = [Place]; range = [Place]
        class placeAdminCat(ObjectProperty, FunctionalProperty):
            domain = [Place]; range = [AdminCatType]
        class textCategory(ObjectProperty):
            domain = [Text]; range = [TextCategory]
        class extantStatus(ObjectProperty, FunctionalProperty):
            domain = [Text]; range = [ExtantStatus]
        class conceptBroader(ObjectProperty, TransitiveProperty):
            domain = [Concept]; range = [Concept]
        class marriedTo(ObjectProperty, SymmetricProperty):
            domain = [Person]; range = [Person]  # v1.0 仅定义（C7）

        # ============ 4 数据属性 ============
        class personId(DataProperty, FunctionalProperty):
            domain = [Person]; range = [int]
        class nameChn(DataProperty, FunctionalProperty):
            domain = [Person]; range = [str]
        class namePinyin(DataProperty, FunctionalProperty):
            domain = [Person]; range = [str]
        class isFemale(DataProperty, FunctionalProperty):
            domain = [Person]; range = [bool]
        class birthYear(DataProperty, FunctionalProperty):
            domain = [Person]; range = [int]
        class deathYear(DataProperty, FunctionalProperty):
            domain = [Person]; range = [int]
        class deathAge(DataProperty, FunctionalProperty):
            domain = [Person]; range = [int]
        class indexYear(DataProperty, FunctionalProperty):
            domain = [Person]; range = [int]
        class floruitStart(DataProperty, FunctionalProperty):
            domain = [Person]; range = [int]
        class floruitEnd(DataProperty, FunctionalProperty):
            domain = [Person]; range = [int]
        class altName(DataProperty):
            domain = [Person]; range = [str]

        class upStep(DataProperty, FunctionalProperty):
            domain = [KinType]; range = [int]
        class dwnStep(DataProperty, FunctionalProperty):
            domain = [KinType]; range = [int]
        class colStep(DataProperty, FunctionalProperty):
            domain = [KinType]; range = [int]
        class marStep(DataProperty, FunctionalProperty):
            domain = [KinType]; range = [int]
        class conceptNameChn(DataProperty, FunctionalProperty):
            domain = [Concept]; range = [str]
        class conceptNameEn(DataProperty, FunctionalProperty):
            domain = [Concept]; range = [str]
        class assocPairCode(DataProperty, FunctionalProperty):
            domain = [AssocType]; range = [int]

        class tenureFirstYear(DataProperty, FunctionalProperty):
            domain = [OfficeTenure]; range = [int]
        class tenureLastYear(DataProperty, FunctionalProperty):
            domain = [OfficeTenure]; range = [int]
        class tenureSequence(DataProperty, FunctionalProperty):
            domain = [OfficeTenure]; range = [int]
        class entryYear(DataProperty, FunctionalProperty):
            domain = [EntryRecord]; range = [int]
        class entryAge(DataProperty, FunctionalProperty):
            domain = [EntryRecord]; range = [int]
        class examRank(DataProperty, FunctionalProperty):
            domain = [EntryRecord]; range = [str]
        class examField(DataProperty, FunctionalProperty):
            domain = [EntryRecord]; range = [str]
        class assocFirstYear(DataProperty, FunctionalProperty):
            domain = [AssociationEvent]; range = [int]
        class addrFirstYear(DataProperty, FunctionalProperty):
            domain = [AddressClaim]; range = [int]
        class addrLastYear(DataProperty, FunctionalProperty):
            domain = [AddressClaim]; range = [int]
        class statusFirstYear(DataProperty, FunctionalProperty):
            domain = [StatusPeriod]; range = [int]
        class statusLastYear(DataProperty, FunctionalProperty):
            domain = [StatusPeriod]; range = [int]

        class placeNameChn(DataProperty, FunctionalProperty):
            domain = [Place]; range = [str]
        class placeNameEn(DataProperty, FunctionalProperty):
            domain = [Place]; range = [str]
        class xCoord(DataProperty, FunctionalProperty):
            domain = [Place]; range = [float]
        class yCoord(DataProperty, FunctionalProperty):
            domain = [Place]; range = [float]
        class placeFirstYear(DataProperty, FunctionalProperty):
            domain = [Place]; range = [int]
        class placeLastYear(DataProperty, FunctionalProperty):
            domain = [Place]; range = [int]
        class officeNameChn(DataProperty, FunctionalProperty):
            domain = [Office]; range = [str]
        class officeNameEn(DataProperty, FunctionalProperty):
            domain = [Office]; range = [str]
        class textTitleChn(DataProperty, FunctionalProperty):
            domain = [Text]; range = [str]
        class textTitleEn(DataProperty, FunctionalProperty):
            domain = [Text]; range = [str]
        class textYear(DataProperty, FunctionalProperty):
            domain = [Text]; range = [int]

        # ============ 5 公理 ============
        # A1 顶层互斥
        AllDisjoint([Person, Place, Office, Text, Assertion])

        # A2/A3 Person 约束
        Person.is_a.append(personId.exactly(1, int))
        Person.is_a.append(birthYear.max(1, int))
        Person.is_a.append(deathYear.max(1, int))
        Person.is_a.append(indexYear.max(1, int))

        # A4–A8 断言三要素
        KinshipAssertion.is_a.append(kinSource.exactly(1, Person))
        KinshipAssertion.is_a.append(kinTarget.exactly(1, Person))
        KinshipAssertion.is_a.append(kinType.exactly(1, KinType))
        AssociationEvent.is_a.append(assocFrom.exactly(1, Person))
        AssociationEvent.is_a.append(assocTo.exactly(1, Person))
        AssociationEvent.is_a.append(assocType.exactly(1, AssocType))
        OfficeTenure.is_a.append(tenureHolder.exactly(1, Person))
        OfficeTenure.is_a.append(tenureOffice.exactly(1, Office))
        EntryRecord.is_a.append(entryPerson.exactly(1, Person))
        EntryRecord.is_a.append(entryMode.exactly(1, EntryModeConcept))
        AddressClaim.is_a.append(addrPerson.exactly(1, Person))
        AddressClaim.is_a.append(addrPlace.exactly(1, Place))
        AddressClaim.is_a.append(addrKind.exactly(1, AddrKind))

        # ============ 2.4 枚举个体（TBox 写死） ============
        _mk_enums(onto, ns, AssumeStatus, "assume", [
            (0, "未詳", "unknown"), (1, "赴任", "assumed office"), (2, "辭不就", "declined"),
            (3, "未赴任而卒", "died before assuming"), (4, "未赴任而改命", "reassigned"),
            (5, "未赴任", "did not assume")])
        _mk_enums(onto, ns, ParentalStatus, "parental", [
            (1, "具慶", "both parents alive"), (2, "嚴侍", "father alive"),
            (3, "慈侍", "mother alive"), (4, "永感", "both deceased"),
            (5, "偏侍", "one parent alive"), (6, "其他", "other"), (7, "未詳", "unknown")])
        _mk_enums(onto, ns, ExtantStatus, "extant", [
            (0, "未詳", "unknown"), (1, "現存", "extant"),
            (2, "已佚", "lost"), (3, "Secondary source", "secondary source")])
        _mk_enums(onto, ns, YearRangeType, "yearrange", [
            (1, "確定年", "exact"), (2, "範圍", "range"), (3, "大約", "circa"),
            (4, "之前", "before"), (5, "之後", "after"), (6, "未詳", "unknown")])

        # ============ 2.5 推理类（等价类） ============
        class Official(Thing): pass
        Official.equivalent_to.append(Person & Inverse(tenureHolder).some(OfficeTenure))

        class Female(Thing): pass
        Female.equivalent_to.append(Person & isFemale.value(True))   # C3 值约束

        class Male(Thing): pass
        Male.equivalent_to.append(Person & isFemale.value(False))

        # MingPerson 需要 dynasty/19 锚点个体（ETL 全量 Dynasty 时复用同 IRI）
        ming = Dynasty("dynasty/19", namespace=ns)
        _lab(ming, "明", "Ming")

        class MingPerson(Thing): pass
        MingPerson.equivalent_to.append(Person & dynastyOf.value(ming))

        # JinshiHolder 的進士集合由 ETL 生成（C4），先占位类
        class JinshiModes(Thing): pass
        class JinshiHolder(Thing): pass
        class JinshiOfficial(Thing): pass
        JinshiOfficial.equivalent_to.append(JinshiHolder & Official)

    # ============ TBox 双语标签（核心元素） ============
    L = {
        "Person": ("人物", "Person"), "Place": ("地址/行政单位", "Place"),
        "Office": ("官职", "Office"), "Text": ("文本", "Text"),
        "Institution": ("社会机构", "Social Institution"),
        "Dynasty": ("朝代", "Dynasty"), "Assertion": ("断言", "Assertion"),
        "KinshipAssertion": ("亲属断言", "Kinship Assertion"),
        "AssociationEvent": ("交遊事件", "Association Event"),
        "OfficeTenure": ("任职 tenure", "Office Tenure"),
        "EntryRecord": ("入仕记录", "Entry Record"),
        "AddressClaim": ("地址关系断言", "Address Claim"),
        "StatusPeriod": ("身份时期", "Status Period"),
        "TextRoleLink": ("文本角色关联", "Text Role Link"),
        "Concept": ("概念", "Concept"), "KinType": ("亲属类型", "Kin Type"),
        "AssocType": ("交遊类型", "Association Type"),
        "EntryModeConcept": ("入仕途径", "Entry Mode"),
        "OfficeTypeConcept": ("官职类型", "Office Type"),
        "StatusConcept": ("身份概念", "Status Concept"),
        "AddrKind": ("地址关系类型", "Address Kind"),
        "Official": ("有任官记录者", "Official"),
        "JinshiHolder": ("进士出身者", "Jinshi Holder"),
        "Female": ("女性人物", "Female"), "Male": ("男性人物", "Male"),
        "MingPerson": ("明代人物", "Ming Person"),
        "JinshiOfficial": ("进士出身官员", "Jinshi Official"),
    }
    for name, (zh, en) in L.items():
        _lab(onto[name], zh, en)

    return onto, ns


def _mk_enums(onto, ns, cls, scheme, items):
    """创建枚举个体 + OneOf 等价（A10）。个体 IRI: cbdbi:enum/{scheme}/{code}"""
    inds = []
    for code, zh, en in items:
        i = cls(f"enum/{scheme}/{code}", namespace=ns)
        _lab(i, zh, en)
        inds.append(i)
    cls.equivalent_to.append(OneOf(inds))
    return inds


def attach_jinshi_modes(onto, jinshi_individuals):
    """C4：ETL 生成進士词条个体集后调用，挂 OneOf + JinshiHolder 等价类。"""
    onto["JinshiModes"].equivalent_to.append(OneOf(jinshi_individuals))
    jh = onto["JinshiHolder"]
    jh.equivalent_to.append(
        onto["Person"] & Inverse(onto["entryPerson"]).some(
            onto["EntryRecord"] & onto["entryMode"].some(onto["JinshiModes"])
        )
    )
