<template>
  <div class="app-layout">
    <AppSidebar class="app-layout__desktop-sidebar" />

    <div class="app-layout__main">
      <header class="app-layout__mobile-bar">
        <n-button quaternary circle @click="showMobileSidebar = true">
          <template #icon>
            <n-icon :component="MenuOutline" />
          </template>
        </n-button>
        <div class="app-layout__mobile-title">{{ route.meta.title || '知源' }}</div>
        <div class="app-layout__mobile-space" />
      </header>

      <main
        class="app-layout__content"
        :class="{ 'app-layout__content--full': route.path === '/chat' || route.path.includes('/graph') }"
      >
        <router-view v-slot="{ Component, route: currentRoute }">
          <transition name="page-fade" mode="out-in">
            <component :is="Component" :key="currentRoute.path" />
          </transition>
        </router-view>
      </main>
    </div>

    <n-drawer v-model:show="showMobileSidebar" placement="left" :width="264">
      <n-drawer-content body-content-style="padding: 0">
        <AppSidebar drawer-mode @navigate="showMobileSidebar = false" />
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { NButton, NDrawer, NDrawerContent, NIcon } from 'naive-ui'
import { MenuOutline } from '@vicons/ionicons5'
import AppSidebar from './AppSidebar.vue'

const route = useRoute()
const showMobileSidebar = ref(false)
</script>

<style scoped>
/* 页面切换过渡动画 */
.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity 0.22s ease, transform 0.22s ease;
}

.page-fade-enter-from {
  opacity: 0;
  transform: translateY(6px);
}

.page-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.app-layout {
  display: flex;
  min-height: 100vh;
  background: var(--page-bg);
  overflow: hidden;
}

.app-layout__desktop-sidebar {
  position: sticky;
  top: 0;
  flex-shrink: 0;
}

.app-layout__main {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  height: 100vh;
}

.app-layout__content {
  min-height: 100vh;
  width: min(100%, var(--layout-content-max));
  margin: 0 auto;
  padding: 24px 28px 28px;
}

.app-layout__content--full {
  width: 100%;
  margin: 0;
  padding: 0;
}

.app-layout__mobile-bar {
  display: none;
}

@media (max-width: 960px) {
  .app-layout__desktop-sidebar {
    display: none;
  }

  .app-layout__mobile-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 16px 8px;
  }

  .app-layout__mobile-title {
    font-size: 16px;
    font-weight: 700;
    color: var(--text-1);
  }

  .app-layout__mobile-space {
    width: 34px;
    height: 34px;
  }

  .app-layout__content {
    width: 100%;
    padding: 12px 16px 24px;
  }
}
</style>
