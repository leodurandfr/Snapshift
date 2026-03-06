<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useTagsStore } from '@/stores/tags'
import type { MonitoredURL, URLCreatePayload, URLUpdatePayload } from '@/types'

const props = defineProps<{
  url?: MonitoredURL | null
}>()

const emit = defineEmits<{
  submit: [data: URLCreatePayload | URLUpdatePayload]
  cancel: []
}>()

const tagsStore = useTagsStore()
onMounted(() => tagsStore.fetchTags())

const isEditing = computed(() => !!props.url)

const form = ref({
  url: props.url?.url ?? '',
  label: props.url?.label ?? '',
  schedule: props.url?.schedule ?? 'daily',
  change_threshold: props.url?.change_threshold ?? 0.02,
  full_page: props.url?.full_page ?? true,
  archive_enabled: props.url?.archive_enabled ?? true,
  dismiss_cookies: props.url?.dismiss_cookies ?? true,
  selectedTagIds: props.url?.tags?.map(t => t.id) ?? [] as string[],
})

const scheduleOptions = [
  { value: 'every_1h', label: 'Every hour' },
  { value: 'every_2h', label: 'Every 2 hours' },
  { value: 'every_6h', label: 'Every 6 hours' },
  { value: 'every_12h', label: 'Every 12 hours' },
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
]

function toggleTag(tagId: string) {
  const idx = form.value.selectedTagIds.indexOf(tagId)
  if (idx >= 0) {
    form.value.selectedTagIds.splice(idx, 1)
  } else {
    form.value.selectedTagIds.push(tagId)
  }
}

function normalizeUrl(raw: string): string {
  let url = raw.trim()
  if (url && !/^https?:\/\//i.test(url)) {
    url = `https://${url}`
  }
  return url
}

function handleSubmit() {
  const data: URLCreatePayload | URLUpdatePayload = {
    url: normalizeUrl(form.value.url),
    label: form.value.label || undefined,
    schedule: form.value.schedule,
    change_threshold: form.value.change_threshold,
    full_page: form.value.full_page,
    archive_enabled: form.value.archive_enabled,
    dismiss_cookies: form.value.dismiss_cookies,
    tag_ids: form.value.selectedTagIds,
  }
  emit('submit', data)
}
</script>

<template>
  <form class="space-y-4" @submit.prevent="handleSubmit">
    <!-- URL -->
    <div class="space-y-1.5">
      <label class="text-sm font-medium">URL</label>
      <Input v-model="form.url" placeholder="https://example.com" required />
    </div>

    <!-- Label -->
    <div class="space-y-1.5">
      <label class="text-sm font-medium">Label (optional)</label>
      <Input v-model="form.label" placeholder="My website" />
    </div>

    <!-- Schedule -->
    <div class="space-y-1.5">
      <label class="text-sm font-medium">Capture frequency</label>
      <Select v-model="form.schedule">
        <SelectTrigger>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem v-for="opt in scheduleOptions" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </SelectItem>
        </SelectContent>
      </Select>
    </div>

    <!-- Tags -->
    <div class="space-y-1.5">
      <label class="text-sm font-medium">Tags</label>
      <div class="flex flex-wrap gap-2">
        <button
          v-for="tag in tagsStore.tags"
          :key="tag.id"
          type="button"
          class="px-2.5 py-1 rounded-full text-xs border transition-colors"
          :class="form.selectedTagIds.includes(tag.id) ? 'bg-primary text-primary-foreground' : 'bg-background text-foreground hover:bg-accent'"
          :style="form.selectedTagIds.includes(tag.id) ? { backgroundColor: tag.color, borderColor: tag.color } : { borderColor: tag.color, color: tag.color }"
          @click="toggleTag(tag.id)"
        >
          {{ tag.name }}
        </button>
        <span v-if="tagsStore.tags.length === 0" class="text-xs text-muted-foreground">
          No tags yet
        </span>
      </div>
    </div>

    <!-- Options checkboxes -->
    <div class="space-y-2">
      <label class="flex items-center gap-2 text-sm">
        <input type="checkbox" v-model="form.full_page" class="rounded" />
        Full page screenshot
      </label>
      <label class="flex items-center gap-2 text-sm">
        <input type="checkbox" v-model="form.archive_enabled" class="rounded" />
        Save page archive
      </label>
      <label class="flex items-center gap-2 text-sm">
        <input type="checkbox" v-model="form.dismiss_cookies" class="rounded" />
        Auto-dismiss cookie banners
      </label>
    </div>

    <!-- Actions -->
    <div class="flex gap-2 pt-2">
      <Button type="submit">{{ isEditing ? 'Update' : 'Add URL' }}</Button>
      <Button type="button" variant="outline" @click="$emit('cancel')">Cancel</Button>
    </div>
  </form>
</template>
