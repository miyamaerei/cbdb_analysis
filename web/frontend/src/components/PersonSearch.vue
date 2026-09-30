<script setup>
// 人物定位搜索框：与「视图检索」工具栏同款样式，输入姓名（支持简繁）后联想命中人物，
// 点选即 emit('select', personid)。逻辑等价于原「人物年谱」左侧搜索框 + 结果列表，
// 只是移到了顶部一行，腾出左侧空间让年谱占满宽度。
import { onMounted, ref } from 'vue'
import { api } from '../api'
import SearchBox from './SearchBox.vue'

const props = defineProps({
  initial: { type: String, default: '王安石' },
  autoSelectFirst: { type: Boolean, default: true },
})
const emit = defineEmits(['select'])

const q = ref(props.initial)
const hits = ref([])
const open = ref(false)
const loading = ref(false)
let timer = null
let done = false // 初始自动选中只做一次

async function run(text) {
  const t = (text || '').trim()
  if (!t) {
    hits.value = []
    open.value = false
    return
  }
  loading.value = true
  try {
    const r = await api.search(t, 20)
    hits.value = r || []
    open.value = true
  } catch (e) {
    hits.value = []
  } finally {
    loading.value = false
  }
}

function onInput(v) {
  clearTimeout(timer)
  timer = setTimeout(() => run(v), 300)
}
function onSearch(v) {
  run(v)
}
function pick(p) {
  emit('select', p.c_personid)
  open.value = false
  q.value = p.c_name_chn || p.c_name
}

onMounted(async () => {
  await run(q.value)
  if (props.autoSelectFirst && hits.value.length && !done) {
    done = true
    emit('select', hits.value[0].c_personid)
  }
})
</script>

<template>
  <div class="psearch">
    <SearchBox
      v-model="q"
      placeholder="输入姓名，如 王安石 / 蘇軾 / 朱熹 / 王阳明"
      :debounce="300"
      width="320px"
      @search="onSearch"
      @update:modelValue="onInput"
    />
    <span v-if="loading" class="muted ps-hint">搜索中…</span>
    <span v-else-if="open && hits.length" class="muted ps-hint">{{ hits.length }} 个匹配</span>

    <div v-if="open && hits.length" class="pp-list">
      <div
        v-for="p in hits"
        :key="p.c_personid"
        class="pp-item"
        @click="pick(p)"
      >
        <span class="nm">{{ p.c_name_chn || p.c_name }}</span>
        <span class="muted">
          id={{ p.c_personid }} · {{ p.dynasty || '—' }} · {{ p.events }} 事件
        </span>
      </div>
    </div>
    <div v-else-if="open && !loading && q.trim()" class="pp-list empty muted">
      没有匹配结果
    </div>
  </div>
</template>

<style scoped>
.psearch {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 0 0 auto;
}
.ps-hint {
  font-size: 12px;
  white-space: nowrap;
}
.pp-list {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  z-index: 31;
  width: 340px;
  max-height: 320px;
  overflow: auto;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 6px 24px rgba(16, 24, 40, 0.12);
  padding: 4px;
}
.pp-list.empty {
  padding: 12px;
  text-align: center;
  font-size: 13px;
}
.pp-item {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 5px 8px;
  border-radius: 5px;
  cursor: pointer;
  font-size: 13px;
}
.pp-item:hover {
  background: var(--accent-soft);
}
.pp-item .nm {
  font-weight: 600;
}
.pp-item .muted {
  font-size: 11px;
  white-space: nowrap;
}
</style>
