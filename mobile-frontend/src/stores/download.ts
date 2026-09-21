import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { listDownloads, createDownload, cancelDownload } from '../api/downloads'
import { onProgress } from '../composables/useWebSocket'
import type { DownloadTask, DownloadRequest } from '../api/downloads'

export const useDownloadStore = defineStore('download', () => {
  const tasks = ref<DownloadTask[]>([])
  const submitting = ref(false)

  const activeTasks = computed(() =>
    tasks.value
      .filter((t) => ['queued', 'starting', 'downloading', 'processing'].includes(t.status))
      .sort((a, b) => (b.created_at || 0) - (a.created_at || 0))
  )

  const completedTasks = computed(() =>
    [...tasks.value]
      .filter((t) => ['completed', 'failed', 'cancelled'].includes(t.status))
      .sort((a, b) => (b.completed_at || b.created_at || 0) - (a.completed_at || a.created_at || 0))
  )

  // Listen for WebSocket progress updates
  onProgress((msg) => {
    const idx = tasks.value.findIndex((t) => t.id === msg.task_id)
    if (idx >= 0) {
      // Update existing task (placeholder or real)
      const task = tasks.value[idx]
      task.status = msg.status
      task.progress_pct = msg.progress_pct
      if (msg.title) task.title = msg.title
      if (msg.thumbnail) task.thumbnail = msg.thumbnail
      if (msg.speed) task.speed = msg.speed
      if (msg.eta) task.eta = msg.eta
      if (msg.filename) task.filename = msg.filename
      if (msg.filesize) task.filesize = msg.filesize
      if (msg.error) task.error = msg.error
      if (msg.completed_at !== undefined) task.completed_at = msg.completed_at
      if (msg.created_at !== undefined) task.created_at = msg.created_at
    } else {
      // New task from WebSocket - but check if a placeholder with same URL exists
      const placeholderIdx = tasks.value.findIndex(
        (t) => t.url === (msg.url || '') && t.id.startsWith('opt_')
      )
      if (placeholderIdx >= 0) {
        // Replace placeholder with real task data
        tasks.value[placeholderIdx] = {
          id: msg.task_id,
          url: msg.url || '',
          status: msg.status,
          title: msg.title,
          thumbnail: msg.thumbnail,
          progress_pct: msg.progress_pct,
          speed: msg.speed,
          eta: msg.eta,
          filename: msg.filename,
          filesize: msg.filesize,
          error: msg.error,
          created_at: msg.created_at || Math.floor(Date.now() / 1000),
          completed_at: msg.completed_at,
        }
      } else {
        // Truly new task
        tasks.value.push({
          id: msg.task_id,
          url: msg.url || '',
          status: msg.status,
          title: msg.title,
          thumbnail: msg.thumbnail,
          progress_pct: msg.progress_pct,
          speed: msg.speed,
          eta: msg.eta,
          filename: msg.filename,
          filesize: msg.filesize,
          error: msg.error,
          created_at: msg.created_at || Math.floor(Date.now() / 1000),
          completed_at: msg.completed_at,
        })
      }
    }
  })

  async function refreshTasks() {
    try {
      tasks.value = await listDownloads()
    } catch (e) {
      console.error('Failed to load tasks:', e)
    }
  }

  async function submitDownload(req: DownloadRequest) {
    submitting.value = true
    try {
      // Optimistic update: create placeholder tasks immediately
      for (const url of req.urls) {
        const placeholderId = 'opt_' + Math.random().toString(36).slice(2, 8)
        tasks.value.unshift({
          id: placeholderId,
          url,
          status: 'queued',
          progress_pct: 0,
          title: '解析中...',
          created_at: Math.floor(Date.now() / 1000),
        })
      }

      const { task_ids } = await createDownload(req)

      // Replace placeholders with real task IDs
      for (let i = 0; i < req.urls.length; i++) {
        const url = req.urls[i]
        const realId = task_ids[i]
        // Check if WebSocket already created the real task
        const realIdx = tasks.value.findIndex((t) => t.id === realId)
        const phIdx = tasks.value.findIndex((t) => t.url === url && t.id.startsWith('opt_'))
        if (realIdx >= 0 && phIdx >= 0) {
          // WebSocket already pushed this task, remove the orphaned placeholder
          tasks.value.splice(phIdx, 1)
        } else if (phIdx >= 0) {
          // WebSocket hasn't pushed yet, rename placeholder
          tasks.value[phIdx].id = realId
          tasks.value[phIdx].title = undefined
        }
      }
      // WebSocket will push real-time updates, no need to refresh full list
    } catch (e) {
      console.error('Submit failed:', e)
      // Remove optimistic placeholders on failure
      tasks.value = tasks.value.filter((t) => !t.id.startsWith('opt_'))
      throw e
    } finally {
      submitting.value = false
    }
  }

  async function cancel(taskId: string) {
    try {
      await cancelDownload(taskId)
      const task = tasks.value.find((t) => t.id === taskId)
      if (task) task.status = 'cancelled'
    } catch (e) {
      console.error('Cancel failed:', e)
    }
  }

  return {
    tasks,
    submitting,
    activeTasks,
    completedTasks,
    refreshTasks,
    submitDownload,
    cancel,
  }
})
