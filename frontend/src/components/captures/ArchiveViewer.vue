<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { X, Maximize2, Minimize2 } from 'lucide-vue-next'
import { useCapturesStore } from '@/stores/captures'

const props = defineProps<{
  captureId: string
  open: boolean
  captureLabel?: string
}>()

const emit = defineEmits<{ 'update:open': [value: boolean] }>()

const capturesStore = useCapturesStore()
const isFullscreen = ref(false)
const iframeLoaded = ref(false)

const previewUrl = computed(() =>
  props.captureId && props.open ? capturesStore.archivePreviewUrl(props.captureId) : ''
)

watch(() => props.open, (val) => {
  if (!val) {
    isFullscreen.value = false
    iframeLoaded.value = false
  }
})

function close() {
  emit('update:open', false)
}

function onBackdropClick(e: MouseEvent) {
  if (e.target === e.currentTarget) close()
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-[60] flex items-center justify-center bg-black/80"
      @click="onBackdropClick"
    >
      <div
        :class="[
          'bg-background flex flex-col shadow-2xl overflow-hidden transition-all duration-200',
          isFullscreen
            ? 'fixed inset-0'
            : 'relative rounded-lg w-[85vw] h-[85vh]',
        ]"
      >
        <!-- Control bar -->
        <div class="flex items-center justify-between px-4 h-12 border-b shrink-0 bg-background relative z-10">
          <span class="text-sm font-medium truncate text-foreground">
            {{ captureLabel || 'Archive Preview' }}
          </span>
          <div class="flex items-center gap-1">
            <button
              class="p-1.5 rounded hover:bg-muted transition-colors"
              :title="isFullscreen ? 'Exit fullscreen' : 'Fullscreen'"
              @click="isFullscreen = !isFullscreen"
            >
              <Minimize2 v-if="isFullscreen" class="w-4 h-4" />
              <Maximize2 v-else class="w-4 h-4" />
            </button>
            <button
              class="p-1.5 rounded hover:bg-muted transition-colors"
              title="Close"
              @click="close"
            >
              <X class="w-4 h-4" />
            </button>
          </div>
        </div>

        <!-- Loading state -->
        <div
          v-if="!iframeLoaded"
          class="flex-1 flex items-center justify-center bg-muted/20 text-muted-foreground text-sm"
        >
          Loading preview...
        </div>

        <!-- iframe loads archive-preview endpoint (HTML with <replay-web-page>) -->
        <iframe
          v-if="open && previewUrl"
          :src="previewUrl"
          sandbox="allow-scripts allow-same-origin allow-popups"
          class="flex-1 w-full border-0 min-h-0"
          :class="{ hidden: !iframeLoaded }"
          @load="iframeLoaded = true"
        />
      </div>
    </div>
  </Teleport>
</template>
