<script setup>
import { computed, inject, onMounted, ref, watch } from 'vue'
import { api, fmtAmount } from '../api.js'
import ChartCanvas from '../components/ChartCanvas.vue'

const accounts = inject('accounts')
const summary = ref(null)
const networth = ref(null)
const savingsRate = ref(null)
const yearComp = ref(null)
const recurringStatus = ref(null)
const deposits = ref(null)
const categories = ref([])

// Zeitraum-Voreinstellung: letzter abgeschlossener Kalendermonat (4.9) –
// bewusst lokale Datumsteile statt toISOString(), sonst verschiebt die
// UTC-Umrechnung das Datum je nach Zeitzone um einen Tag.
function fmtDateLocal(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}
function lastMonthRange() {
  const now = new Date()
  const lastMonthEnd = new Date(now.getFullYear(), now.getMonth(), 0) // Tag 0 = letzter Tag des Vormonats
  const lastMonthStart = new Date(lastMonthEnd.getFullYear(), lastMonthEnd.getMonth(), 1)
  return { date_from: fmtDateLocal(lastMonthStart), date_to: fmtDateLocal(lastMonthEnd) }
}

// Filter-Chips: mehrere Konten UND mehrere Kategorien gleichzeitig wählbar,
// alle Auswahlen filtern zusammen alle Kacheln (4.9.1)
const filter = ref({ account_ids: [], category_ids: [], ...lastMonthRange() })

function accountLabel() {
  const n = filter.value.account_ids.length
  return n ? `Konten (${n})` : 'Alle Konten'
}
function categoryLabel() {
  const n = filter.value.category_ids.length
  return n ? `Kategorien (${n})` : 'Alle Kategorien'
}

// Kachel-Registry: eine neue Auswertung ist ein neuer Eintrag, kein Layout-Umbau (4.9.1)
const TILES = [
  ['income', 'Einnahmen'], ['expenses', 'Ausgaben'], ['balance', 'Bilanz'],
  ['total', 'Gesamtvermögen'], ['unassigned', 'Handlungsbedarf'],
  ['monthly_balance', 'Monatliche Bilanz'], ['monthly_expenses', 'Monatliche Ausgaben'],
  ['by_category', 'Ausgaben nach Kategorie'], ['fixed', 'Fix / Variabel'],
  ['savings', 'Bewegung Sparkonten'], ['top', 'Top-Ausgaben'],
  ['networth', 'Vermögensverlauf'], ['savings_rate', 'Sparquote'],
  ['year_comparison', 'Jahresvergleich'],
  ['recurring_ampel', 'Wiederkehrende Kosten (Ampel)'], ['deposits', 'Einzahlungen gemeinsames Konto'],
]
const layout = ref(TILES.map(([id]) => ({ id, visible: true })))
const dragId = ref(null)

function normalizeLayout(stored) {
  // gespeicherte Reihenfolge übernehmen, neue Kacheltypen hinten anfügen
  const known = new Map(TILES.map(([id, label]) => [id, label]))
  const result = (stored || []).filter((t) => known.has(t.id))
  for (const [id] of TILES) if (!result.find((t) => t.id === id)) result.push({ id, visible: true })
  return result
}

// Einzahlungstransparenz braucht ein konkretes gemeinsames Konto (4.9)
const depositAccountId = ref('')
const sharedAccounts = computed(() => accounts.value.filter((a) => a.shared))

async function loadDeposits() {
  if (!depositAccountId.value) { deposits.value = null; return }
  const range = { date_from: filter.value.date_from, date_to: filter.value.date_to }
  deposits.value = await api.get('/dashboard/deposits', { ...range, account_id: depositAccountId.value })
}

async function load() {
  const range = {}
  if (filter.value.date_from) range.date_from = filter.value.date_from
  if (filter.value.date_to) range.date_to = filter.value.date_to
  const accountRange = { ...range }
  if (filter.value.account_ids.length) accountRange.account_ids = filter.value.account_ids
  const summaryParams = { ...accountRange }
  if (filter.value.category_ids.length) summaryParams.category_ids = filter.value.category_ids

  ;[summary.value, networth.value, savingsRate.value, yearComp.value, recurringStatus.value] = await Promise.all([
    api.get('/dashboard/summary', summaryParams),
    api.get('/dashboard/networth', accountRange),
    api.get('/dashboard/savings-rate', accountRange),
    api.get('/dashboard/year-comparison', filter.value.account_ids.length ? { account_ids: filter.value.account_ids } : {}),
    api.get('/recurring-items/status').then((r) => r.rows),
  ])
  await loadDeposits()
}

onMounted(async () => {
  categories.value = await api.get('/categories')
  const saved = await api.get('/dashboard/layout')
  layout.value = normalizeLayout(saved.tiles)
  if (sharedAccounts.value.length) depositAccountId.value = sharedAccounts.value[0].id
  await load()
})
watch(filter, load, { deep: true })
watch(depositAccountId, loadDeposits)

const orderOf = (id) => layout.value.findIndex((t) => t.id === id)
const isVisible = (id) => layout.value.find((t) => t.id === id)?.visible !== false
const hiddenTiles = computed(() =>
  layout.value.filter((t) => !t.visible).map((t) => ({ ...t, label: TILES.find(([i]) => i === t.id)?.[1] })))

async function saveLayout() {
  await api.put('/dashboard/layout', { tiles: layout.value })
}
function hide(id) {
  const t = layout.value.find((t) => t.id === id)
  if (t) { t.visible = false; saveLayout() }
}
function show(id) {
  const t = layout.value.find((t) => t.id === id)
  if (t) { t.visible = true; saveLayout() }
}
function onDrop(targetId) {
  if (!dragId.value || dragId.value === targetId) return
  const from = orderOf(dragId.value)
  const to = orderOf(targetId)
  const [moved] = layout.value.splice(from, 1)
  layout.value.splice(to, 0, moved)
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

const palette = ['#2563eb', '#0f766e', '#b45309', '#7c3aed', '#be185d', '#0369a1',
  '#4d7c0f', '#b91c1c', '#6b7280', '#92400e', '#065f46', '#1d4ed8']
</script>

<template>
  <div v-if="summary">
    <div class="chips">
      <!-- Mehrfachauswahl: mehrere Konten UND mehrere Kategorien gleichzeitig kombinierbar (4.9.1) -->
      <details class="multi-select">
        <summary>{{ accountLabel() }}</summary>
        <div class="menu">
          <label v-for="a in accounts" :key="a.id">
            <input type="checkbox" :value="a.id" v-model="filter.account_ids" /> {{ a.name }}
          </label>
          <div class="actions">
            <button type="button" @click="filter.account_ids = accounts.map((a) => a.id)">Alle</button>
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
      <!-- frei wählbarer Zeitraum statt festem Raster (4.9) -->
      <input type="date" v-model="filter.date_from" />
      <input type="date" v-model="filter.date_to" />
      <span v-if="hiddenTiles.length" class="hint" style="align-self: center">
        Ausgeblendet:
        <button v-for="t in hiddenTiles" :key="t.id" @click="show(t.id)" style="margin-left: .25rem">
          + {{ t.label }}</button>
      </span>
    </div>
    <p class="hint" style="margin-top: -0.5rem">Mehrere Konten/Kategorien gleichzeitig wählbar, kombinieren sich als Filter. Kacheln per Drag &amp; Drop anordnen, ✕ blendet aus – Layout wird pro Nutzer gespeichert.</p>

    <div class="grid">
      <div v-if="isVisible('income')" class="tile" v-bind="tileProps('income')">
        <button class="tile-close" @click="hide('income')">✕</button>
        <h3>Einnahmen</h3>
        <div class="big pos">{{ fmtAmount(summary.income) }}</div>
        <p class="hint">{{ summary.date_from }} – {{ summary.date_to }}, ohne Umbuchungen</p>
      </div>
      <div v-if="isVisible('expenses')" class="tile" v-bind="tileProps('expenses')">
        <button class="tile-close" @click="hide('expenses')">✕</button>
        <h3>Ausgaben</h3>
        <div class="big neg">{{ fmtAmount(summary.expenses) }}</div>
      </div>
      <div v-if="isVisible('balance')" class="tile" v-bind="tileProps('balance')">
        <button class="tile-close" @click="hide('balance')">✕</button>
        <h3>Bilanz</h3>
        <div class="big" :class="summary.income - summary.expenses >= 0 ? 'pos' : 'neg'">
          {{ fmtAmount(summary.income - summary.expenses) }}
        </div>
      </div>
      <div v-if="isVisible('total')" class="tile" v-bind="tileProps('total')">
        <button class="tile-close" @click="hide('total')">✕</button>
        <h3>Gesamtvermögen</h3>
        <div class="big">{{ fmtAmount(summary.balance_total) }}</div>
      </div>

      <!-- Handlungsbedarf wird nicht versteckt (4.9.1) -->
      <div v-if="isVisible('unassigned') && summary.unassigned_count > 0" class="tile warn" v-bind="tileProps('unassigned')">
        <h3>⚠ Handlungsbedarf</h3>
        <p><strong>{{ summary.unassigned_count }}</strong> Buchungen ohne Kategorie.</p>
        <router-link class="btn" :to="{ path: '/buchungen', query: { unassigned: 1 } }">Jetzt zuordnen</router-link>
      </div>

      <div v-if="isVisible('monthly_balance')" class="tile wide" v-bind="tileProps('monthly_balance')">
        <button class="tile-close" @click="hide('monthly_balance')">✕</button>
        <h3>Monatliche Bilanz (Einnahmen − Ausgaben)</h3>
        <ChartCanvas type="bar"
          :labels="summary.monthly_balance.map((m) => m.month)"
          :datasets="[{ label: 'Bilanz', data: summary.monthly_balance.map((m) => m.value),
                        backgroundColor: summary.monthly_balance.map((m) => m.value >= 0 ? '#15803d' : '#b91c1c') }]" />
      </div>
      <div v-if="isVisible('monthly_expenses')" class="tile wide" v-bind="tileProps('monthly_expenses')">
        <button class="tile-close" @click="hide('monthly_expenses')">✕</button>
        <h3>Monatliche Gesamtausgaben</h3>
        <ChartCanvas type="bar"
          :labels="summary.monthly_expenses.map((m) => m.month)"
          :datasets="[{ label: 'Ausgaben', data: summary.monthly_expenses.map((m) => m.value),
                        backgroundColor: '#2563eb' }]" />
      </div>
      <div v-if="isVisible('by_category')" class="tile" v-bind="tileProps('by_category')">
        <button class="tile-close" @click="hide('by_category')">✕</button>
        <h3>Ausgaben nach Kategorie</h3>
        <ChartCanvas type="doughnut"
          :labels="summary.by_category.slice(0, 12).map((c) => c.category_name)"
          :datasets="[{ data: summary.by_category.slice(0, 12).map((c) => c.value),
                        backgroundColor: palette }]"
          :options="{ plugins: { legend: { position: 'right' } } }" />
      </div>
      <div v-if="isVisible('fixed')" class="tile" v-bind="tileProps('fixed')">
        <button class="tile-close" @click="hide('fixed')">✕</button>
        <h3>Fix / Variabel</h3>
        <ChartCanvas type="doughnut"
          :labels="['Ausgaben fix', 'Ausgaben variabel', 'Einnahmen fix', 'Einnahmen variabel']"
          :datasets="[{ data: [summary.fixed_vs_variable.expenses_fixed,
                              summary.fixed_vs_variable.expenses_variable,
                              summary.fixed_vs_variable.income_fixed,
                              summary.fixed_vs_variable.income_variable],
                        backgroundColor: ['#b45309', '#2563eb', '#0f766e', '#15803d'] }]"
          :options="{ plugins: { legend: { position: 'right' } } }" />
      </div>
      <div v-if="isVisible('savings')" class="tile wide" v-bind="tileProps('savings')">
        <button class="tile-close" @click="hide('savings')">✕</button>
        <h3>Monatliche Bewegung der Sparkonten</h3>
        <ChartCanvas type="bar"
          :labels="summary.savings_movement.map((m) => m.month)"
          :datasets="[{ label: 'Bewegung', data: summary.savings_movement.map((m) => m.value),
                        backgroundColor: '#0f766e' }]" />
      </div>
      <div v-if="isVisible('top')" class="tile" v-bind="tileProps('top')">
        <button class="tile-close" @click="hide('top')">✕</button>
        <h3>Top-Ausgaben im Zeitraum</h3>
        <table>
          <tbody>
            <tr v-for="c in summary.by_category.slice(0, 8)" :key="c.category_name">
              <td>{{ c.category_name }} <span v-if="c.is_fixed_cost" class="badge gray">fix</span></td>
              <td class="num neg">{{ fmtAmount(c.value) }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- v1.1: Vermögensverlauf pro Konto (4.9) -->
      <div v-if="isVisible('networth') && networth" class="tile wide" v-bind="tileProps('networth')">
        <button class="tile-close" @click="hide('networth')">✕</button>
        <h3>Vermögensverlauf (Monatsende)</h3>
        <ChartCanvas type="line"
          :labels="networth.months"
          :datasets="[
            { label: 'Gesamt', data: networth.total, borderColor: '#1c2530', borderWidth: 2.5, tension: .2, pointRadius: 0 },
            ...networth.series.map((s, i) => ({ label: s.name, data: s.values,
              borderColor: palette[i % palette.length], tension: .2, pointRadius: 0 })),
          ]" />
      </div>
      <!-- v1.1: Sparquote (4.9) -->
      <div v-if="isVisible('savings_rate') && savingsRate" class="tile wide" v-bind="tileProps('savings_rate')">
        <button class="tile-close" @click="hide('savings_rate')">✕</button>
        <h3>Sparquote (Bilanz ÷ Einnahmen)</h3>
        <ChartCanvas type="line"
          :labels="savingsRate.months"
          :datasets="[{ label: 'Sparquote %', data: savingsRate.rate,
                        borderColor: '#0f766e', backgroundColor: '#0f766e33', fill: true, tension: .2 }]"
          :options="{ scales: { y: { ticks: { callback: (v) => v + ' %' } } } }" />
      </div>
      <!-- v1.1: Jahresvergleich pro Kategorie (4.9) -->
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
        <div v-if="sharedAccounts.length">
          <select v-model="depositAccountId" style="margin-bottom: .5rem">
            <option v-for="a in sharedAccounts" :key="a.id" :value="a.id">{{ a.name }}</option>
          </select>
          <ChartCanvas v-if="deposits" type="bar"
            :labels="deposits.months"
            :datasets="deposits.depositors.map((d, i) => ({ label: d,
              data: deposits.series.map((s) => s.values[d] || 0),
              backgroundColor: palette[i % palette.length] }))"
            :options="{ scales: { x: { stacked: true }, y: { stacked: true } } }" />
        </div>
        <p v-else class="hint">Kein gemeinsames Konto vorhanden.</p>
      </div>
    </div>
  </div>
  <p v-else class="hint">Lade Dashboard …</p>
</template>
