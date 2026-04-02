import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { getKnowledgeBaseStats, listKnowledgeBases } from '@/api/zhiyuan'

const CACHE_TTL = 30_000 // 30s 内不重复请求

export const useKnowledgeBaseStore = defineStore('knowledgeBase', () => {
  const list = ref([])
  const statsCache = ref({})
  const loading = ref(false)
  const lastFetched = ref(null)

  const isStale = computed(() => !lastFetched.value || Date.now() - lastFetched.value > CACHE_TTL)

  const readyCount = computed(() => list.value.filter((kb) => kb.is_initialized).length)
  const documentTotal = computed(() => list.value.reduce((s, kb) => s + (kb.document_count || 0), 0))
  const chunkTotal = computed(() => list.value.reduce((s, kb) => s + (kb.total_chunks || 0), 0))

  async function fetchList(force = false) {
    if (!force && !isStale.value && list.value.length) return list.value
    loading.value = true
    try {
      list.value = await listKnowledgeBases()
      lastFetched.value = Date.now()
    } finally {
      loading.value = false
    }
    return list.value
  }

  async function fetchStats(kbId, force = false) {
    if (!force && statsCache.value[kbId]) return statsCache.value[kbId]
    const stats = await getKnowledgeBaseStats(kbId)
    statsCache.value[kbId] = stats
    return stats
  }

  function invalidate(kbId) {
    if (kbId) {
      delete statsCache.value[kbId]
    } else {
      lastFetched.value = null
      statsCache.value = {}
    }
  }

  return {
    list,
    loading,
    readyCount,
    documentTotal,
    chunkTotal,
    fetchList,
    fetchStats,
    invalidate,
  }
})
