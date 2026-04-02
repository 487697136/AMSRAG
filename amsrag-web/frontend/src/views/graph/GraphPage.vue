<template>
  <div class="graph-explorer">
    <div class="graph-canvas">
      <VChart
        ref="chartRef"
        class="graph-chart"
        :option="chartOption"
        :autoresize="true"
        @click="handleChartClick"
        @dblclick="handleChartDblClick"
      />
    </div>

    <div class="overlay overlay--top">
      <div class="status-pill">
        <span class="dot" :class="source === 'neo4j' ? 'dot--ok' : (source === 'graphml' ? 'dot--warn' : 'dot--idle')" />
        <span class="status-text">{{ sourceLabel }}</span>
        <span class="sep">|</span>
        <span>节点 {{ count(stats?.node_count) }}</span>
        <span class="sep">|</span>
        <span>关系 {{ count(stats?.edge_count) }}</span>
        <span class="sep">|</span>
        <span>文档 {{ count(kbStats?.document_count) }}</span>
        <span class="sep">|</span>
        <span>切块 {{ count(kbStats?.total_chunks) }}</span>
      </div>
      <div v-if="graphMessage" class="status-hint">{{ graphMessage }}</div>
    </div>

    <div class="overlay overlay--left">
      <div class="glass panel">
        <div class="panel__title">探索</div>
        <n-select v-model:value="selectedKnowledgeBaseId" :options="knowledgeBaseOptions" size="small" />
        <n-input
          v-model:value="keyword"
          clearable
          size="small"
          placeholder="搜索节点名称或 ID"
          @keyup.enter="runSearch"
        >
          <template #prefix><n-icon :component="SearchOutline" /></template>
        </n-input>
        <n-select v-model:value="selectedType" :options="nodeTypeOptions" size="small" />
        <div class="panel__row">
          <n-button size="small" secondary @click="runSearch">搜索</n-button>
          <n-button size="small" quaternary @click="resetExplorer">重置</n-button>
        </div>
      </div>
    </div>

    <div class="overlay overlay--right">
      <div class="glass panel">
        <div class="panel__title">图例与控制</div>
        <n-select v-model:value="layoutMode" :options="layoutOptions" size="small" />
        <div class="legend">
          <div v-for="item in legendList" :key="item.label" class="legend__item">
            <span class="legend__dot" :style="{ background: item.color }" />
            <span class="legend__label">{{ item.label }}</span>
            <span class="legend__count">{{ item.count }}</span>
          </div>
        </div>
        <div class="panel__row">
          <n-button size="small" secondary @click="autoLayout">自动布局</n-button>
          <n-button size="small" quaternary :disabled="!selectedNode" @click="expandNeighbors(2)">扩展邻居</n-button>
        </div>
      </div>
    </div>

    <n-drawer v-model:show="detailOpen" placement="right" :width="420">
      <n-drawer-content body-content-style="padding: 14px 14px 18px">
        <div class="detail">
          <div class="detail__header">
            <div class="detail__title">{{ selectedNode?.label || '节点详情' }}</div>
            <div class="detail__meta">
              <span class="pill">{{ selectedNode?.type || 'unknown' }}</span>
              <span class="pill">关系 {{ selectedRelations.length }}</span>
            </div>
          </div>

          <div v-if="selectedNode" class="detail__section">
            <div class="section-title">核心信息</div>
            <div class="kv">
              <div class="kv__row"><span>ID</span><strong>{{ selectedNode.id }}</strong></div>
              <div class="kv__row"><span>类型</span><strong>{{ selectedNode.type || 'unknown' }}</strong></div>
              <div class="kv__row"><span>来源</span><strong>{{ sourceLabel }}</strong></div>
            </div>
          </div>

          <div v-if="selectedRelations.length" class="detail__section">
            <div class="section-title">关系</div>
            <div class="rels">
              <button
                v-for="rel in selectedRelations"
                :key="rel.key"
                type="button"
                class="rel"
                @click="focusNode(rel.otherId)"
              >
                <div class="rel__head">
                  <strong>{{ rel.otherLabel }}</strong>
                  <span class="rel__dir">{{ rel.direction }}</span>
                </div>
                <div class="rel__badge">{{ rel.relation }}</div>
              </button>
            </div>
          </div>

          <div v-if="selectedNode" class="detail__section">
            <div class="section-title">原始属性</div>
            <div class="kv">
              <div v-for="([k, v]) in rawAttrs" :key="k" class="kv__row">
                <span>{{ k }}</span>
                <strong>{{ stringify(v) }}</strong>
              </div>
            </div>
          </div>

          <div class="detail__actions">
            <n-button type="primary" :disabled="!selectedNode" @click="askFromNode">以此节点发起问答</n-button>
            <n-button secondary :disabled="!selectedNode" @click="expandNeighbors(2)">扩展邻居</n-button>
          </div>
        </div>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NDrawer, NDrawerContent, NIcon, NInput, NSelect, useMessage } from 'naive-ui'
import { SearchOutline } from '@vicons/ionicons5'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { GraphChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import { getKnowledgeBaseGraph, getKnowledgeBaseStats, listKnowledgeBases } from '@/api/zhiyuan'

// vue-echarts v6+ requires explicit ECharts module registration
use([CanvasRenderer, GraphChart, TooltipComponent])

const router = useRouter()
const message = useMessage()

const chartRef = ref(null)
const loading = ref(false)

const knowledgeBaseList = ref([])
const selectedKnowledgeBaseId = ref('')
const keyword = ref('')
const selectedType = ref('all')
const depth = ref(1)
const layoutMode = ref('force')

const nodes = ref([])
const edges = ref([])
const graphMessage = ref('')
const source = ref('unknown')
const kbStats = ref(null)
const stats = ref(null)

const selectedNodeId = ref('')
const detailOpen = ref(false)

const knowledgeBaseOptions = computed(() =>
  knowledgeBaseList.value.map((item) => ({ label: item.name, value: String(item.id) }))
)

const typeSet = computed(() => new Set(nodes.value.map((n) => n.type).filter(Boolean)))
const nodeTypeOptions = computed(() => [
  { label: '全部类型', value: 'all' },
  ...Array.from(typeSet.value).sort().map((t) => ({ label: t, value: t })),
])

const layoutOptions = [
  { label: '力导向', value: 'force' },
  { label: '环形', value: 'circular' },
]

const sourceLabel = computed(() => {
  if (source.value === 'neo4j') return 'Neo4j · 实时图谱'
  if (source.value === 'graphml') return 'GraphML · 回退快照'
  if (source.value === 'memory') return 'NetworkX · 本地图谱'
  if (source.value === 'none') return '暂无图谱数据'
  return '图谱加载中'
})

const count = (value) =>
  value === null || value === undefined || value === '' ? '--' : Number(value).toLocaleString('zh-CN')

const stringify = (value) =>
  Array.isArray(value) ? value.join(', ') : typeof value === 'object' && value !== null ? JSON.stringify(value) : String(value)

const cssVar = (name, fallback) => {
  if (typeof window === 'undefined') return fallback
  const raw = window.getComputedStyle(document.documentElement).getPropertyValue(name)
  return (raw || '').trim() || fallback
}

const colorForType = (type) => {
  const palette = {
    unknown: '#94a3b8',
    PERSON: '#34d399',
    ORGANIZATION: '#a78bfa',
    LOCATION: '#60a5fa',
    EVENT: '#f59e0b',
    BOOK: '#22d3ee',
  }
  return palette[type] || '#60a5fa'
}

const visibleNodes = computed(() => {
  if (selectedType.value === 'all') return nodes.value
  return nodes.value.filter((n) => n.type === selectedType.value)
})
const visibleIds = computed(() => new Set(visibleNodes.value.map((n) => n.id)))
const visibleEdges = computed(() => edges.value.filter((e) => visibleIds.value.has(e.source) && visibleIds.value.has(e.target)))

const legendList = computed(() => {
  const m = new Map()
  visibleNodes.value.forEach((n) => {
    const k = n.type || 'unknown'
    const cur = m.get(k) || { label: k, color: colorForType(k), count: 0 }
    cur.count += 1
    m.set(k, cur)
  })
  return Array.from(m.values()).sort((a, b) => b.count - a.count).slice(0, 12)
})

const nodeMap = computed(() => new Map(nodes.value.map((n) => [n.id, n])))
const selectedNode = computed(() => nodeMap.value.get(selectedNodeId.value) || null)

const visibleIndexById = computed(() => new Map(visibleNodes.value.map((n, idx) => [n.id, idx])))

const selectedRelations = computed(() => {
  if (!selectedNode.value) return []
  return visibleEdges.value
    .filter((e) => e.source === selectedNode.value.id || e.target === selectedNode.value.id)
    .map((e, idx) => {
      const outgoing = e.source === selectedNode.value.id
      const otherId = outgoing ? e.target : e.source
      return {
        key: `${e.id}-${idx}`,
        relation: e.relation || 'RELATED',
        otherId,
        otherLabel: nodeMap.value.get(otherId)?.label || otherId,
        direction: outgoing ? '→' : '←',
      }
    })
})

const rawAttrs = computed(() => {
  if (!selectedNode.value) return []
  const deny = new Set(['name', 'label', 'type', 'id'])
  return Object.entries(selectedNode.value).filter(([k]) => !deny.has(k))
})

const chartOption = computed(() => {
  const labelColor = cssVar('--text-1', '#0f172a')
  const edgeColor = cssVar('--gray-400', '#94a3b8')
  const isDark = cssVar('--page-bg', '#ffffff').toLowerCase() === '#0f172a'

  const data = visibleNodes.value.map((n) => ({
    id: n.id,
    name: n.label || n.id,
    value: n.id,
    category: n.type || 'unknown',
    symbolSize: (() => {
      const d = Number(n.degree || 0)
      return 14 + Math.min(Math.max(d, 0), 10) * 1.2
    })(),
    itemStyle: {
      color: colorForType(n.type || 'unknown'),
      shadowBlur: 14,
      shadowColor: isDark ? 'rgba(37,99,235,0.30)' : 'rgba(37,99,235,0.18)',
    },
    label: { show: false, color: labelColor },
  }))

  const links = visibleEdges.value.map((e) => ({
    source: e.source,
    target: e.target,
    value: e.relation || 'RELATED',
    lineStyle: { opacity: 0.22, width: 1 },
  }))

  const categories = Array.from(new Set(data.map((d) => d.category))).map((c) => ({ name: c }))

  return {
    backgroundColor: 'transparent',
    animation: true,
    tooltip: {
      trigger: 'item',
      formatter: (params) => {
        if (params.dataType === 'edge') return params.data?.value || 'RELATED'
        return `${params.name}<br/>${params.data?.category || 'unknown'}`
      },
    },
    series: [
      {
        type: 'graph',
        layout: layoutMode.value,
        data,
        links,
        categories,
        roam: true,
        draggable: true,
        focusNodeAdjacency: true,
        emphasis: { scale: true },
        force: layoutMode.value === 'force' ? {
          repulsion: 210,
          gravity: 0.055,
          edgeLength: [86, 160],
        } : undefined,
        circular: layoutMode.value === 'circular' ? { rotateLabel: false } : undefined,
        lineStyle: {
          color: isDark ? 'rgba(148,163,184,0.42)' : `${edgeColor}99`,
          curveness: 0.12,
        },
      },
    ],
  }
})

watch(layoutMode, () => {
  // restart layout (especially for force) for immediate feedback
  autoLayout()
})

const highlightNodeInChart = (nodeId) => {
  const inst = chartRef.value?.getEchartsInstance?.()
  if (!inst) return
  const idx = visibleIndexById.value.get(String(nodeId))
  if (idx === undefined) return
  try {
    inst.dispatchAction({ type: 'downplay', seriesIndex: 0 })
    inst.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex: idx })
    inst.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: idx })
  } catch {
    // ignore
  }
}

const fetchKbStats = async () => {
  if (!selectedKnowledgeBaseId.value) return
  try {
    kbStats.value = await getKnowledgeBaseStats(selectedKnowledgeBaseId.value)
  } catch {
    kbStats.value = null
  }
}

const fetchGraph = async ({ nodeId = null, keywordText = null, nextDepth = null } = {}) => {
  if (!selectedKnowledgeBaseId.value) return
  loading.value = true
  try {
    const result = await getKnowledgeBaseGraph(selectedKnowledgeBaseId.value, {
      node_id: nodeId || undefined,
      keyword: keywordText || undefined,
      limit: 200,
      depth: nextDepth ?? depth.value,
    })
    source.value = result.source || (result.fallback === 'graphml' ? 'graphml' : 'neo4j')
    graphMessage.value = result.message || result.error || ''
    stats.value = result.stats || null

    nodes.value = (result.nodes || []).map((n) => ({
      id: String(n.id),
      label: String(n.label || n.name || n.id),
      type: String(n.type || n.entity_type || 'unknown').toUpperCase(),
      ...n,
    }))
    edges.value = (result.edges || []).map((e, idx) => ({
      id: e.id ? String(e.id) : `${e.source}-${e.target}-${idx}`,
      source: String(e.source),
      target: String(e.target),
      relation: String(e.relation || 'RELATED'),
      ...e,
    }))

    // 搜索后自动聚焦（轻量体验，不引入复杂交互）
    if (keywordText) {
      const key = String(keywordText).trim().toLowerCase()
      if (key) {
        const hit = nodes.value.find((n) => String(n.label || '').toLowerCase().includes(key) || String(n.id).toLowerCase().includes(key))
        if (hit) {
          focusNode(hit.id)
          // wait for chart to apply new option first
          setTimeout(() => highlightNodeInChart(hit.id), 0)
        }
      }
    }
  } catch (err) {
    nodes.value = []
    edges.value = []
    stats.value = null
    graphMessage.value = err?.response?.data?.detail || '图谱加载失败'
    message.error(graphMessage.value)
  } finally {
    loading.value = false
  }
}

const runSearch = async () => {
  const k = keyword.value.trim()
  await fetchGraph({ keywordText: k || null, nodeId: null })
}

const resetExplorer = async () => {
  keyword.value = ''
  selectedType.value = 'all'
  depth.value = 1
  selectedNodeId.value = ''
  detailOpen.value = false
  await fetchGraph()
}

const focusNode = (nodeId) => {
  selectedNodeId.value = String(nodeId)
  detailOpen.value = true
  setTimeout(() => highlightNodeInChart(nodeId), 0)
}

const expandNeighbors = async (extraDepth = 2) => {
  if (!selectedNode.value) return
  const next = Math.min((depth.value || 1) + extraDepth, 4)
  depth.value = next
  await fetchGraph({ nodeId: selectedNode.value.id, nextDepth: next })
  focusNode(selectedNode.value.id)
}

const autoLayout = () => {
  const inst = chartRef.value?.getEchartsInstance?.()
  if (inst) inst.setOption(chartOption.value, true)
}

const askFromNode = async () => {
  if (!selectedNode.value) return
  await router.push({ path: '/chat', query: { kb: selectedKnowledgeBaseId.value, q: selectedNode.value.label } })
}

const handleChartClick = (params) => {
  if (params?.dataType !== 'node') return
  focusNode(params.data?.id || params.data?.value || params.name)
}

const handleChartDblClick = async (params) => {
  if (params?.dataType !== 'node') return
  const nid = params.data?.id || params.data?.value || params.name
  selectedNodeId.value = String(nid)
  detailOpen.value = true
  await fetchGraph({ nodeId: String(nid), nextDepth: Math.max(depth.value, 2) })
}

watch(selectedKnowledgeBaseId, async () => {
  selectedNodeId.value = ''
  detailOpen.value = false
  depth.value = 1
  await Promise.all([fetchKbStats(), fetchGraph()])
})

onMounted(async () => {
  knowledgeBaseList.value = await listKnowledgeBases()
  if (knowledgeBaseList.value.length) {
    selectedKnowledgeBaseId.value = String(knowledgeBaseList.value[0].id)
  }
})
</script>

<style scoped>
.graph-explorer {
  position: relative;
  width: 100%;
  height: calc(100svh - 52px);
  min-height: 0;
  background:
    radial-gradient(900px 600px at 20% 10%, rgba(37, 99, 235, 0.10), transparent 62%),
    radial-gradient(760px 520px at 85% 18%, rgba(59, 130, 246, 0.08), transparent 58%),
    linear-gradient(180deg, var(--page-bg) 0%, var(--page-bg) 100%);
  overflow: hidden;
}

.graph-canvas { position: absolute; inset: 0; }
.graph-chart { width: 100%; height: 100%; }

.overlay { position: absolute; z-index: 5; pointer-events: none; }
.overlay--top {
  top: 14px; left: 14px; right: 14px;
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
}
.overlay--left { top: 78px; left: 14px; }
.overlay--right { top: 78px; right: 14px; }

.glass {
  pointer-events: auto;
  background: color-mix(in srgb, var(--surface-card) 78%, transparent);
  border: 1px solid color-mix(in srgb, var(--border-color) 82%, transparent);
  box-shadow: var(--shadow-card);
  backdrop-filter: blur(12px);
  border-radius: 14px;
}
.panel { width: 320px; padding: 12px; display: flex; flex-direction: column; gap: 10px; }
.panel__title { font-size: 12px; font-weight: 800; color: var(--text-2); letter-spacing: 0.4px; }
.panel__row { display: flex; gap: 10px; }

.status-pill {
  pointer-events: auto;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--surface-card) 76%, transparent);
  border: 1px solid color-mix(in srgb, var(--border-color) 82%, transparent);
  color: var(--text-2);
  font-size: 12.5px;
  backdrop-filter: blur(12px);
}
.status-hint {
  pointer-events: auto;
  color: var(--text-3);
  font-size: 12px;
  padding: 8px 10px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--surface-card) 70%, transparent);
  border: 1px solid color-mix(in srgb, var(--border-color) 70%, transparent);
  backdrop-filter: blur(10px);
  max-width: 520px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.dot { width: 8px; height: 8px; border-radius: 999px; }
.dot--ok { background: var(--success-color); }
.dot--warn { background: var(--warning-color); }
.dot--idle { background: var(--gray-400); }
.sep { opacity: 0.35; }

.legend { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.legend__item {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 8px; border-radius: 12px;
  background: color-mix(in srgb, var(--surface-muted) 78%, transparent);
  border: 1px solid color-mix(in srgb, var(--border-color) 76%, transparent);
}
.legend__dot { width: 10px; height: 10px; border-radius: 999px; box-shadow: 0 0 0 4px rgba(59,130,246,0.12); }
.legend__label { flex: 1; min-width: 0; color: var(--text-2); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.legend__count { color: var(--text-4); font-size: 12px; }

.detail__header { padding-bottom: 10px; border-bottom: 1px solid var(--border-color); }
.detail__title { font-size: 16px; font-weight: 900; color: var(--text-1); }
.detail__meta { margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap; }
.pill {
  display: inline-flex; align-items: center; height: 24px; padding: 0 10px;
  border-radius: 999px; background: rgba(37,99,235,0.10);
  border: 1px solid rgba(37,99,235,0.18); color: var(--brand-600);
  font-size: 12px; font-weight: 800;
}
.detail__section { margin-top: 14px; }
.section-title { font-size: 12px; font-weight: 900; color: var(--text-2); margin-bottom: 10px; }
.kv { display: flex; flex-direction: column; gap: 8px; }
.kv__row { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.kv__row span { color: var(--text-4); font-size: 12.5px; }
.kv__row strong { color: var(--text-1); font-size: 12.5px; max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rels { display: flex; flex-direction: column; gap: 10px; }
.rel { border: 1px solid var(--border-color); background: var(--surface-card); border-radius: 14px; padding: 10px 10px; text-align: left; cursor: pointer; }
.rel:hover { border-color: rgba(37,99,235,0.28); box-shadow: 0 10px 22px rgba(15,23,42,0.06); }
.rel__head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.rel__dir { color: var(--text-4); font-size: 12px; }
.rel__badge { margin-top: 6px; font-size: 12px; color: var(--brand-600); font-weight: 800; }
.detail__actions { margin-top: 16px; display: flex; gap: 10px; }

:deep(.overlay .n-input), :deep(.overlay .n-base-selection) {
  --n-color: color-mix(in srgb, var(--surface-muted) 82%, transparent);
  --n-color-focus: color-mix(in srgb, var(--surface-muted) 82%, transparent);
  --n-border: var(--border-color);
  --n-border-hover: var(--border-strong);
  --n-text-color: var(--text-1);
  --n-placeholder-color: var(--text-5);
}

@supports not (color-mix(in srgb, white, black)) {
  .glass,
  .status-pill,
  .status-hint {
    background: rgba(255, 255, 255, 0.82);
  }
  [data-theme='dark'] .glass,
  [data-theme='dark'] .status-pill,
  [data-theme='dark'] .status-hint {
    background: rgba(17, 28, 47, 0.82);
  }
}
</style>
