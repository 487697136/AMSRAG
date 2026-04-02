import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createDiscreteApi } from 'naive-ui'
import App from './App.vue'
import router from './router'

import './assets/styles/design-tokens.css'
import './assets/styles/base.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)

// 全局错误处理：捕获组件内未处理的异常并展示友好 Toast
const { message } = createDiscreteApi(['message'])

app.config.errorHandler = (err, _vm, info) => {
  console.error('[全局错误]', info, err)
  const text = err?.response?.data?.detail || err?.message || '发生未知错误，请刷新重试'
  message.error(text, { duration: 5000, keepAliveOnHover: true })
}

window.addEventListener('unhandledrejection', (event) => {
  const err = event.reason
  if (err?.name === 'AbortError') return // 用户主动取消，忽略
  console.error('[未处理 Promise 拒绝]', err)
  const text = err?.response?.data?.detail || err?.message || '网络请求失败，请检查连接'
  message.error(text, { duration: 5000, keepAliveOnHover: true })
})

app.mount('#app')
