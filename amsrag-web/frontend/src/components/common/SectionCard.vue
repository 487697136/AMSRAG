<template>
  <n-card
    :bordered="false"
    class="section-card surface-card"
    :class="[`section-card--${size}`, `section-card--${variant}`]"
  >
    <template v-if="hasHeader" #header>
      <div class="section-card__header">
        <div class="section-card__heading">
          <div v-if="$slots.icon" class="section-card__icon">
            <slot name="icon" />
          </div>
          <div class="section-card__heading-copy">
            <div v-if="title" class="section-card__title">{{ title }}</div>
            <p v-if="description" class="section-card__description">{{ description }}</p>
          </div>
        </div>
        <div v-if="$slots.extra" class="section-card__extra">
          <slot name="extra" />
        </div>
      </div>
    </template>

    <div class="section-card__body" :class="{ 'section-card__body--flush': flush }">
      <slot />
    </div>

    <template v-if="$slots.footer" #footer>
      <div class="section-card__footer">
        <slot name="footer" />
      </div>
    </template>
  </n-card>
</template>

<script setup>
import { computed, useSlots } from 'vue'
import { NCard } from 'naive-ui'

const props = defineProps({
  title: {
    type: String,
    default: ''
  },
  description: {
    type: String,
    default: ''
  },
  size: {
    type: String,
    default: 'default'
  },
  variant: {
    type: String,
    default: 'default'
  },
  flush: {
    type: Boolean,
    default: false
  }
})

const slots = useSlots()
const hasHeader = computed(() => Boolean(props.title || props.description || slots.icon || slots.extra))
</script>

<style scoped>
.section-card {
  border-radius: var(--radius-md);
}

.section-card--default {
  --section-card-padding: var(--card-padding);
}

.section-card--compact {
  --section-card-padding: var(--card-padding-sm);
}

.section-card--dense {
  --section-card-padding: 16px;
}

.section-card--default.section-card--default,
.section-card--compact.section-card--default,
.section-card--dense.section-card--default {
  background: var(--surface-card);
}

.section-card--highlight {
  border-color: #cddcf3;
  box-shadow: 0 10px 26px rgba(15, 23, 42, 0.06);
}

.section-card--muted {
  background: linear-gradient(180deg, #fbfcff 0%, #f7faff 100%);
}

.section-card :deep(.n-card-header),
.section-card :deep(.n-card__content),
.section-card :deep(.n-card__footer) {
  padding-left: var(--section-card-padding);
  padding-right: var(--section-card-padding);
}

.section-card :deep(.n-card-header) {
  padding-top: var(--section-card-padding);
  padding-bottom: 0;
}

.section-card :deep(.n-card__content) {
  padding-top: 16px;
  padding-bottom: var(--section-card-padding);
}

.section-card :deep(.n-card__footer) {
  padding-top: 0;
  padding-bottom: var(--section-card-padding);
}

.section-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.section-card__heading {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  min-width: 0;
}

.section-card__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: var(--surface-soft);
  color: var(--brand-700);
  flex-shrink: 0;
}

.section-card__heading-copy {
  min-width: 0;
}

.section-card__title {
  font-size: 15.5px;
  font-weight: 700;
  line-height: 1.35;
  color: var(--text-1);
  letter-spacing: -0.1px;
}

.section-card__description {
  margin: 4px 0 0;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--text-4);
}

.section-card__extra {
  flex-shrink: 0;
}

.section-card__body {
  min-width: 0;
}

.section-card__body--flush {
  margin-left: calc(var(--section-card-padding) * -1);
  margin-right: calc(var(--section-card-padding) * -1);
  margin-bottom: calc(var(--section-card-padding) * -1);
}

.section-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

@media (max-width: 900px) {
  .section-card__header {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
