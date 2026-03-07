import { useJobsStore } from '@/stores/jobs'

let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let reconnectDelay = 1000

export function connectWebSocket() {
  const token = import.meta.env.VITE_API_TOKEN
  if (!token) return

  const baseUrl = (import.meta.env.VITE_API_URL || 'http://localhost:8000/api')
    .replace(/\/api\/?$/, '')
    .replace(/^http/, 'ws')

  ws = new WebSocket(`${baseUrl}/ws?token=${token}`)

  ws.onopen = () => {
    reconnectDelay = 1000
  }

  ws.onmessage = (event) => {
    const jobsStore = useJobsStore()
    const data = JSON.parse(event.data)

    if (data.type === 'init') {
      jobsStore.handleInit(data.jobs)
    } else if (data.type === 'job_update') {
      jobsStore.handleJobUpdate(data.job)
    }
  }

  ws.onclose = () => {
    ws = null
    scheduleReconnect()
  }

  ws.onerror = () => {
    ws?.close()
  }
}

function scheduleReconnect() {
  if (reconnectTimer) return
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    reconnectDelay = Math.min(reconnectDelay * 2, 30000)
    connectWebSocket()
  }, reconnectDelay)
}

export function disconnectWebSocket() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  ws?.close()
  ws = null
}
