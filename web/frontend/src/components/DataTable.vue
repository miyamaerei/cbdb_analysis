<script setup>
import { computed } from 'vue'

const props = defineProps({
  columns: { type: Array, default: () => [] },
  rows: { type: Array, default: () => [] },
  maxHeight: { type: String, default: '420px' },
  // 行可选：开启后点击行会 emit('row-click', row)，并按 selectedKey 高亮
  selectable: { type: Boolean, default: false },
  // 行键：对象行传列名（如 'personid'）；数组行传数字索引（如 0）
  rowKey: { type: [String, Number], default: '' },
  selectedKey: { type: [String, Number, null], default: null },
})

const emit = defineEmits(['row-click'])

// 兼容两种行形态：
//   * 数组行（如知识图谱检索：rows 是二维数组、columns 给表头）—— 按索引取数
//   * 对象行（如视图检索：rows 是对象数组、columns 给键名）—— 按 key 取数
const isArrayRows = computed(() =>
  props.rows.length > 0 && Array.isArray(props.rows[0])
)

const cols = computed(() => {
  if (props.columns.length) return props.columns
  if (!props.rows.length) return []
  return isArrayRows.value
    ? []
    : Object.keys(props.rows[0])
})

function cellValue(r, i, c) {
  const v = isArrayRows.value ? r[i] : r[c]
  return v
}

function fmt(v) {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') return v.toLocaleString('en-US')
  return String(v)
}

function isSel(r) {
  if (!props.selectable || props.selectedKey == null || props.rowKey === '') return false
  if (isArrayRows.value) {
    // 数组行：rowKey 必须是数字索引
    if (typeof props.rowKey !== 'number') return false
    return r[props.rowKey] === props.selectedKey
  }
  return r[props.rowKey] === props.selectedKey
}

function onRow(r) {
  if (props.selectable) emit('row-click', r)
}
</script>

<template>
  <div class="wrap" :style="{ maxHeight }">
    <table class="grid" v-if="rows.length">
      <thead>
        <tr>
          <th style="width: 44px">#</th>
          <th v-for="c in cols" :key="c">{{ c }}</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(r, i) in rows"
          :key="i"
          :class="{ sel: isSel(r), clickable: selectable }"
          @click="onRow(r)"
        >
          <td class="muted mono">{{ i + 1 }}</td>
          <td v-for="(c, ci) in cols" :key="c">{{ fmt(cellValue(r, ci, c)) }}</td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty muted">没有数据</div>
  </div>
</template>

<style scoped>
.wrap { overflow: auto; }
.empty { padding: 24px; text-align: center; }
tr.clickable { cursor: pointer; }
tr.sel { background: var(--accent-soft); }
tr.sel:hover { background: var(--accent-soft); }
</style>
