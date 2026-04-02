import { marked } from 'marked'
import DOMPurify from 'dompurify'

marked.setOptions({ breaks: true, gfm: true })

const ALLOWED_TAGS = [
  'a', 'p', 'br', 'hr',
  'strong', 'em', 'del',
  'blockquote',
  'code', 'pre',
  'ul', 'ol', 'li',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'table', 'thead', 'tbody', 'tr', 'th', 'td',
]
const ALLOWED_ATTR = ['href', 'title', 'target', 'rel', 'class']

let purifierInitialized = false
const initPurifierOnce = () => {
  if (purifierInitialized) return
  purifierInitialized = true

  DOMPurify.addHook('afterSanitizeAttributes', (node) => {
    if (node?.tagName?.toLowerCase() !== 'a') return
    const href = node.getAttribute('href') || ''
    if (!href) return

    // For external links, force safe new-tab behavior.
    if (/^https?:\/\//i.test(href)) {
      node.setAttribute('target', '_blank')
      node.setAttribute('rel', 'noopener noreferrer')
    }
  })
}

export function useMarkdownRenderer() {
  initPurifierOnce()
  const cache = new Map()

  const renderMarkdown = (text) => {
    if (!text) return ''
    const key = String(text)
    const hit = cache.get(key)
    if (hit !== undefined) return hit

    const rendered = DOMPurify.sanitize(marked.parse(key), {
      ALLOWED_TAGS,
      ALLOWED_ATTR,
    })

    cache.set(key, rendered)
    // Simple size cap to avoid unbounded growth.
    if (cache.size > 200) {
      const firstKey = cache.keys().next().value
      cache.delete(firstKey)
    }

    return rendered
  }

  return { renderMarkdown }
}

