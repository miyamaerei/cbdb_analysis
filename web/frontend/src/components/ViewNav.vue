<script setup>
// 视图导航 —— 用「一行」取代原来占 260px 宽的左侧分组树。
//
// 依据：
//   Canvas Catalog 2025 改版把 tab 导航换成下拉菜单，理由是「层级更清楚、能显示更长的名字、
//   靠面包屑保持方位感」；大目录的成熟做法是「组 tab + 组内下拉 + 一个可搜索的全量面板」。
//   所以这里三件套：9 个组做成横向 tab、当前视图做成下拉、右下角 ⊞ 打开 24 个视图的全量浮层。
import { computed, nextTick, ref } from 'vue'

const props = defineProps({
  meta: { type: Object, required: true },
  activeGroup: { type: String, default: '' },
  activeView: { type: String, default: '' },
})
const emit = defineEmits(['pick'])

const groups = computed(() => props.meta.groups || [])
const vlabels = computed(() => props.meta.view_labels || {})
const group = computed(() => groups.value.find((g) => g.key === props.activeGroup) || null)
const groupViews = computed(() => group.value?.views || [])
const cur = computed(() => props.meta.views?.[props.activeView] || null)

const pop = ref('') // '' | 'group' | 'all'
const q = ref('')
const qRef = ref(null)

function vzh(v) {
  return vlabels.value[v]?.zh || v.replace(/^View_/, '')
}
function fmtRows(n) {
  if (n == null) return '?'
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (n >= 1e4) return Math.round(n / 1e3) + 'k'
  return String(n)
}
function nrows(v) {
  return props.meta.views?.[v]?.rows ?? 0
}
function groupOf(v) {
  return groups.value.find((g) => g.views.includes(v))
}

function pick(v) {
  emit('pick', { group: groupOf(v)?.key || '', view: v })
  pop.value = ''
  q.value = ''
}
// 点组 tab：留在本组就保持当前视图，跳到别的组就换到那组的第一个视图
function pickGroup(g) {
  if (g.key === props.activeGroup) return
  emit('pick', { group: g.key, view: g.views.includes(props.activeView) ? props.activeView : g.views[0] })
  pop.value = ''
}

async function toggle(p) {
  pop.value = pop.value === p ? '' : p
  if (pop.value === 'all') {
    q.value = ''
    await nextTick()
    qRef.value?.focus()
  }
}

// 全量浮层：中文名 / 英文名 / 组名 / 任一列的中文名都能搜
const hits = computed(() => {
  const kw = q.value.trim().toLowerCase()
  if (!kw) return groups.value
  return groups.value
    .map((g) => ({
      ...g,
      views: g.views.filter(
        (v) =>
          v.toLowerCase().includes(kw) ||
          vzh(v).toLowerCase().includes(kw) ||
          g.name.toLowerCase().includes(kw) ||
          Object.values(props.meta.views?.[v]?.labels || {}).some((s) =>
            s.toLowerCase().includes(kw)
          )
      ),
    }))
    .filter((g) => g.views.length)
})
</script>

<template>
  <div class="vnav panel">
    <!-- 9 个分组 tab -->
    <div class="gtabs">
      <button
        v-for="g in groups"
        :key="g.key"
        class="gtab"
        :class="{ on: g.key === activeGroup }"
        :title="g.desc"
        @click="pickGroup(g)"
      >
        {{ g.name }}<i>{{ g.views.length }}</i>
      </button>
    </div>

    <!-- 当前视图 + 全量入口 -->
    <div class="vpick">
      <button class="vbtn" :class="{ on: pop === 'group' }" @click="toggle('group')">
        <b>{{ vzh(activeView) }}</b>
        <span class="raw mono">{{ activeView }}</span>
        <span class="muted sep">·</span>
        <span class="muted">{{ fmtRows(cur?.rows) }} 行 / {{ cur?.columns?.length }} 列</span>
        <span class="muted sep">·</span>
        <span class="muted">可筛 {{ cur?.filters?.length }}</span>
        <span class="car">▾</span>
      </button>
      <button
        class="allbtn"
        :class="{ on: pop === 'all' }"
        title="全部 24 个视图（可按中文名 / 列名搜索）"
        @click="toggle('all')"
      >
        ⊞ 全部
      </button>
    </div>

    <div class="popmask" v-if="pop" @click="pop = ''"></div>

    <!-- 本组视图 -->
    <div class="vpop" v-if="pop === 'group'">
      <div class="ph">
        本组视图 · {{ group?.name }}
        <i>{{ groupViews.length }}</i>
      </div>
      <div class="gdesc muted">{{ group?.desc }}</div>
      <div
        v-for="v in groupViews"
        :key="v"
        class="vrow"
        :class="{ on: v === activeView }"
        @click="pick(v)"
      >
        <span class="vz">{{ vzh(v) }}</span>
        <span class="raw mono">{{ v }}</span>
        <span class="muted vr">{{ fmtRows(nrows(v)) }} 行</span>
      </div>
      <div class="hint muted">
        同组视图共享关联键 —— 结果表里带 🔗 的值点一下，就能带着条件跳到别的视图。
      </div>
    </div>

    <!-- 全部视图 -->
    <div class="vpop all" v-if="pop === 'all'">
      <input
        ref="qRef"
        v-model="q"
        placeholder="搜索视图：中文名 / 英文名 / 列的中文名，如「官职」「籍贯」…"
      />
      <div class="allbody">
        <div v-for="g in hits" :key="g.key" class="allgrp">
          <div class="ph">{{ g.name }} <i>{{ g.views.length }}</i></div>
          <div
            v-for="v in g.views"
            :key="v"
            class="vrow"
            :class="{ on: v === activeView }"
            @click="pick(v)"
          >
            <span class="vz" :title="vlabels[v]?.desc || ''">{{ vzh(v) }}</span>
            <span class="raw mono">{{ v }}</span>
            <span class="muted vr">{{ fmtRows(nrows(v)) }} 行</span>
          </div>
        </div>
        <div v-if="!hits.length" class="muted h-none">没有匹配「{{ q }}」的视图</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 整条导航固定一行，任何情况都不换行：组 tab 横向滚动，右侧视图按钮固定 */
.vnav {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 5px 8px;
  flex: 0 0 auto;
  min-height: 42px;
}

.gtabs {
  display: flex;
  gap: 3px;
  flex: 1 1 auto;
  min-width: 0;
  overflow-x: auto;
  scrollbar-width: thin;
}
.gtabs::-webkit-scrollbar { height: 4px; }
.gtab {
  flex: 0 0 auto;
  padding: 4px 9px;
  font-size: 12.5px;
  border-radius: 6px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--muted);
  white-space: nowrap;
}
.gtab:hover { background: #f2f5fa; color: var(--text); }
.gtab.on {
  background: var(--accent-soft);
  border-color: #cddefb;
  color: var(--accent);
  font-weight: 600;
}
.gtab i {
  font-style: normal;
  font-size: 10px;
  margin-left: 4px;
  opacity: 0.65;
}

.vpick { display: flex; align-items: center; gap: 6px; flex: 0 0 auto; }
.vbtn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  font-size: 12.5px;
  border-radius: 6px;
  background: #fff;
  max-width: 560px;
}
.vbtn b { font-size: 13px; }
.vbtn.on { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
.vbtn .raw, .vrow .raw {
  font-size: 11px;
  color: var(--muted);
  background: #f3f5f8;
  border-radius: 3px;
  padding: 0 5px;
}
.vbtn .sep { font-size: 11px; }
.vbtn .car { opacity: 0.5; font-size: 10px; }
.allbtn { padding: 4px 10px; font-size: 12.5px; }
.allbtn.on { border-color: var(--accent); color: var(--accent); }

/* 浮层 */
.popmask { position: fixed; inset: 0; z-index: 30; }
.vpop {
  position: absolute;
  top: calc(100% + 5px);
  right: 8px;
  z-index: 31;
  width: 460px;
  max-height: 62vh;
  overflow: auto;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 8px 28px rgba(16, 24, 40, 0.14);
  padding: 8px;
}
.vpop.all { width: 620px; }
.ph {
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 6px 2px 4px;
}
.ph i {
  font-style: normal;
  background: #f0f2f5;
  border-radius: 8px;
  padding: 0 6px;
  font-weight: 400;
}
.gdesc { font-size: 11px; padding: 0 2px 6px; border-bottom: 1px solid var(--border); margin-bottom: 4px; }
.vrow {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 6px;
  border-radius: 5px;
  cursor: pointer;
  font-size: 13px;
}
.vrow:hover { background: var(--accent-soft); }
.vrow.on { background: var(--accent-soft); box-shadow: inset 2px 0 0 var(--accent); }
.vrow .vz { flex: 0 1 auto; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.vrow .raw { flex: 0 0 auto; }
.vrow .vr { margin-left: auto; flex: 0 0 auto; font-size: 11px; }
.hint { font-size: 11px; line-height: 1.5; margin-top: 6px; padding-top: 6px; border-top: 1px solid var(--border); }
.allbody { display: flex; flex-direction: column; }
.allgrp + .allgrp { border-top: 1px solid var(--border); margin-top: 4px; padding-top: 4px; }
.h-none { font-size: 12px; padding: 12px 4px; }
input { font-size: 13px; }
</style>
