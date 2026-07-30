<script setup>
import { inject, onMounted, ref } from 'vue'
import { api, fmtAmount, fmtDate } from '../api.js'

const accounts = inject('accounts')
const refreshAccounts = inject('refreshAccounts')
const profiles = ref([])
const batches = ref([])
const categories = ref([])
const file = ref(null)
const profileId = ref('')
const preview = ref(null)
const targetAccount = ref('')
const busy = ref(false)
const error = ref('')
const dragOver = ref(false)

// Mapping-Assistent (4.5)
const analyze = ref(null)
const newProfile = ref(null)
const FIELDS = [
  ['booking_date', 'Buchungstag *'], ['value_date', 'Valutadatum'], ['amount', 'Betrag *'],
  ['currency', 'Währung'], ['counterparty', 'Gegenpartei'], ['counterparty_iban', 'Gegen-IBAN'],
  ['purpose', 'Verwendungszweck'], ['booking_text', 'Buchungstext'], ['account_iban', 'Konto-IBAN'],
]

async function load() {
  profiles.value = await api.get('/imports/profiles')
  batches.value = await api.get('/imports/batches')
  categories.value = await api.get('/categories')
}
onMounted(load)

function pickFile(e) {
  const f = e.target.files?.[0] || e.dataTransfer?.files?.[0]
  if (f) { file.value = f; preview.value = null; analyze.value = null }
  dragOver.value = false
}

async function runPreview() {
  if (!file.value || !profileId.value) return
  busy.value = true; error.value = ''
  try {
    const form = new FormData()
    form.append('file', file.value)
    form.append('profile_id', profileId.value)
    preview.value = await api.postForm('/imports/preview', form)
    targetAccount.value = preview.value.suggested_account_id || ''
  } catch (e) { error.value = e.message } finally { busy.value = false }
}

async function runAnalyze() {
  if (!file.value) return
  busy.value = true; error.value = ''
  try {
    const form = new FormData()
    form.append('file', file.value)
    analyze.value = await api.postForm('/imports/analyze', form)
    newProfile.value = {
      name: '', delimiter: analyze.value.delimiter, encoding: analyze.value.encoding,
      skip_rows: analyze.value.skip_rows, header_signature: '', column_map: {},
      date_formats: ['%d.%m.%Y', '%d.%m.%y'], decimal_separator: ',',
      thousands_separator: '.', negate_amount: false, quotechar: '"',
    }
  } catch (e) { error.value = e.message } finally { busy.value = false }
}

async function saveProfile() {
  error.value = ''
  const map = {}
  for (const [field, col] of Object.entries(newProfile.value.column_map)) {
    if (col !== '') map[field] = col
  }
  if (map.booking_date === undefined || map.amount === undefined) {
    error.value = 'Mindestens Buchungstag und Betrag zuordnen'
    return
  }
  try {
    const created = await api.post('/imports/profiles', { ...newProfile.value, column_map: map })
    await load()
    profileId.value = created.id
    analyze.value = null
    error.value = ''
  } catch (e) { error.value = e.message }
}

async function commit() {
  if (!preview.value || !targetAccount.value) return
  busy.value = true; error.value = ''
  try {
    await api.post('/imports/commit', {
      profile_id: preview.value.profile_id, account_id: Number(targetAccount.value),
      filename: preview.value.filename, rows: preview.value.rows,
    })
    preview.value = null; file.value = null
    await load(); await refreshAccounts()
  } catch (e) { error.value = e.message } finally { busy.value = false }
}

async function rollback(batch) {
  if (!confirm(`Import "${batch.filename}" (${batch.num_transactions} Buchungen) komplett zurücknehmen?`)) return
  await api.del(`/imports/batches/${batch.id}`)
  await load(); await refreshAccounts()
}

function catName(id) {
  const c = categories.value.find((c) => c.id === id)
  return c ? c.name : ''
}
const includedCount = () => preview.value ? preview.value.rows.filter((r) => r.include).length : 0
</script>

<template>
  <div>
    <h1 style="margin-bottom: 1rem">CSV-Import</h1>

    <!-- Upload per Drag & Drop (4.5) -->
    <div class="dropzone" :class="{ over: dragOver }"
         @dragover.prevent="dragOver = true" @dragleave="dragOver = false"
         @drop.prevent="pickFile" @click="$refs.fileInput.click()">
      <template v-if="file">📄 {{ file.name }}</template>
      <template v-else>Bank-CSV hierher ziehen oder klicken</template>
      <input ref="fileInput" type="file" accept=".csv,text/csv" hidden @change="pickFile" />
    </div>

    <div class="form-row" style="margin-top: 1rem">
      <div><label>Importprofil</label>
        <select v-model="profileId">
          <option value="" disabled>Bank wählen…</option>
          <option v-for="p in profiles" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select></div>
      <button class="primary" :disabled="!file || !profileId || busy" @click="runPreview">Vorschau</button>
      <button :disabled="!file || busy" @click="runAnalyze">Unbekanntes Format? → Mapping-Assistent</button>
    </div>
    <p v-if="error" class="error">{{ error }}</p>

    <!-- Mapping-Assistent: Spalten zuordnen, als neues Profil speichern (4.5) -->
    <div v-if="analyze" class="tile" style="margin: 1rem 0">
      <h3>Mapping-Assistent</h3>
      <p class="hint">Erkannt: Trennzeichen „{{ analyze.delimiter }}“, Encoding {{ analyze.encoding }},
        {{ analyze.skip_rows }} Kopfzeile(n) übersprungen.</p>
      <div class="form-row">
        <div><label>Profilname *</label><input v-model="newProfile.name" placeholder="z.B. Volksbank" /></div>
        <div><label>Kopfzeilen überspringen</label><input type="number" v-model.number="newProfile.skip_rows" style="width: 5rem" /></div>
        <div><label>Vorzeichen umkehren</label><input type="checkbox" v-model="newProfile.negate_amount" /></div>
      </div>
      <div class="form-row">
        <div v-for="[field, label] in FIELDS" :key="field">
          <label>{{ label }}</label>
          <select v-model="newProfile.column_map[field]">
            <option value="">–</option>
            <option v-for="(h, i) in analyze.header" :key="i" :value="h">{{ h }}</option>
          </select>
        </div>
      </div>
      <table style="margin-bottom: .75rem">
        <thead><tr><th v-for="h in analyze.header" :key="h">{{ h }}</th></tr></thead>
        <tbody><tr v-for="(row, i) in analyze.sample_rows" :key="i">
          <td v-for="(cell, j) in row" :key="j">{{ cell }}</td></tr></tbody>
      </table>
      <button class="primary" @click="saveProfile">Profil speichern</button>
    </div>

    <!-- Vorschau vor Übernahme (4.5) -->
    <div v-if="preview" class="tile" style="margin: 1rem 0">
      <h3>Vorschau: {{ preview.filename }}</h3>
      <div class="form-row">
        <div><label>Zielkonto {{ preview.suggested_account_id ? '(automatisch erkannt)' : '' }}</label>
          <select v-model="targetAccount">
            <option value="" disabled>Konto wählen…</option>
            <option v-for="a in accounts.filter((a) => a.my_role !== 'reader')" :key="a.id" :value="a.id">
              {{ a.name }} ({{ a.iban || 'ohne IBAN' }})
            </option>
          </select></div>
        <button class="primary" :disabled="!targetAccount || busy" @click="commit">
          {{ includedCount() }} Buchungen übernehmen
        </button>
      </div>
      <table>
        <thead><tr><th></th><th>Datum</th><th>Gegenpartei</th><th>Zweck</th>
          <th>Kategorie (Regel)</th><th class="num">Betrag</th><th>Status</th></tr></thead>
        <tbody>
          <tr v-for="r in preview.rows" :key="r.row_number">
            <td><input type="checkbox" v-model="r.include" :disabled="!!r.error" /></td>
            <td>{{ fmtDate(r.booking_date) }}</td>
            <td>{{ r.counterparty }}</td>
            <td class="hint">{{ r.purpose }}</td>
            <td>{{ catName(r.suggested_category_id) || '–' }}</td>
            <td class="num" :class="r.amount < 0 ? 'neg' : 'pos'">{{ r.amount != null ? fmtAmount(r.amount) : '' }}</td>
            <td>
              <span v-if="r.error" class="badge warn" :title="r.error">Fehler</span>
              <span v-else-if="r.duplicate === 'duplicate'" class="badge gray">Duplikat</span>
              <span v-else-if="r.duplicate === 'suspect'" class="badge warn">Duplikat? bitte prüfen</span>
              <span v-else class="badge">neu</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Import-Vorgänge: protokolliert & rückrollbar (Prinzip 7) -->
    <h2>Bisherige Importe</h2>
    <table>
      <thead><tr><th>Datum</th><th>Datei</th><th>Profil</th><th class="num">Buchungen</th><th></th></tr></thead>
      <tbody>
        <tr v-for="b in batches" :key="b.id">
          <td>{{ new Date(b.created_at).toLocaleString('de-DE') }}</td>
          <td>{{ b.filename }} <span v-if="b.reverted" class="badge gray">zurückgenommen</span></td>
          <td>{{ profiles.find((p) => p.id === b.profile_id)?.name }}</td>
          <td class="num">{{ b.num_transactions }}</td>
          <td><button v-if="!b.reverted" @click="rollback(b)">Rückgängig</button></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
