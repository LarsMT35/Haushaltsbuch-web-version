<script setup>
import { inject, onMounted, ref } from 'vue'
import { api, fmtAmount, fmtDate } from '../api.js'

const accounts = inject('accounts')
const categories = ref([])
const items = ref([])
const status = ref([])
const links = ref({}) // item_id -> links[]
const openLinks = ref(null)
const error = ref('')
const info = ref('')

const blank = () => ({ name: '', cycle_months: 12, expected_amount: '', paying_account_id: '',
                       category_id: null, match_text: '', reimbursement_account_id: null,
                       reimbursement_match_text: '', prefinance_note: '' })
const form = ref(blank())
const editing = ref(null)
const manualLink = ref({ transaction_id: '', role: 'charge' })

async function load() {
  categories.value = await api.get('/categories')
  items.value = await api.get('/recurring-items')
  status.value = (await api.get('/recurring-items/status')).rows
}
onMounted(load)

async function save() {
  error.value = ''
  try {
    const payload = { ...form.value,
      paying_account_id: form.value.paying_account_id || null,
      reimbursement_account_id: form.value.reimbursement_account_id || null,
      category_id: form.value.category_id || null,
      expected_amount: String(form.value.expected_amount || '0') }
    if (editing.value) await api.put(`/recurring-items/${editing.value}`, payload)
    else await api.post('/recurring-items', payload)
    form.value = blank(); editing.value = null
    await load()
  } catch (e) { error.value = e.message }
}

function edit(item) {
  editing.value = item.id
  form.value = { ...item, paying_account_id: item.paying_account_id || '',
                reimbursement_account_id: item.reimbursement_account_id || '' }
}

async function remove(item) {
  if (!confirm(`Position „${item.name}“ inkl. aller Verknüpfungen löschen?`)) return
  await api.del(`/recurring-items/${item.id}`)
  await load()
}

async function detectAll() {
  error.value = ''; info.value = ''
  try {
    const r = await api.post('/recurring-items/detect')
    info.value = `${r.charges_linked} Abbuchung(en), ${r.reimbursements_linked} Erstattung(en) neu verknüpft.`
    await load()
    if (openLinks.value) await loadLinks(openLinks.value)
  } catch (e) { error.value = e.message }
}

async function loadLinks(itemId) {
  openLinks.value = itemId
  links.value[itemId] = await api.get(`/recurring-items/${itemId}/links`)
}

async function addManualLink(item) {
  error.value = ''
  try {
    await api.post(`/recurring-items/${item.id}/links`, {
      transaction_id: Number(manualLink.value.transaction_id), role: manualLink.value.role })
    manualLink.value.transaction_id = ''
    await loadLinks(item.id)
    status.value = (await api.get('/recurring-items/status')).rows
  } catch (e) { error.value = e.message }
}

async function removeLink(item, link) {
  await api.del(`/recurring-items/links/${link.id}`)
  await loadLinks(item.id)
  status.value = (await api.get('/recurring-items/status')).rows
}

async function applyRate(row) {
  await api.put(`/recurring-items/${row.id}`, { current_rate: String(Math.round(row.suggested_rate * 100) / 100) })
  await load()
}

function accName(id) {
  return accounts.value.find((a) => a.id === id)?.name || '–'
}
function catName(id) {
  return categories.value.find((c) => c.id === id)?.name || '–'
}
</script>

<template>
  <div>
    <div class="topbar">
      <h1>Wiederkehrende Kostenpositionen</h1>
      <div class="spacer"></div>
      <button class="primary" @click="detectAll">Erkennung ausführen</button>
    </div>
    <p class="hint">z.B. ADAC (jährlich), Rundfunkbeitrag (quartalsweise), Abos (monatlich). Der
      Zahler ergibt sich automatisch aus dem Konto der erkannten Abbuchung (4.7 b).</p>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="info" class="hint">✓ {{ info }}</p>

    <!-- Ampel-Übersicht Soll/Ist (4.9) -->
    <div class="tile" style="margin-bottom: 1rem">
      <h3>Ampel-Übersicht Soll / Ist</h3>
      <table v-if="status.length">
        <thead><tr><th></th><th>Position</th><th>Letzte Abbuchung</th><th class="num">Ist</th>
          <th class="num">Soll (Erstattungen)</th><th class="num">Abweichung</th>
          <th>Fällig ca.</th><th></th></tr></thead>
        <tbody>
          <tr v-for="row in status" :key="row.id">
            <td><span class="ampel" :class="row.ampel"></span></td>
            <td>{{ row.name }}</td>
            <td>{{ fmtDate(row.last_charge_date) }}</td>
            <td class="num">{{ row.last_charge_amount != null ? fmtAmount(row.last_charge_amount) : '–' }}</td>
            <td class="num">{{ row.is_prefinanced ? (row.soll != null ? fmtAmount(row.soll) : '–') : '–' }}</td>
            <td class="num" :class="row.deviation && row.deviation > 0 ? 'neg' : ''">
              {{ row.deviation != null ? fmtAmount(row.deviation) : '–' }}</td>
            <td>{{ fmtDate(row.next_due_estimate) }}</td>
            <td>
              <button v-if="row.is_prefinanced && row.suggested_rate && row.ampel !== 'gruen'"
                      @click="applyRate(row)" title="Rate auf letzte Abbuchung ÷ Zyklus setzen">
                Rate auf {{ fmtAmount(row.suggested_rate) }}/Monat setzen
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="hint">Noch keine wiederkehrenden Positionen angelegt.</p>
    </div>

    <div class="tile" style="margin-bottom: 1rem">
      <h3>{{ editing ? 'Position bearbeiten' : 'Neue Position' }}</h3>
      <div class="form-row">
        <div><label>Name *</label><input v-model="form.name" placeholder="z.B. ADAC" /></div>
        <div><label>Zyklus (Monate)</label><input type="number" v-model.number="form.cycle_months" style="width: 5rem" /></div>
        <div><label>Erwarteter Betrag</label><input type="number" step="0.01" v-model="form.expected_amount" style="width: 7rem" /></div>
        <div><label>Zahlendes Konto</label>
          <select v-model="form.paying_account_id">
            <option value="">– wählen –</option>
            <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
          </select></div>
        <div><label>Kategorie</label>
          <select v-model="form.category_id">
            <option :value="null">–</option>
            <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select></div>
        <div><label>Erkennungstext (Abbuchung)</label>
          <input v-model="form.match_text" placeholder="Gegenpartei/Zweck enthält…" /></div>
      </div>
      <p class="hint">Vorfinanzierung (optional, 4.7 b): monatliche Erstattung über ein anderes
        Konto (z.B. gemeinsames Konto), die die Abbuchung anteilig vorstreckt.</p>
      <div class="form-row">
        <div><label>Vorfinanzierungskonto</label>
          <select v-model="form.reimbursement_account_id">
            <option :value="null">– keine Vorfinanzierung –</option>
            <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
          </select></div>
        <div><label>Erkennungstext (Erstattung)</label>
          <input v-model="form.reimbursement_match_text" placeholder="z.B. Erstattung Rundfunk" /></div>
        <div style="flex: 1; min-width: 12rem"><label>Notiz</label><input v-model="form.prefinance_note" /></div>
        <button class="primary" :disabled="!form.name" @click="save">{{ editing ? 'Speichern' : 'Anlegen' }}</button>
        <button v-if="editing" @click="editing = null; form = blank()">Abbrechen</button>
      </div>
    </div>

    <table>
      <thead><tr><th>Name</th><th>Zyklus</th><th>Konto</th><th>Vorfinanzierung</th>
        <th>Aktuelle Rate</th><th></th></tr></thead>
      <tbody>
        <template v-for="item in items" :key="item.id">
        <tr>
          <td>{{ item.name }} <span v-if="!item.active" class="badge gray">inaktiv</span></td>
          <td>alle {{ item.cycle_months }} Monat(e)</td>
          <td>{{ accName(item.paying_account_id) }}</td>
          <td>{{ item.reimbursement_account_id ? accName(item.reimbursement_account_id) : '–' }}</td>
          <td>{{ item.current_rate ? fmtAmount(item.current_rate) + '/Monat' : '–' }}</td>
          <td style="white-space: nowrap; text-align: right">
            <button @click="loadLinks(item.id)">{{ openLinks === item.id ? 'Verknüpfungen ▴' : 'Verknüpfungen ▾' }}</button>
            <button @click="edit(item)">Bearbeiten</button>
            <button @click="remove(item)">Löschen</button>
          </td>
        </tr>
        <tr v-if="openLinks === item.id">
          <td colspan="6" style="background: var(--bg)">
            <table v-if="links[item.id]?.length" style="margin-bottom: .5rem">
              <thead><tr><th>Rolle</th><th>Datum</th><th>Konto</th><th>Gegenpartei</th>
                <th class="num">Betrag</th><th></th></tr></thead>
              <tbody>
                <tr v-for="link in links[item.id]" :key="link.id">
                  <td><span class="badge" :class="link.role === 'reimbursement' ? 'gray' : ''">
                    {{ link.role === 'charge' ? 'Abbuchung' : 'Erstattung' }}</span>
                    <span v-if="!link.is_auto" class="hint">manuell</span></td>
                  <td>{{ fmtDate(link.transaction.booking_date) }}</td>
                  <td>{{ accName(link.transaction.account_id) }}</td>
                  <td>{{ link.transaction.counterparty }}</td>
                  <td class="num">{{ fmtAmount(link.transaction.amount) }}</td>
                  <td><button @click="removeLink(item, link)">✕ lösen</button></td>
                </tr>
              </tbody>
            </table>
            <p v-else class="hint">Noch keine Verknüpfungen.</p>
            <div class="form-row" style="margin-bottom: 0">
              <strong>Manuell verknüpfen:</strong>
              <input v-model="manualLink.transaction_id" placeholder="Buchungs-ID" style="width: 7rem" />
              <select v-model="manualLink.role">
                <option value="charge">als Abbuchung</option>
                <option value="reimbursement">als Erstattung</option>
              </select>
              <button class="primary" :disabled="!manualLink.transaction_id" @click="addManualLink(item)">Verknüpfen</button>
              <span class="hint">Buchungs-ID steht in der Buchungsliste beim Öffnen der Detailzeile nicht direkt –
                am einfachsten über die Erkennung automatisch verknüpfen lassen.</span>
            </div>
          </td>
        </tr>
        </template>
      </tbody>
    </table>
  </div>
</template>
