<script setup>
import { computed, inject, onMounted, ref } from 'vue'
import { api } from '../api.js'

const accounts = inject('accounts')
const user = inject('user')
const categories = ref([])
const error = ref('')
const form = ref({ name: '', scope: 'personal', account_id: null, parent_id: null,
                  is_fixed_cost: false, is_transfer_like: false })
const mergeSource = ref(null)
const mergeTarget = ref('')
const info = ref('')
const importInput = ref(null)

async function load() {
  categories.value = await api.get('/categories', { include_inactive: false })
}
onMounted(load)

// Export/Import als JSON (4.11) – für Backup oder Übertragung auf eine andere Installation
async function exportCategories() {
  const data = await api.get('/categories/export')
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `haushaltsbuch-kategorien-${new Date().toISOString().slice(0, 10)}.json`
  a.click()
  URL.revokeObjectURL(url)
}

async function importCategories(e) {
  const file = e.target.files?.[0]
  if (!file) return
  error.value = ''; info.value = ''
  try {
    const data = JSON.parse(await file.text())
    const res = await api.post('/categories/import', data)
    info.value = `${res.created} neu angelegt, ${res.updated_fixed_cost} Fixkosten-Flags aktualisiert ` +
      `(${res.skipped_existing} unverändert, ${res.skipped_no_permission} ohne Berechtigung, ` +
      `${res.skipped_no_account} mit unbekanntem Konto übersprungen).`
    await load()
  } catch (e) { error.value = e.message } finally { e.target.value = '' }
}

const groups = computed(() => ({
  'Global (alle Nutzer)': categories.value.filter((c) => c.scope === 'global'),
  'Kontobezogen (gemeinsame Konten)': categories.value.filter((c) => c.scope === 'account'),
  'Persönlich': categories.value.filter((c) => c.scope === 'personal'),
}))

async function create() {
  error.value = ''
  try {
    await api.post('/categories', { ...form.value,
      account_id: form.value.scope === 'account' ? form.value.account_id : null,
      parent_id: form.value.parent_id || null })
    form.value.name = ''
    await load()
  } catch (e) { error.value = e.message }
}

async function toggleFixed(cat) {
  error.value = ''
  try {
    await api.put(`/categories/${cat.id}`, { is_fixed_cost: !cat.is_fixed_cost })
    await load()
  } catch (e) { error.value = e.message }
}

async function toggleTransferLike(cat) {
  error.value = ''
  try {
    await api.put(`/categories/${cat.id}`, { is_transfer_like: !cat.is_transfer_like })
    await load()
  } catch (e) { error.value = e.message }
}

async function rename(cat) {
  const name = prompt('Neuer Name:', cat.name)
  if (!name || name === cat.name) return
  try {
    await api.put(`/categories/${cat.id}`, { name })
    await load()
  } catch (e) { error.value = e.message }
}

async function doMerge() {
  if (!mergeSource.value || !mergeTarget.value) return
  error.value = ''
  try {
    await api.post(`/categories/${mergeSource.value.id}/merge`,
                   { target_category_id: Number(mergeTarget.value) })
    mergeSource.value = null; mergeTarget.value = ''
    await load()
  } catch (e) { error.value = e.message }
}

function parentName(id) {
  const c = categories.value.find((c) => c.id === id)
  return c ? c.name : ''
}
</script>

<template>
  <div>
    <div class="topbar">
      <h1>Kategorien</h1>
      <div class="spacer"></div>
      <button @click="exportCategories">Export</button>
      <button @click="importInput.click()">Import</button>
      <input ref="importInput" type="file" accept="application/json" hidden @change="importCategories" />
    </div>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="info" class="hint">✓ {{ info }}</p>

    <div class="tile" style="margin-bottom: 1rem">
      <h3>Neue Kategorie</h3>
      <div class="form-row">
        <div><label>Name *</label><input v-model="form.name" /></div>
        <div><label>Geltungsbereich</label>
          <select v-model="form.scope">
            <option value="personal">persönlich</option>
            <option value="account">kontobezogen</option>
            <option value="global" v-if="user && user.is_admin">global</option>
          </select></div>
        <div v-if="form.scope === 'account'"><label>Konto</label>
          <select v-model="form.account_id">
            <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
          </select></div>
        <div><label>Oberkategorie</label>
          <select v-model="form.parent_id">
            <option :value="null">– keine –</option>
            <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select></div>
        <div><label>Fixkosten</label><input type="checkbox" v-model="form.is_fixed_cost" /></div>
        <div><label title="Zählt nicht als Einnahme/Ausgabe, sondern wie eine Sparkonten-Bewegung – z.B. für Sparplan-Ausführungen ohne mitgeführtes Depot-Konto">Wie Umbuchung behandeln</label>
          <input type="checkbox" v-model="form.is_transfer_like" /></div>
        <button class="primary" :disabled="!form.name" @click="create">Anlegen</button>
      </div>
    </div>

    <div v-if="mergeSource" class="tile warn" style="margin-bottom: 1rem">
      <h3>„{{ mergeSource.name }}“ zusammenführen mit …</h3>
      <p class="hint">Alle Buchungen und Regeln wandern zur Zielkategorie, die Quelle wird deaktiviert – kein Datenverlust (4.6).</p>
      <div class="form-row">
        <select v-model="mergeTarget">
          <option value="" disabled>Zielkategorie…</option>
          <option v-for="c in categories.filter((c) => c.id !== mergeSource.id)" :key="c.id" :value="c.id">{{ c.name }}</option>
        </select>
        <button class="primary" @click="doMerge">Zusammenführen</button>
        <button @click="mergeSource = null">Abbrechen</button>
      </div>
    </div>

    <div v-for="(items, title) in groups" :key="title" style="margin-bottom: 1.25rem">
      <h2>{{ title }}</h2>
      <table v-if="items.length">
        <tbody>
          <tr v-for="c in items" :key="c.id">
            <td>
              {{ c.name }}
              <span v-if="c.parent_id" class="hint">↳ unter {{ parentName(c.parent_id) }}</span>
              <span v-if="c.scope === 'account'" class="badge gray">
                {{ accounts.find((a) => a.id === c.account_id)?.name }}</span>
            </td>
            <td>
              <span v-if="c.is_fixed_cost" class="badge">fix</span>
              <span v-if="c.is_transfer_like" class="badge gray" title="Zählt wie eine Umbuchung, nicht als Ausgabe">wie Umbuchung</span>
            </td>
            <td style="text-align: right; white-space: nowrap">
              <button @click="toggleFixed(c)">{{ c.is_fixed_cost ? 'fix ✕' : 'als fix markieren' }}</button>
              <button @click="toggleTransferLike(c)">{{ c.is_transfer_like ? 'Umbuchung ✕' : 'wie Umbuchung' }}</button>
              <button @click="rename(c)">Umbenennen</button>
              <button @click="mergeSource = c">Zusammenführen</button>
            </td>
          </tr>
        </tbody>
      </table>
      <p v-else class="hint">Keine Kategorien.</p>
    </div>
  </div>
</template>
