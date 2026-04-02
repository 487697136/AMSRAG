<template>
  <n-config-provider
    :theme="theme"
    :theme-overrides="themeOverrides"
    :locale="zhCN"
    :date-locale="dateZhCN"
  >
    <n-message-provider>
      <n-dialog-provider>
        <n-notification-provider>
          <router-view />
        </n-notification-provider>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup>
import { computed, onMounted, provide, ref, watch } from 'vue'
import {
  NConfigProvider,
  NDialogProvider,
  NMessageProvider,
  NNotificationProvider,
  darkTheme,
  dateZhCN,
  zhCN
} from 'naive-ui'
import { getNaiveThemeOverrides } from '@/theme/naiveTheme'

const THEME_STORAGE_KEY = 'amsrag-theme'
const darkMode = ref(false)

const applyTheme = (isDark) => {
  if (typeof document === 'undefined') {
    return
  }
  document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light')
}

const setThemePreference = (value) => {
  darkMode.value = Boolean(value)
}

const theme = computed(() => (darkMode.value ? darkTheme : null))
const themeOverrides = computed(() => getNaiveThemeOverrides(darkMode.value))

provide('themePreference', {
  darkMode,
  setThemePreference
})

onMounted(() => {
  if (typeof window === 'undefined') {
    return
  }

  darkMode.value = window.localStorage.getItem(THEME_STORAGE_KEY) === 'dark'
  applyTheme(darkMode.value)
})

watch(darkMode, (value) => {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(THEME_STORAGE_KEY, value ? 'dark' : 'light')
  }
  applyTheme(value)
})
</script>
