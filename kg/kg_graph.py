# -*- coding: utf-8 -*-
"""quadstore → 内存谓词子图索引（GraphIndex），专题查询的底座。

owlready2 自带的 SPARQL 解析器不支持尖括号 IRI 且大数据量慢，
所以这里把需要的谓词子图一次性抽进内存（~3.4s / 292 万边），
之后所有查询都是纯字典查找（毫秒级）。

职责边界：
  * 本文件只做**索引**（打开 sqlite、建 prop→s→o 映射、简繁归一化）；
  * Q1–Q9 的查询实现在 `kg_query.py`（改查询只看那个文件）。

⚠️ 与 owlready2 World 的共存问题：World 会长期持有 quadstore 的写事务，
   本文件用只读连接会撞上 "database is locked"，
   所以 get_index() 里检测到 locked 时会先释放本进程的 World 缓存再读。
"""
import os
import sqlite3
import threading
import time
from collections import defaultdict, deque

HERE = os.path.dirname(os.path.abspath(__file__))
CBDB = "http://cbdb.example.org/ontology#"
RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"

OBJ_PROPS = [
    "hasKin", "kinOf", "hasAssociate", "associateOf", "dynastyOf", "indexYearRule",
    "belongsTo", "placeAdminCat", "addrPlace", "addrPerson", "addrKind",
    "kinSource", "kinTarget", "kinType", "kinSourceText",
    "tenureHolder", "tenureOffice", "tenurePlace", "apptType", "assumeStatus",
    "officeCategoryOf", "entryPerson", "entryMode", "parentalStatus",
    "assocFrom", "assocTo", "assocType", "assocPlace", "assocOccasion",
    "assocTopic", "assocGenre", "sourceOf", "rolePerson", "roleText", "roleType",
    "statusPerson", "statusConcept", "officeType", "textCategory", "extantStatus",
    "broader", "marriedTo",
]
DATA_PROPS = [
    "personId", "nameChn", "namePinyin", "isFemale", "birthYear", "deathYear",
    "deathAge", "indexYear", "floruitStart", "floruitEnd",
    "placeNameChn", "placeNameEn", "placeFirstYear", "placeLastYear",
    "officeNameChn", "officeNameEn", "textTitleChn", "textTitleEn", "textYear",
    "conceptNameChn", "conceptNameEn", "entryYear", "entryAge", "examRank",
    "examField", "tenureFirstYear", "tenureLastYear", "tenureSequence",
    "assocFirstYear", "addrFirstYear", "addrLastYear",
    "statusFirstYear", "statusLastYear", "upStep", "dwnStep", "altName",
]
MULTI_DATA = {"altName"}
SPECIAL_PROPS = {"label": RDFS_LABEL}


class GraphIndex:
    """quadstore 的谓词子图索引（按 quadstore 路径缓存）。"""

    def __init__(self, path):
        self.path = path
        t0 = time.time()
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=30)
        self.pid = {}
        for n in OBJ_PROPS + DATA_PROPS:
            r = con.execute("SELECT storid FROM resources WHERE iri=?", (CBDB + n,)).fetchone()
            if r:
                self.pid[n] = r[0]
        for n, iri in SPECIAL_PROPS.items():
            r = con.execute("SELECT storid FROM resources WHERE iri=?", (iri,)).fetchone()
            if r:
                self.pid[n] = r[0]
        rev = {v: k for k, v in self.pid.items()}

        self.E = defaultdict(lambda: defaultdict(list))   # prop -> s -> [o]
        self.D = defaultdict(dict)                        # prop -> s -> value
        self.Dm = defaultdict(lambda: defaultdict(list))  # 多值数据属性

        oids = [self.pid[n] for n in OBJ_PROPS if n in self.pid]
        q = f"SELECT s,p,o FROM objs WHERE p IN ({','.join('?' * len(oids))})"
        for s, p, o in con.execute(q, oids):
            self.E[rev[p]][s].append(o)

        # 注意：owlready2 的 datas(c,s,p,o,d) 里**字面量值在 o 列**，d 存数据类型/语言标签
        dids = [self.pid[n] for n in DATA_PROPS + list(SPECIAL_PROPS) if n in self.pid]
        q = f"SELECT s,p,o,d FROM datas WHERE p IN ({','.join('?' * len(dids))})"
        for s, p, val, lang in con.execute(q, dids):
            n = rev[p]
            if n in MULTI_DATA:
                self.Dm[n][s].append(val)
            elif n == "label":              # 双语标签：优先保留 @zh
                if lang == "@zh" or s not in self.D[n]:
                    self.D[n][s] = val
            else:
                self.D[n][s] = val
        con.close()

        # 常用映射
        self.s2pid = {s: int(v) for s, v in self.D.get("personId", {}).items()}
        self.pid2s = {v: k for k, v in self.s2pid.items()}
        self.name = self.D.get("nameChn", {})
        self.pname = self.D.get("placeNameChn", {})
        self.tname = self.D.get("textTitleChn", {})
        self.cname = self.D.get("conceptNameChn", {})
        self.oname = self.D.get("officeNameChn", {})
        self.label = self.D.get("label", {})
        self.name2c = {}
        for s, n in self.cname.items():
            self.name2c.setdefault(str(n), s)
        self._rev = {}

        # ---- 简繁归一化：CBDB 全库繁体（餘姚/傳習錄/講學），用户常输简体（余姚/传习录/讲学）
        try:
            from zhconv import convert as _conv
        except Exception:          # 未装 zhconv 时退化为原样匹配
            _conv = None
        self._conv = _conv
        self.pname_s = {s: self._simp(n) for s, n in self.pname.items()}
        self.tname_s = {s: self._simp(n) for s, n in self.tname.items()}
        self.cname_s = {s: self._simp(n) for s, n in self.cname.items()}
        self.oname_s = {s: self._simp(n) for s, n in self.oname.items()}
        self._place_freq = None
        self.build_secs = round(time.time() - t0, 1)

    # ---------------------------------------------------------------- 简繁归一化
    def _simp(self, x):
        s = "" if x is None else str(x)
        if not s or self._conv is None:
            return s
        try:
            return self._conv(s, "zh-hans")
        except Exception:
            return s

    def variants(self, s):
        """输入词的 原样 / 简体 / 繁体 三种写法（去重）。"""
        out, seen = [], set()
        base = "" if s is None else str(s)
        for v in (base, self._simp(base)):
            if v and v not in seen:
                seen.add(v)
                out.append(v)
        if self._conv is not None and base:
            try:
                t = self._conv(base, "zh-hant")
                if t not in seen:
                    out.append(t)
            except Exception:
                pass
        return out

    def match_by_name(self, mapping, simp_map, keyword):
        """在 {storid: 名称} 里按关键词匹配，自动兼容简繁体。返回 [(storid, 名称)]。"""
        kws = self.variants(keyword)
        if not kws:
            return []
        hits = []
        for s, n in mapping.items():
            a, b = str(n), simp_map.get(s, "")
            if any((k in a) or (k in b) for k in kws):
                hits.append((s, n))
        return hits

    def top_places(self, n=12):
        """最常被引用（AddressClaim）的地点，用于「没匹配上」时给候选提示。"""
        if self._place_freq is None:
            fq = defaultdict(int)
            for c, places in self.E.get("addrPlace", {}).items():
                for pl in places:
                    fq[pl] += 1
            self._place_freq = fq
        top = sorted(self._place_freq.items(), key=lambda x: -x[1])[: int(n)]
        return [(self.pname.get(s, ""), c) for s, c in top if self.pname.get(s)]

    # ---------------------------------------------------------------- 基础访问
    def o(self, prop, s):
        return self.E.get(prop, {}).get(s, [])

    def d(self, prop, s):
        return self.D.get(prop, {}).get(s)

    def rev(self, prop):
        """反向索引：prop 的 o -> [s]"""
        if prop not in self._rev:
            m = defaultdict(list)
            for s, os_ in self.E.get(prop, {}).items():
                for o in os_:
                    m[o].append(s)
            self._rev[prop] = m
        return self._rev[prop]

    def plabel(self, s):
        """人物 storid → "姓名(pid)" """
        if s is None:
            return "—"
        n = self.name.get(s, "?")
        p = self.s2pid.get(s)
        return f"{n}({p})" if p is not None else str(n)

    def cname_of(self, s):
        return self.cname.get(s) or self.label.get(s) or ""

    def dynasty_of(self, s):
        dys = self.o("dynastyOf", s)
        return self.label.get(dys[0]) if dys else ""

    def dynasties_present(self):
        """[(朝代名, 人数)]，按人数降序。"""
        cnt = defaultdict(int)
        for s, ds in self.E.get("dynastyOf", {}).items():
            for d in ds:
                cnt[d] += 1
        out = [(self.label.get(d, f"#{d}"), n) for d, n in cnt.items()]
        out.sort(key=lambda x: -x[1])
        return out

    def place_path(self, s, maxlen=6):
        """地点 storid → 层级路径字符串（子 → 父）"""
        out, cur, seen = [], s, set()
        while cur is not None and cur not in seen and len(out) < maxlen:
            seen.add(cur)
            out.append(self.pname.get(cur, f"#{cur}"))
            ps = self.o("belongsTo", cur)
            cur = ps[0] if ps else None
        return " → ".join(out)

    def place_closure(self, roots):
        """给定地点集合，返回其全部后代（含自身），走 belongsTo 反向闭包。"""
        rmap = self.rev("belongsTo")
        seen, stack = set(roots), list(roots)
        while stack:
            x = stack.pop()
            for ch in rmap.get(x, []):
                if ch not in seen:
                    seen.add(ch)
                    stack.append(ch)
        return seen


_cache = {}
_index_lock = threading.Lock()


def get_index(path):
    if not path:
        return None
    if path not in _cache:
        # 大图谱（如 明 587MB）首次构建较慢；用锁避免并发请求重复构建
        with _index_lock:
            if path not in _cache:
                try:
                    _cache[path] = GraphIndex(path)
                except sqlite3.OperationalError as e:
                    if "locked" not in str(e):
                        raise
                    # owlready2 的 World 会长期持有 quadstore 的写事务，
                    # 导致本进程的只读连接拿不到 SHARED 锁（database is locked）。
                    # 先关掉自己的 World 缓存再读；之后详情页会按需重建。
                    _release_world(path)
                    _cache[path] = GraphIndex(path)
    return _cache[path]


def _release_world(path):
    try:
        import kg_backend
        kg_backend.close_worlds(path)
    except Exception:
        pass


def drop_index(path=None):
    if path is None:
        _cache.clear()
    else:
        _cache.pop(path, None)


# ============================================================ 兼容转发
_Q_FUNCS = ("q1_dossier", "q2_kin", "q3_kinnet", "q4_teacher", "q5_jinshi",
            "q6_tenure", "q7_county", "q8_book", "q9_topic",
            "teacher_code_sets", "topic_candidates", "assoc_type_candidates")


def __getattr__(name):
    """Q1–Q9 的实现已迁到 `kg_query.py`，这里保留同名访问以免老调用点报错。"""
    if name in _Q_FUNCS:
        import kg_query
        return getattr(kg_query, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
