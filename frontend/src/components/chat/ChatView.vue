<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useMessageStore } from '@/stores/messageStore'
import { useSessionStore } from '@/stores/sessionStore'
import { useScroll } from '@/composables/useScroll'
import ChatMessage from './ChatMessage.vue'
import ThinkingIndicator from './ThinkingIndicator.vue'

const msgStore = useMessageStore()
const sessionStore = useSessionStore()

const containerRef = ref<HTMLElement | null>(null)
const { onScroll, scrollToBottom } = useScroll(containerRef)

// 诊断完成后禁用选项和历史选项
const isDiagnosisDone = computed(() => msgStore.isDiagnosisDone)

// 新消息到来时滚动到底部
watch(
  () => msgStore.messages.length,
  () => scrollToBottom(),
)

function onSelectChoice(value: string, label: string) {
  if (!sessionStore.currentSessionId) return
  msgStore.sendChoice(value, label, sessionStore.currentSessionId)
}
</script>

<template>
  <div
    ref="containerRef"
    class="chat-scroll flex-1 w-full max-w-3xl overflow-y-auto px-4 py-4 flex flex-col gap-3.5"
    @scroll="onScroll"
  >
    <!-- 空状态欢迎 -->
    <div
      v-if="msgStore.messages.length === 0 && !msgStore.isLoading"
      class="flex-1 flex flex-col items-center justify-center gap-3 text-text-secondary"
    >
      <h2 class="font-brand text-3xl font-bold text-eggplant">灵兰健康</h2>
      <p class="text-lg font-semibold">描述您的症状，AI 将为您逐步分析</p>
    </div>

    <!-- 消息列表 -->
    <ChatMessage
      v-for="msg in msgStore.messages"
      :key="msg.id"
      :message="msg"
      :disabled-choices="isDiagnosisDone"
      @select-choice="onSelectChoice"
    />

    <!-- 思考指示器 -->
    <ThinkingIndicator v-if="msgStore.isLoading" />
  </div>
</template>
