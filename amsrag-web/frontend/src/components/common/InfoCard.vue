<template>
  <n-card
    :bordered="false"
    class="info-card surface-card"
    :class="[`info-card--${tone}`, `info-card--${size}`]"
  >
    <div class="info-card__top">
      <span class="info-card__label">{{ label }}</span>
      <div v-if="$slots.extra" class="info-card__extra">
        <slot name="extra" />
      </div>
    </div>
    <div class="info-card__value">
      <slot name="value">{{ value }}</slot>
    </div>
    <div v-if="caption || $slots.caption" class="info-card__caption">
      <slot name="caption">{{ caption }}</slot>
    </div>
  </n-card>
</template>

<script setup>
import { NCard } from 'naive-ui'

defineProps({
  label: {
    type: String,
    default: ''
  },
  value: {
    type: [String, Number],
    default: ''
  },
  caption: {
    type: String,
    default: ''
  },
  tone: {
    type: String,
    default: 'default'
  },
  size: {
    type: String,
    default: 'default'
  }
})
</script>

<style scoped>
.info-card {
  border-radius: var(--radius-md);
  position: relative;
  overflow: hidden;
  transition: box-shadow 0.2s, transform 0.2s;
}

.info-card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}

/* Top accent bar */
.info-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, var(--brand-500), var(--brand-300));
  opacity: 0;
  transition: opacity 0.2s;
}

.info-card--info::before {
  opacity: 1;
  background: linear-gradient(90deg, #2563eb, #60a5fa);
}

.info-card:hover::before {
  opacity: 1;
}

.info-card :deep(.n-card__content) {
  padding: 18px 20px;
}

.info-card--compact :deep(.n-card__content) {
  padding: 16px 18px;
}

.info-card--default {
  background: var(--surface-card);
}

.info-card--info {
  background: linear-gradient(180deg, #fbfdff 0%, #f0f7ff 100%);
}

.info-card--muted {
  background: linear-gradient(180deg, #fbfcfe 0%, #f7f9fc 100%);
}

.info-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.info-card__label {
  font-size: 12.5px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-4);
}

.info-card__value {
  margin-top: 10px;
  font-size: clamp(24px, 2.2vw, 30px);
  font-weight: 800;
  line-height: 1.15;
  color: var(--text-1);
  letter-spacing: -0.5px;
}

.info-card__caption {
  margin-top: 8px;
  font-size: 12.5px;
  line-height: 1.6;
  color: var(--text-4);
}
</style>
