<script setup>
// 知识图谱力导向图（vis-network）。
//
// 通用组件：父组件把任意「人物网络」归一化成
//   nodes: [{ id, label, group?, title?, degree? }]
//   edges: [{ from, to, label?, arrows?, color? }]
// 即可渲染。点击节点 emit('select', id) 方便父组件联动详情。
//
// 用于：Q3 N 度家族网、Q9 学派主题网（也可复用给 Q4 师承链）。
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Network, DataSet } from 'vis-network/standalone'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  edges: { type: Array, default: () => [] },
  height: { type: String, default: '520px' },
})
const emit = defineEmits(['select'])

const el = ref(null)
let net = null
let dNodes = null
let dEdges = null

// 关系/分组调色板（节点按 group 上色，边统一灰）
const PALETTE = [
  '#4f8cff', '#ef6c5a', '#46b67c', '#f0a93b', '#9b6cf0', '#36b5c4',
  '#e0689a', '#7d8a99', '#c7b04a', '#5a8fef', '#d2691e', '#6dae3f',
]
function buildGroupColors(groups) {
  const m = {}
  groups.forEach((g, i) => { m[g] = { color: { background: PALETTE[i % PALETTE.length], border: PALETTE[i % PALETTE.length] } } })
  return m
}

function render() {
  if (!el.value) return
  if (net) { net.destroy(); net = null }
  const nodeGroups = [...new Set(props.nodes.map(n => n.group || 'n'))]
  const groups = buildGroupColors(nodeGroups)
  const showEdgeLabels = props.edges.length <= 200
  dNodes = new DataSet(props.nodes.map(n => ({
    id: n.id, label: n.label, group: n.group || 'n',
    title: n.title || n.label, value: n.degree ? n.degree + 1 : 1,
  })))
  dEdges = new DataSet(props.edges.map(e => ({
    from: e.from, to: e.to, label: showEdgeLabels ? e.label || '' : undefined,
    arrows: e.arrows || '', color: e.color || { color: '#ccd6e2', highlight: '#4f8cff' },
    title: e.label || '',
  })))
  net = new Network(el.value, { nodes: dNodes, edges: dEdges }, {
    nodes: { shape: 'dot', size: 11, font: { size: 12, color: '#33415c', face: 'inherit' }, borderWidth: 1, scaling: { min: 8, max: 26 } },
    edges: { smooth: { enabled: true, type: 'dynamic', roundness: 0.5 }, font: { size: 9, color: '#9aa7b8', strokeWidth: 0, align: 'middle' }, width: 1 },
    groups,
    physics: {
      enabled: true,
      stabilization: { enabled: true, iterations: 180, fit: true },
      barnesHut: { gravitationalConstant: -9000, springLength: 95, springConstant: 0.04, damping: 0.45, avoidOverlap: 0.1 },
    },
    interaction: { hover: true, tooltipDelay: 100, zoomView: true, dragView: true, dragNodes: true, multiselect: false },
    layout: { improvedLayout: true },
  })
  net.on('click', (p) => {
    if (p.nodes && p.nodes.length) emit('select', p.nodes[0])
  })
  net.once('stabilizationIterationsDone', () => {
    if (net && props.nodes.length > 250) net.setOptions({ physics: { enabled: false } }) // 大模型稳定后关物理，避免抖动
  })
}

onMounted(render)
watch(() => [props.nodes, props.edges], render, { deep: true })
onBeforeUnmount(() => { if (net) { net.destroy(); net = null } })
</script>

<template>
  <div class="kg-graph-wrap">
    <div ref="el" class="kg-graph" :style="{ height }"></div>
    <div v-if="!nodes.length" class="kg-graph-empty muted">无节点可绘制</div>
  </div>
</template>

<style scoped>
.kg-graph-wrap { position: relative; width: 100%; }
.kg-graph { width: 100%; border: 1px solid var(--border); border-radius: 8px; background: #fbfcfe; }
.kg-graph-empty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: 13px; }
</style>
