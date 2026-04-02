<template>
  <div class="login-container">
    <div class="login-background">
      <div class="bg-shape shape-1"></div>
      <div class="bg-shape shape-2"></div>
      <div class="bg-shape shape-3"></div>
    </div>

    <div class="login-content">
      <!-- 左侧品牌区域 -->
      <div class="brand-section">
        <div class="brand-logo">
          <svg width="80" height="80" viewBox="0 0 100 100" fill="none">
            <!-- Central node -->
            <circle cx="50" cy="50" r="12" fill="white" opacity="0.95"/>
            <!-- Outer nodes -->
            <circle cx="50" cy="16" r="7" fill="white" opacity="0.8"/>
            <circle cx="80" cy="32" r="6" fill="white" opacity="0.7"/>
            <circle cx="80" cy="68" r="6" fill="white" opacity="0.7"/>
            <circle cx="50" cy="84" r="7" fill="white" opacity="0.8"/>
            <circle cx="20" cy="68" r="6" fill="white" opacity="0.7"/>
            <circle cx="20" cy="32" r="6" fill="white" opacity="0.7"/>
            <!-- Edges -->
            <line x1="50" y1="23" x2="50" y2="38" stroke="white" stroke-width="2" opacity="0.5"/>
            <line x1="74" y1="35" x2="61" y2="43" stroke="white" stroke-width="2" opacity="0.5"/>
            <line x1="74" y1="65" x2="61" y2="57" stroke="white" stroke-width="2" opacity="0.5"/>
            <line x1="50" y1="77" x2="50" y2="62" stroke="white" stroke-width="2" opacity="0.5"/>
            <line x1="26" y1="65" x2="39" y2="57" stroke="white" stroke-width="2" opacity="0.5"/>
            <line x1="26" y1="35" x2="39" y2="43" stroke="white" stroke-width="2" opacity="0.5"/>
            <!-- Glow rings -->
            <circle cx="50" cy="50" r="20" fill="none" stroke="white" stroke-width="1" opacity="0.2"/>
            <circle cx="50" cy="50" r="36" fill="none" stroke="white" stroke-width="0.5" opacity="0.12" stroke-dasharray="4 6"/>
          </svg>
        </div>
        <h1 class="brand-title">知源</h1>
        <p class="brand-subtitle">基于知识图谱与多源融合检索的<br>智能知识服务系统</p>
        <div class="brand-features">
          <div class="feature-item">
            <n-icon size="20" :component="CheckmarkCircleOutline" color="rgba(255,255,255,0.9)" />
            <span>知识图谱可视化探索</span>
          </div>
          <div class="feature-item">
            <n-icon size="20" :component="CheckmarkCircleOutline" color="rgba(255,255,255,0.9)" />
            <span>多源融合检索增强生成</span>
          </div>
          <div class="feature-item">
            <n-icon size="20" :component="CheckmarkCircleOutline" color="rgba(255,255,255,0.9)" />
            <span>复杂度自适应查询路由</span>
          </div>
          <div class="feature-item">
            <n-icon size="20" :component="CheckmarkCircleOutline" color="rgba(255,255,255,0.9)" />
            <span>流式实时问答响应</span>
          </div>
        </div>
      </div>

      <!-- 右侧登录表单 -->
      <div class="form-section">
        <n-card class="login-card" :bordered="false">
          <div class="card-header">
            <h2>欢迎使用知源</h2>
            <n-text depth="3">登录账户，开启智能知识探索之旅</n-text>
          </div>

          <n-tabs v-model:value="activeTab" type="segment" animated size="large">
            <n-tab-pane name="login" tab="登录">
              <n-form 
                ref="loginFormRef" 
                :model="loginForm" 
                :rules="loginRules" 
                size="large"
                style="margin-top: 24px"
              >
                <n-form-item path="username">
                  <n-input
                    v-model:value="loginForm.username"
                    placeholder="用户名"
                    size="large"
                    @keyup.enter="handleLogin"
                  >
                    <template #prefix>
                      <n-icon :component="PersonOutline" />
                    </template>
                  </n-input>
                </n-form-item>
                <n-form-item path="password">
                  <n-input
                    v-model:value="loginForm.password"
                    type="password"
                    show-password-on="click"
                    placeholder="密码"
                    size="large"
                    @keyup.enter="handleLogin"
                  >
                    <template #prefix>
                      <n-icon :component="LockClosedOutline" />
                    </template>
                  </n-input>
                </n-form-item>
                
                <n-space vertical :size="16" style="width: 100%">
                  <n-button
                    type="primary"
                    size="large"
                    block
                    :loading="loading"
                    @click="handleLogin"
                    class="login-btn"
                  >
                    <template #icon>
                      <n-icon :component="LogInOutline" />
                    </template>
                    登录
                  </n-button>
                </n-space>
              </n-form>
            </n-tab-pane>

            <n-tab-pane name="register" tab="注册">
              <n-form 
                ref="registerFormRef" 
                :model="registerForm" 
                :rules="registerRules" 
                size="large"
                style="margin-top: 24px"
              >
                <n-form-item path="username">
                  <n-input
                    v-model:value="registerForm.username"
                    placeholder="用户名 (3-20个字符)"
                    size="large"
                  >
                    <template #prefix>
                      <n-icon :component="PersonOutline" />
                    </template>
                  </n-input>
                </n-form-item>
                <n-form-item path="email">
                  <n-input
                    v-model:value="registerForm.email"
                    placeholder="邮箱地址"
                    size="large"
                  >
                    <template #prefix>
                      <n-icon :component="MailOutline" />
                    </template>
                  </n-input>
                </n-form-item>
                <n-form-item path="password">
                  <n-input
                    v-model:value="registerForm.password"
                    type="password"
                    show-password-on="click"
                    placeholder="密码 (至少6位)"
                    size="large"
                  >
                    <template #prefix>
                      <n-icon :component="LockClosedOutline" />
                    </template>
                  </n-input>
                </n-form-item>
                <n-form-item path="confirmPassword">
                  <n-input
                    v-model:value="registerForm.confirmPassword"
                    type="password"
                    show-password-on="click"
                    placeholder="确认密码"
                    size="large"
                    @keyup.enter="handleRegister"
                  >
                    <template #prefix>
                      <n-icon :component="LockClosedOutline" />
                    </template>
                  </n-input>
                </n-form-item>
                <n-button
                  type="primary"
                  size="large"
                  block
                  :loading="loading"
                  @click="handleRegister"
                  class="login-btn"
                >
                  <template #icon>
                    <n-icon :component="PersonAddOutline" />
                  </template>
                  注册
                </n-button>
              </n-form>
            </n-tab-pane>
          </n-tabs>
        </n-card>

        <div class="footer-text">
          <n-text depth="3" style="font-size: 13px">
            © 2026 知源 · 智能知识服务系统
          </n-text>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { 
  useMessage, NCard, NTabs, NTabPane, NForm, NFormItem, NInput, 
  NButton, NText, NIcon, NSpace 
} from 'naive-ui'
import {
  CheckmarkCircleOutline, PersonOutline, 
  LockClosedOutline, LogInOutline, PersonAddOutline, MailOutline
} from '@vicons/ionicons5'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const message = useMessage()
const authStore = useAuthStore()

const activeTab = ref('login')
const loading = ref(false)
const loginFormRef = ref(null)
const registerFormRef = ref(null)

const loginForm = ref({
  username: '',
  password: ''
})

const registerForm = ref({
  username: '',
  email: '',
  password: '',
  confirmPassword: ''
})

const loginRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' }
  ]
}

const registerRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 20, message: '用户名长度为 3-20 个字符', trigger: 'blur' }
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入有效的邮箱地址', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 个字符', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (rule, value) => {
        return value === registerForm.value.password
      },
      message: '两次输入的密码不一致',
      trigger: 'blur'
    }
  ]
}

const handleLogin = async () => {
  try {
    await loginFormRef.value?.validate()
    loading.value = true
    
    await authStore.login(loginForm.value.username, loginForm.value.password)
    
    message.success('登录成功，欢迎回来！')
    const redirect = router.currentRoute.value.query.redirect
    if (typeof redirect === 'string' && redirect.startsWith('/')) {
      router.push(redirect)
    } else {
      router.push('/')
    }
  } catch (error) {
    if (error.response) {
      message.error(error.response.data.detail || '登录失败，请检查用户名和密码')
    } else if (!error.errors) {
      message.error('登录失败，请检查网络连接')
    }
  } finally {
    loading.value = false
  }
}

const handleRegister = async () => {
  try {
    await registerFormRef.value?.validate()
    loading.value = true
    
    await authStore.register(
      registerForm.value.username,
      registerForm.value.email,
      registerForm.value.password
    )
    
    message.success('注册成功，请登录')
    activeTab.value = 'login'
    loginForm.value.username = registerForm.value.username
  } catch (error) {
    if (error.response) {
      message.error(error.response.data.detail || '注册失败')
    } else if (!error.errors) {
      message.error('注册失败，请检查网络连接')
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  overflow: hidden;
  background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 40%, #1d4ed8 70%, #2563eb 100%);
}

.login-background {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  overflow: hidden;
}

.bg-shape {
  position: absolute;
  border-radius: var(--radius-full);
  filter: blur(60px);
}

.shape-1 {
  width: 700px;
  height: 700px;
  top: -300px;
  left: -200px;
  background: rgba(99, 102, 241, 0.2);
  animation: float 22s ease-in-out infinite;
}

.shape-2 {
  width: 500px;
  height: 500px;
  bottom: -150px;
  right: -150px;
  background: rgba(59, 130, 246, 0.25);
  animation: float 18s ease-in-out infinite reverse;
}

.shape-3 {
  width: 400px;
  height: 400px;
  top: 40%;
  left: 45%;
  background: rgba(139, 92, 246, 0.12);
  animation: float 28s ease-in-out infinite;
}

@keyframes float {
  0%, 100% {
    transform: translate(0, 0) scale(1);
  }
  33% {
    transform: translate(20px, -25px) scale(1.04);
  }
  66% {
    transform: translate(-15px, 15px) scale(0.97);
  }
}

.login-content {
  position: relative;
  display: flex;
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--spacing-4xl);
  gap: var(--spacing-6xl);
  align-items: center;
  z-index: 1;
}

.brand-section {
  flex: 1;
  color: var(--text-inverse);
  text-align: center;
}

.brand-logo {
  margin-bottom: var(--spacing-2xl);
  animation: logo-float 4s ease-in-out infinite;
  filter: drop-shadow(0 8px 32px rgba(255, 255, 255, 0.2));
}

@keyframes logo-float {
  0%, 100% { transform: translateY(0) scale(1); }
  50% { transform: translateY(-6px) scale(1.03); }
}

.brand-title {
  font-size: var(--font-6xl);
  font-weight: var(--font-weight-bold);
  margin: 0 0 var(--spacing-md) 0;
  text-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
  letter-spacing: 2px;
}

.brand-subtitle {
  font-size: var(--font-xl);
  margin: 0 0 var(--spacing-5xl) 0;
  opacity: 0.95;
  font-weight: var(--font-weight-normal);
}

.brand-features {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xl);
  align-items: flex-start;
  max-width: 400px;
  margin: 0 auto;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  font-size: var(--font-lg);
  opacity: 0.9;
  transition: all var(--transition-base);
}

.feature-item:hover {
  opacity: 1;
  transform: translateX(4px);
}

.form-section {
  flex: 1;
  max-width: 480px;
}

.login-card {
  background: rgba(255, 255, 255, 0.98);
  backdrop-filter: blur(20px);
  border-radius: var(--radius-3xl);
  box-shadow: var(--shadow-2xl);
  padding: var(--spacing-4xl);
  transition: all var(--transition-slow);
}

.login-card:hover {
  box-shadow: 0 24px 52px -20px rgba(15, 23, 42, 0.28);
}

.card-header {
  text-align: center;
  margin-bottom: var(--spacing-3xl);
}

.card-header h2 {
  font-size: var(--font-4xl);
  font-weight: var(--font-weight-bold);
  margin: 0 0 var(--spacing-sm) 0;
  background: var(--primary-gradient);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.login-btn {
  height: 48px;
  font-size: var(--font-lg);
  font-weight: var(--font-weight-semibold);
  border-radius: var(--radius-lg);
  background: var(--primary-gradient);
  border: none;
  transition: all var(--transition-base);
  position: relative;
  overflow: hidden;
}

.login-btn::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
  transition: left 0.5s;
}

.login-btn:hover::before {
  left: 100%;
}

.login-btn:hover {
  background: linear-gradient(135deg, var(--brand-500) 0%, var(--brand-700) 100%);
  transform: translateY(-2px);
  box-shadow: var(--shadow-primary-lg);
}

.login-btn:active {
  transform: translateY(0) scale(0.98);
}

.footer-text {
  text-align: center;
  margin-top: var(--spacing-2xl);
  color: rgba(255, 255, 255, 0.8);
}

:deep(.n-input) {
  border-radius: var(--radius-lg);
  transition: all var(--transition-base);
}

:deep(.n-input:hover) {
  box-shadow: var(--shadow-sm);
}

:deep(.n-input.n-input--focus) {
  box-shadow: var(--shadow-md);
}

:deep(.n-tabs .n-tabs-nav) {
  background: var(--gray-100);
  border-radius: var(--radius-lg);
  padding: 4px;
}

:deep(.n-tabs .n-tabs-tab) {
  border-radius: var(--radius-md);
  font-weight: var(--font-weight-medium);
  transition: all var(--transition-base);
}

:deep(.n-tabs .n-tabs-tab:hover) {
  background: rgba(37, 99, 235, 0.1);
}

@media (max-width: 968px) {
  .login-content {
    flex-direction: column;
    gap: var(--spacing-4xl);
    padding: var(--spacing-2xl);
  }

  .brand-section {
    display: none;
  }

  .form-section {
    max-width: 100%;
  }
  
  .login-card {
    padding: var(--spacing-3xl);
  }
}
</style>
