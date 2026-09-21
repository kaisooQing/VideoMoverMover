import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import DownloadView from './views/DownloadView.vue'
import HistoryView from './views/HistoryView.vue'
import SettingsView from './views/SettingsView.vue'
import './style.css'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', component: DownloadView },
    { path: '/history', component: HistoryView },
    { path: '/settings', component: SettingsView },
  ],
})

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
