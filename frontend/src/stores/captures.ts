import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/lib/api'
import type { Capture } from '@/types'

const API_TOKEN = import.meta.env.VITE_API_TOKEN || ''

export const useCapturesStore = defineStore('captures', () => {
  const captures = ref<Capture[]>([])
  const total = ref(0)
  const loading = ref(false)

  async function fetchCaptures(params?: { url_id?: string; viewport_label?: string; offset?: number; limit?: number }) {
    loading.value = true
    try {
      const { data } = await api.get('/captures', { params })
      captures.value = data.items
      total.value = data.total
    } finally {
      loading.value = false
    }
  }

  function screenshotUrl(captureId: string): string {
    const baseUrl = api.defaults.baseURL || ''
    return `${baseUrl}/captures/${captureId}/screenshot?token=${API_TOKEN}`
  }

  function thumbnailUrl(captureId: string): string {
    const baseUrl = api.defaults.baseURL || ''
    return `${baseUrl}/captures/${captureId}/thumbnail?token=${API_TOKEN}`
  }

  function archiveUrl(captureId: string): string {
    const baseUrl = api.defaults.baseURL || ''
    return `${baseUrl}/captures/${captureId}/archive?token=${API_TOKEN}`
  }

  function archivePreviewUrl(captureId: string): string {
    const baseUrl = api.defaults.baseURL || ''
    return `${baseUrl}/captures/${captureId}/archive-preview?token=${API_TOKEN}`
  }

  async function deleteCaptures(ids: string[]) {
    await api.post('/captures/delete-batch', { capture_ids: ids })
    captures.value = captures.value.filter(c => !ids.includes(c.id))
    total.value = captures.value.length
  }

  return {
    captures,
    total,
    loading,
    fetchCaptures,
    deleteCaptures,
    screenshotUrl,
    thumbnailUrl,
    archiveUrl,
    archivePreviewUrl,
  }
})
