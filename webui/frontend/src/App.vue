<template>
  <div class="app">
    <nav class="sidebar">
      <div class="logo">
        <h1>视频搬运工</h1>
        <span class="subtitle">视频下载</span>
      </div>
      <ul class="nav-links">
        <li>
          <router-link to="/" :class="{ active: $route.path === '/' }">
            <span class="icon">⬇</span> 下载
          </router-link>
        </li>
        <li>
          <router-link to="/history" :class="{ active: $route.path === '/history' }">
            <span class="icon">📋</span> 历史
          </router-link>
        </li>
        <li>
          <router-link to="/settings" :class="{ active: $route.path === '/settings' }">
            <span class="icon">⚙</span> 设置
          </router-link>
        </li>
      </ul>
      <div class="status">
        <span :class="['dot', { connected: store.connected }]"></span>
        {{ store.connected ? '已连接' : '连接中...' }}
      </div>
      <div class="author-badge">by <strong>王小氢</strong></div>
    </nav>
    <main class="content">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useDownloadStore } from './stores/download'

const store = useDownloadStore()

onMounted(() => {
  store.refreshTasks()
})
</script>
