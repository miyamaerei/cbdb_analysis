#!/usr/bin/env bash

# Create three analyst-oriented CBDB views that are NOT part of the upstream
# create_views.sh set:
#
#   View_KinshipGenealogyData 族谱视角：人物 + 亲属 + 世代差 + 宗族(郡望/同姓) + 史料出处
#   View_CountyPeopleData     县城视角：县级政区 + 上级府州路省 + 人物 + 关系类型
#   View_TextAssociationData  单本文献视角：一本书里记录的全部关联（社会关系/亲属/入仕/任官/身份/地理/著作）
#
# Usage: scripts/create_custom_views.sh path/to/database.db
#
# Requires: sqlite3 CLI on PATH.
# Idempotent: each view is dropped before it is recreated.

set -euo pipefail
IFS=$'\n\t'

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 path/to/database.db" >&2
    exit 1
fi

DB_PATH=$1

if [[ ! -f "$DB_PATH" ]]; then
    echo "Error: database file '$DB_PATH' does not exist." >&2
    exit 1
fi

if ! command -v sqlite3 >/dev/null 2>&1; then
    echo "Error: sqlite3 is required but not installed or not on PATH." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Supporting indexes — created FIRST, before any view is queried.
#
# The raw CBDB export carries almost no indexes, and these views are meant to be
# filtered by c_personid / c_addr_id / c_source. Without an index on
# ADDRESSES(c_addr_id) the correlated hierarchy lookup in View_CountyPeopleData
# degrades into a full table scan per row (hours instead of seconds).
# ---------------------------------------------------------------------------
echo "Creating supporting indexes (IF NOT EXISTS)..."
sqlite3 "$DB_PATH" <<'SQL'
CREATE INDEX IF NOT EXISTS idx_addresses_addr          ON ADDRESSES(c_addr_id, c_belongs_firstyear, c_belongs_lastyear);
CREATE INDEX IF NOT EXISTS idx_assoc_data_source       ON ASSOC_DATA(c_source);
CREATE INDEX IF NOT EXISTS idx_kin_data_source         ON KIN_DATA(c_source);
CREATE INDEX IF NOT EXISTS idx_entry_data_source       ON ENTRY_DATA(c_source);
CREATE INDEX IF NOT EXISTS idx_posted_office_source    ON POSTED_TO_OFFICE_DATA(c_source);
CREATE INDEX IF NOT EXISTS idx_status_data_source      ON STATUS_DATA(c_source);
CREATE INDEX IF NOT EXISTS idx_biog_addr_source        ON BIOG_ADDR_DATA(c_source);
CREATE INDEX IF NOT EXISTS idx_biog_text_source        ON BIOG_TEXT_DATA(c_source);
CREATE INDEX IF NOT EXISTS idx_kin_data_person         ON KIN_DATA(c_personid);
CREATE INDEX IF NOT EXISTS idx_kin_data_kin            ON KIN_DATA(c_kin_id);
CREATE INDEX IF NOT EXISTS idx_assoc_data_person       ON ASSOC_DATA(c_personid);
CREATE INDEX IF NOT EXISTS idx_biog_addr_person        ON BIOG_ADDR_DATA(c_personid);
CREATE INDEX IF NOT EXISTS idx_biog_addr_addr          ON BIOG_ADDR_DATA(c_addr_id);
SQL
echo "Indexes ready."

# ---------------------------------------------------------------------------
# View_KinshipGenealogyData
# ---------------------------------------------------------------------------
# One row per recorded kinship link (KIN_DATA), enriched with:
#   * both parties' names, surnames, lifespans, dynasty
#   * the standardised generation distance (c_upstep - c_dwnstep)
#   * a coarse lineage class (直系尊長 / 直系卑幼 / 旁系 / 姻親)
#   * clan signals: choronym (郡望) of ego, and whether both share a surname
#   * the source text and page that attests the link
#
# Notes:
#   * KIN_DATA stores relations one-way ("A has B as father"); to build a full
#     tree you must also read the reverse direction, or UNION both directions.
#   * c_upstep / c_dwnstep use 99 (and 100) as "unknown" sentinels, so
#     generation_offset is NULLed out when either side is unknown.
# ---------------------------------------------------------------------------
echo "Creating view View_KinshipGenealogyData..."
sqlite3 "$DB_PATH" <<'SQL'
DROP VIEW IF EXISTS View_KinshipGenealogyData;
CREATE VIEW View_KinshipGenealogyData AS
SELECT
    k.c_personid                                    AS c_personid,
    ego.c_name_chn                                  AS person_name_chn,
    ego.c_name                                      AS person_name,
    ego.c_surname_chn                               AS person_surname_chn,
    ego.c_female                                    AS person_female,
    ego.c_index_year                                AS person_index_year,
    ego.c_birthyear                                 AS person_birthyear,
    ego.c_deathyear                                 AS person_deathyear,
    d1.c_dynasty_chn                                AS person_dynasty_chn,
    ch.c_choronym_chn                               AS person_choronym_chn,
    ad1.c_name_chn                                  AS person_addr_chn,

    k.c_kin_id                                      AS kin_personid,
    alt.c_name_chn                                  AS kin_name_chn,
    alt.c_name                                      AS kin_name,
    alt.c_surname_chn                               AS kin_surname_chn,
    alt.c_female                                    AS kin_female,
    alt.c_index_year                                AS kin_index_year,
    alt.c_birthyear                                 AS kin_birthyear,
    alt.c_deathyear                                 AS kin_deathyear,
    d2.c_dynasty_chn                                AS kin_dynasty_chn,
    ad2.c_name_chn                                  AS kin_addr_chn,
    CASE WHEN alt.c_personid IS NULL THEN 0 ELSE 1 END AS kin_identified,

    k.c_kin_code                                    AS c_kin_code,
    kc.c_kinrel_chn                                 AS kinrel_chn,
    kc.c_kinrel                                     AS kinrel,
    kc.c_upstep                                     AS c_upstep,
    kc.c_dwnstep                                    AS c_dwnstep,
    kc.c_colstep                                    AS c_colstep,
    kc.c_marstep                                    AS c_marstep,

    CASE
        WHEN kc.c_upstep >= 90 OR kc.c_dwnstep >= 90 THEN NULL
        ELSE kc.c_upstep - kc.c_dwnstep
    END                                             AS generation_offset,

    CASE
        WHEN kc.c_upstep >= 90 OR kc.c_dwnstep >= 90 THEN '未詳'
        WHEN kc.c_marstep  > 0                      THEN '姻親'
        WHEN kc.c_colstep  > 0                      THEN '旁系'
        WHEN kc.c_upstep   > 0                      THEN '直系尊長'
        WHEN kc.c_dwnstep  > 0                      THEN '直系卑幼'
        ELSE '同輩/其他'
    END                                             AS lineage_type,

    CASE
        WHEN ego.c_surname_chn IS NULL OR alt.c_surname_chn IS NULL THEN NULL
        WHEN ego.c_surname_chn = ''    OR alt.c_surname_chn = ''    THEN NULL
        WHEN ego.c_surname_chn = alt.c_surname_chn                  THEN 1
        ELSE 0
    END                                             AS same_surname,

    k.c_source                                      AS c_source,
    src.c_title_chn                                 AS source_title_chn,
    src.c_title                                     AS source_title,
    k.c_pages                                       AS c_pages,
    k.c_notes                                       AS c_notes
FROM KIN_DATA AS k
LEFT JOIN BIOG_MAIN      AS ego ON ego.c_personid = k.c_personid
LEFT JOIN BIOG_MAIN      AS alt ON alt.c_personid = k.c_kin_id
LEFT JOIN KINSHIP_CODES  AS kc  ON kc.c_kincode   = k.c_kin_code
LEFT JOIN DYNASTIES      AS d1  ON d1.c_dy        = ego.c_dy
LEFT JOIN DYNASTIES      AS d2  ON d2.c_dy        = alt.c_dy
LEFT JOIN CHORONYM_CODES AS ch  ON ch.c_choronym_code = ego.c_choronym_code
LEFT JOIN ADDR_CODES     AS ad1 ON ad1.c_addr_id  = ego.c_index_addr_id
LEFT JOIN ADDR_CODES     AS ad2 ON ad2.c_addr_id  = alt.c_index_addr_id
LEFT JOIN TEXT_CODES     AS src ON src.c_textid   = k.c_source;
SQL
echo "Finished view View_KinshipGenealogyData."

# ---------------------------------------------------------------------------
# View_CountyPeopleData
# ---------------------------------------------------------------------------
# One row per (person, county, address-relation) link, restricted to county-grade
# administrative units (c_admin_type = Xian / xian / County — note the casing is
# inconsistent in the source data).
#
# The superior administrative chain (府/州 → 路/省 → …) comes from ADDRESSES.
# ADDRESSES holds ~2.1 rows per c_addr_id (one per affiliation period), so joining
# it on c_addr_id alone would multiply people. We therefore pick a single
# representative hierarchy row per address:
#   1. prefer the period covering the person's index year
#   2. otherwise the longest-lived affiliation period
# If you need period-exact hierarchies, query ADDRESSES directly and filter by year.
# ---------------------------------------------------------------------------
echo "Creating view View_CountyPeopleData..."
sqlite3 "$DB_PATH" <<'SQL'
DROP VIEW IF EXISTS View_CountyPeopleData;
CREATE VIEW View_CountyPeopleData AS
SELECT
    p.c_personid                                    AS c_personid,
    p.c_name_chn                                    AS person_name_chn,
    p.c_name                                        AS person_name,
    p.c_surname_chn                                 AS person_surname_chn,
    p.c_female                                      AS person_female,
    p.c_index_year                                  AS c_index_year,
    p.c_birthyear                                   AS c_birthyear,
    p.c_deathyear                                   AS c_deathyear,
    dy.c_dynasty_chn                                AS dynasty_chn,

    a.c_addr_id                                     AS county_addr_id,
    a.c_name_chn                                    AS county_name_chn,
    a.c_name                                        AS county_name,
    a.c_admin_type                                  AS county_admin_type,
    a.c_firstyear                                   AS county_firstyear,
    a.c_lastyear                                    AS county_lastyear,
    a.x_coord                                       AS county_x_coord,
    a.y_coord                                       AS county_y_coord,

    h.belongs1_Name_chn                             AS parent1_name_chn,
    h.belongs2_Name_chn                             AS parent2_name_chn,
    h.belongs3_Name_chn                             AS parent3_name_chn,
    h.belongs4_Name_chn                             AS parent4_name_chn,
    h.belongs5_Name_chn                             AS parent5_name_chn,
    h.c_belongs_firstyear                           AS belongs_firstyear,
    h.c_belongs_lastyear                            AS belongs_lastyear,

    b.c_addr_type                                   AS addr_relation_code,
    bac.c_addr_desc_chn                             AS addr_relation_chn,
    b.c_firstyear                                   AS relation_firstyear,
    b.c_lastyear                                    AS relation_lastyear,
    b.c_natal                                       AS c_natal,

    b.c_source                                      AS c_source,
    src.c_title_chn                                 AS source_title_chn,
    b.c_pages                                       AS c_pages,
    b.c_notes                                       AS c_notes
FROM BIOG_ADDR_DATA AS b
JOIN ADDR_CODES     AS a   ON a.c_addr_id = b.c_addr_id
JOIN BIOG_MAIN      AS p   ON p.c_personid = b.c_personid
LEFT JOIN BIOG_ADDR_CODES AS bac ON bac.c_addr_type = b.c_addr_type
LEFT JOIN DYNASTIES AS dy  ON dy.c_dy = p.c_dy
LEFT JOIN ADDRESSES AS h   ON h.rowid = (
        SELECT ah.rowid
        FROM ADDRESSES AS ah
        WHERE ah.c_addr_id = a.c_addr_id
        ORDER BY
            CASE WHEN p.c_index_year BETWEEN ah.c_belongs_firstyear
                                        AND ah.c_belongs_lastyear THEN 0 ELSE 1 END,
            (ah.c_belongs_lastyear - ah.c_belongs_firstyear) DESC,
            ah.c_belongs_firstyear
        LIMIT 1
    )
LEFT JOIN TEXT_CODES AS src ON src.c_textid = b.c_source
WHERE LOWER(a.c_admin_type) = 'xian' OR a.c_admin_type = 'County';
SQL
echo "Finished view View_CountyPeopleData."

# ---------------------------------------------------------------------------
# View_TextAssociationData
# ---------------------------------------------------------------------------
# "Everything this one book attests." A single denormalised stream of every
# relation CBDB recorded, keyed by the source text (c_source -> TEXT_CODES).
# Filter by c_source (a c_textid) to reconstruct a book's social world.
#
# relation_category is one of:
#   社會關係 / 親屬關係 / 入仕 / 任官 / 社會身份 / 人物地理 / 著作角色
#
# counterpart_* is the other end of the relation. counterpart_is_person = 1 when
# the other end is another historical person (社會關係, 親屬關係), otherwise it is
# a code (office, entry route, status, address, text).
# ---------------------------------------------------------------------------
echo "Creating view View_TextAssociationData..."
sqlite3 "$DB_PATH" <<'SQL'
DROP VIEW IF EXISTS View_TextAssociationData;
CREATE VIEW View_TextAssociationData AS

-- 1. 社会关系（非亲属）
SELECT
    a.c_source                                      AS c_source,
    src.c_title_chn                                 AS source_title_chn,
    src.c_title                                     AS source_title,
    src.c_text_dy                                   AS source_dy,
    '社會關係'                                       AS relation_category,
    ac.c_assoc_desc_chn                             AS relation_desc_chn,
    a.c_personid                                    AS c_personid,
    p.c_name_chn                                    AS person_name_chn,
    p.c_name                                        AS person_name,
    a.c_assoc_id                                    AS counterpart_id,
    q.c_name_chn                                    AS counterpart_name_chn,
    q.c_name                                        AS counterpart_name,
    1                                               AS counterpart_is_person,
    a.c_assoc_first_year                            AS c_year,
    a.c_pages                                       AS c_pages,
    a.c_notes                                       AS c_notes
FROM ASSOC_DATA  AS a
LEFT JOIN ASSOC_CODES AS ac  ON ac.c_assoc_code = a.c_assoc_code
LEFT JOIN BIOG_MAIN   AS p   ON p.c_personid = a.c_personid
LEFT JOIN BIOG_MAIN   AS q   ON q.c_personid = a.c_assoc_id
LEFT JOIN TEXT_CODES  AS src ON src.c_textid = a.c_source

UNION ALL

-- 2. 亲属关系
SELECT
    k.c_source, src.c_title_chn, src.c_title, src.c_text_dy,
    '親屬關係',
    kc.c_kinrel_chn,
    k.c_personid, p.c_name_chn, p.c_name,
    k.c_kin_id,  q.c_name_chn, q.c_name,
    1,
    NULL,
    k.c_pages, k.c_notes
FROM KIN_DATA AS k
LEFT JOIN KINSHIP_CODES AS kc  ON kc.c_kincode = k.c_kin_code
LEFT JOIN BIOG_MAIN     AS p   ON p.c_personid = k.c_personid
LEFT JOIN BIOG_MAIN     AS q   ON q.c_personid = k.c_kin_id
LEFT JOIN TEXT_CODES    AS src ON src.c_textid = k.c_source

UNION ALL

-- 3. 入仕
SELECT
    e.c_source, src.c_title_chn, src.c_title, src.c_text_dy,
    '入仕',
    ec.c_entry_desc_chn,
    e.c_personid, p.c_name_chn, p.c_name,
    e.c_entry_code, ec.c_entry_desc_chn, ec.c_entry_desc,
    0,
    e.c_year,
    e.c_pages, e.c_notes
FROM ENTRY_DATA AS e
LEFT JOIN ENTRY_CODES AS ec  ON ec.c_entry_code = e.c_entry_code
LEFT JOIN BIOG_MAIN   AS p   ON p.c_personid = e.c_personid
LEFT JOIN TEXT_CODES  AS src ON src.c_textid = e.c_source

UNION ALL

-- 4. 任官
SELECT
    o.c_source, src.c_title_chn, src.c_title, src.c_text_dy,
    '任官',
    oc.c_office_chn,
    o.c_personid, p.c_name_chn, p.c_name,
    o.c_office_id, oc.c_office_chn, oc.c_office_pinyin,
    0,
    o.c_firstyear,
    o.c_pages, o.c_notes
FROM POSTED_TO_OFFICE_DATA AS o
LEFT JOIN OFFICE_CODES AS oc  ON oc.c_office_id = o.c_office_id
LEFT JOIN BIOG_MAIN    AS p   ON p.c_personid = o.c_personid
LEFT JOIN TEXT_CODES   AS src ON src.c_textid = o.c_source

UNION ALL

-- 5. 社会身份
SELECT
    s.c_source, src.c_title_chn, src.c_title, src.c_text_dy,
    '社會身份',
    sc.c_status_desc_chn,
    s.c_personid, p.c_name_chn, p.c_name,
    s.c_status_code, sc.c_status_desc_chn, sc.c_status_desc,
    0,
    s.c_firstyear,
    s.c_pages, s.c_notes
FROM STATUS_DATA AS s
LEFT JOIN STATUS_CODES AS sc ON sc.c_status_code = s.c_status_code
LEFT JOIN BIOG_MAIN    AS p  ON p.c_personid = s.c_personid
LEFT JOIN TEXT_CODES   AS src ON src.c_textid = s.c_source

UNION ALL

-- 6. 人物地理
SELECT
    b.c_source, src.c_title_chn, src.c_title, src.c_text_dy,
    '人物地理',
    bac.c_addr_desc_chn,
    b.c_personid, p.c_name_chn, p.c_name,
    b.c_addr_id, ad.c_name_chn, ad.c_name,
    0,
    b.c_firstyear,
    b.c_pages, b.c_notes
FROM BIOG_ADDR_DATA AS b
LEFT JOIN BIOG_ADDR_CODES AS bac ON bac.c_addr_type = b.c_addr_type
LEFT JOIN ADDR_CODES      AS ad  ON ad.c_addr_id = b.c_addr_id
LEFT JOIN BIOG_MAIN       AS p   ON p.c_personid = b.c_personid
LEFT JOIN TEXT_CODES      AS src ON src.c_textid = b.c_source

UNION ALL

-- 7. 著作角色
SELECT
    t.c_source, src.c_title_chn, src.c_title, src.c_text_dy,
    '著作角色',
    tr.c_role_desc_chn,
    t.c_personid, p.c_name_chn, p.c_name,
    t.c_textid, tc.c_title_chn, tc.c_title,
    0,
    t.c_year,
    t.c_pages, t.c_notes
FROM BIOG_TEXT_DATA AS t
LEFT JOIN TEXT_ROLE_CODES AS tr  ON tr.c_role_id = t.c_role_id
LEFT JOIN TEXT_CODES      AS tc  ON tc.c_textid = t.c_textid
LEFT JOIN BIOG_MAIN       AS p   ON p.c_personid = t.c_personid
LEFT JOIN TEXT_CODES      AS src ON src.c_textid = t.c_source;
SQL
echo "Finished view View_TextAssociationData."

# ---------------------------------------------------------------------------
# View_PersonLifeTimeline
# ---------------------------------------------------------------------------
# "一个人的一生"：把散落在 12 张关系表里的记录，摊成一条可按时间排序的事件流。
#
# CBDB 的时间字段覆盖率极不均匀（任官 53% 有公历年，亲属 0%，著作 0%），
# 所以这里不做单一排序键，而是给每条记录标出**它的时间究竟精确到哪一级**：
#
#   time_precision = year     有公历年
#                  = nianhao  只有年号，用该年号的中点年估算
#                  = sequence 只有 c_sequence，只能定先后不能定年份
#                  = anchor   本身无时间，用关联人物的 index_year 作为锚点（亲属）
#                  = dynasty  只有朝代，用朝代起始年
#                  = undated  完全无时间
#
# 排序建议（把精度高的排前面、无时间的沉底）：
#   ORDER BY CASE time_precision WHEN 'year' THEN 0 WHEN 'nianhao' THEN 1
#                                WHEN 'anchor' THEN 2 WHEN 'sequence' THEN 3
#                                WHEN 'dynasty' THEN 4 ELSE 5 END,
#            sort_year, stage_no, sort_seq
# ---------------------------------------------------------------------------
echo "Creating view View_PersonLifeTimeline..."
sqlite3 "$DB_PATH" <<'SQL'
DROP VIEW IF EXISTS View_PersonLifeTimeline;
CREATE VIEW View_PersonLifeTimeline AS

-- 1. 生
SELECT p.c_personid, 1 AS stage_no, '生' AS stage,
       '出生' AS event_label, NULL AS counterpart_type,
       NULL AS counterpart_id, NULL AS counterpart_name_chn,
       p.c_birthyear AS year_from, p.c_birthyear AS year_to,
       CASE WHEN p.c_birthyear > 0 THEN 'year'
            WHEN p.c_by_nh_code > 0 THEN 'nianhao' ELSE 'undated' END AS time_precision,
       CASE WHEN p.c_birthyear > 0 THEN p.c_birthyear
            WHEN p.c_by_nh_code > 0 THEN (SELECT n.c_firstyear FROM NIAN_HAO n WHERE n.c_nianhao_id = p.c_by_nh_code)
            ELSE NULL END AS sort_year_lo,
       CASE WHEN p.c_birthyear > 0 THEN p.c_birthyear
            WHEN p.c_by_nh_code > 0 THEN (SELECT n.c_lastyear FROM NIAN_HAO n WHERE n.c_nianhao_id = p.c_by_nh_code)
            ELSE NULL END AS sort_year_hi,
       CASE WHEN p.c_birthyear > 0 THEN p.c_birthyear
            WHEN p.c_by_nh_code > 0 THEN (SELECT (n.c_firstyear + n.c_lastyear) / 2 FROM NIAN_HAO n WHERE n.c_nianhao_id = p.c_by_nh_code)
            ELSE NULL END AS sort_year,
       0 AS sort_seq, NULL AS c_source
FROM BIOG_MAIN p WHERE p.c_birthyear > 0 OR p.c_by_nh_code > 0

UNION ALL

-- 2. 名号（字/号/谥…无年份，只有顺序）
SELECT a.c_personid, 2, '名號',
       COALESCE(a.c_alt_name_chn, a.c_alt_name) || '（' ||
         COALESCE(ac.c_name_type_desc_chn, '未詳') || '）',
       '名號', a.c_alt_name_type_code, COALESCE(a.c_alt_name_chn, a.c_alt_name),
       NULL, NULL,
       CASE WHEN a.c_sequence > 0 THEN 'sequence' ELSE 'undated' END,
       NULL AS sort_year_lo, NULL AS sort_year_hi,
       NULL, COALESCE(a.c_sequence, 0), a.c_source
FROM ALTNAME_DATA a
LEFT JOIN ALTNAME_CODES ac ON ac.c_name_type_code = a.c_alt_name_type_code

UNION ALL

-- 3. 親屬（表内无时间，改用对方 index_year 作为锚点）
SELECT k.c_personid, 3, '親屬',
       COALESCE(q.c_name_chn, q.c_name, '（未識別）') || '（' ||
         COALESCE(kc.c_kinrel_chn, '未詳') || '）',
       '人物', k.c_kin_id, q.c_name_chn,
       NULL, NULL,
       CASE WHEN q.c_index_year IS NOT NULL AND q.c_index_year <> 0 THEN 'anchor'
            ELSE 'undated' END,
       CASE WHEN q.c_index_year IS NOT NULL AND q.c_index_year <> 0
            THEN q.c_index_year ELSE NULL END AS sort_year_lo,
       CASE WHEN q.c_index_year IS NOT NULL AND q.c_index_year <> 0
            THEN q.c_index_year ELSE NULL END AS sort_year_hi,
       CASE WHEN q.c_index_year IS NOT NULL AND q.c_index_year <> 0
            THEN q.c_index_year ELSE NULL END,
       0, k.c_source
FROM KIN_DATA k
LEFT JOIN KINSHIP_CODES kc ON kc.c_kincode = k.c_kin_code
LEFT JOIN BIOG_MAIN    q  ON q.c_personid = k.c_kin_id

UNION ALL

-- 4. 地理（籍貫 / 遷住地 / 葬地 / 死所 …）
SELECT b.c_personid, 4, '地理',
       COALESCE(ad.c_name_chn, ad.c_name) || '（' ||
         COALESCE(bac.c_addr_desc_chn, '未詳') || '）',
       '地名', b.c_addr_id, ad.c_name_chn,
       CASE WHEN b.c_firstyear > 0 THEN b.c_firstyear END,
       CASE WHEN b.c_lastyear  > 0 THEN b.c_lastyear  END,
       CASE WHEN b.c_firstyear > 0 THEN 'year'
            WHEN b.c_fy_nh_code > 0 THEN 'nianhao'
            WHEN b.c_sequence  > 0 THEN 'sequence' ELSE 'undated' END,
       CASE WHEN b.c_firstyear > 0 THEN b.c_firstyear
            WHEN b.c_fy_nh_code > 0 THEN (SELECT n.c_firstyear FROM NIAN_HAO n WHERE n.c_nianhao_id = b.c_fy_nh_code)
            ELSE NULL END AS sort_year_lo,
       CASE WHEN b.c_firstyear > 0 THEN b.c_firstyear
            WHEN b.c_fy_nh_code > 0 THEN (SELECT n.c_lastyear FROM NIAN_HAO n WHERE n.c_nianhao_id = b.c_fy_nh_code)
            ELSE NULL END AS sort_year_hi,
       CASE WHEN b.c_firstyear > 0 THEN b.c_firstyear
            WHEN b.c_fy_nh_code > 0 THEN (SELECT (n.c_firstyear + n.c_lastyear) / 2 FROM NIAN_HAO n WHERE n.c_nianhao_id = b.c_fy_nh_code)
            ELSE NULL END AS sort_year,
       COALESCE(b.c_sequence, 0), b.c_source
FROM BIOG_ADDR_DATA b
LEFT JOIN BIOG_ADDR_CODES bac ON bac.c_addr_type = b.c_addr_type
LEFT JOIN ADDR_CODES      ad  ON ad.c_addr_id = b.c_addr_id

UNION ALL

-- 5. 教育 / 宗教机构
SELECT i.c_personid, 5, '機構',
       COALESCE(sn.c_inst_name_hz, '（未詳機構）') || '（' ||
         COALESCE(rc.c_bi_role_chn, '未詳') || '）',
       '機構', i.c_inst_code, sn.c_inst_name_hz,
       CASE WHEN i.c_bi_begin_year > 0 THEN i.c_bi_begin_year END,
       CASE WHEN i.c_bi_end_year   > 0 THEN i.c_bi_end_year   END,
       CASE WHEN i.c_bi_begin_year > 0 THEN 'year'
            WHEN i.c_bi_by_nh_code > 0 THEN 'nianhao' ELSE 'undated' END,
       CASE WHEN i.c_bi_begin_year > 0 THEN i.c_bi_begin_year
            WHEN i.c_bi_by_nh_code > 0 THEN (SELECT n.c_firstyear FROM NIAN_HAO n WHERE n.c_nianhao_id = i.c_bi_by_nh_code)
            ELSE NULL END AS sort_year_lo,
       CASE WHEN i.c_bi_begin_year > 0 THEN i.c_bi_begin_year
            WHEN i.c_bi_by_nh_code > 0 THEN (SELECT n.c_lastyear FROM NIAN_HAO n WHERE n.c_nianhao_id = i.c_bi_by_nh_code)
            ELSE NULL END AS sort_year_hi,
       CASE WHEN i.c_bi_begin_year > 0 THEN i.c_bi_begin_year
            WHEN i.c_bi_by_nh_code > 0 THEN (SELECT (n.c_firstyear + n.c_lastyear) / 2 FROM NIAN_HAO n WHERE n.c_nianhao_id = i.c_bi_by_nh_code)
            ELSE NULL END AS sort_year,
       0, i.c_source
FROM BIOG_INST_DATA i
LEFT JOIN BIOG_INST_CODES           rc ON rc.c_bi_role_code = i.c_bi_role_code
LEFT JOIN SOCIAL_INSTITUTION_NAME_CODES sn ON sn.c_inst_name_code = i.c_inst_name_code

UNION ALL

-- 6. 入仕
SELECT e.c_personid, 6, '入仕',
       COALESCE(ec.c_entry_desc_chn, '未詳途徑') ||
         CASE WHEN e.c_exam_rank IS NOT NULL THEN '（第' || e.c_exam_rank || '名）' ELSE '' END,
       '入仕途徑', e.c_entry_code, ec.c_entry_desc_chn,
       CASE WHEN e.c_year > 0 THEN e.c_year END, CASE WHEN e.c_year > 0 THEN e.c_year END,
       CASE WHEN e.c_year > 0 THEN 'year'
            WHEN e.c_entry_nh_id > 0 THEN 'nianhao'
            WHEN e.c_sequence > 0 THEN 'sequence' ELSE 'undated' END,
       CASE WHEN e.c_year > 0 THEN e.c_year
            WHEN e.c_entry_nh_id > 0 THEN (SELECT n.c_firstyear FROM NIAN_HAO n WHERE n.c_nianhao_id = e.c_entry_nh_id)
            ELSE NULL END AS sort_year_lo,
       CASE WHEN e.c_year > 0 THEN e.c_year
            WHEN e.c_entry_nh_id > 0 THEN (SELECT n.c_lastyear FROM NIAN_HAO n WHERE n.c_nianhao_id = e.c_entry_nh_id)
            ELSE NULL END AS sort_year_hi,
       CASE WHEN e.c_year > 0 THEN e.c_year
            WHEN e.c_entry_nh_id > 0 THEN (SELECT (n.c_firstyear + n.c_lastyear) / 2 FROM NIAN_HAO n WHERE n.c_nianhao_id = e.c_entry_nh_id)
            ELSE NULL END AS sort_year,
       COALESCE(e.c_sequence, 0), e.c_source
FROM ENTRY_DATA e
LEFT JOIN ENTRY_CODES ec ON ec.c_entry_code = e.c_entry_code

UNION ALL

-- 7. 任官
SELECT o.c_personid, 7, '任官',
       COALESCE(oc.c_office_chn, oc.c_office_pinyin, '（未詳官職）') ||
         CASE WHEN ac.c_appt_desc_chn IS NOT NULL THEN '（' || ac.c_appt_desc_chn || '）' ELSE '' END ||
         CASE WHEN ao.c_assume_office_desc_chn IS NOT NULL AND ao.c_assume_office_code > 0
              THEN '［' || ao.c_assume_office_desc_chn || '］' ELSE '' END,
       '官職', o.c_office_id, oc.c_office_chn,
       CASE WHEN o.c_firstyear > 0 THEN o.c_firstyear END,
       CASE WHEN o.c_lastyear  > 0 THEN o.c_lastyear  END,
       CASE WHEN o.c_firstyear > 0 THEN 'year'
            WHEN o.c_fy_nh_code > 0 THEN 'nianhao'
            WHEN o.c_sequence  > 0 THEN 'sequence' ELSE 'undated' END,
       CASE WHEN o.c_firstyear > 0 THEN o.c_firstyear
            WHEN o.c_fy_nh_code > 0 THEN (SELECT n.c_firstyear FROM NIAN_HAO n WHERE n.c_nianhao_id = o.c_fy_nh_code)
            ELSE NULL END AS sort_year_lo,
       CASE WHEN o.c_firstyear > 0 THEN o.c_firstyear
            WHEN o.c_fy_nh_code > 0 THEN (SELECT n.c_lastyear FROM NIAN_HAO n WHERE n.c_nianhao_id = o.c_fy_nh_code)
            ELSE NULL END AS sort_year_hi,
       CASE WHEN o.c_firstyear > 0 THEN o.c_firstyear
            WHEN o.c_fy_nh_code > 0 THEN (SELECT (n.c_firstyear + n.c_lastyear) / 2 FROM NIAN_HAO n WHERE n.c_nianhao_id = o.c_fy_nh_code)
            ELSE NULL END AS sort_year,
       COALESCE(o.c_sequence, 0), o.c_source
FROM POSTED_TO_OFFICE_DATA o
LEFT JOIN OFFICE_CODES        oc ON oc.c_office_id = o.c_office_id
LEFT JOIN APPOINTMENT_CODES   ac ON ac.c_appt_code = o.c_appt_code
LEFT JOIN ASSUME_OFFICE_CODES ao ON ao.c_assume_office_code = o.c_assume_office_code

UNION ALL

-- 8. 任職地（本身无时间，借 posting_id 回任官表取）
SELECT pa.c_personid, 8, '任職地',
       COALESCE(ad.c_name_chn, ad.c_name, '（未詳地）') || '：' ||
         COALESCE(oc.c_office_chn, '（未詳官職）'),
       '地名', pa.c_addr_id, ad.c_name_chn,
       CASE WHEN o.c_firstyear > 0 THEN o.c_firstyear END,
       CASE WHEN o.c_lastyear  > 0 THEN o.c_lastyear  END,
       CASE WHEN o.c_firstyear > 0 THEN 'year'
            WHEN o.c_fy_nh_code > 0 THEN 'nianhao' ELSE 'undated' END,
       CASE WHEN o.c_firstyear > 0 THEN o.c_firstyear
            WHEN o.c_fy_nh_code > 0 THEN (SELECT n.c_firstyear FROM NIAN_HAO n WHERE n.c_nianhao_id = o.c_fy_nh_code)
            ELSE NULL END AS sort_year_lo,
       CASE WHEN o.c_firstyear > 0 THEN o.c_firstyear
            WHEN o.c_fy_nh_code > 0 THEN (SELECT n.c_lastyear FROM NIAN_HAO n WHERE n.c_nianhao_id = o.c_fy_nh_code)
            ELSE NULL END AS sort_year_hi,
       CASE WHEN o.c_firstyear > 0 THEN o.c_firstyear
            WHEN o.c_fy_nh_code > 0 THEN (SELECT (n.c_firstyear + n.c_lastyear) / 2 FROM NIAN_HAO n WHERE n.c_nianhao_id = o.c_fy_nh_code)
            ELSE NULL END AS sort_year,
       -- POSTED_TO_ADDR_DATA 本身没有年代/出处字段，时间借自同 posting 的任官记录
       0, NULL
FROM POSTED_TO_ADDR_DATA pa
LEFT JOIN POSTED_TO_OFFICE_DATA o ON o.c_posting_id = pa.c_posting_id AND o.c_office_id = pa.c_office_id
LEFT JOIN OFFICE_CODES oc ON oc.c_office_id = pa.c_office_id
LEFT JOIN ADDR_CODES   ad ON ad.c_addr_id = pa.c_addr_id

UNION ALL

-- 9. 交遊（社会关系）
SELECT a.c_personid, 9, '交遊',
       COALESCE(q.c_name_chn, q.c_name, '（未識別）') || '：' ||
         COALESCE(ac.c_assoc_desc_chn, '未詳關係'),
       '人物', a.c_assoc_id, q.c_name_chn,
       CASE WHEN a.c_assoc_first_year > 0 THEN a.c_assoc_first_year END,
       CASE WHEN a.c_assoc_last_year  > 0 THEN a.c_assoc_last_year  END,
       CASE WHEN a.c_assoc_first_year > 0 THEN 'year'
            WHEN a.c_assoc_fy_nh_code > 0 THEN 'nianhao'
            WHEN a.c_sequence > 0 THEN 'sequence' ELSE 'undated' END,
       CASE WHEN a.c_assoc_first_year > 0 THEN a.c_assoc_first_year
            WHEN a.c_assoc_fy_nh_code > 0 THEN (SELECT n.c_firstyear FROM NIAN_HAO n WHERE n.c_nianhao_id = a.c_assoc_fy_nh_code)
            ELSE NULL END AS sort_year_lo,
       CASE WHEN a.c_assoc_first_year > 0 THEN a.c_assoc_first_year
            WHEN a.c_assoc_fy_nh_code > 0 THEN (SELECT n.c_lastyear FROM NIAN_HAO n WHERE n.c_nianhao_id = a.c_assoc_fy_nh_code)
            ELSE NULL END AS sort_year_hi,
       CASE WHEN a.c_assoc_first_year > 0 THEN a.c_assoc_first_year
            WHEN a.c_assoc_fy_nh_code > 0 THEN (SELECT (n.c_firstyear + n.c_lastyear) / 2 FROM NIAN_HAO n WHERE n.c_nianhao_id = a.c_assoc_fy_nh_code)
            ELSE NULL END AS sort_year,
       COALESCE(a.c_sequence, 0), a.c_source
FROM ASSOC_DATA a
LEFT JOIN ASSOC_CODES ac ON ac.c_assoc_code = a.c_assoc_code
LEFT JOIN BIOG_MAIN   q  ON q.c_personid = a.c_assoc_id

UNION ALL

-- 10. 社会身份
SELECT s.c_personid, 10, '身份',
       COALESCE(sc.c_status_desc_chn, '未詳身份'),
       '身份', s.c_status_code, sc.c_status_desc_chn,
       CASE WHEN s.c_firstyear > 0 THEN s.c_firstyear END,
       CASE WHEN s.c_lastyear  > 0 THEN s.c_lastyear  END,
       CASE WHEN s.c_firstyear > 0 THEN 'year'
            WHEN s.c_fy_nh_code > 0 THEN 'nianhao'
            WHEN s.c_sequence  > 0 THEN 'sequence' ELSE 'undated' END,
       CASE WHEN s.c_firstyear > 0 THEN s.c_firstyear
            WHEN s.c_fy_nh_code > 0 THEN (SELECT n.c_firstyear FROM NIAN_HAO n WHERE n.c_nianhao_id = s.c_fy_nh_code)
            ELSE NULL END AS sort_year_lo,
       CASE WHEN s.c_firstyear > 0 THEN s.c_firstyear
            WHEN s.c_fy_nh_code > 0 THEN (SELECT n.c_lastyear FROM NIAN_HAO n WHERE n.c_nianhao_id = s.c_fy_nh_code)
            ELSE NULL END AS sort_year_hi,
       CASE WHEN s.c_firstyear > 0 THEN s.c_firstyear
            WHEN s.c_fy_nh_code > 0 THEN (SELECT (n.c_firstyear + n.c_lastyear) / 2 FROM NIAN_HAO n WHERE n.c_nianhao_id = s.c_fy_nh_code)
            ELSE NULL END AS sort_year,
       COALESCE(s.c_sequence, 0), s.c_source
FROM STATUS_DATA s
LEFT JOIN STATUS_CODES sc ON sc.c_status_code = s.c_status_code

UNION ALL

-- 11. 著作（c_year 在现行数据里 100% 为空，只能靠对方的成书年做弱锚点）
SELECT t.c_personid, 11, '著作',
       COALESCE(tc.c_title_chn, tc.c_title, '（未詳書）') || '［' ||
         COALESCE(tr.c_role_desc_chn, '未詳角色') || '］',
       '文本', t.c_textid, tc.c_title_chn,
       CASE WHEN t.c_year > 0 THEN t.c_year END, NULL,
       CASE WHEN t.c_year > 0 THEN 'year'
            WHEN tc.c_text_year > 0 THEN 'anchor'
            WHEN t.c_nh_code > 0 THEN 'nianhao' ELSE 'undated' END,
       CASE WHEN t.c_year > 0 THEN t.c_year
            WHEN tc.c_text_year > 0 THEN tc.c_text_year
            WHEN t.c_nh_code > 0 THEN (SELECT n.c_firstyear FROM NIAN_HAO n WHERE n.c_nianhao_id = t.c_nh_code)
            ELSE NULL END AS sort_year_lo,
       CASE WHEN t.c_year > 0 THEN t.c_year
            WHEN tc.c_text_year > 0 THEN tc.c_text_year
            WHEN t.c_nh_code > 0 THEN (SELECT n.c_lastyear FROM NIAN_HAO n WHERE n.c_nianhao_id = t.c_nh_code)
            ELSE NULL END AS sort_year_hi,
       CASE WHEN t.c_year > 0 THEN t.c_year
            WHEN tc.c_text_year > 0 THEN tc.c_text_year
            WHEN t.c_nh_code > 0 THEN (SELECT (n.c_firstyear + n.c_lastyear) / 2 FROM NIAN_HAO n WHERE n.c_nianhao_id = t.c_nh_code)
            ELSE NULL END AS sort_year,
       0, t.c_source
FROM BIOG_TEXT_DATA t
LEFT JOIN TEXT_ROLE_CODES tr ON tr.c_role_id = t.c_role_id
LEFT JOIN TEXT_CODES      tc ON tc.c_textid = t.c_textid

UNION ALL

-- 12. 財產
SELECT ps.c_personid, 12, '財產',
       COALESCE(ps.c_possession_desc_chn, '（未詳）') ||
         CASE WHEN ps.c_quantity IS NOT NULL
              THEN ' ' || ps.c_quantity || COALESCE(mc.c_measure_desc_chn, '') ELSE '' END,
       '財產', ps.c_possession_record_id, ps.c_possession_desc_chn,
       CASE WHEN ps.c_possession_yr > 0 THEN ps.c_possession_yr END, NULL,
       CASE WHEN ps.c_possession_yr > 0 THEN 'year'
            WHEN ps.c_possession_nh_code > 0 THEN 'nianhao'
            WHEN ps.c_sequence > 0 THEN 'sequence' ELSE 'undated' END,
       CASE WHEN ps.c_possession_yr > 0 THEN ps.c_possession_yr
            WHEN ps.c_possession_nh_code > 0 THEN (SELECT n.c_firstyear FROM NIAN_HAO n WHERE n.c_nianhao_id = ps.c_possession_nh_code)
            ELSE NULL END AS sort_year_lo,
       CASE WHEN ps.c_possession_yr > 0 THEN ps.c_possession_yr
            WHEN ps.c_possession_nh_code > 0 THEN (SELECT n.c_lastyear FROM NIAN_HAO n WHERE n.c_nianhao_id = ps.c_possession_nh_code)
            ELSE NULL END AS sort_year_hi,
       CASE WHEN ps.c_possession_yr > 0 THEN ps.c_possession_yr
            WHEN ps.c_possession_nh_code > 0 THEN (SELECT (n.c_firstyear + n.c_lastyear) / 2 FROM NIAN_HAO n WHERE n.c_nianhao_id = ps.c_possession_nh_code)
            ELSE NULL END AS sort_year,
       COALESCE(ps.c_sequence, 0), ps.c_source
FROM POSSESSION_DATA ps
LEFT JOIN MEASURE_CODES mc ON mc.c_measure_code = ps.c_measure_code

UNION ALL

-- 13. 事件
SELECT ev.c_personid, 13, '事件',
       COALESCE(ec.c_event_name_chn, ev.c_event, '（未詳事件）'),
       '事件', ev.c_event_code, ec.c_event_name_chn,
       CASE WHEN ev.c_year > 0 THEN ev.c_year END, NULL,
       CASE WHEN ev.c_year > 0 THEN 'year'
            WHEN ev.c_nh_code > 0 THEN 'nianhao'
            WHEN ev.c_sequence > 0 THEN 'sequence' ELSE 'undated' END,
       CASE WHEN ev.c_year > 0 THEN ev.c_year
            WHEN ev.c_nh_code > 0 THEN (SELECT n.c_firstyear FROM NIAN_HAO n WHERE n.c_nianhao_id = ev.c_nh_code)
            ELSE NULL END AS sort_year_lo,
       CASE WHEN ev.c_year > 0 THEN ev.c_year
            WHEN ev.c_nh_code > 0 THEN (SELECT n.c_lastyear FROM NIAN_HAO n WHERE n.c_nianhao_id = ev.c_nh_code)
            ELSE NULL END AS sort_year_hi,
       CASE WHEN ev.c_year > 0 THEN ev.c_year
            WHEN ev.c_nh_code > 0 THEN (SELECT (n.c_firstyear + n.c_lastyear) / 2 FROM NIAN_HAO n WHERE n.c_nianhao_id = ev.c_nh_code)
            ELSE NULL END AS sort_year,
       COALESCE(ev.c_sequence, 0), ev.c_source
FROM EVENTS_DATA ev
LEFT JOIN EVENT_CODES ec ON ec.c_event_code = ev.c_event_code

UNION ALL

-- 14. 卒
SELECT p.c_personid, 14, '卒',
       '卒' || CASE WHEN p.c_death_age > 0 THEN '（享年' || p.c_death_age || '）' ELSE '' END,
       NULL, NULL, NULL,
       p.c_deathyear, p.c_deathyear,
       CASE WHEN p.c_deathyear > 0 THEN 'year'
            WHEN p.c_dy_nh_code > 0 THEN 'nianhao' ELSE 'undated' END,
       CASE WHEN p.c_deathyear > 0 THEN p.c_deathyear
            WHEN p.c_dy_nh_code > 0 THEN (SELECT n.c_firstyear FROM NIAN_HAO n WHERE n.c_nianhao_id = p.c_dy_nh_code)
            ELSE NULL END AS sort_year_lo,
       CASE WHEN p.c_deathyear > 0 THEN p.c_deathyear
            WHEN p.c_dy_nh_code > 0 THEN (SELECT n.c_lastyear FROM NIAN_HAO n WHERE n.c_nianhao_id = p.c_dy_nh_code)
            ELSE NULL END AS sort_year_hi,
       CASE WHEN p.c_deathyear > 0 THEN p.c_deathyear
            WHEN p.c_dy_nh_code > 0 THEN (SELECT (n.c_firstyear + n.c_lastyear) / 2 FROM NIAN_HAO n WHERE n.c_nianhao_id = p.c_dy_nh_code)
            ELSE NULL END AS sort_year,
       0, NULL
FROM BIOG_MAIN p WHERE p.c_deathyear > 0 OR p.c_dy_nh_code > 0;
SQL
echo "Finished view View_PersonLifeTimeline."

# ---------------------------------------------------------------------------
# View_RelationEdges
# ---------------------------------------------------------------------------
# 把 CBDB 建模成属性图（property graph），供递归 CTE 做 A→B→C 的链式遍历。
#   节点类型：P 人物 / A 地址 / O 官職 / I 機構 / T 文本 / S 身份 / E 事件 / N 財產 / C 入仕途徑 / Y 朝代
#   边类型：kinship / association / identity / person_place / person_office /
#            person_institution / person_text / person_status / person_entry /
#            person_event / place_hierarchy / institution_place
# ---------------------------------------------------------------------------
echo "Creating view View_RelationEdges..."
sqlite3 "$DB_PATH" <<'SQL'
DROP VIEW IF EXISTS View_RelationEdges;
CREATE VIEW View_RelationEdges AS

-- 人 → 人：親屬
SELECT 'P' AS src_type, k.c_personid AS src_id, p.c_name_chn AS src_name_chn,
       'P' AS dst_type, k.c_kin_id AS dst_id, q.c_name_chn AS dst_name_chn,
       COALESCE(kc.c_kinrel_chn, '親屬') AS relation, 'kinship' AS edge_type,
       NULL AS year_from, NULL AS year_to, 'undated' AS time_precision,
       k.c_source AS c_source
FROM KIN_DATA k
LEFT JOIN KINSHIP_CODES kc ON kc.c_kincode = k.c_kin_code
LEFT JOIN BIOG_MAIN p ON p.c_personid = k.c_personid
LEFT JOIN BIOG_MAIN q ON q.c_personid = k.c_kin_id
WHERE k.c_kin_id > 0

UNION ALL

-- 人 → 人：交遊（社会关系）
SELECT 'P', a.c_personid, p.c_name_chn,
       'P', a.c_assoc_id, q.c_name_chn,
       COALESCE(ac.c_assoc_desc_chn, '社會關係'), 'association',
       CASE WHEN a.c_assoc_first_year > 0 THEN a.c_assoc_first_year END,
       CASE WHEN a.c_assoc_last_year  > 0 THEN a.c_assoc_last_year  END,
       CASE WHEN a.c_assoc_first_year > 0 THEN 'year' ELSE 'undated' END,
       a.c_source
FROM ASSOC_DATA a
LEFT JOIN ASSOC_CODES ac ON ac.c_assoc_code = a.c_assoc_code
LEFT JOIN BIOG_MAIN p ON p.c_personid = a.c_personid
LEFT JOIN BIOG_MAIN q ON q.c_personid = a.c_assoc_id
WHERE a.c_assoc_id > 0

UNION ALL

-- 人 → 人：同一人的合并记录（身份同一，用于查 ID 归一）
SELECT 'P', m.c_merged_from_personid, b2.c_name_chn,
       'P', m.c_personid, b1.c_name_chn,
       '合併為同一人', 'identity',
       NULL, NULL, 'undated', m.c_source
FROM MERGED_PERSON_DATA m
LEFT JOIN BIOG_MAIN b1 ON b1.c_personid = m.c_personid
LEFT JOIN BIOG_MAIN b2 ON b2.c_personid = m.c_merged_from_personid

UNION ALL

-- 人 → 地
SELECT 'P', b.c_personid, p.c_name_chn,
       'A', b.c_addr_id, ad.c_name_chn,
       COALESCE(bac.c_addr_desc_chn, '人物地理'), 'person_place',
       CASE WHEN b.c_firstyear > 0 THEN b.c_firstyear END,
       CASE WHEN b.c_lastyear  > 0 THEN b.c_lastyear  END,
       CASE WHEN b.c_firstyear > 0 THEN 'year' ELSE 'undated' END,
       b.c_source
FROM BIOG_ADDR_DATA b
LEFT JOIN BIOG_ADDR_CODES bac ON bac.c_addr_type = b.c_addr_type
LEFT JOIN ADDR_CODES ad ON ad.c_addr_id = b.c_addr_id
LEFT JOIN BIOG_MAIN p ON p.c_personid = b.c_personid
WHERE b.c_addr_id > 0

UNION ALL

-- 人 → 官職
SELECT 'P', o.c_personid, p.c_name_chn,
       'O', o.c_office_id, oc.c_office_chn,
       COALESCE(ac.c_appt_desc_chn, '任官'), 'person_office',
       CASE WHEN o.c_firstyear > 0 THEN o.c_firstyear END,
       CASE WHEN o.c_lastyear  > 0 THEN o.c_lastyear  END,
       CASE WHEN o.c_firstyear > 0 THEN 'year' ELSE 'undated' END,
       o.c_source
FROM POSTED_TO_OFFICE_DATA o
LEFT JOIN OFFICE_CODES oc ON oc.c_office_id = o.c_office_id
LEFT JOIN APPOINTMENT_CODES ac ON ac.c_appt_code = o.c_appt_code
LEFT JOIN BIOG_MAIN p ON p.c_personid = o.c_personid
WHERE o.c_office_id > 0

UNION ALL

-- 人 → 機構
SELECT 'P', i.c_personid, p.c_name_chn,
       'I', i.c_inst_code, sn.c_inst_name_hz,
       COALESCE(rc.c_bi_role_chn, '參與機構'), 'person_institution',
       CASE WHEN i.c_bi_begin_year > 0 THEN i.c_bi_begin_year END,
       CASE WHEN i.c_bi_end_year   > 0 THEN i.c_bi_end_year   END,
       CASE WHEN i.c_bi_begin_year > 0 THEN 'year' ELSE 'undated' END,
       i.c_source
FROM BIOG_INST_DATA i
LEFT JOIN BIOG_INST_CODES rc ON rc.c_bi_role_code = i.c_bi_role_code
LEFT JOIN SOCIAL_INSTITUTION_NAME_CODES sn ON sn.c_inst_name_code = i.c_inst_name_code
LEFT JOIN BIOG_MAIN p ON p.c_personid = i.c_personid
WHERE i.c_inst_code > 0 OR i.c_inst_name_code > 0

UNION ALL

-- 人 → 文本
SELECT 'P', t.c_personid, p.c_name_chn,
       'T', t.c_textid, tc.c_title_chn,
       COALESCE(tr.c_role_desc_chn, '著作角色'), 'person_text',
       CASE WHEN t.c_year > 0 THEN t.c_year END, NULL,
       CASE WHEN t.c_year > 0 THEN 'year' ELSE 'undated' END,
       t.c_source
FROM BIOG_TEXT_DATA t
LEFT JOIN TEXT_ROLE_CODES tr ON tr.c_role_id = t.c_role_id
LEFT JOIN TEXT_CODES tc ON tc.c_textid = t.c_textid
LEFT JOIN BIOG_MAIN p ON p.c_personid = t.c_personid
WHERE t.c_textid > 0

UNION ALL

-- 人 → 身份
SELECT 'P', s.c_personid, p.c_name_chn,
       'S', s.c_status_code, sc.c_status_desc_chn,
       '社會身份', 'person_status',
       CASE WHEN s.c_firstyear > 0 THEN s.c_firstyear END,
       CASE WHEN s.c_lastyear  > 0 THEN s.c_lastyear  END,
       CASE WHEN s.c_firstyear > 0 THEN 'year' ELSE 'undated' END,
       s.c_source
FROM STATUS_DATA s
LEFT JOIN STATUS_CODES sc ON sc.c_status_code = s.c_status_code
LEFT JOIN BIOG_MAIN p ON p.c_personid = s.c_personid

UNION ALL

-- 人 → 入仕途徑
SELECT 'P', e.c_personid, p.c_name_chn,
       'C', e.c_entry_code, ec.c_entry_desc_chn,
       '入仕', 'person_entry',
       CASE WHEN e.c_year > 0 THEN e.c_year END, NULL,
       CASE WHEN e.c_year > 0 THEN 'year' ELSE 'undated' END,
       e.c_source
FROM ENTRY_DATA e
LEFT JOIN ENTRY_CODES ec ON ec.c_entry_code = e.c_entry_code
LEFT JOIN BIOG_MAIN p ON p.c_personid = e.c_personid

UNION ALL

-- 人 → 事件
SELECT 'P', ev.c_personid, p.c_name_chn,
       'E', ev.c_event_code, ec.c_event_name_chn,
       '事件', 'person_event',
       CASE WHEN ev.c_year > 0 THEN ev.c_year END, NULL,
       CASE WHEN ev.c_year > 0 THEN 'year' ELSE 'undated' END,
       ev.c_source
FROM EVENTS_DATA ev
LEFT JOIN EVENT_CODES ec ON ec.c_event_code = ev.c_event_code
LEFT JOIN BIOG_MAIN p ON p.c_personid = ev.c_personid

UNION ALL

-- 地 → 地：行政隶属
SELECT 'A', ab.c_addr_id, a1.c_name_chn,
       'A', ab.c_belongs_to, a2.c_name_chn,
       '隸屬於', 'place_hierarchy',
       CASE WHEN ab.c_firstyear > 0 THEN ab.c_firstyear END,
       CASE WHEN ab.c_lastyear  > 0 THEN ab.c_lastyear  END,
       CASE WHEN ab.c_firstyear > 0 THEN 'year' ELSE 'undated' END,
       ab.c_source
FROM ADDR_BELONGS_DATA ab
LEFT JOIN ADDR_CODES a1 ON a1.c_addr_id = ab.c_addr_id
LEFT JOIN ADDR_CODES a2 ON a2.c_addr_id = ab.c_belongs_to

UNION ALL

-- 機構 → 地
SELECT 'I', sa.c_inst_code, sn.c_inst_name_hz,
       'A', sa.c_inst_addr_id, ad.c_name_chn,
       '機構位於', 'institution_place',
       NULL, NULL, 'undated', sa.c_source
FROM SOCIAL_INSTITUTION_ADDR sa
LEFT JOIN SOCIAL_INSTITUTION_NAME_CODES sn ON sn.c_inst_name_code = sa.c_inst_name_code
LEFT JOIN ADDR_CODES ad ON ad.c_addr_id = sa.c_inst_addr_id
WHERE sa.c_inst_addr_id > 0;
SQL
echo "Finished view View_RelationEdges."

# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------
echo "Running sanity counts on the new views..."
for view in View_KinshipGenealogyData View_CountyPeopleData View_TextAssociationData \
            View_PersonLifeTimeline View_RelationEdges; do
    echo "Checking view: $view..."
    if sqlite3 "$DB_PATH" "SELECT '$view' AS view_name, COUNT(*) AS row_count FROM $view;"; then
        echo "  OK  $view"
    else
        echo "  ERROR: $view failed" >&2
        exit 1
    fi
done

echo "All sanity checks passed!"
