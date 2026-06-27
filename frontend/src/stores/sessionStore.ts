import { defineStore } from 'pinia'
import { ref } from 'vue'
import { sessionsApi } from '@/api/sessions'
import type { Session } from '@/types/session'

export const useSessionStore = defineStore('session', () => {
  const sessions = ref<Session[]>([])
  const currentSessionId = ref<string | null>(null)

  /** 加载会话列表 */
  async function fetchSessions() {
    try {
      const res = await sessionsApi.listSessions()
      // 防御：过滤掉 session_id 无效的条目
      sessions.value = (res.data || []).filter(
        s => s.session_id && s.session_id !== 'undefined' && s.session_id !== 'null',
      )
    } catch (e) {
      console.error('fetchSessions:', e)
    }
  }

  /** 创建新会话 */
  async function createSession(): Promise<Session | null> {
    try {
      const session = await sessionsApi.createSession()
      sessions.value.unshift(session)
      return session
    } catch (e) {
      console.error('createSession:', e)
      return null
    }
  }

  /** 删除会话 */
  async function deleteSession(sid: string) {
    // 防御：拒绝无效 session_id
    if (!sid || sid === 'undefined' || sid === 'null') return
    try {
      await sessionsApi.deleteSession(sid)
      if (currentSessionId.value === sid) {
        currentSessionId.value = null
      }
      sessions.value = sessions.value.filter(s => s.session_id !== sid)
    } catch (e) {
      console.error('deleteSession:', e)
    }
  }

  /** 切换当前会话（只改 ID，消息加载由 messageStore 负责） */
  function selectSession(sid: string) {
    currentSessionId.value = sid
  }

  /** 清空当前会话选择 */
  function clearCurrentSession() {
    currentSessionId.value = null
  }

  return {
    sessions,
    currentSessionId,
    fetchSessions,
    createSession,
    deleteSession,
    selectSession,
    clearCurrentSession,
  }
})
