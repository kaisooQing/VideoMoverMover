<template>
  <div class="download-view">
    <div class="page-header">
      <div>
        <div class="page-title">下载</div>
        <div class="page-subtitle">粘贴链接，一键下载</div>
      </div>
    </div>

    <!-- URL Input -->
    <div class="card">
      <div class="form-group">
        <div v-if="!batchMode">
          <input
            v-model="url"
            type="url"
            placeholder="粘贴视频链接..."
            @keyup.enter="submit"
          />
        </div>
        <div v-else>
          <textarea
            v-model="batchUrls"
            placeholder="每行一个链接"
            rows="4"
          ></textarea>
        </div>
      </div>

      <div style="display: flex; gap: 8px; align-items: center; margin-bottom: 14px;">
        <button
          class="btn btn-primary btn-block"
          :disabled="!hasUrls || store.submitting"
          @click="submit"
        >
          {{ store.submitting ? '解析中...' : '开始下载' }}
        </button>
      </div>

      <div style="display: flex; justify-content: space-between; align-items: center;">
        <button class="collapse-toggle" style="margin: 0;" @click="batchMode = !batchMode">
          {{ batchMode ? '单个链接' : '批量模式' }}
        </button>
        <button class="collapse-toggle" style="margin: 0;" @click="showAdvanced = !showAdvanced">
          {{ showAdvanced ? '收起选项' : '更多选项' }}
        </button>
      </div>

      <!-- Advanced Options (collapsible) -->
      <div v-if="showAdvanced" class="collapse-content" style="margin-top: 14px;">
        <!-- Download Directory -->
        <div class="form-group">
          <label>保存目录</label>
          <div class="dir-picker" @click="showDirPicker = true">
            <span>📂</span>
            <input
              v-model="downloadDir"
              type="text"
              placeholder="默认目录"
              readonly
              class="dir-input-readonly"
            />
          </div>
        </div>

        <!-- Video Quality -->
        <div class="form-group">
          <label>视频质量</label>
          <select v-model="format.mode">
            <option value="best">最佳画质</option>
            <option value="worst">最低画质</option>
            <option value="audio_only">仅音频（MP3）</option>
            <option value="custom">自定义格式</option>
          </select>
        </div>

        <!-- Custom Format String -->
        <div v-if="format.mode === 'custom'" class="form-group">
          <label>自定义格式字符串</label>
          <input v-model="format.format_string" type="text" placeholder="例: bestvideo[height<=1080]+bestaudio/best" />
        </div>

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

        <!-- Cookie -->
        <div class="form-group">
          <label>Cookie 来源</label>
          <select v-model="cookieBrowser" @change="onCookieBrowserChange">
            <option value="">不使用</option>
            <option v-for="b in browsers" :key="b" :value="b">{{ b }}</option>
          </select>
        </div>

        <!-- Cookie file upload -->
        <div class="form-group">
          <label>Cookie 文件</label>
          <div style="display: flex; gap: 8px; align-items: center;">
            <input v-model="cookieFile" type="text" placeholder="选择 Cookie 文件" readonly style="flex: 1;" />
            <label class="btn btn-secondary" style="cursor: pointer; margin: 0; padding: 10px 14px;">
              上传
              <input type="file" accept=".txt" @change="uploadCookieFile" style="display: none;" />
            </label>
          </div>
          <div v-if="cookieFiles.length > 0" style="margin-top: 6px; display: flex; gap: 4px; flex-wrap: wrap;">
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
            抖音/快手等平台需要 Cookie。在 Chrome 安装 Get cookies.txt LOCALLY 扩展导出。
          </div>
        </div>

        <!-- Proxy -->
        <div class="form-group">
          <label>代理</label>
          <input v-model="proxy" type="text" placeholder="http://127.0.0.1:7890" />
        </div>

        <!-- Subtitles -->
        <div class="form-group">
          <label>字幕</label>
          <label class="checkbox-label">
            <input type="checkbox" v-model="subtitleOptions.enabled" /> 下载字幕
          </label>
          <div v-if="subtitleOptions.enabled" style="margin-top: 10px; display: flex; flex-direction: column; gap: 10px; padding-left: 4px;">
            <div>
              <label>字幕语言（逗号分隔）</label>
              <input v-model="subtitleOptions.languages" type="text" placeholder="zh-Hans,en" />
            </div>
            <div>
              <label>字幕格式</label>
              <select v-model="subtitleOptions.sub_format">
                <option value="srt">SRT</option>
                <option value="vtt">VTT</option>
                <option value="ass">ASS</option>
                <option value="lrc">LRC</option>
              </select>
            </div>
            <label class="checkbox-label">
              <input type="checkbox" v-model="subtitleOptions.auto_subs" /> 自动生成的字幕
            </label>
            <label class="checkbox-label">
              <input type="checkbox" v-model="subtitleOptions.embed_subs" /> 嵌入字幕到视频
            </label>
          </div>
        </div>

        <!-- Metadata & Thumbnail -->
        <div class="form-group">
          <label>元数据与封面</label>
          <div style="display: flex; flex-direction: column; gap: 8px;">
            <label class="checkbox-label">
              <input type="checkbox" v-model="embedMetadata" /> 嵌入元数据
            </label>
            <label class="checkbox-label">
              <input type="checkbox" v-model="embedThumbnail" /> 嵌入封面图
            </label>
            <label class="checkbox-label">
              <input type="checkbox" v-model="writeThumbnail" /> 单独保存封面图
            </label>
          </div>
        </div>
      </div>
    </div>

    <!-- Active Downloads -->
    <div v-if="store.activeTasks.length > 0">
      <div class="section-title">下载中 ({{ store.activeTasks.length }})</div>
      <div v-for="task in store.activeTasks" :key="task.id" class="progress-card">
        <img v-if="task.thumbnail" :src="proxyThumb(task.thumbnail)" class="thumb" />
        <div v-else class="thumb">⬇</div>
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
        <div class="actions">
          <button class="btn btn-danger btn-sm" @click="store.cancel(task.id)">取消</button>
        </div>
      </div>
    </div>

    <!-- Recent completed -->
    <div v-if="store.completedTasks.length > 0">
      <div class="section-title">最近完成</div>
      <div v-for="task in store.completedTasks.slice(0, 10)" :key="task.id" class="progress-card">
        <img v-if="task.thumbnail" :src="proxyThumb(task.thumbnail)" class="thumb" />
        <div v-else class="thumb">✓</div>
        <div class="info">
          <div class="title">{{ task.title || task.url }}</div>
          <div class="meta">
            <span class="status-badge" :class="task.status">{{ statusLabel(task.status) }}</span>
            <span v-if="task.error" style="color: var(--error);">{{ task.error }}</span>
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

    <!-- Directory Picker Modal -->
    <div v-if="showDirPicker" class="modal-overlay" @click.self="showDirPicker = false">
      <div class="modal">
        <h3>选择目录</h3>
        <div class="dir-path-input-row">
          <input
            v-model="manualPath"
            type="text"
            class="dir-path-input"
            placeholder="输入路径"
            @keydown.enter="navigateToManualPath"
          />
          <button class="btn btn-secondary dir-path-go-btn" @click="navigateToManualPath">前往</button>
        </div>
        <div class="dir-breadcrumb" style="font-size: 0.8rem; color: var(--text-dim); margin-bottom: 8px;">
          {{ currentPath || '根目录' }}
        </div>
        <div class="dir-list" style="max-height: 40vh; overflow-y: auto;">
          <div
            v-for="item in dirItems"
            :key="item.path"
            class="dir-tree-item"
            @click="navigateDir(item.path)"
          >
            <span>{{ currentPath ? '📁' : '💿' }}</span>
            <span>{{ item.name }}</span>
          </div>
          <div v-if="dirItems.length === 0" class="empty-state" style="padding: 20px;">空目录</div>
        </div>
        <div style="display: flex; gap: 8px; margin-top: 14px;">
          <button class="btn btn-primary btn-block" @click="selectDir" :disabled="!currentPath">选择此目录</button>
          <button class="btn btn-secondary" @click="showDirPicker = false">取消</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useDownloadStore } from '../stores/download'
import { getBrowsers, getDirectories, openFile, openFolder } from '../api/settings'
import type { DownloadRequest } from '../api/downloads'

const store = useDownloadStore()

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

// Form state
const url = ref('')
const batchMode = ref(false)
const batchUrls = ref('')
const downloadDir = ref('')
const outputTemplate = ref('%(title)s.%(ext)s')
const cookieBrowser = ref('')
const proxy = ref('')
const showAdvanced = ref(false)

// Video quality
const format = ref({ mode: 'best', format_string: '' })

// Subtitles
const subtitleOptions = ref({
  enabled: false,
  languages: 'zh-Hans,en',
  auto_subs: true,
  sub_format: 'srt',
  embed_subs: false,
})

// Metadata & thumbnail
const embedMetadata = ref(false)
const embedThumbnail = ref(false)
const writeThumbnail = ref(false)

// Directory picker
const showDirPicker = ref(false)
const currentPath = ref('')
const dirItems = ref<{ name: string; path: string }[]>([])
const manualPath = ref('')

watch(showDirPicker, async (val) => {
  if (val) {
    manualPath.value = currentPath.value
    try {
      const result = await getDirectories('')
      currentPath.value = result.path
      dirItems.value = result.children || []
    } catch (e) {
      console.error('Failed to load drives:', e)
    }
  }
})

async function navigateToManualPath() {
  const p = manualPath.value.trim()
  if (!p) return
  try {
    const result = await getDirectories(p)
    currentPath.value = result.path
    dirItems.value = result.children || []
  } catch (e) {
    currentPath.value = p
    dirItems.value = []
  }
}

// Browsers & cookies
const browsers = ref<string[]>([])
const cookieFile = ref('')
const cookieFiles = ref<{ filename: string; path: string }[]>([])

function onCookieBrowserChange() {
  if (cookieBrowser.value) cookieFile.value = ''
}

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
    queued: '排队', downloading: '下载中', processing: '处理中',
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
    download_dir: downloadDir.value || undefined,
    format_option: format.value,
    cookie_browser: cookieBrowser.value || undefined,
    cookie_file: cookieFile.value || undefined,
    proxy: proxy.value || undefined,
    output_template: outputTemplate.value,
    subtitle_options: subtitleOptions.value,
    embed_metadata: embedMetadata.value,
    embed_thumbnail: embedThumbnail.value,
    write_thumbnail: writeThumbnail.value,
  }

  await store.submitDownload(req)
  url.value = ''
  batchUrls.value = ''
}

async function navigateDir(path: string) {
  try {
    const result = await getDirectories(path)
    currentPath.value = result.path
    dirItems.value = result.children || []
  } catch (e) {
    console.error('Failed to list directory:', e)
  }
}

function selectDir() {
  downloadDir.value = currentPath.value
  showDirPicker.value = false
}

onMounted(async () => {
  try {
    browsers.value = await getBrowsers()
    await refreshCookieFiles()
  } catch (e) {
    console.error('Failed to load initial data:', e)
  }
})
</script>

<style scoped>
.dir-input-readonly {
  flex: 1;
  border: none;
  background: transparent;
  color: var(--text);
  font-size: 0.9rem;
  cursor: pointer;
  outline: none;
  padding: 0;
}
.dir-input-readonly::placeholder { color: var(--text-muted); }
.dir-picker {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-input);
}
.dir-picker:hover { border-color: var(--primary); }
.template-hints {
  display: flex;
  gap: 6px;
  margin-top: 6px;
  flex-wrap: wrap;
}
.hint-chip {
  font-size: 0.75rem;
  padding: 3px 8px;
  border-radius: 99px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.15s;
}
.hint-chip:hover { border-color: var(--primary); color: var(--primary); }
.hint-chip.active { border-color: var(--primary); color: var(--primary); background: rgba(99,102,241,0.1); }
.cookie-tip {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-top: 6px;
  padding: 8px 10px;
  background: var(--bg-input);
  border-radius: 6px;
  border-left: 3px solid var(--primary);
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
.btn-action:hover { opacity: 0.85; }
.btn-block { width: 100%; justify-content: center; }
.dir-list { margin: 0 -4px; }
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 20px;
}
.page-title {
  font-size: 1.4rem;
  font-weight: 600;
}
.page-subtitle {
  font-size: 0.85rem;
  color: var(--text-muted);
  margin-top: 4px;
}
</style>
