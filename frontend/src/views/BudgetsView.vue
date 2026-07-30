<script setup>
import { inject, onMounted, ref, watch } from 'vue'
import { api, fmtAmount, fmtDate } from '../api.js'

const accounts = inject('accounts')
const user = inject('user')
const categories = ref([])
const budgets = ref([])
const status = ref(null)
const thresholds = ref({ green_below: 80, red_from: 98 })
const error = ref('')
const month = ref(new Date().toISOString().slice(0, 7))
const form = ref({ category_id: '', account_id: null, amount: '',
                   valid_from: new Date().toISOString().slice(0, 8) + '01' })

async function load() {
  categories.value = await api.get('/categories')
  budgets.value = await api.get('/budgets')
  thresholds.value = await api.get('/budgets/thresholds')
  status.value = await api.get('/budgets/status', { month: month.value })
}
onMounted(load)
watch(month, async () => { status.value = await api.get('/budgets/status', { month: month.value }) })

async function create() {
  error.value = ''
  try {
    await api.post('/budgets', { ...form.value, category_id: Number(form.value.category_id),
                                 account_id: form.value.account_id || null,
                                 amount: String(form.value.amount) })
    form.value.amount = ''
    await load()
  } catch (e) { error.value = e.message }
}

async function remove(b) {
  if (!confirm('Budget-Eintrag löschen?')) return
  await api.del(`/budgets/${b.id}`)
  await load()
}

async function saveThresholds() {
  error.value = ''
  try {
    thresholds.value = await api.put('/budgets/thresholds', thresholds.value)
    status.value = await api.get('/budgets/status', { month: month.value })
  } catch (e) { error.value = e.message }
}

function catName(id) {
  const c = categories.value.find((c) => c.id === id)
  return c ? c.name : `#${id}`
}
const ampelColor = { gruen: 'var(--ampel-gruen)', gelb: 'var(--ampel-gelb)', rot: 'var(--ampel-rot)' }
</script>

<template>
  <div>
    <div class="topbar">
      <h1>Budgets</h1>
      <div class="spacer"></div>
      <input type="month" v-model="month" />
    </div>
    <p v-if="error" class="error">{{ error }}</p>

    <!-- Soll/Ist mit Ampel (4.8) – Ampelfarben sind fest, unabhängig vom Farbschema -->
    <div v-if="status" class="tile" style="margin-bottom: 1rem">
      <h3>Soll / Ist im {{ status.month }}</h3>
      <table v-if="status.rows.length">
        <thead><tr><th></th><th>Kategorie</th><th class="num">Budget</th><th class="num">Ausgegeben</th>
          <th style="width: 30%">Ausschöpfung</th></tr></thead>
        <tbody>
          <tr v-for="r in status.rows" :key="r.category_id">
            <td><span class="ampel" :class="r.ampel"></span></td>
            <td>{{ r.category_name }}</td>
            <td class="num">{{ fmtAmount(r.budget) }}</td>
            <td class="num" :class="r.ampel === 'rot' ? 'neg' : ''">{{ fmtAmount(r.spent) }}</td>
            <td>
              <div class="budget-bar">
                <div :style="{ width: Math.min(100, r.percent) + '%', background: ampelColor[r.ampel] }"></div>
              </div>
              <span class="hint">{{ r.percent }} %</span>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="hint">Noch keine Budgets für diesen Monat definiert.</p>
    </div>

    <div class="tile" style="margin-bottom: 1rem">
      <h3>Neues Budget (monatlich)</h3>
      <p class="hint">Budgets gelten ab dem Gültigkeitsdatum – eine spätere Erhöhung ist ein neuer
        Eintrag und verändert die Vergangenheit nicht (4.8).</p>
      <div class="form-row">
        <div><label>Kategorie *</label>
          <select v-model="form.category_id">
            <option value="" disabled>wählen…</option>
            <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select></div>
        <div><label>Konto (leer = alle)</label>
          <select v-model="form.account_id">
            <option :value="null">alle Konten</option>
            <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
          </select></div>
        <div><label>Betrag/Monat *</label><input type="number" step="0.01" v-model="form.amount" /></div>
        <div><label>Gültig ab</label><input type="date" v-model="form.valid_from" /></div>
        <button class="primary" :disabled="!form.category_id || !form.amount" @click="create">Anlegen</button>
      </div>
    </div>

    <div class="tile" style="margin-bottom: 1rem">
      <h3>Alle Budget-Einträge (versioniert)</h3>
      <table>
        <thead><tr><th>Kategorie</th><th>Konto</th><th class="num">Betrag</th><th>Gültig ab</th><th></th></tr></thead>
        <tbody>
          <tr v-for="b in budgets" :key="b.id">
            <td>{{ catName(b.category_id) }}</td>
            <td>{{ b.account_id ? accounts.find((a) => a.id === b.account_id)?.name : 'alle' }}</td>
            <td class="num">{{ fmtAmount(b.amount) }}</td>
            <td>{{ fmtDate(b.valid_from) }}</td>
            <td style="text-align: right"><button @click="remove(b)">Löschen</button></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="user && user.is_admin" class="tile">
      <h3>Ampel-Schwellwerte (konfigurierbar, 4.8)</h3>
      <div class="form-row">
        <div><label>grün unter (%)</label>
          <input type="number" v-model.number="thresholds.green_below" style="width: 5rem" /></div>
        <div><label>rot ab (%)</label>
          <input type="number" v-model.number="thresholds.red_from" style="width: 5rem" /></div>
        <button class="primary" @click="saveThresholds">Speichern</button>
      </div>
      <p class="hint">Dazwischen: gelb. Standard: grün &lt; 80 %, gelb 80–97 %, rot ≥ 98 %.</p>
    </div>
  </div>
</template>
