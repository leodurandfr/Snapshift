<script setup lang="ts">
import { onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { useUrlsStore } from '@/stores/urls'
import { useCapturesStore } from '@/stores/captures'

const router = useRouter()
const urlsStore = useUrlsStore()
const capturesStore = useCapturesStore()

onMounted(async () => {
  await Promise.all([
    urlsStore.fetchUrls(),
    capturesStore.fetchCaptures({ limit: 12 }),
  ])
})

const activeUrls = computed(() => urlsStore.urls.filter(u => u.is_active).length)
const errorCaptures = computed(() => capturesStore.captures.filter(c => c.status !== 'success'))
const recentCaptures = computed(() => capturesStore.captures.slice(0, 8))

function formatDate(date: string): string {
  return new Date(date).toLocaleDateString('fr-FR', {
    day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit',
  })
}
</script>

<template>
  <div class="p-6 space-y-6">
    <div>
      <h1 class="text-2xl font-bold">Dashboard</h1>
      <p class="text-muted-foreground text-sm mt-1">Snapshift overview</p>
    </div>

    <!-- Stats cards -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <Card>
        <CardHeader class="pb-2">
          <CardDescription>Monitored URLs</CardDescription>
          <CardTitle class="text-3xl">{{ urlsStore.total }}</CardTitle>
        </CardHeader>
        <CardContent>
          <p class="text-xs text-muted-foreground">{{ activeUrls }} active</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader class="pb-2">
          <CardDescription>Recent captures</CardDescription>
          <CardTitle class="text-3xl">{{ capturesStore.total }}</CardTitle>
        </CardHeader>
        <CardContent>
          <p class="text-xs text-muted-foreground">Total captures stored</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader class="pb-2">
          <CardDescription>Errors</CardDescription>
          <CardTitle class="text-3xl">{{ errorCaptures.length }}</CardTitle>
        </CardHeader>
        <CardContent>
          <p class="text-xs text-muted-foreground">In recent captures</p>
        </CardContent>
      </Card>
    </div>

    <!-- Recent captures -->
    <div>
      <h2 class="text-lg font-semibold mb-3">Recent captures</h2>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div
          v-for="capture in recentCaptures"
          :key="capture.id"
          class="border rounded-lg overflow-hidden cursor-pointer hover:ring-2 hover:ring-primary transition-all"
          @click="router.push(`/urls/${capture.url_id}`)"
        >
          <div class="aspect-[4/3] bg-muted">
            <img
              v-if="capture.thumbnail_path"
              :src="capturesStore.thumbnailUrl(capture.id)"
              class="w-full h-full object-cover object-top"
              alt=""
              loading="lazy"
            />
          </div>
          <div class="p-2">
            <p class="text-xs font-medium truncate">{{ capture.viewport_label }}</p>
            <p class="text-[10px] text-muted-foreground">{{ formatDate(capture.captured_at) }}</p>
            <Badge
              :variant="capture.status === 'success' ? 'default' : 'destructive'"
              class="text-[10px] px-1 py-0 mt-1"
            >
              {{ capture.status }}
            </Badge>
          </div>
        </div>
      </div>
      <p v-if="recentCaptures.length === 0" class="text-center text-muted-foreground py-8">
        No captures yet. Add URLs and start monitoring.
      </p>
    </div>

    <!-- URLs with errors -->
    <div v-if="errorCaptures.length > 0">
      <h2 class="text-lg font-semibold mb-3">Failed captures</h2>
      <div class="space-y-2">
        <div
          v-for="capture in errorCaptures"
          :key="capture.id"
          class="flex items-center justify-between p-3 border rounded-lg"
        >
          <div>
            <p class="text-sm font-medium">{{ capture.viewport_label }}</p>
            <p class="text-xs text-muted-foreground">{{ capture.error_message }}</p>
          </div>
          <Badge variant="destructive">{{ capture.status }}</Badge>
        </div>
      </div>
    </div>
  </div>
</template>
