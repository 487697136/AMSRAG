<template>
  <div class="sessions-page page-shell">
    <PageHeader
      title="会话中心"
      description="统一查看真实会话记录，并基于已保存的上下文继续处理问题。"
      badge="会话记录"
    >
      <template #actions>
        <n-space>
          <n-button quaternary :loading="loading" @click="loadSessions">刷新列表</n-button>
          <n-button type="primary" @click="handleCreateConversation">新建会话</n-button>
        </n-space>
      </template>
    </PageHeader>

    <div class="sessions-overview-grid">
      <InfoCard label="会话总数" :value="sessionRecordList.length" caption="当前账户下的全部会话记录" tone="info" />
      <InfoCard label="累计轮次" :value="totalTurns" caption="所有会话累计保存的问答轮次" tone="muted" />
      <InfoCard label="知识库覆盖" :value="activeKnowledgeBaseCount" caption="参与会话的知识库数量" tone="muted" />
    </div>

    <FilterToolbar>
      <template #filters>
        <n-input
          v-model:value="searchKeyword"
          clearable
          placeholder="搜索会话标题"
          style="min-width: 280px; flex: 1"
        >
          <template #prefix>
            <n-icon :component="SearchOutline" />
          </template>
        </n-input>

        <n-select
          v-model:value="selectedKnowledgeBaseId"
          :options="knowledgeBaseFilterOptions"
          style="width: 220px"
        />
      </template>

      <template #summary>
        <div class="toolbar-summary">
          <span>筛选结果 {{ filteredSessionList.length }} 条</span>
        </div>
      </template>
    </FilterToolbar>

    <div class="sessions-layout">
      <SectionCard title="会话记录" description="按最近活跃时间分组，方便快速回到历史上下文。" size="compact">
        <n-spin :show="loading">
          <div
            v-for="sessionGroup in groupedSessionList"
            :key="sessionGroup.label"
            class="session-group"
          >
            <div class="session-group__title">{{ sessionGroup.label }}</div>

            <button
              v-for="sessionItem in sessionGroup.items"
              :key="sessionItem.id"
              type="button"
              class="session-item"
              :class="{ 'is-active': sessionItem.id === selectedSessionId }"
              @click="handleSelectSession(sessionItem.id)"
            >
              <div class="session-item__header">
                <div>
                  <div class="session-item__title">{{ sessionItem.title }}</div>
                  <div class="session-item__meta">
                    <span>{{ resolveKnowledgeBaseName(sessionItem.knowledge_base_id) }}</span>
                    <span>{{ formatDateTime(sessionItem.updated_at || sessionItem.last_active_at) }}</span>
                  </div>
                </div>
                <div class="session-item__actions">
                  <span class="status-badge status-badge--default">{{ sessionItem.turn_count }} 轮</span>
                  <n-button text type="error" @click.stop="confirmDeleteSession(sessionItem.id)">
                    <template #icon>
                      <n-icon :component="TrashOutline" />
                    </template>
                  </n-button>
                </div>
              </div>
            </button>
          </div>

          <n-empty
            v-if="!groupedSessionList.length"
            description="暂无会话记录"
            style="padding: 28px 0 8px"
          />
        </n-spin>
      </SectionCard>

      <div class="sessions-layout__workspace">
        <SectionCard
          v-if="selectedSessionRecord"
          :title="selectedSessionRecord.title"
          description="以下内容来自真实会话详情接口，可直接继续追问。"
        >
          <template #extra>
            <n-button type="primary" @click="handleContinueSession(selectedSessionRecord)">继续会话</n-button>
          </template>

          <div class="session-overview-grid">
            <InfoCard label="知识库" :value="resolveKnowledgeBaseName(selectedSessionRecord.knowledge_base_id)" tone="info" size="compact" />
            <InfoCard label="轮次" :value="selectedSessionRecord.turn_count" size="compact" />
            <InfoCard label="最后活跃" :value="formatDateTime(selectedSessionRecord.last_active_at)" size="compact" />
          </div>

          <n-spin :show="detailLoading">
            <div v-if="selectedSessionDetail" class="turn-preview-list">
              <div
                v-for="turnItem in selectedSessionDetail.turns"
                :key="turnItem.id"
                class="turn-preview-item"
              >
                <div class="turn-preview-item__question">
                  <span class="turn-preview-item__label">问题</span>
                  <div>{{ turnItem.question }}</div>
                </div>
                <div class="turn-preview-item__answer">
                  <span class="turn-preview-item__label">回答</span>
                  <div>{{ turnItem.answer || '暂无回答' }}</div>
                </div>
                <div class="turn-preview-item__meta">
                  <span>模式 {{ turnItem.mode || turnItem.requested_mode || '--' }}</span>
                  <span>时间 {{ formatDateTime(turnItem.created_at) }}</span>
                </div>
              </div>
            </div>
            <n-empty v-else description="请选择会话后查看详情" />
          </n-spin>
        </SectionCard>

        <SectionCard v-else title="会话详情" description="从左侧选择任意会话，即可查看完整上下文和最近轮次。" size="compact">
          <n-empty description="请选择会话后查看详情" style="padding: 28px 0" />
        </SectionCard>
      </div>
    </div>
    <!-- 删除确认弹窗 -->
    <n-modal
      v-model:show="showDeleteConfirm"
      preset="dialog"
      type="error"
      title="删除会话"
      positive-text="确认删除"
      negative-text="取消"
      @positive-click="handleDeleteSession"
      @negative-click="showDeleteConfirm = false"
    >
      <template #default>
        <p>确定要删除此会话吗？会话记录将被永久清除，无法恢复。</p>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'

import { useRouter } from 'vue-router'
import {
  NButton,
  NEmpty,
  NIcon,
  NInput,
  NModal,
  NSpace,
  NSelect,
  NSpin,
  useMessage
} from 'naive-ui'
import { SearchOutline, TrashOutline } from '@vicons/ionicons5'
import {
  deleteConversationSession,
  getConversationSessionDetail,
  listConversationSessions,
} from '@/api/zhiyuan'
import FilterToolbar from '@/components/common/FilterToolbar.vue'
import InfoCard from '@/components/common/InfoCard.vue'
import SectionCard from '@/components/common/SectionCard.vue'
import PageHeader from '@/components/layout/PageHeader.vue'
import { formatDateTime, formatRelativeGroup } from '@/utils/formatters'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBase'

const router = useRouter()
const message = useMessage()
const kbStore = useKnowledgeBaseStore()

const sessionRecordList = ref([])
const knowledgeBaseList = computed(() => kbStore.list)
const selectedSessionDetail = ref(null)
const searchKeyword = ref('')
const selectedKnowledgeBaseId = ref('all')
const selectedSessionId = ref('')
const loading = ref(false)
const showDeleteConfirm = ref(false)
const pendingDeleteSessionId = ref(null)
const detailLoading = ref(false)

const knowledgeBaseFilterOptions = computed(() => [
  { label: '全部知识库', value: 'all' },
  ...knowledgeBaseList.value.map((kbItem) => ({ label: kbItem.name, value: String(kbItem.id) }))
])

const filteredSessionList = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase()

  return sessionRecordList.value.filter((sessionItem) => {
    if (selectedKnowledgeBaseId.value !== 'all' && String(sessionItem.knowledge_base_id) !== selectedKnowledgeBaseId.value) {
      return false
    }
    if (!keyword) {
      return true
    }
    return String(sessionItem.title || '').toLowerCase().includes(keyword)
  })
})

const groupedSessionList = computed(() => {
  const groupOrder = ['今天', '近 7 天', '更早']
  return groupOrder
    .map((groupLabel) => ({
      label: groupLabel,
      items: filteredSessionList.value.filter((sessionItem) => formatRelativeGroup(sessionItem.last_active_at || sessionItem.updated_at) === groupLabel)
    }))
    .filter((groupItem) => groupItem.items.length > 0)
})

const selectedSessionRecord = computed(() => {
  return sessionRecordList.value.find((sessionItem) => String(sessionItem.id) === String(selectedSessionId.value)) || null
})

const totalTurns = computed(() => sessionRecordList.value.reduce((sum, item) => sum + Number(item.turn_count || 0), 0))
const activeKnowledgeBaseCount = computed(() => new Set(sessionRecordList.value.map((item) => item.knowledge_base_id).filter(Boolean)).size)

const resolveKnowledgeBaseName = (kbId) => {
  return kbStore.list.find((kbItem) => kbItem.id === kbId)?.name || `知识库 ${kbId}`
}

const loadSessions = async () => {
  loading.value = true
  try {
    const [sessions] = await Promise.all([
      listConversationSessions({ limit: 100 }),
      kbStore.fetchList()
    ])
    sessionRecordList.value = sessions
    if (!selectedSessionId.value && sessions.length) {
      selectedSessionId.value = String(sessions[0].id)
    }
  } catch (error) {
    message.error(error.response?.data?.detail || '加载会话失败')
  } finally {
    loading.value = false
  }
}

const loadSessionDetail = async (sessionId) => {
  if (!sessionId) {
    selectedSessionDetail.value = null
    return
  }
  detailLoading.value = true
  try {
    selectedSessionDetail.value = await getConversationSessionDetail(sessionId)
  } catch (error) {
    selectedSessionDetail.value = null
    message.error(error.response?.data?.detail || '加载会话详情失败')
  } finally {
    detailLoading.value = false
  }
}

const handleSelectSession = async (sessionId) => {
  selectedSessionId.value = String(sessionId)
  await loadSessionDetail(sessionId)
}

const handleContinueSession = async (sessionItem) => {
  await router.push({
    path: '/chat',
    query: {
      session: String(sessionItem.id),
      kb: String(sessionItem.knowledge_base_id)
    }
  })
}

function confirmDeleteSession(sessionId) {
  pendingDeleteSessionId.value = sessionId
  showDeleteConfirm.value = true
}

const handleDeleteSession = async () => {
  const sessionId = pendingDeleteSessionId.value
  if (!sessionId) return
  try {
    await deleteConversationSession(sessionId)
    showDeleteConfirm.value = false
    message.success('会话已删除')
    await loadSessions()
    if (selectedSessionId.value === String(sessionId)) {
      const nextSessionId = sessionRecordList.value[0]?.id
      selectedSessionId.value = nextSessionId ? String(nextSessionId) : ''
    }
  } catch (error) {
    message.error(error.response?.data?.detail || '删除会话失败')
  } finally {
    pendingDeleteSessionId.value = null
  }
}

const handleCreateConversation = async () => {
  await router.push('/chat')
}

watch(selectedSessionId, async (sessionId) => {
  if (sessionId) {
    await loadSessionDetail(sessionId)
  } else {
    selectedSessionDetail.value = null
  }
})

onMounted(async () => {
  await loadSessions()
})
</script>

<style scoped>
.sessions-overview-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.toolbar-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 13px;
  color: var(--text-4);
}

.sessions-layout {
  display: grid;
  grid-template-columns: minmax(320px, 0.92fr) minmax(0, 1.4fr);
  gap: 16px;
  align-items: start;
}

.sessions-layout__workspace {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.session-group + .session-group {
  margin-top: 20px;
}

.session-group__title {
  margin-bottom: 10px;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-4);
}

.session-item {
  width: 100%;
  padding: 14px 16px;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background: var(--surface-card);
  text-align: left;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.session-item + .session-item {
  margin-top: 10px;
}

.session-item:hover,
.session-item.is-active {
  border-color: var(--brand-soft-border);
  background: var(--surface-hover);
  box-shadow: 0 12px 28px rgba(37, 99, 235, 0.08);
}

.session-item__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.session-item__actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.session-item__title {
  font-size: 15px;
  font-weight: 700;
  line-height: 1.45;
  color: var(--text-1);
}

.session-item__meta,
.turn-preview-item__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-4);
}

.session-overview-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.turn-preview-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 16px;
}

.turn-preview-item {
  padding: 14px 16px;
  border-radius: 12px;
  background: var(--surface-muted);
  border: 1px solid var(--border-color);
}

.turn-preview-item__label {
  display: inline-block;
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 700;
  color: var(--brand-700);
}

.turn-preview-item__question,
.turn-preview-item__answer {
  line-height: 1.7;
  color: var(--text-2);
}

.turn-preview-item__answer {
  margin-top: 12px;
}

@media (max-width: 1200px) {
  .sessions-overview-grid,
  .sessions-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .session-overview-grid {
    grid-template-columns: 1fr;
  }

  .session-item__header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
