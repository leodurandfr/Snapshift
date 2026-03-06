import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/lib/api'
import type { CaptureJob, MonitoredURL, URLCreatePayload, URLUpdatePayload } from '@/types'

export const useUrlsStore = defineStore('urls', () => {
  const urls = ref<MonitoredURL[]>([])
  const total = ref(0)
  const loading = ref(false)
  const currentUrl = ref<MonitoredURL | null>(null)

  async function fetchUrls(params?: { tag?: string; search?: string; is_active?: boolean; offset?: number; limit?: number }) {
    loading.value = true
    try {
      const { data } = await api.get('/urls', { params })
      urls.value = data.items
      total.value = data.total
    } finally {
      loading.value = false
    }
  }

  async function fetchUrl(id: string) {
    loading.value = true
    try {
      const { data } = await api.get(`/urls/${id}`)
      currentUrl.value = data
      return data
    } finally {
      loading.value = false
    }
  }

  async function createUrl(payload: URLCreatePayload): Promise<MonitoredURL> {
    const { data } = await api.post('/urls', payload)
    await fetchUrls()
    return data
  }

  async function updateUrl(id: string, payload: URLUpdatePayload): Promise<MonitoredURL> {
    const { data } = await api.put(`/urls/${id}`, payload)
    await fetchUrls()
    return data
  }

  async function deleteUrl(id: string) {
    await api.delete(`/urls/${id}`)
    await fetchUrls()
  }

  async function captureNow(id: string): Promise<CaptureJob[]> {
    const { data } = await api.post(`/urls/${id}/capture-now`)
    return data
  }

  async function fetchJobs(urlId: string): Promise<CaptureJob[]> {
    const { data } = await api.get(`/urls/${urlId}/jobs`)
    return data
  }

  return {
    urls,
    total,
    loading,
    currentUrl,
    fetchUrls,
    fetchUrl,
    createUrl,
    updateUrl,
    deleteUrl,
    captureNow,
    fetchJobs,
  }
})
