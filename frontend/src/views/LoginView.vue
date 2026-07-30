<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { login } from '../api.js'

const emit = defineEmits(['logged-in'])
const router = useRouter()
const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  error.value = ''
  busy.value = true
  try {
    await login(username.value, password.value)
    emit('logged-in')
    router.push('/')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <form class="login-box" @submit.prevent="submit">
      <h1 style="margin-bottom: 1rem">💰 Haushaltsbuch</h1>
      <label>Benutzername</label>
      <input v-model="username" autocomplete="username" required />
      <label>Passwort</label>
      <input v-model="password" type="password" autocomplete="current-password" required />
      <p v-if="error" class="error">{{ error }}</p>
      <button class="primary" style="width: 100%" :disabled="busy">Anmelden</button>
      <p class="hint" style="margin-top: 1rem">
        Kein Konto? Zugänge legt der Administrator an – es gibt bewusst keine Selbstregistrierung.
      </p>
    </form>
  </div>
</template>
