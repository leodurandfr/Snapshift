import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '@/lib/api'
import type { Tag, TagCreatePayload } from '@/types'

export const useTagsStore = defineStore('tags', () => {
  const tags = ref<Tag[]>([])
  const loading = ref(false)

  async function fetchTags() {
    loading.value = true
    try {
      const { data } = await api.get('/tags')
      tags.value = data
    } finally {
      loading.value = false
    }
  }

  async function createTag(payload: TagCreatePayload): Promise<Tag> {
    const { data } = await api.post('/tags', payload)
    await fetchTags()
    return data
  }

  async function deleteTag(id: string) {
    await api.delete(`/tags/${id}`)
    await fetchTags()
  }

  return {
    tags,
    loading,
    fetchTags,
    createTag,
    deleteTag,
  }
})
