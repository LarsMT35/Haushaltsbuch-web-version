<script setup>
import { Chart } from 'chart.js/auto'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  type: { type: String, default: 'bar' },
  labels: { type: Array, default: () => [] },
  datasets: { type: Array, default: () => [] },
  options: { type: Object, default: () => ({}) },
})

const canvas = ref(null)
let chart = null

function render() {
  if (!canvas.value) return
  if (chart) chart.destroy()
  chart = new Chart(canvas.value, {
    type: props.type,
    data: { labels: props.labels, datasets: props.datasets },
    options: { responsive: true, maintainAspectRatio: false, ...props.options },
  })
}

onMounted(render)
watch(() => [props.labels, props.datasets], render, { deep: true })
onBeforeUnmount(() => chart && chart.destroy())
</script>

<template>
  <div style="position: relative; height: 220px"><canvas ref="canvas"></canvas></div>
</template>
