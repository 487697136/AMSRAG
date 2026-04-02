import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/views/Login.vue'),
      meta: { requiresAuth: false }
    },
    {
      path: '/',
      component: () => import('@/components/layout/AppLayout.vue'),
      meta: { requiresAuth: true },
      children: [
        {
          path: '',
          redirect: '/chat'
        },
        {
          path: 'chat',
          name: 'Chat',
          component: () => import('@/views/chat/ChatPage.vue'),
          meta: { title: '智能问答' }
        },
        {
          path: 'sessions',
          name: 'Sessions',
          component: () => import('@/views/sessions/SessionsPage.vue'),
          meta: { title: '会话中心' }
        },
        {
          path: 'knowledge',
          name: 'Knowledge',
          component: () => import('@/views/knowledge/KnowledgePage.vue'),
          meta: { title: '知识库中心' }
        },
        {
          path: 'documents',
          name: 'Documents',
          component: () => import('@/views/documents/DocumentsPage.vue'),
          meta: { title: '文档中心' }
        },
        {
          path: 'graph',
          name: 'Graph',
          component: () => import('@/views/graph/GraphPage.vue'),
          meta: { title: '知识图谱' }
        },
        {
          path: 'settings',
          name: 'Settings',
          component: () => import('@/views/settings/SettingsPage.vue'),
          meta: { title: '系统设置' }
        }
      ]
    },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/chat'
    }
  ]
})

router.beforeEach((to, from, next) => {
  const authStore = useAuthStore()

  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    next('/login')
  } else if (to.path === '/login' && authStore.isAuthenticated) {
    next('/')
  } else {
    next()
  }
})

export default router
