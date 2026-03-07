<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Globe, Loader2 } from 'lucide-vue-next'
import TagBadge from '@/components/tags/TagBadge.vue'
import UrlForm from '@/components/urls/UrlForm.vue'
import ArchiveViewer from '@/components/captures/ArchiveViewer.vue'
import { useUrlsStore } from '@/stores/urls'
import { useCapturesStore } from '@/stores/captures'
import { useJobsStore } from '@/stores/jobs'
import api from '@/lib/api'
import type { Capture, URLUpdatePayload } from '@/types'

const route = useRoute()
const router = useRouter()
const urlsStore = useUrlsStore()
const capturesStore = useCapturesStore()
const jobsStore = useJobsStore()

const urlId = computed(() => route.params.id as string)
const showEditDialog = ref(false)
const selectedCapture = ref<Capture | null>(null)
const archiveViewerCapture = ref<Capture | null>(null)
const viewportFilter = ref<string>('all')

const capturing = ref(false)

const activeJobs = computed(() => jobsStore.jobsForUrl(urlId.value))

const jobProgress = computed(() => {
  if (!activeJobs.value.length) return null
  const total = activeJobs.value.length
  const completed = activeJobs.value.filter(j => j.status === 'completed' || j.status === 'failed').length
  const running = activeJobs.value.filter(j => j.status === 'running').length
  const failed = activeJobs.value.filter(j => j.status === 'failed').length
  const allDone = completed === total
  return { total, completed, running, failed, allDone }
})

// Refresh captures when a job for this URL completes
const unsubscribe = jobsStore.onCompletion(async (completedUrlId: string) => {
  if (completedUrlId === urlId.value) {
    await capturesStore.fetchCaptures({ url_id: urlId.value })
  }
})

onUnmounted(() => unsubscribe())

// Selection mode
const selectMode = ref(false)
const selectedIds = ref<Set<string>>(new Set())

onMounted(async () => {
  await Promise.all([
    urlsStore.fetchUrl(urlId.value),
    capturesStore.fetchCaptures({ url_id: urlId.value }),
  ])
})

const filteredCaptures = computed(() => {
  if (viewportFilter.value === 'all') return capturesStore.captures
  return capturesStore.captures.filter(c => c.viewport_label === viewportFilter.value)
})

const viewportOptions = computed(() => {
  const labels = new Set(capturesStore.captures.map(c => c.viewport_label))
  return Array.from(labels)
})

function toggleSelectMode() {
  selectMode.value = !selectMode.value
  if (!selectMode.value) {
    selectedIds.value.clear()
  }
}

function toggleCapture(id: string) {
  if (selectedIds.value.has(id)) {
    selectedIds.value.delete(id)
  } else {
    selectedIds.value.add(id)
  }
  // Force reactivity
  selectedIds.value = new Set(selectedIds.value)
}

function selectAll() {
  if (selectedIds.value.size === filteredCaptures.value.length) {
    selectedIds.value.clear()
  } else {
    selectedIds.value = new Set(filteredCaptures.value.map(c => c.id))
  }
}

async function deleteSelected() {
  const ids = Array.from(selectedIds.value)
  if (!ids.length) return
  if (!confirm(`Delete ${ids.length} capture(s)? This cannot be undone.`)) return

  try {
    await capturesStore.deleteCaptures(ids)
    selectedIds.value.clear()
    selectMode.value = false
    toast.success(`${ids.length} capture(s) deleted`)
  } catch {
    toast.error('Failed to delete captures')
  }
}

function handleCaptureClick(capture: Capture) {
  if (selectMode.value) {
    toggleCapture(capture.id)
  } else {
    selectedCapture.value = capture
  }
}

async function handleCaptureNow() {
  capturing.value = true
  try {
    await urlsStore.captureNow(urlId.value)
    toast.success('Capture job queued')
  } catch {
    toast.error('Failed to queue capture')
  } finally {
    capturing.value = false
  }
}

async function handleUpdate(data: URLUpdatePayload) {
  try {
    await urlsStore.updateUrl(urlId.value, data)
    showEditDialog.value = false
    await urlsStore.fetchUrl(urlId.value)
    toast.success('URL updated')
  } catch (e: any) {
    toast.error(e.response?.data?.detail || 'Failed to update')
  }
}

async function handleDelete() {
  if (!confirm('Delete this URL and all its captures?')) return
  try {
    await urlsStore.deleteUrl(urlId.value)
    router.push('/urls')
    toast.success('URL deleted')
  } catch {
    toast.error('Failed to delete')
  }
}

async function downloadArchive(captureId: string) {
  try {
    const response = await api.get(`/captures/${captureId}/archive`, { responseType: 'blob' })
    const blob = new Blob([response.data], { type: 'application/zip' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `capture-${captureId}.wacz`
    a.click()
    URL.revokeObjectURL(url)
  } catch {
    toast.error('Failed to download archive')
  }
}

function formatDate(date: string): string {
  return new Date(date).toLocaleDateString('fr-FR', {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

function formatBytes(bytes: number | null): string {
  if (!bytes) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
</script>

<template>
  <div class="p-6 space-y-6">
    <!-- Header -->
    <div v-if="urlsStore.currentUrl" class="space-y-4">
      <div class="flex items-start justify-between">
        <div>
          <div class="flex items-center gap-2">
            <Button variant="ghost" size="sm" @click="router.push('/urls')">
              &larr; Back
            </Button>
          </div>
          <h1 class="text-2xl font-bold mt-2">
            {{ urlsStore.currentUrl.label || urlsStore.currentUrl.url }}
          </h1>
          <p v-if="urlsStore.currentUrl.label" class="text-muted-foreground text-sm">
            {{ urlsStore.currentUrl.url }}
          </p>
          <div class="flex items-center gap-2 mt-2">
            <TagBadge
              v-for="tag in urlsStore.currentUrl.tags"
              :key="tag.id"
              :name="tag.name"
              :color="tag.color"
            />
            <Badge :variant="urlsStore.currentUrl.is_active ? 'default' : 'secondary'">
              {{ urlsStore.currentUrl.is_active ? 'Active' : 'Paused' }}
            </Badge>
          </div>
        </div>
        <div class="flex gap-2">
          <Button variant="outline" @click="showEditDialog = true">Edit</Button>
          <Button :disabled="capturing || jobsStore.hasActiveJobs(urlId)" @click="handleCaptureNow">
            <Loader2 v-if="capturing || jobsStore.hasActiveJobs(urlId)" class="w-4 h-4 mr-1 animate-spin" />
            {{ capturing ? 'Queuing...' : jobsStore.hasActiveJobs(urlId) ? 'Capturing...' : 'Capture now' }}
          </Button>
          <Button variant="destructive" @click="handleDelete">Delete</Button>
        </div>
      </div>

      <Separator />

      <!-- Capture progress -->
      <div v-if="activeJobs.length > 0" class="rounded-lg border bg-muted/30 p-4 space-y-3">
        <div class="flex items-center gap-2 text-sm font-medium">
          <Loader2 v-if="!jobProgress?.allDone" class="w-4 h-4 animate-spin" />
          <span>{{ jobProgress?.allDone ? 'Capture complete' : 'Capturing...' }}</span>
          <span class="text-muted-foreground">{{ jobProgress?.completed }}/{{ jobProgress?.total }}</span>
        </div>
        <div class="space-y-1.5">
          <div v-for="job in activeJobs" :key="job.id" class="flex items-center gap-3 text-sm">
            <span class="w-32 truncate font-medium">{{ job.viewport_label }}</span>
            <Badge
              :variant="job.status === 'completed' ? 'default' : job.status === 'failed' ? 'destructive' : 'secondary'"
              class="text-[10px] px-1.5 py-0"
            >
              {{ job.status === 'running' ? 'Capturing...' : job.status }}
            </Badge>
            <span v-if="job.error_message" class="text-xs text-destructive truncate">{{ job.error_message }}</span>
          </div>
        </div>
        <!-- Progress bar -->
        <div v-if="jobProgress && !jobProgress.allDone" class="h-1.5 rounded-full bg-muted overflow-hidden">
          <div
            class="h-full bg-primary transition-all duration-500 rounded-full"
            :style="{ width: `${(jobProgress.completed / jobProgress.total) * 100}%` }"
          />
        </div>
      </div>

      <!-- Info bar -->
      <div class="flex gap-6 text-sm text-muted-foreground">
        <span>Schedule: <strong class="text-foreground">{{ urlsStore.currentUrl.schedule }}</strong></span>
        <span>Threshold: <strong class="text-foreground">{{ (urlsStore.currentUrl.change_threshold * 100).toFixed(0) }}%</strong></span>
      </div>
    </div>

    <!-- Viewport filter + selection toolbar -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <span class="text-sm font-medium">Viewport:</span>
        <Select v-model="viewportFilter">
          <SelectTrigger class="w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All viewports</SelectItem>
            <SelectItem v-for="vp in viewportOptions" :key="vp" :value="vp">{{ vp }}</SelectItem>
          </SelectContent>
        </Select>
        <span class="text-sm text-muted-foreground">{{ filteredCaptures.length }} captures</span>
      </div>

      <div class="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          @click="toggleSelectMode"
        >
          {{ selectMode ? 'Cancel' : 'Select' }}
        </Button>
        <template v-if="selectMode">
          <Button variant="outline" size="sm" @click="selectAll">
            {{ selectedIds.size === filteredCaptures.length ? 'Deselect all' : 'Select all' }}
          </Button>
          <Button
            variant="destructive"
            size="sm"
            :disabled="selectedIds.size === 0"
            @click="deleteSelected"
          >
            Delete ({{ selectedIds.size }})
          </Button>
        </template>
      </div>
    </div>

    <!-- Capture gallery -->
    <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
      <div
        v-for="capture in filteredCaptures"
        :key="capture.id"
        class="group relative border rounded-lg overflow-hidden cursor-pointer transition-all"
        :class="[
          selectMode && selectedIds.has(capture.id)
            ? 'ring-2 ring-primary bg-primary/5'
            : 'hover:ring-2 hover:ring-primary',
        ]"
        @click="handleCaptureClick(capture)"
      >
        <!-- Selection checkbox -->
        <div
          v-if="selectMode"
          class="absolute top-2 left-2 z-10 w-5 h-5 rounded border-2 flex items-center justify-center transition-colors"
          :class="selectedIds.has(capture.id) ? 'bg-primary border-primary text-primary-foreground' : 'bg-background/80 border-muted-foreground/50'"
        >
          <span v-if="selectedIds.has(capture.id)" class="text-xs">&#10003;</span>
        </div>

        <div class="aspect-[4/3] bg-muted">
          <img
            v-if="capture.thumbnail_path"
            :src="capturesStore.thumbnailUrl(capture.id)"
            class="w-full h-full object-cover object-top"
            alt=""
            loading="lazy"
          />
          <div v-else class="w-full h-full flex items-center justify-center text-muted-foreground text-sm">
            {{ capture.status === 'error' ? 'Error' : 'No image' }}
          </div>
        </div>
        <div class="p-2 space-y-1">
          <p class="text-xs font-medium">{{ capture.viewport_label }}</p>
          <p class="text-xs text-muted-foreground">{{ formatDate(capture.captured_at) }}</p>
          <div class="flex items-center gap-2">
            <Badge
              :variant="capture.status === 'success' ? 'default' : 'destructive'"
              class="text-[10px] px-1.5 py-0"
            >
              {{ capture.status }}
            </Badge>
            <span v-if="capture.file_size" class="text-[10px] text-muted-foreground">
              {{ formatBytes(capture.file_size) }}
            </span>
          </div>
        </div>

        <!-- Archive preview icon -->
        <button
          v-if="!selectMode && capture.archive_path"
          class="absolute bottom-2 right-2 p-1 rounded bg-background/80 hover:bg-background border opacity-0 group-hover:opacity-100 transition-opacity"
          title="Preview archive"
          @click.stop="archiveViewerCapture = capture"
        >
          <Globe class="w-3.5 h-3.5" />
        </button>
      </div>
    </div>

    <p v-if="filteredCaptures.length === 0 && !capturesStore.loading" class="text-center text-muted-foreground py-8">
      No captures yet. Click "Capture now" to take the first screenshot.
    </p>

    <!-- Full-size viewer dialog -->
    <Dialog :open="!!selectedCapture" @update:open="selectedCapture = null">
      <DialogContent class="max-w-5xl max-h-[90vh] overflow-auto">
        <DialogHeader>
          <DialogTitle>
            {{ selectedCapture?.viewport_label }} — {{ selectedCapture ? formatDate(selectedCapture.captured_at) : '' }}
          </DialogTitle>
        </DialogHeader>
        <div v-if="selectedCapture" class="space-y-3">
          <img
            :src="capturesStore.screenshotUrl(selectedCapture.id)"
            class="w-full rounded border"
            alt="Full screenshot"
          />
          <div class="flex items-center gap-3 text-sm text-muted-foreground">
            <span>Size: {{ formatBytes(selectedCapture.file_size) }}</span>
            <span v-if="selectedCapture.archive_size">Archive: {{ formatBytes(selectedCapture.archive_size) }}</span>
            <button
              v-if="selectedCapture.archive_path"
              class="text-primary underline"
              @click="archiveViewerCapture = selectedCapture"
            >
              Preview archive
            </button>
            <button
              v-if="selectedCapture.archive_path"
              class="text-primary underline"
              @click="downloadArchive(selectedCapture!.id)"
            >
              Download archive
            </button>
          </div>
        </div>
      </DialogContent>
    </Dialog>

    <!-- Edit dialog -->
    <Dialog v-model:open="showEditDialog">
      <DialogContent class="max-w-lg">
        <DialogHeader>
          <DialogTitle>Edit URL</DialogTitle>
        </DialogHeader>
        <UrlForm :url="urlsStore.currentUrl" @submit="handleUpdate" @cancel="showEditDialog = false" />
      </DialogContent>
    </Dialog>

    <!-- Archive viewer -->
    <ArchiveViewer
      :capture-id="archiveViewerCapture?.id ?? ''"
      :open="!!archiveViewerCapture"
      :capture-label="archiveViewerCapture ? `${archiveViewerCapture.viewport_label} — ${formatDate(archiveViewerCapture.captured_at)}` : undefined"
      @update:open="!$event && (archiveViewerCapture = null)"
    />
  </div>
</template>
