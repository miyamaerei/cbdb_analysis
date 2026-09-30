<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api } from './api'
import DataTable from './components/DataTable.vue'
import IntervalTimeline from './components/IntervalTimeline.vue'
import KgExplorer from './components/KgExplorer.vue'
import PersonSearch from './components/PersonSearch.vue'
import RelationNetwork from './components/RelationNetwork.vue'
import ViewExplorer from './components/ViewExplorer.vue'
import ViewNav from './components/ViewNav.vue'

// ---------------------------------------------------------------- 库概况
const stats = ref(null)
const err = ref('')

// ---------------------------------------------------------------- 主模式
// person = 人物年谱（单人纵向） / view = 视图检索（24 个视图，横向分组）
// kg = 知识图谱（原 Gradio 前端迁移到 Vue，复用 DataTable）
const mode = ref('person')
const MODES = [
  { k: 'person', name: '人物年谱' },
  { k: 'view', name: '视图检索' },
  { k: 'kg', name: '知识图谱' },
]

// ---------------------------------------------------------------- 视图元数据
const meta = ref(null)
const activeGroup = ref('')
const activeView = ref('')
const viewSeed = ref(null) // 下钻带过来的初始条件

const groups = computed(() => meta.value?.groups || [])

// URL 深链：#view=<名字>&st=<状态 JSON> —— 由 ViewExplorer 写出，这里负责恢复
function readUrlState() {
  try {
    const h = location.hash.replace(/^#/, '')
    if (!h) return null
    const raw = new URLSearchParams(h).get('st')
    const st = raw ? JSON.parse(decodeURIComponent(raw)) : null
    return st && st.view ? st : null
  } catch {
    return null
  }
}

async function loadMeta() {
  if (meta.value) return
  try {
    meta.value = await api.views()
    const st = readUrlState()
    if (st && meta.value.views?.[st.view]) {
      // 直接打开链接里指定的视图与条件
      mode.value = 'view'
      activeView.value = st.view
      viewSeed.value = { state: st, n: 1 }
      const g = groups.value.find((x) => x.views.includes(st.view))
      if (g) activeGroup.value = g.key
      return
    }
    if (!activeGroup.value && groups.value.length) activeGroup.value = groups.value[0].key
    if (!activeView.value && groups.value.length)
      activeView.value = groups.value[0].views[0]
  } catch (e) {
    err.value = `视图元数据加载失败：${e}（先跑 web/build_view_meta.py）`
  }
}

function setMode(k) {
  mode.value = k
  if (k === 'view') loadMeta()
}

function openView(name) {
  mode.value = 'view'
  activeView.value = name
  viewSeed.value = null
  const g = groups.value.find((x) => x.views.includes(name))
  if (g) activeGroup.value = g.key
}

// 视图导航条选视图：视图与所在组一起切
function onPick({ group, view }) {
  if (group) activeGroup.value = group
  if (view && view !== activeView.value) {
    activeView.value = view
    viewSeed.value = null
  }
}

// 组内下钻：带着「某列 = 某值」跳到另一个视图
function onDrill({ view, key, value }) {
  const g = groups.value.find((x) => x.views.includes(view))
  if (g) activeGroup.value = g.key
  activeView.value = view
  viewSeed.value = { col: key, value, n: (viewSeed.value?.n || 0) + 1 }
}

// 从 URL 恢复时，ViewExplorer 发现 hash 指向别的视图 → 交给这里切过去并带上条件
function onOpenView(name, state) {
  if (!meta.value?.views?.[name]) return
  const g = groups.value.find((x) => x.views.includes(name))
  if (g) activeGroup.value = g.key
  activeView.value = name
  viewSeed.value = { state, n: (viewSeed.value?.n || 0) + 1 }
}

function onOpenTimeline(id) {
  mode.value = 'person'
  selectPerson(id)
}

// ---------------------------------------------------------------- 当前人物
const pid = ref(null)
const person = ref(null)
const timeline = ref([])
const relations = ref(null)
const graph = ref({ nodes: [], links: [] })

const stageFilter = ref([])
const precFilter = ref([])

const STAGES = [
  { no: 1, name: '生' }, { no: 2, name: '名號' }, { no: 3, name: '親屬' },
  { no: 4, name: '地理' }, { no: 5, name: '機構' }, { no: 6, name: '入仕' },
  { no: 7, name: '任官' }, { no: 8, name: '任職地' }, { no: 9, name: '交遊' },
  { no: 10, name: '身份' }, { no: 11, name: '著作' }, { no: 12, name: '財產' },
  { no: 13, name: '事件' }, { no: 14, name: '卒' },
]
const PRECISIONS = [
  { k: 'exact', name: '精确' },
  { k: 'propagated', name: '推理收窄' },
  { k: 'interval', name: '区间' },
  { k: 'frame', name: '仅框架' },
]

async function selectPerson(id) {
  pid.value = id
  person.value = null
  timeline.value = []
  relations.value = null
  graph.value = { nodes: [], links: [] }
  stageFilter.value = []
  precFilter.value = []
  tab.value = 'timeline'
  try {
    const [p, t] = await Promise.all([
      api.person(id),
      api.timeline(id, { limit: 3000 }),
    ])
    person.value = p
    timeline.value = t
    if (p?.error) err.value = p.error
  } catch (e) {
    err.value = String(e)
  }
}

async function loadRelations() {
  if (!pid.value || relations.value) return
  relations.value = await api.relations(pid.value)
}

async function loadGraph() {
  if (!pid.value) return
  graph.value = await api.graph(pid.value, 1, 120)
}

// ---------------------------------------------------------------- 预设查询
const presets = ref([])
const presetKey = ref('')
const presetData = ref(null)
const presetLoading = ref(false)

async function runPreset(key) {
  presetKey.value = key
  presetLoading.value = true
  presetData.value = null
  try {
    presetData.value = await api.preset(key, pid.value)
  } catch (e) {
    err.value = String(e)
  } finally {
    presetLoading.value = false
  }
}

// ---------------------------------------------------------------- SQL 沙盒
const sqlText = ref(
  'SELECT p.c_name_chn, p.c_index_year, COUNT(*) AS 事件数\n' +
  'FROM LIFE_EVENT_RESOLVED r\n' +
  'JOIN BIOG_MAIN p ON p.c_personid = r.c_personid\n' +
  "WHERE r.stage = '任官'\n" +
  'GROUP BY p.c_personid\n' +
  'ORDER BY 事件数 DESC\n' +
  'LIMIT 30;'
)
const sqlResult = ref(null)
const sqlErr = ref('')
const sqlRunning = ref(false)

async function runSql() {
  sqlRunning.value = true
  sqlErr.value = ''
  sqlResult.value = null
  try {
    sqlResult.value = await api.sql(sqlText.value)
  } catch (e) {
    sqlErr.value = String(e.message || e)
  } finally {
    sqlRunning.value = false
  }
}

const SQL_SAMPLES = [
  ['某人区间年谱', 'SELECT lo, hi, width, stage, event_label\nFROM LIFE_EVENT_RESOLVED\nWHERE c_personid = 1762 AND width <= 50\nORDER BY lo;'],
  ['全库区间轴质量', 'SELECT precision, COUNT(*) n, ROUND(AVG(width),1) avg_w\nFROM LIFE_EVENT_RESOLVED GROUP BY precision;'],
  ['各朝代人数', 'SELECT d.c_dynasty_chn 朝代, COUNT(*) 人数\nFROM BIOG_MAIN b JOIN DYNASTIES d ON d.c_dy = b.c_dy\nGROUP BY 1 ORDER BY 人数 DESC;'],
  ['籍贯 TOP20', "SELECT ad.c_name_chn 籍贯, COUNT(*) 人数\nFROM BIOG_ADDR_DATA a\nJOIN ADDR_CODES ad ON ad.c_addr_id = a.c_addr_id\nJOIN BIOG_ADDR_CODES t ON t.c_addr_type = a.c_addr_type\nWHERE t.c_addr_desc_chn LIKE '%籍貫%'\nGROUP BY 1 ORDER BY 人数 DESC LIMIT 20;"],
  ['脏数据线索', 'SELECT r.c_personid, p.c_name_chn, r.stage, r.event_label\nFROM LIFE_EVENT_RESOLVED r JOIN BIOG_MAIN p ON p.c_personid = r.c_personid\nWHERE r.conflict = 1 LIMIT 50;'],
]

// ---------------------------------------------------------------- Tabs
const tab = ref('timeline')
const TABS = [
  { k: 'timeline', name: '区间年谱' },
  { k: 'relations', name: '关系网络' },
  { k: 'profile', name: '人物档案' },
  { k: 'preset', name: '预设查询' },
  { k: 'sql', name: 'SQL 沙盒' },
]

watch(tab, (v) => {
  if (v === 'relations') { loadRelations(); loadGraph() }
  if (v === 'preset' && !presets.value.length) api.presets().then((d) => (presets.value = d.presets))
})

// ---------------------------------------------------------------- init
onMounted(async () => {
  try {
    stats.value = await api.stats()
    presets.value = (await api.presets()).presets
    await loadMeta()
  } catch (e) {
    err.value = `无法连接后端：${e}。请先在 web/ 下运行 python server.py`
  }
})

const filtered = computed(() => {
  let r = timeline.value
  if (stageFilter.value.length)
    r = r.filter((x) => stageFilter.value.includes(x.stage_no))
  if (precFilter.value.length)
    r = r.filter((x) => precFilter.value.includes(x.precision))
  return r
})

function toggle(arr, v) {
  const i = arr.indexOf(v)
  if (i >= 0) arr.splice(i, 1)
  else arr.push(v)
}

function fmtRows(n) {
  if (n == null) return ''
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (n >= 1e4) return Math.round(n / 1e3) + 'k'
  return String(n)
}

function pct(n) {
  const p = stats.value?.persons
  if (!p) return '—'
  return ((n / p) * 100).toFixed(1) + '%'
}

const lifeSpan = computed(() => {
  const p = person.value
  if (!p) return ''
  const b = p.c_birthyear > 0 ? p.c_birthyear : '?'
  const d = p.c_deathyear > 0 ? p.c_deathyear : '?'
  return `${b} — ${d}`
})
</script>

<template>
  <div class="app">
    <!-- 顶栏：恒定一行（原先是 brand+副标题 / 模式 / KPI 三行，占掉 100px） -->
    <header class="top">
      <div class="brand">
        <span class="logo">CBDB</span>
        <span class="title"
          :title="stats ? `${stats.db_file} · ${stats.db_size_mb} MB` : ''">中国历代人物传记资料库 · 查询台</span>
      </div>

      <nav class="modes">
        <button
          v-for="m in MODES"
          :key="m.k"
          :class="{ active: mode === m.k }"
          @click="setMode(m.k)"
        >{{ m.name }}</button>
      </nav>

      <div class="stats muted" v-if="stats">
        {{ fmtRows(stats.persons) }} 人 · {{ fmtRows(stats.events) }} 事件 ·
        {{ stats.tables }} 表 / {{ stats.views }} 视图
        <template v-if="mode === 'view' && meta">
          · {{ Object.keys(meta.views).length }} 个可检索视图 · {{ groups.length }} 组
        </template>
      </div>

      <div class="kpis" v-if="stats">
        <span>有生年 <b>{{ pct(stats.birth_year) }}</b></span>
        <span>有指数年 <b>{{ pct(stats.index_year) }}</b></span>
        <span>已解析区间 <b>{{ fmtRows(stats.resolved) }}</b></span>
      </div>
    </header>

    <div v-if="err" class="err">⚠ {{ err }}</div>

    <!-- ============ 视图检索模式：导航一行 + 结果区吃满 ============ -->
    <div class="main view-mode" v-if="mode === 'view'">
      <ViewNav
        v-if="meta"
        :meta="meta"
        :active-group="activeGroup"
        :active-view="activeView"
        @pick="onPick"
      />
      <section class="content flat">
        <ViewExplorer
          v-if="meta && activeView"
          :meta="meta"
          :view-name="activeView"
          :seed="viewSeed"
          @drill="onDrill"
          @open-view="onOpenView"
          @open-timeline="onOpenTimeline"
        />
        <div v-else class="panel empty-panel muted">正在加载视图元数据 …</div>
      </section>
    </div>

    <!-- ============ 知识图谱模式（原 Gradio 前端迁移到 Vue） ============ -->
    <div class="main" v-else-if="mode === 'kg'">
      <KgExplorer />
    </div>

    <!-- ============ 人物年谱模式 ============ -->
    <div class="main" v-else>
      <!-- 右侧（占满宽度，搜索框移到顶部一行） -->
      <section class="content">
        <!-- 顶部人物定位搜索框（与视图检索同款） -->
        <div class="panel psearch-bar">
          <PersonSearch @select="selectPerson" />
          <span class="muted ps-tip">
            点击人名载入年谱。数据来自 <code>LIFE_EVENT_RESOLVED</code>：每条事件是一个 <b>区间 [lo, hi]</b>。
          </span>
        </div>


        <div v-if="!person" class="panel empty-panel muted">
          在上方搜索并选择一位人物
        </div>

        <template v-else>
          <!-- 人物头 -->
          <div class="panel phead">
            <div class="h-left">
              <h2>{{ person.c_name_chn || person.c_name }}</h2>
              <div class="muted">
                {{ person.dynasty || '未详朝代' }} ·
                生卒 {{ lifeSpan }}
                <span v-if="person.c_index_year"> · 指数年 {{ person.c_index_year }}</span>
                · id {{ person.c_personid }}
              </div>
            </div>
            <div class="h-right">
              <div class="metric"><b>{{ person.total_events }}</b><span>事件</span></div>
              <div class="metric"><b>{{ person.frame === 'birth_death' ? '生卒' : person.frame === 'index_year' ? '指数年' : '兜底' }}</b><span>人生框架</span></div>
            </div>
          </div>

          <!-- 精度体检 -->
          <div class="panel axis-health">
            <div class="ah-title">时间轴体检（精度轴分布）</div>
            <div class="ah-bars">
              <div
                v-for="a in person.axis"
                :key="a.precision"
                class="ah-bar"
                :style="{
                  width: (a.n / person.total_events * 100) + '%',
                  background: { exact: 'var(--p-exact)', propagated: 'var(--p-propagated)', interval: 'var(--p-interval)', frame: 'var(--p-frame)' }[a.precision],
                }"
                :title="`${a.precision}: ${a.n} 条，平均宽 ${a.avg_width} 年`"
              >
                <span>{{ a.precision }} {{ a.n }}</span>
              </div>
            </div>
            <div class="muted">{{ person.total_events }} 条事件 ·
              <template v-for="(a, i) in person.axis" :key="a.precision">
                {{ i ? ' / ' : '' }}{{ a.precision }} {{ a.n }}（均宽 {{ a.avg_width }} 年）
              </template>
            </div>
          </div>

          <!-- Tabs -->
          <div class="tabs">
            <button
              v-for="t in TABS"
              :key="t.k"
              :class="{ active: tab === t.k }"
              @click="tab = t.k"
            >{{ t.name }}</button>
          </div>

          <!-- 年谱 -->
          <div class="panel" v-show="tab === 'timeline'">
            <div class="filters">
              <span class="muted">阶段</span>
              <button
                v-for="s in STAGES"
                :key="s.no"
                class="chip"
                :class="{ on: stageFilter.includes(s.no) }"
                @click="toggle(stageFilter, s.no)"
              >{{ s.name }}</button>
              <span class="muted" style="margin-left:12px">精度</span>
              <button
                v-for="p in PRECISIONS"
                :key="p.k"
                class="chip"
                :class="{ on: precFilter.includes(p.k) }"
                @click="toggle(precFilter, p.k)"
              >{{ p.name }}</button>
              <button
                v-if="stageFilter.length || precFilter.length"
                class="chip clear"
                @click="stageFilter = []; precFilter = []"
              >清除</button>
            </div>
            <IntervalTimeline
              :rows="filtered"
              :birth="person.c_birthyear"
              :death="person.c_deathyear"
            />
          </div>

          <!-- 关系 -->
          <div v-show="tab === 'relations'" class="rel-grid">
            <div class="panel">
              <div class="sec-title">关系网络（一跳）</div>
              <RelationNetwork :graph="graph" :center-id="pid" />
            </div>
            <div class="panel">
              <div class="sec-title">亲属（{{ relations?.kin.length || 0 }}）</div>
              <div class="chips">
                <span v-for="(k, i) in (relations?.kin || []).slice(0, 60)" :key="i" class="tag">
                  {{ k.rel }} · {{ k.other_name }}
                </span>
              </div>
              <div class="sec-title">交游（{{ relations?.assoc.length || 0 }}）</div>
              <div class="chips">
                <span v-for="(a, i) in (relations?.assoc || []).slice(0, 60)" :key="i" class="tag">
                  {{ a.rel }} · {{ a.other_name }}<span v-if="a.year">（{{ a.year }}）</span>
                </span>
              </div>
              <div class="sec-title">任官（有年份）</div>
              <div class="chips">
                <span v-for="(o, i) in (relations?.office || []).slice(0, 60)" :key="i" class="tag">
                  {{ o.year }} · {{ o.other_name }}
                </span>
              </div>
            </div>
          </div>

          <!-- 档案 -->
          <div v-show="tab === 'profile'" class="panel">
            <div class="sec-title">别名字号</div>
            <div class="chips">
              <span v-for="(a, i) in (person.altnames || [])" :key="i" class="tag">
                {{ a.name_type || '別名' }} · {{ a.name }}
              </span>
              <span v-if="!person.altnames?.length" class="muted">—</span>
            </div>
            <div class="sec-title">地理</div>
            <div class="chips">
              <span v-for="(a, i) in (person.addrs || [])" :key="i" class="tag">
                {{ a.addr }}（{{ a.addr_type }}）
              </span>
              <span v-if="!person.addrs?.length" class="muted">—</span>
            </div>
            <div class="sec-title">各阶段事件数与平均区间宽</div>
            <DataTable :columns="['stage', 'n', 'avg_width']" :rows="person.stages || []" max-height="340px" />
          </div>

          <!-- 预设 -->
          <div class="panel" v-show="tab === 'preset'">
            <div class="presets">
              <button
                v-for="p in presets"
                :key="p.key"
                class="chip"
                :class="{ on: presetKey === p.key }"
                @click="runPreset(p.key)"
              >{{ p.name }}</button>
            </div>
            <div v-if="presetLoading" class="muted" style="padding:16px">查询中 …</div>
            <DataTable
              v-else-if="presetData"
              :columns="presetData.columns"
              :rows="presetData.rows"
              max-height="480px"
            />
            <div v-else class="muted" style="padding:16px">选择一个预设查询。带 <code>pid</code> 的会用当前人物。</div>
          </div>

          <!-- SQL -->
          <div class="panel" v-show="tab === 'sql'">
            <div class="samples">
              <button v-for="[n, s] in SQL_SAMPLES" :key="n" class="chip" @click="sqlText = s">{{ n }}</button>
            </div>
            <textarea v-model="sqlText" rows="8" class="mono" spellcheck="false"></textarea>
            <div class="sql-bar">
              <button class="primary" @click="runSql" :disabled="sqlRunning">
                {{ sqlRunning ? '执行中' : '执行（只读）' }}
              </button>
              <span v-if="sqlResult" class="muted">
                {{ sqlResult.rows.length }} 行 · {{ sqlResult.elapsed }}s
              </span>
              <span v-if="sqlErr" class="err-inline">{{ sqlErr }}</span>
            </div>
            <DataTable
              v-if="sqlResult"
              :columns="sqlResult.columns"
              :rows="sqlResult.rows"
              max-height="420px"
            />
          </div>
        </template>
      </section>
    </div>
  </div>
</template>

<style scoped>
.app { display: flex; flex-direction: column; height: 100%; padding: 10px 14px; gap: 9px; }

/* 顶栏：一行装完 —— 品牌 / 模式切换 / 库概况 / KPI 全在同一行 */
.top {
  display: flex; align-items: center; gap: 16px;
  flex: 0 0 auto; min-height: 34px;
}
.brand { display: flex; align-items: center; gap: 9px; flex: 0 0 auto; }
.logo {
  background: var(--accent);
  color: #fff;
  font-weight: 700;
  font-size: 13px;
  padding: 5px 9px;
  border-radius: 7px;
  letter-spacing: 1px;
}
.title { font-size: 14.5px; font-weight: 600; white-space: nowrap; }
.stats { font-size: 12px; flex: 1 1 auto; min-width: 0; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }
.kpis { display: flex; gap: 14px; font-size: 12px; color: var(--muted); flex: 0 0 auto; }
.kpis b { color: var(--text); font-size: 13px; margin-left: 3px; }

.err {
  background: #fdecec;
  border: 1px solid #f5c2c2;
  color: #a33;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 13px;
}
.err-inline { color: #a33; font-size: 13px; }

.main { display: flex; gap: 12px; flex: 1 1 auto; min-height: 0; }
/* 视图检索：外层改纵向 —— 导航条一行 + 结果区吃满剩余高度（原来是 260px 左侧栏 + 右内容） */
.main.view-mode { flex-direction: column; gap: 8px; overflow: hidden; }
/* 主模式切换条（已并入顶栏） */
.modes { display: flex; align-items: center; gap: 4px; flex: 0 0 auto; }
.modes button { padding: 4px 12px; font-size: 13px; }
.modes button.active { background: var(--accent); border-color: var(--accent); color: #fff; }

.side { width: 300px; flex: 0 0 300px; padding: 12px; display: flex; flex-direction: column; gap: 10px; min-height: 0; }
.empty-panel { padding: 60px; text-align: center; }

/* 人物定位搜索条：占满顶部一行，下方年谱占满剩余宽度 */
.psearch-bar { display: flex; align-items: center; gap: 12px; flex: 0 0 auto; flex-wrap: wrap; }
.psearch-bar .ps-tip { font-size: 12px; line-height: 1.4; }

.content { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 10px; overflow-y: auto; }
/* 视图检索模式：内部自带滚动（结果表占满高度），外层不要再滚 */
.content.flat { overflow: hidden; gap: 0; }

.phead { padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; }
.phead h2 { margin: 0; font-size: 20px; }
.h-right { display: flex; gap: 18px; }
.metric { text-align: center; }
.metric b { display: block; font-size: 18px; }
.metric span { font-size: 11px; color: var(--muted); }

.axis-health { padding: 10px 16px; }
.ah-title { font-size: 12px; font-weight: 600; margin-bottom: 6px; }
.ah-bars { display: flex; height: 20px; border-radius: 4px; overflow: hidden; margin-bottom: 6px; }
.ah-bar { display: flex; align-items: center; justify-content: center; font-size: 10px; color: #fff; overflow: hidden; }
.axis-health .muted { font-size: 12px; }

.tabs { display: flex; gap: 6px; }
.tabs button.active { background: var(--accent); border-color: var(--accent); color: #fff; }

.filters { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; padding: 10px 14px; border-bottom: 1px solid var(--border); }
.chip { padding: 2px 9px; font-size: 12px; border-radius: 12px; }
.chip.on { background: var(--accent); border-color: var(--accent); color: #fff; }
.chip.clear { color: #a33; }

.sec-title { font-size: 12px; font-weight: 600; margin: 10px 0 6px; padding: 0 14px; }
.chips { display: flex; flex-wrap: wrap; gap: 4px; padding: 0 14px 6px; }

.rel-grid { display: grid; grid-template-columns: 1.15fr 1fr; gap: 10px; align-items: start; }

.presets { display: flex; flex-wrap: wrap; gap: 5px; padding: 10px 14px; border-bottom: 1px solid var(--border); }
.samples { display: flex; flex-wrap: wrap; gap: 5px; padding: 10px 14px; }
textarea { margin: 0 14px; width: calc(100% - 28px); font-size: 12.5px; }
.sql-bar { display: flex; align-items: center; gap: 12px; padding: 10px 14px; }
</style>
