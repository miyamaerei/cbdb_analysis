<script setup>
import { computed } from 'vue'

const props = defineProps({
  columns: { type: Array, default: () => [] },
  rows: { type: Array, default: () => [] },
  maxHeight: { type: String, default: '420px' },
})

const cols = computed(() =>
  props.columns.length
    ? props.columns
    : props.rows.length
      ? Object.keys(props.rows[0])
      : []
)

function fmt(v) {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') return v.toLocaleString('en-US')
  return String(v)
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
        <tr v-for="(r, i) in rows" :key="i">
          <td class="muted mono">{{ i + 1 }}</td>
          <td v-for="c in cols" :key="c">{{ fmt(r[c]) }}</td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty muted">没有数据</div>
  </div>
</template>

<style scoped>
.wrap { overflow: auto; }
.empty { padding: 24px; text-align: center; }
</style>
