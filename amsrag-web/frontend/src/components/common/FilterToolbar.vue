<template>
  <div class="filter-toolbar surface-card">
    <div v-if="tabs?.length || $slots.tabs" class="filter-toolbar__tabs">
      <slot name="tabs">
        <button
          v-for="tabItem in tabs"
          :key="tabItem.value"
          type="button"
          class="filter-toolbar__tab"
          :class="{ 'is-active': tabItem.value === activeTab }"
          @click="handleSelectTab(tabItem.value)"
        >
          <span>{{ tabItem.label }}</span>
          <span v-if="tabItem.count !== undefined" class="filter-toolbar__tab-count">{{ tabItem.count }}</span>
        </button>
      </slot>
    </div>

    <div class="filter-toolbar__main">
      <div v-if="$slots.filters" class="filter-toolbar__filters">
        <slot name="filters" />
      </div>
      <div v-if="$slots.actions" class="filter-toolbar__actions">
        <slot name="actions" />
      </div>
    </div>

    <div v-if="$slots.summary" class="filter-toolbar__summary">
      <slot name="summary" />
    </div>
  </div>
</template>

<script setup>
defineProps({
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
.filter-toolbar {
  padding: 16px 20px;
}

.filter-toolbar__tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border-color);
}

.filter-toolbar__tab {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 32px;
  padding: 0 14px;
  border: 1px solid var(--border-color);
  border-radius: 999px;
  background: var(--surface-card);
  color: var(--text-3);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.16s ease;
}

.filter-toolbar__tab:hover {
  border-color: var(--brand-soft-border);
  background: var(--surface-hover);
  color: var(--text-2);
}

.filter-toolbar__tab.is-active {
  border-color: var(--brand-500);
  background: var(--brand-600);
  color: #ffffff;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
}

.filter-toolbar__tab-count {
  color: var(--text-4);
}

.filter-toolbar__main {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.filter-toolbar__tabs + .filter-toolbar__main {
  padding-top: 14px;
}

.filter-toolbar__filters,
.filter-toolbar__actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.filter-toolbar__filters {
  flex: 1;
  min-width: 280px;
}

.filter-toolbar__actions {
  justify-content: flex-end;
  flex-shrink: 0;
}

.filter-toolbar__summary {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--border-color);
}

@media (max-width: 900px) {
  .filter-toolbar {
    padding: 14px 16px;
  }

  .filter-toolbar__main,
  .filter-toolbar__actions {
    align-items: stretch;
  }

  .filter-toolbar__actions {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
