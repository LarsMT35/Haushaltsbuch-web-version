<script setup>
import { inject, onMounted, ref } from 'vue'
import { api, fmtAmount, fmtDate } from '../api.js'

const user = inject('user')
const settings = inject('settings')
const accounts = inject('accounts')
const refreshAccounts = inject('refreshAccounts')
const error = ref('')
const info = ref('')

// Konto anlegen (4.2)
const accountForm = ref({ name: '', type: 'giro', bank: '', iban: '',
                          opening_balance: '0', opening_balance_date: '', is_household: false })
// Rollen (4.1)
const users = ref([])
const roleForm = ref({ account_id: '', user_id: '', role: 'reader' })
// Benutzerverwaltung (Admin)
const userForm = ref({ username: '', password: '', display_name: '', is_admin: false })
const pwForm = ref({ old_password: '', new_password: '' })

// Saldo-Abgleich gegen Bank (4.2)
const balanceCheckAccount = ref('')
const balanceCheck = ref(null)
const balanceCheckBusy = ref(false)

onMounted(async () => {
  if (user.value?.is_admin) users.value = await api.get('/users')
})

async function runBalanceCheck() {
  if (!balanceCheckAccount.value) return
  balanceCheckBusy.value = true
  error.value = ''
  try {
    balanceCheck.value = await api.get(`/accounts/${balanceCheckAccount.value}/balance-check`)
  } catch (e) { error.value = e.message } finally { balanceCheckBusy.value = false }
}

async function saveSettings() {
  await api.put('/auth/settings', { color_scheme: settings.value.color_scheme,
                                    dark_mode: settings.value.dark_mode })
}

async function createAccount() {
  error.value = ''
  try {
    await api.post('/accounts', { ...accountForm.value,
      opening_balance: String(accountForm.value.opening_balance || '0'),
      opening_balance_date: accountForm.value.opening_balance_date || null })
    accountForm.value.name = ''; accountForm.value.iban = ''
    await refreshAccounts()
    info.value = 'Konto angelegt.'
  } catch (e) { error.value = e.message }
}

async function archive(a) {
  const res = await api.del(`/accounts/${a.id}`)
  info.value = `Konto archiviert (${res.transactions_affected} Buchungen bleiben erhalten).`
  await refreshAccounts()
}

// Haushalts- vs. Privatkonto: steuert die Trennung des Dashboards (4.9.1)
async function toggleHousehold(a) {
  error.value = ''
  try {
    await api.put(`/accounts/${a.id}`, { is_household: !a.is_household })
    await refreshAccounts()
  } catch (e) { error.value = e.message }
}

async function assignRole() {
  error.value = ''
  try {
    await api.put(`/accounts/${roleForm.value.account_id}/roles`,
                  { user_id: Number(roleForm.value.user_id), role: roleForm.value.role })
    info.value = 'Rolle gespeichert.'
    await refreshAccounts()
  } catch (e) { error.value = e.message }
}

async function createUser() {
  error.value = ''
  try {
    await api.post('/users', userForm.value)
    users.value = await api.get('/users')
    userForm.value = { username: '', password: '', display_name: '', is_admin: false }
    info.value = 'Benutzer angelegt.'
  } catch (e) { error.value = e.message }
}

async function toggleUser(u) {
  await api.put(`/users/${u.id}`, { is_active: !u.is_active })
  users.value = await api.get('/users')
}

async function changePassword() {
  error.value = ''; info.value = ''
  try {
    await api.post('/auth/change-password', pwForm.value)
    info.value = 'Passwort geändert.'
    pwForm.value = { old_password: '', new_password: '' }
  } catch (e) { error.value = e.message }
}
</script>

<template>
  <div>
    <h1 style="margin-bottom: 1rem">Einstellungen</h1>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="info" class="hint">✓ {{ info }}</p>

    <div class="grid">
      <!-- Design pro Nutzer (4.10); Ampel-/Warnfarben bleiben immer gleich -->
      <div class="tile">
        <h3>Darstellung</h3>
        <div class="form-row">
          <div><label>Farbschema</label>
            <select v-model="settings.color_scheme" @change="saveSettings">
              <option value="hell">Hell & sachlich</option>
              <option value="ruhig">Ruhig (grün)</option>
              <option value="warm">Warm</option>
            </select></div>
          <div><label>Dunkles Design</label>
            <input type="checkbox" v-model="settings.dark_mode" @change="saveSettings" /></div>
        </div>
        <p class="hint">Budget-Ampel und Warnfarben ändern sich bewusst nicht mit dem Schema.</p>
      </div>

      <div class="tile">
        <h3>Passwort ändern</h3>
        <div class="form-row">
          <div><label>Aktuell</label><input type="password" v-model="pwForm.old_password" /></div>
          <div><label>Neu</label><input type="password" v-model="pwForm.new_password" /></div>
          <button class="primary" @click="changePassword">Ändern</button>
        </div>
      </div>

      <div class="tile wide">
        <h3>Neues Konto</h3>
        <div class="form-row">
          <div><label>Name *</label><input v-model="accountForm.name" /></div>
          <div><label>Typ</label>
            <select v-model="accountForm.type">
              <option value="giro">Giro</option><option value="tagesgeld">Tagesgeld</option>
              <option value="sparbuch">Sparbuch</option><option value="depot">Depot</option>
              <option value="bargeld">Bargeld</option><option value="kreditkarte">Kreditkarte</option>
            </select></div>
          <div><label>Bank</label><input v-model="accountForm.bank" /></div>
          <div><label>IBAN</label><input v-model="accountForm.iban" placeholder="für Auto-Erkennung & Umbuchungen" /></div>
          <div><label>Anfangssaldo *</label><input type="number" step="0.01" v-model="accountForm.opening_balance" /></div>
          <div><label>Saldo-Stichtag</label><input type="date" v-model="accountForm.opening_balance_date" /></div>
          <div><label title="Zählt im Dashboard zum Bereich „Gemeinsam“ statt „Persönlich“">Haushaltskonto</label>
            <input type="checkbox" v-model="accountForm.is_household" /></div>
          <button class="primary" :disabled="!accountForm.name" @click="createAccount">Anlegen</button>
        </div>
        <p class="hint">Ohne Anfangssaldo zum Startdatum wäre jeder berechnete Kontostand falsch (4.2).
          Tipp: Bargeld als eigenes Konto führen, Abhebung = Umbuchung.<br />
          <strong>Haushaltskonto</strong> trennt das Dashboard in „Gemeinsam“ und „Persönlich“ – unabhängig davon,
          wer Zugriff hat. Wer nur Zugriff auf Haushaltskonten hat, sieht ausschließlich diesen Bereich.</p>
        <table>
          <tbody>
            <tr v-for="a in accounts" :key="a.id">
              <td>{{ a.name }} <span class="hint">{{ a.type }}</span>
                <span v-if="a.is_household" class="badge">Haushalt</span>
                <span v-if="a.shared" class="badge gray">geteilt</span></td>
              <td class="hint">{{ a.iban }}</td>
              <td>{{ a.my_role }}</td>
              <td style="text-align: right; white-space: nowrap">
                <button v-if="a.my_role === 'owner'" @click="toggleHousehold(a)">
                  {{ a.is_household ? 'Haushalt ✕' : 'als Haushaltskonto' }}</button>
                <button v-if="a.my_role === 'owner'" @click="archive(a)">Archivieren</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="tile wide">
        <h3>Saldo-Abgleich gegen Bank</h3>
        <p class="hint">Wo eine Bank einen laufenden Saldo mitliefert (z.B. ING), wird der
          berechnete Kontostand dagegen geprüft – Abweichungen erkennen fehlende Importe oder
          Lücken (4.2).</p>
        <div class="form-row">
          <select v-model="balanceCheckAccount">
            <option value="" disabled>Konto wählen…</option>
            <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
          </select>
          <button class="primary" :disabled="!balanceCheckAccount || balanceCheckBusy" @click="runBalanceCheck">Prüfen</button>
        </div>
        <div v-if="balanceCheck">
          <p v-if="!balanceCheck.checked_count" class="hint">
            Diese Bank liefert in den importierten Buchungen keinen Saldo mit – Abgleich nicht möglich.</p>
          <p v-else-if="!balanceCheck.rows.length" class="hint">
            ✓ Alle {{ balanceCheck.checked_count }} geprüften Salden stimmen überein.</p>
          <table v-else>
            <thead><tr><th>Datum</th><th>Gegenpartei</th><th class="num">Berechnet</th>
              <th class="num">Bank-Saldo</th><th class="num">Abweichung</th></tr></thead>
            <tbody>
              <tr v-for="r in balanceCheck.rows" :key="r.transaction_id">
                <td>{{ fmtDate(r.booking_date) }}</td>
                <td>{{ r.counterparty }}</td>
                <td class="num">{{ fmtAmount(r.computed_balance) }}</td>
                <td class="num">{{ fmtAmount(r.bank_balance) }}</td>
                <td class="num neg">{{ fmtAmount(r.deviation) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="user && user.is_admin" class="tile wide">
        <h3>Benutzerverwaltung (Admin)</h3>
        <div class="form-row">
          <div><label>Benutzername *</label><input v-model="userForm.username" /></div>
          <div><label>Anzeigename *</label><input v-model="userForm.display_name" /></div>
          <div><label>Passwort *</label><input type="password" v-model="userForm.password" /></div>
          <div><label>Admin</label><input type="checkbox" v-model="userForm.is_admin" /></div>
          <button class="primary" :disabled="!userForm.username || !userForm.password" @click="createUser">Anlegen</button>
        </div>
        <table>
          <tbody>
            <tr v-for="u in users" :key="u.id">
              <td>{{ u.display_name }} <span class="hint">({{ u.username }})</span>
                <span v-if="u.is_admin" class="badge">Admin</span>
                <span v-if="!u.is_active" class="badge gray">deaktiviert</span></td>
              <td style="text-align: right">
                <button v-if="u.id !== user.id" @click="toggleUser(u)">
                  {{ u.is_active ? 'Deaktivieren' : 'Aktivieren' }}</button>
              </td>
            </tr>
          </tbody>
        </table>

        <h3 style="margin-top: 1rem">Kontorechte vergeben (Rollenmodell 4.1)</h3>
        <div class="form-row">
          <div><label>Konto</label>
            <select v-model="roleForm.account_id">
              <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
            </select></div>
          <div><label>Benutzer</label>
            <select v-model="roleForm.user_id">
              <option v-for="u in users" :key="u.id" :value="u.id">{{ u.display_name }}</option>
            </select></div>
          <div><label>Rolle</label>
            <select v-model="roleForm.role">
              <option value="owner">Eigentümer</option>
              <option value="editor">Bearbeiter</option>
              <option value="reader">Leser</option>
              <option value="none">entfernen</option>
            </select></div>
          <button class="primary" :disabled="!roleForm.account_id || !roleForm.user_id" @click="assignRole">Speichern</button>
        </div>
      </div>
    </div>
  </div>
</template>
