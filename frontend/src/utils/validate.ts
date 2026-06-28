/** 检测 session_id 是否有效（排除 undefined/null 等序列化残留） */
export function isValidSessionId(sid: string | null | undefined): sid is string {
  return !!sid && sid !== 'undefined' && sid !== 'null'
}
