<script setup>
import { inject, onMounted, ref, watch } from 'vue'
import { api } from '../api.js'

const accounts = inject('accounts')
const rules = ref([])
const categories = ref([])
const error = ref('')
const info = ref('')
// Freitextsuche: bei gewachsenen Regelbeständen sonst nicht mehr auffindbar
const search = ref('')
const blank = () => ({ name: '', category_id: '', priority: 100, text_contains: '',
                       counterparty_contains: '', iban_equals: '', booking_text_contains: '',
                       amount_min: null, amount_max: null, account_id: null, active: true })
const form = ref(blank())
const editing = ref(null)
const importInput = ref(null)

async function load() {
  rules.value = await api.get('/rules', search.value ? { q: search.value } : {})
  categories.value = await api.get('/categories')
}
onMounted(load)

// Tippen nicht bei jedem Anschlag ans Backend schicken
let searchTimer = null
watch(search, () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(load, 250)
})

async function save() {
  error.value = ''
  try {
    const payload = { ...form.value, category_id: Number(form.value.category_id),
                      account_id: form.value.account_id || null,
                      amount_min: form.value.amount_min || null,
                      amount_max: form.value.amount_max || null }
    if (editing.value) await api.put(`/rules/${editing.value}`, payload)
    else await api.post('/rules', payload)
    form.value = blank(); editing.value = null
    await load()
  } catch (e) { error.value = e.message }
}

function edit(rule) {
  editing.value = rule.id
  form.value = { ...rule }
}

async function remove(rule) {
  if (!confirm(`Regel „${rule.name}“ löschen?`)) return
  await api.del(`/rules/${rule.id}`)
  await load()
}

async function reapply(onlyUnassigned) {
  error.value = ''; info.value = ''
  try {
    const res = await api.post(`/rules/reapply?only_unassigned=${onlyUnassigned}`)
    info.value = `${res.changed} Buchungen neu kategorisiert.`
  } catch (e) { error.value = e.message }
}

function catName(id) {
  const c = categories.value.find((c) => c.id === id)
  return c ? c.name : ''
}

// Export/Import als JSON (4.11) – für Backup oder Übertragung auf eine andere Installation
async function exportRules() {
  const data = await api.get('/rules/export')
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `haushaltsbuch-regeln-${new Date().toISOString().slice(0, 10)}.json`
  a.click()
  URL.revokeObjectURL(url)
}

async function importRules(e) {
  const file = e.target.files?.[0]
  if (!file) return
  error.value = ''; info.value = ''
  try {
    const data = JSON.parse(await file.text())
    const res = await api.post('/rules/import', data)
    info.value = `${res.created} neue Regeln importiert ` +
      `(${res.skipped_duplicate} bereits vorhanden, ${res.skipped_no_category} ohne passende Kategorie übersprungen).`
    await load()
  } catch (e) { error.value = e.message } finally { e.target.value = '' }
}
</script>

<template>
  <div>
    <div class="sticky-top">
      <div class="topbar">
        <h1>Kategorisierungsregeln</h1>
        <!-- Freitextsuche über Name, alle Textkriterien und Zielkategorie (4.6) -->
        <input v-model="search" placeholder="🔍 Regel, Händler, IBAN oder Kategorie…"
               style="min-width: 18rem" />
        <button v-if="search" @click="search = ''" title="Suche zurücksetzen">✕</button>
        <div class="spacer"></div>
        <!-- rückwirkende Neuanwendung dank aufbewahrter Rohdaten (4.6, Prinzip 2) -->
        <button @click="reapply(true)">Auf nicht zugeordnete anwenden</button>
        <button @click="reapply(false)">Auf ALLE rückwirkend anwenden</button>
        <button @click="exportRules">Export</button>
        <button @click="importInput.click()">Import</button>
        <input ref="importInput" type="file" accept="application/json" hidden @change="importRules" />
      </div>
      <p class="hint" style="margin: 0 0 .5rem">
        <template v-if="search"><strong>{{ rules.length }}</strong> Treffer für „{{ search }}“ –
          gesucht wird in Name, allen Textkriterien und der Zielkategorie.</template>
        <template v-else>{{ rules.length }} Regeln. Kriterien einer Regel sind UND-verknüpft.
          Bei mehreren Treffern gewinnt die kleinste Prioritätszahl (4.6).</template></p>
      <p v-if="error" class="error" style="margin: 0 0 .5rem">{{ error }}</p>
      <p v-if="info" class="hint" style="margin: 0 0 .5rem">✓ {{ info }}</p>

      <div class="tile" style="margin-bottom: 0">
        <h3>{{ editing ? 'Regel bearbeiten' : 'Neue Regel' }}</h3>
        <div class="form-row" style="margin-bottom: 0">
          <div><label>Name *</label><input v-model="form.name" /></div>
          <div><label>Kategorie *</label>
            <select v-model="form.category_id">
              <option value="" disabled>wählen…</option>
              <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select></div>
          <div><label>Priorität</label><input type="number" v-model.number="form.priority" style="width: 5rem" /></div>
          <div><label>Verwendungszweck enthält</label><input v-model="form.text_contains" /></div>
          <div><label>Gegenpartei enthält</label><input v-model="form.counterparty_contains" /></div>
          <div><label>Gegen-IBAN ist</label><input v-model="form.iban_equals" /></div>
          <div><label>Buchungstext enthält</label><input v-model="form.booking_text_contains" /></div>
          <div><label>Betrag von</label><input type="number" step="0.01" v-model="form.amount_min" style="width: 6rem" /></div>
          <div><label>Betrag bis</label><input type="number" step="0.01" v-model="form.amount_max" style="width: 6rem" /></div>
          <div><label>Nur Konto</label>
            <select v-model="form.account_id">
              <option :value="null">alle</option>
              <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
            </select></div>
          <button class="primary" :disabled="!form.name || !form.category_id" @click="save">
            {{ editing ? 'Speichern' : 'Anlegen' }}</button>
          <button v-if="editing" @click="editing = null; form = blank()">Abbrechen</button>
        </div>
      </div>
    </div>

    <table>
      <thead><tr><th class="num">Prio</th><th>Name</th><th>Kriterien</th><th>→ Kategorie</th><th></th></tr></thead>
      <tbody>
        <tr v-for="r in rules" :key="r.id">
          <td class="num">{{ r.priority }}</td>
          <td>{{ r.name }} <span v-if="!r.active" class="badge gray">inaktiv</span></td>
          <td class="hint">
            <span v-if="r.text_contains">Zweck ~ „{{ r.text_contains }}“ </span>
            <span v-if="r.counterparty_contains">Gegenpartei ~ „{{ r.counterparty_contains }}“ </span>
            <span v-if="r.iban_equals">IBAN = {{ r.iban_equals }} </span>
            <span v-if="r.booking_text_contains">Buchungstext ~ „{{ r.booking_text_contains }}“ </span>
            <span v-if="r.amount_min != null">≥ {{ r.amount_min }} </span>
            <span v-if="r.amount_max != null">≤ {{ r.amount_max }} </span>
            <span v-if="r.account_id">nur {{ accounts.find((a) => a.id === r.account_id)?.name }}</span>
          </td>
          <td>{{ catName(r.category_id) }}</td>
          <td style="white-space: nowrap; text-align: right">
            <button @click="edit(r)">Bearbeiten</button>
            <button @click="remove(r)">Löschen</button>
          </td>
        </tr>
        <tr v-if="!rules.length">
          <td colspan="5" class="hint" style="text-align: center; padding: 1.5rem">
            Keine Regel gefunden<span v-if="search"> für „{{ search }}“</span>.
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
