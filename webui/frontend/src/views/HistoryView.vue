<template>
  <div class="history-view">
    <h2 class="page-title">下载历史</h2>

    <div class="filter-bar">
      <button
        v-for="f in filters"
        :key="f.value"
        class="btn"
        :class="currentFilter === f.value ? 'btn-primary' : 'btn-secondary'"
        @click="currentFilter = f.value"
      >
        {{ f.label }}
      </button>
    </div>

    <div v-if="filteredTasks.length === 0" class="empty-state">
      暂无{{ currentFilter === 'all' ? '' : statusLabel(currentFilter) }}下载记录
    </div>

    <div v-for="task in filteredTasks" :key="task.id" class="progress-card">
      <img v-if="task.thumbnail" :src="proxyThumb(task.thumbnail)" class="thumb" />
      <div v-else class="thumb" style="display: flex; align-items: center; justify-content: center; color: var(--text-muted);">📄</div>
      <div class="info">
        <div class="title">{{ task.title || task.url }}</div>
        <div class="meta">
          <span class="status-badge" :class="task.status">{{ statusLabel(task.status) }}</span>
          <span v-if="task.filename" style="word-break: break-all;">{{ task.filename }}</span>
          <span v-if="task.error" style="color: var(--error);">{{ task.error }}</span>
        </div>
        <div v-if="task.filename && task.status === 'completed'" class="task-actions">
          <button class="btn btn-sm btn-action" @click="handleOpenFile(task.filename)" :title="getFileActionLabel(task.filename)">
            {{ getFileActionIcon(task.filename) }} {{ getFileActionLabel(task.filename) }}
          </button>
          <button class="btn btn-sm btn-secondary" @click="handleOpenFolder(task.filename)" title="打开所在文件夹">
            📂 文件夹
          </button>
        </div>
        <div class="meta" style="margin-top: 4px;">
          <span>{{ formatDate(task.created_at) }}</span>
          <span>{{ task.url }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useDownloadStore } from '../stores/download'
import { openFile, openFolder } from '../api/settings'

const store = useDownloadStore()
const currentFilter = ref('all')

// Proxy thumbnail URLs through backend (external) or read local files
function proxyThumb(thumbnail: string | null | undefined): string {
  if (!thumbnail) return ''
  // Remote URL -> proxy via backend
  if (thumbnail.startsWith('http://') || thumbnail.startsWith('https://')) {
    return `/api/system/proxy-image?url=${encodeURIComponent(thumbnail)}`
  }
  // Local file path (Windows C:\ or Unix /) -> read via backend
  return `/api/system/proxy-image?path=${encodeURIComponent(thumbnail)}`
}

const filters = [
  { value: 'all', label: '全部' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '失败' },
  { value: 'cancelled', label: '已取消' },
]

const filteredTasks = computed(() => {
  const tasks = store.completedTasks
  if (currentFilter.value === 'all') return tasks
  return tasks.filter((t) => t.status === currentFilter.value)
})

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }
  return labels[status] || status
}

function formatDate(timestamp: number): string {
  if (!timestamp) return ''
  const d = new Date(timestamp * 1000)
  return d.toLocaleString('zh-CN')
}

const VIDEO_EXTS = new Set(['.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv', '.m4v', '.ts', '.rmvb', '.rm'])
const IMAGE_EXTS = new Set(['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'])

function getFileExt(path: string): string {
  const i = path.lastIndexOf('.')
  return i >= 0 ? path.substring(i).toLowerCase() : ''
}

function isFolder(path: string): boolean {
  if (path.endsWith('\\') || path.endsWith('/')) return true
  const lastSep = Math.max(path.lastIndexOf('/'), path.lastIndexOf('\\'))
  const lastComponent = lastSep >= 0 ? path.substring(lastSep + 1) : path
  if (!lastComponent.includes('.')) return true
  const ext = getFileExt(path)
  return !ext || ext.length > 5
}

function getFileActionLabel(path: string): string {
  if (isFolder(path)) return '打开'
  const ext = getFileExt(path)
  if (VIDEO_EXTS.has(ext)) return '播放'
  if (IMAGE_EXTS.has(ext)) return '查看'
  return '打开'
}

function getFileActionIcon(path: string): string {
  if (isFolder(path)) return ''
  const ext = getFileExt(path)
  if (VIDEO_EXTS.has(ext)) return '▶'
  if (IMAGE_EXTS.has(ext)) return '🖼'
  return '📄'
}

async function handleOpenFile(path: string) {
  try {
    const res = await openFile(path)
    if (!res.success) {
      alert('打开失败: ' + (res.error || '未知错误'))
    }
  } catch (e: any) {
    alert('打开失败: ' + (e.message || e))
  }
}

async function handleOpenFolder(path: string) {
  try {
    const res = await openFolder(path)
    if (!res.success) {
      alert('打开失败: ' + (res.error || '未知错误'))
    }
  } catch (e: any) {
    alert('打开失败: ' + (e.message || e))
  }
}
</script>

<style scoped>
.page-title {
  font-size: 1.4rem;
  margin-bottom: 20px;
}

.filter-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
}

.empty-state {
  text-align: center;
  color: var(--text-muted);
  padding: 60px 0;
  font-size: 0.95rem;
}

.task-actions {
  display: flex;
  gap: 6px;
  margin-top: 8px;
}

.btn-sm {
  padding: 4px 10px;
  font-size: 0.78rem;
  border-radius: 4px;
}

.btn-action {
  background: var(--primary);
  color: #fff;
  border: none;
  cursor: pointer;
}

.btn-action:hover {
  opacity: 0.85;
}
</style>
