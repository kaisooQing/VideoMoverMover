<template>
  <div class="settings-view">
    <h2 class="page-title">设置</h2>

    <div class="card">
      <h3 class="section-title">基本设置</h3>

      <div class="form-group">
        <label>默认下载目录</label>
        <div class="dir-picker" @click="showDirPicker = true">
          <span class="dir-icon">📂</span>
          <input
            v-model="settings.download_dir"
            type="text"
            readonly
            class="dir-input-readonly"
          />
        </div>
      </div>

      <div class="form-row">
        <div class="form-group">
          <label>最大并发下载数</label>
          <input v-model.number="settings.max_concurrent" type="number" min="1" max="10" />
        </div>
        <div class="form-group">
          <label>FFmpeg 路径</label>
          <input v-model="settings.ffmpeg_path" type="text" placeholder="留空则使用系统 PATH" />
        </div>
      </div>

      <div class="form-group">
        <label>默认文件命名模板</label>
        <input v-model="settings.output_template" type="text" />
      </div>
    </div>

    <div class="card">
      <h3 class="section-title">网络设置</h3>

      <div class="form-group">
        <label>代理 (Proxy)</label>
        <input v-model="settings.proxy" type="text" placeholder="http://127.0.0.1:7890 或 socks5://..." />
      </div>

      <div class="form-group">
        <label>Cookie 来源浏览器</label>
        <select v-model="settings.cookie_browser">
          <option value="">不使用 Cookie</option>
          <option v-for="b in browsers" :key="b" :value="b">{{ b }}</option>
        </select>
      </div>
    </div>

    <div class="card">
      <h3 class="section-title">媒体设置</h3>

      <div class="form-row">
        <div class="form-group">
          <label class="checkbox-label">
            <input type="checkbox" v-model="settings.embed_metadata" />
            嵌入元数据
          </label>
        </div>
        <div class="form-group">
          <label class="checkbox-label">
            <input type="checkbox" v-model="settings.embed_thumbnail" />
            嵌入缩略图
          </label>
        </div>
      </div>

      <div class="form-row">
        <div class="form-group">
          <label class="checkbox-label">
            <input type="checkbox" v-model="settings.write_subs" />
            默认下载字幕
          </label>
        </div>
        <div class="form-group">
          <label>字幕语言</label>
          <input v-model="settings.sub_languages" type="text" placeholder="zh-Hans,en" />
        </div>
      </div>
    </div>

    <div class="card">
      <h3 class="section-title">系统信息</h3>
      <div class="meta">
        <div>FFmpeg: <span :style="{ color: ffmpegOk ? 'var(--success)' : 'var(--warning)' }">
          {{ ffmpegOk ? '✓ 可用' : '✗ 未找到' }}
        </span></div>
      </div>
    </div>

    <div style="margin-top: 20px;">
      <button class="btn btn-primary" @click="save" :disabled="saving">
        {{ saving ? '保存中...' : '保存设置' }}
      </button>
      <span v-if="saved" style="color: var(--success); margin-left: 12px; font-size: 0.85rem;">
        ✓ 已保存
      </span>
    </div>

    <!-- Directory Picker Modal -->
    <div v-if="showDirPicker" class="modal-overlay" @click.self="showDirPicker = false">
      <div class="modal dir-modal">
        <div class="dir-modal-header">
          <h3>选择目录</h3>
          <button
            v-if="currentPath"
            class="btn btn-icon"
            @click="goUpDir"
            title="上一级"
          ></button>
        </div>
        <div class="dir-breadcrumb">{{ currentPath || '我的电脑' }}</div>
        <div class="dir-path-input-row">
          <input
            v-model="manualPath"
            type="text"
            class="dir-path-input"
            placeholder="手动输入路径，如 C:\Users\Downloads"
            @keydown.enter="navigateToManualPath"
          />
          <button class="btn btn-secondary dir-path-go-btn" @click="navigateToManualPath" title="前往">前往</button>
        </div>
        <div class="dir-list">
          <div
            v-for="item in dirItems"
            :key="item.path"
            class="dir-tree-item"
            @click="navigateDir(item.path)"
            @dblclick="selectDir"
          >
            <span class="dir-item-icon">{{ currentPath ? '📁' : '💿' }}</span>
            <span class="dir-item-name">{{ item.name }}</span>
          </div>
          <div v-if="dirItems.length === 0" class="dir-empty">
            此目录为空或无权限访问
          </div>
        </div>
        <div class="dir-modal-footer">
          <button class="btn btn-primary" @click="selectDir" :disabled="!currentPath">选择此目录</button>
          <button class="btn btn-secondary" @click="showDirPicker = false">取消</button>
        </div>
      </div>
    </div>

    <div class="footer-signature">
      <span class="sig-line"></span>
      <span class="sig-name">王小氢</span>
      <span class="sig-line"></span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { getSettings, updateSettings, getBrowsers, getDirectories, checkFfmpeg } from '../api/settings'
import type { Settings } from '../api/settings'

const settings = ref<Settings>({
  download_dir: '',
  max_concurrent: 3,
  output_template: '%(title)s.%(ext)s',
  embed_metadata: true,
  embed_thumbnail: false,
  write_subs: false,
  sub_languages: 'zh-Hans,en',
  theme: 'light',
})

const browsers = ref<string[]>([])
const ffmpegOk = ref(false)
const saving = ref(false)
const saved = ref(false)

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
    if (result.error) {
      currentPath.value = p
      dirItems.value = []
    } else {
      currentPath.value = result.path
      dirItems.value = result.children || []
    }
  } catch (e) {
    currentPath.value = p
    dirItems.value = []
  }
}

async function save() {
  saving.value = true
  saved.value = false
  try {
    await updateSettings(settings.value)
    saved.value = true
    setTimeout(() => (saved.value = false), 2000)
  } finally {
    saving.value = false
  }
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

function goUpDir() {
  if (!currentPath.value) return
  const parent = currentPath.value.replace(/[^\\\/]+[\\\/]?$/, '')
  if (parent && parent !== currentPath.value) {
    navigateDir(parent)
  } else {
    currentPath.value = ''
    getDirectories('').then(r => { dirItems.value = r.children || [] })
  }
}

function selectDir() {
  settings.value.download_dir = currentPath.value
  showDirPicker.value = false
}

onMounted(async () => {
  try {
    settings.value = await getSettings()
    browsers.value = await getBrowsers()
    const ff = await checkFfmpeg()
    ffmpegOk.value = ff.available
  } catch (e) {
    console.error('Failed to load settings:', e)
  }
})
</script>

<style scoped>
.page-title {
  font-size: 1.4rem;
  margin-bottom: 20px;
}

.dir-picker {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg-input);
  transition: border-color 0.15s;
}

.dir-picker:hover {
  border-color: var(--primary);
}

.dir-icon {
  font-size: 1.1rem;
  flex-shrink: 0;
}

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

.dir-breadcrumb {
  font-size: 0.85rem;
  color: var(--text-muted);
  padding: 8px 0;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--border);
}

.dir-list {
  max-height: 300px;
  overflow-y: auto;
}

.dir-modal {
  width: 520px;
}

.dir-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.dir-modal-header h3 {
  margin: 0;
}

.dir-item-icon {
  font-size: 1rem;
  flex-shrink: 0;
}

.dir-item-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dir-empty {
  padding: 20px;
  text-align: center;
  color: var(--text-muted);
  font-size: 0.85rem;
}

.dir-modal-footer {
  margin-top: 16px;
  display: flex;
  gap: 8px;
}

.btn-icon {
  background: none;
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  padding: 4px 10px;
  font-size: 1.1rem;
  color: var(--text);
  line-height: 1;
}

.btn-icon:hover {
  border-color: var(--primary);
  color: var(--primary);
}

.btn-icon::before {
  content: '↑';
}

.meta {
  font-size: 0.9rem;
  color: var(--text-muted);
}
</style>
