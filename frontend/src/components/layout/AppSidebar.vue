<script setup lang="ts">
import { useRoute } from 'vue-router'
import { computed } from 'vue'

const route = useRoute()

const navItems = [
  { name: 'Dashboard', path: '/', icon: 'layout-dashboard' },
  { name: 'URLs', path: '/urls', icon: 'globe' },
  { name: 'Settings', path: '/settings', icon: 'settings' },
]

function isActive(path: string): boolean {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}
</script>

<template>
  <aside class="w-60 border-r border-border bg-card flex flex-col h-screen sticky top-0">
    <!-- Logo -->
    <div class="p-4 border-b border-border">
      <RouterLink to="/" class="flex items-center gap-2">
        <div class="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
          <span class="text-primary-foreground font-bold text-sm">SS</span>
        </div>
        <span class="font-semibold text-lg">Snapshift</span>
      </RouterLink>
    </div>

    <!-- Navigation -->
    <nav class="flex-1 p-3 space-y-1">
      <RouterLink
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors"
        :class="isActive(item.path)
          ? 'bg-accent text-accent-foreground font-medium'
          : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground'"
      >
        {{ item.name }}
      </RouterLink>
    </nav>

    <!-- Footer -->
    <div class="p-4 border-t border-border">
      <p class="text-xs text-muted-foreground">Snapshift v0.1.0</p>
    </div>
  </aside>
</template>
