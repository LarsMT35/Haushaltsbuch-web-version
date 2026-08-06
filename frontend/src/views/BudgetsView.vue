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
const info = ref('')

// Abrechnungsmonat (4.9): der angezeigte Zeitraum ist NICHT zwingend der
// Kalendermonat. Welcher gerade läuft, sagt das Backend – am 28. gehört man
// mit Starttag 27 schon in die nächste Periode, ein `new Date()` in
// JavaScript läge dann einen Monat daneben.
const period = ref(null)
const month = ref('')

const form = ref({ category_id: '', account_id: null, amount: '', valid_from: '' })
// Bearbeiten eines bestehenden Eintrags (Kopie, damit Abbrechen wirklich abbricht)
const editing = ref(null)

async function loadStatus() {
  status.value = await api.get('/budgets/status', month.value ? { month: month.value } : {})
  month.value = status.value.month
}

async function load() {
  categories.value = await api.get('/categories')
  budgets.value = await api.get('/budgets')
  thresholds.value = await api.get('/budgets/thresholds')
  period.value = await api.get('/budgets/period').catch(() => null)
  await loadStatus()
  if (!form.value.valid_from) {
    form.value.valid_from = status.value.date_from
  }
}
onMounted(load)
watch(month, loadStatus)

/** Reine Monatsarithmetik auf dem Periodenschlüssel – die Regel, WELCHE Tage
 *  dazugehören, bleibt im Backend. */
function shiftMonth(step) {
  const [y, m] = month.value.split('-').map(Number)
  const d = new Date(y, m - 1 + step, 1)
  month.value = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}
function currentPeriod() {
  if (period.value) month.value = period.value.current_period
}

async function create() {
  error.value = ''; info.value = ''
  try {
    await api.post('/budgets', { ...form.value, category_id: Number(form.value.category_id),
                                 account_id: form.value.account_id || null,
                                 amount: String(form.value.amount) })
    form.value.amount = ''
    await load()
    info.value = 'Budget angelegt.'
  } catch (e) { error.value = e.message }
}

function startEdit(b) {
  editing.value = { id: b.id, category_id: b.category_id, account_id: b.account_id,
                    amount: String(b.amount), valid_from: b.valid_from }
}
function cancelEdit() { editing.value = null }

async function saveEdit() {
  error.value = ''; info.value = ''
  try {
    await api.put(`/budgets/${editing.value.id}`, {
      category_id: Number(editing.value.category_id),
      account_id: editing.value.account_id || null,
      amount: String(editing.value.amount),
      valid_from: editing.value.valid_from,
    })
    editing.value = null
    await load()
    info.value = 'Budget geändert.'
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
    await loadStatus()
  } catch (e) { error.value = e.message }
}

function catName(id) {
  const c = categories.value.find((c) => c.id === id)
  return c ? c.name : `#${id}`
}
function accName(id) {
  return id ? (accounts.value.find((a) => a.id === id)?.name || `#${id}`) : 'alle'
}
const ampelColor = { gruen: 'var(--ampel-gruen)', gelb: 'var(--ampel-gelb)', rot: 'var(--ampel-rot)' }
</script>

<template>
  <div>
    <div class="topbar">
      <h1>Budgets</h1>
      <div class="spacer"></div>
      <div class="chips segmented">
        <button type="button" @click="shiftMonth(-1)"
                data-tip="Einen Abrechnungsmonat zurück. Jede Periode hat ihren eigenen Verbrauch – Budgets beginnen dort wieder bei 0." data-tip-pos="below">‹</button>
        <button type="button" @click="currentPeriod" :disabled="!period"
                data-tip="Zurück zum laufenden Abrechnungsmonat." data-tip-pos="below">Laufender Zeitraum</button>
        <button type="button" @click="shiftMonth(1)"
                data-tip="Einen Abrechnungsmonat vor – auch in die Zukunft, um zu sehen, welche Budgets dann gelten." data-tip-pos="below">›</button>
      </div>
      <input type="month" v-model="month" />
    </div>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="info" class="hint">✓ {{ info }}</p>

    <!-- Soll/Ist mit Ampel (4.8) – Ampelfarben sind fest, unabhängig vom Farbschema -->
    <div v-if="status" class="tile" style="margin-bottom: 1rem">
      <h3>Soll / Ist im Abrechnungsmonat {{ status.month }}
        <span class="hint">{{ fmtDate(status.date_from) }} – {{ fmtDate(status.date_to) }}</span>
      </h3>
      <p v-if="period && period.start_day > 1" class="hint" style="margin-top: -.3rem">
        Dein Abrechnungsmonat beginnt am {{ period.start_day }}. – der Verbrauch zählt genau
        diesen Zeitraum und beginnt in jeder Periode wieder bei 0.
      </p>
      <table v-if="status.rows.length">
        <thead><tr><th></th><th>Kategorie</th><th>Konto</th><th class="num">Budget</th>
          <th class="num">Ausgegeben</th><th class="num">Rest</th>
          <th style="width: 25%">Ausschöpfung</th></tr></thead>
        <tbody>
          <tr v-for="r in status.rows" :key="`${r.category_id}-${r.account_id}`">
            <td><span class="ampel" :class="r.ampel"></span></td>
            <td>{{ r.category_name }}</td>
            <td><span class="hint">{{ accName(r.account_id) }}</span></td>
            <td class="num">{{ fmtAmount(r.budget) }}</td>
            <td class="num" :class="r.ampel === 'rot' ? 'neg' : ''">{{ fmtAmount(r.spent) }}</td>
            <td class="num" :class="r.budget - r.spent < 0 ? 'neg' : 'pos'">
              {{ fmtAmount(r.budget - r.spent) }}</td>
            <td>
              <div class="budget-bar">
                <div :style="{ width: Math.min(100, r.percent) + '%', background: ampelColor[r.ampel] }"></div>
              </div>
              <span class="hint">{{ r.percent }} %</span>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="hint">Noch keine Budgets für diesen Abrechnungsmonat definiert.</p>
    </div>

    <div class="tile" style="margin-bottom: 1rem">
      <h3>Neues Budget (monatlich)</h3>
      <p class="hint">Ein monatliches Budget gilt <strong>je Abrechnungsmonat</strong> und beginnt in
        jedem neuen Zeitraum wieder bei 0 – es wandert also mit. Budgets gelten ab dem
        Gültigkeitsdatum; eine spätere Erhöhung ist ein neuer Eintrag und verändert die
        Vergangenheit nicht (4.8). Einen Vertipper korrigierst du dagegen direkt am Eintrag.</p>
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
          <template v-for="b in budgets" :key="b.id">
            <tr v-if="!editing || editing.id !== b.id">
              <td>{{ catName(b.category_id) }}</td>
              <td>{{ accName(b.account_id) }}</td>
              <td class="num">{{ fmtAmount(b.amount) }}</td>
              <td>{{ fmtDate(b.valid_from) }}</td>
              <td style="text-align: right">
                <button @click="startEdit(b)"
                        data-tip="Diesen Eintrag korrigieren (Betrag, Konto, Kategorie, Gültig ab). Für eine Änderung, die erst ab einem Datum gelten soll, lieber einen neuen Eintrag anlegen – dann bleibt die Vergangenheit unverändert."
                        data-tip-pos="left">Bearbeiten</button>
                <button style="margin-left: .3rem" @click="remove(b)"
                        data-tip="Eintrag endgültig entfernen – auch rückwirkend. Wenn das Budget nur künftig anders sein soll, stattdessen einen neuen Eintrag mit späterem „Gültig ab“ anlegen."
                        data-tip-pos="left">Löschen</button>
              </td>
            </tr>
            <tr v-else>
              <td>
                <select v-model="editing.category_id">
                  <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
                </select>
              </td>
              <td>
                <select v-model="editing.account_id">
                  <option :value="null">alle Konten</option>
                  <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
                </select>
              </td>
              <td class="num"><input type="number" step="0.01" v-model="editing.amount" style="width: 7rem" /></td>
              <td><input type="date" v-model="editing.valid_from" /></td>
              <td style="text-align: right">
                <button class="primary" @click="saveEdit">Speichern</button>
                <button style="margin-left: .3rem" @click="cancelEdit">Abbrechen</button>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
      <p v-if="!budgets.length" class="hint">Noch keine Budgets angelegt.</p>
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
