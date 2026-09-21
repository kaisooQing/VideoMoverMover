import { ref, onUnmounted } from 'vue'

interface ProgressMessage {
  task_id: string
  status: string
  progress_pct: number
  title?: string
  thumbnail?: string
  speed?: string
  eta?: string
  filename?: string
  filesize?: string
  error?: string
  url?: string
  created_at?: number
  completed_at?: number
}

const connected = ref(false)
let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
const listeners = new Set<(msg: ProgressMessage) => void>()

function connect() {
  if (ws?.readyState === WebSocket.OPEN) return

  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
  const url = `${protocol}//${location.host}/ws/progress`

  ws = new WebSocket(url)

  ws.onopen = () => {
    connected.value = true
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  ws.onclose = () => {
    connected.value = false
    reconnectTimer = setTimeout(connect, 3000)
  }

  ws.onerror = () => {
    ws?.close()
  }

  ws.onmessage = (event) => {
    try {
      const msg: ProgressMessage = JSON.parse(event.data)
      listeners.forEach((fn) => fn(msg))
    } catch (e) {
      console.error('WebSocket parse error:', e)
    }
  }
}

export function useWebSocket() {
  connect()

  onUnmounted(() => {
    // Don't disconnect on unmount since it's shared
  })

  return { connected }
}

export function onProgress(fn: (msg: ProgressMessage) => void) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

export type { ProgressMessage }
