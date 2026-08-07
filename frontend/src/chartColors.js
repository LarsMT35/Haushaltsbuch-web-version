/**
 * Diagrammfarben aus dem aktiven Farbschema lesen (4.10).
 *
 * Vorher standen die Farben als feste Hex-Werte in den Kacheln. Damit blieben
 * die Diagramme blau-türkis, während die ganze übrige Seite auf „Beere“ oder
 * „Kontrastreich“ umschaltete – und im Dark Mode lagen dunkle Töne auf
 * dunklem Grund.
 *
 * Chart.js kann `var(--c1)` nicht auflösen (es zeichnet auf ein Canvas, nicht
 * ins DOM), deshalb werden die Werte hier einmal ausgelesen und bei jedem
 * Themenwechsel neu geholt.
 *
 * Die Ampelfarben stehen bewusst NICHT hier: sie sind schema-unabhängig fest.
 */
import { ref } from 'vue'

const KEYS = ['--c1', '--c2', '--c3', '--c4', '--c5', '--c6',
              '--c7', '--c8', '--c9', '--c10', '--c11', '--c12']
const ROLES = { income: '--c-income', expense: '--c-expense',
                neutral: '--c-neutral', strong: '--c-strong' }
const FALLBACK = '#2563eb'

function read(name) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || FALLBACK
}

/** Farbwerte des aktuellen Schemas. `palette` ist die Reihenfolge für
 *  gleichrangige Serien, `role` steht für feste Bedeutungen. */
export const palette = ref(KEYS.map(() => FALLBACK))
export const role = ref({ income: FALLBACK, expense: FALLBACK,
                          neutral: FALLBACK, strong: FALLBACK })

export function refreshChartColors() {
  palette.value = KEYS.map(read)
  role.value = Object.fromEntries(Object.entries(ROLES).map(([k, v]) => [k, read(v)]))
}

/** Halbtransparente Variante – für Flächen unter Linien. */
export function fade(color, alpha = 0.15) {
  const hex = (color || '').replace('#', '')
  if (hex.length !== 6) return color
  const [r, g, b] = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16))
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}
