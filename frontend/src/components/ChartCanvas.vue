<script setup>
import { Chart } from 'chart.js/auto'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  type: { type: String, default: 'bar' },
  labels: { type: Array, default: () => [] },
  datasets: { type: Array, default: () => [] },
  options: { type: Object, default: () => ({}) },
})

const wrap = ref(null)
const canvas = ref(null)
let chart = null
let observer = null

/** Chart.js legt die Legende INNERHALB der Zeichenfläche an. Wird die Kachel
 *  klein gezogen, frisst sie sonst den Rest oder wird abgeschnitten. Deshalb
 *  kompakte Legendenkästchen und Umbruch, und die Zeichenfläche hat per CSS
 *  eine Mindesthöhe. */
const LEGEND_DEFAULTS = {
  labels: { boxWidth: 12, boxHeight: 12, padding: 8, font: { size: 11 } },
}

function mergedOptions() {
  const plugins = props.options.plugins || {}
  const legend = plugins.legend || {}
  return {
    responsive: true,
    // ohne das würde Chart.js ein festes Seitenverhältnis erzwingen und die
    // Höhe der Kachel ignorieren
    maintainAspectRatio: false,
    ...props.options,
    plugins: {
      ...plugins,
      legend: { ...LEGEND_DEFAULTS, ...legend,
                labels: { ...LEGEND_DEFAULTS.labels, ...(legend.labels || {}) } },
    },
  }
}

function render() {
  if (!canvas.value) return
  if (chart) chart.destroy()
  chart = new Chart(canvas.value, {
    type: props.type,
    data: { labels: props.labels, datasets: props.datasets },
    options: mergedOptions(),
  })
}

onMounted(() => {
  render()
  // Kachelgröße ist frei einstellbar – das Diagramm muss mitgehen, auch wenn
  // sich nur der Container ändert und nicht das Fenster
  if (window.ResizeObserver && wrap.value) {
    observer = new ResizeObserver(() => chart && chart.resize())
    observer.observe(wrap.value)
  }
})
watch(() => [props.labels, props.datasets, props.options], render, { deep: true })
onBeforeUnmount(() => {
  if (observer) observer.disconnect()
  if (chart) chart.destroy()
})
</script>

<template>
  <div ref="wrap" class="chart-wrap"><canvas ref="canvas"></canvas></div>
</template>
