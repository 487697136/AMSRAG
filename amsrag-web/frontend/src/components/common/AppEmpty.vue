<template>
  <div class="app-empty">
    <n-empty v-bind="$attrs">
      <template v-if="$slots.icon" #icon>
        <slot name="icon" />
      </template>
      <template v-if="$slots.extra" #extra>
        <slot name="extra" />
      </template>
    </n-empty>
  </div>
</template>

<script setup>
import { NEmpty } from 'naive-ui'

defineOptions({ inheritAttrs: false })
</script>

<style scoped>
.app-empty {
  padding: 24px 0 28px;
}

.app-empty :deep(.n-empty__description) {
  color: var(--text-3);
  font-size: 14px;
  line-height: var(--line-height-body);
}
</style>
