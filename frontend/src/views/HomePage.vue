<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useSessionStore } from '@/stores/sessionStore'
import { useMessageStore } from '@/stores/messageStore'
import { useAuthStore } from '@/stores/authStore'
import { maskPII } from '@/utils/piiMasker'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import AppHeader from '@/components/layout/AppHeader.vue'
import ChatView from '@/components/chat/ChatView.vue'
import ChatInput from '@/components/chat/ChatInput.vue'
import EmergencyAlert from '@/components/common/EmergencyAlert.vue'
import ProfileModal from '@/components/profile/ProfileModal.vue'

const sessionStore = useSessionStore()
const msgStore = useMessageStore()
const authStore = useAuthStore()

const showProfile = ref(false)
const showEmergency = ref(false)
const emergencyRedFlags = ref<string[]>([])
const emergencyGuidance = ref('')

onMounted(async () => {
  await sessionStore.fetchSessions()
  await authStore.fetchProfile()
})

/** 点击侧边栏会话 */
async function onSelectSession(sid: string) {
  msgStore.cancelRequest()
  sessionStore.selectSession(sid)
  try {
    await msgStore.loadMessages(sid)
  } catch {
    // 加载失败已在 store 中处理
  }
}

/** 删除会话 */
async function onDeleteSession(sid: string) {
  await sessionStore.deleteSession(sid)
  if (sessionStore.currentSessionId === sid) {
    msgStore.clearMessages()
  }
}

/** 新建会话 */
function onNewSession() {
  msgStore.cancelRequest()
  sessionStore.clearCurrentSession()
  msgStore.clearMessages()
}

/** 发送消息 */
async function onSendMessage(text: string) {
  // PII 脱敏前置（安全红线 #4）
  const sanitized = maskPII(text)

  // 如果还没有会话，自动创建
  if (!sessionStore.currentSessionId) {
    const session = await sessionStore.createSession()
    if (!session) return
    sessionStore.currentSessionId = session.session_id
    await sessionStore.fetchSessions()
  }

  // 防御：确保会话 ID 有效
  const sid = sessionStore.currentSessionId
  if (!sid || sid === 'undefined' || sid === 'null') {
    console.error('Invalid session ID, aborting send')
    return
  }
  // 用户看到原始输入，但发送给后端的是脱敏版本
  msgStore.addUserMessage(text, sid)
  try {
    await msgStore.sendMessage(sanitized, sid)
    // 刷新侧边栏（更新轮数/标题）
    await sessionStore.fetchSessions()
  } catch {
    // 错误已在 store 中处理
  }
}

/** 输入框 placeholder */
const inputPlaceholder = () => {
  if (msgStore.isDiagnosisDone) return '诊断已完成，可新建会话继续'
  return '描述您的症状...'
}
</script>

<template>
  <div class="flex w-full h-full overflow-hidden bg-white">
    <!-- 侧边栏 -->
    <AppSidebar
      @select-session="onSelectSession"
      @delete-session="onDeleteSession"
      @new-session="onNewSession"
      @open-profile="showProfile = true"
    />

    <!-- 主聊天区 -->
    <main class="flex-1 flex flex-col items-center min-w-0 bg-lavender">
      <AppHeader />
      <ChatView />
      <ChatInput
        :disabled="msgStore.isDiagnosisDone"
        :placeholder="inputPlaceholder()"
        @send="onSendMessage"
      />
    </main>

    <!-- 紧急弹窗 -->
    <EmergencyAlert
      :show="showEmergency"
      :red-flags="emergencyRedFlags"
      :guidance="emergencyGuidance"
      @close="showEmergency = false"
    />

    <!-- 个人信息弹窗 -->
    <ProfileModal
      :show="showProfile"
      @close="showProfile = false"
    />
  </div>
</template>
