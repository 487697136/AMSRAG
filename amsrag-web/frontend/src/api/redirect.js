export function buildLoginRedirectUrl() {
  if (typeof window === 'undefined') return '/login'
  const current = window.location.pathname + window.location.search + window.location.hash
  const params = new URLSearchParams()
  if (current && current !== '/login') {
    params.set('redirect', current)
  }
  const qs = params.toString()
  return qs ? `/login?${qs}` : '/login'
}

export function hardRedirectToLogin() {
  if (typeof window === 'undefined') return
  window.location.href = buildLoginRedirectUrl()
}

