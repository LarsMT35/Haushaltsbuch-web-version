<script setup>
import { computed, inject, onMounted, ref, watch } from 'vue'
import { api, fmtAmount, fmtDate } from '../api.js'
import ChartCanvas from '../components/ChartCanvas.vue'

const accounts = inject('accounts')
const summary = ref(null)          // gewählter Zeitraum -> Kennzahlen, Kategorien
const previous = ref(null)         // Vergleichszeitraum davor -> Veränderung in %
const trend = ref(null)            // rollierendes Fenster -> Verlaufs-Kacheln
const networth = ref(null)
const savingsRate = ref(null)
const yearComp = ref(null)
const recurringStatus = ref(null)
const deposits = ref(null)
const categories = ref([])
const budgetStatus = ref(null)
const cumulative = ref(null)
const categoryTrend = ref(null)
const topCounterparties = ref(null)

// ---------------------------------------------------------------- Zeitraum
// Lokale Datumsteile statt toISOString(), sonst verschiebt die UTC-Umrechnung
// das Datum je nach Zeitzone um einen Tag.
function fmtDateLocal(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function lastMonthDates() {
  const now = new Date()
  const end = new Date(now.getFullYear(), now.getMonth(), 0) // Tag 0 = letzter Tag des Vormonats
  return [new Date(end.getFullYear(), end.getMonth(), 1), end]
}
function lastMonthRange() {
  const [start, end] = lastMonthDates()
  return { date_from: fmtDateLocal(start), date_to: fmtDateLocal(end) }
}

// Verlaufs-Kacheln hängen bewusst NICHT am Zeitraumfilter: ein Liniendiagramm
// über einen einzelnen Monat wäre ein einzelner Punkt. Sie zeigen immer ein
// rollierendes Fenster, der gewählte Zeitraum wird darin nur hervorgehoben (4.9).
const TREND_MONTHS = 12
function trendRange() {
  const now = new Date()
  return {
    date_from: fmtDateLocal(new Date(now.getFullYear(), now.getMonth() - (TREND_MONTHS - 1), 1)),
    date_to: fmtDateLocal(now),
  }
}

/** Vergleichszeitraum unmittelbar davor – bei ganzen Monaten/Jahren
 *  kalendarisch, sonst gleich lang direkt davor. */
function previousRange(fromIso, toIso) {
  const f = new Date(fromIso)
  const t = new Date(toIso)
  const lastOfMonth = new Date(t.getFullYear(), t.getMonth() + 1, 0).getDate()
  const sameMonth = f.getFullYear() === t.getFullYear() && f.getMonth() === t.getMonth()
  if (f.getDate() === 1 && t.getDate() === lastOfMonth && sameMonth) {
    return { date_from: fmtDateLocal(new Date(f.getFullYear(), f.getMonth() - 1, 1)),
             date_to: fmtDateLocal(new Date(f.getFullYear(), f.getMonth(), 0)) }
  }
  if (f.getMonth() === 0 && f.getDate() === 1 && t.getMonth() === 11 && t.getDate() === 31) {
    return { date_from: `${f.getFullYear() - 1}-01-01`, date_to: `${f.getFullYear() - 1}-12-31` }
  }
  const days = Math.round((t - f) / 86400000) + 1
  const prevTo = new Date(f); prevTo.setDate(prevTo.getDate() - 1)
  const prevFrom = new Date(prevTo); prevFrom.setDate(prevFrom.getDate() - days + 1)
  return { date_from: fmtDateLocal(prevFrom), date_to: fmtDateLocal(prevTo) }
}

// Abrechnungsmonat (4.9): Grenzen kommen vom Backend, damit die Periodenregel
// nicht ein zweites Mal in JavaScript existiert und auseinanderlaufen kann.
const period = ref(null)

const filter = ref({ account_ids: [], category_ids: [], ...lastMonthRange() })

// Fertige Zeitraum-Quicklinks: ein Klick setzt Start+Ende (4.9)
const activePreset = ref('last_month')
function setRange(from, to, preset) {
  filter.value.date_from = fmtDateLocal(from)
  filter.value.date_to = fmtDateLocal(to)
  activePreset.value = preset
}
const PRESETS = {
  this_month: () => (period.value
    ? [new Date(period.value.current_from), new Date(period.value.current_to)]
    : [new Date(new Date().getFullYear(), new Date().getMonth(), 1), new Date()]),
  last_month: () => (period.value
    ? [new Date(period.value.previous_from), new Date(period.value.previous_to)]
    : lastMonthDates()),
  this_year: () => { const n = new Date(); return [new Date(n.getFullYear(), 0, 1), n] },
  last_year: () => { const y = new Date().getFullYear() - 1; return [new Date(y, 0, 1), new Date(y, 11, 31)] },
  last_12_months: () => { const n = new Date(); return [new Date(n.getFullYear(), n.getMonth() - 11, 1), n] },
}
function applyPreset(key) { const [f, t] = PRESETS[key](); setRange(f, t, key) }
function applyYear(year) {
  if (!year) return
  setRange(new Date(Number(year), 0, 1), new Date(Number(year), 11, 31), `year_${year}`)
}
function onManualDate() { activePreset.value = null }
const availableYears = computed(() => (yearComp.value?.years || []).slice().sort((a, b) => b - a))

// ------------------------------------------------------- Dashboard-Modus
// Gemeinsamer Haushalt und eigenes Geld beantworten unterschiedliche Fragen –
// eine gemeinsame Ausgabensumme aus Miete und privatem Kaffee sagt nichts.
// Wer nur Zugriff auf gemeinsame Konten hat (z.B. der Partner als Leser),
// bekommt gar keinen Umschalter zu sehen (4.1/4.9.1).
const MODES = [
  ['gemeinsam', '🏠 Gemeinsam'],
  ['persoenlich', '👤 Persönlich'],
  ['gesamt', 'Σ Gesamt'],
]
const mode = ref(localStorage.getItem('dashboard_mode') || 'gemeinsam')

const householdAccounts = computed(() => accounts.value.filter((a) => a.is_household))
const privateAccounts = computed(() => accounts.value.filter((a) => !a.is_household))
const availableModes = computed(() => MODES.filter(([key]) => {
  if (key === 'gemeinsam') return householdAccounts.value.length > 0
  if (key === 'persoenlich') return privateAccounts.value.length > 0
  return householdAccounts.value.length > 0 && privateAccounts.value.length > 0
}))
/** Konten des aktiven Modus – der Kontenfilter wirkt nur noch innerhalb davon. */
const modeAccounts = computed(() => {
  if (mode.value === 'gemeinsam') return householdAccounts.value
  if (mode.value === 'persoenlich') return privateAccounts.value
  return accounts.value
})
/** Kontenauswahl für die API: Modus als äußerer Rahmen, Filter als Verfeinerung. */
function scopedAccountIds() {
  const inMode = modeAccounts.value.map((a) => a.id)
  if (!filter.value.account_ids.length) return inMode
  return filter.value.account_ids.filter((id) => inMode.includes(id))
}

function ensureValidMode() {
  if (!accounts.value.length) return
  const keys = availableModes.value.map(([k]) => k)
  if (!keys.includes(mode.value)) mode.value = keys[0] || 'gesamt'
}
async function switchMode(key) {
  if (mode.value === key) return
  mode.value = key
  localStorage.setItem('dashboard_mode', key)
  filter.value.account_ids = []  // Auswahl gilt für den alten Modus nicht mehr
  await loadLayout()
  await load()
}

function accountLabel() {
  const n = filter.value.account_ids.length
  return n ? `Konten (${n})` : 'Alle Konten des Bereichs'
}
function categoryLabel() {
  const n = filter.value.category_ids.length
  return n ? `Kategorien (${n})` : 'Alle Kategorien'
}

// ------------------------------------------------------------ Kachel-Layout
// Kachel-Registry: eine neue Auswertung ist ein neuer Eintrag, kein Layout-Umbau (4.9.1)
const TILES = [
  ['kpis', 'Kennzahlen'], ['unassigned', 'Handlungsbedarf'],
  ['cumulative', 'Monatsverlauf kumuliert'],
  ['budget_progress', 'Budget-Fortschritt'],
  ['fixed_base', 'Fixkosten-Sockel'],
  ['cashflow', 'Einnahmen / Ausgaben im Verlauf'],
  ['by_category', 'Ausgaben nach Kategorie'], ['fixed', 'Fix / Variabel'],
  ['upcoming', 'Fällig in den nächsten 30 Tagen'],
  ['category_trend', 'Kategorie-Trend'],
  ['top_counterparties', 'Top-Empfänger'],
  ['savings', 'Bewegung Sparkonten'],
  ['networth', 'Vermögensverlauf'], ['savings_rate', 'Sparquote'],
  ['year_comparison', 'Jahresvergleich'],
  ['recurring_ampel', 'Wiederkehrende Kosten (Ampel)'],
  ['deposits', 'Einzahlungen gemeinsames Konto'],
]
// Je Modus nur zeigen, was dort auch eine Frage beantwortet – statt überall
// alles. Der Rest ist über „Ausgeblendet: +" jederzeit dazuschaltbar (4.9.1).
const HIDDEN_BY_MODE = {
  gemeinsam: ['networth', 'savings_rate', 'savings', 'year_comparison',
              'category_trend', 'top_counterparties'],
  persoenlich: ['deposits', 'category_trend', 'top_counterparties', 'upcoming'],
  gesamt: ['deposits', 'category_trend', 'top_counterparties'],
}
const layout = ref([])
const dragId = ref(null)

function defaultLayout() {
  const hidden = HIDDEN_BY_MODE[mode.value] || []
  return TILES.map(([id]) => ({ id, visible: !hidden.includes(id) }))
}
function normalizeLayout(stored) {
  // gespeicherte Reihenfolge übernehmen, neue Kacheltypen hinten anfügen
  const known = new Set(TILES.map(([id]) => id))
  const result = (stored || []).filter((t) => known.has(t.id))
  if (!result.length) return defaultLayout()
  const hidden = HIDDEN_BY_MODE[mode.value] || []
  for (const [id] of TILES) {
    if (!result.find((t) => t.id === id)) result.push({ id, visible: !hidden.includes(id) })
  }
  return result
}

const orderOf = (id) => layout.value.findIndex((t) => t.id === id)
const isVisible = (id) => layout.value.find((t) => t.id === id)?.visible !== false
const hiddenTiles = computed(() =>
  layout.value.filter((t) => !t.visible).map((t) => ({ ...t, label: TILES.find(([i]) => i === t.id)?.[1] })))

async function loadLayout() {
  const saved = await api.get('/dashboard/layout', { mode: mode.value })
  layout.value = normalizeLayout(saved.tiles)
}
async function saveLayout() {
  await api.put('/dashboard/layout', { tiles: layout.value }, { mode: mode.value })
}
function hide(id) {
  const t = layout.value.find((t) => t.id === id)
  if (t) { t.visible = false; saveLayout() }
}
async function show(id) {
  const t = layout.value.find((t) => t.id === id)
  if (!t) return
  t.visible = true
  saveLayout()
  await load()   // Daten der eben eingeblendeten Kachel nachladen
}
function onDrop(targetId) {
  if (!dragId.value || dragId.value === targetId) return
  const [moved] = layout.value.splice(orderOf(dragId.value), 1)
  layout.value.splice(orderOf(targetId), 0, moved)
  dragId.value = null
  saveLayout()
}
function tileProps(id) {
  return {
    style: { order: orderOf(id) },
    draggable: true,
    onDragstart: () => { dragId.value = id },
    onDragover: (e) => e.preventDefault(),
    onDrop: () => onDrop(id),
  }
}

// ------------------------------------------------------------------- Laden
// Einzahlungstransparenz braucht ein konkretes gemeinsames Konto (4.9)
const depositAccountId = ref('')

async function loadDeposits() {
  if (!depositAccountId.value || !isVisible('deposits')) { deposits.value = null; return }
  deposits.value = await api.get('/dashboard/deposits',
    { ...trendRange(), account_id: depositAccountId.value })
}

async function load() {
  if (!accounts.value.length) return
  const account_ids = scopedAccountIds()
  if (!account_ids.length) { summary.value = null; return }

  const range = { date_from: filter.value.date_from, date_to: filter.value.date_to }
  const summaryParams = { ...range, account_ids }
  if (filter.value.category_ids.length) summaryParams.category_ids = filter.value.category_ids
  const trendParams = { ...trendRange(), account_ids }
  const month = (range.date_to || fmtDateLocal(new Date())).slice(0, 7)

  // Nur laden, was gerade auch sichtbar ist – ausgeblendete Kacheln kosten
  // sonst bei jedem Filterwechsel unnötige Abfragen.
  const optional = (id, fn) => (isVisible(id) ? fn() : Promise.resolve(null))

  ;[summary.value, previous.value, trend.value, networth.value, savingsRate.value,
    yearComp.value, recurringStatus.value, budgetStatus.value, cumulative.value,
    categoryTrend.value, topCounterparties.value] = await Promise.all([
    api.get('/dashboard/summary', summaryParams),
    api.get('/dashboard/summary', { ...previousRange(range.date_from, range.date_to), account_ids }),
    api.get('/dashboard/summary', trendParams),
    optional('networth', () => api.get('/dashboard/networth', trendParams)),
    optional('savings_rate', () => api.get('/dashboard/savings-rate', trendParams)),
    optional('year_comparison', () => api.get('/dashboard/year-comparison', { account_ids })),
    api.get('/recurring-items/status').then((r) => r.rows),
    optional('budget_progress', () => api.get('/budgets/status', { month, account_ids })),
    optional('cumulative', () => api.get('/dashboard/cumulative', { month, account_ids })),
    optional('category_trend', () => api.get('/dashboard/category-trend', { ...trendParams, limit: 5 })),
    optional('top_counterparties', () => api.get('/dashboard/top-counterparties', { ...range, account_ids, limit: 10 })),
  ])
  await loadDeposits()
}

function pickDepositAccount() {
  if (householdAccounts.value.length && !depositAccountId.value) {
    depositAccountId.value = householdAccounts.value[0].id
  }
}

onMounted(async () => {
  categories.value = await api.get('/categories')
  period.value = await api.get('/budgets/period').catch(() => null)
  if (period.value && period.value.start_day > 1) applyPreset('last_month')
  ensureValidMode()
  pickDepositAccount()
  await loadLayout()
  await load()
})
// Konten kommen aus App.vue asynchron – erst dann steht der Modus fest
watch(() => accounts.value.length, async () => {
  ensureValidMode()
  pickDepositAccount()
  await loadLayout()
  await load()
})
watch(filter, load, { deep: true })
watch(depositAccountId, loadDeposits)

// ------------------------------------------------------------- Auswertungen
/** Veränderung gegenüber dem Vergleichszeitraum – ohne Bezug ist eine
 *  einzelne Zahl ("Ausgaben 2.345 €") nicht einzuordnen. */
function change(now, before, moreIsBetter = true) {
  if (before == null || Math.abs(before) < 0.005) return null
  const pct = ((now - before) / Math.abs(before)) * 100
  if (Math.abs(pct) < 0.5) return { text: '≈ unverändert', cls: 'hint' }
  const up = pct > 0
  return {
    text: `${up ? '▲' : '▼'} ${Math.abs(pct).toFixed(0)} %`,
    cls: up === moreIsBetter ? 'pos' : 'neg',
  }
}
const kpi = computed(() => {
  if (!summary.value) return null
  const s = summary.value
  const p = previous.value
  return {
    income: s.income, expenses: s.expenses,
    balance: s.income - s.expenses, total: s.balance_total,
    incomeChange: change(s.income, p?.income, true),
    expensesChange: change(s.expenses, p?.expenses, false),
    balanceChange: change(s.income - s.expenses, p ? p.income - p.expenses : null, true),
  }
})

/** Einnahmen, Ausgaben und Bilanz in EINER Kachel statt zwei fast gleichen
 *  Balkendiagrammen nebeneinander. */
const cashflow = computed(() => {
  if (!trend.value) return null
  const months = trend.value.monthly_balance.map((m) => m.month)
  const expenses = trend.value.monthly_expenses.map((m) => m.value)
  const balance = trend.value.monthly_balance.map((m) => m.value)
  return { months, balance, expenses, income: balance.map((b, i) => b + expenses[i]) }
})

// Waagerechte Balken statt Donut: Längen vergleicht das Auge deutlich
// zuverlässiger als Kreissegmente, gerade bei vielen Kategorien.
const topCategories = computed(() => (summary.value?.by_category || []).slice(0, 10))

/** Fixkosten-Sockel: wie viel vom Einkommen ist überhaupt frei verfügbar?
 *  Die zentrale Haushaltszahl – im Fix/Variabel-Diagramm bisher vergraben. */
const fixedBase = computed(() => {
  if (!summary.value) return null
  const income = summary.value.income
  const fixed = summary.value.fixed_vs_variable.expenses_fixed
  const variable = summary.value.fixed_vs_variable.expenses_variable
  return {
    income, fixed, variable,
    free: income - fixed - variable,
    fixedPct: income ? Math.round((fixed / income) * 100) : 0,
  }
})

/** Was in den nächsten 30 Tagen abgebucht wird – für die Liquidität wichtiger
 *  als jede Rückschau. */
const upcoming = computed(() => {
  const rows = recurringStatus.value || []
  const today = new Date()
  const limit = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 30)
  const due = rows
    .filter((r) => r.next_due_estimate && new Date(r.next_due_estimate) <= limit)
    .sort((a, b) => a.next_due_estimate.localeCompare(b.next_due_estimate))
  return { rows: due, total: due.reduce((s, r) => s + Number(r.expected_amount || 0), 0) }
})

const palette = ['#2563eb', '#0f766e', '#b45309', '#7c3aed', '#be185d', '#0369a1',
  '#4d7c0f', '#b91c1c', '#6b7280', '#92400e', '#065f46', '#1d4ed8']
const NO_LEGEND = { plugins: { legend: { display: false } } }
</script>

<template>
  <div v-if="summary">
    <!-- Bereichs-Umschalter: nur sichtbar, wenn es überhaupt etwas zu trennen gibt -->
    <div v-if="availableModes.length > 1" class="chips segmented">
      <button v-for="[key, label] in availableModes" :key="key"
              type="button" :class="{ active: mode === key }" @click="switchMode(key)">{{ label }}</button>
      <span class="hint" style="align-self: center">
        {{ mode === 'gemeinsam' ? 'Nur Haushaltskonten' :
           mode === 'persoenlich' ? 'Nur eigene Konten' : 'Alle Konten zusammen' }}
        – Kacheln und Layout werden je Bereich getrennt gespeichert.
      </span>
    </div>

    <div class="chips">
      <!-- Mehrfachauswahl: mehrere Konten UND mehrere Kategorien gleichzeitig kombinierbar (4.9.1) -->
      <details class="multi-select">
        <summary>{{ accountLabel() }}</summary>
        <div class="menu">
          <label v-for="a in modeAccounts" :key="a.id">
            <input type="checkbox" :value="a.id" v-model="filter.account_ids" /> {{ a.name }}
          </label>
          <div class="actions">
            <button type="button" @click="filter.account_ids = modeAccounts.map((a) => a.id)">Alle</button>
            <button type="button" @click="filter.account_ids = []">Keine</button>
          </div>
        </div>
      </details>
      <details class="multi-select">
        <summary>{{ categoryLabel() }}</summary>
        <div class="menu">
          <label v-for="c in categories" :key="c.id">
            <input type="checkbox" :value="c.id" v-model="filter.category_ids" /> {{ c.name }}
          </label>
          <div class="actions">
            <button type="button" @click="filter.category_ids = categories.map((c) => c.id)">Alle</button>
            <button type="button" @click="filter.category_ids = []">Keine</button>
          </div>
        </div>
      </details>
      <input type="date" v-model="filter.date_from" @input="onManualDate" />
      <input type="date" v-model="filter.date_to" @input="onManualDate" />
      <span v-if="hiddenTiles.length" class="hint" style="align-self: center">
        Ausgeblendet:
        <button v-for="t in hiddenTiles" :key="t.id" @click="show(t.id)" style="margin-left: .25rem">
          + {{ t.label }}</button>
      </span>
    </div>
    <!-- Zeitraum-Quicklinks (4.9) -->
    <div class="chips">
      <button type="button" :class="{ active: activePreset === 'this_month' }" @click="applyPreset('this_month')">{{ period && period.start_day > 1 ? 'Laufender Zeitraum' : 'Dieser Monat' }}</button>
      <button type="button" :class="{ active: activePreset === 'last_month' }" @click="applyPreset('last_month')">{{ period && period.start_day > 1 ? 'Letzter Zeitraum' : 'Letzter Monat' }}</button>
      <button type="button" :class="{ active: activePreset === 'this_year' }" @click="applyPreset('this_year')">Dieses Jahr</button>
      <button type="button" :class="{ active: activePreset === 'last_year' }" @click="applyPreset('last_year')">Letztes Jahr</button>
      <button type="button" :class="{ active: activePreset === 'last_12_months' }" @click="applyPreset('last_12_months')">Letzte 12 Monate</button>
      <select :value="activePreset && activePreset.startsWith('year_') ? activePreset.slice(5) : ''"
              @change="applyYear($event.target.value)" title="Ganzes Kalenderjahr auswählen">
        <option value="">Jahr wählen…</option>
        <option v-for="y in availableYears" :key="y" :value="y">{{ y }}</option>
      </select>
    </div>
    <p class="hint" style="margin-top: -0.5rem">
      Zeitraum gilt für Kennzahlen und Kategorien; Verlaufs-Kacheln zeigen immer die letzten
      {{ TREND_MONTHS }} Monate. Kacheln per Drag &amp; Drop anordnen, ✕ blendet aus.
      <template v-if="period && period.start_day > 1">
        Abrechnungsmonat beginnt am {{ period.start_day }}. – laufender Zeitraum
        <strong>{{ period.current_period }}</strong> ({{ fmtDate(period.current_from) }} –
        {{ fmtDate(period.current_to) }}).
      </template>
    </p>

    <div class="grid">
      <!-- Kennzahlen gebündelt statt vier einzelner Kacheln, jeweils mit
           Veränderung gegenüber dem Vergleichszeitraum davor -->
      <div v-if="isVisible('kpis')" class="tile wide" v-bind="tileProps('kpis')">
        <button class="tile-close" @click="hide('kpis')">✕</button>
        <h3>Kennzahlen <span class="hint">{{ summary.date_from }} – {{ summary.date_to }}</span></h3>
        <div class="kpi-row">
          <div>
            <span class="hint">Einnahmen</span>
            <div class="big pos">{{ fmtAmount(kpi.income) }}</div>
            <span v-if="kpi.incomeChange" :class="kpi.incomeChange.cls" style="font-size: .8rem">
              {{ kpi.incomeChange.text }}</span>
          </div>
          <div>
            <span class="hint">Ausgaben</span>
            <div class="big neg">{{ fmtAmount(kpi.expenses) }}</div>
            <span v-if="kpi.expensesChange" :class="kpi.expensesChange.cls" style="font-size: .8rem">
              {{ kpi.expensesChange.text }}</span>
          </div>
          <div>
            <span class="hint">Bilanz</span>
            <div class="big" :class="kpi.balance >= 0 ? 'pos' : 'neg'">{{ fmtAmount(kpi.balance) }}</div>
            <span v-if="kpi.balanceChange" :class="kpi.balanceChange.cls" style="font-size: .8rem">
              {{ kpi.balanceChange.text }}</span>
          </div>
          <div>
            <span class="hint">{{ mode === 'gemeinsam' ? 'Haushaltsvermögen' : 'Gesamtvermögen' }}</span>
            <div class="big">{{ fmtAmount(kpi.total) }}</div>
            <span class="hint" style="font-size: .8rem">{{ modeAccounts.length }} Konten</span>
          </div>
        </div>
        <p class="hint" style="margin: .4rem 0 0">Vergleich: gleich langer Zeitraum davor, ohne Umbuchungen.</p>
      </div>

      <!-- Handlungsbedarf wird nicht versteckt (4.9.1) -->
      <div v-if="isVisible('unassigned') && summary.unassigned_count > 0" class="tile warn" v-bind="tileProps('unassigned')">
        <h3>⚠ Handlungsbedarf</h3>
        <p><strong>{{ summary.unassigned_count }}</strong> Buchungen ohne Kategorie.</p>
        <router-link class="btn" :to="{ path: '/buchungen', query: { unassigned: 1 } }">Jetzt zuordnen</router-link>
      </div>

      <!-- Kumulierter Monatsverlauf: gegensteuern, solange der Monat läuft -->
      <div v-if="isVisible('cumulative') && cumulative" class="tile wide" v-bind="tileProps('cumulative')">
        <button class="tile-close" @click="hide('cumulative')">✕</button>
        <h3>Ausgaben kumuliert – {{ cumulative.month }} gegen {{ cumulative.previous_month }}
          <span class="hint">{{ fmtDate(cumulative.date_from) }} – {{ fmtDate(cumulative.date_to) }}</span></h3>
        <ChartCanvas type="line" :labels="cumulative.days"
          :datasets="[
            { label: cumulative.previous_month, data: cumulative.previous, borderColor: '#9aa7b4',
              borderDash: [5, 4], pointRadius: 0, tension: .2 },
            { label: cumulative.month, data: cumulative.current, borderColor: '#2563eb',
              backgroundColor: '#2563eb22', fill: true, pointRadius: 0, tension: .2, spanGaps: false },
          ]"
          :options="{ scales: { x: { title: { display: true, text: 'Tag im Monat' } } } }" />
        <p class="hint" style="margin: .4rem 0 0">Liegt die blaue Linie über der grauen, wird schneller
          ausgegeben als im Vormonat.</p>
      </div>

      <!-- Budget-Fortschritt: die handlungsrelevanteste Ansicht überhaupt (4.8) -->
      <div v-if="isVisible('budget_progress') && budgetStatus" class="tile wide" v-bind="tileProps('budget_progress')">
        <button class="tile-close" @click="hide('budget_progress')">✕</button>
        <h3>Budget-Fortschritt <span class="hint">{{ budgetStatus.month }}</span></h3>
        <table v-if="budgetStatus.rows.length">
          <tbody>
            <tr v-for="row in budgetStatus.rows" :key="row.budget_id">
              <td style="width: 30%">{{ row.category_name }}
                <span v-if="row.account_name" class="badge gray"
                      :title="`Gilt nur für ${row.account_name} und verbraucht sich nur an dessen Buchungen`">
                  {{ row.account_name }}</span></td>
              <td>
                <div class="budget-bar">
                  <div :style="{ width: Math.min(100, row.percent) + '%',
                                 background: `var(--ampel-${row.ampel})` }"></div>
                </div>
              </td>
              <td class="num" style="width: 22%">
                {{ fmtAmount(row.spent) }} <span class="hint">/ {{ fmtAmount(row.budget) }}</span>
              </td>
              <td class="num hint" style="width: 8%">{{ Math.round(row.percent) }} %</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="hint">Noch keine Budgets angelegt.
          <router-link to="/budgets">Jetzt anlegen</router-link></p>
      </div>

      <!-- Fixkosten-Sockel: wie viel vom Einkommen ist frei verfügbar? -->
      <div v-if="isVisible('fixed_base') && fixedBase" class="tile wide" v-bind="tileProps('fixed_base')">
        <button class="tile-close" @click="hide('fixed_base')">✕</button>
        <h3>Fixkosten-Sockel</h3>
        <p v-if="fixedBase.income">
          Von <strong>{{ fmtAmount(fixedBase.income) }}</strong> Einnahmen sind
          <strong>{{ fmtAmount(fixedBase.fixed) }}</strong> Fixkosten
          (<strong>{{ fixedBase.fixedPct }} %</strong>),
          <span :class="fixedBase.free >= 0 ? 'pos' : 'neg'">
            {{ fmtAmount(fixedBase.free) }}</span> blieben übrig.
        </p>
        <p v-else class="hint">Keine Einnahmen im gewählten Zeitraum.</p>
        <ChartCanvas type="bar" :labels="['Einnahmen']"
          :datasets="[
            { label: 'Fixkosten', data: [fixedBase.fixed], backgroundColor: '#b45309' },
            { label: 'variable Ausgaben', data: [fixedBase.variable], backgroundColor: '#2563eb' },
            { label: 'übrig', data: [Math.max(0, fixedBase.free)], backgroundColor: '#15803d' },
          ]"
          :options="{ indexAxis: 'y', scales: { x: { stacked: true }, y: { stacked: true } } }" />
      </div>

      <!-- Fälligkeiten: Liquiditätsblick nach vorn statt nur zurück (4.7 b) -->
      <div v-if="isVisible('upcoming')" class="tile" v-bind="tileProps('upcoming')">
        <button class="tile-close" @click="hide('upcoming')">✕</button>
        <h3>Fällig in den nächsten 30 Tagen</h3>
        <template v-if="upcoming.rows.length">
          <div class="big">{{ fmtAmount(upcoming.total) }}</div>
          <table>
            <tbody>
              <tr v-for="row in upcoming.rows.slice(0, 8)" :key="row.id">
                <td><span class="ampel" :class="row.ampel"></span> {{ row.name }}</td>
                <td class="hint">{{ row.next_due_estimate }}</td>
                <td class="num">{{ fmtAmount(row.expected_amount) }}</td>
              </tr>
            </tbody>
          </table>
        </template>
        <p v-else class="hint">Keine wiederkehrende Position mit Fälligkeit in den nächsten 30 Tagen.</p>
      </div>

      <!-- Kategorie-Trend: WAS ist teurer geworden (Jahresvergleich ist zu grob) -->
      <div v-if="isVisible('category_trend') && categoryTrend" class="tile wide" v-bind="tileProps('category_trend')">
        <button class="tile-close" @click="hide('category_trend')">✕</button>
        <h3>Kategorie-Trend <span class="hint">größte Ausgabenkategorien, letzte {{ TREND_MONTHS }} Monate</span></h3>
        <ChartCanvas v-if="categoryTrend.rows.length" type="line" :labels="categoryTrend.months"
          :datasets="categoryTrend.rows.map((r, i) => ({ label: r.category_name, data: r.values,
            borderColor: palette[i % palette.length], tension: .25, pointRadius: 0 }))" />
        <p v-else class="hint">Keine Ausgaben im Zeitraum.</p>
      </div>

      <!-- Top-Empfänger: wohin das Geld jenseits der Kategorie fließt -->
      <div v-if="isVisible('top_counterparties') && topCounterparties" class="tile" v-bind="tileProps('top_counterparties')">
        <button class="tile-close" @click="hide('top_counterparties')">✕</button>
        <h3>Top-Empfänger im Zeitraum</h3>
        <table v-if="topCounterparties.rows.length">
          <tbody>
            <tr v-for="row in topCounterparties.rows" :key="row.counterparty">
              <td>{{ row.counterparty }} <span class="hint">{{ row.count }}×</span></td>
              <td class="num neg">{{ fmtAmount(row.total) }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="hint">Keine Ausgaben im gewählten Zeitraum.</p>
      </div>

      <div v-if="isVisible('cashflow') && cashflow" class="tile wide" v-bind="tileProps('cashflow')">
        <button class="tile-close" @click="hide('cashflow')">✕</button>
        <h3>Einnahmen / Ausgaben im Verlauf <span class="hint">letzte {{ TREND_MONTHS }} Monate</span></h3>
        <ChartCanvas type="bar" :labels="cashflow.months"
          :datasets="[
            { label: 'Einnahmen', data: cashflow.income, backgroundColor: '#15803d' },
            { label: 'Ausgaben', data: cashflow.expenses.map((v) => -v), backgroundColor: '#b91c1c' },
            { type: 'line', label: 'Bilanz', data: cashflow.balance, borderColor: '#1c2530',
              borderWidth: 2, pointRadius: 2, tension: .2 },
          ]" />
      </div>

      <div v-if="isVisible('by_category')" class="tile wide" v-bind="tileProps('by_category')">
        <button class="tile-close" @click="hide('by_category')">✕</button>
        <h3>Ausgaben nach Kategorie</h3>
        <ChartCanvas v-if="topCategories.length" type="bar"
          :labels="topCategories.map((c) => c.category_name)"
          :datasets="[{ data: topCategories.map((c) => c.value), backgroundColor: palette }]"
          :options="{ indexAxis: 'y', ...NO_LEGEND }" />
        <p v-else class="hint">Keine Ausgaben im gewählten Zeitraum.</p>
      </div>

      <div v-if="isVisible('fixed')" class="tile" v-bind="tileProps('fixed')">
        <button class="tile-close" @click="hide('fixed')">✕</button>
        <h3>Ausgaben: fix vs. variabel</h3>
        <ChartCanvas type="bar"
          :labels="['Ausgaben']"
          :datasets="[
            { label: 'fix', data: [summary.fixed_vs_variable.expenses_fixed], backgroundColor: '#b45309' },
            { label: 'variabel', data: [summary.fixed_vs_variable.expenses_variable], backgroundColor: '#2563eb' },
          ]"
          :options="{ indexAxis: 'y', scales: { x: { stacked: true }, y: { stacked: true } } }" />
        <p class="hint" style="margin: .4rem 0 0">
          Fixkosten-Anteil:
          <strong>{{ summary.expenses ? Math.round(summary.fixed_vs_variable.expenses_fixed / summary.expenses * 100) : 0 }} %</strong>
          – der Rest ist kurzfristig beeinflussbar.
        </p>
      </div>

      <div v-if="isVisible('savings') && trend" class="tile wide" v-bind="tileProps('savings')">
        <button class="tile-close" @click="hide('savings')">✕</button>
        <h3>Monatliche Bewegung der Sparkonten <span class="hint">letzte {{ TREND_MONTHS }} Monate</span></h3>
        <ChartCanvas type="bar"
          :labels="trend.savings_movement.map((m) => m.month)"
          :datasets="[{ label: 'Bewegung', data: trend.savings_movement.map((m) => m.value),
                        backgroundColor: '#0f766e' }]" />
      </div>

      <div v-if="isVisible('networth') && networth" class="tile wide" v-bind="tileProps('networth')">
        <button class="tile-close" @click="hide('networth')">✕</button>
        <h3>Vermögensverlauf (Monatsende) <span class="hint">letzte {{ TREND_MONTHS }} Monate</span></h3>
        <ChartCanvas type="line"
          :labels="networth.months"
          :datasets="[
            { label: 'Gesamt', data: networth.total, borderColor: '#1c2530', borderWidth: 2.5, tension: .2, pointRadius: 0 },
            ...networth.series.map((s, i) => ({ label: s.name, data: s.values,
              borderColor: palette[i % palette.length], tension: .2, pointRadius: 0 })),
          ]" />
      </div>

      <div v-if="isVisible('savings_rate') && savingsRate" class="tile wide" v-bind="tileProps('savings_rate')">
        <button class="tile-close" @click="hide('savings_rate')">✕</button>
        <h3>Sparquote <span class="hint">letzte {{ TREND_MONTHS }} Monate</span></h3>
        <ChartCanvas type="bar"
          :labels="savingsRate.months"
          :datasets="[
            { label: 'tatsächlich gespart %', data: savingsRate.rate,
              backgroundColor: savingsRate.rate.map((v) => v >= 0 ? '#0f766e' : '#b91c1c') },
            { type: 'line', label: 'Sparpotenzial (Einnahmen − Ausgaben) %', data: savingsRate.surplus_rate,
              borderColor: '#9aa7b4', borderDash: [5, 4], borderWidth: 2, pointRadius: 0, tension: .2 },
          ]"
          :options="{ scales: { y: { ticks: { callback: (v) => v + ' %' } } } }" />
        <p class="hint" style="margin: .4rem 0 0">
          Balken = Netto-Zufluss auf die Sparkonten, inklusive aller Umbuchungen in beide Richtungen
          (200 € aufs Tagesgeld, 50 € zurück = 150 € gespart).
          Die gestrichelte Linie ist das, was rechnerisch übrig blieb – der Abstand dazwischen liegt
          unverzinst auf dem Girokonto.
        </p>
      </div>

      <div v-if="isVisible('year_comparison') && yearComp" class="tile wide" v-bind="tileProps('year_comparison')">
        <button class="tile-close" @click="hide('year_comparison')">✕</button>
        <h3>Jahresvergleich – Ausgaben pro Kategorie</h3>
        <div style="overflow-x: auto">
          <table>
            <thead><tr><th>Kategorie</th><th v-for="y in yearComp.years" :key="y" class="num">{{ y }}</th></tr></thead>
            <tbody>
              <tr v-for="row in yearComp.rows.slice(0, 10)" :key="row.category_name">
                <td>{{ row.category_name }}</td>
                <td v-for="(v, i) in row.values" :key="i" class="num">{{ v ? fmtAmount(v) : '–' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- v1.2: Ampel-Übersicht wiederkehrende Kostenpositionen (4.7 b, 4.9) -->
      <div v-if="isVisible('recurring_ampel') && recurringStatus" class="tile wide" v-bind="tileProps('recurring_ampel')">
        <button class="tile-close" @click="hide('recurring_ampel')">✕</button>
        <h3>Wiederkehrende Kosten – Soll/Ist</h3>
        <table v-if="recurringStatus.length">
          <tbody>
            <tr v-for="row in recurringStatus.slice(0, 8)" :key="row.id">
              <td><span class="ampel" :class="row.ampel"></span></td>
              <td>{{ row.name }}</td>
              <td class="hint">fällig ca. {{ row.next_due_estimate || '–' }}</td>
              <td class="num">{{ row.last_charge_amount != null ? fmtAmount(row.last_charge_amount) : '–' }}</td>
            </tr>
          </tbody>
        </table>
        <p v-else class="hint">Noch keine wiederkehrenden Positionen angelegt.
          <router-link to="/wiederkehrend">Jetzt anlegen</router-link></p>
        <router-link class="btn" style="margin-top: .5rem; display: inline-block" to="/wiederkehrend">Details →</router-link>
      </div>

      <!-- v1.2: Einzahlungstransparenz gemeinsames Konto (4.9) -->
      <div v-if="isVisible('deposits')" class="tile wide" v-bind="tileProps('deposits')">
        <button class="tile-close" @click="hide('deposits')">✕</button>
        <h3>Einzahlungen pro Person (gemeinsames Konto)</h3>
        <div v-if="householdAccounts.length">
          <select v-model="depositAccountId" style="margin-bottom: .5rem">
            <option v-for="a in householdAccounts" :key="a.id" :value="a.id">{{ a.name }}</option>
          </select>
          <ChartCanvas v-if="deposits" type="bar"
            :labels="deposits.months"
            :datasets="deposits.depositors.map((d, i) => ({ label: d,
              data: deposits.series.map((s) => s.values[d] || 0),
              backgroundColor: palette[i % palette.length] }))"
            :options="{ scales: { x: { stacked: true }, y: { stacked: true } } }" />
        </div>
        <p v-else class="hint">Kein Haushaltskonto vorhanden – in den Einstellungen als solches markieren.</p>
      </div>
    </div>
  </div>
  <p v-else-if="accounts.length" class="hint">Lade Dashboard …</p>
  <p v-else class="hint">Noch keine Konten angelegt – unter <router-link to="/einstellungen">Einstellungen</router-link> anlegen.</p>
</template>
