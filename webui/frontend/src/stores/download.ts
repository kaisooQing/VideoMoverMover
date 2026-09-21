import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useWebSocket } from '../composables/useWebSocket'
import type { DownloadTask } from '../api/downloads'
import { createDownload, listDownloads, cancelDownload } from '../api/downloads'
import type { DownloadRequest } from '../api/downloads'

export const useDownloadStore = defineStore('download', () => {
  const tasks = ref<Map<string, DownloadTask>>(new Map())
  const submitting = ref(false)

  const { connected } = useWebSocket((msg) => {
    const task = tasks.value.get(msg.task_id)
    if (task) {
      // Update existing task
      Object.assign(task, msg)
    } else {
      // New task from server
      tasks.value.set(msg.task_id, {
        id: msg.task_id,
        url: '',
        status: msg.status,
        title: msg.title,
        thumbnail: msg.thumbnail,
        progress_pct: msg.progress_pct,
        speed: msg.speed,
        eta: msg.eta,
        filename: msg.filename,
        filesize: msg.filesize,
        error: msg.error,
        created_at: msg.created_at || Date.now() / 1000,
        completed_at: msg.completed_at,
      })
    }
    // Trigger reactivity
    tasks.value = new Map(tasks.value)
  })

  const activeTasks = computed(() => {
    return Array.from(tasks.value.values()).filter(
      (t) => ['queued', 'downloading', 'processing'].includes(t.status)
    )
  })

  const completedTasks = computed(() => {
    return Array.from(tasks.value.values())
      .filter((t) => ['completed', 'failed', 'cancelled'].includes(t.status))
      .sort((a, b) => (b.completed_at || 0) - (a.completed_at || 0))
  })

  async function submitDownload(req: DownloadRequest) {
    submitting.value = true

    // Optimistic update: show placeholder tasks immediately
    const pendingIds: string[] = []
    const now = Date.now() / 1000
    for (let i = 0; i < req.urls.length; i++) {
      const pid = `pending-${now}-${i}`
      pendingIds.push(pid)
      tasks.value.set(pid, {
        id: pid,
        url: req.urls[i],
        status: 'queued',
        title: req.urls[i],
        thumbnail: undefined,
        progress_pct: 0,
        speed: undefined,
        eta: undefined,
        filename: undefined,
        filesize: undefined,
        error: undefined,
        created_at: now,
        completed_at: undefined,
      })
    }
    tasks.value = new Map(tasks.value)

    try {
      const { task_ids } = await createDownload(req)
      // Remove placeholders
      for (const pid of pendingIds) {
        tasks.value.delete(pid)
      }
      // Fetch full task info for real tasks
      const all = await listDownloads()
      for (const t of all) {
        if (task_ids.includes(t.id)) {
          tasks.value.set(t.id, t)
        }
      }
      tasks.value = new Map(tasks.value)
      return task_ids
    } catch (e) {
      // On error, remove placeholders
      for (const pid of pendingIds) {
        tasks.value.delete(pid)
      }
      tasks.value = new Map(tasks.value)
      throw e
    } finally {
      submitting.value = false
    }
  }

  async function cancel(taskId: string) {
    await cancelDownload(taskId)
    const task = tasks.value.get(taskId)
    if (task) {
      task.status = 'cancelled'
      tasks.value = new Map(tasks.value)
    }
  }

  async function refreshTasks() {
    const all = await listDownloads()
    for (const t of all) {
      tasks.value.set(t.id, t)
    }
    tasks.value = new Map(tasks.value)
  }

  return {
    tasks,
    connected,
    submitting,
    activeTasks,
    completedTasks,
    submitDownload,
    cancel,
    refreshTasks,
  }
})
