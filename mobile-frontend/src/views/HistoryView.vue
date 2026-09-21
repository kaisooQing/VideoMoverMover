<template>
  <div class="history-view">
    <div class="page-header">
      <div class="page-title">下载历史</div>
    </div>

    <div class="filter-bar">
      <button
        v-for="f in filters"
        :key="f.value"
        class="filter-chip"
        :class="{ active: currentFilter === f.value }"
        @click="currentFilter = f.value"
      >
        {{ f.label }}
      </button>
    </div>

    <div v-if="filteredTasks.length === 0" class="empty-state">
      暂无{{ currentFilter === 'all' ? '' : statusLabel(currentFilter) }}下载记录
    </div>

    <div v-for="task in filteredTasks" :key="task.id" class="progress-card">
      <div class="card-header">
        <img v-if="task.thumbnail" :src="proxyThumb(task.thumbnail)" class="thumb" />
        <div v-else class="thumb">📄</div>
        <div class="info">
          <div class="title">{{ task.title || task.url }}</div>
          <div class="meta">
            <span class="status-badge" :class="task.status">{{ statusLabel(task.status) }}</span>
            <span v-if="task.error" class="error-text">{{ task.error }}</span>
          </div>
          <div v-if="task.filename" class="meta" style="margin-top: 2px;">
            <span class="filename-text">{{ task.filename.split('/').pop()?.split('\\').pop() }}</span>
          </div>
          <div v-if="task.filename && task.status === 'completed'" class="task-actions">
            <button class="btn btn-sm btn-action" @click="handleOpenFile(task.filename)">
              {{ getFileActionIcon(task.filename) }} {{ getFileActionLabel(task.filename) }}
            </button>
            <button class="btn btn-sm btn-secondary" @click="handleOpenFolder(task.filename)">
              📂 文件夹
            </button>
          </div>
          <div class="meta" style="margin-top: 4px;">
            <span>{{ formatDate(task.created_at) }}</span>
          </div>
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

// Proxy thumbnail URLs through backend to avoid CORS/referer restrictions
function proxyThumb(thumbnail: string | null | undefined): string {
  if (!thumbnail) return ''
  if (thumbnail.startsWith('http://') || thumbnail.startsWith('https://')) {
    return `/api/system/proxy-image?url=${encodeURIComponent(thumbnail)}`
  }
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
    completed: '已完成', failed: '失败', cancelled: '已取消',
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
  return !path.includes('.') || path.endsWith('\\') || path.endsWith('/')
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
    if (!res.success) alert('打开失败: ' + (res.error || '未知错误'))
  } catch (e: any) {
    alert('打开失败: ' + (e.message || e))
  }
}

async function handleOpenFolder(path: string) {
  try {
    const res = await openFolder(path)
    if (!res.success) alert('打开失败: ' + (res.error || '未知错误'))
  } catch (e: any) {
    alert('打开失败: ' + (e.message || e))
  }
}
</script>

<style scoped>
/* ===== Filter Bar ===== */
.filter-bar {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}

/* ===== Filter Chips ===== */
.filter-chip {
  padding: 6px 14px;
  border-radius: 99px;
  border: 1px solid var(--border);
  background: linear-gradient(135deg, var(--bg-card), var(--bg-input));
  color: var(--text-muted);
  font-size: 0.82rem;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s ease;
}

.filter-chip:active {
  transform: scale(0.96);
}

.filter-chip.active {
  background: linear-gradient(135deg, #818cf8, #a78bfa);
  color: white;
  border-color: transparent;
  box-shadow: 0 2px 10px rgba(129, 140, 248, 0.3);
}

/* ===== Progress Card (History) ===== */
.progress-card {
  transition: all 0.15s ease;
}

.progress-card:active {
  background: #1e1f2b;
  transform: scale(0.98);
}

.progress-card .thumb {
  width: 72px;
  height: 50px;
  border-radius: 12px;
}

.progress-card .thumb img {
  filter: brightness(0.9);
  transition: filter 0.2s ease;
}

.progress-card:active .thumb img {
  filter: brightness(1);
}

/* ===== Filename Text ===== */
.filename-text {
  word-break: break-all;
  font-size: 0.72rem;
  color: rgba(129, 140, 248, 0.5);
}

/* ===== Error Text ===== */
.error-text {
  color: var(--error);
  word-break: break-all;
  background: rgba(239, 68, 68, 0.08);
  padding: 4px 8px;
  border-radius: 6px;
}

/* ===== Empty State ===== */
.empty-state {
  text-align: center;
  color: #4b5563;
  padding: 60px 0 40px 0;
  font-size: 0.95rem;
}

.empty-state::before {
  content: '📭';
  display: block;
  font-size: 2.5rem;
  margin-bottom: 16px;
  opacity: 0.5;
}
</style>
