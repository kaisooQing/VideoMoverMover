import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'download',
    component: () => import('../views/DownloadView.vue'),
  },
  {
    path: '/history',
    name: 'history',
    component: () => import('../views/HistoryView.vue'),
  },
  {
    path: '/settings',
    name: 'settings',
    component: () => import('../views/SettingsView.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
