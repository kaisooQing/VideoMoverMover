<template>
  <div class="settings-view">
    <div class="page-header">
      <div class="page-title">设置</div>
    </div>

    <div class="card">
      <h3 class="section-title">下载设置</h3>

      <div class="form-group">
        <label>最大并发数</label>
        <input v-model.number="settings.max_concurrent" type="number" min="1" max="5" />
      </div>

      <div class="form-group">
        <label>文件命名模板</label>
        <input v-model="settings.output_template" type="text" placeholder="%(title)s.%(ext)s" />
      </div>
    </div>

    <div class="card">
      <h3 class="section-title">字幕</h3>

      <label class="checkbox-label">
        <input type="checkbox" v-model="settings.write_subs" /> 自动下载字幕
      </label>

      <div v-if="settings.write_subs" class="form-group" style="margin-top: 8px;">
        <label>字幕语言</label>
        <input v-model="settings.sub_languages" type="text" placeholder="zh-Hans,en" />
      </div>
    </div>

    <div class="card">
      <h3 class="section-title">元数据</h3>

      <label class="checkbox-label">
        <input type="checkbox" v-model="settings.embed_metadata" /> 嵌入元数据
      </label>
      <label class="checkbox-label">
        <input type="checkbox" v-model="settings.embed_thumbnail" /> 嵌入封面图
      </label>
    </div>

    <div class="card">
      <h3 class="section-title">系统信息</h3>
      <div class="sys-info">
        <div>FFmpeg:
          <span :class="ffmpegOk ? 'text-success' : 'text-warning'">
            {{ ffmpegOk ? '✓ 可用' : '✗ 未找到' }}
          </span>
        </div>
        <div>下载目录:
          <span class="text-muted">{{ settings.download_dir || '默认' }}</span>
        </div>
      </div>
    </div>

    <button class="btn btn-primary btn-block" @click="save" :disabled="saving" style="margin-top: 16px;">
      {{ saving ? '保存中...' : '保存设置' }}
    </button>
    <div v-if="saved" class="save-toast">✓ 已保存</div>

    <div class="footer-signature">
      <span class="sig-line"></span>
      <span class="sig-name">王小氢</span>
      <span class="sig-line"></span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getSettings, updateSettings, checkFfmpeg } from '../api/settings'
import type { Settings } from '../api/settings'

const settings = ref<Settings>({
  download_dir: '',
  max_concurrent: 3,
  output_template: '%(title)s.%(ext)s',
  embed_metadata: true,
  embed_thumbnail: false,
  write_subs: false,
  sub_languages: 'zh-Hans,en',
  theme: 'dark',
})

const ffmpegOk = ref(false)
const saving = ref(false)
const saved = ref(false)

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

onMounted(async () => {
  try {
    settings.value = await getSettings()
    const ff = await checkFfmpeg()
    ffmpegOk.value = ff.available
  } catch (e) {
    console.error('Failed to load settings:', e)
  }
})
</script>

<style scoped>
.section-title {
  border-left: 3px solid var(--primary);
  padding-left: 10px;
  font-weight: 600;
  font-size: 0.95rem;
}

.card {
  transition: all 0.2s ease;
}

.sys-info {
  font-size: 0.85rem;
  color: var(--text-muted);
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.sys-info > div {
  display: flex;
  align-items: center;
  border-bottom: 1px solid var(--border);
  padding-bottom: 10px;
}

.sys-info > div::before {
  content: '';
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--primary);
  margin-right: 8px;
  flex-shrink: 0;
}

.sys-info > div:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.text-success {
  color: var(--success);
  text-shadow: 0 0 8px rgba(34, 197, 94, 0.3);
}

.text-warning {
  color: var(--warning);
  text-shadow: 0 0 8px rgba(245, 158, 11, 0.3);
}

.text-muted { color: var(--text-muted); font-size: 0.8rem; word-break: break-all; }

.save-toast {
  text-align: center;
  color: var(--success);
  font-size: 0.85rem;
  margin-top: 10px;
  background: rgba(34, 197, 94, 0.1);
  border: 1px solid rgba(34, 197, 94, 0.2);
  padding: 10px 16px;
  border-radius: 10px;
  display: inline-block;
}

:deep(.btn-primary) {
  height: 48px;
  font-size: 1rem;
  font-weight: 600;
  letter-spacing: 0.5px;
  background: linear-gradient(135deg, #818cf8, #a78bfa);
  box-shadow: 0 4px 15px rgba(129, 140, 248, 0.3);
  border-radius: 12px;
}

.checkbox-label {
  border-radius: 8px;
  padding: 10px 12px;
  transition: background 0.15s;
  display: flex;
  align-items: center;
  cursor: pointer;
}

.checkbox-label:hover {
  background: rgba(255, 255, 255, 0.05);
}

.checkbox-label input[type="checkbox"] {
  width: 20px;
  height: 20px;
  accent-color: #818cf8;
  margin-right: 8px;
}

label {
  font-weight: 500;
  color: #9ca3af;
}
</style>
