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
      <div v-if="loading" class="graph-loading">
        <n-spin size="large" />
      </div>
    </div>

    <!-- 顶部状态栏 -->
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

    <!-- 左侧控制面板 -->
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

    <!-- 右侧图例与控制 -->
    <div class="overlay overlay--right">
      <div class="glass panel">
        <div class="panel__title">图例与控制</div>
        <n-select v-model:value="layoutMode" :options="layoutOptions" size="small" />
        <div class="panel__row panel__row--wrap">
          <span class="ctrl-label">节点标签</span>
          <n-select v-model:value="labelMode" :options="labelModeOptions" size="small" style="flex:1;min-width:0" />
        </div>
        <div class="panel__row panel__row--wrap">
          <span class="ctrl-label">边标签</span>
          <n-switch v-model:value="showEdgeLabel" size="small" />
        </div>
        <div class="legend">
          <div v-for="item in legendList" :key="item.label" class="legend__item">
            <span class="legend__dot" :style="{ background: item.color, boxShadow: `0 0 0 3px ${item.color}28` }" />
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

    <!-- 节点详情抽屉 -->
    <n-drawer v-model:show="detailOpen" placement="right" :width="420">
      <n-drawer-content body-content-style="padding: 14px 14px 18px">
        <div class="detail">
          <div class="detail__header">
            <div class="detail__dot" :style="{ background: colorForType(selectedNode?.type || 'unknown') }" />
            <div class="detail__title">{{ selectedNode?.label || '节点详情' }}</div>
            <div class="detail__meta">
              <span class="pill">{{ selectedNode?.type || 'unknown' }}</span>
              <span class="pill">关系 {{ selectedRelations.length }}</span>
              <span class="pill">度数 {{ nodeDegreeMap.get(selectedNodeId) || 0 }}</span>
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
            <div class="section-title">关系 ({{ selectedRelations.length }})</div>
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
import { NButton, NDrawer, NDrawerContent, NIcon, NInput, NSelect, NSpin, NSwitch, useMessage } from 'naive-ui'
import { SearchOutline } from '@vicons/ionicons5'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { GraphChart } from 'echarts/charts'
import { TooltipComponent, LegendComponent } from 'echarts/components'
import { getKnowledgeBaseGraph, getKnowledgeBaseStats, listKnowledgeBases } from '@/api/zhiyuan'

use([CanvasRenderer, GraphChart, TooltipComponent, LegendComponent])

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
const labelMode = ref('auto')   // 'all' | 'auto' | 'important' | 'none'
const showEdgeLabel = ref(false)

const nodes = ref([])
const edges = ref([])
const graphMessage = ref('')
const source = ref('unknown')
const kbStats = ref(null)
const stats = ref(null)

const selectedNodeId = ref('')
const detailOpen = ref(false)

// ─── 选项配置 ───────────────────────────────────────────────────────────────

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

const labelModeOptions = [
  { label: '自动（按重要性）', value: 'auto' },
  { label: '全部显示', value: 'all' },
  { label: '仅重要节点', value: 'important' },
  { label: '隐藏', value: 'none' },
]

// ─── 颜色系统（同时支持中英文实体类型 + 哈希兜底）────────────────────────────

const TYPE_PALETTE = {
  // ── 英文 ──────────────────────────────────────────────────────────────────
  PERSON:         '#34d399',
  ORGANIZATION:   '#a78bfa',
  ORG:            '#a78bfa',
  LOCATION:       '#60a5fa',
  LOC:            '#60a5fa',
  EVENT:          '#f59e0b',
  BOOK:           '#22d3ee',
  PRODUCT:        '#fb923c',
  CONCEPT:        '#e879f9',
  TECHNOLOGY:     '#38bdf8',
  TECH:           '#38bdf8',
  COMPANY:        '#818cf8',
  DEPARTMENT:     '#c084fc',
  INDUSTRY:       '#f472b6',
  FIELD:          '#f472b6',
  GOVERNMENT:     '#4ade80',
  LAW:            '#fbbf24',
  MEDICINE:       '#f87171',
  DISEASE:        '#ef4444',
  UNKNOWN:        '#94a3b8',

  // ── 中文（直接用原始字符串匹配）────────────────────────────────────────────
  人物:   '#f87171',  // 珊瑚红   ─ 人最多，给最醒目颜色
  地点:   '#60a5fa',  // 天蓝     ─ 地点
  场景:   '#38bdf8',  // 浅蓝     ─ 场景
  组织:   '#a78bfa',  // 紫罗兰
  机构:   '#818cf8',  // 靛蓝
  事件:   '#f59e0b',  // 琥珀
  物品:   '#fb923c',  // 橙色
  道具:   '#fdba74',  // 浅橙
  文学作品: '#22d3ee', // 青色
  书籍:   '#67e8f9',  // 淡青
  诗词:   '#a5f3fc',  // 极淡青
  概念:   '#e879f9',  // 粉紫
  思想:   '#d946ef',  // 洋红
  技术:   '#2dd4bf',  // 蒂尔绿
  科技:   '#2dd4bf',
  政府:   '#4ade80',  // 草绿
  法律:   '#fbbf24',  // 金黄
  药物:   '#ef4444',  // 鲜红
  疾病:   '#f43f5e',  // 玫瑰红
  公司:   '#818cf8',  // 蓝紫
  部门:   '#c084fc',  // 紫丁香
  行业:   '#f472b6',  // 玫瑰粉
  时间:   '#94a3b8',  // 银灰
  朝代:   '#fde68a',  // 淡金
  文连:   '#86efac',  // 浅绿
  神话:   '#f0abfc',  // 淡紫
  奴仆:   '#fca5a5',  // 浅珊瑚
  仙人:   '#c4b5fd',  // 淡紫
}

// 哈希颜色：对未知类型生成固定且饱和度高的颜色，而非灰色
const hashColor = (str) => {
  let h = 0
  for (let i = 0; i < str.length; i++) h = (Math.imul(31, h) + str.charCodeAt(i)) | 0
  // 用黄金比例分散色相，饱和度/亮度保持高对比度
  const hue = ((Math.abs(h) % 360) * 137.508) % 360
  return `hsl(${Math.round(hue)}, 72%, 58%)`
}

const colorForType = (type) => {
  if (!type) return TYPE_PALETTE.UNKNOWN
  // 1. 先用原始字符串直接查（支持中文）
  if (TYPE_PALETTE[type]) return TYPE_PALETTE[type]
  // 2. 再用大写英文查
  const upper = String(type).toUpperCase()
  if (TYPE_PALETTE[upper]) return TYPE_PALETTE[upper]
  // 3. 兜底：哈希生成独特颜色，不再是灰色
  return hashColor(String(type))
}

// ─── 过滤后的数据 ─────────────────────────────────────────────────────────────

const visibleNodes = computed(() => {
  if (selectedType.value === 'all') return nodes.value
  return nodes.value.filter((n) => n.type === selectedType.value)
})
const visibleIds = computed(() => new Set(visibleNodes.value.map((n) => n.id)))
const visibleEdges = computed(() =>
  edges.value.filter((e) => visibleIds.value.has(e.source) && visibleIds.value.has(e.target))
)

// ─── 度数计算（基于实际边数据）──────────────────────────────────────────────

const nodeDegreeMap = computed(() => {
  const map = new Map()
  visibleEdges.value.forEach((e) => {
    map.set(e.source, (map.get(e.source) || 0) + 1)
    map.set(e.target, (map.get(e.target) || 0) + 1)
  })
  return map
})

// ─── 辅助函数 ─────────────────────────────────────────────────────────────────

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

// ─── 图例 ────────────────────────────────────────────────────────────────────

const legendList = computed(() => {
  const m = new Map()
  visibleNodes.value.forEach((n) => {
    const k = n.type || 'unknown'
    const cur = m.get(k) || { label: k, color: colorForType(k), count: 0 }
    cur.count += 1
    m.set(k, cur)
  })
  return Array.from(m.values()).sort((a, b) => b.count - a.count).slice(0, 14)
})

// ─── 选中节点 ─────────────────────────────────────────────────────────────────

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

// ─── 颜色工具函数 ─────────────────────────────────────────────────────────────

/**
 * 将颜色与 white/black 按比例混合，始终返回 #rrggbb 字符串（ECharts 渐变 stop 只支持 hex/rgb）。
 * 支持 #rrggbb、hsl(h,s%,l%) 两种输入格式。
 */
const blendHex = (() => {
  // hsl → rgb 辅助（避免依赖浏览器 API，纯计算）
  const hslToRgb = (h, s, l) => {
    s /= 100; l /= 100
    const k = (n) => (n + h / 30) % 12
    const a = s * Math.min(l, 1 - l)
    const f = (n) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)))
    return [Math.round(f(0) * 255), Math.round(f(8) * 255), Math.round(f(4) * 255)]
  }

  return (hex, mix, t) => {
    let r1 = 148, g1 = 163, b1 = 184  // 默认灰
    const r2 = mix === '#ffffff' ? 255 : 0
    const g2 = mix === '#ffffff' ? 255 : 0
    const b2 = mix === '#ffffff' ? 255 : 0

    if (hex && hex.startsWith('#') && hex.length >= 7) {
      r1 = parseInt(hex.slice(1, 3), 16)
      g1 = parseInt(hex.slice(3, 5), 16)
      b1 = parseInt(hex.slice(5, 7), 16)
    } else if (hex && hex.startsWith('hsl')) {
      // 解析 hsl(h, s%, l%) 或 hsl(h s% l%)
      const m = hex.match(/hsl\(\s*([\d.]+)[,\s]+([\d.]+)%[,\s]+([\d.]+)%/)
      if (m) [, r1, g1, b1] = [0, ...hslToRgb(Number(m[1]), Number(m[2]), Number(m[3]))]
    }

    const lerp = (a, b, t) => Math.round(a + (b - a) * t)
    const toHex = (v) => Math.max(0, Math.min(255, v)).toString(16).padStart(2, '0')
    return `#${toHex(lerp(r1, r2, t))}${toHex(lerp(g1, g2, t))}${toHex(lerp(b1, b2, t))}`
  }
})()

// ─── ECharts 配置（核心优化）────────────────────────────────────────────────

const chartOption = computed(() => {
  const isDark = cssVar('--page-bg', '#ffffff').toLowerCase().includes('#0f1')
    || window.document?.documentElement?.dataset?.theme === 'dark'
  const labelColor = isDark ? '#e2e8f0' : '#1e293b'
  const edgeColor = isDark ? 'rgba(148,163,184,0.55)' : 'rgba(100,116,139,0.50)'
  const textBorderColor = isDark ? '#0f172a' : '#ffffff'

  const degMap = nodeDegreeMap.value
  const allDeg = Array.from(degMap.values())
  const maxDeg = allDeg.length ? Math.max(...allDeg) : 1
  const medianDeg = allDeg.length
    ? allDeg.slice().sort((a, b) => a - b)[Math.floor(allDeg.length / 2)]
    : 1

  const nodeCount = visibleNodes.value.length

  // 标签显示判断
  const shouldShowLabel = (deg) => {
    if (labelMode.value === 'all') return true
    if (labelMode.value === 'none') return false
    if (labelMode.value === 'important') return deg >= medianDeg * 1.5
    // auto: 节点少则全显，否则按度数阈值
    if (nodeCount <= 60) return true
    if (nodeCount <= 120) return deg >= medianDeg
    return deg >= medianDeg * 1.5
  }

  // 截断标签
  const truncLabel = (str, maxLen = 8) => {
    if (!str) return ''
    return str.length > maxLen ? str.slice(0, maxLen) + '…' : str
  }

  const data = visibleNodes.value.map((n) => {
    const deg = degMap.get(n.id) || 0
    // 节点大小：按度数平方根映射到 10-48 范围
    const ratio = maxDeg > 0 ? Math.sqrt(deg / maxDeg) : 0
    const symbolSize = 10 + ratio * 38
    const showLabel = shouldShowLabel(deg)
    const color = colorForType(n.type || 'unknown')
    // 字体大小：重要节点更大
    const fontSize = 10 + ratio * 4

    // 用 ECharts linearGradient 给节点球面制造高光渐变，避免纯色扁平感
    const gradientColor = {
      type: 'radial',
      x: 0.35, y: 0.35, r: 0.65,
      colorStops: [
        { offset: 0,   color: blendHex(color, '#ffffff', 0.55) },  // 高光
        { offset: 0.5, color: blendHex(color, '#ffffff', 0.12) },  // 中间
        { offset: 1,   color: blendHex(color, '#000000', 0.18) },  // 暗边
      ],
    }

    return {
      id: n.id,
      name: n.label || n.id,
      value: deg,
      category: n.type || 'unknown',
      symbolSize,
      itemStyle: {
        color: gradientColor,
        borderColor: blendHex(color, '#ffffff', isDark ? 0.45 : 0.65),
        borderWidth: 1.2 + ratio * 1.8,
        shadowBlur: 6 + ratio * 22,
        shadowColor: color + (isDark ? '70' : '55'),
      },
      label: {
        show: showLabel,
        formatter: ({ name }) => truncLabel(name, nodeCount > 100 ? 6 : 10),
        fontSize: Math.round(fontSize),
        fontWeight: deg >= medianDeg ? 700 : 500,
        color: labelColor,
        textBorderColor,
        textBorderWidth: 2.5,
        distance: 4,
        position: layoutMode.value === 'circular' ? 'outside' : 'right',
      },
      emphasis: {
        itemStyle: {
          color: {
            type: 'radial', x: 0.35, y: 0.35, r: 0.65,
            colorStops: [
              { offset: 0,   color: blendHex(color, '#ffffff', 0.72) },
              { offset: 0.5, color: blendHex(color, '#ffffff', 0.25) },
              { offset: 1,   color: color },
            ],
          },
          shadowBlur: 32,
          shadowColor: color + 'aa',
          borderWidth: 3,
          borderColor: '#ffffff',
        },
        label: {
          show: true,
          formatter: ({ name }) => truncLabel(name, 16),
          fontSize: Math.round(fontSize + 2),
          fontWeight: 800,
        },
      },
    }
  })

  const edgeLabelShow = showEdgeLabel.value && visibleEdges.value.length < 200
  const isCircular = layoutMode.value === 'circular'

  const links = visibleEdges.value.map((e) => {
    const sourceDeg = degMap.get(e.source) || 0
    const targetDeg = degMap.get(e.target) || 0
    const relWeight = Math.min((sourceDeg + targetDeg) / (maxDeg * 2 + 1), 1)
    const rel = e.relation || 'RELATED'
    // 边颜色：跟随源节点类型颜色，但降低透明度
    const srcNode = nodeMap.value.get(e.source)
    const srcColor = colorForType(srcNode?.type || 'unknown')
    return {
      source: e.source,
      target: e.target,
      value: rel,
      lineStyle: {
        color: srcColor,
        width: 0.8 + relWeight * 2.0,
        opacity: 0.20 + relWeight * 0.45,
        curveness: isCircular ? 0.32 : 0.08,
      },
      label: {
        show: edgeLabelShow,
        formatter: ({ data: d }) => {
          const t = d?.value || ''
          return t.length > 8 ? t.slice(0, 8) + '…' : t
        },
        fontSize: 9,
        color: isDark ? 'rgba(203,213,225,0.85)' : 'rgba(51,65,85,0.80)',
        textBorderColor,
        textBorderWidth: 2,
      },
      emphasis: {
        lineStyle: { color: srcColor, opacity: 1, width: 3 },
        label: { show: true, fontSize: 11, fontWeight: 700 },
      },
    }
  })

  const categories = Array.from(new Set(data.map((d) => d.category))).map((c) => ({
    name: c,
    itemStyle: { color: colorForType(c) },
  }))

  return {
    backgroundColor: 'transparent',
    animation: true,
    animationDuration: 600,
    animationEasing: 'cubicOut',

    tooltip: {
      trigger: 'item',
      backgroundColor: isDark ? 'rgba(15,23,42,0.92)' : 'rgba(255,255,255,0.96)',
      borderColor: isDark ? 'rgba(59,130,246,0.4)' : 'rgba(59,130,246,0.25)',
      borderWidth: 1,
      textStyle: { color: isDark ? '#f1f5f9' : '#0f172a', fontSize: 13 },
      extraCssText: 'border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,0.14);',
      formatter: (params) => {
        if (params.dataType === 'edge') {
          const rel = params.data?.value || 'RELATED'
          return `<div style="padding:2px 4px">
            <span style="color:${isDark ? '#94a3b8' : '#64748b'};font-size:11px">关系</span>
            <div style="font-weight:800;font-size:13px;margin-top:2px">${rel}</div>
          </div>`
        }
        const deg = degMap.get(params.data?.id) || 0
        const color = colorForType(params.data?.category)
        return `<div style="padding:2px 4px">
          <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
            <span style="width:10px;height:10px;border-radius:50%;background:${color};flex-shrink:0;box-shadow:0 0 0 3px ${color}33;display:inline-block"></span>
            <strong style="font-size:14px">${params.name}</strong>
          </div>
          <div style="color:${isDark ? '#94a3b8' : '#64748b'};font-size:12px;margin-bottom:2px">${params.data?.category || 'unknown'}</div>
          <div style="color:${isDark ? '#94a3b8' : '#64748b'};font-size:12px">关系数：<strong style="color:${color}">${deg}</strong></div>
        </div>`
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
        draggable: !isCircular,
        focusNodeAdjacency: true,

        emphasis: {
          focus: 'adjacency',
          scale: true,
        },

        blur: {
          itemStyle: { opacity: 0.08 },
          label: { opacity: 0.05 },
          lineStyle: { opacity: 0.04 },
        },

        // 力导向参数
        force: !isCircular ? {
          repulsion: Math.max(200, Math.min(600, nodeCount * 3.5)),
          gravity: 0.04,
          edgeLength: [70, Math.max(160, 300 - nodeCount)],
          layoutAnimation: true,
          friction: 0.65,
        } : undefined,

        // 环形参数
        circular: isCircular ? {
          rotateLabel: true,
        } : undefined,

        // 全局 lineStyle 只设曲率；颜色由每条边独立设置（跟随源节点类型色）
        lineStyle: {
          curveness: isCircular ? 0.32 : 0.08,
        },

        // 边箭头（力导向时显示方向）
        edgeSymbol: isCircular ? ['none', 'none'] : ['none', 'arrow'],
        edgeSymbolSize: [0, 7],

        // 选中高亮
        select: {
          itemStyle: {
            shadowBlur: 32,
            borderWidth: 3,
          },
        },
      },
    ],
  }
})

// ─── 布局切换 ─────────────────────────────────────────────────────────────────

watch(layoutMode, () => autoLayout())
watch(labelMode, () => autoLayout())
watch(showEdgeLabel, () => autoLayout())

// ─── 图表高亮 ─────────────────────────────────────────────────────────────────

const highlightNodeInChart = (nodeId) => {
  const inst = chartRef.value?.getEchartsInstance?.()
  if (!inst) return
  const idx = visibleIndexById.value.get(String(nodeId))
  if (idx === undefined) return
  try {
    inst.dispatchAction({ type: 'downplay', seriesIndex: 0 })
    inst.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex: idx })
    inst.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: idx })
  } catch { /* ignore */ }
}

// ─── 数据获取 ─────────────────────────────────────────────────────────────────

const fetchKbStats = async () => {
  if (!selectedKnowledgeBaseId.value) return
  try { kbStats.value = await getKnowledgeBaseStats(selectedKnowledgeBaseId.value) }
  catch { kbStats.value = null }
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

    if (keywordText) {
      const key = String(keywordText).trim().toLowerCase()
      if (key) {
        const hit = nodes.value.find(
          (n) => String(n.label || '').toLowerCase().includes(key) || String(n.id).toLowerCase().includes(key)
        )
        if (hit) {
          focusNode(hit.id)
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

// ─── 交互操作 ─────────────────────────────────────────────────────────────────

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
  // 在 await 之前先捕获 id，避免 fetchGraph 完成后 selectedNode 因响应式更新变 null
  const nodeId = selectedNode.value.id
  const next = Math.min((depth.value || 1) + extraDepth, 4)
  depth.value = next
  await fetchGraph({ nodeId, nextDepth: next })
  focusNode(nodeId)
}

const autoLayout = () => {
  const inst = chartRef.value?.getEchartsInstance?.()
  if (inst) inst.setOption(chartOption.value, true)
}

const askFromNode = async () => {
  if (!selectedNode.value) return
  // 在 await 之前先捕获属性，防止异步期间响应式变化
  const label = selectedNode.value.label
  const kb = selectedKnowledgeBaseId.value
  await router.push({ path: '/chat', query: { kb, q: label } })
}

const handleChartClick = (params) => {
  if (params?.dataType !== 'node') return
  // params.data 极少数情况下可能为 null（ECharts 边界情况），需防御处理
  const nid = params.data?.id ?? params.data?.name ?? params.name
  if (nid == null) return
  focusNode(String(nid))
}

const handleChartDblClick = async (params) => {
  if (params?.dataType !== 'node') return
  const nid = params.data?.id ?? params.data?.name ?? params.name
  if (nid == null) return
  const nodeIdStr = String(nid)
  selectedNodeId.value = nodeIdStr
  detailOpen.value = true
  await fetchGraph({ nodeId: nodeIdStr, nextDepth: Math.max(depth.value, 2) })
}

// ─── 监听与初始化 ─────────────────────────────────────────────────────────────

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
/* ─── 布局容器 ──────────────────────────────────────────────────────────────── */
.graph-explorer {
  position: relative;
  width: 100%;
  height: calc(100svh - 52px);
  min-height: 0;
  background:
    radial-gradient(900px 600px at 20% 10%, rgba(37, 99, 235, 0.08), transparent 62%),
    radial-gradient(760px 520px at 85% 18%, rgba(59, 130, 246, 0.06), transparent 58%),
    radial-gradient(600px 500px at 50% 90%, rgba(168, 85, 247, 0.05), transparent 60%),
    linear-gradient(180deg, var(--page-bg) 0%, var(--page-bg) 100%);
  overflow: hidden;
}

.graph-canvas { position: absolute; inset: 0; }
.graph-chart  { width: 100%; height: 100%; }

.graph-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.08);
  pointer-events: none;
}

/* ─── 浮层 ──────────────────────────────────────────────────────────────────── */
.overlay           { position: absolute; z-index: 5; pointer-events: none; }
.overlay--top      { top: 14px; left: 14px; right: 14px; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.overlay--left     { top: 78px; left: 14px; }
.overlay--right    { top: 78px; right: 14px; }

/* ─── 玻璃面板 ──────────────────────────────────────────────────────────────── */
.glass {
  pointer-events: auto;
  background: color-mix(in srgb, var(--surface-card) 82%, transparent);
  border: 1px solid color-mix(in srgb, var(--border-color) 80%, transparent);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.10), 0 2px 8px rgba(0, 0, 0, 0.06);
  backdrop-filter: blur(16px);
  border-radius: 14px;
}

.panel {
  width: 240px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.panel__title {
  font-size: 11px;
  font-weight: 800;
  color: var(--text-3);
  letter-spacing: 0.8px;
  text-transform: uppercase;
}

.panel__row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.panel__row--wrap {
  flex-wrap: nowrap;
}

.ctrl-label {
  font-size: 12px;
  color: var(--text-3);
  white-space: nowrap;
  flex-shrink: 0;
  min-width: 44px;
}

/* ─── 顶部状态栏 ────────────────────────────────────────────────────────────── */
.status-pill {
  pointer-events: auto;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 9px 14px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--surface-card) 80%, transparent);
  border: 1px solid color-mix(in srgb, var(--border-color) 80%, transparent);
  color: var(--text-2);
  font-size: 12.5px;
  backdrop-filter: blur(14px);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
}

.status-hint {
  pointer-events: auto;
  color: var(--text-3);
  font-size: 12px;
  padding: 8px 12px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--surface-card) 72%, transparent);
  border: 1px solid color-mix(in srgb, var(--border-color) 70%, transparent);
  backdrop-filter: blur(12px);
  max-width: 520px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dot        { width: 8px; height: 8px; border-radius: 999px; flex-shrink: 0; }
.dot--ok    { background: var(--success-color); box-shadow: 0 0 0 3px rgba(52, 211, 153, 0.25); }
.dot--warn  { background: var(--warning-color); box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.25); }
.dot--idle  { background: var(--gray-400); }
.sep        { opacity: 0.28; }

/* ─── 图例 ──────────────────────────────────────────────────────────────────── */
.legend {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
  max-height: 220px;
  overflow-y: auto;
}

.legend__item {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 5px 8px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--surface-muted) 80%, transparent);
  border: 1px solid color-mix(in srgb, var(--border-color) 70%, transparent);
  transition: background 0.15s;
}

.legend__item:hover {
  background: color-mix(in srgb, var(--surface-muted) 100%, transparent);
}

.legend__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.legend__label {
  flex: 1;
  min-width: 0;
  color: var(--text-2);
  font-size: 11.5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.legend__count {
  color: var(--text-4);
  font-size: 11px;
  font-weight: 600;
}

/* ─── 节点详情抽屉 ──────────────────────────────────────────────────────────── */
.detail__header {
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.detail__dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  flex-shrink: 0;
}

.detail__title  { font-size: 16px; font-weight: 900; color: var(--text-1); line-height: 1.3; }
.detail__meta   { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; }

.pill {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 9px;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.08);
  border: 1px solid rgba(37, 99, 235, 0.16);
  color: var(--brand-600);
  font-size: 11.5px;
  font-weight: 700;
}

.detail__section  { margin-top: 14px; }
.section-title    { font-size: 11px; font-weight: 900; color: var(--text-3); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.6px; }

.kv               { display: flex; flex-direction: column; gap: 7px; }
.kv__row          { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.kv__row span     { color: var(--text-4); font-size: 12px; flex-shrink: 0; }
.kv__row strong   { color: var(--text-1); font-size: 12px; max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: right; }

.rels             { display: flex; flex-direction: column; gap: 8px; }
.rel {
  border: 1px solid var(--border-color);
  background: var(--surface-card);
  border-radius: 12px;
  padding: 9px 10px;
  text-align: left;
  cursor: pointer;
  transition: all 0.15s;
}
.rel:hover        { border-color: rgba(37, 99, 235, 0.30); box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06); transform: translateY(-1px); }
.rel__head        { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.rel__dir         { color: var(--text-4); font-size: 12px; }
.rel__badge       { margin-top: 4px; font-size: 11.5px; color: var(--brand-600); font-weight: 700; }

.detail__actions  { margin-top: 16px; display: flex; gap: 10px; }

/* ─── Naive UI 样式覆盖 ─────────────────────────────────────────────────────── */
:deep(.overlay .n-input),
:deep(.overlay .n-base-selection) {
  --n-color: color-mix(in srgb, var(--surface-muted) 85%, transparent);
  --n-color-focus: color-mix(in srgb, var(--surface-muted) 85%, transparent);
  --n-border: var(--border-color);
  --n-border-hover: var(--border-strong);
  --n-text-color: var(--text-1);
  --n-placeholder-color: var(--text-5);
}

@supports not (color-mix(in srgb, white, black)) {
  .glass,
  .status-pill,
  .status-hint {
    background: rgba(255, 255, 255, 0.85);
  }
  [data-theme='dark'] .glass,
  [data-theme='dark'] .status-pill,
  [data-theme='dark'] .status-hint {
    background: rgba(17, 28, 47, 0.85);
  }
}
</style>
