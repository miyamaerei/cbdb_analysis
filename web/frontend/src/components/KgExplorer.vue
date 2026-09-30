<script setup>
// 知识图谱（Vue 版，迁移自 Gradio「🔍 查询 / 📄 详情 / ⚙️ 构建 / ①~⑨ 专题」）。
//
// 四个内部分页：检索 / 详情 / 专题 / 导出。
//   * 检索：复用后端 search_persons_fallback（含简繁 + 别名/字号回退链）
//   * 详情：点检索结果行 → 调 /api/kg/person/<id>（自动选图谱，无则源库基本信息回退）
//   * 专题：/api/kg/topics 规格驱动的动态表单 → /api/kg/topic（Q1–Q9，复用 kg_query）
//   * 导出：把当前检索条件发给 /api/kg/export，下载 CSV
//
// 结果表 rows 是**数组**（按 RESULT_HEADERS 顺序），DataTable 已支持数组行按索引渲染。
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import DataTable from './DataTable.vue'
import SearchBox from './SearchBox.vue'
import KgGraph from './KgGraph.vue'

// ---------------------------------------------------------------- 选项
const dynasties = ref([])
const quads = ref([])
const topics = ref([])
const loading = ref(false)
const err = ref('')
const tab = ref('search') // search | detail | topics | export

const ORDER_OPTIONS = [
  { k: 'personid', name: 'ID（默认）' },
  { k: 'birth', name: '生年' },
  { k: 'death', name: '卒年' },
  { k: 'index', name: '指数年' },
  { k: 'name', name: '姓名' },
  { k: 'kin', name: '亲属数' },
  { k: 'assoc', name: '交遊数' },
  { k: 'tenure', name: '任职数' },
]

// ---------------------------------------------------------------- 检索表单
const f = reactive({
  dy: 19,
  name: '',
  pinyin: '',
  gender: '全部',
  birth_from: null, birth_to: null,
  death_from: null, death_to: null,
  index_from: null, index_to: null,
  jinshi_only: false, official_only: false, match_alt: false, include_neighbors: false,
  order_by: 'personid', desc: false, limit: 200,
})

const activeCount = computed(() => {
  let n = 0
  if (f.pinyin.trim()) n++
  if (f.gender !== '全部') n++
  if (f.birth_from != null || f.birth_to != null) n++
  if (f.death_from != null || f.death_to != null) n++
  if (f.index_from != null || f.index_to != null) n++
  if (f.jinshi_only) n++
  if (f.official_only) n++
  if (f.match_alt) n++
  if (f.include_neighbors) n++
  if (f.order_by !== 'personid' || f.desc) n++
  if (Number(f.limit) !== 200) n++
  return n
})

// ---------------------------------------------------------------- 检索结果
const result = ref(null) // { headers, rows, total, dyn_name, truncated, note, used_name }
const selId = ref(null)
const drawer = ref(false)

function num(v) {
  if (v === '' || v == null) return null
  const n = parseInt(v, 10)
  return Number.isFinite(n) ? n : null
}

async function doSearch() {
  loading.value = true
  err.value = ''
  selId.value = null
  try {
    result.value = await api.kgSearch({
      dy: f.dy, name: f.name.trim(), pinyin: f.pinyin.trim(), gender: f.gender,
      birth_from: num(f.birth_from), birth_to: num(f.birth_to),
      death_from: num(f.death_from), death_to: num(f.death_to),
      index_from: num(f.index_from), index_to: num(f.index_to),
      jinshi_only: f.jinshi_only, official_only: f.official_only,
      match_alt: f.match_alt, include_neighbors: f.include_neighbors,
      order_by: f.order_by, desc: f.desc, limit: num(f.limit) || 200,
    })
  } catch (e) {
    err.value = String(e.message || e)
    result.value = null
  } finally {
    loading.value = false
  }
}

function onRow(r) {
  selId.value = r[0] // rows 是数组，personid 在索引 0
  loadPerson(r[0])
  tab.value = 'detail'
}

// ---------------------------------------------------------------- 详情
const person = ref(null)
const personErr = ref('')
const personLoading = ref(false)

async function loadPerson(pid) {
  personLoading.value = true
  personErr.value = ''
  person.value = null
  try {
    const d = await api.kgPerson(pid)
    if (d.error) personErr.value = d.error
    else person.value = d
  } catch (e) {
    personErr.value = String(e.message || e)
  } finally {
    personLoading.value = false
  }
}

const BASIC_LABELS = {
  nameChn: '姓名', namePinyin: '拼音', isFemale: '性别', dynastyOf: '朝代',
  birthYear: '生年', deathYear: '卒年', deathAge: '享年', indexYear: '指数年',
  floruitStart: '活跃起始', floruitEnd: '活跃结束', iri: 'IRI',
}
function femaleText(v) { return v === true ? '女' : (v === false ? '男' : '未详') }

// ---------------------------------------------------------------- 专题
const topicKey = ref('Q1')
const topicQuad = ref('')
const topicVals = reactive([])
const topicResult = ref(null)
const topicErr = ref('')
const topicLoading = ref(false)

const currentTopic = computed(() => topics.value.find(t => t.key === topicKey.value) || null)

// ---------------------------------------------------------------- 力导向图（Q3/Q9）
// 把专题返回的 nodes/edges 表归一化成 KgGraph 需要的 {id,label,group}/{from,to,label}
const graphData = computed(() => {
  const res = topicResult.value
  if (!res || !res.sheets) return null
  const sheets = res.sheets
  if (topicKey.value === 'Q3') {
    const ns = sheets.find(s => s.name === '节点')
    const es = sheets.find(s => s.name === '边')
    if (!ns || !es) return null
    const nodes = ns.rows.map(r => ({
      id: r[1], label: r[2] || String(r[1]), group: `d${r[0]}`, degree: r[0],
      title: `${r[2] || r[1]}（${r[1]}）\n${r[5] || ''} ${r[3] ?? '?'}–${r[4] ?? '?'}`,
    }))
    const edges = es.rows.map(r => ({ from: r[0], to: r[2], label: r[4] }))
    return { nodes, edges }
  }
  if (topicKey.value === 'Q9') {
    const ns = sheets.find(s => s.name === '人物节点')
    const es = sheets.find(s => s.name === '关系边')
    if (!ns || !es) return null
    const nodes = ns.rows.map(r => ({
      id: r[0], label: r[1] || String(r[0]), group: r[2] || '未知',
      title: `${r[1] || r[0]}（${r[0]}）\n${r[2] || ''}`,
    }))
    const edges = es.rows.map(r => ({ from: r[0], to: r[2], label: r[4] }))
    return { nodes, edges }
  }
  return null
})

function onGraphSelect(id) {
  if (id == null) return
  selId.value = id
  loadPerson(id)
  tab.value = 'detail'
}

function defaultVals(fields) {
  topicVals.length = 0
  ;(fields || []).forEach(fld => {
    if (fld.kind === 'checkbox') topicVals.push(fld.default || false)
    else if (fld.default !== undefined && fld.default !== null) topicVals.push(fld.default)
    else if (fld.kind === 'dropdown') topicVals.push(fld.choices ? fld.choices[0] : '')
    else topicVals.push('')
  })
}

function onTopicChange() {
  defaultVals(currentTopic.value?.fields)
  topicResult.value = null
  topicErr.value = ''
}

async function runTopic() {
  if (!topicQuad.value) { topicErr.value = '请先在上方选择一个知识图谱'; return }
  topicLoading.value = true
  topicErr.value = ''
  try {
    topicResult.value = await api.kgTopic({
      key: topicKey.value, quad: topicQuad.value, vals: topicVals.slice(),
    })
  } catch (e) {
    topicErr.value = String(e.message || e)
    topicResult.value = null
  } finally {
    topicLoading.value = false
  }
}

// ---------------------------------------------------------------- 导出
const exportState = ref('') // 状态文案
async function doExport() {
  exportState.value = '生成中…'
  try {
    const { blob, fname } = await api.kgExport({
      dy: f.dy, name: f.name.trim(), pinyin: f.pinyin.trim(), gender: f.gender,
      birth_from: num(f.birth_from), birth_to: num(f.birth_to),
      death_from: num(f.death_from), death_to: num(f.death_to),
      index_from: num(f.index_from), index_to: num(f.index_to),
      jinshi_only: f.jinshi_only, official_only: f.official_only,
      match_alt: f.match_alt, include_neighbors: f.include_neighbors,
      order_by: f.order_by, desc: f.desc, limit: num(f.limit) || 200,
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = fname
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    exportState.value = `✅ 已下载 ${fname}`
  } catch (e) {
    exportState.value = '❌ ' + String(e.message || e)
  }
}

// ---------------------------------------------------------------- 构建（ETL）
const buildDy = ref(19)
const buildLimit = ref(0) // 0 = 全量
const buildLog = ref('')
const buildRunning = ref(false)
const buildDone = ref(false)

async function runBuild() {
  if (buildRunning.value) return
  buildRunning.value = true
  buildDone.value = false
  buildLog.value = '⏳ 正在启动构建…\n'
  try {
    await api.kgBuild(
      { dy: Number(buildDy.value), limit: Number(buildLimit.value) || 0 },
      (ev) => {
        if (ev.log != null) buildLog.value = ev.log
        if (ev.error) { buildLog.value += '\n❌ ' + ev.error; buildDone.value = true }
        if (ev.done) {
          buildDone.value = true
          // 构建完成后刷新图谱清单
          api.kgQuads().then(q => { quads.value = q.quads || [] }).catch(() => {})
        }
      }
    )
  } catch (e) {
    buildLog.value += '\n❌ ' + String(e.message || e)
    buildDone.value = true
  } finally {
    buildRunning.value = false
  }
}

// ---------------------------------------------------------------- 初始化
onMounted(async () => {
  try {
    const d = await api.kgDynasties()
    dynasties.value = d.dynasties || []
    if (dynasties.value.length) f.dy = dynasties.value[0].dy
    const q = await api.kgQuads()
    quads.value = q.quads || []
    if (quads.value.length) topicQuad.value = quads.value[0].path
    const t = await api.kgTopics()
    topics.value = t.topics || []
    if (topics.value.length) defaultVals(topics.value[0].fields)
    await doSearch()
  } catch (e) {
    err.value = `知识图谱服务连接失败：${e}。请确认 kg/api_server.py 已启动。`
  }
})
</script>

<template>
  <div class="kg-app">
    <!-- ============ 内部 Tab 条 ============ -->
    <div class="tabs">
      <button :class="{ on: tab === 'search' }" @click="tab = 'search'">检索</button>
      <button :class="{ on: tab === 'detail' }" @click="tab = 'detail'">
        详情<span v-if="selId != null" class="pid">·{{ selId }}</span>
      </button>
      <button :class="{ on: tab === 'topics' }" @click="tab = 'topics'">专题</button>
      <button :class="{ on: tab === 'export' }" @click="tab = 'export'">导出</button>
      <button :class="{ on: tab === 'build' }" @click="tab = 'build'">构建</button>
    </div>

    <!-- ============ 检索 ============ -->
    <section v-show="tab === 'search'" class="tab-body">
      <div class="panel fbar">
        <SearchBox v-model="f.name" placeholder="姓名（简繁自动，如 王陽明/王阳明）"
          width="240px" @search="doSearch" />
        <select v-model="f.dy" class="dy" title="朝代">
          <option v-for="d in dynasties" :key="d.dy" :value="d.dy">{{ d.label }}</option>
        </select>
        <button class="primary go" @click="doSearch" :disabled="loading">
          {{ loading ? '检索中' : '检索' }}
        </button>
        <button class="chip" :class="{ on: drawer }" @click="drawer = !drawer" title="展开更多检索条件">
          更多条件 <i v-if="activeCount">{{ activeCount }}</i>
        </button>
        <div class="fb-right">
          <span v-if="result" class="cnt muted">
            命中 <b>{{ result.total.toLocaleString() }}</b> 人
            <template v-if="result.truncated">（截断至 {{ f.limit }}）</template>
          </span>
        </div>
      </div>

      <!-- 更多条件抽屉 -->
      <div class="d-mask" v-if="drawer" @click.self="drawer = false">
        <aside class="drawer">
          <div class="d-head">
            <b>检索条件</b><span class="sp"></span>
            <button class="primary" @click="drawer = false">应用</button>
            <button class="mini" @click="drawer = false">×</button>
          </div>
          <div class="d-body">
            <label class="field"><span>拼音</span><input v-model="f.pinyin" placeholder="如 Wang Shouren" /></label>
            <label class="field"><span>性别</span>
              <select v-model="f.gender"><option>全部</option><option>男</option><option>女</option></select>
            </label>
            <div class="field"><span>生年</span>
              <div class="two"><input v-model="f.birth_from" type="number" placeholder="≥" /><input v-model="f.birth_to" type="number" placeholder="≤" /></div>
            </div>
            <div class="field"><span>卒年</span>
              <div class="two"><input v-model="f.death_from" type="number" placeholder="≥" /><input v-model="f.death_to" type="number" placeholder="≤" /></div>
            </div>
            <div class="field"><span>指数年</span>
              <div class="two"><input v-model="f.index_from" type="number" placeholder="≥" /><input v-model="f.index_to" type="number" placeholder="≤" /></div>
            </div>
            <div class="checks">
              <label><input type="checkbox" v-model="f.jinshi_only" /> 仅进士</label>
              <label><input type="checkbox" v-model="f.official_only" /> 仅官员</label>
              <label><input type="checkbox" v-model="f.match_alt" /> 含别名匹配</label>
              <label><input type="checkbox" v-model="f.include_neighbors" /> 含邻域人物</label>
            </div>
            <div class="field"><span>排序</span>
              <div class="two">
                <select v-model="f.order_by">
                  <option v-for="o in ORDER_OPTIONS" :key="o.k" :value="o.k">{{ o.name }}</option>
                </select>
                <button class="mini" @click="f.desc = !f.desc">{{ f.desc ? '降序' : '升序' }}</button>
              </div>
            </div>
            <label class="field"><span>上限</span><input v-model="f.limit" type="number" min="1" max="2000" /></label>
            <div class="hint muted">
              数据来自源库 BIOG_MAIN。姓名自动兼容简繁体；0 命中会自动尝试别名/字号（如「王阳明」→「阳明」命中王守仁）。
            </div>
          </div>
        </aside>
      </div>

      <div v-if="err" class="err">⚠ {{ err }}</div>
      <div v-if="result && result.note" class="note">
        ⓘ 原名 0 命中，已自动改用 <b>{{ result.used_name }}</b> 匹配（别名/字号回退）。
      </div>
      <div v-if="result && result.total === 0" class="hint0">
        ⚠️ 0 命中排查：① 当前朝代是 <b>{{ result.dyn_name }}</b>，此人可能不在该朝（换朝代试试）；
        ② 已自动转简繁并尝试别名/字号，仍无则库里确实没有；③ 试只输一个字；④ 勾选「含邻域人物」。
      </div>

      <div v-if="result" class="panel grid-wrap">
        <DataTable :columns="result.headers" :rows="result.rows" max-height="calc(100vh - 250px)"
          selectable :row-key="0" :selected-key="selId" @row-click="onRow" />
      </div>
      <div v-else-if="!err" class="panel empty-panel muted">正在检索…</div>
      <div class="tip muted">💡 点任意一行 → 在「详情」页看该人完整档案</div>
    </section>

    <!-- ============ 详情 ============ -->
    <section v-show="tab === 'detail'" class="tab-body">
      <div v-if="personLoading" class="panel empty-panel muted">载入中…</div>
      <div v-else-if="personErr" class="err">⚠ {{ personErr }}</div>
      <div v-else-if="!person" class="panel empty-panel muted">
        请先在「检索」页点选一位人物。
      </div>
      <div v-else class="detail-body">
        <div v-if="person.note" class="note">ⓘ {{ person.note }}</div>
        <div class="panel basic">
          <div class="sec-title">
            {{ person.basic.nameChn || '（无名）' }}
            <span class="pid">person/{{ person.personid }}</span>
          </div>
          <div class="dl">
            <template v-for="(v, k) in person.basic" :key="k">
              <template v-if="k !== 'personid'">
                <span class="k">{{ BASIC_LABELS[k] || k }}</span>
                <span class="v">{{ k === 'isFemale' ? femaleText(v) : (v == null || v === '' ? '—' : v) }}</span>
              </template>
            </template>
          </div>
          <div class="chips" v-if="person.alts.length">
            <span class="muted">别名：</span>
            <span class="chip-sm" v-for="a in person.alts" :key="a">{{ a }}</span>
          </div>
          <div class="labels" v-if="person.labels.length">
            <span class="muted">推理标签：</span>{{ person.labels.join('；') }}
          </div>
        </div>

        <div class="panel sec" v-for="(sec, key) in person.sections" :key="key">
          <div class="sec-title">{{ key }}（{{ sec.rows.length }} 条）</div>
          <DataTable :columns="sec.headers" :rows="sec.rows" max-height="320px" />
        </div>
      </div>
    </section>

    <!-- ============ 专题 ============ -->
    <section v-show="tab === 'topics'" class="tab-body">
      <div class="panel fbar">
        <select v-model="topicQuad" class="dy" title="知识图谱">
          <option v-for="q in quads" :key="q.path" :value="q.path">{{ q.label }}</option>
        </select>
        <select v-model="topicKey" @change="onTopicChange" class="dy" title="专题">
          <option v-for="t in topics" :key="t.key" :value="t.key">{{ t.tab }}</option>
        </select>
        <button class="primary go" @click="runTopic" :disabled="topicLoading">
          {{ topicLoading ? '运行中' : (currentTopic ? currentTopic.btn : '运行') }}
        </button>
      </div>
      <div v-if="currentTopic" class="hint muted">{{ currentTopic.hint }}</div>

      <div class="panel tform" v-if="currentTopic">
        <div class="field" v-for="(fld, i) in currentTopic.fields" :key="i">
          <span>{{ fld.label }}</span>
          <input v-if="fld.kind === 'number'" type="number" v-model="topicVals[i]" :placeholder="fld.placeholder" />
          <input v-else-if="fld.kind === 'text'" type="text" v-model="topicVals[i]" :placeholder="fld.placeholder" />
          <select v-else-if="fld.kind === 'dropdown'" v-model="topicVals[i]">
            <option v-for="c in fld.choices" :key="c" :value="c">{{ c }}</option>
          </select>
          <label v-else-if="fld.kind === 'checkbox'" class="cb">
            <input type="checkbox" v-model="topicVals[i]" /> {{ fld.label }}
          </label>
          <span v-else-if="fld.kind === 'radio'" class="radio">
            <label v-for="c in fld.choices" :key="c">
              <input type="radio" :name="'tf' + i" :value="c" v-model="topicVals[i]" /> {{ c }}
            </label>
          </span>
        </div>
      </div>

      <div v-if="topicErr" class="err">⚠ {{ topicErr }}</div>
      <div v-if="topicResult" class="topic-res">
        <pre class="md" v-if="topicResult.md">{{ topicResult.md }}</pre>
        <KgGraph v-if="graphData" :nodes="graphData.nodes" :edges="graphData.edges"
          @select="onGraphSelect" />
        <div v-if="graphData" class="hint muted">💡 点击图中节点 → 跳到「详情」页看该人档案（颜色=度/朝代，拖拽可整理布局）</div>
        <div class="panel sec" v-for="sh in topicResult.sheets" :key="sh.name">
          <div class="sec-title">{{ sh.name }}（{{ sh.rows.length }} 条）</div>
          <DataTable :columns="sh.headers" :rows="sh.rows" max-height="360px" />
        </div>
      </div>
    </section>

    <!-- ============ 导出 ============ -->
    <section v-show="tab === 'export'" class="tab-body">
      <div class="panel exp">
        <div class="sec-title">导出当前检索结果</div>
        <div class="cond muted">
          朝代：<b>{{ (dynasties.find(d => d.dy === f.dy) || {}).label || f.dy }}</b>　|
          姓名含「<b>{{ f.name || '（不限）' }}</b>」　|
          上限 <b>{{ f.limit }}</b>
        </div>
        <div class="hint muted">
          导出的是「检索」页当前条件命中的全部人物（与屏幕显示无关，不受分页/列筛选影响）。
        </div>
        <button class="primary" @click="doExport">⬇ 下载 CSV</button>
        <span v-if="exportState" class="estate">{{ exportState }}</span>
      </div>
    </section>

    <!-- ============ 构建（ETL） ============ -->
    <section v-show="tab === 'build'" class="tab-body">
      <div class="panel exp">
        <div class="sec-title">生成知识图谱（ETL）</div>
        <div class="field-row">
          <label class="field"><span>朝代</span>
            <select v-model="buildDy">
              <option v-for="d in dynasties" :key="d.dy" :value="d.dy">{{ d.label }}</option>
            </select>
          </label>
          <label class="field"><span>人数上限（0=全量）</span>
            <input v-model="buildLimit" type="number" min="0" placeholder="0" />
          </label>
          <button class="primary" @click="runBuild" :disabled="buildRunning">
            {{ buildRunning ? '构建中…' : '⚙ 开始构建' }}
          </button>
        </div>
        <div class="hint muted">
          运行 <code>etl_seed_ming.py</code>：取该朝代核心人物 + 1 度邻域（亲属/交遊对端），
          生成 quadstore（RDF 三元组）供专题查询使用。全量可能耗时数分钟，日志实时滚动。
        </div>
        <div v-if="buildDone" class="note">✅ 构建流程结束，已刷新上方「专题」页的图谱清单。</div>
      </div>
      <pre class="build-log" v-if="buildLog">{{ buildLog }}</pre>
    </section>
  </div>
</template>

<style scoped>
.kg-app { display: flex; flex-direction: column; gap: 8px; flex: 1 1 auto; min-height: 0; }

/* ---------------- 内部 Tab 条 ---------------- */
.tabs { display: flex; gap: 4px; flex: 0 0 auto; }
.tabs button {
  padding: 6px 14px; font-size: 13px; border: 1px solid var(--border);
  background: #fff; border-radius: 6px 6px 0 0; cursor: pointer; color: var(--muted);
}
.tabs button.on { background: var(--accent-soft); border-color: #b9d0ff; color: var(--accent); font-weight: 600; }
.tabs button .pid { font-size: 11px; margin-left: 3px; }

.tab-body { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 10px; overflow-y: auto; }

/* ---------------- 顶部工具栏（一行） ---------------- */
.fbar {
  position: relative; display: flex; align-items: center; gap: 8px; flex-wrap: nowrap;
  padding: 6px 10px; flex: 0 0 auto;
}
.fbar .dy { flex: 0 0 auto; font-size: 13px; max-width: 320px; }
.fbar .go { flex: 0 0 auto; }
.fbar .chip { flex: 0 0 auto; padding: 4px 10px; font-size: 12px; border-radius: 6px; }
.fbar .chip.on { background: var(--accent-soft); border-color: #b9d0ff; color: var(--accent); }
.fbar .chip i { font-style: normal; margin-left: 3px; }
.fb-right { display: flex; align-items: center; gap: 5px; flex: 0 0 auto; margin-left: auto; }
.fb-right .cnt { font-size: 12px; white-space: nowrap; }

/* ---------------- 抽屉 ---------------- */
.d-mask { position: fixed; inset: 0; z-index: 40; background: rgba(15, 20, 28, 0.28); }
.drawer {
  position: absolute; top: 0; right: 0; bottom: 0; width: 360px; max-width: 92vw;
  background: #fff; border-left: 1px solid var(--border); display: flex; flex-direction: column;
  box-shadow: -8px 0 28px rgba(16, 24, 40, 0.12);
}
.d-head { display: flex; align-items: center; gap: 7px; padding: 10px 12px; border-bottom: 1px solid var(--border); font-size: 13px; }
.d-head .sp { flex: 1 1 auto; }
.d-head .primary { padding: 4px 12px; font-size: 12px; }
.d-head .mini { padding: 2px 8px; font-size: 13px; }
.d-body { flex: 1 1 auto; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 10px; }
.d-body .field { display: flex; flex-direction: column; gap: 3px; font-size: 12px; color: var(--muted); }
.d-body .field > span { font-size: 12px; }
.d-body .two { display: flex; gap: 6px; }
.d-body .two > * { flex: 1 1 0; }
.d-body .checks { display: flex; flex-direction: column; gap: 4px; font-size: 12px; }
.d-body .checks label { display: flex; align-items: center; gap: 5px; cursor: pointer; }
.d-body .checks input { width: auto; }
.d-body .mini { padding: 4px 10px; font-size: 12px; white-space: nowrap; }
.d-body .hint { font-size: 11px; line-height: 1.5; border-top: 1px solid var(--border); padding-top: 8px; }

/* ---------------- 提示条 ---------------- */
.err { background: #fdecec; border: 1px solid #f5c2c2; color: #a33; padding: 8px 12px; border-radius: 6px; font-size: 13px; }
.note { background: #eef5ff; border: 1px solid #cfe0ff; color: #2b5fb0; padding: 7px 12px; border-radius: 6px; font-size: 13px; }
.hint0 { background: #fff6e6; border: 1px solid #ffe2b0; color: #9a6b00; padding: 7px 12px; border-radius: 6px; font-size: 13px; line-height: 1.5; }
.empty-panel { padding: 60px; text-align: center; }
.tip { font-size: 12px; }

.grid-wrap { padding: 0; }

/* ---------------- 详情 ---------------- */
.detail-body { display: flex; flex-direction: column; gap: 10px; }
.basic { padding: 12px 14px; }
.sec-title { font-size: 13px; font-weight: 600; margin: 2px 0 8px; }
.sec-title .pid { font-size: 11px; color: var(--muted); margin-left: 6px; font-weight: 400; }
.dl { display: grid; grid-template-columns: max-content 1fr; gap: 4px 16px; font-size: 13px; }
.dl .k { color: var(--muted); }
.dl .v { font-weight: 500; }
.chips { margin-top: 8px; font-size: 13px; display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.chip-sm { background: var(--accent-soft); border: 1px solid #cfe0ff; border-radius: 10px; padding: 1px 8px; font-size: 12px; }
.labels { margin-top: 6px; font-size: 12px; color: var(--muted); }
.sec { padding: 10px 14px; }

/* ---------------- 专题 ---------------- */
.tform { padding: 12px 14px; display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; }
.tform .field { display: flex; flex-direction: column; gap: 3px; font-size: 12px; color: var(--muted); min-width: 160px; }
.tform .field > span { font-size: 12px; }
.tform .radio { display: flex; gap: 10px; align-items: center; }
.tform .radio label { display: flex; align-items: center; gap: 3px; font-size: 12px; color: var(--text); }
.tform .cb { flex-direction: row !important; align-items: center; gap: 5px; color: var(--text) !important; font-size: 13px !important; }
.topic-res { display: flex; flex-direction: column; gap: 10px; }
.md { white-space: pre-wrap; word-break: break-word; font-family: inherit; font-size: 13px; background: #f7f9fc; border: 1px solid var(--border); border-radius: 6px; padding: 10px 12px; margin: 0; }

/* ---------------- 导出 ---------------- */
.exp { padding: 14px; display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
.exp .cond { font-size: 13px; }
.estate { font-size: 13px; color: var(--accent); }

/* ---------------- 构建 ---------------- */
.exp .field-row { display: flex; gap: 14px; align-items: flex-end; flex-wrap: wrap; }
.exp .field { display: flex; flex-direction: column; gap: 3px; font-size: 12px; color: var(--muted); }
.exp .field > span { font-size: 12px; }
.exp code { background: #eef2f7; padding: 1px 5px; border-radius: 4px; font-size: 12px; }
.build-log { white-space: pre-wrap; word-break: break-word; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; background: #0f1722; color: #d6e2f0; border-radius: 8px; padding: 12px 14px; max-height: 60vh; overflow: auto; margin: 0; }
</style>
