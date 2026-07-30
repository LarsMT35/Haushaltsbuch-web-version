import { createRouter, createWebHashHistory } from 'vue-router'
import { getToken } from './api.js'

import BudgetsView from './views/BudgetsView.vue'
import CategoriesView from './views/CategoriesView.vue'
import DashboardView from './views/DashboardView.vue'
import ImportView from './views/ImportView.vue'
import LoginView from './views/LoginView.vue'
import RecurringView from './views/RecurringView.vue'
import RulesView from './views/RulesView.vue'
import SettingsView from './views/SettingsView.vue'
import TransactionsView from './views/TransactionsView.vue'

export const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/login', component: LoginView },
    { path: '/', component: DashboardView },
    { path: '/buchungen', component: TransactionsView },
    { path: '/import', component: ImportView },
    { path: '/budgets', component: BudgetsView },
    { path: '/kategorien', component: CategoriesView },
    { path: '/regeln', component: RulesView },
    { path: '/wiederkehrend', component: RecurringView },
    { path: '/einstellungen', component: SettingsView },
  ],
})

router.beforeEach((to) => {
  if (to.path !== '/login' && !getToken()) return '/login'
})
