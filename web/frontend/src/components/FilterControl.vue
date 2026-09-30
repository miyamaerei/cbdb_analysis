<script setup>
// 单个可筛列的条件控件。工具栏快捷条件的浮层与右侧抽屉共用同一份实现。
// 自身不保存状态，全部通过事件交回父组件（ViewExplorer 持有 filters）。
//
// 列名显示：主显中文名（col.label），原始列名（col.name）在抽屉里以小号等宽字跟随，
// 浮层（compact）里只留中文名、原始名放 title —— 避免条件一多就满屏 c_xx。
import { ref } from 'vue'

const props = defineProps({
  // {name, label, kind, min, max, distinct, values:[{v,c}]}
  col: { type: Object, required: true },
  filter: { type: Object, default: null },   // {op, val, val2} | null
  compact: { type: Boolean, default: false }, // 浮层里用紧凑样式
})
const emit = defineEmits(['patch', 'toggle-cat', 'clear'])

const expanded = ref(false)

const KIND_BADGE = {
  pid: ['人物id', '#2f6feb'],
  year: ['年', '#1f9d55'],
  num: ['数值', '#6b7280'],
  cat: ['枚举', '#d9822b'],
  text: ['文本', '#8b5cf6'],
}

function isOn(v) {
  const f = props.filter
  return !!f && f.op === 'in' && Array.isArray(f.val) && f.val.includes(v)
}
function num(e) {
  const s = e.target.value
  return s === '' ? '' : +s
}
</script>

<template>
  <div class="fc" :class="{ compact }">
    <div class="fc-head" :title="col.label ? `${col.label}（${col.name}）` : col.name">
      <span class="fc-name">{{ col.label || col.name }}</span>
      <code v-if="!compact && col.label" class="fc-raw mono">{{ col.name }}</code>
      <span class="badge" :style="{ background: KIND_BADGE[col.kind]?.[1] }">
        {{ KIND_BADGE[col.kind]?.[0] || col.kind }}
      </span>
      <span class="fc-stat muted" v-if="col.distinct">取值 {{ col.distinct.toLocaleString() }} 种</span>
      <button v-if="filter" class="fc-clr" title="清除该条件" @click="emit('clear')">×</button>
    </div>

    <!-- 人物 id -->
    <div v-if="col.kind === 'pid'" class="fc-ctl">
      <input
        type="number"
        placeholder="精确匹配"
        :value="filter?.val ?? ''"
        @input="emit('patch', { op: 'eq', val: num($event) })"
      />
    </div>

    <!-- 年 / 数值：区间 -->
    <div v-else-if="col.kind === 'year' || col.kind === 'num'" class="fc-ctl range">
      <input
        type="number"
        :placeholder="col.min"
        :value="filter?.val ?? ''"
        @input="emit('patch', { op: 'between', val: num($event) })"
      />
      <span>~</span>
      <input
        type="number"
        :placeholder="col.max"
        :value="filter?.val2 ?? ''"
        @input="emit('patch', { op: 'between', val2: num($event) })"
      />
    </div>

    <!-- 枚举：多选 chips -->
    <div v-else-if="col.kind === 'cat'" class="fc-ctl">
      <div class="cat-chips">
        <span
          v-for="v in (expanded ? col.values : col.values.slice(0, compact ? 8 : 10))"
          :key="v.v"
          class="tag pick"
          :class="{ on: isOn(v.v) }"
          :title="`样本内 ${v.c} 条`"
          @click="emit('toggle-cat', v.v)"
        >{{ v.v }}<i>{{ v.c }}</i></span>
      </div>
      <button
        v-if="col.values.length > (compact ? 8 : 10)"
        class="chip more"
        @click="expanded = !expanded"
      >{{ expanded ? '收起' : `展开全部 ${col.distinct} 项` }}</button>
    </div>

    <!-- 文本：包含 / 等于 / 开头是 -->
    <div v-else class="fc-ctl">
      <div class="op-row">
        <select
          class="op"
          :value="filter?.op || 'contains'"
          @change="emit('patch', { op: $event.target.value })"
        >
          <option value="contains">包含</option>
          <option value="eq">等于</option>
          <option value="startswith">开头是</option>
        </select>
        <input
          placeholder="关键词"
          :value="filter?.val ?? ''"
          @input="emit('patch', { val: $event.target.value })"
        />
      </div>
    </div>

    <!-- 空值条件（所有类型通用） -->
    <div class="null-row">
      <label>
        <input
          type="checkbox"
          :checked="filter?.op === 'notnull'"
          @change="$event.target.checked ? emit('patch', { op: 'notnull', val: '' }) : (filter?.op === 'notnull' && emit('clear'))"
        />
        仅非空
      </label>
      <label>
        <input
          type="checkbox"
          :checked="filter?.op === 'isnull'"
          @change="$event.target.checked ? emit('patch', { op: 'isnull', val: '' }) : (filter?.op === 'isnull' && emit('clear'))"
        />
        仅为空
      </label>
    </div>
  </div>
</template>

<style scoped>
.fc { padding: 7px 9px; border: 1px solid var(--border); border-radius: 6px; background: #fcfdfe; }
.fc.compact { border: 0; padding: 0; background: transparent; }

.fc-head { display: flex; align-items: center; gap: 5px; margin-bottom: 5px; font-size: 12px; min-width: 0; }
.fc-name { font-weight: 600; white-space: nowrap; }
.fc-raw {
  font-size: 10px; font-weight: 400; color: var(--muted);
  background: #f1f3f6; border-radius: 3px; padding: 0 4px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 150px;
}
.badge { color: #fff; font-size: 10px; padding: 0 5px; border-radius: 3px; font-weight: 400; flex: 0 0 auto; }
.fc-stat { font-size: 11px; opacity: 0.75; }
.fc-clr {
  margin-left: auto; padding: 0 6px; line-height: 16px; font-size: 13px;
  border-radius: 4px; color: var(--muted);
}
.fc-clr:hover { color: #a33; border-color: #f0c4c4; }

.fc-ctl input { font-size: 12px; padding: 3px 7px; }
.range { display: flex; align-items: center; gap: 4px; }
.range span { color: var(--muted); }

.op-row { display: flex; gap: 4px; }
.op-row .op { width: 78px; flex: 0 0 auto; font-size: 11px; padding: 3px 4px; }

.null-row {
  display: flex; align-items: center; gap: 10px;
  margin-top: 4px; font-size: 11px; color: var(--muted);
}
.null-row label { display: flex; align-items: center; gap: 3px; cursor: pointer; }
.null-row input { width: auto; }

.cat-chips { display: flex; flex-wrap: wrap; gap: 3px; max-height: 132px; overflow: auto; }
.tag.pick { cursor: pointer; }
.tag.pick:hover { border-color: var(--accent); }
.tag.pick.on { background: var(--accent-soft); border-color: #b9d0ff; color: var(--accent); }
.tag.pick i { font-style: normal; opacity: 0.5; margin-left: 3px; font-size: 10px; }
.chip.more { margin-top: 4px; font-size: 11px; padding: 2px 8px; }
</style>
