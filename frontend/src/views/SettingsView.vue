<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { toast } from 'vue-sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { useTagsStore } from '@/stores/tags'

const tagsStore = useTagsStore()

const newTagName = ref('')
const newTagColor = ref('#6366f1')
const retentionDays = ref(90)

onMounted(() => {
  tagsStore.fetchTags()
})

async function addTag() {
  if (!newTagName.value.trim()) return
  try {
    await tagsStore.createTag({ name: newTagName.value.trim(), color: newTagColor.value })
    newTagName.value = ''
    toast.success('Tag created')
  } catch (e: any) {
    toast.error(e.response?.data?.detail || 'Failed to create tag')
  }
}

async function removeTag(id: string) {
  if (!confirm('Delete this tag?')) return
  await tagsStore.deleteTag(id)
  toast.success('Tag deleted')
}

const TAG_COLORS = [
  '#ef4444', '#f97316', '#eab308', '#22c55e', '#06b6d4',
  '#3b82f6', '#6366f1', '#8b5cf6', '#ec4899', '#64748b',
]
</script>

<template>
  <div class="p-6 space-y-6 max-w-2xl">
    <div>
      <h1 class="text-2xl font-bold">Settings</h1>
      <p class="text-muted-foreground text-sm mt-1">Configure Snapshift</p>
    </div>

    <!-- Tags management -->
    <Card>
      <CardHeader>
        <CardTitle>Tags</CardTitle>
        <CardDescription>Manage your tags for URL organization</CardDescription>
      </CardHeader>
      <CardContent class="space-y-4">
        <!-- Existing tags -->
        <div class="flex flex-wrap gap-2">
          <div
            v-for="tag in tagsStore.tags"
            :key="tag.id"
            class="flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-sm"
            :style="{ borderColor: tag.color, color: tag.color }"
          >
            <span>{{ tag.name }}</span>
            <button
              class="hover:opacity-70 text-xs"
              @click="removeTag(tag.id)"
            >
              x
            </button>
          </div>
          <span v-if="tagsStore.tags.length === 0" class="text-sm text-muted-foreground">
            No tags yet
          </span>
        </div>

        <Separator />

        <!-- Add tag -->
        <div class="flex items-end gap-3">
          <div class="flex-1 space-y-1.5">
            <label class="text-sm font-medium">New tag</label>
            <Input v-model="newTagName" placeholder="Tag name" @keyup.enter="addTag" />
          </div>
          <div class="space-y-1.5">
            <label class="text-sm font-medium">Color</label>
            <div class="flex gap-1">
              <button
                v-for="color in TAG_COLORS"
                :key="color"
                class="w-6 h-6 rounded-full border-2 transition-transform hover:scale-110"
                :class="newTagColor === color ? 'border-foreground scale-110' : 'border-transparent'"
                :style="{ backgroundColor: color }"
                @click="newTagColor = color"
              />
            </div>
          </div>
          <Button @click="addTag">Add</Button>
        </div>
      </CardContent>
    </Card>

    <!-- Capture defaults -->
    <Card>
      <CardHeader>
        <CardTitle>Capture defaults</CardTitle>
        <CardDescription>Default settings for new URLs</CardDescription>
      </CardHeader>
      <CardContent class="space-y-4">
        <div class="space-y-1.5">
          <label class="text-sm font-medium">Retention (days)</label>
          <Input
            v-model.number="retentionDays"
            type="number"
            min="1"
            max="365"
            class="w-32"
          />
          <p class="text-xs text-muted-foreground">Captures older than this will be automatically deleted</p>
        </div>
      </CardContent>
    </Card>

    <!-- System info -->
    <Card>
      <CardHeader>
        <CardTitle>System</CardTitle>
      </CardHeader>
      <CardContent class="space-y-2 text-sm">
        <div class="flex justify-between">
          <span class="text-muted-foreground">Version</span>
          <span>0.1.0</span>
        </div>
        <div class="flex justify-between">
          <span class="text-muted-foreground">API</span>
          <span>http://localhost:8000</span>
        </div>
      </CardContent>
    </Card>
  </div>
</template>
