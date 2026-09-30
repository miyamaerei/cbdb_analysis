<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  rows: { type: Array, default: () => [] },
  birth: { type: Number, default: null },
  death: { type: Number, default: null },
})

const hideFrame = ref(true)      // 默认隐藏「只剩人生框架」的超宽区间
const groupByStage = ref(false)
const ROW_H = 22

const PREC_COLOR = {
  exact: 'var(--p-exact)',
  propagated: 'var(--p-propagated)',
  interval: 'var(--p-interval)',
  frame: 'var(--p-frame)',
}
const PREC_LABEL = {
  exact: '精确',
  propagated: '推理收窄',
  interval: '区间',
  frame: '仅人生框架',
}

const FRAME_WIDTH = 500

const visible = computed(() => {
  let r = props.rows
  if (hideFrame.value) r = r.filter((x) => x.width <= FRAME_WIDTH)
  return r
})

// 时间轴范围
const span = computed(() => {
  const rs = visible.value
  if (!rs.length) return { lo: 0, hi: 1 }
  let lo = Math.min(...rs.map((r) => r.lo))
  let hi = Math.max(...rs.map((r) => r.hi))
  if (props.birth > 0) lo = Math.min(lo, props.birth)
  if (props.death > 0) hi = Math.max(hi, props.death)
  if (hi - lo < 10) hi = lo + 10
  const pad = Math.max(2, Math.round((hi - lo) * 0.02))
  return { lo: lo - pad, hi: hi + pad }
})

const total = computed(() => span.value.hi - span.value.lo)

function pct(y) {
  return ((y - span.value.lo) / total.value) * 100
}

// 刻度
const ticks = computed(() => {
  const { lo, hi } = span.value
  const n = hi - lo
  const step = n > 800 ? 200 : n > 400 ? 100 : n > 150 ? 50 : n > 60 ? 20 : 10
  const out = []
  for (let y = Math.ceil(lo / step) * step; y <= hi; y += step) out.push(y)
  return out
})

// 分组（按阶段）
const groups = computed(() => {
  if (!groupByStage.value) return [{ key: '', label: '', rows: visible.value }]
  const m = new Map()
  for (const r of visible.value) {
    const k = r.stage_no
    if (!m.has(k)) m.set(k, { key: k, label: r.stage, rows: [] })
    m.get(k).rows.push(r)
  }
  return [...m.values()].sort((a, b) => a.key - b.key)
})

const hover = ref(null)

function tip(r) {
  return [
    r.event_label,
    `区间 [${r.lo}, ${r.hi}]  宽 ${r.width} 年`,
    r.narrowed > 0 ? `传播收窄 ${r.narrowed} 年（原 [${r.prior_lo}, ${r.prior_hi}]）` : '未被收窄',
    `精度：${PREC_LABEL[r.precision] || r.precision} / 输入 ${r.time_precision}`,
    r.conflict ? '⚠ 约束自相矛盾，已回退' : '',
    r.locked ? '🔒 数据自带确切年份' : '',
  ]
    .filter(Boolean)
    .join('\n')
}
</script>

<template>
  <div class="tl">
    <div class="toolbar">
      <label><input type="checkbox" v-model="hideFrame" /> 隐藏超宽区间（>{{ FRAME_WIDTH }} 年）</label>
      <label><input type="checkbox" v-model="groupByStage" /> 按阶段分组</label>
      <span class="muted">共 {{ visible.length }} / {{ rows.length }} 条</span>
      <span class="legend">
        <i v-for="(c, k) in PREC_COLOR" :key="k" :style="{ background: c }"></i>
        <span class="muted">精确 / 推理 / 区间 / 框架</span>
      </span>
    </div>

    <!-- 年份刻度 -->
    <div class="axis">
      <div class="axis-inner">
        <span v-for="t in ticks" :key="t" class="tick" :style="{ left: pct(t) + '%' }">
          {{ t }}
        </span>
      </div>
    </div>

    <div class="body">
      <div v-for="g in groups" :key="g.key" class="group">
        <div v-if="groupByStage" class="group-title">{{ g.label }} · {{ g.rows.length }}</div>
        <div
          v-for="r in g.rows"
          :key="r.order_rank + '-' + r.event_label"
          class="row"
          :style="{ height: ROW_H + 'px' }"
          @mouseenter="hover = r"
          @mouseleave="hover = null"
        >
          <div class="track">
            <!-- 生卒参考带 -->
            <div
              v-if="birth > 0 && death > 0"
              class="life-band"
              :style="{ left: pct(birth) + '%', width: pct(death) - pct(birth) + '%' }"
            />
            <!-- 先验区间（灰） -->
            <div
              v-if="r.narrowed > 0"
              class="prior"
              :style="{ left: pct(r.prior_lo) + '%', width: Math.max(pct(r.prior_hi) - pct(r.prior_lo), 0.3) + '%' }"
            />
            <!-- 传播后区间 -->
            <div
              class="bar"
              :class="{ conflict: r.conflict, locked: r.locked }"
              :style="{
                left: pct(r.lo) + '%',
                width: Math.max(pct(r.hi) - pct(r.lo), 0.4) + '%',
                background: PREC_COLOR[r.precision] || 'var(--p-frame)',
              }"
            />
            <div
              v-for="t in ticks"
              :key="'g' + t"
              class="grid-line"
              :style="{ left: pct(t) + '%' }"
            />
          </div>
          <div class="label" :title="tip(r)">
            <span class="stage tag">{{ r.stage }}</span>
            <span class="txt">{{ r.event_label }}</span>
          </div>
        </div>
      </div>
      <div v-if="!visible.length" class="empty muted">（当前筛选下没有事件）</div>
    </div>

    <div v-if="hover" class="tooltip">
      <div class="tt-title">{{ hover.event_label }}</div>
      <div class="mono">
        [{{ hover.lo }}, {{ hover.hi }}]　宽 {{ hover.width }} 年
        <span v-if="hover.narrowed > 0">
          ← 收窄 {{ hover.narrowed }}（原 [{{ hover.prior_lo }}, {{ hover.prior_hi }}]）
        </span>
      </div>
      <div class="muted">
        {{ PREC_LABEL[hover.precision] }} · 输入精度 {{ hover.time_precision }}
        <span v-if="hover.locked"> · 🔒 硬年份</span>
        <span v-if="hover.conflict"> · ⚠ 矛盾回退</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tl { position: relative; }

.toolbar {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 8px 0 10px;
  flex-wrap: wrap;
  font-size: 13px;
}
.toolbar label { display: flex; align-items: center; gap: 5px; cursor: pointer; }
.toolbar input[type='checkbox'] { width: auto; }
.legend { display: flex; align-items: center; gap: 4px; margin-left: auto; }
.legend i { width: 14px; height: 8px; border-radius: 2px; display: inline-block; }

.axis { padding-left: 300px; height: 18px; position: relative; }
.axis-inner { position: relative; height: 100%; }
.tick {
  position: absolute;
  transform: translateX(-50%);
  font-size: 11px;
  color: var(--muted);
  font-family: Consolas, monospace;
}

.body { max-height: 520px; overflow-y: auto; }
.group-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
  padding: 8px 0 4px;
  border-bottom: 1px dashed var(--border);
}

.row { display: flex; align-items: center; position: relative; }
.row:hover { background: #f8fafc; }

.label {
  width: 300px;
  flex: 0 0 300px;
  display: flex;
  gap: 6px;
  align-items: baseline;
  padding-right: 12px;
  overflow: hidden;
  white-space: nowrap;
  font-size: 12px;
}
.label .stage { flex: 0 0 auto; font-size: 11px; }
.label .txt { overflow: hidden; text-overflow: ellipsis; }

.track { position: relative; flex: 1 1 auto; height: 100%; }
.grid-line {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 1px;
  background: #eef1f4;
}
.life-band {
  position: absolute;
  top: 0;
  bottom: 0;
  background: rgba(47, 111, 235, 0.07);
  border-left: 1px dashed rgba(47, 111, 235, 0.35);
  border-right: 1px dashed rgba(47, 111, 235, 0.35);
}
.prior {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  height: 12px;
  background: #dfe3e8;
  border-radius: 2px;
}
.bar {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  height: 6px;
  border-radius: 3px;
  min-width: 2px;
}
.bar.locked { height: 8px; box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.12); }
.bar.conflict { outline: 1px solid #d64545; outline-offset: 1px; }

.empty { padding: 24px; text-align: center; }

.tooltip {
  position: absolute;
  right: 0;
  bottom: 0;
  background: #1f2328;
  color: #fff;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 12px;
  max-width: 460px;
  pointer-events: none;
  z-index: 20;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}
.tooltip .tt-title { font-weight: 600; margin-bottom: 2px; }
.tooltip .muted { color: #b9c0c9; }
</style>
