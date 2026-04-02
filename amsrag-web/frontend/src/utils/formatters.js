export function formatDateTime(value) {
  if (!value) return '--'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return String(value)
  }

  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date)
}

export function formatRelativeGroup(value) {
  if (!value) return '更早'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '更早'

  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const target = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  const diffDays = Math.floor((today - target) / 86400000)

  if (diffDays <= 0) return '今天'
  if (diffDays <= 7) return '近 7 天'
  return '更早'
}

export function formatBytes(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '--'
  }

  const units = ['B', 'KB', 'MB', 'GB']
  let size = Number(value)
  let unitIndex = 0
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024
    unitIndex += 1
  }
  return `${size.toFixed(unitIndex === 0 ? 0 : 2)}${units[unitIndex]}`
}

export function formatDocumentStatus(status) {
  const normalized = String(status || '').toLowerCase()
  if (normalized === 'completed') return '已完成'
  if (normalized === 'processing') return '处理中'
  if (normalized === 'pending') return '待处理'
  if (normalized === 'failed') return '失败'
  return status || '--'
}

export function statusToneFromDocument(status) {
  const normalized = String(status || '').toLowerCase()
  if (normalized === 'completed') return 'success'
  if (normalized === 'processing' || normalized === 'pending') return 'warning'
  return 'default'
}

export function statusToneFromKnowledgeBase(item) {
  if (!item) return 'default'
  if (item.is_initialized) return 'success'
  if (item.document_count > 0) return 'warning'
  return 'default'
}

export function statusLabelFromKnowledgeBase(item) {
  if (!item) return '未配置'
  if (item.is_initialized) return '已就绪'
  if (item.document_count > 0) return '待构建'
  return '空知识库'
}