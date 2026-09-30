-- ============================================================
-- CBDB SQLite 示例查询集（45 条，全部实测通过）
-- 数据库: cbdb_20260926.sqlite3
--   79 表 / 23 视图（含新增 5 个分析型视图）/ 662,152 人
--   View_PersonLifeTimeline 3,006,222 行 / View_RelationEdges 2,245,701 行
-- 演示人物: c_personid = 1762 (王安石)
-- 用法: 在 DBeaver 里打开本文件，选中单条语句执行 (Ctrl+Enter)
-- 详细表/视图说明见 CBDB_SQLite_使用报告.md
-- ============================================================



-- ########## 单个人物的完整档案 ##########

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


-- ########## 群体统计 ##########

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


-- ########## 特定主题 ##########

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


-- ########## 三个新增视图的用法 ##########

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


-- ########## 生平年谱与链式关系遍历（View_PersonLifeTimeline / View_RelationEdges） ##########
-- 前置说明：View_PersonLifeTimeline 3,006,222 行；View_RelationEdges 2,245,701 行。
-- 每条记录的时间精度由 time_precision 标记：
--   year(确切年) / nianhao(年号中点估算) / anchor(借关联对象年份) / sequence(仅序号) / dynasty / undated
-- 排序永远按「精度权重 + sort_year + stage_no + sort_seq」，不要单独按 sort_year 排。

-- ㉟ 任意一个人的完整年谱（改 c_personid 即可）
SELECT stage_no, stage, time_precision, sort_year, sort_seq,
       counterpart_type, counterpart_name_chn, event_label, c_source
FROM View_PersonLifeTimeline
WHERE c_personid = 1762
ORDER BY CASE time_precision WHEN 'year' THEN 0 WHEN 'nianhao' THEN 1 WHEN 'anchor' THEN 2
              WHEN 'sequence' THEN 3 WHEN 'dynasty' THEN 4 ELSE 5 END,
         sort_year, stage_no, sort_seq;

-- ㊱ 只要「有确切年份」的骨架年谱（剔除估算值）
SELECT sort_year, stage, event_label
FROM View_PersonLifeTimeline
WHERE c_personid = 1762 AND time_precision = 'year'
ORDER BY sort_year, stage_no;

-- ㊲ 判断某人值不值得做年谱：各时间精度分别有多少条
SELECT time_precision, COUNT(*) AS 条数
FROM View_PersonLifeTimeline
WHERE c_personid = 1762
GROUP BY time_precision
ORDER BY CASE time_precision WHEN 'year' THEN 0 WHEN 'nianhao' THEN 1 WHEN 'anchor' THEN 2
              WHEN 'sequence' THEN 3 WHEN 'dynasty' THEN 4 ELSE 5 END;

-- ㊳ 限定在生卒区间内的年谱（剔除早于生年 / 晚于卒年的噪声）
SELECT t.stage, t.sort_year, t.event_label
FROM View_PersonLifeTimeline t
JOIN BIOG_MAIN p ON p.c_personid = t.c_personid
WHERE t.c_personid = 1762
  AND (t.sort_year IS NULL
       OR (p.c_birthyear > 0 AND t.sort_year >= p.c_birthyear
           AND p.c_deathyear > 0 AND t.sort_year <= p.c_deathyear))
ORDER BY t.sort_year, t.stage_no;

-- ㊴ 全库各人生阶段的时间精度分布（判断哪类信息排得进时间）
SELECT stage_no, stage, COUNT(*) AS 总行数,
       SUM(time_precision = 'year')     AS 确切年,
       SUM(time_precision = 'nianhao')  AS 年号估算,
       SUM(time_precision = 'anchor')   AS 借锚点,
       SUM(time_precision = 'sequence') AS 仅序号,
       SUM(time_precision = 'undated')  AS 无时间
FROM View_PersonLifeTimeline
GROUP BY stage_no, stage ORDER BY stage_no;

-- ㊵ 关系图谱：各类边的规模与有年份占比
SELECT edge_type, src_type || '->' || dst_type AS 方向, COUNT(*) AS 边数,
       SUM(time_precision = 'year') AS 有确切年份
FROM View_RelationEdges
GROUP BY edge_type, 方向 ORDER BY 边数 DESC;

-- ㊶【链式遍历】第 1 步：物化「人物—人物」的双向边并建索引
--    KIN_DATA / ASSOC_DATA 都是单向存储，必须 UNION ALL 反向补全，否则网络缺一半边。
--    这一步决定了后面的递归是 1 秒还是 10 分钟。
CREATE TEMP TABLE e_pp AS
SELECT src_id AS a, dst_id AS b, relation, edge_type, year_from, year_to, time_precision
FROM View_RelationEdges WHERE src_type = 'P' AND dst_type = 'P'
UNION ALL
SELECT dst_id, src_id, relation, edge_type, year_from, year_to, time_precision
FROM View_RelationEdges WHERE src_type = 'P' AND dst_type = 'P';
CREATE INDEX tmp_e_pp_a ON e_pp(a);
CREATE INDEX tmp_e_pp_b ON e_pp(b);
-- 双向共 1,518,020 条边

-- ㊷【链式遍历】第 2 步：递归 CTE 多跳遍历（路径去重 + 时间窗单调折叠 + 剪枝）
--    lo/hi 沿路径求交：lo = MAX(lo, 新下界)，hi = MIN(hi, 新上界)；lo > hi 即时间自相矛盾，剪掉。
WITH RECURSIVE walk(a, b, depth, path, rels, lo, hi) AS (
    SELECT e.a, e.b, 1, '|' || e.a || '|' || e.b || '|', e.relation,
           COALESCE(e.year_from, -9999), COALESCE(e.year_to, 9999)
    FROM e_pp e
    WHERE e.a = 1762                                  -- 起点：王安石
    UNION ALL
    SELECT w.a, e.b, w.depth + 1, w.path || e.b || '|', w.rels || ' / ' || e.relation,
           MAX(w.lo, COALESCE(e.year_from, -9999)),
           MIN(w.hi, COALESCE(e.year_to, 9999))
    FROM walk w JOIN e_pp e ON e.a = w.b
    WHERE w.depth < 3                                 -- 限深：3 跳会到 5,183 万条路径
      AND instr(w.path, '|' || e.b || '|') = 0        -- 防环
      AND w.lo <= w.hi                                -- 时间窗自洽
)
SELECT depth, COUNT(*) AS 路径数,
       SUM(lo <= 1086 AND hi >= 1021) AS 落在王安石生卒窗内
FROM walk GROUP BY depth ORDER BY depth;

-- ㊸【链式遍历】两跳关系链的具体内容（起点 → 中间人 → 终点）
WITH RECURSIVE walk(a, b, depth, path, rels) AS (
    SELECT e.a, e.b, 1, '|' || e.a || '|' || e.b || '|', e.relation
    FROM e_pp e WHERE e.a = 1762
    UNION ALL
    SELECT w.a, e.b, w.depth + 1, w.path || e.b || '|', w.rels || ' / ' || e.relation
    FROM walk w JOIN e_pp e ON e.a = w.b
    WHERE w.depth < 2 AND instr(w.path, '|' || e.b || '|') = 0
)
SELECT w.b AS 终点id, bm.c_name_chn AS 终点姓名, w.rels AS 关系链
FROM walk w LEFT JOIN BIOG_MAIN bm ON bm.c_personid = w.b
WHERE w.depth = 2
LIMIT 100;

-- ㊹【链式遍历】非人物边也能递归：某地的全部上级行政隶属
WITH RECURSIVE up(a, b, depth, path) AS (
    SELECT src_id, dst_id, 1, src_name_chn
    FROM View_RelationEdges
    WHERE edge_type = 'place_hierarchy' AND src_id = 15279
    UNION ALL
    SELECT e.src_id, e.dst_id, u.depth + 1, u.path || ' < ' || e.dst_name_chn
    FROM up u JOIN View_RelationEdges e ON e.src_id = u.b AND e.edge_type = 'place_hierarchy'
    WHERE u.depth < 5
)
SELECT depth, path FROM up;

-- ㊺ 谁的年谱最完整：有确切年份记录最多的前 20 人
SELECT p.c_personid, p.c_name_chn, COUNT(*) AS 有年份事件数
FROM View_PersonLifeTimeline t
JOIN BIOG_MAIN p ON p.c_personid = t.c_personid
WHERE t.time_precision IN ('year', 'nianhao')
GROUP BY p.c_personid
ORDER BY 有年份事件数 DESC
LIMIT 20;

-- ============================================================================
-- 区间轴 + 序轴：LIFE_EVENT_RESOLVED（由 scripts/life_order.py 生成）
-- ============================================================================

-- ㊻【推荐】任意一个人的「区间年谱」：宽区间自动沉底，可信的排前面
SELECT order_rank, stage, lo, hi, width, precision, conflict, event_label
FROM LIFE_EVENT_RESOLVED
WHERE c_personid = 1762
ORDER BY lo, width, order_rank;

-- ㊼ 只要「窄区间」的高置信年谱（≤30 年）
SELECT lo, hi, stage, event_label
FROM LIFE_EVENT_RESOLVED
WHERE c_personid = 1762 AND width <= 30
ORDER BY lo;

-- ㊽ 纯序轴：完全不看年份，只看先后（适合做成甘特/流程图）
SELECT order_rank, stage, event_label
FROM LIFE_EVENT_RESOLVED
WHERE c_personid = 1762
ORDER BY order_rank;

-- ㊾ 这个人的时间轴可信度体检
SELECT precision, COUNT(*) AS 条数, ROUND(AVG(width), 1) AS 平均宽,
       SUM(conflict) AS 矛盾数
FROM LIFE_EVENT_RESOLVED
WHERE c_personid = 1762
GROUP BY precision;

-- ㊿ 全库：哪些人的年谱被推理改善得最多
SELECT r.c_personid, p.c_name_chn,
       COUNT(*) AS 事件数,
       ROUND(AVG(r.prior_width), 1) AS 原宽,
       ROUND(AVG(r.width), 1) AS 现宽,
       SUM(r.narrowed) AS 总收窄年数
FROM LIFE_EVENT_RESOLVED r
JOIN BIOG_MAIN p ON p.c_personid = r.c_personid
GROUP BY r.c_personid
HAVING 事件数 >= 30
ORDER BY 总收窄年数 DESC
LIMIT 20;

-- 51 全库：数据自相矛盾的记录（本身就是脏数据线索）
SELECT r.c_personid, p.c_name_chn, r.stage, r.event_label,
       r.prior_lo, r.prior_hi, r.time_precision
FROM LIFE_EVENT_RESOLVED r
JOIN BIOG_MAIN p ON p.c_personid = r.c_personid
WHERE r.conflict = 1
LIMIT 200;

-- 52 全库：各阶段的时间可解性（哪一类事件最难定年）
SELECT stage, COUNT(*) AS 条数,
       ROUND(AVG(prior_width), 1) AS 原宽, ROUND(AVG(width), 1) AS 现宽,
       ROUND(100.0 * SUM(narrowed > 0) / COUNT(*), 1) AS 被收窄百分比
FROM LIFE_EVENT_RESOLVED
GROUP BY stage
ORDER BY 条数 DESC;

-- 53 区间重叠查询：某人在 [1060, 1080] 之间可能发生了什么
SELECT stage, lo, hi, event_label
FROM LIFE_EVENT_RESOLVED
WHERE c_personid = 1762 AND lo <= 1080 AND hi >= 1060
ORDER BY lo;
