<script setup>
import { computed, onMounted, provide, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, fmtAmount, getToken, setToken } from './api.js'

const route = useRoute()
const router = useRouter()
const user = ref(null)
const settings = ref({ color_scheme: 'hell', dark_mode: false })
const accounts = ref([])
const loggedIn = computed(() => route.path !== '/login')

async function loadSession() {
  if (!getToken()) return
  try {
    user.value = await api.get('/auth/me')
    settings.value = await api.get('/auth/settings')
    accounts.value = await api.get('/accounts')
  } catch { /* 401 → Login-Redirect übernimmt api.js */ }
}

function applyTheme() {
  document.documentElement.dataset.scheme = settings.value.color_scheme || 'hell'
  document.documentElement.dataset.dark = settings.value.dark_mode ? 'true' : 'false'
}
watch(settings, applyTheme, { deep: true })
watch(() => route.path, () => { if (loggedIn.value && !user.value) loadSession() })
onMounted(loadSession)

async function refreshAccounts() {
  if (getToken()) accounts.value = await api.get('/accounts')
}
provide('accounts', accounts)
provide('refreshAccounts', refreshAccounts)
provide('user', user)
provide('settings', settings)
provide('reloadSession', loadSession)

function logout() {
  setToken(null)
  user.value = null
  router.push('/login')
}

// Trennung nach dem expliziten Haushalts-Flag, nicht nach der Zahl der
// Zugriffsberechtigten – dieselbe Einteilung wie im Dashboard (4.9.1)
// Auf schmalen Geräten ist die Seitenleiste eingeklappt – ohne Umschalter
// gäbe es dort gar keine Navigation mehr (4.9: mobiltauglich)
const navOpen = ref(false)
watch(() => route.path, () => { navOpen.value = false })

const personal = computed(() => accounts.value.filter((a) => !a.is_household))
const household = computed(() => accounts.value.filter((a) => a.is_household))
const totalBalance = computed(() =>
  accounts.value.reduce((sum, a) => sum + Number(a.balance || 0), 0))
</script>

<template>
  <div v-if="!loggedIn"><router-view @logged-in="loadSession" /></div>
  <div v-else class="layout" :class="{ 'nav-open': navOpen }">
    <!-- Abdunkeln hinter der ausgeklappten Navigation, Klick schließt sie -->
    <div class="nav-backdrop" @click="navOpen = false"></div>
    <aside class="sidebar">
      <h1 style="margin-bottom: 1rem">💰 Haushaltsbuch</h1>
      <nav class="nav">
        <router-link to="/">Dashboard</router-link>
        <router-link to="/buchungen">Buchungen</router-link>
        <router-link to="/import">Import</router-link>
        <router-link to="/budgets">Budgets</router-link>
        <router-link to="/kategorien">Kategorien</router-link>
        <router-link to="/regeln">Regeln</router-link>
        <router-link to="/wiederkehrend">Wiederkehrend</router-link>
      </nav>
      <!-- Kontenliste dauerhaft sichtbar, persönlich/gemeinsam getrennt (4.9.1) -->
      <template v-if="household.length">
        <h2 style="color: var(--muted); font-size: .8rem; text-transform: uppercase">Gemeinsame Konten</h2>
        <div v-for="a in household" :key="a.id" class="account-item"
             @click="$router.push({ path: '/buchungen', query: { account_id: a.id } })">
          <span>{{ a.name }}
            <span v-if="a.my_role === 'reader'" class="badge gray">Leser</span></span>
          <span class="bal" :class="a.balance < 0 ? 'neg' : ''">{{ fmtAmount(a.balance) }}</span>
        </div>
      </template>
      <template v-if="personal.length">
        <h2 style="color: var(--muted); font-size: .8rem; text-transform: uppercase">Meine Konten</h2>
        <div v-for="a in personal" :key="a.id" class="account-item"
             @click="$router.push({ path: '/buchungen', query: { account_id: a.id } })">
          <span>{{ a.name }}
            <span v-if="a.shared" class="badge gray">geteilt</span></span>
          <span class="bal" :class="a.balance < 0 ? 'neg' : ''">{{ fmtAmount(a.balance) }}</span>
        </div>
      </template>
      <div v-if="accounts.length" class="account-item account-total">
        <span>Gesamt</span>
        <span class="bal" :class="totalBalance < 0 ? 'neg' : ''">{{ fmtAmount(totalBalance) }}</span>
      </div>
    </aside>
    <main class="main">
      <div class="topbar">
        <button class="nav-toggle" aria-label="Menü" @click="navOpen = !navOpen">☰</button>
        <div class="spacer"></div>
        <span v-if="user" class="hint">{{ user.display_name }}</span>
        <!-- Zahnrad neben dem Benutzer-Avatar (4.10) -->
        <router-link to="/einstellungen" class="btn" title="Einstellungen">⚙️</router-link>
        <button @click="logout">Abmelden</button>
      </div>
      <router-view />
    </main>
  </div>
</template>
