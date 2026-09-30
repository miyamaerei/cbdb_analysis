<script setup>
// 视图检索：单行工具栏 + 结果区吃满剩余高度 + 右侧条件抽屉
//
// 布局取舍（对应「条件太多把结果表挤没了」）：
//   1. 原来左侧那条 260px 的分组树已经移到 App 的 ViewNav（一行），本组件不再有侧栏
//   2. 页面上只留一行工具栏：全局搜索 / Top-3 快捷条件 / 已选 chips / 结果统计 / 翻页 / 按钮组
//   3. 结果表 flex 占满，表头 sticky、内部滚动；排序改成点表头（省掉一整行排序控件）
//   4. 其余条件全部收进右侧抽屉，抽屉内可搜条件名
//   5. 条件状态写进 URL hash，可分享 / 刷新 / 后退；另可存成本地预设
//
// 列名显示策略（对应「c_xxx 对新人太不友好、但同时显示中英文又太乱」）：
//   默认只显示中文名；原始列名通过三条路径兜底 ——
//     a. 表头 / 控件 hover 时的 tooltip（零视觉成本）
//     b. 抽屉（精确配置处）里的控件名下方小号等宽字
//     c. 全局开关「原始列名」（localStorage 记住），一开全部显示
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { api } from '../api'
import FilterControl from './FilterControl.vue'

const props = defineProps({
  meta: { type: Object, required: true },
  viewName: { type: String, required: true },
  // 跨视图下钻：{ col, value, n }；或 URL 恢复：{ state, n }
  seed: { type: Object, default: null },
})
const emit = defineEmits(['drill', 'open-timeline', 'open-view'])

const PAGE = 100
const LS_KEY = 'cbdb.savedViews'
const LS_PREF = 'cbdb.viewPrefs'
const DEFAULT_VISIBLE = 14

const view = computed(() => props.meta.views?.[props.viewName] || null)
const viewZh = computed(() => props.meta.view_labels?.[props.viewName]?.zh || props.viewName)

// ---------------------------------------------------------------- 列名中文化
const labels = computed(() => view.value?.labels || {})
/** 中文名；没有就回落原始列名 */
function lbl(c) {
  return labels.value[c] || c
}
/** hover 提示：中文（原始列名） */
function lblTip(c) {
  const t = labels.value[c]
  return t ? `${t}（${c}）` : c
}
const KEY_LABELS = computed(() => Object.fromEntries(props.meta.join_keys || []))

// ---------------------------------------------------------------- 显示偏好（记住）
function loadPrefs() {
  try {
    return JSON.parse(localStorage.getItem(LS_PREF)) || {}
  } catch {
    return {}
  }
}
const prefs = loadPrefs()
const dense = ref(!!prefs.dense)          // 紧凑行高
const showRaw = ref(!!prefs.showRaw)      // 全局显示原始列名
function savePrefs() {
  localStorage.setItem(LS_PREF, JSON.stringify({ dense: dense.value, showRaw: showRaw.value }))
}
watch([dense, showRaw], savePrefs)

// ---------------------------------------------------------------- 状态
const filters = ref({})          // { col: {op, val, val2} }  —— AND
const globalQ = ref('')          // 全局关键词 —— 跨文本列 OR
const sort = ref({ col: '', dir: 'ASC' })
const rows = ref([])
const columns = ref([])
const loading = ref(false)
const error = ref('')
const hasMore = ref(false)
const page = ref(0)
const elapsed = ref(0)

const hidden = ref(new Set())
const drawer = ref(false)
const condQ = ref('')            // 抽屉内「搜索条件名」
const pop = ref('')              // 浮层：'' | '__cols__' | '__person__' | '__saved__' | '__group__'

const personQ = ref('')
const personHits = ref([])

// ---------------------------------------------------------------- 条件判定
function isActive(f) {
  if (!f) return false
  if (f.op === 'notnull' || f.op === 'isnull') return true
  if (f.op === 'in') return Array.isArray(f.val) && f.val.length > 0
  if (f.op === 'between') return f.val !== '' && f.val != null && f.val2 !== '' && f.val2 != null
  return f.val !== '' && f.val !== null && f.val !== undefined
}

const activeFilters = computed(() =>
  Object.entries(filters.value).filter(([, f]) => isActive(f))
)
const condCount = computed(
  () => activeFilters.value.length + (globalQ.value.trim() ? 1 : 0)
)

function chipText(col) {
  const f = filters.value[col]
  if (!isActive(f)) return ''
  if (f.op === 'notnull') return '非空'
  if (f.op === 'isnull') return '为空'
  if (f.op === 'in') {
    const s = f.val.join(' / ')
    return s.length > 24 ? s.slice(0, 24) + '…' : s
  }
  if (f.op === 'between') return `${f.val}~${f.val2}`
  if (f.op === 'contains') return `含 ${f.val}`
  if (f.op === 'eq') return `= ${f.val}`
  if (f.op === 'startswith') return `${f.val}…`
  return String(f.val)
}

// 工具栏只放 3 个最可能常用的：人物 → 年份 → 枚举
const quickCols = computed(() => {
  const fs = view.value?.filters || []
  const out = []
  for (const k of ['pid', 'year', 'cat', 'num', 'text']) {
    for (const c of fs) {
      if (c.kind === k && out.length < 3 && !out.includes(c)) out.push(c)
    }
  }
  return out
})

// 全局关键词作用的列：优先字符串型，取前 24 列，避免 LIKE 链过长
const globalCols = computed(() => {
  const fs = view.value?.filters || []
  const str = fs.filter((c) => c.kind === 'text' || c.kind === 'cat').map((c) => c.name)
  return (str.length ? str : view.value?.columns || []).slice(0, 24)
})

const shownColumns = computed(() =>
  (columns.value.length ? columns.value : view.value?.columns || []).filter(
    (c) => !hidden.value.has(c)
  )
)

// 抽屉内条件列表（中文名与原始列名都能搜）
const drawerCols = computed(() => {
  const fs = view.value?.filters || []
  const kw = condQ.value.trim().toLowerCase()
  if (!kw) return fs
  return fs.filter(
    (c) => c.name.toLowerCase().includes(kw) || (c.label || '').toLowerCase().includes(kw)
  )
})
const DRAWER_GROUPS = [
  { k: 'pid', title: '人物 / 主键' },
  { k: 'year', title: '年份区间' },
  { k: 'num', title: '数值区间' },
  { k: 'cat', title: '枚举取值' },
  { k: 'text', title: '文本匹配' },
]
const drawerGroups = computed(() =>
  DRAWER_GROUPS.map((g) => ({ ...g, cols: drawerCols.value.filter((c) => c.kind === g.k) })).filter(
    (g) => g.cols.length
  )
)
const hiddenCount = computed(() => (view.value?.filters || []).length - activeFilters.value.length)

// ---------------------------------------------------------------- 条件写操作
function setFilter(col, patch) {
  const cur = filters.value[col] || { op: 'eq', val: '', val2: '' }
  filters.value[col] = { ...cur, ...patch }
  filters.value = { ...filters.value }
}
function clearFilter(col) {
  delete filters.value[col]
  filters.value = { ...filters.value }
}
function toggleCat(col, v) {
  const cur = filters.value[col]
  if (!cur || cur.op !== 'in' || !Array.isArray(cur.val)) {
    filters.value[col] = { op: 'in', val: [v], val2: '' }
  } else {
    const i = cur.val.indexOf(v)
    if (i >= 0) cur.val.splice(i, 1)
    else cur.val.push(v)
    if (!cur.val.length) delete filters.value[col]
    else filters.value[col] = { ...cur }
  }
  filters.value = { ...filters.value }
}
function resetAll() {
  filters.value = {}
  globalQ.value = ''
  sort.value = { col: '', dir: 'ASC' }
  page.value = 0
  run()
}
function defaultHidden() {
  return new Set((view.value?.columns || []).slice(DEFAULT_VISIBLE))
}
function showAllCols() {
  hidden.value = new Set()
}
function showDefaultCols() {
  hidden.value = defaultHidden()
}
function toggleCol(c) {
  if (hidden.value.has(c)) hidden.value.delete(c)
  else hidden.value.add(c)
  hidden.value = new Set(hidden.value)
}
// 显示列优先展示有中文名、且是关联键的列
const allColsSorted = computed(() => {
  const cols = view.value?.columns || []
  return cols
})

// ---------------------------------------------------------------- 排序（点表头）
function sortBy(c) {
  if (sort.value.col !== c) sort.value = { col: c, dir: 'ASC' }
  else if (sort.value.dir === 'ASC') sort.value = { col: c, dir: 'DESC' }
  else sort.value = { col: '', dir: 'ASC' }
  run()
}

// ---------------------------------------------------------------- 查询
function payload(offset = 0) {
  const gq = globalQ.value.trim()
  return {
    filters: activeFilters.value.map(([col, f]) => ({ col, ...f })),
    any: gq ? [{ cols: globalCols.value, val: gq }] : [],
    sort: sort.value.col ? sort.value : null,
    limit: PAGE,
    offset,
  }
}

let seq = 0
async function run(resetPage = true) {
  if (!view.value) return
  if (resetPage) page.value = 0
  const me = ++seq
  loading.value = true
  error.value = ''
  try {
    const r = await api.view(props.viewName, payload(page.value * PAGE))
    if (me !== seq) return
    rows.value = r.rows
    columns.value = r.columns
    hasMore.value = r.has_more
    elapsed.value = r.elapsed
  } catch (e) {
    if (me !== seq) return
    error.value = String(e.message || e)
    rows.value = []
  } finally {
    if (me === seq) loading.value = false
  }
}

function nextPage() {
  page.value += 1
  run(false)
}
function prevPage() {
  if (page.value > 0) {
    page.value -= 1
    run(false)
  }
}

// 条件变化 → 自动重查（合并连续输入，避免每敲一个字打一次库）
let timer = null
function scheduleRun() {
  clearTimeout(timer)
  timer = setTimeout(() => run(), 320)
}

// ---------------------------------------------------------------- 本地预设
function loadAll() {
  try {
    return JSON.parse(localStorage.getItem(LS_KEY)) || {}
  } catch {
    return {}
  }
}
const saved = ref(loadAll()[props.viewName] || [])

function snapshot() {
  return {
    view: props.viewName,
    q: globalQ.value,
    f: JSON.parse(JSON.stringify(filters.value)),
    s: sort.value.col ? [sort.value.col, sort.value.dir] : null,
    p: page.value,
  }
}
function applyState(st) {
  filters.value = JSON.parse(JSON.stringify(st.f || {}))
  globalQ.value = st.q || ''
  sort.value = st.s ? { col: st.s[0], dir: st.s[1] } : { col: '', dir: 'ASC' }
  page.value = st.p || 0
}
function saveCurrent() {
  const name = window.prompt('把这组条件存为（起个名字）：', '')
  if (!name) return
  const all = loadAll()
  const list = (all[props.viewName] || []).filter((x) => x.name !== name)
  list.push({ name, ...snapshot() })
  all[props.viewName] = list
  localStorage.setItem(LS_KEY, JSON.stringify(all))
  saved.value = list
  pop.value = ''
}
function applySaved(sv) {
  applyState(sv)
  pop.value = ''
  run(false)
}
function delSaved(sv) {
  const all = loadAll()
  all[props.viewName] = (all[props.viewName] || []).filter((x) => x.name !== sv.name)
  localStorage.setItem(LS_KEY, JSON.stringify(all))
  saved.value = all[props.viewName]
}

// ---------------------------------------------------------------- URL 同步
function writeUrl() {
  const st = snapshot()
  const h =
    '#view=' + encodeURIComponent(st.view) + '&st=' + encodeURIComponent(JSON.stringify(st))
  history.replaceState(null, '', location.pathname + location.search + h)
}
function readUrl() {
  const h = location.hash.replace(/^#/, '')
  if (!h) return null
  try {
    const raw = new URLSearchParams(h).get('st')
    return raw ? JSON.parse(decodeURIComponent(raw)) : null
  } catch {
    return null
  }
}

// ---------------------------------------------------------------- 初始化
const boot = readUrl()
let bootDone = false

watch(
  () => [props.viewName, props.seed],
  () => {
    saved.value = loadAll()[props.viewName] || []
    hidden.value = defaultHidden()
    pop.value = ''

    condQ.value = ''
    drawer.value = false

    let restored = false
    if (boot && !bootDone) {
      bootDone = true
      if (boot.view && boot.view !== props.viewName) {
        // URL 指向的是另一个视图：交给 App 切过去，并把这组条件带过去
        emit('open-view', boot.view, boot)
        return
      }
      applyState(boot)
      restored = true
    } else if (props.seed?.state) {
      applyState(props.seed.state)
      restored = true
    } else {
      globalQ.value = ''
      filters.value = {}
      sort.value = { col: '', dir: 'ASC' }
      page.value = 0
      const col = props.seed?.col
      if (col && props.seed.value !== null && props.seed.value !== undefined) {
        const kind = (view.value?.filters || []).find((c) => c.name === col)?.kind
        setFilter(col, { op: kind === 'text' ? 'contains' : 'eq', val: props.seed.value })
      }
    }
    rows.value = []
    columns.value = []
    run(!restored)
  },
  { immediate: true }
)

watch([filters, sort, globalQ, page], () => writeUrl(), { deep: true })
watch(globalQ, scheduleRun)
watch(filters, scheduleRun, { deep: true })

// Esc 关闭所有浮层
function onKey(e) {
  if (e.key !== 'Escape') return
  pop.value = ''

  drawer.value = false
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))

// ---------------------------------------------------------------- 跨视图下钻
const drill = ref(null)
function viewsWithKey(col) {
  return (props.meta.groups || [])
    .map((g) => ({
      group: g.name,
      views: g.views.filter(
        (v) => v !== props.viewName && (props.meta.views[v]?.join_keys || []).includes(col)
      ),
    }))
    .filter((g) => g.views.length)
}
function vzh(v) {
  return props.meta.view_labels?.[v]?.zh || v.replace(/^View_/, '')
}
function doDrill(v) {
  emit('drill', { view: v, key: drill.value.col, value: drill.value.value })
  drill.value = null
}

// ---------------------------------------------------------------- 人物定位
async function searchPerson() {
  if (!personQ.value.trim()) return
  personHits.value = await api.search(personQ.value.trim(), 20)
}
function pickPerson(p) {
  setFilter('c_personid', { op: 'eq', val: p.c_personid, val2: '' })
  pop.value = ''
  personHits.value = []
  personQ.value = ''
}
</script>

<template>
  <div class="ve">
    <!-- ============ 工具栏：恒定一行 ============ -->
    <div class="panel fbar">
      <div class="gsearch">
        <span class="mag">⌕</span>
        <input
          v-model="globalQ"
          placeholder="在所有文本列中搜索…"
          :title="`实际搜索 ${globalCols.length} 列：${globalCols.map(lblTip).join('、')}`"
        />
        <button v-if="globalQ" class="gnone" @click="globalQ = ''">×</button>
      </div>

      <div class="qwrap">
        <button
          v-for="c in quickCols"
          :key="c.name"
          class="qbtn"
          :class="{ on: isActive(filters[c.name]), open: pop === c.name }"
          :title="lblTip(c.name)"
          @click="pop = pop === c.name ? '' : c.name"
        >
          <span class="qn">{{ c.label || c.name }}</span>
          <span v-if="chipText(c.name)" class="qv">{{ chipText(c.name) }}</span>
          <span class="car">▾</span>
        </button>
        <button
          v-if="view?.join_keys?.includes('c_personid')"
          class="qbtn"
          :class="{ on: isActive(filters.c_personid), open: pop === '__person__' }"
          title="按姓名查人物ID（支持简繁）"
          @click="pop = pop === '__person__' ? '' : '__person__'"
        >
          <span class="qn">按姓名</span>
          <span v-if="chipText('c_personid')" class="qv">{{ chipText('c_personid') }}</span>
          <span class="car">▾</span>
        </button>
      </div>

      <!-- 已选条件 chips -->
      <div class="chips">
        <span v-for="[col, f] in activeFilters" :key="col" class="tag on" :title="`${lblTip(col)} ${chipText(col)}`">
          {{ lbl(col) }} {{ chipText(col) }}
          <b @click="clearFilter(col)">×</b>
        </span>
        <span v-if="globalQ" class="tag on" title="全列关键词">
          全列含 <b>{{ globalQ }}</b><i @click="globalQ = ''">×</i>
        </span>
        <span v-if="sort.col" class="tag on" :title="`按 ${lblTip(sort.col)} 排序`">
          排序 {{ lbl(sort.col) }} {{ sort.dir === 'ASC' ? '↑' : '↓' }}
          <b @click="sort = { col: '', dir: 'ASC' }; run()">×</b>
        </span>
      </div>

      <!-- 右侧：统计 / 密度 / 按钮 / 翻页（不参与滚动，永远可见） -->
      <div class="fb-right">
        <span class="cnt muted">
          <template v-if="loading">查询中…</template>
          <template v-else-if="error">—</template>
          <template v-else>{{ rows.length }} 行<template v-if="hasMore">+</template><template v-if="elapsed"> · {{ elapsed }}s</template></template>
        </span>
        <button
          class="chip icon"
          :class="{ on: dense }"
          :title="dense ? '紧凑行高（点击切舒适）' : '舒适行高（点击切紧凑）'"
          @click="dense = !dense"
        >{{ dense ? '≡' : '≣' }}</button>
        <button
          class="chip"
          :class="{ on: showRaw }"
          title="表头同时显示数据库原始列名"
          @click="showRaw = !showRaw"
        >列名</button>
        <button class="chip" :class="{ on: pop === '__cols__' }" title="选择显示的列" @click="pop = pop === '__cols__' ? '' : '__cols__'">
          列 {{ shownColumns.length }}/{{ view?.columns?.length ?? 0 }}
        </button>
        <button class="chip" @click="drawer = !drawer" title="打开全部查询条件">
          筛选 <i v-if="condCount">{{ condCount }}</i>
        </button>
        <button class="chip" @click="resetAll" :disabled="!condCount && !sort.col">重置</button>
        <span class="pg">
          <button class="icon" @click="prevPage" :disabled="page === 0 || loading" title="上一页">‹</button>
          <span class="muted">{{ page + 1 }}</span>
          <button class="icon" @click="nextPage" :disabled="!hasMore || loading" title="下一页">›</button>
        </span>
        <button class="chip primary" @click="run()" :disabled="loading">刷新</button>
      </div>

      <!-- 浮层容器 -->
      <div class="popmask" v-if="pop" @click="pop = ''"></div>
      <div class="pop" v-if="pop">
        <!-- 单列条件 -->
        <template v-if="pop && (view?.filters || []).some((c) => c.name === pop)">
          <FilterControl
            :key="pop"
            :col="(view?.filters || []).find((c) => c.name === pop)"
            :filter="filters[pop]"
            compact
            @patch="setFilter(pop, $event)"
            @toggle-cat="toggleCat(pop, $event)"
            @clear="clearFilter(pop)"
          />
        </template>

        <!-- 按姓名定位 -->
        <template v-else-if="pop === '__person__'">
          <div class="pop-h">按姓名定位「{{ lbl('c_personid') }}」</div>
          <div class="row">
            <input v-model="personQ" placeholder="如 王守仁 / 苏轼" @keyup.enter="searchPerson" />
            <button @click="searchPerson">搜索</button>
          </div>
          <div class="pp-list">
            <div v-for="p in personHits" :key="p.c_personid" class="pp-item" @click="pickPerson(p)">
              {{ p.c_name_chn }}
              <span class="muted">id={{ p.c_personid }} · {{ p.dynasty || '—' }} · {{ p.events }} 事件</span>
            </div>
          </div>
        </template>

        <!-- 列显示 -->
        <template v-else-if="pop === '__cols__'">
          <div class="pop-h">
            显示列
            <span class="sp"></span>
            <button class="mini" @click="showDefaultCols">默认 {{ DEFAULT_VISIBLE }} 列</button>
            <button class="mini" @click="showAllCols">全选</button>
            <button class="mini" @click="showRaw = !showRaw">{{ showRaw ? '藏起列名' : '显示列名' }}</button>
          </div>
          <div class="colpick">
            <label v-for="c in allColsSorted" :key="c" :title="lblTip(c)">
              <input type="checkbox" :checked="!hidden.has(c)" @change="toggleCol(c)" />
              <span class="cl">{{ lbl(c) }}</span>
              <span v-if="showRaw" class="raw mono">{{ c }}</span>
            </label>
          </div>
        </template>

        <!-- 预设 -->
        <template v-else>
          <div class="pop-h">
            条件预设（存在本机浏览器）
            <span class="sp"></span>
            <button class="mini" @click="saveCurrent">存当前条件</button>
          </div>
          <div v-if="!saved.length" class="muted empty-mini">还没有预设。调好条件后点「存当前条件」。</div>
          <div v-for="sv in saved" :key="sv.name" class="sv-item">
            <a @click="applySaved(sv)">{{ sv.name }}</a>
            <span class="muted">
              {{ (Object.keys(sv.f || {}).length) }} 条条件<span v-if="sv.q"> + 全列搜索</span>
            </span>
            <b @click="delSaved(sv)">×</b>
          </div>
        </template>
      </div>
    </div>

    <!-- ============ 结果：吃满剩余高度 ============ -->
    <div class="panel result">
      <div class="r-wrap" v-if="rows.length">
        <table class="grid" :class="{ dense }">
          <thead>
            <tr>
              <th class="idx">#</th>
              <th
                v-for="c in shownColumns"
                :key="c"
                :title="lblTip(c) + (KEY_LABELS[c] ? ' · 关联键，点值可下钻' : '') + ' · 点表头排序'"
                @click="sortBy(c)"
              >
                <div class="th-in">
                  <span class="thz">{{ lbl(c) }}</span>
                  <span v-if="showRaw" class="thraw mono">{{ c }}</span>
                  <span v-if="KEY_LABELS[c]" class="keybadge">🔗</span>
                  <span class="ind" :class="{ on: sort.col === c }">
                    {{ sort.col === c ? (sort.dir === 'ASC' ? '▲' : '▼') : '↕' }}
                  </span>
                </div>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in rows" :key="i">
              <td class="muted mono idx">{{ page * PAGE + i + 1 }}</td>
              <td v-for="c in shownColumns" :key="c">
                <span
                  v-if="KEY_LABELS[c] && r[c] !== null && r[c] !== undefined"
                  class="link"
                  @click="drill = { col: c, value: r[c] }"
                  :title="`在其它视图中查 ${lblTip(c)} = ${r[c]}`"
                >{{ r[c] }}</span>
                <span v-else>{{ r[c] === null || r[c] === undefined ? '—' : r[c] }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-else-if="!loading" class="empty muted">
        <div v-if="error">查询出错：{{ error }}</div>
        <template v-else>
          <div>没有匹配结果 —— 试试放宽条件</div>
          <div class="ehint">「{{ viewZh }}」{{ view?.columns?.length }} 列、{{ view?.filters?.length }} 个可筛列；条件都在右上角「筛选」里。</div>
        </template>
        <div v-if="condCount" style="margin-top:10px">
          <button @click="resetAll">清除全部条件</button>
        </div>
      </div>
      <div v-else class="empty muted">查询中 …</div>
    </div>

    <!-- ============ 右侧条件抽屉 ============ -->
    <div class="d-mask" v-if="drawer" @click.self="drawer = false">
      <aside class="drawer">
        <div class="d-head">
          <b>全部查询条件</b>
          <span class="muted">已用 {{ activeFilters.length }} / {{ view?.filters?.length }} 列</span>
          <span class="sp"></span>
          <button class="mini" :class="{ on: showRaw }" @click="showRaw = !showRaw">原始列名</button>
          <button class="mini" @click="resetAll" :disabled="!condCount">清空</button>
          <button class="primary" @click="run(); drawer = false">应用</button>
          <button class="mini" @click="drawer = false">×</button>
        </div>

        <div class="d-search">
          <input
            v-model="condQ"
            :placeholder="`在 ${view?.filters?.length} 个可筛列中搜索（中文名或 c_xx 列名都行）…`"
          />
        </div>

        <div class="d-body">
          <div v-if="hiddenCount" class="d-tip muted">另有 {{ hiddenCount }} 列未设条件，往下找即可。</div>
          <section v-for="g in drawerGroups" :key="g.k" class="d-group">
            <h4>{{ g.title }} <i>{{ g.cols.length }}</i></h4>
            <FilterControl
              v-for="c in g.cols"
              :key="c.name"
              :col="c"
              :filter="filters[c.name]"
              @patch="setFilter(c.name, $event)"
              @toggle-cat="toggleCat(c.name, $event)"
              @clear="clearFilter(c.name)"
            />
          </section>
          <div v-if="condQ && !drawerGroups.length" class="muted empty-mini">
            没有匹配「{{ condQ }}」的可筛列。
          </div>
        </div>
      </aside>
    </div>

    <!-- ============ 下钻弹层 ============ -->
    <div v-if="drill" class="drill-mask" @click.self="drill = null">
      <div class="drill panel">
        <div class="d-title">
          在其它视图中查
          <code>{{ drill.col }}</code>
          <span class="muted">({{ lbl(drill.col) }})</span>
          = <b>{{ drill.value }}</b>
          <button @click="drill = null">关闭</button>
        </div>
        <div v-for="g in viewsWithKey(drill.col)" :key="g.group" class="dgrp">
          <div class="d-gname">{{ g.group }}</div>
          <button v-for="v in g.views" :key="v" class="chip" :title="v" @click="doDrill(v)">
            {{ vzh(v) }}
          </button>
        </div>
        <div class="dgrp" v-if="drill.col === 'c_personid'">
          <div class="d-gname">生平</div>
          <button class="chip" @click="emit('open-timeline', drill.value); drill = null">
            查看区间年谱
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ve {
  display: flex; flex-direction: column; gap: 8px;
  height: 100%; min-height: 0; flex: 1 1 auto;
}

/* ---------------- 工具栏（一行，不换行） ---------------- */
.fbar {
  position: relative;
  display: flex; align-items: center; gap: 7px;
  flex-wrap: nowrap;
  padding: 6px 10px; flex: 0 0 auto;
}
.gsearch { position: relative; display: flex; align-items: center; flex: 0 0 230px; }
.gsearch .mag { position: absolute; left: 8px; color: var(--muted); font-size: 15px; pointer-events: none; }
.gsearch input { padding-left: 25px; padding-right: 24px; font-size: 13px; }
.gsearch .gnone { position: absolute; right: 3px; border: 0; background: transparent; color: var(--muted); padding: 2px 6px; }
.gsearch .gnone:hover { color: var(--text); }

.qwrap { display: flex; gap: 5px; flex: 0 0 auto; }
.qbtn {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 8px; font-size: 12px; border-radius: 6px;
  border: 1px dashed var(--border); background: #fff; color: var(--text);
  white-space: nowrap;
}
.qbtn:hover { border-color: var(--accent); color: var(--accent); }
.qbtn.on { border-style: solid; background: var(--accent-soft); border-color: #b9d0ff; color: var(--accent); }
.qbtn.open { box-shadow: 0 0 0 3px var(--accent-soft); }
.qbtn .qv { font-weight: 600; max-width: 120px; overflow: hidden; text-overflow: ellipsis; }
.qbtn .car { opacity: 0.5; font-size: 9px; }

.chips {
  display: flex; gap: 5px; align-items: center;
  flex: 1 1 auto; min-width: 0; overflow-x: auto; white-space: nowrap;
  scrollbar-width: thin;
}
.chips::-webkit-scrollbar { height: 4px; }
.chips .tag.on {
  background: var(--accent-soft); border-color: #b9d0ff; color: var(--accent);
  flex: 0 0 auto; cursor: default;
}
.chips .tag.on b, .chips .tag.on i { cursor: pointer; margin-left: 4px; font-style: normal; }

.fb-right { display: flex; align-items: center; gap: 5px; flex: 0 0 auto; margin-left: auto; }
.chip { padding: 3px 9px; font-size: 12px; border-radius: 6px; white-space: nowrap; }
.chip.on { background: var(--accent-soft); border-color: #b9d0ff; color: var(--accent); }
.chip i { font-style: normal; margin-left: 3px; }
.chip.icon { padding: 3px 7px; }
.chip.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.cnt { font-size: 12px; min-width: 84px; text-align: right; }
.pg { display: flex; align-items: center; gap: 3px; font-size: 12px; }
.pg .icon { padding: 3px 7px; }

/* 浮层 */
.popmask { position: fixed; inset: 0; z-index: 30; }
.pop {
  position: absolute; top: calc(100% + 4px); left: 10px; z-index: 31;
  width: 430px; max-height: 62vh; overflow: auto;
  background: #fff; border: 1px solid var(--border); border-radius: 8px;
  box-shadow: 0 6px 24px rgba(16, 24, 40, 0.12); padding: 10px;
}
.pop-h { display: flex; align-items: center; gap: 6px; font-size: 12px; font-weight: 600; margin-bottom: 7px; }
.pop-h .sp, .sp { flex: 1 1 auto; }
.mini { padding: 2px 8px; font-size: 11px; border-radius: 5px; }
.mini.on { background: var(--accent-soft); border-color: #b9d0ff; color: var(--accent); }
.row { display: flex; gap: 6px; }
.pp-list { max-height: 220px; overflow: auto; margin-top: 6px; }
.pp-item { padding: 4px 6px; border-radius: 4px; cursor: pointer; font-size: 13px; display: flex; justify-content: space-between; gap: 8px; }
.pp-item:hover { background: var(--accent-soft); }
.colpick { display: grid; grid-template-columns: 1fr 1fr; gap: 1px 10px; font-size: 12px; }
.colpick label { display: flex; align-items: center; gap: 5px; min-width: 0; padding: 1px 0; }
.colpick input { width: auto; flex: 0 0 auto; }
.colpick .cl { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.colpick .raw { font-size: 10px; color: var(--muted); flex: 0 0 auto; }
.sv-item { display: flex; align-items: center; gap: 8px; padding: 4px 2px; font-size: 13px; }
.sv-item a { color: var(--accent); cursor: pointer; }
.sv-item .sp { flex: 1 1 auto; }
.sv-item b { cursor: pointer; color: var(--muted); }
.sv-item b:hover { color: #a33; }
.empty-mini { font-size: 12px; padding: 8px 2px; }

/* ---------------- 结果：吃满剩余高度 ---------------- */
.result { display: flex; flex-direction: column; flex: 1 1 auto; min-height: 0; padding: 0; overflow: hidden; }
.r-wrap { flex: 1 1 auto; min-height: 0; overflow: auto; border-radius: var(--radius); }
.empty { padding: 50px 20px; text-align: center; margin: auto; }
.ehint { font-size: 12px; margin-top: 6px; }
.err-inline { color: #a33; }

table.grid { font-size: 13px; }
table.grid th { cursor: pointer; user-select: none; white-space: nowrap; z-index: 2; }
table.grid th:hover { background: #f0f4fb; }
table.grid th .th-in { display: flex; align-items: center; gap: 4px; }
table.grid th .thz { font-weight: 600; }
table.grid th .thraw {
  font-size: 10px; font-weight: 400; color: var(--muted);
  background: #f1f3f6; border-radius: 3px; padding: 0 4px;
}
table.grid th .ind { opacity: 0; font-size: 9px; color: var(--muted); margin-left: auto; }
table.grid th:hover .ind { opacity: 0.55; }
table.grid th .ind.on { opacity: 1; color: var(--accent); }
table.grid td { white-space: nowrap; max-width: 340px; overflow: hidden; text-overflow: ellipsis; }
table.grid .idx { width: 46px; text-align: right; }

/* 紧凑行高 */
table.grid.dense { font-size: 12px; }
table.grid.dense th, table.grid.dense td { padding: 2px 8px; }

.link { color: var(--accent); cursor: pointer; text-decoration: underline dotted; }
.keybadge { font-size: 9px; opacity: 0.55; }

/* ---------------- 抽屉 ---------------- */
.d-mask { position: fixed; inset: 0; z-index: 40; background: rgba(15, 20, 28, 0.28); }
.drawer {
  position: absolute; top: 0; right: 0; bottom: 0; width: 430px; max-width: 92vw;
  background: #fff; border-left: 1px solid var(--border);
  display: flex; flex-direction: column; box-shadow: -8px 0 28px rgba(16, 24, 40, 0.12);
}
.d-head { display: flex; align-items: center; gap: 7px; padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 13px; }
.d-head .muted { font-size: 11px; }
.d-search { padding: 8px 12px; border-bottom: 1px solid var(--border); }
.d-search input { font-size: 13px; }
.d-body { flex: 1 1 auto; overflow-y: auto; padding: 10px 12px 24px; display: flex; flex-direction: column; gap: 12px; }
.d-tip { font-size: 11px; }
.d-group h4 {
  margin: 0 0 6px; font-size: 12px; font-weight: 600; color: var(--muted);
  display: flex; align-items: center; gap: 6px;
}
.d-group h4 i { font-style: normal; background: #f0f2f5; border-radius: 8px; padding: 0 6px; font-weight: 400; }
.d-group { display: flex; flex-direction: column; gap: 6px; }

/* ---------------- 下钻 ---------------- */
.drill-mask {
  position: fixed; inset: 0; background: rgba(15, 20, 28, 0.35);
  display: flex; align-items: center; justify-content: center; z-index: 50;
}
.drill { width: 640px; max-height: 70vh; overflow: auto; padding: 14px 16px; }
.d-title { display: flex; align-items: center; gap: 6px; margin-bottom: 10px; font-size: 14px; }
.d-title button { margin-left: auto; }
.dgrp { margin-bottom: 10px; }
.d-gname { font-size: 12px; font-weight: 600; color: var(--muted); margin-bottom: 4px; }
.dgrp .chip { margin-right: 4px; margin-bottom: 4px; }
</style>
