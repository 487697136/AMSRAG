import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import { hardRedirectToLogin } from '@/api/redirect'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 120000  // 增加到120秒，给文件上传更多时间
})

// 请求拦截器
api.interceptors.request.use(
  (config) => {
    const authStore = useAuthStore()
    if (authStore.token) {
      config.headers.Authorization = `Bearer ${authStore.token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  (response) => {
    return response
  },
  (error) => {
    if (error.response?.status === 401) {
      const authStore = useAuthStore()
      authStore.logout()
      hardRedirectToLogin()
    }
    return Promise.reject(error)
  }
)

export default api
