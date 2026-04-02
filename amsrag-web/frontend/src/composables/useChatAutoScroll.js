import { nextTick, ref } from 'vue'

export function useChatAutoScroll(conversationScrollerRef) {
  const shouldAutoScroll = ref(true)

  const updateAutoScrollFlag = () => {
    const scroller = conversationScrollerRef.value
    if (!scroller) {
      shouldAutoScroll.value = true
      return
    }
    const distanceToBottom = scroller.scrollHeight - (scroller.scrollTop + scroller.clientHeight)
    shouldAutoScroll.value = distanceToBottom < 96
  }

  const handleConversationScroll = () => {
    updateAutoScrollFlag()
  }

  const scrollConversationToBottom = async (behavior = 'auto', force = false) => {
    await nextTick()
    const scroller = conversationScrollerRef.value
    if (!scroller) return
    if (!force && !shouldAutoScroll.value) return
    scroller.scrollTo({ top: scroller.scrollHeight, behavior })
  }

  return {
    shouldAutoScroll,
    updateAutoScrollFlag,
    handleConversationScroll,
    scrollConversationToBottom,
  }
}

