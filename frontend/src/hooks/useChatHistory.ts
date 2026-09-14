import { useCallback, useEffect, useState } from "react"
import { listKbs, type KbSummary } from "@/api/kb"
import { listSessions, type ChatSessionItem } from "@/api/chat"

export interface ChatHistoryGroup {
  kb: KbSummary
  sessions: ChatSessionItem[]
  error: boolean
}

/** Sessions are stored per KB, so the navigation and dashboard share this rollup. */
export function useChatHistory() {
  const [groups, setGroups] = useState<ChatHistoryGroup[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)
  const reload = useCallback(() => {
    setLoading(true)
    setRevision((value) => value + 1)
  }, [])

  useEffect(() => {
    let cancelled = false
    listKbs()
      .then(async ({ knowledge_bases }) => {
        const next = await Promise.all(knowledge_bases.map(async (kb): Promise<ChatHistoryGroup> => {
          try {
            const { sessions } = await listSessions(kb.name)
            return {
              kb,
              sessions: sessions.sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
              error: false,
            }
          } catch {
            return { kb, sessions: [], error: true }
          }
        }))
        if (!cancelled) {
          setGroups(next)
          setError(null)
        }
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason))
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [revision])

  useEffect(() => {
    window.addEventListener("openkb:reload-kbs", reload)
    window.addEventListener("openkb:reload-sessions", reload)
    return () => {
      window.removeEventListener("openkb:reload-kbs", reload)
      window.removeEventListener("openkb:reload-sessions", reload)
    }
  }, [reload])

  return { groups, loading, error, reload }
}
