<script setup>
import { inject, onMounted, ref, watch } from 'vue'
import { api, fmtAmount } from '../api.js'
import ChartCanvas from '../components/ChartCanvas.vue'

const accounts = inject('accounts')
const summary = ref(null)
const categories = ref([])
// Filter-Chips: eine Auswahl filtert alle Kacheln gleichzeitig (4.9.1)
const filter = ref({ account_id: '', category_id: '', date_from: '', date_to: '' })

async function load() {
  const params = {}
  for (const [k, v] of Object.entries(filter.value)) if (v) params[k] = v
  summary.value = await api.get('/dashboard/summary', params)
}

onMounted(async () => {
  categories.value = await api.get('/categories')
  await load()
})
watch(filter, load, { deep: true })

const palette = ['#2563eb', '#0f766e', '#b45309', '#7c3aed', '#be185d', '#0369a1',
  '#4d7c0f', '#b91c1c', '#6b7280', '#92400e', '#065f46', '#1d4ed8']
</script>

<template>
  <div v-if="summary">
    <div class="chips">
      <select v-model="filter.account_id">
        <option value="">Alle Konten</option>
        <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
      </select>
      <select v-model="filter.category_id">
        <option value="">Alle Kategorien</option>
        <option v-for="c in categories" :key="c.id" :value="c.id">{{ c.name }}</option>
      </select>
      <!-- frei wählbarer Zeitraum statt festem Raster (4.9) -->
      <input type="date" v-model="filter.date_from" />
      <input type="date" v-model="filter.date_to" />
    </div>

    <div class="grid">
      <div class="tile">
        <h3>Einnahmen</h3>
        <div class="big pos">{{ fmtAmount(summary.income) }}</div>
        <p class="hint">{{ summary.date_from }} – {{ summary.date_to }}, ohne Umbuchungen</p>
      </div>
      <div class="tile">
        <h3>Ausgaben</h3>
        <div class="big neg">{{ fmtAmount(summary.expenses) }}</div>
      </div>
      <div class="tile">
        <h3>Bilanz</h3>
        <div class="big" :class="summary.income - summary.expenses >= 0 ? 'pos' : 'neg'">
          {{ fmtAmount(summary.income - summary.expenses) }}
        </div>
      </div>
      <div class="tile">
        <h3>Gesamtvermögen</h3>
        <div class="big">{{ fmtAmount(summary.balance_total) }}</div>
      </div>

      <!-- Handlungsbedarf wird nicht versteckt (4.9.1) -->
      <div v-if="summary.unassigned_count > 0" class="tile warn">
        <h3>⚠ Handlungsbedarf</h3>
        <p><strong>{{ summary.unassigned_count }}</strong> Buchungen ohne Kategorie.</p>
        <router-link class="btn" :to="{ path: '/buchungen', query: { unassigned: 1 } }">Jetzt zuordnen</router-link>
      </div>

      <div class="tile wide">
        <h3>Monatliche Bilanz (Einnahmen − Ausgaben)</h3>
        <ChartCanvas type="bar"
          :labels="summary.monthly_balance.map((m) => m.month)"
          :datasets="[{ label: 'Bilanz', data: summary.monthly_balance.map((m) => m.value),
                        backgroundColor: summary.monthly_balance.map((m) => m.value >= 0 ? '#15803d' : '#b91c1c') }]" />
      </div>
      <div class="tile wide">
        <h3>Monatliche Gesamtausgaben</h3>
        <ChartCanvas type="bar"
          :labels="summary.monthly_expenses.map((m) => m.month)"
          :datasets="[{ label: 'Ausgaben', data: summary.monthly_expenses.map((m) => m.value),
                        backgroundColor: '#2563eb' }]" />
      </div>
      <div class="tile">
        <h3>Ausgaben nach Kategorie</h3>
        <ChartCanvas type="doughnut"
          :labels="summary.by_category.slice(0, 12).map((c) => c.category_name)"
          :datasets="[{ data: summary.by_category.slice(0, 12).map((c) => c.value),
                        backgroundColor: palette }]"
          :options="{ plugins: { legend: { position: 'right' } } }" />
      </div>
      <div class="tile">
        <h3>Fix / Variabel</h3>
        <ChartCanvas type="doughnut"
          :labels="['Ausgaben fix', 'Ausgaben variabel', 'Einnahmen fix', 'Einnahmen variabel']"
          :datasets="[{ data: [summary.fixed_vs_variable.expenses_fixed,
                              summary.fixed_vs_variable.expenses_variable,
                              summary.fixed_vs_variable.income_fixed,
                              summary.fixed_vs_variable.income_variable],
                        backgroundColor: ['#b45309', '#2563eb', '#0f766e', '#15803d'] }]"
          :options="{ plugins: { legend: { position: 'right' } } }" />
      </div>
      <div class="tile wide">
        <h3>Monatliche Bewegung der Sparkonten</h3>
        <ChartCanvas type="bar"
          :labels="summary.savings_movement.map((m) => m.month)"
          :datasets="[{ label: 'Bewegung', data: summary.savings_movement.map((m) => m.value),
                        backgroundColor: '#0f766e' }]" />
      </div>
      <div class="tile">
        <h3>Top-Ausgaben im Zeitraum</h3>
        <table>
          <tbody>
            <tr v-for="c in summary.by_category.slice(0, 8)" :key="c.category_name">
              <td>{{ c.category_name }} <span v-if="c.is_fixed_cost" class="badge gray">fix</span></td>
              <td class="num neg">{{ fmtAmount(c.value) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
  <p v-else class="hint">Lade Dashboard …</p>
</template>
