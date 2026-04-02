<template>
  <section class="detail-panel surface-card">
    <div class="detail-panel__header">
      <div class="detail-panel__copy">
        <div class="detail-panel__title">{{ title }}</div>
        <p v-if="description" class="detail-panel__description">{{ description }}</p>
      </div>
      <div v-if="$slots.actions" class="detail-panel__actions">
        <slot name="actions" />
      </div>
    </div>

    <div v-if="tabs?.length || $slots.tabs" class="detail-panel__tabs">
      <slot name="tabs">
        <button
          v-for="tabItem in tabs"
          :key="tabItem.value"
          type="button"
          class="detail-panel__tab"
          :class="{ 'is-active': tabItem.value === activeTab }"
          @click="handleSelectTab(tabItem.value)"
        >
          {{ tabItem.label }}
        </button>
      </slot>
    </div>

    <div class="detail-panel__body">
      <slot />
    </div>

    <div v-if="$slots.footer" class="detail-panel__footer">
      <slot name="footer" />
    </div>
  </section>
</template>

<script setup>
defineProps({
  title: {
    type: String,
    required: true
  },
  description: {
    type: String,
    default: ''
  },
  tabs: {
    type: Array,
    default: () => []
  },
  activeTab: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['update:activeTab', 'tab-change'])

const handleSelectTab = (value) => {
  emit('update:activeTab', value)
  emit('tab-change', value)
}
</script>

<style scoped>
.detail-panel {
  padding: 20px;
}

.detail-panel__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.detail-panel__copy {
  min-width: 0;
}

.detail-panel__title {
  font-size: 16px;
  font-weight: 700;
  line-height: 1.35;
  color: var(--text-1);
}

.detail-panel__description {
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-4);
}

.detail-panel__tabs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border-color);
}

.detail-panel__tab {
  height: 32px;
  padding: 0 12px;
  border: 1px solid transparent;
  border-radius: 999px;
  background: transparent;
  color: var(--text-4);
  font-size: 13px;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.detail-panel__tab:hover {
  background: var(--surface-muted);
  color: var(--text-2);
}

.detail-panel__tab.is-active {
  background: var(--brand-50);
  border-color: var(--brand-soft-border);
  color: var(--brand-700);
}

.detail-panel__body {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-panel__footer {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

@media (max-width: 900px) {
  .detail-panel {
    padding: 16px;
  }

  .detail-panel__header {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
