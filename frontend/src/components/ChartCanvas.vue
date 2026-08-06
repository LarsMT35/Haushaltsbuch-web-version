<script setup>
import { Chart } from 'chart.js/auto'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  type: { type: String, default: 'bar' },
  labels: { type: Array, default: () => [] },
  datasets: { type: Array, default: () => [] },
  options: { type: Object, default: () => ({}) },
  // Nur wo der Aufrufer auch etwas mit dem Klick anfängt: sonst würde der
  // Zeiger Interaktivität versprechen, die es nicht gibt.
  clickable: { type: Boolean, default: false },
})
const emit = defineEmits(['pick'])

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

/** Klick auf ein Segment/einen Balken meldet, WELCHER Datenpunkt getroffen
 *  wurde – die Bedeutung (Kategorie? Monat?) kennt nur der Aufrufer. */
function clickHandlers() {
  if (!props.clickable) return {}
  return {
    // Liniendiagramme zeichnen wir ohne sichtbare Punkte – ohne 'nearest'
    // müsste man exakt den unsichtbaren Datenpunkt treffen. 'nearest' liefert
    // GENAU EIN Element, also auch die richtige Linie (datasetIndex).
    // Balken behalten intersect: true, sonst führt schon ein Klick neben den
    // Balken in eine Liste, die mit dem Angeklickten nichts zu tun hat.
    ...(props.type === 'line' ? { interaction: { mode: 'nearest', intersect: false } } : {}),
    onClick: (evt, elements) => {
      if (!elements.length) return
      const { index, datasetIndex } = elements[0]
      emit('pick', {
        index,
        datasetIndex,
        label: props.labels[index],
        datasetLabel: props.datasets[datasetIndex]?.label,
      })
    },
    onHover: (evt, elements) => {
      const el = evt.native?.target
      if (el) el.style.cursor = elements.length ? 'pointer' : 'default'
    },
  }
}

function mergedOptions() {
  const plugins = props.options.plugins || {}
  const legend = plugins.legend || {}
  return {
    responsive: true,
    // ohne das würde Chart.js ein festes Seitenverhältnis erzwingen und die
    // Höhe der Kachel ignorieren
    maintainAspectRatio: false,
    ...clickHandlers(),
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
