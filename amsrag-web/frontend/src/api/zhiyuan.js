import api from '@/api'
import { useAuthStore } from '@/stores/auth'
import { hardRedirectToLogin } from '@/api/redirect'

export const queryModeOptions = [
  { label: '文档检索', value: 'naive' },
  { label: '图谱局部检索', value: 'local' },
  { label: '图谱全局分析', value: 'global' },
  { label: '图谱混合检索', value: 'global_local' },
  { label: '关键词检索', value: 'bm25' }
]

export async function listKnowledgeBases(params = {}) {
  const response = await api.get('/knowledge-bases/', { params })
  return response.data
}

export async function createKnowledgeBase(payload) {
  const response = await api.post('/knowledge-bases/', payload)
  return response.data
}

export async function deleteKnowledgeBase(kbId) {
  await api.delete(`/knowledge-bases/${kbId}`)
}

export async function rebuildKnowledgeBase(kbId) {
  const response = await api.post(`/knowledge-bases/${kbId}/rebuild`)
  return response.data
}

export async function cleanupKnowledgeBase(kbId) {
  const response = await api.post(`/knowledge-bases/${kbId}/cleanup`)
  return response.data
}

export async function getKnowledgeBaseStats(kbId) {
  const response = await api.get(`/knowledge-bases/${kbId}/stats`)
  return response.data
}

export async function getKnowledgeBaseGraph(kbId, params = {}) {
  const response = await api.get(`/knowledge-bases/${kbId}/graph`, { params })
  return response.data
}

export async function listDocumentsByKnowledgeBase(kbId, params = {}) {
  const response = await api.get('/documents/', {
    params: {
      kb_id: kbId,
      ...params
    }
  })
  return response.data
}

export async function uploadDocument(kbId, file) {
  const formData = new FormData()
  formData.append('kb_id', String(kbId))
  formData.append('file', file)
  const response = await api.post('/documents/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
  return response.data
}

export async function deleteDocument(documentId) {
  await api.delete(`/documents/${documentId}`)
}

export async function reprocessDocument(documentId) {
  const response = await api.post(`/documents/${documentId}/reprocess`)
  return response.data
}

export async function executeQueryStream(payload, { signal, onMessage } = {}) {
  const authStore = useAuthStore()
  const response = await fetch('/api/v1/query/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(authStore.token ? { Authorization: `Bearer ${authStore.token}` } : {})
    },
    body: JSON.stringify(payload),
    signal
  })

  if (response.status === 401) {
    authStore.logout()
    hardRedirectToLogin()
    throw new Error('Authentication expired.')
  }

  if (!response.ok || !response.body) {
    let detail = 'Request failed.'
    try {
      const errorData = await response.json()
      detail = errorData.detail || detail
    } catch {
      detail = response.statusText || detail
    }
    throw new Error(detail)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let finalPayload = null

  const flushEventBlock = async (block) => {
    if (signal?.aborted) return
    const dataLines = block
      .split('\n')
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trim())

    if (!dataLines.length) return
    const payloadText = dataLines.join('\n')
    if (!payloadText) return

    const parsed = JSON.parse(payloadText)
    const handlerResult = onMessage?.(parsed)
    if (handlerResult instanceof Promise) {
      await handlerResult
    }
    if (parsed.done) {
      finalPayload = parsed
    }
  }

  try {
    while (true) {
      if (signal?.aborted) break
      const { done, value } = await reader.read()
      if (signal?.aborted) break
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done })

      const eventBlocks = buffer.split('\n\n')
      buffer = eventBlocks.pop() || ''
      for (const block of eventBlocks) {
        if (signal?.aborted) break
        await flushEventBlock(block)
      }

      if (done) break
    }
  } catch (err) {
    // If the caller aborted the request, treat it as a clean stop.
    if (signal?.aborted) {
      try { await reader.cancel() } catch {}
      return null
    }
    throw err
  }

  if (!signal?.aborted && buffer.trim()) {
    await flushEventBlock(buffer)
  }

  return finalPayload
}

export async function listConversationSessions(params = {}) {
  const response = await api.get('/query/sessions', { params })
  return response.data
}

export async function getConversationSessionDetail(sessionId, params = {}) {
  const response = await api.get(`/query/sessions/${sessionId}`, { params })
  return response.data
}

export async function deleteConversationSession(sessionId, params = {}) {
  await api.delete(`/query/sessions/${sessionId}`, { params })
}

export async function listApiKeys() {
  const response = await api.get('/api-keys/')
  return response.data
}

export async function listProviders() {
  const response = await api.get('/api-keys/providers')
  return response.data
}

export async function getRuntimeStatus() {
  const response = await api.get('/api-keys/runtime-status')
  return response.data
}

export async function saveApiKey(payload) {
  const response = await api.post('/api-keys/', payload)
  return response.data
}

export async function deleteApiKey(keyId) {
  await api.delete(`/api-keys/${keyId}`)
}

export async function fetchCurrentUser() {
  const response = await api.get('/auth/me')
  return response.data
}

export async function changePassword(payload) {
  const response = await api.post('/auth/change-password', payload)
  return response.data
}