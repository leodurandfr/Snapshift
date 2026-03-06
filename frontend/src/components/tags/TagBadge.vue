<script setup lang="ts">
import { Badge } from '@/components/ui/badge'

defineProps<{
  name: string
  color: string
}>()
</script>

<template>
  <Badge variant="outline" class="text-xs" :style="{ borderColor: color, color: color }">
    {{ name }}
  </Badge>
</template>
