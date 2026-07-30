<script setup>
import { inject, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, exportUrl, fmtAmount, fmtDate } from '../api.js'

const route = useRoute()
const accounts = inject('accounts')
const refreshAccounts = inject('refreshAccounts')
const categories = ref([])
const page = ref({ total: 0, items: [] })
const suggestions = ref([])
const error = ref('')
const limit = 100
const offset = ref(0)

const filter = ref({
  account_id: route.query.account_id || '',
  category_id: '',
  date_from: '',
  date_to: '',
  text: '',
  tag: '',
  unassigned: route.query.unassigned ? true : false,
})
const allTags = ref([])

// v1.1: Detailbereich je Buchung für Splits & Tags
const openDetail = ref(null)
const splitRows = ref([])
const tagInput = ref('')

function toggleDetail(tx) {
  if (openDetail.value === tx.id) { openDetail.value = null; return }
  openDetail.value = tx.id
  splitRows.value = tx.splits.length
    ? tx.splits.map((s) => ({ category_id: s.category_id, amount: s.amount }))
    : [{ category_id: tx.category_id || '', amount: tx.amount }]
  tagInput.value = tx.tags.map((t) => t.name).join(', ')
}

function splitSum() {
  return splitRows.value.reduce((s, r) => s + Number(r.amount || 0), 0)
}

async function saveSplits(tx) {
  error.value = ''
  try {
    const payload = splitRows.value
      .filter((r) => r.category_id && r.amount)
      .map((r) => ({ category_id: Number(r.category_id), amount: String(r.amount) }))
    const updated = await api.put(`/transactions/${tx.id}/splits`, payload)
    Object.assign(tx, updated)
  } catch (e) { error.value = e.message }
}

async function clearSplits(tx) {
  const updated = await api.put(`/transactions/${tx.id}/splits`, [])
  Object.assign(tx, updated)
  splitRows.value = [{ category_id: tx.category_id || '', amount: tx.amount }]
}

async function saveTags(tx) {
  error.value = ''
  try {
    const names = tagInput.value.split(',').map((s) => s.trim()).filter(Boolean)
    const updated = await api.put(`/transactions/${tx.id}/tags`, names)
    Object.assign(tx, updated)
    allTags.value = await api.get('/transactions/tags')
  } catch (e) { error.value = e.message }
}

const manual = ref({ account_id: '', booking_date: new Date().toISOString().slice(0, 10),
                     amount: '', counterparty: '', purpose: '', category_id: null })
const showManual = ref(false)

async function load() {
  const params = { limit, offset: offset.value }
  for (const [k, v] of Object.entries(filter.value)) if (v) params[k] = v
  page.value = await api.get('/transactions', params)
  suggestions.value = await api.get('/transfers/suggestions')
}

onMounted(async () => {
  categories.value = await api.get('/categories')
  allTags.value = await api.get('/transactions/tags')
  await load()
})
watch(filter, () => { offset.value = 0; load() }, { deep: true })
watch(() => route.query, () => {
  filter.value.account_id = route.query.account_id || ''
  filter.value.unassigned = !!route.query.unassigned
})

function catName(id) {
  const c = categories.value.find((c) => c.id === id)
  return c ? c.name : ''
}

async function setCategory(tx, categoryId) {
  error.value = ''
  try {
    await api.put(`/transactions/${tx.id}`, { category_id: categoryId ? Number(categoryId) : null })
    tx.category_id = categoryId ? Number(categoryId) : null
  } catch (e) { error.value = e.message }
}

async function makeRule(tx) {
  // Aus manueller Zuordnung eine Regel machen: "künftig immer so" (4.6)
  if (!tx.category_id) return
  const criteria = tx.counterparty_iban
    ? { iban_equals: tx.counterparty_iban }
    : { counterparty_contains: tx.counterparty || tx.purpose.slice(0, 30) }
  try {
    await api.post('/rules', { name: `Auto: ${tx.counterparty || tx.purpose.slice(0, 30)}`,
                               category_id: tx.category_id, ...criteria })
    error.value = ''
    alert('Regel angelegt – über "Regeln" anpassbar, rückwirkend anwendbar.')
  } catch (e) { error.value = e.message }
}

async function saveManual() {
  error.value = ''
  try {
    await api.post('/transactions', { ...manual.value, amount: String(manual.value.amount),
                                      category_id: manual.value.category_id || null })
    showManual.value = false
    manual.value.amount = ''; manual.value.counterparty = ''; manual.value.purpose = ''
    await load(); await refreshAccounts()
  } catch (e) { error.value = e.message }
}

async function linkPair(s) {
  await api.post('/transfers/link', { transaction_id_a: s.transaction_a.id,
                                      transaction_id_b: s.transaction_b.id })
  await load()
}

async function unlink(tx) {
  await api.del(`/transfers/${tx.transfer_id}`)
  await load()
}

function doExport() {
  const params = {}
  for (const [k, v] of Object.entries(filter.value)) if (v && k !== 'unassigned') params[k] = v
  window.open(exportUrl(params), '_blank')
}
</script>

<template>
  <div>
    <div class="topbar">
      <h1>Buchungen</h1>
      <div class="spacer"></div>
      <button @click="showManual = !showManual">+ Manuelle Buchung</button>
      <button @click="doExport">Export CSV</button>
    </div>

    <div v-if="showManual" class="tile" style="margin-bottom: 1rem">
      <h3>Manuelle Buchung (z.B. Bargeld)</h3>
      <div class="form-row">
        <div><label>Konto</label>
          <select v-model="manual.account_id">
            <option v-for="a in accounts.filter((a) => a.my_role !== 'reader')" :key="a.id" :value="a.id">{{ a.name }}</option>
          </select></div>
        <div><label>Datum</label><input type="date" v-model="manual.booking_date" /></div>
        <div><label>Betrag (− = Ausgabe)</label><input type="number" step="0.01" v-model="manual.amount" /></div>
        <div><label>Gegenpartei</label><input v-model="manual.counterparty" /></div>
        <div><label>Zweck</label><input v-model="manual.purpose" /></div>
        <div><label>Kategorie</label>
          <select v-model="manual.category_id">
            <option :value="null">–</option>
            <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select></div>
        <button class="primary" @click="saveManual">Speichern</button>
      </div>
    </div>

    <div class="chips">
      <select v-model="filter.account_id">
        <option value="">Alle Konten</option>
        <option v-for="a in accounts" :key="a.id" :value="String(a.id)">{{ a.name }}</option>
      </select>
      <select v-model="filter.category_id">
        <option value="">Alle Kategorien</option>
        <option v-for="c in categories" :key="c.id" :value="String(c.id)">{{ c.name }}</option>
      </select>
      <input type="date" v-model="filter.date_from" />
      <input type="date" v-model="filter.date_to" />
      <input v-model.lazy="filter.text" placeholder="Suche…" />
      <select v-model="filter.tag">
        <option value="">Alle Tags</option>
        <option v-for="t in allTags" :key="t.id" :value="t.name">🏷 {{ t.name }}</option>
      </select>
      <label style="align-self: center"><input type="checkbox" v-model="filter.unassigned" /> nur ohne Kategorie</label>
    </div>

    <p v-if="error" class="error">{{ error }}</p>

    <div v-if="suggestions.length" class="tile warn" style="margin-bottom: 1rem">
      <h3>Mögliche Umbuchungen ({{ suggestions.length }})</h3>
      <p class="hint">Gleicher Betrag, gegenläufig, ±5 Tage – bitte bestätigen (4.4).</p>
      <div v-for="s in suggestions" :key="s.transaction_a.id" style="margin-bottom: .4rem">
        {{ fmtDate(s.transaction_a.booking_date) }}: {{ fmtAmount(s.transaction_a.amount) }}
        ({{ accounts.find((a) => a.id === s.transaction_a.account_id)?.name }})
        ↔ {{ accounts.find((a) => a.id === s.transaction_b.account_id)?.name }}
        <button style="margin-left: .5rem" @click="linkPair(s)">Als Umbuchung verknüpfen</button>
      </div>
    </div>

    <table>
      <thead>
        <tr><th>Datum</th><th>Konto</th><th>Gegenpartei / Zweck</th><th>Kategorie</th><th class="num">Betrag</th><th></th></tr>
      </thead>
      <tbody>
        <template v-for="t in page.items" :key="t.id">
        <tr :class="t.transfer_id ? 'transfer' : ''">
          <td>{{ fmtDate(t.booking_date) }}</td>
          <td>{{ accounts.find((a) => a.id === t.account_id)?.name }}</td>
          <td>
            <strong>{{ t.counterparty }}</strong>
            <span v-if="t.is_manual" class="badge gray">manuell</span>
            <span v-if="t.transfer_id" class="badge gray">Umbuchung</span>
            <span v-if="t.splits.length" class="badge">Split ({{ t.splits.length }})</span>
            <span v-for="tag in t.tags" :key="tag.id" class="badge gray">🏷 {{ tag.name }}</span>
            <br /><span class="hint">{{ t.purpose }}</span>
          </td>
          <td>
            <!-- auffälliger Zuordnen-Hinweis statt stillem Verschwinden (4.9.1) -->
            <span v-if="!t.category_id && !t.splits.length && !t.transfer_id" class="badge warn">zuordnen ↓</span>
            <template v-if="!t.splits.length">
              <select :value="t.category_id ?? ''" @change="setCategory(t, $event.target.value)">
                <option value="">– keine –</option>
                <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
              </select>
              <button v-if="t.category_id" title="Regel: künftig immer so" @click="makeRule(t)">↻ Regel</button>
            </template>
            <span v-else class="hint">aufgeteilt</span>
          </td>
          <td class="num" :class="t.transfer_id ? '' : t.amount < 0 ? 'neg' : 'pos'">{{ fmtAmount(t.amount) }}</td>
          <td style="white-space: nowrap">
            <button @click="toggleDetail(t)" title="Split & Tags">{{ openDetail === t.id ? '▴' : '▾' }}</button>
            <button v-if="t.transfer_id" class="hint" @click="unlink(t)" title="Umbuchung auflösen">✕</button>
          </td>
        </tr>
        <!-- v1.1: Splitbuchung & Tags (4.4) -->
        <tr v-if="openDetail === t.id">
          <td colspan="6" style="background: var(--bg)">
            <div class="form-row" style="margin-bottom: .25rem">
              <strong>Split:</strong>
              <template v-for="(row, i) in splitRows" :key="i">
                <select v-model="row.category_id">
                  <option value="" disabled>Kategorie…</option>
                  <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
                </select>
                <input type="number" step="0.01" v-model="row.amount" style="width: 6.5rem" />
              </template>
              <button @click="splitRows.push({ category_id: '', amount: '' })">+ Teil</button>
              <span class="hint" :class="Math.abs(splitSum() - Number(t.amount)) > 0.004 ? 'error' : ''">
                Summe {{ splitSum().toFixed(2) }} / {{ t.amount }}</span>
              <button class="primary" @click="saveSplits(t)">Split speichern</button>
              <button v-if="t.splits.length" @click="clearSplits(t)">Split entfernen</button>
            </div>
            <div class="form-row" style="margin-bottom: .25rem">
              <strong>Tags:</strong>
              <input v-model="tagInput" placeholder="z.B. Urlaub Norwegen 2026, Umzug" style="min-width: 20rem" />
              <button class="primary" @click="saveTags(t)">Tags speichern</button>
            </div>
            <p class="hint" style="margin: 0">
              Buchungs-ID {{ t.id }} – z.B. für manuelles Verknüpfen bei
              <router-link to="/wiederkehrend">Wiederkehrende Kostenpositionen</router-link>.</p>
          </td>
        </tr>
        </template>
      </tbody>
    </table>
    <div class="topbar" style="margin-top: .75rem">
      <span class="hint">{{ page.total }} Buchungen</span>
      <div class="spacer"></div>
      <button :disabled="offset === 0" @click="offset = Math.max(0, offset - limit); load()">‹ Zurück</button>
      <button :disabled="offset + limit >= page.total" @click="offset += limit; load()">Weiter ›</button>
    </div>
  </div>
</template>
