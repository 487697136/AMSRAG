import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { listApiKeys, listProviders } from '@/api/zhiyuan'

const CACHE_TTL = 60_000 // 1 分钟内不重复请求

export const useProviderStore = defineStore('provider', () => {
  const registry = ref({})
  const configuredKeys = ref([])
  const loading = ref(false)
  const lastFetched = ref(null)

  const isStale = computed(() => !lastFetched.value || Date.now() - lastFetched.value > CACHE_TTL)

  const llmProviders = computed(() =>
    [...new Set(
      configuredKeys.value
        .filter((k) => registry.value[k.provider]?.type === 'llm')
        .map((k) => k.provider)
    )]
  )

  const embeddingProviders = computed(() =>
    [...new Set(
      configuredKeys.value
        .filter((k) => registry.value[k.provider]?.type === 'embedding')
        .map((k) => k.provider)
    )]
  )

  const llmKeys = computed(() =>
    configuredKeys.value.filter((k) => registry.value[k.provider]?.type === 'llm')
  )

  const embeddingKeys = computed(() =>
    configuredKeys.value.filter((k) => registry.value[k.provider]?.type === 'embedding')
  )

  async function fetchProviders(force = false) {
    if (!force && !isStale.value && configuredKeys.value.length) return
    loading.value = true
    try {
      const [keys, providers] = await Promise.all([listApiKeys(), listProviders()])
      configuredKeys.value = keys
      registry.value = providers || {}
      lastFetched.value = Date.now()
    } finally {
      loading.value = false
    }
  }

  function invalidate() {
    lastFetched.value = null
  }

  function providerLabel(provider) {
    return registry.value[provider]?.label || provider
  }

  function displayKeyName(k) {
    return k.description || providerLabel(k.provider)
  }

  return {
    registry,
    configuredKeys,
    loading,
    llmProviders,
    embeddingProviders,
    llmKeys,
    embeddingKeys,
    fetchProviders,
    invalidate,
    providerLabel,
    displayKeyName,
  }
})
