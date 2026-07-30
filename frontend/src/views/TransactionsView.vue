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
  unassigned: route.query.unassigned ? true : false,
})

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
        <tr v-for="t in page.items" :key="t.id" :class="t.transfer_id ? 'transfer' : ''">
          <td>{{ fmtDate(t.booking_date) }}</td>
          <td>{{ accounts.find((a) => a.id === t.account_id)?.name }}</td>
          <td>
            <strong>{{ t.counterparty }}</strong>
            <span v-if="t.is_manual" class="badge gray">manuell</span>
            <span v-if="t.transfer_id" class="badge gray">Umbuchung</span>
            <br /><span class="hint">{{ t.purpose }}</span>
          </td>
          <td>
            <!-- auffälliger Zuordnen-Hinweis statt stillem Verschwinden (4.9.1) -->
            <span v-if="!t.category_id && !t.transfer_id" class="badge warn">zuordnen ↓</span>
            <select :value="t.category_id ?? ''" @change="setCategory(t, $event.target.value)">
              <option value="">– keine –</option>
              <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
            <button v-if="t.category_id" title="Regel: künftig immer so" @click="makeRule(t)">↻ Regel</button>
          </td>
          <td class="num" :class="t.transfer_id ? '' : t.amount < 0 ? 'neg' : 'pos'">{{ fmtAmount(t.amount) }}</td>
          <td><button v-if="t.transfer_id" class="hint" @click="unlink(t)" title="Umbuchung auflösen">✕</button></td>
        </tr>
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
