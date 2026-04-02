<template>
  <header class="page-header">
    <div class="page-header__info">
      <div class="page-header__title-row">
        <h1 class="page-header__title">{{ title }}</h1>
        <span v-if="badge" class="page-header__badge">{{ badge }}</span>
      </div>
      <p v-if="description" class="page-header__description">{{ description }}</p>
      <div v-if="$slots.meta" class="page-header__meta">
        <slot name="meta" />
      </div>
    </div>

    <div v-if="$slots.actions" class="page-header__actions">
      <slot name="actions" />
    </div>
  </header>
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
  badge: {
    type: String,
    default: ''
  }
})
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 20px;
  margin-bottom: 18px;
}

.page-header__info {
  min-width: 0;
}

.page-header__title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.page-header__title {
  margin: 0;
  font-size: clamp(24px, 2.6vw, 30px);
  line-height: 1.2;
  letter-spacing: -0.02em;
  color: var(--text-1);
}

.page-header__badge {
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: var(--brand-50);
  color: var(--brand-700);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.page-header__description {
  max-width: 760px;
  margin: 6px 0 0;
  font-size: 14px;
  line-height: 1.65;
  color: var(--text-3);
}

.page-header__meta {
  margin-top: 12px;
}

.page-header__actions {
  flex-shrink: 0;
}

@media (max-width: 900px) {
  .page-header {
    flex-direction: column;
    align-items: stretch;
  }

  .page-header__actions {
    width: 100%;
  }
}
</style>
