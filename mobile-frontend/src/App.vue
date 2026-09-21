<template>
  <div class="app">
    <div class="author-badge">by <strong>王小氢</strong></div>

    <main class="content">
      <router-view />
    </main>

    <nav class="tab-bar">
      <router-link to="/" class="tab-item" :class="{ active: $route.path === '/' }">
        <span class="tab-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="12" y1="4" x2="12" y2="20" />
            <polyline points="6 14 12 20 18 14" />
          </svg>
        </span>
        <span class="tab-label">下载</span>
      </router-link>
      <router-link to="/history" class="tab-item" :class="{ active: $route.path === '/history' }">
        <span class="tab-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="9" />
            <polyline points="12 7 12 12 15 15" />
          </svg>
        </span>
        <span class="tab-label">历史</span>
      </router-link>
      <router-link to="/settings" class="tab-item" :class="{ active: $route.path === '/settings' }">
        <span class="tab-icon">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <circle cx="12" cy="12" r="3" />
          </svg>
        </span>
        <span class="tab-label">设置</span>
      </router-link>
    </nav>

    <div class="status-bar" :class="{ connected }">
      <span class="status-dot"></span>
      <span>{{ connected ? '已连接' : '连接中...' }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useDownloadStore } from './stores/download'
import { useWebSocket } from './composables/useWebSocket'

const store = useDownloadStore()
const { connected } = useWebSocket()

onMounted(() => {
  store.refreshTasks()
})
</script>

<style>
/* ===== Tab Bar - Frosted Glass ===== */
.tab-bar {
  background: rgba(22, 23, 31, 0.85) !important;
  backdrop-filter: blur(20px) !important;
  -webkit-backdrop-filter: blur(20px) !important;
  border-top: 1px solid rgba(129, 140, 248, 0.12) !important;
  height: calc(60px + var(--safe-bottom)) !important;
}

/* ===== Tab Item Active ===== */
.tab-item {
  position: relative;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

.tab-item.active .tab-icon {
  transform: scale(1.1);
  filter: drop-shadow(0 0 8px rgba(129, 140, 248, 0.5));
}

.tab-item.active::after {
  content: '';
  position: absolute;
  bottom: 4px;
  left: 50%;
  transform: translateX(-50%);
  width: 20px;
  height: 3px;
  background: linear-gradient(90deg, #818cf8, #a78bfa);
  border-radius: 2px;
}

/* ===== Status Bar - Frosted Glass ===== */
.status-bar {
  backdrop-filter: blur(12px) !important;
  -webkit-backdrop-filter: blur(12px) !important;
  background: rgba(22, 23, 31, 0.75) !important;
}

.status-bar.connected .status-dot {
  animation: status-pulse 2s ease-in-out infinite;
}

@keyframes status-pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.4); }
  50% { box-shadow: 0 0 0 4px rgba(34, 197, 94, 0); }
}
</style>
