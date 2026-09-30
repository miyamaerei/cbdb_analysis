#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
life_order.py —— 把 CBDB 的「没有年份的一生」变成「有区间的一生 + 有先后的一生」。

=============================================================================
为什么需要这个脚本
=============================================================================
CBDB 的时间轴是残缺的：只有 9.0% 的人有确切生年、5.7% 生卒俱全，亲属关系
0% 有年份、著作 0% 有年份。直接按年份排序会对 90% 的记录撒谎。

但 CBDB 并没有丢掉「顺序信息」：
  · c_sequence  —— 录入时的人工排序（任官 27.9 万条有）
  · 年号区间    —— 至少能定一个 [起始年, 结束年]
  · 生卒边界    —— 人生所有事件必然落在 [生年, 卒年] 内
  · 亲属世代    —— 尊长必早于本人出生、卑幼必晚于本人成年
  · 领域常识    —— 字在 15~30 岁取、諡號在死后、科举在 12~60 岁、入仕早于任官
  · 对方活跃年  —— 亲属/交游的对方有 index_year，可反推窗口

本脚本把这些编译成**时间约束网络（Simple Temporal Problem）**，做弧一致性传播，
把每条记录从一个点 / 一个无穷区间收窄成一个有限区间，并给出拓扑序（纯先后）。

=============================================================================
输出的三根轴
=============================================================================
  1. 区间轴  lo / hi     —— 每条记录的可能年份范围（传播后收窄）
  2. 序轴    order_rank  —— 拓扑排序得到的纯先后序号（不含任何年份）
  3. 精度轴  precision   —— exact / propagated / interval / frame（可信度分级）

用法:
    python scripts/life_order.py --db cbdb_20260926.sqlite3 --person 1762
    python scripts/life_order.py --db cbdb_20260926.sqlite3 --top 500 --write
    python scripts/life_order.py --db cbdb_20260926.sqlite3 --all --write
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import defaultdict, deque

# --------------------------------------------------------------------------
# 可调参数：领域规则（改这里就能调“推理的胆量”）
# --------------------------------------------------------------------------
INF = 10 ** 6

FRAME_FALLBACK = (-800, 2000)          # CBDB 覆盖 7–19 世纪，留足余量
INDEX_YEAR_MARGIN = 45                 # 只有 index_year 时用 ±45 年（约一代人）
ANCHOR_MARGIN = 45                     # anchor（借对方年份）时的对称误差
DYNASTY_SPAN = 300                     # dynasty 级粗估跨度

# 名号 → 年龄/时序约束
COURTESY_NAME_AGE = (15, 30)           # 字：成年礼
CHILDHOOD_NAME_AGE = (0, 12)           # 小名 / 小字 / 行第
STUDIO_NAME_AGE = (25, 70)             # 室名、別號
RELIGIOUS_NAME_AGE = (20, 70)          # 法號 / 道號
POSTHUMOUS_AFTER_DEATH = (0, 60)       # 諡號：卒后追赠
ENFEoffMENT_AFTER_ENTRY = (0, 50)      # 封爵：入仕之后
BESTOWED_AFTER_ENTRY = (0, 55)         # 賜號 / 尊號 / 廟額

ENTRY_AGE = (12, 60)                   # 科举/入仕年龄
ENTRY_TO_OFFICE = (0, 45)              # 入仕 → 首次任官
OFFICE_GAP = (0, 30)                   # 相邻两任官职
SEQUENCE_GAP = (0, 40)                 # 同阶段内相邻两条

# 亲属世代约束（需要 KINSHIP_CODES 的 upstep / dwnstep / marstep）
# 方向：约束写作 (a, b, gmin, gmax) 表示 b 落在 a 之后 [gmin, gmax] 年内
KIN_ASCENDANT = (0, 60)                # 尊长 → 本人出生：尊长关系最晚成立于本人出生时
KIN_DESCENDANT = (12, 70)              # 本人出生 → 卑幼
KIN_AFFINAL = (15, 70)                 # 本人出生 → 姻親

# 「同类锚点」：用全库同一个官职的出现年份，给无年份的任官记录定界
TYPE_ANCHOR_MIN_SAMPLES = 8            # 样本太少则不启用
TYPE_ANCHOR_PAD = 10                   # 样本少时向两侧放宽的年数

# 开关：是否用「亲属本人的生卒年」给亲属关系定界（A/B 对照用）
USE_KIN_ANCHOR = True

# 交遊对方的生卒年 / 指数年锚点
USE_PEER_ANCHOR = True
PEER_PAD = 10                          # 生卒两侧留的缓冲（避免制造假冲突）
PEER_INDEX_MARGIN = 30                 # 对方只有 index_year 时的对称误差
                                       # （45 年比典型寿命还宽，交集后等于没约束）

# 「成年后才可能发生」的事件：给下界（仅当人生框架来自真实生卒年时启用）
ADULT_START_AGE = {10: 15, 11: 20}     # 身份 / 著作
POST_DEATH_PAD = {10: 20, 11: 40}      # 死后仍可成立的年数

# ALTNAME_CODES.c_name_type_code
NAME_COURTESY = 4
NAME_STUDIO = 5
NAME_POSTHUMOUS = 6
NAME_CHILDHOOD = {7, 9, 10}            # 行第 / 小名 / 小字
NAME_ENFEFFMENT = 8
NAME_BESTOWED = {11, 15, 16}           # 賜號 / 尊號 / 廟額
NAME_RELIGIOUS = {19, 20}              # 法號 / 道號

MAX_ITER = 60


# --------------------------------------------------------------------------
# 取数
# --------------------------------------------------------------------------
EVENT_SQL = """
SELECT c_personid, stage_no, stage, event_label, counterpart_type, counterpart_id,
       counterpart_name_chn, year_from, year_to, time_precision,
       sort_year, sort_seq, sort_year_lo, sort_year_hi, c_source
FROM View_PersonLifeTimeline
WHERE c_personid = ?
ORDER BY stage_no, sort_seq, event_label
"""

FRAME_SQL = """
SELECT c_birthyear, c_deathyear, c_index_year FROM BIOG_MAIN WHERE c_personid = ?
"""

KIN_SQL = """
SELECT k.c_kin_id                              AS kin_id,
       MAX(COALESCE(kc.c_upstep,  0))          AS upstep,
       MAX(COALESCE(kc.c_dwnstep, 0))          AS dwnstep,
       MAX(COALESCE(kc.c_marstep, 0))          AS marstep,
       MAX(b.c_birthyear)                      AS kin_birth,
       MAX(b.c_deathyear)                      AS kin_death
FROM KIN_DATA k
LEFT JOIN KINSHIP_CODES kc ON kc.c_kincode = k.c_kin_code
LEFT JOIN BIOG_MAIN     b  ON b.c_personid = k.c_kin_id
WHERE k.c_personid = ?
GROUP BY k.c_kin_id
"""

# 交遊对方本人的生卒 / 指数年——给「无年份的社会关系」定界
# 交遊是 View_PersonLifeTimeline 里最大的一块（top500 中占 62%），
# 而 ASSOC_DATA 缺年份的比例极高，不加锚点就会全部落回整段人生框架。
ASSOC_PEER_SQL = """
SELECT a.c_assoc_id                     AS peer_id,
       MAX(b.c_birthyear)               AS peer_birth,
       MAX(b.c_deathyear)               AS peer_death,
       MAX(b.c_index_year)              AS peer_index
FROM ASSOC_DATA a
JOIN BIOG_MAIN  b ON b.c_personid = a.c_assoc_id
WHERE a.c_personid = ? AND a.c_assoc_id > 0
GROUP BY a.c_assoc_id
"""

# ---- 全库批量取数（--all 专用）------------------------------------------
# 原因：View_PersonLifeTimeline 是 14 张表的 UNION ALL，SQLite 无法把
#       WHERE c_personid = ? 下推到各分支用索引，逐人查询 = 每人全表扫 300 万行
#       （实测 ~100 ms/人 × 63.8 万人 ≈ 17.8 小时）。必须改成一次有序扫描。
EVENT_SQL_BULK = """
SELECT c_personid, stage_no, stage, event_label, counterpart_type, counterpart_id,
       counterpart_name_chn, year_from, year_to, time_precision,
       sort_year, sort_seq, sort_year_lo, sort_year_hi, c_source
FROM View_PersonLifeTimeline
WHERE c_personid >= ?
ORDER BY c_personid
LIMIT ?
"""

FRAME_BULK_SQL = "SELECT c_personid, c_birthyear, c_deathyear, c_index_year FROM BIOG_MAIN"

KIN_BULK_SQL = """
SELECT k.c_personid, k.c_kin_id,
       MAX(COALESCE(kc.c_upstep,  0)), MAX(COALESCE(kc.c_dwnstep, 0)),
       MAX(COALESCE(kc.c_marstep, 0)),
       MAX(b.c_birthyear), MAX(b.c_deathyear)
FROM KIN_DATA k
LEFT JOIN KINSHIP_CODES kc ON kc.c_kincode = k.c_kin_code
LEFT JOIN BIOG_MAIN     b  ON b.c_personid = k.c_kin_id
GROUP BY k.c_personid, k.c_kin_id
"""

ASSOC_PEER_BULK_SQL = """
SELECT a.c_personid, a.c_assoc_id,
       MAX(b.c_birthyear), MAX(b.c_deathyear), MAX(b.c_index_year)
FROM ASSOC_DATA a
JOIN BIOG_MAIN  b ON b.c_personid = a.c_assoc_id
WHERE a.c_assoc_id > 0
GROUP BY a.c_personid, a.c_assoc_id
"""

BULK_CHUNK = 50000

# 群体统计锚点：某个官职在全库出现过的年份区间
OFFICE_ANCHOR_SQL = """
SELECT c_office_id AS oid,
       MIN(c_firstyear) AS lo, MAX(c_firstyear) AS hi, COUNT(*) AS n
FROM POSTED_TO_OFFICE_DATA
WHERE c_firstyear > 0
GROUP BY c_office_id
"""

COLS = ['c_personid', 'stage_no', 'stage', 'event_label', 'counterpart_type',
        'counterpart_id', 'counterpart_name_chn', 'year_from', 'year_to',
        'time_precision', 'sort_year', 'sort_seq', 'sort_year_lo', 'sort_year_hi',
        'c_source']


def load_office_anchors(conn):
    """全库同一官职的出现年份区间——给个体无年份的任官记录提供外部边界。"""
    out = {}
    for r in conn.execute(OFFICE_ANCHOR_SQL).fetchall():
        if r['n'] < TYPE_ANCHOR_MIN_SAMPLES:
            pad = TYPE_ANCHOR_PAD
        else:
            pad = 0
        out[r['oid']] = (r['lo'] - pad, r['hi'] + pad)
    return out


def isect(a, b):
    """区间求交；无交集时退回 a（不制造假区间）。"""
    lo, hi = max(a[0], b[0]), min(a[1], b[1])
    return (lo, hi) if lo <= hi else a


def frame_from(birth, death, iy):
    if birth and birth > 0 and death and death > 0 and death >= birth:
        return (birth, death), 'birth_death'
    if iy and iy != 0:
        return (iy - INDEX_YEAR_MARGIN, iy + INDEX_YEAR_MARGIN), 'index_year'
    return FRAME_FALLBACK, 'fallback'


def get_frame(conn, pid):
    row = conn.execute(FRAME_SQL, (pid,)).fetchone()
    if row is None:
        return FRAME_FALLBACK, 'none'
    return frame_from(*row)


def peer_span(p):
    """交遊对方的生存窗口：优先生卒年，其次 index_year ± margin。"""
    if not p:
        return None
    pb, pd, piy = p[0], p[1], p[2]
    if pb and pd and pb > 0 and pd > 0 and pd >= pb:
        return (pb - PEER_PAD, pd + PEER_PAD)
    if piy and piy != 0:
        return (piy - PEER_INDEX_MARGIN, piy + PEER_INDEX_MARGIN)
    if pb and pb > 0:
        return (pb - PEER_PAD, pb + 90)
    if pd and pd > 0:
        return (pd - 90, pd + PEER_PAD)
    return None


def prior_interval(ev, frame, kin_info=None, office_anchor=None, peer_info=None):
    prec, sy = ev['time_precision'], ev['sort_year']
    slo, shi = ev['sort_year_lo'], ev['sort_year_hi']
    if prec == 'year' and sy:
        return sy, sy
    if prec == 'nianhao' and slo and shi:
        return slo, shi
    if prec == 'dynasty' and sy:
        return sy, sy + DYNASTY_SPAN

    base = frame
    # 亲属：优先用「对方本人的生卒年」定界，比 index_year ± 45 精确得多
    if USE_KIN_ANCHOR and ev['stage_no'] == 3 and kin_info:
        kb, kd = kin_info[3], kin_info[4]
        if kb and kd and kb > 0 and kd > 0 and kd >= kb:
            base = isect(base, (kb, kd))
        elif prec == 'anchor' and sy:
            base = isect(base, (sy - ANCHOR_MARGIN, sy + ANCHOR_MARGIN))
    elif prec == 'anchor' and sy:
        return sy - ANCHOR_MARGIN, sy + ANCHOR_MARGIN

    # 交遊：社会关系必须落在「双方生命的交集」内
    if USE_PEER_ANCHOR and ev['stage_no'] == 9 and peer_info:
        sp = peer_span(peer_info)
        if sp:
            base = isect(base, sp)

    # 无年份的任官/任职地：用「同一个官职在全库的活跃年份」进一步定界
    if office_anchor and ev['stage_no'] in (7, 8):
        oid = ev['counterpart_id']
        if oid and oid in office_anchor:
            base = isect(base, office_anchor[oid])
    return base


# --------------------------------------------------------------------------
# 约束生成
# --------------------------------------------------------------------------
def classify_kin(events, kin_map):
    """把亲属事件分成 姻亲 / 尊长 / 卑幼（upstep 等为 99 表示 CBDB 的“未知”哨兵）。"""
    asc, desc, aff = set(), set(), set()
    for i, ev in enumerate(events):
        if ev['stage_no'] != 3:
            continue
        info = kin_map.get(ev['counterpart_id'])
        if not info:
            continue
        up, down, mar = info[0], info[1], info[2]
        if mar and mar < 90:
            aff.add(i)
        elif up and up < 90:
            asc.add(i)
        elif down and down < 90:
            desc.add(i)
    return asc, desc, aff


def frame_for(i, ev, frame, asc, desc, frame_src='birth_death'):
    """人生框架按事件性质放宽：出生前成立的关系向下放宽，死后成立的关系向上放宽。"""
    lo, hi = frame
    if i in asc:
        return (lo - 60, hi)
    if i in desc:
        return (lo, hi + 70)
    if ev['stage_no'] == 2 and ev['counterpart_id'] == NAME_POSTHUMOUS:
        return (lo, hi + 60)

    sn = ev['stage_no']
    # 只有框架来自真实生卒年时，「成年后」「死后若干年」才有意义
    if frame_src == 'birth_death':
        if sn in ADULT_START_AGE:
            lo = lo + ADULT_START_AGE[sn]
    if sn in POST_DEATH_PAD:
        hi = hi + POST_DEATH_PAD[sn]
    return (lo, hi) if lo <= hi else frame


def build_constraints(events, kin_map):
    """返回 [(a, b, gmin, gmax, rule)]：b 落在 a 之后 [gmin, gmax] 年内。"""
    e = []
    add = e.append

    by_stage = defaultdict(list)
    for i, ev in enumerate(events):
        by_stage[ev['stage_no']].append(i)

    birth = by_stage.get(1, [])
    death = by_stage.get(14, [])
    entry = by_stage.get(6, [])
    office = by_stage.get(7, [])
    addr = by_stage.get(8, [])
    names = by_stage.get(2, [])
    kins = by_stage.get(3, [])

    # ---- 先把亲属按「姻亲 / 尊长 / 卑幼」分类 ----
    kin_asc, kin_desc, kin_affinal = classify_kin(events, kin_map)

    # 豁免：出生前就已成立的关系（尊长亲属）不受「生最早」约束
    #       死后仍可成立的关系（諡號、著作、卑幼亲属）不受「卒最晚」约束
    exempt_birth = set(kin_asc)
    exempt_death = set(kin_desc) | {i for i in names
                                    if events[i]['counterpart_id'] == NAME_POSTHUMOUS} \
                   | set(by_stage.get(11, []))

    # R1/R2 生最早、卒最晚
    if birth:
        b = birth[0]
        for i in range(len(events)):
            if i != b and i not in exempt_birth:
                add((b, i, 0, INF, 'birth_first'))
    if death:
        d = death[0]
        for i in range(len(events)):
            if i != d and i not in exempt_death:
                add((i, d, 0, INF, 'death_last'))

    # R3 名号年龄/时序
    if birth:
        b = birth[0]
        for i in names:
            code = events[i]['counterpart_id']
            if code == NAME_COURTESY:
                add((b, i, *COURTESY_NAME_AGE, 'courtesy_name'))
            elif code in NAME_CHILDHOOD:
                add((b, i, *CHILDHOOD_NAME_AGE, 'childhood_name'))
            elif code == NAME_STUDIO:
                add((b, i, *STUDIO_NAME_AGE, 'studio_name'))
            elif code in NAME_RELIGIOUS:
                add((b, i, *RELIGIOUS_NAME_AGE, 'religious_name'))
    if death:
        for i in names:
            if events[i]['counterpart_id'] == NAME_POSTHUMOUS:
                add((death[0], i, *POSTHUMOUS_AFTER_DEATH, 'posthumous_name'))
    if entry:
        for i in names:
            code = events[i]['counterpart_id']
            if code == NAME_ENFEFFMENT:
                add((entry[0], i, *ENFEoffMENT_AFTER_ENTRY, 'enfeoffment'))
            elif code in NAME_BESTOWED:
                add((entry[0], i, *BESTOWED_AFTER_ENTRY, 'bestowed_name'))

    # R4 入仕年龄 + 入仕早于任官
    if birth and entry:
        for i in entry:
            add((birth[0], i, *ENTRY_AGE, 'entry_age'))
    if entry and office:
        for i in office:
            add((entry[0], i, *ENTRY_TO_OFFICE, 'entry_before_office'))

    # R5 亲属世代
    if birth:
        for i in kin_asc:
            add((i, birth[0], *KIN_ASCENDANT, 'kin_ascendant'))
        for i in kin_desc:
            add((birth[0], i, *KIN_DESCENDANT, 'kin_descendant'))
        for i in kin_affinal:
            add((birth[0], i, *KIN_AFFINAL, 'kin_affinal'))

    # R6 任官序列（按 sort_seq / 年份）
    def seq_chain(idxs, gap, rule):
        if len(idxs) < 2:
            return
        ordered = sorted(idxs, key=lambda k: (events[k]['sort_seq'] or 0,
                                              events[k]['sort_year'] or INF))
        for a, b in zip(ordered, ordered[1:]):
            add((a, b, gap[0], gap[1], rule))

    # 只有真正带 c_sequence 的任官才有位置信息；sort_seq=0 的不能排进链里
    seq_chain([i for i in office if (events[i]['sort_seq'] or 0) > 0],
              OFFICE_GAP, 'office_sequence')

    # R7 任職地跟随同年份的任官
    if office and addr:
        offices = sorted(office, key=lambda k: (events[k]['sort_year'] or INF))
        for i in addr:
            ay = events[i]['sort_year']
            if not ay:
                continue
            best, bestd = None, None
            for k in offices:
                oy = events[k]['sort_year']
                if not oy:
                    continue
                d = abs(oy - ay)
                if bestd is None or d < bestd:
                    best, bestd = k, d
            if best is not None and bestd is not None and bestd <= 2:
                e.append((best, i, 0, 0, 'posting_addr_sync'))

    # R8 同阶段内 c_sequence 相邻
    for st in (4, 6, 7, 10, 12, 13):
        idxs = [i for i in by_stage.get(st, [])
                if events[i]['time_precision'] in ('sequence', 'undated')
                and (events[i]['sort_seq'] or 0) > 0]
        seq_chain(idxs, SEQUENCE_GAP, 'sequence_order')

    return e


# --------------------------------------------------------------------------
# 弧一致性传播
# --------------------------------------------------------------------------
def propagate(lo, hi, prior_lo, prior_hi, locked, edges):
    """
    locked=True 的节点是「数据直接给的确切年份」——只允许它影响别人，不允许被改写。
    收窄后若 lo>hi 视为约束矛盾：回退到先验区间并标记，而不是静默折叠成一个假年份。
    """
    for _ in range(MAX_ITER):
        changed = False
        for (a, b, gmin, gmax, _r) in edges:
            if not locked[b]:
                v = lo[a] + gmin
                if lo[b] < v:
                    lo[b] = v; changed = True
                v = hi[a] + gmax
                if hi[b] > v:
                    hi[b] = v; changed = True
            if not locked[a]:
                v = lo[b] - gmax
                if lo[a] < v:
                    lo[a] = v; changed = True
                v = hi[b] - gmin
                if hi[a] > v:
                    hi[a] = v; changed = True
        if not changed:
            break

    conflict = [0] * len(lo)
    for i in range(len(lo)):
        if lo[i] > hi[i] and not locked[i]:
            lo[i], hi[i] = prior_lo[i], prior_hi[i]
            conflict[i] = 1

    violations = 0
    for (a, b, gmin, gmax, _r) in edges:
        if hi[b] < lo[a] + gmin or lo[b] > hi[a] + gmax:
            violations += 1
    return lo, hi, conflict, violations


def topo_order(n, edges):
    indeg = [0] * n
    adj = defaultdict(list)
    for (a, b, *_r) in edges:
        if a != b and b not in adj[a]:
            adj[a].append(b)
            indeg[b] += 1
    q = deque([i for i in range(n) if indeg[i] == 0])
    rank, seen = [0] * n, 0
    while q:
        i = q.popleft()
        rank[i] = seen; seen += 1
        for j in adj[i]:
            indeg[j] -= 1
            if indeg[j] == 0:
                q.append(j)
    for i in range(n):
        if indeg[i] > 0:
            rank[i] = seen; seen += 1
    return rank


# --------------------------------------------------------------------------
def preload(conn):
    """--all 专用：把人生框架 / 亲属 / 交遊对方一次性读进内存。

    逐人查询在 UNION ALL 视图上会退化成全表扫描（~100 ms/人），必须先预加载。
    """
    print('预加载 BIOG_MAIN 生卒 / index_year ...', file=sys.stderr)
    frames = {r[0]: (r[1], r[2], r[3]) for r in conn.execute(FRAME_BULK_SQL)}
    print(f'  {len(frames):,} 人', file=sys.stderr)

    print('预加载 KIN_DATA ...', file=sys.stderr)
    kin = {}
    for pid, kid, up, dn, mar, kb, kd in conn.execute(KIN_BULK_SQL):
        kin.setdefault(pid, {})[kid] = (up, dn, mar, kb, kd)
    print(f'  {len(kin):,} 人有亲属', file=sys.stderr)

    peer = {}
    if USE_PEER_ANCHOR:
        print('预加载 ASSOC_DATA ...', file=sys.stderr)
        for pid, aid, pb, pd, piy in conn.execute(ASSOC_PEER_BULK_SQL):
            peer.setdefault(pid, {})[aid] = (pb, pd, piy)
        print(f'  {len(peer):,} 人有交遊', file=sys.stderr)
    return frames, kin, peer


def iter_event_chunks(conn):
    """按 c_personid 有序、分块取事件；返回 (pid, events) 流，内存受块大小限制。

    块末尾那个人的记录可能不完整——下块从他重新开始，重取后覆盖。
    """
    start = 0
    while True:
        rows = conn.execute(EVENT_SQL_BULK, (start, BULK_CHUNK)).fetchall()
        if not rows:
            return
        cur, buf = rows[0]['c_personid'], []
        for r in rows:
            p = r['c_personid']
            if p != cur:
                yield cur, buf
                cur, buf = p, []
            buf.append({c: r[c] for c in COLS})
        if len(rows) < BULK_CHUNK:
            yield cur, buf
            return
        # 块末尾那个人可能被截断，留到下一块重取（单人最多 2,705 条 << 块大小）
        start = cur


def solve_person(conn, pid, events, kin_map, office_anchor=None, peer_map=None,
                 frame=None, frame_src=None):
    if frame is None:
        frame, frame_src = get_frame(conn, pid)
    n = len(events)
    asc, desc, _aff = classify_kin(events, kin_map)
    lo, hi = [], []
    for i, ev in enumerate(events):
        a, b = prior_interval(ev, frame_for(i, ev, frame, asc, desc, frame_src),
                              kin_map.get(ev['counterpart_id']) if ev['stage_no'] == 3 else None,
                              office_anchor,
                              (peer_map or {}).get(ev['counterpart_id'])
                              if ev['stage_no'] == 9 else None)
        lo.append(a); hi.append(b)
    prior_lo, prior_hi = list(lo), list(hi)

    # 硬锚点：数据直接给了确切公历年的记录
    locked = [ev['time_precision'] == 'year' and ev['sort_year'] for ev in events]

    edges = build_constraints(events, kin_map)
    lo, hi, conflict, violations = propagate(lo, hi, prior_lo, prior_hi, locked, edges)
    rank = topo_order(n, edges)

    out = []
    for i, ev in enumerate(events):
        pw = prior_hi[i] - prior_lo[i]
        w = hi[i] - lo[i]
        if w <= 0:
            prec = 'exact'
        elif w < pw:
            prec = 'propagated'
        elif pw >= 2000:
            prec = 'frame'
        else:
            prec = 'interval'
        out.append({
            'c_personid': pid, 'order_rank': rank[i],
            'stage_no': ev['stage_no'], 'stage': ev['stage'],
            'event_label': ev['event_label'],
            'counterpart_name_chn': ev['counterpart_name_chn'],
            'time_precision': ev['time_precision'],
            'prior_lo': prior_lo[i], 'prior_hi': prior_hi[i], 'prior_width': pw,
            'lo': lo[i], 'hi': hi[i], 'width': w, 'narrowed': pw - w,
            'precision': prec, 'conflict': conflict[i],
            'locked': int(locked[i]), 'frame_src': frame_src,
            'c_source': ev['c_source'],
        })
    return out, len(edges), violations, frame_src


# --------------------------------------------------------------------------
DDL = """
CREATE TABLE IF NOT EXISTS LIFE_EVENT_RESOLVED (
    c_personid INTEGER, order_rank INTEGER,
    stage_no INTEGER, stage TEXT, event_label TEXT, counterpart_name_chn TEXT,
    time_precision TEXT,
    prior_lo INTEGER, prior_hi INTEGER, prior_width INTEGER,
    lo INTEGER, hi INTEGER, width INTEGER,
    narrowed INTEGER, precision TEXT, conflict INTEGER, locked INTEGER,
    frame_src TEXT, c_source INTEGER
);
"""
IDX = (
    "CREATE INDEX IF NOT EXISTS idx_life_resolved_pid "
    "ON LIFE_EVENT_RESOLVED(c_personid, order_rank);",
    "CREATE INDEX IF NOT EXISTS idx_life_resolved_prec "
    "ON LIFE_EVENT_RESOLVED(precision);",
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True)
    ap.add_argument('--person', type=int)
    ap.add_argument('--persons')
    ap.add_argument('--top', type=int)
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--limit-print', type=int, default=15)
    ap.add_argument('--no-kin-anchor', action='store_true',
                    help='A/B 对照：关闭「亲属本人生卒年」定界')
    ap.add_argument('--no-peer-anchor', action='store_true',
                    help='A/B 对照：关闭「交遊对方生卒年」定界')
    args = ap.parse_args()

    global USE_KIN_ANCHOR, USE_PEER_ANCHOR
    if args.no_kin_anchor:
        USE_KIN_ANCHOR = False
    if args.no_peer_anchor:
        USE_PEER_ANCHOR = False

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    office_anchor = load_office_anchors(conn)
    print(f'同类锚点(官职): {len(office_anchor):,} 个', file=sys.stderr)

    bulk = False
    if args.person or args.persons:
        ids = [args.person] if args.person else [int(x) for x in args.persons.split(',')]
    elif args.top:
        ids = [r[0] for r in conn.execute(
            "SELECT c_personid FROM View_PersonLifeTimeline GROUP BY c_personid "
            "ORDER BY COUNT(*) DESC LIMIT ?", (args.top,)).fetchall()]
    elif args.all:
        ids = []
        bulk = True
    else:
        ap.error('需要 --person / --persons / --top / --all 之一')
        return

    if not bulk:
        print(f'目标人物: {len(ids):,}', file=sys.stderr)
    else:
        print('目标人物: 全库（批量流式扫描）', file=sys.stderr)

    frames = kins = peers = None
    if bulk:
        frames, kins, peers = preload(conn)

    if args.write:
        conn.execute('DROP TABLE IF EXISTS LIFE_EVENT_RESOLVED')
        conn.execute(DDL)

    st = dict(events=0, edges=0, violations=0, conflicts=0, narrowed=0,
              prec=defaultdict(int), frame=defaultdict(int),
              width_before=0, width_after=0, dated_before=0, dated_after=0)
    buf, printed = [], 0

    def load_one(pid):
        """逐人查询路径（--person / --persons / --top）"""
        events = [{c: r[c] for c in COLS}
                  for r in conn.execute(EVENT_SQL, (pid,)).fetchall()]
        if not events:
            return None
        kin_map = {r['kin_id']: (r['upstep'], r['dwnstep'], r['marstep'],
                                 r['kin_birth'], r['kin_death'])
                   for r in conn.execute(KIN_SQL, (pid,)).fetchall()}
        peer_map = None
        if USE_PEER_ANCHOR:
            peer_map = {r['peer_id']: (r['peer_birth'], r['peer_death'], r['peer_index'])
                        for r in conn.execute(ASSOC_PEER_SQL, (pid,)).fetchall()}
        return events, kin_map, peer_map, None, None

    def bulk_one(pid, events):
        """批量路径（--all）：一切都从预加载的字典里取"""
        frame, fsrc = frame_from(*frames.get(pid, (None, None, None)))
        return events, kins.get(pid, {}), peers.get(pid, {}), frame, fsrc

    if bulk:
        src = ((pid, bulk_one(pid, ev)) for pid, ev in iter_event_chunks(conn))
    else:
        src = ((pid, load_one(pid)) for pid in ids)

    nproc = 0
    for pid, payload in src:
        if payload is None:
            continue
        events, kin_map, peer_map, frame, frame_src = payload
        nproc += 1
        if nproc % 100000 == 0:
            print(f'  已处理 {nproc:,} 人 / {st["events"]:,} 事件', file=sys.stderr)
        res, nedges, viol, fsrc = solve_person(conn, pid, events, kin_map,
                                               office_anchor, peer_map,
                                               frame, frame_src)

        st['events'] += len(res); st['edges'] += nedges; st['violations'] += viol
        st['frame'][fsrc] += 1
        for r in res:
            st['narrowed'] += r['narrowed']
            st['prec'][r['precision']] += 1
            st['conflicts'] += r['conflict']
            st['width_before'] += r['prior_width']
            st['width_after'] += r['width']
            if r['prior_width'] <= 50:
                st['dated_before'] += 1
            if r['width'] <= 50:
                st['dated_after'] += 1

        if args.write:
            buf.extend(res)
            if len(buf) > 50000:
                keys = ', :'.join(res[0].keys())
                conn.executemany(f'INSERT INTO LIFE_EVENT_RESOLVED VALUES (:{keys})', buf)
                buf.clear(); conn.commit()
        if printed < args.limit_print and not bulk and len(ids) <= 5:
            printed += 1
            print_person(pid, res, nedges, viol)

    if args.write and buf:
        keys = ', :'.join(buf[0].keys())
        conn.executemany(f'INSERT INTO LIFE_EVENT_RESOLVED VALUES (:{keys})', buf)
        conn.commit()

    if args.write:
        print('建索引中 ...', file=sys.stderr)
        for s in IDX:
            conn.execute(s)
        conn.commit()

    n = st['events'] or 1
    print('\n========== 汇总 ==========', file=sys.stderr)
    print(f"人物数        : {nproc:,}", file=sys.stderr)
    print(f"事件数        : {st['events']:,}", file=sys.stderr)
    print(f"约束边数      : {st['edges']:,}", file=sys.stderr)
    print(f"约束违反      : {st['violations']:,}  (数据自相矛盾，已保留原区间)", file=sys.stderr)
    print(f"冲突回退      : {st['conflicts']:,}", file=sys.stderr)
    print(f"平均区间宽度  : {st['width_before'] / n:.1f} 年 → {st['width_after'] / n:.1f} 年"
          f"  (收窄 {(1 - st['width_after'] / max(st['width_before'], 1)):.1%})", file=sys.stderr)
    print(f"窄区间(≤50年) : {st['dated_before']:,} → {st['dated_after']:,} 条"
          f"  (+{st['dated_after'] - st['dated_before']:,})", file=sys.stderr)
    tot = sum(st['prec'].values()) or 1
    print('精度分级      : ' + ', '.join(
        f"{k} {v:,} ({v / tot:.1%})" for k, v in sorted(st['prec'].items())), file=sys.stderr)
    print('人生框架来源  : ' + str(dict(st['frame'])), file=sys.stderr)


def print_person(pid, res, nedges, viol):
    print(f'\n========== c_personid={pid}  事件 {len(res)} 条  约束 {nedges} 条  '
          f'违反 {viol}  框架={res[0]["frame_src"]} ==========')
    print(f'{"序":>4} {"阶段":<7} {"区间":<15} {"宽":>4} {"收窄":>5} {"精度":<11} 事件')
    print('-' * 100)
    for r in sorted(res, key=lambda x: (x['lo'], x['order_rank'])):
        iv = f"{r['lo']}" if r['width'] <= 0 else f"[{r['lo']},{r['hi']}]"
        flag = '!' if r['conflict'] else ('*' if r['locked'] else ' ')
        print(f"{r['order_rank']:>4} {r['stage']:<7} {iv:<15} {r['width']:>4} "
              f"{r['narrowed']:>5} {r['precision']:<11} {flag} {(r['event_label'] or '')[:40]}")


if __name__ == '__main__':
    main()
