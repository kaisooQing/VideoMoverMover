<template>
  <div class="download-view">
    <div class="page-header">
      <div class="page-title">下载</div>
      <div class="page-subtitle">粘贴链接，一键下载</div>
    </div>

    <!-- URL Input Card -->
    <div class="card">
      <div class="form-group">
        <div v-if="!batchMode">
          <textarea
            v-model="url"
            placeholder="粘贴视频链接..."
            @keyup.enter.ctrl="submit"
            autocomplete="off"
            rows="3"
            style="min-height: 112px; padding: 16px 14px; font-size: 1rem; resize: none;"
          ></textarea>
        </div>
        <div v-else>
          <textarea
            v-model="batchUrls"
            placeholder="每行一个链接"
            rows="4"
          ></textarea>
        </div>
      </div>

      <button
        class="btn btn-primary btn-block"
        :disabled="!hasUrls || store.submitting"
        @click="submit"
      >
        {{ store.submitting ? '解析中...' : '开始下载' }}
      </button>

      <div class="inline-actions">
        <button class="collapse-toggle" @click="batchMode = !batchMode">
          {{ batchMode ? '单个链接' : '批量模式' }}
        </button>
        <button class="collapse-toggle" @click="showAdvanced = !showAdvanced">
          {{ showAdvanced ? '收起选项' : '更多选项' }}
        </button>
      </div>

      <!-- Advanced Options -->
      <div v-if="showAdvanced" class="collapse-content" style="margin-top: 12px;">
        <!-- Output Template -->
        <div class="form-group">
          <label>文件命名</label>
          <input v-model="outputTemplate" type="text" placeholder="%(title)s.%(ext)s" />
          <div class="template-hints">
            <span class="hint-chip" @click="outputTemplate += '%(title)s'">标题</span>
            <span class="hint-chip" @click="outputTemplate += '%(uploader)s'">作者</span>
            <span class="hint-chip" @click="outputTemplate += '%(upload_date)s'">日期</span>
          </div>
        </div>

        <!-- Cookie File Upload -->
        <div class="form-group">
          <label>Cookie 文件</label>
          <div class="cookie-upload-row">
            <input v-model="cookieFile" type="text" placeholder="选择 Cookie 文件" readonly />
            <label class="btn btn-secondary btn-upload">
              上传
              <input type="file" accept=".txt" @change="uploadCookieFile" style="display: none;" />
            </label>
          </div>
          <div v-if="cookieFiles.length > 0" class="cookie-chips">
            <span
              v-for="cf in cookieFiles"
              :key="cf.path"
              class="hint-chip"
              :class="{ active: cookieFile === cf.path }"
              @click="cookieFile = cf.path"
            >
              {{ cf.filename }}
            </span>
          </div>
          <div class="cookie-tip">
            抖音/快手等平台需要 Cookie。在浏览器安装 Get cookies.txt LOCALLY 扩展导出。
          </div>
        </div>
      </div>
    </div>

    <!-- Active Downloads -->
    <div v-if="store.activeTasks.length > 0">
      <div class="section-title">下载中 ({{ store.activeTasks.length }})</div>
      <div v-for="task in store.activeTasks" :key="task.id" class="progress-card is-active">
        <div class="card-header">
          <img v-if="task.thumbnail" :src="proxyThumb(task.thumbnail)" class="thumb" />
          <div v-else class="thumb thumb-placeholder"></div>
          <div class="info">
            <div class="title">{{ task.title || task.url }}</div>
            <div class="progress-bar-bg">
              <div
                class="progress-bar-fill"
                :class="{ processing: task.status === 'processing' }"
                :style="{ width: task.progress_pct + '%' }"
              ></div>
            </div>
            <div class="meta">
              <span>{{ task.progress_pct.toFixed(1) }}%</span>
              <span v-if="task.speed">{{ task.speed }}</span>
              <span v-if="task.eta">{{ task.eta }}</span>
              <span class="status-badge" :class="task.status">{{ statusLabel(task.status) }}</span>
            </div>
          </div>
        </div>
        <div class="actions">
          <button class="btn btn-danger btn-sm" @click="store.cancel(task.id)">取消</button>
        </div>
      </div>
    </div>

    <!-- Recent Completed -->
    <div v-if="store.completedTasks.length > 0">
      <div class="section-title">最近完成</div>
      <div v-for="task in store.completedTasks.slice(0, 10)" :key="task.id" class="progress-card">
        <div class="card-header">
          <img v-if="task.thumbnail" :src="proxyThumb(task.thumbnail)" class="thumb" />
          <div v-else class="thumb">✓</div>
          <div class="info">
            <div class="title">{{ task.title || task.url }}</div>
            <div class="meta">
              <span class="status-badge" :class="task.status">{{ statusLabel(task.status) }}</span>
              <span v-if="task.error" class="error-text">{{ task.error }}</span>
            </div>
            <div v-if="task.filename && !task.error" class="task-actions">
              <button class="btn btn-sm btn-action" @click="handleOpenFile(task.filename)">
                {{ getFileActionIcon(task.filename) }} {{ getFileActionLabel(task.filename) }}
              </button>
              <button class="btn btn-sm btn-secondary" @click="handleOpenFolder(task.filename)">
                📂 文件夹
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useDownloadStore } from '../stores/download'
import { openFile, openFolder } from '../api/settings'
import type { DownloadRequest } from '../api/downloads'

const store = useDownloadStore()

// Proxy thumbnail URLs through backend to avoid CORS/referer restrictions
function proxyThumb(thumbnail: string | null | undefined): string {
  if (!thumbnail) return ''
  if (thumbnail.startsWith('http://') || thumbnail.startsWith('https://')) {
    return `/api/system/proxy-image?url=${encodeURIComponent(thumbnail)}`
  }
  return `/api/system/proxy-image?path=${encodeURIComponent(thumbnail)}`
}

const url = ref('')
const batchMode = ref(false)
const batchUrls = ref('')
const outputTemplate = ref('%(title)s.%(ext)s')
const showAdvanced = ref(false)
const cookieFile = ref('')
const cookieFiles = ref<{ filename: string; path: string }[]>([])

async function uploadCookieFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await fetch('/api/downloads/cookies/upload', { method: 'POST', body: formData })
    const data = await res.json()
    cookieFile.value = data.path
    await refreshCookieFiles()
  } catch (e) {
    console.error('Cookie upload failed:', e)
  }
  input.value = ''
}

async function refreshCookieFiles() {
  try {
    const res = await fetch('/api/downloads/cookies/list')
    cookieFiles.value = await res.json()
  } catch (e) {
    console.error('Failed to list cookie files:', e)
  }
}

const hasUrls = computed(() => {
  if (batchMode.value) return batchUrls.value.split('\n').some((u) => u.trim().length > 0)
  return url.value.trim().length > 0
})

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    queued: '排队', starting: '初始化', downloading: '下载中', processing: '处理中',
    completed: '完成', failed: '失败', cancelled: '已取消',
  }
  return labels[status] || status
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

async function submit() {
  const urls = batchMode.value
    ? batchUrls.value.split('\n').map((u) => u.trim()).filter(Boolean)
    : [url.value.trim()]

  const req: DownloadRequest = {
    urls,
    format_option: { mode: 'best', format_string: '' },
    output_template: outputTemplate.value,
    subtitle_options: { enabled: false, languages: '', auto_subs: false, sub_format: 'srt', embed_subs: false },
    cookie_file: cookieFile.value || undefined,
    write_thumbnail: false,
    embed_thumbnail: false,
    embed_metadata: false,
  }

  await store.submitDownload(req)
  url.value = ''
  batchUrls.value = ''
}

onMounted(async () => {
  await refreshCookieFiles()
})
</script>

<style scoped>
/* ===== Page Subtitle ===== */
.page-subtitle {
  letter-spacing: 0.5px;
  color: #6b7280;
}

/* ===== Input Height & Focus Glow ===== */
:deep(input),
:deep(textarea) {
  transition: all 0.25s ease;
}

:deep(textarea) {
  min-height: 112px !important;
  padding: 16px 14px !important;
}

:deep(input) {
  min-height: 56px !important;
  padding: 16px 14px !important;
}

:deep(input:focus),
:deep(textarea:focus) {
  border-color: #818cf8;
  box-shadow: 0 0 0 3px rgba(129, 140, 248, 0.15);
}

/* ===== Primary Button ===== */
.btn-primary {
  height: 48px;
  font-size: 1rem;
  font-weight: 600;
  background: linear-gradient(135deg, #818cf8, #a78bfa);
  box-shadow: 0 4px 15px rgba(129, 140, 248, 0.3);
  border-radius: 12px;
  letter-spacing: 1px;
}

.btn-primary:active {
  background: linear-gradient(135deg, #6366f1, #818cf8);
  box-shadow: 0 2px 10px rgba(129, 140, 248, 0.2);
  transform: scale(0.98);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  box-shadow: none;
}

/* ===== Inline Actions ===== */
.inline-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid transparent;
  background-image: linear-gradient(90deg, transparent, var(--border), transparent);
  background-size: 100% 1px;
  background-position: bottom;
  background-repeat: no-repeat;
}

.inline-actions .collapse-toggle {
  font-weight: 500;
}

/* ===== Section Title ===== */
.section-title {
  border-left: 3px solid var(--primary);
  padding-left: 10px;
  font-weight: 600;
  font-size: 0.95rem;
}

/* ===== Thumb Shimmer Placeholder ===== */
@keyframes shimmer {
  0% { background-position: -200px 0; }
  100% { background-position: 200px 0; }
}

.thumb-placeholder {
  background: linear-gradient(90deg, var(--bg-input) 25%, #2a2b38 50%, var(--bg-input) 75%);
  background-size: 200px 100%;
  animation: shimmer 1.5s infinite;
}

/* ===== Active Progress Card ===== */
.progress-card.is-active {
  border-left: 3px solid var(--primary);
}

/* ===== Task Actions ===== */
.task-actions {
  gap: 10px !important;
}

.btn-action {
  background: linear-gradient(135deg, #818cf8, #a78bfa);
  color: #fff;
  border: none;
  cursor: pointer;
}

.btn-action:active {
  opacity: 0.85;
}

.btn-secondary {
  border: none;
  background: rgba(129, 140, 248, 0.1);
  color: #818cf8;
}

.btn-secondary:active {
  background: rgba(129, 140, 248, 0.2);
}

/* ===== Cookie Upload Row ===== */
.cookie-upload-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.cookie-upload-row input[readonly] {
  flex: 1;
}

.btn-upload {
  padding: 10px 14px;
  white-space: nowrap;
  cursor: pointer;
  flex-shrink: 0;
}

.cookie-chips {
  margin-top: 8px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

/* ===== Error Text ===== */
.error-text {
  color: var(--error);
  font-size: 0.75rem;
  word-break: break-all;
}
</style>
