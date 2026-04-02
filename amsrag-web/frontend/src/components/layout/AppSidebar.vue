<template>
  <aside
    class="app-sidebar"
    :class="{
      'app-sidebar--drawer': drawerMode,
      'app-sidebar--collapsed': !drawerMode && sidebarCollapsed
    }"
  >
    <!-- 品牌区域 -->
    <div class="app-sidebar__brand" @click="handleNavigate('/chat')">
      <div class="app-sidebar__logo">
        <img class="app-sidebar__logo-img" src="/logo.png" alt="知源 Logo" />
      </div>
      <div class="app-sidebar__brand-copy">
        <div class="app-sidebar__brand-title">知源</div>
        <div class="app-sidebar__brand-subtitle">智能知识服务系统</div>
      </div>
    </div>

    <!-- 新建问答按钮 -->
    <button class="app-sidebar__new-chat" :title="sidebarCollapsed ? '新建问答' : undefined" @click="handleNavigate('/chat')">
      <div class="app-sidebar__new-chat-icon">
        <n-icon :component="AddOutline" size="16" />
      </div>
      <span class="app-sidebar__new-chat-text">新建问答</span>
    </button>

    <!-- 折叠开关（小按钮，不作为主菜单项） -->
    <button
      v-if="!drawerMode"
      type="button"
      class="app-sidebar__collapse-mini"
      :title="sidebarCollapsed ? '展开导航' : '收起导航'"
      @click="toggleSidebar"
    >
      {{ sidebarCollapsed ? '»' : '«' }}
    </button>

    <!-- 导航菜单 -->
    <nav class="app-sidebar__nav">
      <div class="app-sidebar__nav-group">
        <div class="app-sidebar__nav-label">核心功能</div>
        <button
          v-for="item in primaryNav"
          :key="item.path"
          class="app-sidebar__nav-item"
          :class="{ 'is-active': isActive(item.path) }"
          :title="sidebarCollapsed ? item.label : undefined"
          @click="handleNavigate(item.path)"
        >
          <div class="app-sidebar__nav-icon">
            <n-icon size="16" :component="item.icon" />
          </div>
          <span>{{ item.label }}</span>
          <div v-if="isActive(item.path)" class="app-sidebar__nav-indicator" />
        </button>
      </div>

      <div class="app-sidebar__nav-group">
        <div class="app-sidebar__nav-label">知识管理</div>
        <button
          v-for="item in secondaryNav"
          :key="item.path"
          class="app-sidebar__nav-item"
          :class="{ 'is-active': isActive(item.path) }"
          :title="sidebarCollapsed ? item.label : undefined"
          @click="handleNavigate(item.path)"
        >
          <div class="app-sidebar__nav-icon">
            <n-icon size="16" :component="item.icon" />
          </div>
          <span>{{ item.label }}</span>
          <div v-if="isActive(item.path)" class="app-sidebar__nav-indicator" />
        </button>
      </div>
    </nav>

    <!-- 用户信息 -->
    <n-dropdown
      :options="userMenuOptions"
      placement="top-start"
      trigger="click"
      @select="handleUserMenuSelect"
    >
      <div class="app-sidebar__footer">
        <div class="app-sidebar__avatar-wrap">
          <div class="app-sidebar__avatar">{{ userInitial }}</div>
          <div class="app-sidebar__status-dot" />
        </div>
        <div class="app-sidebar__user">
          <div class="app-sidebar__user-name">{{ authStore.user?.username || '未登录用户' }}</div>
          <div class="app-sidebar__user-role">{{ authStore.user?.email || '请先登录' }}</div>
        </div>
        <n-icon :component="SettingsOutline" size="15" class="app-sidebar__footer-icon" />
      </div>
    </n-dropdown>
  </aside>
</template>

<script setup>
import { computed, h, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NDropdown, NIcon } from 'naive-ui'
import { AddOutline, ChatbubblesOutline, DocumentTextOutline, ExitOutline, GitNetworkOutline, LibraryOutline, SettingsOutline, TimeOutline } from '@vicons/ionicons5'
import { useAuthStore } from '@/stores/auth'

const props = defineProps({ drawerMode: { type: Boolean, default: false } })
const emit = defineEmits(['navigate'])
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const SIDEBAR_COLLAPSED_KEY = 'amsrag.sidebar.collapsed'
const sidebarCollapsed = ref(false)

const loadSidebarState = () => {
  try {
    sidebarCollapsed.value = window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1'
  } catch {
    sidebarCollapsed.value = false
  }
}

const persistSidebarState = () => {
  try {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, sidebarCollapsed.value ? '1' : '0')
  } catch {
    // ignore
  }
}

const toggleSidebar = () => {
  sidebarCollapsed.value = !sidebarCollapsed.value
  persistSidebarState()
}

onMounted(() => { if (!props.drawerMode) loadSidebarState() })

const renderIcon = (icon) => () => h(NIcon, null, { default: () => h(icon) })

const userMenuOptions = computed(() => [
  {
    label: authStore.user?.full_name || authStore.user?.username || '当前用户',
    key: 'profile-header',
    disabled: true,
  },
  { type: 'divider', key: 'd1' },
  { label: '账号设置', key: 'settings', icon: renderIcon(SettingsOutline) },
  { type: 'divider', key: 'd2' },
  { label: '退出登录', key: 'logout', icon: renderIcon(ExitOutline) },
])

const handleUserMenuSelect = (key) => {
  if (key === 'settings') {
    handleNavigate('/settings')
  } else if (key === 'logout') {
    authStore.logout()
    router.push('/login')
  }
}

const primaryNav = [
  { label: '智能问答', path: '/chat', icon: ChatbubblesOutline },
  { label: '会话中心', path: '/sessions', icon: TimeOutline },
]

const secondaryNav = [
  { label: '知识库中心', path: '/knowledge', icon: LibraryOutline },
  { label: '文档中心', path: '/documents', icon: DocumentTextOutline },
  { label: '知识图谱', path: '/graph', icon: GitNetworkOutline },
]

const userInitial = computed(() => (authStore.user?.username || 'A').charAt(0).toUpperCase())
const isActive = (targetPath) => route.path === targetPath
const handleNavigate = (targetPath) => {
  router.push(targetPath)
  if (props.drawerMode) emit('navigate', targetPath)
}
</script>

<style scoped>
.app-sidebar {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: var(--layout-sidebar-width);
  height: 100vh;
  padding: 20px 14px 16px;
  background: var(--sidebar-bg, #0f1629);
  border-right: 1px solid var(--sidebar-border, rgba(255,255,255,0.06));
  position: relative;
  overflow: hidden;
}

/* Mini collapse toggle */
.app-sidebar__collapse-mini {
  position: absolute;
  top: 18px;
  right: 10px;
  width: 28px;
  height: 28px;
  border-radius: 9px;
  border: 1px solid rgba(255,255,255,0.10);
  background: rgba(255,255,255,0.04);
  color: rgba(226,232,240,0.92);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.16s ease, border-color 0.16s ease, transform 0.16s ease;
}

.app-sidebar__collapse-mini:hover {
  background: rgba(255,255,255,0.07);
  border-color: rgba(255,255,255,0.14);
  transform: translateY(-1px);
}

/* Collapsed state: icon-first, keep tooltips via title */
.app-sidebar--collapsed {
  width: 72px;
  padding: 14px 10px 14px;
}

.app-sidebar--collapsed .app-sidebar__brand {
  padding: 6px 6px;
  justify-content: center;
}

.app-sidebar--collapsed .app-sidebar__brand-copy {
  display: none;
}

.app-sidebar--collapsed .app-sidebar__new-chat {
  justify-content: center;
  padding: 10px 10px;
}

.app-sidebar--collapsed .app-sidebar__new-chat-text {
  display: none;
}

/* Mini toggle remains visible in collapsed state */

.app-sidebar--collapsed .app-sidebar__nav-label {
  display: none;
}

.app-sidebar--collapsed .app-sidebar__nav-item {
  justify-content: center;
  padding: 9px 8px;
}

.app-sidebar--collapsed .app-sidebar__nav-item span {
  display: none;
}

.app-sidebar--collapsed .app-sidebar__nav-icon {
  width: 34px;
  height: 34px;
  border-radius: 10px;
}

.app-sidebar--collapsed .app-sidebar__nav-indicator {
  right: -2px;
  width: 2px;
  height: 18px;
}

.app-sidebar--collapsed .app-sidebar__footer {
  justify-content: center;
  padding: 10px 6px;
}

.app-sidebar--collapsed .app-sidebar__user,
.app-sidebar--collapsed .app-sidebar__footer-icon {
  display: none;
}

.app-sidebar::before {
  content: '';
  position: absolute;
  top: -80px;
  right: -80px;
  width: 220px;
  height: 220px;
  background: radial-gradient(circle, rgba(59,130,246,0.12) 0%, transparent 70%);
  pointer-events: none;
}

.app-sidebar--drawer {
  width: 100%;
  border-right: none;
  padding-top: 16px;
}

/* 品牌区域 */
.app-sidebar__brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  cursor: pointer;
  border-radius: 10px;
  transition: background 0.18s ease;
  margin-bottom: 8px;
}

.app-sidebar__brand:hover {
  background: rgba(255,255,255,0.06);
}

.app-sidebar__logo {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border-radius: 10px;
  background: linear-gradient(135deg, #60a5fa 0%, #93c5fd 100%);
  flex-shrink: 0;
  box-shadow: 0 4px 16px rgba(96,165,250,0.28);
}

.app-sidebar__logo-img {
  width: 34px;
  height: 34px;
  border-radius: 12px;
  object-fit: cover;
  user-select: none;
  pointer-events: none;
}

.app-sidebar__brand-title {
  font-size: 17px;
  font-weight: 700;
  color: #f1f5f9;
  letter-spacing: 0.5px;
}

.app-sidebar__brand-subtitle {
  margin-top: 1px;
  font-size: 11px;
  color: rgba(148,163,184,0.8);
  letter-spacing: 0.3px;
}

/* 新建问答按钮 */
.app-sidebar__new-chat {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 10px 12px;
  margin-bottom: 8px;
  border: 1px dashed rgba(59,130,246,0.4);
  border-radius: 10px;
  background: rgba(59,130,246,0.08);
  color: #60a5fa;
  font-size: 13.5px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.18s ease;
}

.app-sidebar__new-chat:hover {
  background: rgba(59,130,246,0.15);
  border-color: rgba(59,130,246,0.6);
  color: #93c5fd;
}

.app-sidebar__new-chat-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  background: rgba(59,130,246,0.2);
}

/* 导航 */
.app-sidebar__nav {
  display: flex;
  flex-direction: column;
  gap: 16px;
  flex: 1;
  overflow-y: auto;
}

.app-sidebar__nav::-webkit-scrollbar { display: none; }

.app-sidebar__nav-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.app-sidebar__nav-label {
  font-size: 10.5px;
  font-weight: 600;
  color: rgba(148,163,184,0.5);
  text-transform: uppercase;
  letter-spacing: 0.8px;
  padding: 0 12px;
  margin-bottom: 4px;
}

.app-sidebar__nav-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 9px 12px;
  border: none;
  border-radius: 9px;
  background: transparent;
  color: rgba(148,163,184,0.85);
  font-size: 13.5px;
  font-weight: 500;
  text-align: left;
  cursor: pointer;
  transition: all 0.16s ease;
}

.app-sidebar__nav-item:hover {
  background: rgba(255,255,255,0.07);
  color: #e2e8f0;
}

.app-sidebar__nav-item.is-active {
  background: rgba(59,130,246,0.15);
  color: #93c5fd;
}

.app-sidebar__nav-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 7px;
  background: rgba(255,255,255,0.06);
  flex-shrink: 0;
  transition: all 0.16s ease;
}

.app-sidebar__nav-item.is-active .app-sidebar__nav-icon {
  background: rgba(59,130,246,0.25);
  color: #60a5fa;
}

.app-sidebar__nav-indicator {
  position: absolute;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 3px;
  height: 20px;
  background: #3b82f6;
  border-radius: 3px 0 0 3px;
}

/* 底部用户区 */
.app-sidebar__footer {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 8px;
  margin-top: auto;
  border-top: 1px solid rgba(255,255,255,0.07);
  padding-top: 14px;
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.16s ease;
}

.app-sidebar__footer:hover {
  background: rgba(255,255,255,0.07);
}

.app-sidebar__avatar-wrap {
  position: relative;
  flex-shrink: 0;
}

.app-sidebar__avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: linear-gradient(135deg, #3b82f6, #6366f1);
  color: #fff;
  font-size: 13px;
  font-weight: 700;
  box-shadow: 0 2px 8px rgba(99,102,241,0.3);
}

.app-sidebar__status-dot {
  position: absolute;
  bottom: 1px;
  right: 1px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #22c55e;
  border: 2px solid #0f1629;
}

.app-sidebar__user {
  flex: 1;
  min-width: 0;
}

.app-sidebar__user-name {
  font-size: 13px;
  font-weight: 600;
  color: #e2e8f0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.app-sidebar__user-role {
  margin-top: 1px;
  font-size: 11px;
  color: rgba(148,163,184,0.6);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.app-sidebar__footer-icon {
  flex-shrink: 0;
  color: rgba(148,163,184,0.5);
}
</style>