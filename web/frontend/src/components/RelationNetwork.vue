<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  graph: { type: Object, default: () => ({ nodes: [], links: [] }) },
  centerId: { type: Number, default: null },
})

const W = 640
const H = 460
const CX = W / 2
const CY = H / 2

const hover = ref(null)

const others = computed(() =>
  props.graph.nodes.filter((n) => n.id !== props.centerId)
)

const pos = computed(() => {
  const list = others.value
  const n = list.length || 1
  const R = Math.min(W, H) / 2 - 70
  // 返回数组而不是对象：v-for 遍历对象时 key 是字符串，跟数字 id 比会对不上
  return list.map((node, i) => {
    const a = (2 * Math.PI * i) / n - Math.PI / 2
    return { id: node.id, x: CX + R * Math.cos(a), y: CY + R * Math.sin(a), node }
  })
})

const posMap = computed(() => {
  const m = new Map()
  for (const p of pos.value) m.set(p.id, p)
  return m
})

const lines = computed(() => {
  const m = posMap.value
  return props.graph.links
    .filter((l) => l.a === props.centerId && m.has(l.b))
    .map((l) => ({ ...l, p: m.get(l.b) }))
})

function edgeType(id) {
  const l = props.graph.links.find((x) => x.a === props.centerId && x.b === id)
  return l ? l.t : 'assoc'
}

const colorOf = (t) => (t === 'kinship' ? '#2f6feb' : '#d9822b')
</script>

<template>
  <div class="net">
    <div class="bar muted">
      共 {{ graph.nodes.length }} 人 / {{ graph.links.length }} 条边
      · <span style="color: #2f6feb">━</span> 亲属
      · <span style="color: #d9822b">━</span> 交游
      <span v-if="graph.nodes.length >= 120">（已截断到 120 人，仅展示与中心直接相连的边）</span>
    </div>

    <svg :viewBox="`0 0 ${W} ${H}`" class="svg">
      <line
        v-for="(l, i) in lines"
        :key="i"
        :x1="CX"
        :y1="CY"
        :x2="l.p.x"
        :y2="l.p.y"
        :stroke="colorOf(l.t)"
        stroke-width="1"
        opacity="0.35"
      />
      <g v-for="p in pos" :key="p.id">
        <circle
          :cx="p.x"
          :cy="p.y"
          r="4"
          fill="#fff"
          :stroke="colorOf(edgeType(p.id))"
          stroke-width="1.6"
          @mouseenter="hover = p.node"
          @mouseleave="hover = null"
        />
        <text
          v-if="others.length <= 45"
          :x="p.x"
          :y="p.y - 8"
          font-size="9"
          text-anchor="middle"
          fill="#6b7280"
        >
          {{ p.node.name }}
        </text>
      </g>
      <circle :cx="CX" :cy="CY" r="12" fill="var(--accent)" />
      <text :x="CX" :y="CY + 26" font-size="12" text-anchor="middle" fill="#1f2328">
        {{ graph.nodes.find((n) => n.id === centerId)?.name || centerId }}
      </text>
    </svg>

    <div v-if="hover" class="tip mono">
      {{ hover.name }} · id={{ hover.id }} · index_year={{ hover.iy }}
    </div>
  </div>
</template>

<style scoped>
.net { position: relative; }
.bar { padding: 6px 0 2px; font-size: 12px; }
.svg { width: 100%; height: auto; background: #fcfdfe; border: 1px solid var(--border); border-radius: 6px; }
.tip {
  position: absolute;
  left: 8px;
  bottom: 8px;
  background: #1f2328;
  color: #fff;
  padding: 4px 10px;
  border-radius: 5px;
  font-size: 12px;
}
</style>
