<template>
  <div class="settings-page page-shell">
    <PageHeader title="系统设置" description="管理账户信息、模型密钥与后端运行环境状态。"></PageHeader>

    <div class="settings-overview-grid">
      <InfoCard label="图谱后端" :value="graphBackendLabel" :caption="graphBackendCaption" tone="info" />
      <InfoCard label="上传限制" :value="uploadLimitLabel" caption="当前允许上传的最大文件大小" tone="muted" />
      <InfoCard label="已配置密钥" :value="providerStore.configuredKeys.length" caption="当前账号下已配置的所有密钥数量" tone="muted" />
    </div>

    <div class="settings-layout">
      <SectionCard title="设置导航" description="按主题查看账户、密钥和运行时状态。" size="compact">
        <div class="settings-nav">
          <button
            v-for="section in settingSections"
            :key="section.key"
            type="button"
            class="settings-nav__item"
            :class="{ 'is-active': activeSettingSection === section.key }"
            @click="activeSettingSection = section.key"
          >
            <div class="settings-nav__title">{{ section.label }}</div>
            <div class="settings-nav__desc">{{ section.description }}</div>
          </button>
        </div>
      </SectionCard>

      <SectionCard :title="currentSection?.label || '系统设置'" :description="currentSection?.description || ''">
        <n-spin :show="loading">
          <template v-if="activeSettingSection === 'account'">
            <div class="detail-meta-list">
              <div class="detail-meta-item"><span>用户名</span><strong>{{ userInfo?.username || '--' }}</strong></div>
              <div class="detail-meta-item"><span>邮箱</span><strong>{{ userInfo?.email || '--' }}</strong></div>
              <div class="detail-meta-item"><span>姓名</span><strong>{{ userInfo?.full_name || '--' }}</strong></div>
              <div class="detail-meta-item"><span>注册时间</span><strong>{{ formatDateTime(userInfo?.created_at) }}</strong></div>
            </div>
          </template>

          <template v-else-if="activeSettingSection === 'providers'">
            <div class="provider-block">
              <div class="provider-block__head">
                <div>
                  <div class="provider-section__title">LLM 密钥</div>
                  <div class="provider-section__hint">用于问答生成。你可以为同一种服务商配置/更新同一条密钥。</div>
                </div>
                <n-button size="small" type="primary" @click="openAddModal('llm')">新增密钥</n-button>
              </div>

              <div class="provider-list">
                <div v-for="k in providerStore.llmKeys" :key="k.id" class="provider-card">
                  <div class="provider-card__header">
                    <div>
                      <div class="provider-card__title">{{ providerStore.displayKeyName(k) }}</div>
                      <div class="provider-card__desc">{{ providerStore.providerLabel(k.provider) }}</div>
                    </div>
                    <span class="status-badge status-badge--success">已配置</span>
                  </div>
                  <div class="provider-card__actions">
                    <n-button size="small" type="primary" :loading="savingProvider === k.id" @click="openEditModal(k)">编辑</n-button>
                    <n-button size="small" type="error" quaternary @click="handleDeleteProvider(k)">删除</n-button>
                  </div>
                </div>
                <AppEmpty v-if="!providerStore.llmKeys.length" description="尚未配置 LLM 密钥，请新增后即可使用问答功能。" />
              </div>
            </div>

            <div class="provider-block provider-block--mt">
              <div class="provider-block__head">
                <div>
                  <div class="provider-section__title">嵌入密钥</div>
                  <div class="provider-section__hint">用于文档向量化检索。可在新增/编辑密钥时选择具体嵌入模型。</div>
                </div>
                <n-button size="small" type="primary" @click="openAddModal('embedding')">新增密钥</n-button>
              </div>

              <div class="provider-list">
                <div v-for="k in providerStore.embeddingKeys" :key="k.id" class="provider-card">
                  <div class="provider-card__header">
                    <div>
                      <div class="provider-card__title">{{ providerStore.displayKeyName(k) }}</div>
                      <div class="provider-card__desc">
                        {{ providerStore.providerLabel(k.provider) }}
                        <span v-if="k.model_name" :class="['model-badge', k.model_name.startsWith('Pro/') ? 'model-badge--pro' : '']">
                          {{ k.model_name }}{{ k.model_name.startsWith('Pro/') ? '（付费）' : '' }}
                        </span>
                        <span v-else class="model-badge model-badge--default">BAAI/bge-m3（默认·免费）</span>
                      </div>
                    </div>
                    <span class="status-badge status-badge--success">已配置</span>
                  </div>
                  <div class="provider-card__actions">
                    <n-button size="small" type="primary" :loading="savingProvider === k.id" @click="openEditModal(k)">编辑</n-button>
                    <n-button size="small" type="error" quaternary @click="handleDeleteProvider(k)">删除</n-button>
                  </div>
                </div>
                <AppEmpty v-if="!providerStore.embeddingKeys.length" description="尚未配置嵌入密钥，上传文档时将无法完成向量化处理。" />
              </div>
            </div>

            <n-modal v-model:show="showKeyModal" preset="card" style="max-width: 520px" title="密钥管理">
              <div class="create-form">
                <n-form-item label="服务商类型">
                  <n-input :value="modalTypeLabel" disabled />
                </n-form-item>
                <n-form-item label="服务商">
                  <n-select v-model:value="keyModal.provider" :options="modalProviderOptions" :disabled="modalMode === 'edit'" />
                </n-form-item>
                <!-- 嵌入模型选择（仅 embedding 类型显示） -->
                <n-form-item v-if="modalType === 'embedding'" label="嵌入模型">
                  <n-select
                    v-model:value="keyModal.modelName"
                    :options="modalEmbeddingModelOptions"
                    placeholder="选择嵌入模型"
                  />
                  <template #feedback>
                    <span style="font-size:12px;color:var(--n-text-color-3)">
                      Pro/BAAI/bge-m3 为高性能版本，与标准版使用同一 API Key
                    </span>
                  </template>
                </n-form-item>
                <n-form-item label="密钥名称（自定义）">
                  <n-input v-model:value="keyModal.description" placeholder="例如：公司内网 LLM / 生产环境 / 某模型组" />
                </n-form-item>
                <n-form-item label="API Key">
                  <n-input v-model:value="keyModal.apiKey" type="password" show-password-on="click" placeholder="请输入 API Key" />
                </n-form-item>
              </div>
              <template #footer>
                <n-space justify="end">
                  <n-button @click="showKeyModal = false">取消</n-button>
                  <n-button type="primary" :loading="!!savingProvider" @click="handleSaveKeyModal">保存</n-button>
                </n-space>
              </template>
            </n-modal>
          </template>

          <template v-else-if="activeSettingSection === 'runtime'">
            <div class="detail-meta-list">
              <div class="detail-meta-item"><span>图谱后端</span><strong>{{ graphBackendLabel }}</strong></div>
              <div class="detail-meta-item"><span>允许扩展名</span><strong>{{ allowedExtensionsLabel }}</strong></div>
              <div v-if="runtimeStatus?.neo4j?.configured" class="detail-meta-item"><span>Neo4j 状态</span><strong>{{ neo4jConnected ? '已连接' : '不可用' }}</strong></div>
              <div v-if="runtimeStatus?.neo4j?.url" class="detail-meta-item"><span>Neo4j 地址</span><strong>{{ runtimeStatus.neo4j.url }}</strong></div>
              <div class="detail-meta-item detail-meta-item--full"><span>工作区根目录</span><strong>{{ runtimeStatus?.paths?.workspace_root || '--' }}</strong></div>
              <div class="detail-meta-item detail-meta-item--full"><span>上传目录</span><strong>{{ runtimeStatus?.paths?.upload_root || '--' }}</strong></div>
            </div>
          </template>

          <template v-else>
            <div class="security-form">
              <n-form-item label="当前密码"><n-input v-model:value="passwordForm.old_password" type="password" show-password-on="click" placeholder="输入当前密码" /></n-form-item>
              <n-form-item label="新密码"><n-input v-model:value="passwordForm.new_password" type="password" show-password-on="click" placeholder="输入新密码（至少 6 位）" /></n-form-item>
              <n-form-item label="确认新密码"><n-input v-model:value="passwordForm.confirm_password" type="password" show-password-on="click" placeholder="再次输入新密码" /></n-form-item>
              <div class="security-form__actions"><n-button type="primary" :loading="changingPassword" @click="handleChangePassword">更新密码</n-button></div>
            </div>
          </template>
        </n-spin>
      </SectionCard>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { NButton, NFormItem, NInput, NModal, NSelect, NSpace, NSpin, useMessage } from 'naive-ui'
import { changePassword, deleteApiKey, fetchCurrentUser, getRuntimeStatus, saveApiKey } from '@/api/zhiyuan'
import AppEmpty from '@/components/common/AppEmpty.vue'
import InfoCard from '@/components/common/InfoCard.vue'
import SectionCard from '@/components/common/SectionCard.vue'
import PageHeader from '@/components/layout/PageHeader.vue'
import { formatBytes, formatDateTime } from '@/utils/formatters'
import { useAuthStore } from '@/stores/auth'
import { useProviderStore } from '@/stores/provider'

const message = useMessage()
const authStore = useAuthStore()
const providerStore = useProviderStore()
const loading = ref(false)
const savingProvider = ref('')
const changingPassword = ref(false)
const activeSettingSection = ref('account')
const userInfo = ref(null)
const runtimeStatus = ref(null)

const settingSections = [
  { key: 'account', label: '账户信息', description: '查看当前登录账号的基础资料。' },
  { key: 'providers', label: '模型密钥', description: '管理 LLM 与嵌入模型服务商 API Key。' },
  { key: 'runtime', label: '运行状态', description: '查看图谱后端、上传限制和目录配置。' },
  { key: 'security', label: '安全设置', description: '修改当前账号密码。' }
]

const passwordForm = reactive({ old_password: '', new_password: '', confirm_password: '' })
const currentSection = computed(() => settingSections.find((item) => item.key === activeSettingSection.value))
const neo4jConnected = computed(() => Boolean(runtimeStatus.value?.neo4j?.connected))
const uploadLimitLabel = computed(() => formatBytes(runtimeStatus.value?.upload?.max_upload_size || 0))
const allowedExtensionsLabel = computed(() => (runtimeStatus.value?.upload?.allowed_extensions || []).join(', ') || '--')
const graphBackendLabel = computed(() => {
  const requested = runtimeStatus.value?.graph_backend_requested
  if (!requested) return '--'
  if (requested === 'networkx') return 'NetworkX（本地图谱）'
  if (requested === 'neo4j') return neo4jConnected.value ? 'Neo4j（已连接）' : 'Neo4j（未连接）'
  return requested
})
const graphBackendCaption = computed(() => {
  const requested = runtimeStatus.value?.graph_backend_requested
  if (requested === 'neo4j' && !neo4jConnected.value) return 'Neo4j 未连接，将自动回退到本地图谱'
  if (requested === 'networkx') return '使用本地 NetworkX 存储图谱数据'
  return '当前图谱存储后端'
})

// Key modal state
const showKeyModal = ref(false)
const modalMode = ref('add')
const modalType = ref('llm')
const keyModal = reactive({ id: null, provider: '', description: '', apiKey: '', modelName: '' })

const modalTypeLabel = computed(() => (modalType.value === 'llm' ? 'LLM 密钥' : '嵌入密钥'))

const modalProviderOptions = computed(() => {
  const type = modalType.value === 'llm' ? 'llm' : 'embedding'
  return Object.entries(providerStore.registry || {})
    .filter(([, v]) => v?.type === type)
    .map(([provider, info]) => ({ label: info?.label || provider, value: provider }))
})

// 当前选中嵌入 provider 的可用模型列表
const modalEmbeddingModelOptions = computed(() => {
  if (modalType.value !== 'embedding' || !keyModal.provider) return []
  const models = providerStore.registry?.[keyModal.provider]?.default_models || []
  return models.map((m) => ({
    label: m.startsWith('Pro/') ? `${m}（付费账号）` : `${m}（免费）`,
    value: m,
  }))
})

function resetKeyModal() {
  keyModal.id = null
  keyModal.provider = modalProviderOptions.value[0]?.value || ''
  keyModal.description = ''
  keyModal.apiKey = ''
  // 嵌入模型默认取第一个（即 BAAI/bge-m3）
  const defaultProvider = keyModal.provider
  const models = providerStore.registry?.[defaultProvider]?.default_models || []
  keyModal.modelName = models[0] || ''
}

function openAddModal(type) {
  modalMode.value = 'add'
  modalType.value = type
  resetKeyModal()
  showKeyModal.value = true
}

function openEditModal(key) {
  modalMode.value = 'edit'
  modalType.value = providerStore.registry?.[key.provider]?.type || 'llm'
  keyModal.id = key.id
  keyModal.provider = key.provider
  keyModal.description = key.description || ''
  keyModal.apiKey = ''
  // 回填已保存的模型名称
  const savedModel = key.model_name
  const availableModels = providerStore.registry?.[key.provider]?.default_models || []
  keyModal.modelName = savedModel || availableModels[0] || ''
  showKeyModal.value = true
}

async function handleSaveKeyModal() {
  if (!keyModal.provider) { message.warning('请选择服务商'); return }
  if (!keyModal.apiKey.trim()) { message.warning('请输入 API Key'); return }
  try {
    savingProvider.value = keyModal.id || '__new__'
    await saveApiKey({
      provider: keyModal.provider,
      description: keyModal.description || null,
      api_key: keyModal.apiKey.trim(),
      model_name: modalType.value === 'embedding' ? (keyModal.modelName || null) : null,
    })
    message.success('密钥已保存')
    showKeyModal.value = false
    providerStore.invalidate()
    await providerStore.fetchProviders(true)
  } catch (error) {
    message.error(error.response?.data?.detail || '保存密钥失败')
  } finally {
    savingProvider.value = ''
  }
}

async function handleDeleteProvider(key) {
  if (!key?.id) return
  try {
    savingProvider.value = key.id
    await deleteApiKey(key.id)
    message.success('密钥已删除')
    providerStore.invalidate()
    await providerStore.fetchProviders(true)
  } catch (error) {
    message.error(error.response?.data?.detail || '删除密钥失败')
  } finally {
    savingProvider.value = ''
  }
}

async function loadSettingsData() {
  loading.value = true
  try {
    const [currentUser, runtime] = await Promise.all([
      fetchCurrentUser(),
      getRuntimeStatus(),
      providerStore.fetchProviders(true),
    ])
    userInfo.value = currentUser
    authStore.user = currentUser
    runtimeStatus.value = runtime
  } catch (error) {
    message.error(error.response?.data?.detail || '加载设置数据失败')
  } finally {
    loading.value = false
  }
}

async function handleChangePassword() {
  if (!passwordForm.old_password || !passwordForm.new_password) {
    message.warning('请完整输入当前密码和新密码')
    return
  }
  if (passwordForm.new_password.length < 6) {
    message.warning('新密码长度不能少于 6 位')
    return
  }
  if (passwordForm.new_password !== passwordForm.confirm_password) {
    message.warning('两次输入的新密码不一致')
    return
  }
  changingPassword.value = true
  try {
    await changePassword({ old_password: passwordForm.old_password, new_password: passwordForm.new_password })
    passwordForm.old_password = ''
    passwordForm.new_password = ''
    passwordForm.confirm_password = ''
    message.success('密码已更新')
  } catch (error) {
    message.error(error.response?.data?.detail || '修改密码失败')
  } finally {
    changingPassword.value = false
  }
}

onMounted(loadSettingsData)
</script>

<style scoped>
.settings-overview-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; }
.settings-layout { display:grid; grid-template-columns:280px minmax(0,1fr); gap:16px; align-items:start; }
.settings-nav { display:flex; flex-direction:column; gap:10px; }
.settings-nav__item { width:100%; padding:14px 16px; border:1px solid var(--border-color); border-radius:12px; background:var(--surface-card); text-align:left; cursor:pointer; transition:all var(--transition-fast); }
.settings-nav__item:hover,.settings-nav__item.is-active { border-color:var(--brand-soft-border); background:var(--surface-hover); }
.settings-nav__title { font-size:14px; font-weight:700; color:var(--text-1); }
.settings-nav__desc { margin-top:6px; font-size:12px; line-height:1.6; color:var(--text-4); }
.provider-block { display:flex; flex-direction:column; gap:14px; }
.provider-block__head { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
.provider-block--mt { margin-top: 24px; }
.detail-meta-list { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }
.detail-meta-item { padding:14px 16px; border-radius:12px; background:var(--surface-muted); border:1px solid var(--border-color); display:flex; flex-direction:column; gap:6px; }
.detail-meta-item span { display:block; font-size:12px; color:var(--text-4); }
.detail-meta-item strong { font-size:14px; color:var(--text-1); word-break:break-word; }
.detail-meta-item--full { grid-column:1 / -1; }
.provider-list { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }
.provider-card { padding:14px 16px; border-radius:12px; background:var(--surface-muted); border:1px solid var(--border-color); }
.provider-card__header { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; }
.provider-card__actions { display:flex; gap:10px; margin-top: 10px; }
.provider-card__title { font-size:15px; font-weight:700; color:var(--text-1); }
.provider-card__desc { margin-top:4px; font-size:12px; color:var(--text-4); display:flex; align-items:center; gap:6px; flex-wrap:wrap; }
.model-badge { display:inline-flex; align-items:center; height:18px; padding:0 7px; border-radius:999px; background:rgba(37,99,235,0.10); border:1px solid rgba(37,99,235,0.18); color:var(--brand-600); font-size:11px; font-weight:700; white-space:nowrap; }
.model-badge--default { background:rgba(100,116,139,0.10); border-color:rgba(100,116,139,0.20); color:var(--text-4); }
.model-badge--pro { background:rgba(217,119,6,0.12); border-color:rgba(217,119,6,0.30); color:#b45309; }
.provider-section__title { font-size:15px; font-weight:700; color:var(--text-1); margin-bottom:4px; }
.provider-section__hint { font-size:12px; color:var(--text-4); margin-bottom:12px; }
.security-form { display:flex; flex-direction:column; gap:8px; }
.security-form__actions { margin-top: 12px; }
@media (max-width: 1200px) { .settings-overview-grid,.settings-layout,.detail-meta-list,.provider-list { grid-template-columns:1fr; } .provider-list { grid-template-columns:1fr; } }
</style>
