<script setup>
// 复用的搜索框：与「视图检索」工具栏的 .gsearch 同款样式（⌕ 图标 + 输入框 + × 清除）。
//
// 用法：
//   <SearchBox v-model="q" placeholder="搜索…" :debounce="300" @search="run" />
// - v-model：绑定输入文本
// - debounce>0：输入停止后延迟触发一次 search（适合实时联想 / 过滤）
// - 回车：立即触发 search
// - × 清除：清空并触发一次 search("")
import { ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: '搜索…' },
  debounce: { type: Number, default: 0 },
  width: { type: String, default: '230px' },
  autofocus: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'search'])

const inner = ref(props.modelValue)
watch(
  () => props.modelValue,
  (v) => {
    if (v !== inner.value) inner.value = v || ''
  }
)

let timer = null
function onInput(e) {
  inner.value = e.target.value
  emit('update:modelValue', inner.value)
  if (props.debounce > 0) {
    clearTimeout(timer)
    timer = setTimeout(() => emit('search', inner.value), props.debounce)
  }
}
function onEnter() {
  if (props.debounce > 0) clearTimeout(timer)
  emit('search', inner.value)
}
function clear() {
  inner.value = ''
  emit('update:modelValue', '')
  emit('search', '')
}
</script>

<template>
  <div class="gsearch" :style="{ flex: '0 0 ' + width, width }">
    <span class="mag">⌕</span>
    <input
      ref="inp"
      :value="inner"
      :placeholder="placeholder"
      autocomplete="off"
      @input="onInput"
      @keyup.enter="onEnter"
    />
    <button v-if="inner" class="gnone" title="清除" @click="clear">×</button>
  </div>
</template>

<style scoped>
.gsearch {
  position: relative;
  display: flex;
  align-items: center;
  flex: 0 0 230px;
}
.gsearch .mag {
  position: absolute;
  left: 8px;
  color: var(--muted);
  font-size: 15px;
  pointer-events: none;
}
.gsearch input {
  width: 100%;
  padding-left: 25px;
  padding-right: 24px;
  font-size: 13px;
}
.gsearch .gnone {
  position: absolute;
  right: 3px;
  border: 0;
  background: transparent;
  color: var(--muted);
  padding: 2px 6px;
  cursor: pointer;
}
.gsearch .gnone:hover {
  color: var(--text);
}
</style>
