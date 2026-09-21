import { ref, onMounted, onUnmounted } from 'vue'

interface ProgressMessage {
  task_id: string
  status: string
  title?: string
  thumbnail?: string
  progress_pct: number
  speed?: string
  eta?: string
  filename?: string
  filesize?: string
  error?: string
  completed_at?: number
  created_at?: number
}

export function useWebSocket(onMessage: (msg: ProgressMessage) => void) {
  const connected = ref(false)
  let ws: WebSocket | null = null
  let reconnectTimer: number | null = null

  function connect() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${window.location.host}/ws/progress`

    ws = new WebSocket(url)

    ws.onopen = () => {
      connected.value = true
      // Subscribe to all task updates
      ws!.send(JSON.stringify({ subscribe_all: true }))
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as ProgressMessage
        onMessage(msg)
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e)
      }
    }

    ws.onclose = () => {
      connected.value = false
      // Auto-reconnect after 2 seconds
      reconnectTimer = window.setTimeout(() => connect(), 2000)
    }

    ws.onerror = () => {
      ws?.close()
    }
  }

  function disconnect() {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    ws?.close()
    ws = null
  }

  onMounted(() => connect())
  onUnmounted(() => disconnect())

  return { connected, disconnect }
}
