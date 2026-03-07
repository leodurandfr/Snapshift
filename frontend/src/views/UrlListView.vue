<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import TagBadge from '@/components/tags/TagBadge.vue'
import UrlForm from '@/components/urls/UrlForm.vue'
import { Loader2 } from 'lucide-vue-next'
import { useUrlsStore } from '@/stores/urls'
import { useTagsStore } from '@/stores/tags'
import { useCapturesStore } from '@/stores/captures'
import { useJobsStore } from '@/stores/jobs'
import type { URLCreatePayload, URLUpdatePayload } from '@/types'

const router = useRouter()
const urlsStore = useUrlsStore()
const tagsStore = useTagsStore()
const capturesStore = useCapturesStore()
const jobsStore = useJobsStore()

const search = ref('')
const activeTag = ref<string | undefined>(undefined)
const showAddDialog = ref(false)
const capturingIds = ref<Set<string>>(new Set())

onMounted(async () => {
  await Promise.all([urlsStore.fetchUrls(), tagsStore.fetchTags()])
})

// Refresh URL list (thumbnails) when any capture completes
const unsubscribe = jobsStore.onCompletion(async () => {
  await urlsStore.fetchUrls({ search: search.value || undefined, tag: activeTag.value })
})
onUnmounted(() => unsubscribe())

async function handleSearch() {
  await urlsStore.fetchUrls({ search: search.value || undefined, tag: activeTag.value })
}

async function filterByTag(tagName: string | undefined) {
  activeTag.value = activeTag.value === tagName ? undefined : tagName
  await urlsStore.fetchUrls({ search: search.value || undefined, tag: activeTag.value })
}

async function handleAdd(data: URLCreatePayload | URLUpdatePayload) {
  try {
    await urlsStore.createUrl(data as URLCreatePayload)
    showAddDialog.value = false
    toast.success('URL added successfully')
  } catch (e: any) {
    toast.error(e.response?.data?.detail || 'Failed to add URL')
  }
}

async function handleCaptureNow(id: string) {
  capturingIds.value.add(id)
  capturingIds.value = new Set(capturingIds.value)
  try {
    await urlsStore.captureNow(id)
    toast.success('Capture job queued')
  } catch {
    toast.error('Failed to queue capture')
  } finally {
    capturingIds.value.delete(id)
    capturingIds.value = new Set(capturingIds.value)
  }
}

function formatSchedule(schedule: string): string {
  const map: Record<string, string> = {
    every_1h: '1h', every_2h: '2h', every_6h: '6h', every_12h: '12h',
    daily: 'Daily', weekly: 'Weekly', monthly: 'Monthly',
  }
  return map[schedule] || schedule
}
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold">Monitored URLs</h1>
        <p class="text-muted-foreground text-sm mt-1">{{ urlsStore.total }} URLs monitored</p>
      </div>
      <Button @click="showAddDialog = true">Add URL</Button>
    </div>

    <!-- Filters -->
    <div class="flex items-center gap-3">
      <Input
        v-model="search"
        placeholder="Search URLs..."
        class="max-w-xs"
        @keyup.enter="handleSearch"
      />
      <div class="flex gap-1.5 flex-wrap">
        <button
          v-for="tag in tagsStore.tags"
          :key="tag.id"
          class="px-2.5 py-1 rounded-full text-xs border transition-colors"
          :class="activeTag === tag.name ? 'text-white' : 'hover:bg-accent'"
          :style="activeTag === tag.name ? { backgroundColor: tag.color, borderColor: tag.color } : { borderColor: tag.color, color: tag.color }"
          @click="filterByTag(tag.name)"
        >
          {{ tag.name }}
        </button>
      </div>
    </div>

    <!-- Table -->
    <div class="border rounded-lg">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead class="w-16">Preview</TableHead>
            <TableHead>URL</TableHead>
            <TableHead>Tags</TableHead>
            <TableHead>Schedule</TableHead>
            <TableHead>Status</TableHead>
            <TableHead class="w-40">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow
            v-for="url in urlsStore.urls"
            :key="url.id"
            class="cursor-pointer hover:bg-muted/50"
            @click="router.push(`/urls/${url.id}`)"
          >
            <TableCell>
              <div class="w-12 h-8 bg-muted rounded overflow-hidden">
                <img
                  v-if="url.last_thumbnail"
                  :src="capturesStore.thumbnailUrl(url.id)"
                  class="w-full h-full object-cover"
                  alt=""
                />
              </div>
            </TableCell>
            <TableCell>
              <div>
                <p class="font-medium text-sm truncate max-w-xs">{{ url.label || url.url }}</p>
                <p v-if="url.label" class="text-xs text-muted-foreground truncate max-w-xs">{{ url.url }}</p>
              </div>
            </TableCell>
            <TableCell>
              <div class="flex gap-1 flex-wrap">
                <TagBadge v-for="tag in url.tags" :key="tag.id" :name="tag.name" :color="tag.color" />
              </div>
            </TableCell>
            <TableCell>
              <span class="text-sm">{{ formatSchedule(url.schedule) }}</span>
            </TableCell>
            <TableCell>
              <Badge
                :variant="url.is_active ? 'default' : 'secondary'"
                class="text-xs"
              >
                {{ url.is_active ? 'Active' : 'Paused' }}
              </Badge>
            </TableCell>
            <TableCell @click.stop>
              <Button
                size="sm"
                variant="outline"
                :disabled="capturingIds.has(url.id) || jobsStore.hasActiveJobs(url.id)"
                @click="handleCaptureNow(url.id)"
              >
                <Loader2 v-if="capturingIds.has(url.id) || jobsStore.hasActiveJobs(url.id)" class="w-4 h-4 mr-1 animate-spin" />
                {{ capturingIds.has(url.id) ? 'Queuing...' : jobsStore.hasActiveJobs(url.id) ? 'Capturing...' : 'Capture now' }}
              </Button>
            </TableCell>
          </TableRow>
          <TableRow v-if="urlsStore.urls.length === 0 && !urlsStore.loading">
            <TableCell :colspan="6" class="text-center py-8 text-muted-foreground">
              No URLs monitored yet. Add your first URL to get started.
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>

    <!-- Add URL Dialog -->
    <Dialog v-model:open="showAddDialog">
      <DialogContent class="max-w-lg">
        <DialogHeader>
          <DialogTitle>Add URL to monitor</DialogTitle>
        </DialogHeader>
        <UrlForm @submit="handleAdd" @cancel="showAddDialog = false" />
      </DialogContent>
    </Dialog>
  </div>
</template>
