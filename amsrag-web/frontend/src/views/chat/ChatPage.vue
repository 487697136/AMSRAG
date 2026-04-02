<template>
  <div class="chat-page" :class="chatScene === 'session' ? 'chat-page--session' : 'chat-page--home'">

    <!-- ──────────────── HOME SCENE ──────────────── -->
    <template v-if="chatScene === 'home'">
      <div class="chat-home">

        <!-- 无知识库提示 -->
        <n-alert
          v-if="knowledgeBaseList.length === 0"
          type="info"
          class="chat-home__alert"
          title="暂无知识库"
        >
          您可以直接使用<strong>「仅模型回答」</strong>模式进行对话；如需知识库增强，请前往<strong>知识库中心</strong>创建并上传文档。
        </n-alert>
        <n-alert
          v-else-if="selectedKnowledgeBaseStats && !selectedKnowledgeBaseStats.initialized && selectedAskMode !== 'llm_only'"
          type="warning"
          class="chat-home__alert"
          title="当前知识库尚未初始化"
        >
          请先上传文档并完成处理，或将模式切换为<strong>「仅模型回答」</strong>直接开始对话。
        </n-alert>

        <!-- 欢迎 Hero -->
        <div class="chat-home__hero">
          <div class="chat-home__hero-logo">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
              <circle cx="12" cy="6" r="2" fill="white"/>
              <circle cx="5" cy="17" r="2" fill="white" opacity="0.75"/>
              <circle cx="19" cy="17" r="2" fill="white" opacity="0.75"/>
              <line x1="12" y1="8" x2="5.8" y2="15.2" stroke="white" stroke-width="1.5" opacity="0.6"/>
              <line x1="12" y1="8" x2="18.2" y2="15.2" stroke="white" stroke-width="1.5" opacity="0.6"/>
              <line x1="6.5" y1="17" x2="17.5" y2="17" stroke="white" stroke-width="1.5" opacity="0.4"/>
            </svg>
          </div>
          <h1 class="chat-home__hero-title">你好，我是<em>知源</em></h1>
          <p class="chat-home__hero-desc">基于知识图谱与多源融合检索，精准解答您的问题</p>
        </div>

        <!-- 主输入区 -->
        <div class="chat-home__composer-wrap">
          <div class="chat-home__composer">
            <n-input
              v-model:value="draftQuestion"
              type="textarea"
              placeholder="向知源提问任何问题...（Enter 发送，Shift+Enter 换行）"
              :autosize="{ minRows: 3, maxRows: 8 }"
              class="chat-home__textarea"
              @keydown="handleComposerKeydown"
            />
            <div class="chat-home__composer-bar">
              <div class="chat-home__composer-selectors">
                <n-select
                  v-model:value="selectedKnowledgeBaseId"
                  :options="knowledgeBaseOptions"
                  style="width: 190px; flex-shrink: 0"
                  placeholder="选择知识库"
                  size="small"
                />

                <!-- Auto 滑块式开关：开启时不出现任何手动内容 -->
                <div
                  class="mode-auto-switch"
                  :class="{ 'mode-auto-switch--on': useAutoMode }"
                  role="group"
                  aria-label="Auto 智能路由"
                >
                  <div class="mode-auto-switch__text">
                    <div class="mode-auto-switch__title">Auto</div>
                    <div class="mode-auto-switch__desc">{{ useAutoMode ? '智能路由' : '手动模式' }}</div>
                  </div>
                  <n-switch v-model:value="useAutoMode" size="small" />
                </div>

                <!-- Manual mode selector (visible when Auto is OFF) -->
                <n-select
                  v-if="!useAutoMode"
                  v-model:value="selectedAskMode"
                  :options="effectiveQueryModeOptions"
                  style="width: 164px; flex-shrink: 0"
                  size="small"
                  placeholder="选择检索方式"
                />

                <n-select
                  v-if="configuredLlmProviders.length > 1"
                  v-model:value="selectedLlmProvider"
                  :options="llmProviderOptions"
                  style="width: 140px; flex-shrink: 0"
                  size="small"
                  placeholder="模型服务商"
                />

                <n-select
                  v-if="llmModelOptions.length > 0"
                  v-model:value="selectedLlmModel"
                  :options="llmModelOptions"
                  style="width: 190px; flex-shrink: 0"
                  size="small"
                  placeholder="模型"
                />

                <button class="chat-home__attach-btn" @click="handleUploadAttachment" title="上传附件">
                  <n-icon :component="AttachOutline" size="15" />
                </button>
              </div>
              <n-button
                :type="submitting ? 'default' : 'primary'"
                :disabled="!submitting && !draftQuestion.trim()"
                round
                @click="submitting ? handleStopGeneration() : handleSendQuestion()"
              >
                <template #icon>
                  <n-icon :component="submitting ? StopCircleOutline : SendOutline" />
                </template>
                {{ submitting ? '停止生成' : '发起问答' }}
              </n-button>
            </div>
          </div>

        </div>

        <!-- 信息面板行（保留原版信息结构，不显示推荐问题/能力入口） -->
        <div class="chat-home__panels">
          <!-- 近期会话 -->
          <div class="home-panel">
            <div class="home-panel__header home-panel__header--with-actions">
              <div class="home-panel__header-left">
                <n-icon :component="TimeOutline" size="14" />
                <span>近期会话</span>
              </div>
              <button
                v-if="recentSessions.length > 4"
                class="panel-link panel-link--muted"
                type="button"
                @click="router.push('/sessions')"
              >
                查看全部
              </button>
            </div>
            <div class="home-panel__body">
              <n-spin :show="sessionLoading" :size="16">
                <div v-if="recentSessionsPreview.length" class="session-list">
                <button
                  v-for="sess in recentSessionsPreview"
                  :key="sess.id"
                  class="session-item"
                  @click="openRecentSession(sess)"
                >
                  <div class="session-item__title">{{ sess.title }}</div>
                  <div class="session-item__meta">
                    <span>{{ sess.turn_count }} 轮对话</span>
                    <span>{{ formatDateTime(sess.updated_at || sess.last_active_at) }}</span>
                  </div>
                </button>
              </div>
              <p v-else class="panel-empty">发起第一次问答后，会话将在这里显示</p>
              </n-spin>
            </div>
          </div>

          <!-- 知识库速览 -->
          <div class="home-panel">
            <div class="home-panel__header">
              <n-icon :component="LibraryOutline" size="14" />
              <span>知识库速览</span>
            </div>
            <div class="home-panel__body">
              <n-spin :show="kbLoading" :size="16">
                <div v-if="knowledgeBasePreview.length" class="kb-quick-list">
                <button
                  v-for="kb in knowledgeBasePreview"
                  :key="kb.id"
                  class="kb-quick-item"
                  :class="{ 'is-active': selectedKnowledgeBaseId === String(kb.id) }"
                  @click="selectedKnowledgeBaseId = String(kb.id)"
                >
                  <div class="kb-quick-item__left">
                    <div class="kb-quick-item__dot" :class="`kb-quick-item__dot--${statusToneFromKnowledgeBase(kb)}`" />
                    <span class="kb-quick-item__name">{{ kb.name }}</span>
                  </div>
                  <span :class="['status-badge', `status-badge--${statusToneFromKnowledgeBase(kb)}`]">
                    {{ statusLabelFromKnowledgeBase(kb) }}
                  </span>
                </button>
              </div>
              <p v-else class="panel-empty">暂无知识库</p>
              </n-spin>
            </div>
            <div v-if="knowledgeBaseList.length > 5" class="home-panel__footer">
              <button class="panel-link" type="button" @click="router.push('/knowledge')">查看全部</button>
            </div>
          </div>

          <!-- 知识库运行状态 -->
          <div class="home-panel">
            <div class="home-panel__header">
              <n-icon :component="BarChartOutline" size="14" />
              <span>知识库状态</span>
            </div>
            <div class="home-panel__body">
              <n-spin :show="statsLoading" :size="16">
                <div v-if="selectedKnowledgeBaseStats" class="kb-stats-grid">
                <div class="kb-stat-item">
                  <span class="kb-stat-item__label">初始化</span>
                  <strong
                    class="kb-stat-item__value"
                    :class="selectedKnowledgeBaseStats.initialized ? 'text-success' : 'text-warning'"
                  >
                    {{ selectedKnowledgeBaseStats.initialized ? '已就绪' : '未初始化' }}
                  </strong>
                </div>
                <div class="kb-stat-item">
                  <span class="kb-stat-item__label">图谱来源</span>
                  <strong class="kb-stat-item__value">{{ graphSourceLabel }}</strong>
                </div>
                <div class="kb-stat-item">
                  <span class="kb-stat-item__label">文档</span>
                  <strong class="kb-stat-item__value">{{ selectedKnowledgeBaseStats.document_count || 0 }}</strong>
                </div>
                <div class="kb-stat-item">
                  <span class="kb-stat-item__label">切块</span>
                  <strong class="kb-stat-item__value">{{ selectedKnowledgeBaseStats.total_chunks || 0 }}</strong>
                </div>
                <div class="kb-stat-item">
                  <span class="kb-stat-item__label">实体</span>
                  <strong class="kb-stat-item__value">{{ selectedKnowledgeBaseStats.entity_count || 0 }}</strong>
                </div>
                <div class="kb-stat-item">
                  <span class="kb-stat-item__label">关系</span>
                  <strong class="kb-stat-item__value">{{ selectedKnowledgeBaseStats.relation_count || 0 }}</strong>
                </div>
              </div>
              <p v-else class="panel-empty">请在左侧选择一个知识库</p>
              </n-spin>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- ──────────────── SESSION SCENE ──────────────── -->
    <div v-else class="chat-session-layout" :class="{ 'chat-session-layout--collapsed': sidebarCollapsed }">

      <!-- 移动端侧栏遮罩 -->
      <transition name="mobile-sidebar-fade">
        <div
          v-if="mobileSidebarOpen"
          class="chat-mobile-overlay"
          @click="mobileSidebarOpen = false"
        />
      </transition>

      <!-- 左侧会话栏（主流 AI 对话布局） -->
      <aside class="chat-session-sidebar" :class="{ 'chat-session-sidebar--mobile-open': mobileSidebarOpen }">
        <div class="chat-session-sidebar__top">
          <div class="chat-session-sidebar__title">会话</div>
          <div class="chat-session-sidebar__top-actions">
            <!-- 移动端关闭按钮 -->
            <button class="chat-session-sidebar__close-mobile" type="button" @click="mobileSidebarOpen = false">✕</button>
            <button class="chat-session-sidebar__toggle" type="button" @click="sidebarCollapsed = !sidebarCollapsed">
              {{ sidebarCollapsed ? '展开' : '收起' }}
            </button>
            <button class="chat-session-sidebar__new" type="button" @click="handleStartFreshChat; mobileSidebarOpen = false">
              新建
            </button>
          </div>
        </div>

        <div v-show="!sidebarCollapsed" class="chat-session-sidebar__search">
          <n-input
            v-model:value="sessionSearchKeyword"
            clearable
            placeholder="搜索会话"
            size="small"
          />
        </div>

        <n-spin :show="sessionLoading" :size="16" class="chat-session-sidebar__spin">
          <div v-if="filteredSessions.length" class="chat-session-sidebar__list">
            <button
              v-for="sess in filteredSessions"
              :key="sess.id"
              type="button"
              class="chat-session-sidebar__item"
              :class="{ 'is-active': String(sess.id) === String(activeConversation?.session?.id) }"
              @click="openRecentSession(sess)"
            >
              <div class="chat-session-sidebar__item-main">
                <div class="chat-session-sidebar__item-title">
                  <span v-show="!sidebarCollapsed">{{ sess.title || `会话 #${sess.id}` }}</span>
                  <span v-show="sidebarCollapsed">#{{ sess.id }}</span>
                </div>
                <div v-show="!sidebarCollapsed" class="chat-session-sidebar__item-meta">
                  <span>{{ sess.turn_count }} 轮</span>
                  <span>{{ formatDateTime(sess.updated_at || sess.last_active_at) }}</span>
                </div>
              </div>
              <n-button
                text
                type="error"
                class="chat-session-sidebar__item-delete"
                @click.stop="confirmDeleteSession(sess.id)"
              >
                <template #icon><n-icon :component="TrashOutline" /></template>
              </n-button>
            </button>
          </div>
          <div v-else class="chat-session-sidebar__empty">
            暂无会话
          </div>
        </n-spin>
      </aside>

      <!-- 会话头部 -->
      <section class="chat-session">
      <div class="chat-session__header">
        <!-- 移动端：打开会话列表按钮 -->
        <button class="chat-mobile-sidebar-btn" type="button" @click="mobileSidebarOpen = true" title="查看会话列表">
          <n-icon :component="ChatbubbleEllipsesOutline" size="16" />
        </button>
        <button class="chat-back-btn" type="button" @click="handleStartFreshChat">
          <n-icon :component="HomeOutline" size="14" />
          <span>首页</span>
        </button>
        <div class="chat-session__title-group">
          <span class="chat-session__title">
            {{ activeConversation?.session?.title || '智能问答' }}
          </span>
          <span v-if="selectedKnowledgeBase" class="chat-session__kb-tag">
            <n-icon :component="LibraryOutline" size="11" />
            {{ selectedKnowledgeBase.name }}
          </span>
          <span v-if="activeModelLabel" class="chat-session__model-tag">
            {{ activeModelLabel }}
          </span>
          <span v-if="activeConversation?.session?.id" class="chat-session__id-tag">
            # {{ activeConversation.session.id }}
          </span>
        </div>
        <div class="chat-session__header-actions">
          <n-button
            v-if="conversationTurns.length > 0"
            quaternary
            size="small"
            @click="handleStartFreshChat"
          >
            <template #icon><n-icon :component="ChatbubbleEllipsesOutline" /></template>
            新对话
          </n-button>
        </div>
      </div>

      <!-- 消息滚动区（相对定位容器，用于悬浮按钮） -->
      <div class="chat-session__body-wrap">
      <div ref="conversationScrollerRef" class="chat-session__body" @scroll="handleBodyScroll">
        <n-spin :show="conversationLoading">
          <div v-if="!conversationTurns.length" class="chat-empty-state">
            <div class="chat-empty-state__icon">
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="6" r="2" fill="currentColor" opacity="0.4"/>
                <circle cx="5" cy="17" r="2" fill="currentColor" opacity="0.25"/>
                <circle cx="19" cy="17" r="2" fill="currentColor" opacity="0.25"/>
                <line x1="12" y1="8" x2="5.8" y2="15.2" stroke="currentColor" stroke-width="1.5" opacity="0.3"/>
                <line x1="12" y1="8" x2="18.2" y2="15.2" stroke="currentColor" stroke-width="1.5" opacity="0.3"/>
              </svg>
            </div>
            <p>在下方输入问题，开始对话</p>
          </div>

          <MessageList
            v-else
            :turns="conversationTurns"
            :render-markdown="renderMarkdown"
            :get-mode-label="getModeLabel"
            :get-source-title="getSourceTitle"
          >
            <template #ai-avatar>
              <img class="msg-ai-avatar-img" src="/logo.png" alt="知源" />
            </template>
            <template #source-icon>
              <n-icon :component="DocumentTextOutline" size="12" />
            </template>
            <template #error-actions="{ turn }">
              <n-button size="small" secondary @click="draftQuestion = turn.question; handleSendQuestion()">
                重试
              </n-button>
              <n-button size="small" quaternary @click="selectedAskMode = 'llm_only'">
                切到仅模型回答
              </n-button>
            </template>
          </MessageList>
        </n-spin>
      </div>
      <!-- 滚动到底部悬浮按钮 -->
      <transition name="scroll-btn-fade">
        <button
          v-if="showScrollToBottom"
          class="scroll-to-bottom-btn"
          type="button"
          title="滚动到底部"
          @click="scrollConversationToBottom('smooth', true)"
        >
          <n-icon :component="ChevronDownOutline" size="16" />
        </button>
      </transition>
      </div>

      <!-- 底部输入区 -->
      <div class="chat-session__composer">
        <div class="session-composer">
          <n-input
            v-model:value="draftQuestion"
            type="textarea"
            placeholder="继续提问...（Enter 发送，Shift+Enter 换行）"
            :autosize="{ minRows: 2, maxRows: 5 }"
            class="session-composer__input"
            @keydown="handleComposerKeydown"
          />
          <div class="session-composer__bar">
            <!-- Auto 滑块式开关（紧凑版） -->
            <div
              class="mode-auto-switch mode-auto-switch--sm"
              :class="{ 'mode-auto-switch--on': useAutoMode }"
              role="group"
              aria-label="Auto 智能路由"
            >
              <div class="mode-auto-switch__text">
                <div class="mode-auto-switch__title">Auto</div>
                <div class="mode-auto-switch__desc">{{ useAutoMode ? '智能路由' : '手动' }}</div>
              </div>
              <n-switch v-model:value="useAutoMode" size="small" />
            </div>

            <!-- Manual mode selector (includes 模型直答 as last option) -->
            <n-select
              v-if="!useAutoMode"
              v-model:value="selectedAskMode"
              :options="effectiveQueryModeOptions"
              style="width: 156px; flex-shrink: 0"
              size="small"
              placeholder="选择检索方式"
            />

            <n-select
              v-if="configuredLlmProviders.length > 1"
              v-model:value="selectedLlmProvider"
              :options="llmProviderOptions"
              style="width: 130px; flex-shrink: 0"
              size="small"
              placeholder="服务商"
            />

            <n-select
              v-if="llmModelOptions.length > 0"
              v-model:value="selectedLlmModel"
              :options="llmModelOptions"
              style="width: 170px; flex-shrink: 0"
              size="small"
              placeholder="模型"
            />

            <button class="session-composer__attach" @click="handleUploadAttachment" title="上传附件">
              <n-icon :component="AttachOutline" size="15" />
            </button>
            <n-button
              :type="submitting ? 'default' : 'primary'"
              :disabled="!submitting && !draftQuestion.trim()"
              round
              size="medium"
              @click="submitting ? handleStopGeneration() : handleSendQuestion()"
            >
              <template #icon>
                <n-icon :component="submitting ? StopCircleOutline : SendOutline" />
              </template>
              {{ submitting ? '停止' : '发送' }}
            </n-button>
          </div>
        </div>
      </div>
      </section>
    </div>

    <!-- 隐藏的文件输入 -->
    <input ref="fileInputRef" type="file" class="visually-hidden" accept=".txt,.md,.json,.csv,.pdf,.docx,.xlsx,.xls,.html,.htm" @change="handleFileSelected" />

    <!-- 会话删除确认弹窗 -->
    <n-modal
      v-model:show="showDeleteSessionConfirm"
      preset="dialog"
      type="error"
      title="删除会话"
      positive-text="确认删除"
      negative-text="取消"
      @positive-click="handleDeleteSession"
      @negative-click="showDeleteSessionConfirm = false"
    >
      <template #default>
        <p>确定要删除此会话吗？会话记录将被永久清除，无法恢复。</p>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NAlert,
  NButton,
  NIcon,
  NInput,
  NModal,
  NSelect,
  NSwitch,
  NSpin,
  useMessage
} from 'naive-ui'
import {
  AttachOutline,
  BarChartOutline,
  ChatbubbleEllipsesOutline,
  ChevronDownOutline,
  DocumentTextOutline,
  HomeOutline,
  LibraryOutline,
  SendOutline,
  StopCircleOutline,
  TimeOutline,
  TrashOutline
} from '@vicons/ionicons5'
import {
  executeQueryStream,
  deleteConversationSession,
  getConversationSessionDetail,
  getKnowledgeBaseStats,
  listConversationSessions,
  queryModeOptions,
  uploadDocument
} from '@/api/zhiyuan'
import {
  formatDateTime,
  statusLabelFromKnowledgeBase,
  statusToneFromKnowledgeBase
} from '@/utils/formatters'
import { useMarkdownRenderer } from '@/composables/useMarkdownRenderer'
import { useChatAutoScroll } from '@/composables/useChatAutoScroll'
import MessageList from '@/components/chat/MessageList.vue'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBase'
import { useProviderStore } from '@/stores/provider'

const { renderMarkdown } = useMarkdownRenderer()

const looksLikeRefusalOrEmpty = (answerText) => {
  const t = String(answerText || '').trim().toLowerCase()
  if (!t) return true
  return (
    t === "sorry, i'm not able to provide an answer to that question." ||
    t.includes("i'm not able to provide an answer") ||
    t.includes("cannot provide an answer") ||
    t.includes("i can't help with") ||
    t.includes("unable to help")
  )
}

const getModeLabel = (mode) => {
  const map = {
    local: '图谱局部检索',
    global: '图谱全局分析',
    naive: '文档检索',
    bm25: '关键词检索',
    llm_only: '模型直答',
    auto: 'Auto（智能路由）',
    global_local: '图谱混合检索'
  }
  return map[mode] || mode || 'Auto'
}

const route = useRoute()
const router = useRouter()
const message = useMessage()
const kbStore = useKnowledgeBaseStore()
const providerStore = useProviderStore()

const knowledgeBaseList = computed(() => kbStore.list)
const recentSessions = ref([])
const sessionSearchKeyword = ref('')
const sidebarCollapsed = ref(false)
const selectedKnowledgeBaseId = ref('')
const selectedAskMode = ref('naive')
const selectedKnowledgeBaseStats = ref(null)
const activeConversation = ref(null)
const draftQuestion = ref('')
const chatScene = ref('home')
const fileInputRef = ref(null)
const conversationScrollerRef = ref(null)
const activeStreamController = ref(null)
const activeStreamTurnId = ref(null)
const { shouldAutoScroll, handleConversationScroll, scrollConversationToBottom } = useChatAutoScroll(conversationScrollerRef)
const useAutoMode = ref(true)
const mobileSidebarOpen = ref(false)
const selectedLlmProvider = ref('')
const selectedLlmModel = ref('')

// 从 store 派生，无需硬编码
const configuredLlmProviders = computed(() => providerStore.llmProviders)
const providersRegistry = computed(() => providerStore.registry)

// 会话删除确认
const showDeleteSessionConfirm = ref(false)
const pendingDeleteSessionId = ref(null)

const llmProviderOptions = computed(() => {
  const options = providerStore.llmProviders
    .map((p) => ({ label: providerStore.registry[p]?.label || p, value: p }))
  if (!options.length) return []
  return [{ label: '默认', value: '' }, ...options]
})

const llmModelOptions = computed(() => {
  const provider = selectedLlmProvider.value
  if (!provider) return []
  const info = providersRegistry.value?.[provider]
  const models = info?.default_models || []
  return models.map((m) => ({ label: m, value: m }))
})

watch(selectedLlmProvider, (provider) => {
  if (!provider) {
    selectedLlmModel.value = ''
    return
  }
  const models = providersRegistry.value?.[provider]?.default_models || []
  selectedLlmModel.value = models[0] || ''
})

const kbLoading = computed(() => kbStore.loading)
const sessionLoading = ref(false)
const statsLoading = ref(false)
const conversationLoading = ref(false)
const submitting = ref(false)
const showScrollToBottom = ref(false)

const knowledgeBaseOptions = computed(() =>
  kbStore.list.map((kbItem) => ({
    label: kbItem.name,
    value: String(kbItem.id)
  }))
)

const selectedKnowledgeBase = computed(() => {
  if (!selectedKnowledgeBaseId.value) return null
  return kbStore.list.find((kbItem) => String(kbItem.id) === String(selectedKnowledgeBaseId.value)) || null
})

// Manual RAG modes available based on KB capabilities, plus llm_only as the last option.
const effectiveQueryModeOptions = computed(() => {
  const kb = selectedKnowledgeBase.value
  const enabledLocal = Boolean(kb?.enable_local)
  const enabledNaive = kb ? Boolean(kb.enable_naive_rag) : true
  const enabledBm25 = Boolean(kb?.enable_bm25)

  const modes = queryModeOptions.filter((opt) => {
    if (opt.value === 'naive') return enabledNaive
    if (opt.value === 'bm25') return enabledBm25
    if (opt.value === 'local' || opt.value === 'global' || opt.value === 'global_local') return enabledLocal
    return true
  })
  modes.push({ label: '模型直答', value: 'llm_only' })
  return modes
})

// The actual mode to send to backend: auto when toggle is on, else the selected manual mode.
const effectiveSendMode = computed(() => {
  if (useAutoMode.value) return 'auto'
  return selectedAskMode.value
})

const filteredSessions = computed(() => {
  const keyword = sessionSearchKeyword.value.trim().toLowerCase()
  if (!keyword) return recentSessions.value
  return recentSessions.value.filter((s) => String(s.title || '').toLowerCase().includes(keyword) || String(s.id).includes(keyword))
})

const conversationTurns = computed(() => activeConversation.value?.turns || [])
const graphSourceLabel = computed(() => {
  const source = selectedKnowledgeBaseStats.value?.graph_source
  if (source === 'neo4j') return 'Neo4j 实时图谱'
  if (source === 'graphml') return '本地缓存图谱'
  if (source === 'memory') return '内存图谱'
  if (source === 'none') return '暂无图谱数据'
  return '--'
})

const activeModelLabel = computed(() => {
  // 会话级身份感：展示当前请求实际使用的 best model（来自后端 metadata.configured_models）
  const configured = selectedKnowledgeBaseStats.value?.configured_models
  const best = configured?.best || null
  if (!best) return ''
  return `模型：${best}`
})

const createLocalSessionShell = (questionText) => {
  const timestamp = new Date().toISOString()
  return {
    session: {
      id: null,
      title: questionText.slice(0, 80) || 'New conversation',
      knowledge_base_id: Number(selectedKnowledgeBaseId.value),
      created_at: timestamp,
      updated_at: timestamp,
      last_active_at: timestamp,
      turn_count: 0
    },
    turns: []
  }
}

const ensureLocalConversationShell = (questionText) => {
  if (!activeConversation.value?.session) {
    activeConversation.value = createLocalSessionShell(questionText)
  }
  if (!Array.isArray(activeConversation.value.turns)) {
    activeConversation.value.turns = []
  }
  chatScene.value = 'session'
}

const updateLocalStreamingTurn = (turnId, updater) => {
  const turns = activeConversation.value?.turns
  if (!turns?.length) return

  // Fast path: streaming turn is usually the last one.
  const lastIndex = turns.length - 1
  if (turns[lastIndex]?.id === turnId) {
    const current = turns[lastIndex]
    const nextTurn = typeof updater === 'function' ? updater(current) : updater
    turns[lastIndex] = { ...current, ...nextTurn }
    return
  }

  const idx = turns.findIndex((t) => t.id === turnId)
  if (idx === -1) return
  const current = turns[idx]
  const nextTurn = typeof updater === 'function' ? updater(current) : updater
  turns[idx] = { ...current, ...nextTurn }
}

let scrollRafId = 0
const scrollConversationToBottomThrottled = () => {
  if (scrollRafId) return
  scrollRafId = window.requestAnimationFrame(() => {
    scrollRafId = 0
    void scrollConversationToBottom()
  })
}

const handleBodyScroll = (event) => {
  handleConversationScroll(event)
  const el = conversationScrollerRef.value
  if (!el) return
  const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
  showScrollToBottom.value = distFromBottom > 120
}

const abortActiveStream = () => {
  if (activeStreamController.value) {
    activeStreamController.value.abort()
    activeStreamController.value = null
  }
  activeStreamTurnId.value = null
}

const initializeFromRoute = async () => {
  if (typeof route.query.kb === 'string' && route.query.kb) {
    selectedKnowledgeBaseId.value = route.query.kb
  }
  if (typeof route.query.q === 'string' && route.query.q.trim()) {
    draftQuestion.value = route.query.q.trim()
  }
  if (typeof route.query.session === 'string' && route.query.session) {
    chatScene.value = 'session'
    await loadConversationSession(route.query.session)
  } else {
    chatScene.value = 'home'
    activeConversation.value = null
  }
}

const loadKnowledgeBases = async () => {
  await kbStore.fetchList()
  if (!selectedKnowledgeBaseId.value && kbStore.list.length) {
    selectedKnowledgeBaseId.value = String(kbStore.list[0].id)
  }
}

const loadRecentSessions = async () => {
  sessionLoading.value = true
  try {
    recentSessions.value = await listConversationSessions({ limit: 80 })
  } finally {
    sessionLoading.value = false
  }
}

const recentSessionsPreview = computed(() => recentSessions.value.slice(0, 4))
const knowledgeBasePreview = computed(() => kbStore.list.slice(0, 5))

function confirmDeleteSession(sessionId) {
  pendingDeleteSessionId.value = sessionId
  showDeleteSessionConfirm.value = true
}

const handleDeleteSession = async () => {
  const sessionId = pendingDeleteSessionId.value
  if (!sessionId) return
  try {
    await deleteConversationSession(sessionId)
    showDeleteSessionConfirm.value = false
    message.success('会话已删除')
    await loadRecentSessions()
    if (String(activeConversation.value?.session?.id) === String(sessionId)) {
      await handleStartFreshChat()
    }
  } catch (error) {
    message.error(error.response?.data?.detail || '删除会话失败')
  } finally {
    pendingDeleteSessionId.value = null
  }
}

const loadSelectedKnowledgeBaseStats = async () => {
  if (!selectedKnowledgeBaseId.value) { selectedKnowledgeBaseStats.value = null; return }
  statsLoading.value = true
  try {
    selectedKnowledgeBaseStats.value = await getKnowledgeBaseStats(selectedKnowledgeBaseId.value)
  } catch {
    selectedKnowledgeBaseStats.value = null
  } finally {
    statsLoading.value = false
  }
}

const loadConversationSession = async (sessionId) => {
  if (!sessionId) return
  conversationLoading.value = true
  try {
    activeConversation.value = await getConversationSessionDetail(sessionId)
    if (activeConversation.value?.session?.knowledge_base_id) {
      selectedKnowledgeBaseId.value = String(activeConversation.value.session.knowledge_base_id)
    }
    shouldAutoScroll.value = true
    await scrollConversationToBottom('auto', true)
  } finally {
    conversationLoading.value = false
  }
}

const handleStartFreshChat = async () => {
  abortActiveStream()
  draftQuestion.value = ''
  activeConversation.value = null
  chatScene.value = 'home'
  await router.replace({
    path: '/chat',
    query: selectedKnowledgeBaseId.value ? { kb: selectedKnowledgeBaseId.value } : {}
  })
}

const ensureReadyForQuery = () => {
  if (effectiveSendMode.value === 'llm_only') return true
  if (!selectedKnowledgeBaseId.value) { message.warning('请先选择知识库'); return false }
  if (!selectedKnowledgeBaseStats.value?.initialized) {
    message.warning('当前知识库尚未初始化，请先上传文档完成处理，或切换为「模型直答」模式')
    return false
  }
  return true
}

const handleComposerKeydown = (event) => {
  if (event.key !== 'Enter' || event.shiftKey) return
  event.preventDefault()
  if (submitting.value) return
  void handleSendQuestion()
}

const handleStopGeneration = () => {
  if (!activeStreamController.value) return
  abortActiveStream()
  message.info('已停止生成')
}

const handleSendQuestion = async () => {
  const questionText = draftQuestion.value.trim()
  if (!questionText) { message.warning('请输入问题后再提交'); return }
  if (!ensureReadyForQuery()) return

  submitting.value = true
  const streamController = new AbortController()
  activeStreamController.value = streamController
  const streamingTurnId = `stream-${Date.now()}`
  activeStreamTurnId.value = streamingTurnId
  try {
    ensureLocalConversationShell(questionText)
    const nextTurnIndex = (activeConversation.value?.turns?.length || 0) + 1
    activeConversation.value.turns = [
      ...(activeConversation.value?.turns || []),
      {
        id: streamingTurnId,
        turn_index: nextTurnIndex,
        question: questionText,
        answer: '',
        requested_mode: effectiveSendMode.value,
        mode: effectiveSendMode.value,
        response_time: null,
        token_count: null,
        sources: [],
        retrieval_summary: null,
        created_at: new Date().toISOString(),
        streaming: true
      }
    ]
    draftQuestion.value = ''
    shouldAutoScroll.value = true
    await scrollConversationToBottom('smooth', true)
    const finalPayload = await executeQueryStream(
      {
        question: questionText,
        knowledge_base_id: Number(selectedKnowledgeBaseId.value),
        session_id: activeConversation.value?.session?.id || undefined,
        mode: effectiveSendMode.value,
        top_k: 20,
        use_memory: true,
        memory_turn_window: 4,
        llm_provider: selectedLlmProvider.value || undefined,
        llm_model: selectedLlmModel.value || undefined
      },
      {
        signal: streamController.signal,
        onMessage: (event) => {
          // If user clicked stop, never append any more chunks to this turn.
          if (streamController.signal.aborted) return
          if (activeStreamTurnId.value !== streamingTurnId) return
          if (!event.content) return
          updateLocalStreamingTurn(streamingTurnId, (turnItem) => ({
            ...turnItem,
            answer: `${turnItem.answer || ''}${event.content}`
          }))
          scrollConversationToBottomThrottled()
        }
      }
    )

    // If user stopped generation, do not let a late `done` overwrite the partial content.
    if (streamController.signal.aborted || activeStreamTurnId.value !== streamingTurnId) {
      updateLocalStreamingTurn(streamingTurnId, (t) => ({ ...t, answer: t.answer || '已停止生成', streaming: false }))
      return
    }

    if (finalPayload?.error) throw new Error(finalPayload.error)

    updateLocalStreamingTurn(streamingTurnId, (turnItem) => ({
      ...turnItem,
      answer: finalPayload?.answer || turnItem.answer,
      mode: finalPayload?.mode || turnItem.mode,
      token_count: finalPayload?.tokens || turnItem.token_count,
      sources: finalPayload?.sources || turnItem.sources,
      memory: finalPayload?.metadata?.memory || turnItem.memory,
      retrieval_summary: finalPayload?.metadata?.retrieval || turnItem.retrieval_summary,
      streaming: false
    }))
    // 产品化失败态：英文拒答/空答 => 结构化中文提示 + 可重试
    updateLocalStreamingTurn(streamingTurnId, (turnItem) => {
      const raw = finalPayload?.answer || turnItem.answer
      if (!looksLikeRefusalOrEmpty(raw)) return turnItem
      return {
        ...turnItem,
        answer: [
          "未能生成有效回答。",
          "",
          "可能原因：",
          "- 当前知识库未命中相关内容",
          "- 检索模式不合适（可尝试切换为「仅模型回答」或「朴素检索」）",
          "- 模型拒答或临时异常",
          "",
          "你可以：点击下方「重试」或换个问法再试一次。"
        ].join('\n'),
        is_error: true,
      }
    })
    if (finalPayload?.session_id) {
      await loadConversationSession(finalPayload.session_id)
      await loadRecentSessions()
      await router.replace({
        path: '/chat',
        query: { session: String(finalPayload.session_id), kb: selectedKnowledgeBaseId.value }
      })
    }
  } catch (error) {
    if (streamController.signal.aborted) {
      updateLocalStreamingTurn(streamingTurnId, (t) => ({ ...t, answer: t.answer || '已停止生成', streaming: false }))
      return
    }
    updateLocalStreamingTurn(streamingTurnId, (t) => ({ ...t, streaming: false }))
    if (!error.response?.data?.detail && error.message) {
      message.error(error.message)
      return
    }
    message.error(error.response?.data?.detail || '问答请求失败')
  } finally {
    if (activeStreamController.value === streamController) activeStreamController.value = null
    if (activeStreamTurnId.value === streamingTurnId) activeStreamTurnId.value = null
    submitting.value = false
  }
}

const openRecentSession = async (sessionItem) => {
  mobileSidebarOpen.value = false
  await router.replace({
    path: '/chat',
    query: { session: String(sessionItem.id), kb: String(sessionItem.knowledge_base_id) }
  })
}

const handleUploadAttachment = () => {
  if (!selectedKnowledgeBaseId.value) { message.warning('请先选择知识库后再上传文档'); return }
  fileInputRef.value?.click()
}

const handleFileSelected = async (event) => {
  const file = event.target.files?.[0]
  if (!file) return
  try {
    await uploadDocument(selectedKnowledgeBaseId.value, file)
    message.success('文档已提交，系统将按后台状态进行处理')
    await Promise.all([loadKnowledgeBases(), loadSelectedKnowledgeBaseStats()])
  } catch (error) {
    message.error(error.response?.data?.detail || '文档上传失败')
  } finally {
    event.target.value = ''
  }
}

const getSourceTitle = (sourceItem, index) => {
  const normalize = (s) => {
    const v = String(s || '').trim()
    if (!v) return ''
    const map = {
      naive: 'vector',
      vector: 'vector',
      bm25: 'bm25',
      keyword: 'bm25',
      local: 'local',
      global: 'global',
      global_local: 'global_local',
      graph_local: 'local',
      graph_global: 'global',
      graph_hybrid: 'global_local',
      llm_only: 'llm_only'
    }
    return map[v] || v
  }

  // fused evidence may carry `sources` array (which retriever modes contributed),
  // while `source` is only the "primary" source of the fused chunk.
  if (Array.isArray(sourceItem?.sources) && sourceItem.sources.length) {
    const unique = [...new Set(sourceItem.sources.map(normalize).filter(Boolean))]
    if (unique.length) return unique.join('+')
  }

  return sourceItem?.title || sourceItem?.name || sourceItem?.source || sourceItem?.id || `来源 ${index + 1}`
}

watch(() => route.fullPath, async () => { await initializeFromRoute() }, { immediate: true })
watch(selectedKnowledgeBaseId, async () => { await loadSelectedKnowledgeBaseStats() })
watch(
  () => effectiveQueryModeOptions.value.map((o) => o.value).join(','),
  () => {
    if (!effectiveQueryModeOptions.value.length) return
    const allowed = new Set(effectiveQueryModeOptions.value.map((o) => o.value))
    if (!allowed.has(selectedAskMode.value)) {
      selectedAskMode.value = effectiveQueryModeOptions.value[0]?.value || 'naive'
    }
  },
  { immediate: true }
)
watch(
  () => conversationTurns.value.length,
  async () => { if (chatScene.value === 'session') await scrollConversationToBottom('smooth') }
)

const loadConfiguredProviders = async () => {
  try {
    await providerStore.fetchProviders()
    if (providerStore.llmProviders.length && !selectedLlmProvider.value) {
      selectedLlmProvider.value = providerStore.llmProviders[0] || ''
    }
    if (selectedLlmProvider.value) {
      const models = providerStore.registry?.[selectedLlmProvider.value]?.default_models || []
      selectedLlmModel.value = models[0] || ''
    }
  } catch {
    selectedLlmModel.value = ''
  }
}

onMounted(async () => {
  await Promise.all([loadKnowledgeBases(), loadRecentSessions(), loadConfiguredProviders()])
  await loadSelectedKnowledgeBaseStats()
})

onBeforeUnmount(() => { abortActiveStream() })
</script>

<style scoped>
/* ══════════════════════════════════════════
   BASE
══════════════════════════════════════════ */
.chat-page {
  display: flex;
  flex-direction: column;
}

.chat-page--session {
  height: calc(100svh - 52px);
  min-height: 0;
}

/* ══════════════════════════════════════════
   SESSION LAYOUT (left sidebar)
══════════════════════════════════════════ */
.chat-session-layout {
  display: grid;
  grid-template-columns: 292px minmax(0, 1fr);
  gap: 8px;
  height: calc(100svh - 52px);
  min-height: 0;
  padding: 0;
}

.chat-session-layout--collapsed {
  grid-template-columns: 56px minmax(0, 1fr);
}

.chat-session-sidebar {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--surface-card);
  border: 1.5px solid var(--border-color);
  border-radius: 16px;
  box-shadow: var(--shadow-card);
  overflow: hidden;
}

/* 主对话区：把视觉中心放在消息流与输入 */
.chat-session {
  background: transparent;
}

.chat-session__header {
  border: none;
  background: transparent;
  padding: 14px 14px 8px;
}

.chat-session__body {
  border: none;
  background: transparent;
  padding: 6px 14px 14px;
}

.chat-session__composer {
  border: none;
  background: transparent;
  padding: 0 14px 14px;
}

:deep(.msg-ai-bubble) {
  line-height: 1.65;
}

:deep(.msg-ai-streaming) {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font: inherit;
  color: var(--text-2);
}

:deep(.msg-error-actions) {
  margin-top: 10px;
  display: flex;
  gap: 10px;
}

.chat-session-sidebar__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 12px 8px;
}

.chat-session-sidebar__top-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.chat-session-sidebar__toggle {
  border: 1px solid var(--border-color);
  background: transparent;
  color: var(--text-4);
  border-radius: 999px;
  padding: 6px 10px;
  font-size: 12px;
  cursor: pointer;
}

.chat-session-sidebar__toggle:hover {
  border-color: var(--brand-200);
  color: var(--text-2);
}

.chat-session-sidebar__title {
  font-size: 13px;
  font-weight: 800;
  color: var(--text-2);
}

.chat-session-sidebar__new {
  border: 1px solid var(--border-color);
  background: var(--surface-2);
  color: var(--text-2);
  border-radius: 999px;
  padding: 6px 10px;
  font-size: 12px;
  cursor: pointer;
}

.chat-session-sidebar__new:hover {
  border-color: var(--brand-300);
}

.chat-session-sidebar__search {
  padding: 0 12px 10px;
}

.chat-session-sidebar__spin {
  min-height: 0;
  flex: 1;
}

.chat-session-sidebar__list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 0 10px 10px;
  overflow: auto;
  max-height: 100%;
}

.chat-session-sidebar__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  text-align: left;
  padding: 10px 10px;
  border-radius: 12px;
  border: 1px solid transparent;
  background: transparent;
  cursor: pointer;
}

.chat-session-sidebar__item:hover {
  background: var(--surface-2);
}

.chat-session-sidebar__item.is-active {
  background: rgba(59, 130, 246, 0.08);
  border-color: rgba(59, 130, 246, 0.28);
}

.chat-session-sidebar__item-main {
  min-width: 0;
  flex: 1;
}

.chat-session-sidebar__item-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chat-session-sidebar__item-meta {
  margin-top: 4px;
  display: flex;
  gap: 10px;
  font-size: 12px;
  color: var(--text-4);
}

.chat-session-sidebar__item-delete {
  flex-shrink: 0;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.12s ease;
}

.chat-session-sidebar__item:hover .chat-session-sidebar__item-delete,
.chat-session-sidebar__item.is-active:hover .chat-session-sidebar__item-delete {
  opacity: 0.9;
  pointer-events: auto;
}

.chat-session-sidebar__empty {
  padding: 16px 12px;
  font-size: 12px;
  color: var(--text-4);
}

.chat-session-layout--collapsed .chat-session-sidebar__top {
  padding: 10px 8px;
}

.chat-session-layout--collapsed .chat-session-sidebar__title {
  display: none;
}

.chat-session-layout--collapsed .chat-session-sidebar__top-actions {
  flex-direction: column;
  gap: 6px;
}

.chat-session-layout--collapsed .chat-session-sidebar__toggle,
.chat-session-layout--collapsed .chat-session-sidebar__new {
  width: 40px;
  padding: 6px 0;
  text-align: center;
}

.chat-session-layout--collapsed .chat-session-sidebar__item {
  padding: 10px 8px;
  justify-content: center;
}

.chat-session-layout--collapsed .chat-session-sidebar__item-main {
  display: flex;
  justify-content: center;
}

.chat-session-layout--collapsed .chat-session-sidebar__item-title {
  text-align: center;
  width: 100%;
}

.chat-session-layout--collapsed .chat-session-sidebar__item-delete {
  display: none;
}

/* ── 移动端侧栏遮罩 ─────────────────────── */
.chat-mobile-overlay {
  display: none;
}

.chat-session-sidebar__close-mobile {
  display: none;
}

.chat-mobile-sidebar-btn {
  display: none;
}

@media (max-width: 980px) {
  .chat-session-layout {
    grid-template-columns: 1fr;
  }

  /* 移动端侧栏默认隐藏，打开时以抽屉形式覆盖 */
  .chat-session-sidebar {
    position: fixed;
    left: -300px;
    top: 0;
    width: 280px;
    height: 100dvh;
    z-index: 200;
    border-radius: 0 16px 16px 0;
    transition: left 0.26s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 4px 0 24px rgba(0, 0, 0, 0.18);
  }

  .chat-session-sidebar--mobile-open {
    left: 0;
  }

  /* 移动端半透明遮罩 */
  .chat-mobile-overlay {
    display: block;
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.45);
    z-index: 199;
  }

  .chat-session-sidebar__close-mobile {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border: none;
    border-radius: 50%;
    background: var(--surface-muted);
    color: var(--text-3);
    font-size: 13px;
    cursor: pointer;
  }

  /* 移动端头部显示侧栏触发按钮 */
  .chat-mobile-sidebar-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 34px;
    height: 34px;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    background: var(--surface-muted);
    color: var(--text-3);
    cursor: pointer;
    flex-shrink: 0;
    margin-right: 2px;
  }

  .chat-mobile-sidebar-btn:hover {
    background: var(--surface-soft);
    color: var(--text-1);
  }

  /* 隐藏收起/展开按钮（移动端全屏侧栏）*/
  .chat-session-sidebar--mobile-open .chat-session-sidebar__toggle {
    display: none;
  }
}

/* 移动端侧栏遮罩过渡 */
.mobile-sidebar-fade-enter-active,
.mobile-sidebar-fade-leave-active {
  transition: opacity 0.24s ease;
}
.mobile-sidebar-fade-enter-from,
.mobile-sidebar-fade-leave-to {
  opacity: 0;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}

/* ══════════════════════════════════════════
   HOME SCENE
══════════════════════════════════════════ */
.chat-home {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 32px;
  padding: 8px 0 40px;
  width: 100%;
}

.chat-home__alert {
  width: 100%;
  max-width: 920px;
}

/* Hero */
.chat-home__hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding-top: 16px;
}

.chat-home__hero-logo {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  border-radius: 16px;
  background: linear-gradient(135deg, #60a5fa 0%, #93c5fd 100%);
  box-shadow: 0 8px 24px rgba(59, 130, 246, 0.35);
  margin-bottom: 4px;
}

.chat-home__hero-title {
  margin: 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--text-1);
  text-align: center;
  letter-spacing: -0.5px;
}

.chat-home__hero-title em {
  font-style: normal;
  background: linear-gradient(135deg, #2563eb, #7c3aed);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.chat-home__hero-desc {
  margin: 0;
  font-size: 15px;
  color: var(--text-4);
  text-align: center;
  max-width: 480px;
}

/* Composer */
.chat-home__composer-wrap {
  display: flex;
  flex-direction: column;
  gap: 14px;
  width: 100%;
  max-width: 920px;
}

.chat-session__model-tag {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  color: var(--brand-700);
  background: rgba(37, 99, 235, 0.10);
  border: 1px solid rgba(37, 99, 235, 0.18);
  margin-left: 10px;
}

.chat-home__composer {
  background: var(--surface-card);
  border: 1.5px solid var(--border-color);
  border-radius: 18px;
  padding: 16px 16px 12px;
  box-shadow: var(--shadow-card);
  transition: border-color 0.2s, box-shadow 0.2s;
}

.chat-home__composer:focus-within {
  border-color: var(--brand-400);
  box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.08), var(--shadow-card);
}

.chat-home__textarea {
  --n-border: none !important;
  --n-border-hover: none !important;
  --n-border-focus: none !important;
  --n-box-shadow-focus: none !important;
  --n-color: transparent !important;
}

:deep(.chat-home__textarea .n-input__border),
:deep(.chat-home__textarea .n-input__state-border) {
  display: none !important;
}

:deep(.chat-home__textarea .n-input-wrapper) {
  padding: 0;
}

:deep(.chat-home__textarea .n-input__textarea-el) {
  font-size: 15px;
  line-height: 1.7;
  resize: none;
  color: var(--text-1);
}

.chat-home__composer-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--border-color);
}

.chat-home__composer-selectors {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

/* ── Auto 滑块式开关（信息块） ─────────────────────── */
.mode-auto-switch {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  height: 32px;
  padding: 8px 10px;
  border-radius: 10px;
  background: var(--surface-muted);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  flex-shrink: 0;
}

.mode-auto-switch--on {
  background: color-mix(in srgb, var(--brand-500) 10%, var(--surface-muted));
}

.mode-auto-switch__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  line-height: 1.1;
  min-width: 0;
}

.mode-auto-switch__title {
  font-size: 12.5px;
  font-weight: 650;
  color: var(--text-1);
}

.mode-auto-switch__desc {
  font-size: 11px;
  color: var(--text-5);
  white-space: nowrap;
}

.mode-auto-switch--sm {
  height: 30px;
  padding: 7px 10px;
  border-radius: 10px;
  gap: 10px;
}

.mode-auto-switch--sm .mode-auto-switch__title {
  font-size: 12px;
}

.mode-auto-switch--sm .mode-auto-switch__desc {
  font-size: 10.5px;
}

/* ── Home composer attach button ─────────────────────── */
.chat-home__attach-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 8px;
  background: var(--surface-muted);
  color: var(--text-4);
  cursor: pointer;
  transition: background 0.16s, color 0.16s;
  flex-shrink: 0;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}
.chat-home__attach-btn:hover {
  background: color-mix(in srgb, var(--brand-400) 10%, var(--surface-muted));
  color: var(--text-2);
}

/* Suggestions */
.chat-home__suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}

.suggestion-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border: 1px solid var(--border-color);
  border-radius: 999px;
  background: var(--surface-card);
  color: var(--text-3);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.18s ease;
}

.suggestion-chip:hover {
  border-color: var(--brand-400);
  color: var(--brand-600);
  background: var(--brand-50);
  transform: translateY(-1px);
}

/* Panels */
.chat-home__panels {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  width: 100%;
  max-width: 920px;
  align-items: stretch;
}

@media (max-width: 720px) {
  .chat-home__panels {
    grid-template-columns: 1fr;
  }

  .home-panel {
    height: auto;
    min-height: 200px;
    max-height: 280px;
  }

  .chat-home__composer-wrap {
    padding: 0 4px;
  }

  .chat-home__hero-title {
    font-size: 24px;
  }
}

@media (min-width: 721px) and (max-width: 960px) {
  .chat-home__panels {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .home-panel {
    height: auto;
    min-height: 280px;
  }
}

.home-panel {
  display: flex;
  flex-direction: column;
  background: var(--surface-card);
  border: 1px solid var(--border-color);
  border-radius: 14px;
  padding: 16px;
  box-shadow: var(--shadow-soft);
  height: 332px;
}

.home-panel__header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 12px;
}

.home-panel__header--with-actions {
  justify-content: space-between;
}

.home-panel__header-left {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.home-panel__body {
  flex: 1;
  min-height: 0;
}

.home-panel__footer {
  margin-top: 10px;
  display: flex;
  justify-content: flex-end;
}

.panel-link {
  border: none;
  background: transparent;
  color: var(--brand-600);
  font-size: 12.5px;
  font-weight: 700;
  cursor: pointer;
  padding: 4px 0;
}

.panel-link:hover {
  color: var(--brand-700);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.panel-link--muted {
  font-weight: 600;
  font-size: 12px;
  color: var(--text-4);
  text-transform: none;
  letter-spacing: 0;
}

.panel-link--muted:hover {
  color: var(--brand-700);
}

.panel-empty {
  font-size: 12px;
  color: var(--text-5);
  margin: 0;
  line-height: 1.6;
}

/* Session list */
.session-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.session-item {
  width: 100%;
  padding: 9px 11px;
  border: 1px solid transparent;
  border-radius: 9px;
  background: transparent;
  text-align: left;
  cursor: pointer;
  transition: all 0.16s ease;
}

.session-item:hover {
  background: var(--surface-muted);
  border-color: var(--border-color);
}

.session-item__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.session-item__meta {
  display: flex;
  gap: 10px;
  margin-top: 3px;
  font-size: 11px;
  color: var(--text-5);
}

/* KB quick list */
.kb-quick-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.kb-quick-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  transition: all 0.16s ease;
}

.kb-quick-item:hover {
  background: var(--surface-muted);
}

.kb-quick-item.is-active {
  background: var(--surface-soft);
  border-color: var(--border-color);
}

.kb-quick-item__left {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.kb-quick-item__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.kb-quick-item__dot--success { background: #22c55e; }
.kb-quick-item__dot--warning { background: #f59e0b; }
.kb-quick-item__dot--default { background: #94a3b8; }

.kb-quick-item__name {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--text-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* KB stats grid */
.kb-stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px 12px;
}

.kb-stat-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.kb-stat-item__label {
  font-size: 11px;
  color: var(--text-5);
}

.kb-stat-item__value {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-1);
}

.text-success { color: #16a34a !important; }
.text-warning { color: #d97706 !important; }

/* ══════════════════════════════════════════
   SESSION SCENE
══════════════════════════════════════════ */
.chat-session {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  border: 1px solid var(--border-color);
  border-radius: 16px;
  background: var(--surface-card);
  overflow: hidden;
  box-shadow: var(--shadow-card);
}

/* Session header */
.chat-session__header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border-color);
  background: var(--surface-card);
  flex-shrink: 0;
}

.chat-back-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 12px;
  border: 1px solid var(--border-color);
  border-radius: 8px;
  background: transparent;
  color: var(--text-3);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.16s ease;
  flex-shrink: 0;
}

.chat-back-btn:hover {
  background: var(--surface-muted);
  color: var(--text-1);
  border-color: var(--border-strong);
}

.chat-session__title-group {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.chat-session__title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chat-session__id-tag {
  flex-shrink: 0;
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--surface-muted);
  color: var(--text-5);
  font-size: 11px;
}

.chat-session__kb-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 20px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-4);
  background: var(--surface-muted);
  border: 1px solid var(--border-color);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 140px;
  flex-shrink: 0;
}

.chat-session__header-actions {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

/* Session body wrapper（relative，用于悬浮按钮定位） */
.chat-session__body-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

/* Session body */
.chat-session__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 28px 28px 16px;
  scroll-behavior: smooth;
}

/* 滚动到底部悬浮按钮 */
.scroll-to-bottom-btn {
  position: absolute;
  bottom: 14px;
  right: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 1px solid var(--border-color);
  background: var(--surface-card);
  color: var(--text-3);
  cursor: pointer;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.12);
  transition: all 0.16s ease;
  z-index: 10;
}

.scroll-to-bottom-btn:hover {
  background: var(--brand-50);
  border-color: var(--brand-300);
  color: var(--brand-600);
  transform: translateY(1px);
}

.scroll-btn-fade-enter-active,
.scroll-btn-fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}
.scroll-btn-fade-enter-from,
.scroll-btn-fade-leave-to {
  opacity: 0;
  transform: translateY(6px);
}

/* Empty state */
.chat-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  height: 200px;
  color: var(--text-5);
}

.chat-empty-state__icon {
  opacity: 0.4;
}

.chat-empty-state p {
  font-size: 14px;
  margin: 0;
}

/* Messages */
:deep(.messages) {
  display: flex;
  flex-direction: column;
  gap: 28px;
}

:deep(.message-group) {
  display: flex;
  flex-direction: column;
  gap: 16px;
  animation: msg-in 280ms ease;
}

@keyframes msg-in {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

:deep(.message) {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

:deep(.message--user) {
  justify-content: flex-end;
}

/* Avatar */
:deep(.msg-avatar) {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 700;
}

:deep(.msg-avatar--user) {
  background: var(--gray-800);
  color: #fff;
  order: 2;
}

:deep(.msg-avatar--ai) {
  background: linear-gradient(135deg, #76c7ff 0%, #bde9ff 100%);
  color: #fff;
  box-shadow: 0 2px 8px rgba(96, 165, 250, 0.16);
}

:deep(.msg-ai-avatar-img) {
  width: 22px;
  height: 22px;
  object-fit: cover;
  border-radius: 10px;
  user-select: none;
  pointer-events: none;
}

/* User bubble */
:deep(.msg-user-bubble) {
  max-width: 70%;
  padding: 12px 16px;
  background: linear-gradient(135deg, #1e40af 0%, #1d4ed8 100%);
  color: #fff;
  border-radius: 16px 4px 16px 16px;
  font-size: 14.5px;
  line-height: 1.7;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
}

/* AI content */
:deep(.msg-ai-content) {
  flex: 1;
  min-width: 0;
  max-width: calc(100% - 44px);
}

:deep(.msg-ai-header) {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 5px;
  padding-left: 2px;
}

:deep(.msg-ai-sender) {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--brand-600);
  letter-spacing: 0.2px;
}

:deep(.msg-ai-time) {
  font-size: 11px;
  color: var(--text-5);
}

:deep(.msg-meta-row) {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 7px;
  opacity: 0.65;
}

:deep(.msg-mode-badge) {
  display: inline-flex;
  align-items: center;
  padding: 1px 7px;
  border-radius: 4px;
  background: var(--surface-muted);
  color: var(--text-4);
  font-size: 10.5px;
  font-weight: 500;
  border: 1px solid var(--border-color);
}

:deep(.msg-time-tag) {
  font-size: 10.5px;
  color: var(--text-5);
}

/* AI bubble */
:deep(.msg-ai-bubble) {
  padding: 16px 18px;
  background: var(--surface-card);
  border: 1px solid var(--border-color);
  border-radius: 4px 16px 16px 16px;
  box-shadow: var(--shadow-soft);
  position: relative;
}

/* 流式生成中的气泡轻微闪烁边框 */
:deep(.msg-ai-bubble--streaming) {
  border-color: rgba(59, 130, 246, 0.3);
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.06), var(--shadow-soft);
}

/* 复制按钮 */
:deep(.msg-copy-btn) {
  position: absolute;
  top: 10px;
  right: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--surface-card);
  color: var(--text-5);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.16s, color 0.16s, background 0.16s;
}

:deep(.msg-ai-bubble:hover .msg-copy-btn) {
  opacity: 1;
}

:deep(.msg-copy-btn:hover),
:deep(.msg-copy-btn--copied) {
  background: var(--brand-50);
  color: var(--brand-600);
  border-color: var(--brand-300);
  opacity: 1;
}

/* Markdown 样式 */
:deep(.markdown-body) {
  font-size: 14.5px;
  line-height: 1.8;
  color: var(--text-2);
}

:deep(.markdown-body p) {
  margin: 0 0 10px;
}

:deep(.markdown-body p:last-child) {
  margin-bottom: 0;
}

:deep(.markdown-body h1),
:deep(.markdown-body h2),
:deep(.markdown-body h3),
:deep(.markdown-body h4) {
  color: var(--text-1);
  font-weight: 700;
  margin: 16px 0 8px;
  line-height: 1.4;
}

:deep(.markdown-body h1) { font-size: 20px; }
:deep(.markdown-body h2) { font-size: 17px; }
:deep(.markdown-body h3) { font-size: 15px; }

:deep(.markdown-body code) {
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(59, 130, 246, 0.08);
  color: #1d4ed8;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
}

:deep(.markdown-body pre) {
  background: #0f172a;
  border-radius: 10px;
  padding: 14px 16px;
  overflow-x: auto;
  margin: 12px 0;
}

:deep(.markdown-body pre code) {
  background: transparent;
  color: #e2e8f0;
  padding: 0;
  font-size: 13px;
}

:deep(.markdown-body ul),
:deep(.markdown-body ol) {
  padding-left: 22px;
  margin: 8px 0;
}

:deep(.markdown-body li) {
  margin: 4px 0;
}

:deep(.markdown-body blockquote) {
  border-left: 3px solid var(--brand-400);
  padding: 4px 0 4px 14px;
  color: var(--text-3);
  margin: 10px 0;
  font-style: italic;
}

:deep(.markdown-body table) {
  width: 100%;
  border-collapse: collapse;
  font-size: 13.5px;
  margin: 10px 0;
}

:deep(.markdown-body th) {
  background: var(--surface-muted);
  padding: 8px 12px;
  font-weight: 600;
  text-align: left;
  border: 1px solid var(--border-color);
}

:deep(.markdown-body td) {
  padding: 7px 12px;
  border: 1px solid var(--border-color);
}

:deep(.markdown-body strong) {
  color: var(--text-1);
  font-weight: 600;
}

:deep(.markdown-body a) {
  color: var(--brand-600);
  text-decoration: underline;
  text-underline-offset: 2px;
}

/* Thinking indicator */
:deep(.thinking-indicator) {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 0;
}

:deep(.thinking-dot) {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text-5);
  animation: dot-pulse 1.4s infinite ease-in-out;
}


@keyframes dot-pulse {
  0%, 60%, 100% { transform: scale(0.7); opacity: 0.4; }
  30% { transform: scale(1); opacity: 1; }
}

:deep(.typing-caret) {
  display: inline-block;
  width: 2px;
  height: 0.95em;
  margin-left: 3px;
  background: var(--brand-500);
  vertical-align: -1px;
  border-radius: 1px;
  animation: caret-blink 800ms steps(1) infinite;
}

/* 光标与流式文本对齐 */
:deep(.msg-ai-streaming + .typing-caret),
:deep(.msg-ai-streaming ~ .typing-caret) {
  display: block;
  margin-top: 4px;
}

@keyframes caret-blink {
  0%, 49% { opacity: 1; }
  50%, 100% { opacity: 0; }
}

/* thinking 点改进：波浪效果 */
:deep(.thinking-dot):nth-child(1) { animation-delay: 0s; }
:deep(.thinking-dot):nth-child(2) { animation-delay: 0.16s; }
:deep(.thinking-dot):nth-child(3) { animation-delay: 0.32s; }

/* Sources */
:deep(.msg-sources) {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--border-color);
}

:deep(.msg-sources__toggle) {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 8px 3px 4px;
  border: 1px solid var(--border-color);
  border-radius: 6px;
  background: var(--surface-muted);
  color: var(--text-4);
  font-size: 11.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.14s ease;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  margin-bottom: 8px;
}

:deep(.msg-sources__toggle:hover) {
  background: var(--surface-soft);
  color: var(--text-2);
  border-color: var(--brand-300);
}

:deep(.msg-sources__chevron) {
  transition: transform 0.2s ease;
  flex-shrink: 0;
  margin-left: 2px;
}

:deep(.msg-sources__chevron--open) {
  transform: rotate(180deg);
}

:deep(.source-chips) {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 2px;
}


:deep(.source-chip) {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 6px;
  border: 1px solid rgba(147, 197, 253, 0.6);
  background: rgba(239, 246, 255, 0.8);
  color: var(--brand-700);
  font-size: 12px;
  cursor: default;
  white-space: nowrap;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  title-attr: attr(title);
}

/* ══════════════════════════════════════════
   SESSION COMPOSER
══════════════════════════════════════════ */
.chat-session__composer {
  flex-shrink: 0;
  padding: 12px 16px 16px;
  border-top: 1px solid var(--border-color);
  background: var(--surface-card);
}

.session-composer {
  border: 1.5px solid var(--border-color);
  border-radius: 14px;
  background: var(--surface-card);
  padding: 12px 12px 10px;
  transition: border-color 0.2s;
}

.session-composer:focus-within {
  border-color: var(--brand-400);
}

:deep(.session-composer__input .n-input__border),
:deep(.session-composer__input .n-input__state-border) {
  display: none !important;
}

:deep(.session-composer__input .n-input-wrapper) {
  padding: 0;
}

:deep(.session-composer__input .n-input__textarea-el) {
  font-size: 14px;
  resize: none;
}

.session-composer__bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border-color);
}

.session-composer__attach {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 8px;
  background: var(--surface-muted);
  color: var(--text-4);
  cursor: pointer;
  transition: background 0.16s, color 0.16s;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
}

.session-composer__attach:hover {
  background: color-mix(in srgb, var(--brand-400) 10%, var(--surface-muted));
  color: var(--text-2);
}

.session-composer__bar > .n-button {
  margin-left: auto;
}

/* ══════════════════════════════════════════
   RESPONSIVE
══════════════════════════════════════════ */
@media (max-width: 760px) {
  :deep(.msg-user-bubble) { max-width: 88%; }
  .chat-session__body { padding: 16px; }
  .chat-session__header { padding: 10px 12px; gap: 8px; }
  .chat-back-btn span { display: none; }
  :deep(.chat-session__kb-tag) { display: none; }
  :deep(.chat-session__id-tag) { display: none; }
}
</style>
